# portal_app/modules/tickets/shared.py
from __future__ import annotations

import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import streamlit as st

from services.auditoria import registrar_accion
from services.tickets_store import (
    create_ticket as _create_ticket,
    list_tickets as _list_tickets,
    get_ticket_by_id as _get_ticket_by_id,
    update_ticket as _update_ticket,
)

# Catálogos UI
STATUSES = ["Nuevo", "En Proceso", "Cancelado", "Concluido"]
ANALYSTS = ["Sin asignar", "Abel", "Sasha", "Adrian", "Heidi"]

TICKET_NOTIFICATION_EMAILS = [
    "data.analyst@palosgarza.com",
    "aldo.sanchez@palosgarzalogistics.com",
]


def now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_store():
    """
    Ya no usamos JSON. Se deja por compat con tus pantallas.
    """
    return


def list_tickets() -> List[Dict[str, Any]]:
    return _list_tickets(limit=500)


def get_ticket(ticket_id: int) -> Optional[Dict[str, Any]]:
    return _get_ticket_by_id(ticket_id)


def add_ticket(ticket: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compat: antes guardabas en JSON. Ahora inserta en Supabase.
    """
    return _create_ticket(ticket)


def update_ticket(
    ticket_id: int,
    *,
    estatus: Optional[str] = None,
    assigned_to: Optional[str] = None,
    comentarios: Optional[str] = None,
    updated_by: Optional[str] = None,
) -> bool:
    """
    Compat: antes regresaba True/False. Aquí actualiza en Supabase.
    """
    changes: Dict[str, Any] = {"updated_at": now_iso_utc()}

    if estatus is not None:
        changes["estatus"] = estatus
    if assigned_to is not None:
        changes["assigned_to"] = assigned_to
    if comentarios is not None:
        changes["comentarios"] = comentarios
    if updated_by is not None:
        changes["updated_by"] = updated_by

    try:
        _update_ticket(ticket_id, changes)
        return True
    except Exception:
        return False


def counts_by_status() -> Dict[str, int]:
    rows = _list_tickets(limit=500)
    out = {s: 0 for s in STATUSES}
    for r in rows:
        s = (r.get("estatus") or "Nuevo")
        if s not in out:
            out[s] = 0
        out[s] += 1
    return out


def build_mailto(to_emails, subject: str, body: str) -> str:
    to = ",".join(to_emails)
    return "mailto:{}?subject={}&body={}".format(
        urllib.parse.quote(to),
        urllib.parse.quote(subject),
        urllib.parse.quote(body),
    )


def get_secret(key: str, default=None):
    """
    Lee secretos sin romper en local/codespaces cuando no hay secrets.toml.
    Prioridad:
    1) st.secrets
    2) variables de entorno
    """
    import os

    val = None
    try:
        val = st.secrets.get(key, None)
    except Exception:
        val = None

    if val is None:
        val = os.getenv(key)

    return default if val is None else val


def log_accion(accion: str, detalle: dict | None = None) -> None:
    """Wrapper de auditoría — centraliza el nombre del módulo 'complementarias'."""
    registrar_accion("complementarias", accion, detalle)
