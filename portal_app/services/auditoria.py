import streamlit as st
from services.supabase_client import get_authed_client


def _cliente():
    return get_authed_client()


def registrar_login():
    """Llamar UNA sola vez por sesión, justo después del login exitoso."""
    if st.session_state.get("_login_registrado"):
        return
    try:
        _cliente().table("auditoria_sesiones").insert({
            "full_name": st.session_state.get("full_name"),
            "company_id": st.session_state.get("company_id"),
        }).execute()
        st.session_state["_login_registrado"] = True
    except Exception:
        pass  # la auditoría nunca debe tumbar la app


def registrar_acceso_modulo(modulo: str, empresa: str | None = None):
    """Llamar en el navigation guard de app.py, cada vez que se valida acceso a un módulo."""
    if st.session_state.get("_ultimo_modulo_auditado") == modulo:
        return  # evita duplicados en reruns de Streamlit
    try:
        _cliente().table("auditoria_accesos_modulo").insert({
            "full_name": st.session_state.get("full_name"),
            "modulo": modulo,
            "empresa": empresa,
        }).execute()
        st.session_state["_ultimo_modulo_auditado"] = modulo
    except Exception:
        pass


def registrar_accion(modulo: str, accion: str, detalle: dict | None = None):
    """Llamar justo después de que una acción se complete: crear ruta, generar PDF, descargar archivo, etc."""
    try:
        _cliente().table("auditoria_acciones").insert({
            "full_name": st.session_state.get("full_name"),
            "modulo": modulo,
            "accion": accion,
            "detalle": detalle or {},
        }).execute()
    except Exception:
        pass
