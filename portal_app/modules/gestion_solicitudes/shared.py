# portal_app/modules/gestion_solicitudes/shared.py
# Re-exporta lo necesario desde los servicios reales
from services.supabase_client import get_authed_client
from services.auditoria import registrar_accion
from datetime import datetime, timezone


def now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_complementarias(limit: int = 500) -> list:
    try:
        sb = get_authed_client()
        res = (
            sb.table("solicitudes_complementarias")
            .select("*")
            .order("fecha_captura", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []
    except Exception as e:
        import streamlit as st
        st.error(f"[get_complementarias] Error: {e}")
        return []


def update_complementaria(folio, changes: dict) -> bool:
    try:
        sb = get_authed_client()
        sb.table("solicitudes_complementarias").update(changes).eq("folio", folio).execute()
        return True
    except Exception:
        return False


def get_tickets(limit: int = 500) -> list:
    try:
        sb = get_authed_client()
        res = (
            sb.table("tickets")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []
    except Exception:
        return []


def update_ticket(ticket_id, changes: dict) -> bool:
    try:
        sb = get_authed_client()
        sb.table("tickets").update(changes).eq("id", ticket_id).execute()
        return True
    except Exception:
        return False


def log_accion_complementarias(accion: str, detalle: dict | None = None) -> None:
    """Wrapper de auditoría — módulo seg-complementarias (gestión/auditor)."""
    registrar_accion("seg-complementarias", accion, detalle)


def log_accion_tickets(accion: str, detalle: dict | None = None) -> None:
    """Wrapper de auditoría — módulo seg-tickets (gestión/auditor)."""
    registrar_accion("seg-tickets", accion, detalle)
