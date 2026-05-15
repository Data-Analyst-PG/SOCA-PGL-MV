# portal_app/services/supabase_client.py
import os
from typing import Optional, Dict, Any

import streamlit as st
from supabase import create_client, Client


# -------------------------
# Secrets helper
# -------------------------
@st.cache_resource
def get_secret(key: str, default=None):
    """
    Prioridad:
    1) st.secrets (Streamlit Cloud / local con secrets.toml)
    2) variables de entorno (Codespaces)
    """
    try:
        val = st.secrets.get(key, None)
    except Exception:
        val = None

    if val is None:
        val = os.getenv(key)

    return default if val is None else val


@st.cache_resource
def get_supabase_anon_client() -> Client:
    """
    Cliente base SIEMPRE con ANON key (nunca service_role).
    """
    url = get_secret("SUPABASE_URL")
    anon = get_secret("SUPABASE_ANON_KEY") or get_secret("SUPABASE_KEY")  # por compat
    if not url or not anon:
        raise RuntimeError("Faltan SUPABASE_URL y SUPABASE_ANON_KEY (o SUPABASE_KEY).")

    return create_client(url, anon)


def apply_access_token(sb: Client, access_token: Optional[str]) -> Client:
    """
    Aplica JWT a PostgREST para que RLS vea auth.uid().
    """
    if access_token:
        # supabase-py expone postgrest.auth(token)
        sb.postgrest.auth(access_token)
        # opcional: también para storage/functions si lo usas después
        try:
            sb.storage.auth(access_token)
        except Exception:
            pass
    return sb


# -------------------------
# Session helpers (Streamlit)
# -------------------------
SESSION_KEY = "sb_session"  # guardamos dict: access_token, refresh_token, user...


def get_session_from_state() -> Optional[Dict[str, Any]]:
    return st.session_state.get(SESSION_KEY)


def set_session_in_state(session: Optional[Dict[str, Any]]) -> None:
    if session is None:
        st.session_state.pop(SESSION_KEY, None)
    else:
        st.session_state[SESSION_KEY] = session


def current_user() -> Optional[Dict[str, Any]]:
    sess = get_session_from_state()
    if not sess:
        return None
    return sess.get("user")


def current_access_token() -> Optional[str]:
    sess = get_session_from_state()
    if not sess:
        return None
    return sess.get("access_token")


def sign_in_email_password(email: str, password: str) -> Dict[str, Any]:
    """
    Login real con Supabase Auth.
    """
    sb = get_supabase_anon_client()
    res = sb.auth.sign_in_with_password({"email": email, "password": password})

    # supabase-py suele regresar un objeto con .session y .user
    # normalizamos a dict serializable
    session = None
    if getattr(res, "session", None):
        session = {
            "access_token": res.session.access_token,
            "refresh_token": res.session.refresh_token,
            "expires_at": getattr(res.session, "expires_at", None),
            "user": {
                "id": res.user.id,
                "email": res.user.email,
            } if getattr(res, "user", None) else None,
        }
    else:
        # Por si cambia la lib o viene distinto
        raise RuntimeError("No se recibió sesión de Supabase Auth.")

    set_session_in_state(session)
    return session


def sign_out() -> None:
    """
    Logout: invalida sesión en el cliente y limpia state.
    """
    try:
        sb = get_supabase_anon_client()
        # Si hay token, lo aplicamos para que el sign_out apunte a esa sesión
        apply_access_token(sb, current_access_token())
        sb.auth.sign_out()
    except Exception:
        pass
    finally:
        set_session_in_state(None)


def get_authed_client() -> Client:
    """
    Regresa supabase client con JWT aplicado si hay sesión.
    Úsalo SIEMPRE para queries/insert/update que dependan de RLS.
    IMPORTANTE: Crea instancia nueva cada vez para evitar que el JWT
    de un usuario contamine las queries de otro usuario.
    """
    url = get_secret("SUPABASE_URL")
    anon = get_secret("SUPABASE_ANON_KEY") or get_secret("SUPABASE_KEY")
    sb = create_client(url, anon)
    return apply_access_token(sb, current_access_token())


def refresh_session_if_possible() -> None:
    """
    Rehidrata/refresh si tuvieras refresh_token guardado.
    OJO: Streamlit NO persiste st.session_state tras “hard refresh” del navegador.
    Esto sirve para:
      - reruns normales
      - cuando el token expira durante la sesión viva
    """
    sess = get_session_from_state()
    if not sess:
        return

    refresh_token = sess.get("refresh_token")
    if not refresh_token:
        return

    sb = get_supabase_anon_client()
    try:
        # Muchos setups usan refresh_session({ "refresh_token": ... })
        res = sb.auth.refresh_session(refresh_token)
        if getattr(res, "session", None):
            new_sess = {
                "access_token": res.session.access_token,
                "refresh_token": res.session.refresh_token,
                "expires_at": getattr(res.session, "expires_at", None),
                "user": {"id": res.user.id, "email": res.user.email} if getattr(res, "user", None) else sess.get("user"),
            }
            set_session_in_state(new_sess)
    except Exception:
        # si falla, mejor limpiar para forzar login
        set_session_in_state(None)

# -------------------------
# Backward compatibility
# -------------------------
def get_supabase_client():
    """
    Alias para código antiguo que todavía importa get_supabase_client().
    Regresa cliente con JWT si hay sesión (RLS), o anon si no hay sesión.
    """
    return get_authed_client()
