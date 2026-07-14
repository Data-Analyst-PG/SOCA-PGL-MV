import streamlit as st
from services.supabase_client import get_authed_client


def _cliente():
    return get_authed_client()


def registrar_login():
    """Una sola vez por sesión — ya queda protegido, se puede llamar en cada rerun."""
    if st.session_state.get("_login_registrado"):
        return
    try:
        _cliente().table("auditoria_sesiones").insert({
            "full_name":  st.session_state.get("_auditoria_full_name"),
            "company_id": st.session_state.get("_auditoria_company_id"),
        }).execute()
        st.session_state["_login_registrado"] = True
    except Exception:
        pass


def registrar_acceso_modulo(modulo: str, titulo: str | None = None):
    """Se llama una vez por navegación real a un módulo (protegido contra reruns)."""
    if st.session_state.get("_ultimo_modulo_auditado") == modulo:
        return
    try:
        _cliente().table("auditoria_accesos_modulo").insert({
            "full_name": st.session_state.get("_auditoria_full_name"),
            "modulo":    modulo,
            "empresa":   titulo,
        }).execute()
        st.session_state["_ultimo_modulo_auditado"] = modulo
    except Exception:
        pass


def registrar_accion(modulo: str, accion: str, detalle: dict | None = None):
    """Se llama explícitamente justo después de que una acción se complete."""
    try:
        _cliente().table("auditoria_acciones").insert({
            "full_name": st.session_state.get("_auditoria_full_name"),
            "modulo":    modulo,
            "accion":    accion,
            "detalle":   detalle or {},
        }).execute()
    except Exception:
        pass
