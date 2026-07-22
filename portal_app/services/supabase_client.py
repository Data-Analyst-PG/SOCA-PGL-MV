# portal_app/services/supabase_client.py
# ─────────────────────────────────────────────────────────────────────────────
# Cliente Supabase para Portal PGL
# Mejoras vs versión anterior:
#   ✅ Refresh automático silencioso antes de que el token expire
#   ✅ Detección de token expirado en cada request — redirige a login sin error
#   ✅ service_role key solo para módulos protegidos por permiso de admin (get_service_client)
#   ✅ Compatibilidad total con código existente (aliases conservados)
# ─────────────────────────────────────────────────────────────────────────────
import os
import time
from typing import Optional, Dict, Any

import streamlit as st
from supabase import create_client, Client


# ─────────────────────────────────────────────────────────────────────────────
# SECRETS
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_resource
def _get_secret(key: str, default=None):
    """
    Lee credenciales con prioridad:
    1) st.secrets (Streamlit Cloud / secrets.toml local)
    2) Variables de entorno (Codespaces / CI)
    """
    try:
        val = st.secrets.get(key, None)
    except Exception:
        val = None
    if val is None:
        val = os.getenv(key)
    return default if val is None else val


def get_secret(key: str, default=None):
    """Alias público — compatibilidad con código existente."""
    return _get_secret(key, default)


# ─────────────────────────────────────────────────────────────────────────────
# CLIENTE ANON (singleton — solo para auth sin JWT)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_resource
def get_supabase_anon_client() -> Client:
    """
    Cliente con anon key. Úsalo SOLO para:
      - sign_in_with_password
      - reset_password_for_email
      - verify_otp
    Para queries de datos usa get_authed_client().
    """
    url  = _get_secret("SUPABASE_URL")
    anon = _get_secret("SUPABASE_ANON_KEY") or _get_secret("SUPABASE_KEY")
    if not url or not anon:
        raise RuntimeError(
            "Faltan SUPABASE_URL y SUPABASE_ANON_KEY en secrets. "
            "Agrégalos en Streamlit Cloud → Settings → Secrets."
        )
    return create_client(url, anon)


# ─────────────────────────────────────────────────────────────────────────────
# SESIÓN EN SESSION_STATE
# ─────────────────────────────────────────────────────────────────────────────
_SESSION_KEY = "sb_session"
# Margen de seguridad: refrescar si quedan menos de 5 minutos para que expire
_REFRESH_MARGIN_SECS = 300


def get_session_from_state() -> Optional[Dict[str, Any]]:
    return st.session_state.get(_SESSION_KEY)


def set_session_in_state(session: Optional[Dict[str, Any]]) -> None:
    if session is None:
        st.session_state.pop(_SESSION_KEY, None)
    else:
        st.session_state[_SESSION_KEY] = session


def current_user() -> Optional[Dict[str, Any]]:
    """Devuelve el dict del usuario actual o None si no hay sesión."""
    _auto_refresh_if_needed()
    sess = get_session_from_state()
    return sess.get("user") if sess else None


def current_access_token() -> Optional[str]:
    """Devuelve el JWT activo o None."""
    sess = get_session_from_state()
    return sess.get("access_token") if sess else None


# ─────────────────────────────────────────────────────────────────────────────
# REFRESH AUTOMÁTICO SILENCIOSO
# ─────────────────────────────────────────────────────────────────────────────
def _auto_refresh_if_needed() -> None:
    """
    Si el token expira en menos de _REFRESH_MARGIN_SECS, lo renueva
    automáticamente usando el refresh_token guardado en session_state.
    El usuario nunca nota esto — no hay pantalla de login intermedia.
    """
    sess = get_session_from_state()
    if not sess:
        return

    expires_at    = sess.get("expires_at")
    refresh_token = sess.get("refresh_token")

    if not expires_at or not refresh_token:
        return

    # expires_at puede ser Unix timestamp (int/float) o string ISO
    try:
        expires_ts = float(expires_at)
    except (TypeError, ValueError):
        return

    tiempo_restante = expires_ts - time.time()
    if tiempo_restante > _REFRESH_MARGIN_SECS:
        return  # Aún vigente, no hacer nada

    # Token próximo a expirar — renovar silenciosamente
    try:
        sb  = get_supabase_anon_client()
        res = sb.auth.refresh_session(refresh_token)
        if getattr(res, "session", None):
            set_session_in_state({
                "access_token":  res.session.access_token,
                "refresh_token": res.session.refresh_token,
                "expires_at":    getattr(res.session, "expires_at", None),
                "user": {
                    "id":    res.user.id,
                    "email": res.user.email,
                } if getattr(res, "user", None) else sess.get("user"),
            })
    except Exception:
        # Si el refresh falla (token revocado, etc.) cerrar sesión limpiamente
        set_session_in_state(None)


