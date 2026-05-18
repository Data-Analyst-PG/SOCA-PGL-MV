from ui.components import page_banner, section_header, alert, divider
# portal_app/modules/gestion_solicitudes/shared.py
# ─────────────────────────────────────────────────────────────────────────────
# Shared combinado para el módulo de Seguimiento/Gestión.
# Contiene helpers que usan tanto complementarias.py como tickets.py
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import os
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import streamlit as st

from services.supabase_client import get_authed_client, current_user
from services.tickets_store import (
    create_ticket as _create_ticket,
    list_tickets as _list_tickets,
    get_ticket_by_id as _get_ticket_by_id,
    update_ticket as _update_ticket,
)


# ═══════════════════════════════════════════════════════════════════════════════
# FUNCIONES COMPARTIDAS (usadas por AMBOS)
# ═══════════════════════════════════════════════════════════════════════════════

def get_secret(key: str, default=None):
    """
    Lee secretos sin romper en local/codespaces cuando no hay secrets.toml.
    Prioridad: 1) st.secrets  2) variables de entorno
    """
    val = None
    try:
        val = st.secrets.get(key, None)
    except Exception:
        val = None

    if val is None:
        val = os.getenv(key)

    return default if val is None else val


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_profile_name(user_id: str) -> str:
    """Obtiene el full_name del usuario logueado desde la tabla profiles."""
    if not user_id:
        return ""
    try:
        supabase = get_supabase_client()
        res = (
            supabase.table("profiles")
            .select("full_name")
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        return (res.data or {}).get("full_name") or ""
    except Exception:
        return ""


# ═══════════════════════════════════════════════════════════════════════════════
# FUNCIONES PARA COMPLEMENTARIAS (usadas por complementarias.py)
# ═══════════════════════════════════════════════════════════════════════════════

EMPRESAS = ["Set Freight", "Lincoln Freight", "Set Logis Plus", "Picus", "Igloo"]

def _title_case(s: str) -> str:
    return " ".join(w.capitalize() for w in str(s).strip().split())

SUCURSALES_POR_EMPRESA = {
    "Lincoln Freight": [],
    "Picus": ["Carrier RL", "Carrier RC", "Plus NLD", "Plus QRO", "Logistica"],
    "Igloo": ["Carrier", "Plus", "Logistica"],
    "Set Freight": [
        _title_case(x)
        for x in [
            "CARGAR", "CHICAGO", "CONSOLIDADO", "CONSOLIDADO QUERETARO",
            "DALLAS", "GUADALAJARA", "LEON", "LINCOLN LOGISTICS",
            "LUIS MONCAYO", "MG HAULERS", "MONTERREY", "NUEVO LAREDO",
            "QUERETARO", "RAMOS ARIZPE", "ROLANDO ALFARO", "SLP LOGISTICS",
        ]
    ],
    "Set Logis Plus": [
        _title_case(x)
        for x in [
            "BASICOS GJ", "AG FLEET (ROLANDO)", "AURA TRANSPORT",
            "JOEDAN TRANSPORT", "EFRAIN GARCIA",
        ]
    ],
}


def get_supabase_client():
    """Siempre regresa el cliente con JWT para RLS."""
    return get_authed_client()


def es_plataforma_logismex(plataforma: str) -> bool:
    """Retorna True si la plataforma contiene 'LOGISMEX'."""
    if not plataforma:
        return False
    return "LOGISMEX" in plataforma.upper()


# ═══════════════════════════════════════════════════════════════════════════════
# FUNCIONES PARA TICKETS (usadas por tickets.py)
# ═══════════════════════════════════════════════════════════════════════════════

STATUSES = ["Nuevo", "En Proceso", "Cancelado", "Concluido"]
ANALYSTS = ["Sin asignar", "Abel", "Sasha", "Adrian", "Heidi"]


def init_store():
    """Compat: ya no usamos JSON."""
    return


def list_tickets() -> List[Dict[str, Any]]:
    return _list_tickets(limit=500)


def get_ticket(ticket_id: int) -> Optional[Dict[str, Any]]:
    return _get_ticket_by_id(ticket_id)


def update_ticket(
    ticket_id: int,
    *,
    estatus: Optional[str] = None,
    assigned_to: Optional[str] = None,
    comentarios: Optional[str] = None,
    updated_by: Optional[str] = None,
) -> bool:
    """Actualiza ticket en Supabase."""
    changes: Dict[str, Any] = {"updated_at": now_utc_iso()}

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
