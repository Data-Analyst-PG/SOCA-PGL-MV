# portal_app/modules/auth/auth.py
import streamlit as st
from services.supabase_client import current_user, sign_out


def is_logged_in() -> bool:
    return current_user() is not None


def logout() -> None:
    sign_out()
    # Limpiar perfil, rol, permisos cacheados y cualquier clave de la app
    keys_to_clear = [
        k for k in st.session_state
        if k in ("user_profile", "user_role", "user_permissions",
                 "_user_perms_cache", "_perm_load_error")
        or k.startswith("_app_role_")
    ]
    for k in keys_to_clear:
        st.session_state.pop(k, None)