# ─────────────────────────────────────────────────────────────────────────────
# CLIENTE AUTENTICADO (con JWT — para queries con RLS)
# ─────────────────────────────────────────────────────────────────────────────
def apply_access_token(sb: Client, access_token: Optional[str]) -> Client:
    """Aplica JWT al cliente para que RLS vea auth.uid()."""
    if access_token:
        sb.postgrest.auth(access_token)
        try:
            sb.storage.auth(access_token)
        except Exception:
            pass
    return sb


def get_authed_client() -> Client:
    """
    Devuelve cliente Supabase con JWT aplicado.
    Crea instancia nueva cada vez — evita que el JWT de un usuario
    contamine queries de otro usuario en la misma instancia de Streamlit.
    Úsalo para TODAS las queries que dependen de RLS.
    """
    url  = _get_secret("SUPABASE_URL")
    anon = _get_secret("SUPABASE_ANON_KEY") or _get_secret("SUPABASE_KEY")
    sb   = create_client(url, anon)
    return apply_access_token(sb, current_access_token())


# ─────────────────────────────────────────────────────────────────────────────
# LOGIN / LOGOUT
# ─────────────────────────────────────────────────────────────────────────────
def sign_in_email_password(email: str, password: str) -> Dict[str, Any]:
    """Login con Supabase Auth. Guarda la sesión en session_state."""
    sb  = get_supabase_anon_client()
    res = sb.auth.sign_in_with_password({"email": email, "password": password})

    if not getattr(res, "session", None):
        raise RuntimeError("Supabase no devolvió sesión. Verifica credenciales.")

    session = {
        "access_token":  res.session.access_token,
        "refresh_token": res.session.refresh_token,
        "expires_at":    getattr(res.session, "expires_at", None),
        "user": {
            "id":    res.user.id,
            "email": res.user.email,
        } if getattr(res, "user", None) else None,
    }
    set_session_in_state(session)
    return session


def sign_out() -> None:
    """Cierra sesión en Supabase y limpia session_state."""
    try:
        sb = get_supabase_anon_client()
        apply_access_token(sb, current_access_token())
        sb.auth.sign_out()
    except Exception:
        pass
    finally:
        set_session_in_state(None)


# ─────────────────────────────────────────────────────────────────────────────
# COMPATIBILIDAD CON CÓDIGO EXISTENTE
# ─────────────────────────────────────────────────────────────────────────────
def get_supabase_client() -> Client:
    """Alias legacy — equivale a get_authed_client()."""
    return get_authed_client()


def refresh_session_if_possible() -> None:
    """Alias legacy — ahora el refresh es automático en current_user()."""
    _auto_refresh_if_needed()


def set_session_from_url_params() -> None:
    """
    Stub legacy — ya no se usa con el flujo de OTP actual.
    Se conserva para no romper imports existentes.
    """
    pass

# ─────────────────────────────────────────────────────────────────────────────
# CLIENTE SERVICE-ROLE (solo para módulos protegidos por permiso de admin)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_resource
def get_service_client() -> Client:
    """
    Cliente con la service_role key — bypassa RLS por completo.
    SOLO usar dentro de módulos ya protegidos por permiso de admin
    (ej. modules/administracion/*). Nunca exponer a queries de usuarios
    normales ni a módulos sin gate de permiso.
    """
    url = _get_secret("SUPABASE_URL")
    service_key = _get_secret("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not service_key:
        raise RuntimeError(
            "Falta SUPABASE_SERVICE_ROLE_KEY en secrets. "
            "Agrégala en Streamlit Cloud → Settings → Secrets "
            "(Supabase Dashboard → Project Settings → API → service_role key)."
        )
    return create_client(url, service_key)
