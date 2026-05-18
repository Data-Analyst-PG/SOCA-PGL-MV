# portal_app/services/tickets_store.py
# ─────────────────────────────────────────────────────────────────────────────
# CRUD de tickets contra Supabase
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations
from typing import Any, Dict, List, Optional
from services.supabase_client import get_authed_client


def create_ticket(data: Dict[str, Any]) -> Dict[str, Any]:
    """Inserta un ticket y retorna el registro creado."""
    sb = get_authed_client()
    res = sb.table("tickets").insert(data).execute()
    rows = res.data or []
    return rows[0] if rows else {}


def list_tickets(limit: int = 500) -> List[Dict[str, Any]]:
    """Lista tickets ordenados por fecha de creación descendente."""
    sb = get_authed_client()
    res = (
        sb.table("tickets")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def get_ticket_by_id(ticket_id: int) -> Optional[Dict[str, Any]]:
    """Obtiene un ticket por su ID."""
    sb = get_authed_client()
    res = (
        sb.table("tickets")
        .select("*")
        .eq("id", ticket_id)
        .maybe_single()
        .execute()
    )
    return res.data


def update_ticket(ticket_id: int, changes: Dict[str, Any]) -> Dict[str, Any]:
    """Actualiza campos de un ticket y retorna el registro actualizado."""
    sb = get_authed_client()
    res = (
        sb.table("tickets")
        .update(changes)
        .eq("id", ticket_id)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else {}


def delete_ticket(ticket_id: int) -> bool:
    """Elimina un ticket. Retorna True si tuvo éxito."""
    try:
        sb = get_authed_client()
        sb.table("tickets").delete().eq("id", ticket_id).execute()
        return True
    except Exception:
        return False
