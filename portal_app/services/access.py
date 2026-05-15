# services/access.py
# ─────────────────────────────────────────────────────────────────────────────
# Sistema de permisos v2 — lee desde profiles.access (jsonb)
# Reemplaza la versión anterior que leía user_permissions (columnas bool)
#
# COMPATIBILIDAD: check_access(), require_access(), get_user_permissions()
# y clear_permissions_cache() mantienen la misma firma — no hay que cambiar
# ningún otro archivo de la app.
#
# CÓMO FUNCIONA:
#   profiles.access = {"cotizador_picus:captura": true, "tickets:read": true, ...}
#   check_access(user_id, slug, "cotizador_picus:captura")  →  True / False
#
# AGREGAR NUEVO PERMISO: no requiere migración de BD, solo usa la clave en el JSON
#   UPDATE profiles SET access = access || '{"nuevo:permiso": true}' WHERE ...
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations
import streamlit as st
from services.supabase_client import get_authed_client, current_access_token

_CACHE_KEY = "_user_perms_cache"


def _load_permissions(user_id: str) -> dict:
    """
    Carga el dict de permisos desde profiles.access usando el JWT del usuario.
    Usa caché en session_state para evitar queries por cada rerun.
    """
    if not user_id:
        return {}

    # ── Caché por sesión ──────────────────────────────────────────────────
    cached = st.session_state.get(_CACHE_KEY)
    if cached and cached.get("_uid") == user_id:
        return cached

    # ── Verificar JWT ─────────────────────────────────────────────────────
    token = current_access_token()
    if not token:
        st.session_state["_perm_load_error"] = (
            "Sin access_token en sesión — RLS no puede evaluar auth.uid()."
        )
        return {}

    # ── Consultar profiles.access con JWT aplicado ────────────────────────
    try:
        sb = get_authed_client()
        res = (
            sb.table("profiles")
            .select("access, role")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        data = res.data or {}
    except Exception as e:
        st.session_state["_perm_load_error"] = str(e)
        return {}

    if not data:
        st.session_state["_perm_load_error"] = (
            f"No existe fila en profiles para user_id={user_id}. "
            "Agrégala en Supabase Table Editor."
        )
        return {}

    # Extraer el jsonb de access (puede ser dict o None)
    access: dict = data.get("access") or {}
    role: str = data.get("role") or ""

    # Los admins tienen todos los permisos automáticamente
    if role == "admin":
        access["_is_admin"] = True

    access["_uid"] = user_id
    access["_role"] = role
    st.session_state[_CACHE_KEY] = access
    st.session_state.pop("_perm_load_error", None)
    return access


def check_access(user_id: str, company_slug, permission_key: str) -> bool:
    """
    Retorna True si el usuario tiene el permiso indicado.
    Los admins siempre retornan True.
    """
    if not user_id or not permission_key:
        return False
    perms = _load_permissions(user_id)
    if perms.get("_is_admin"):
        return True
    return bool(perms.get(permission_key, False))


def require_access(user_id: str, company_slug, permission_key: str, mensaje=None) -> bool:
    """Igual que check_access pero detiene la ejecución si no tiene permiso."""
    if check_access(user_id, company_slug, permission_key):
        return True
    st.error(mensaje or "No tienes permiso para acceder a este módulo.")
    st.stop()
    return False


def get_user_permissions(user_id: str) -> dict:
    """Retorna el dict completo de permisos (sin claves internas _uid, _role)."""
    raw = _load_permissions(user_id)
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def get_user_role(user_id: str) -> str:
    """Retorna el rol del usuario (admin, user, data_analyst, auditor...)."""
    return _load_permissions(user_id).get("_role", "")


def clear_permissions_cache() -> None:
    """Llama esto al hacer logout para limpiar el caché de permisos."""
    st.session_state.pop(_CACHE_KEY, None)
    st.session_state.pop("_perm_load_error", None)


def debug_permissions(user_id: str) -> None:
    """Expander de debug. Usar temporalmente en desarrollo."""
    with st.expander("🔧 Debug permisos (solo desarrollo)", expanded=True):
        err = st.session_state.get("_perm_load_error")
        if err:
            st.error(f"❌ Error: {err}")

        token = current_access_token()
        st.write(f"**JWT presente:** {'✅ Sí' if token else '❌ No'}")
        st.write(f"**user_id:** `{user_id}`")

        perms = get_user_permissions(user_id)
        role  = get_user_role(user_id)
        st.write(f"**Rol:** `{role}`")
        if perms:
            st.json(perms)
        else:
            st.warning("⚠️ Sin permisos asignados o falló la query.")
