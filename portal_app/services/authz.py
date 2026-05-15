# portal_app/services/authz.py
from typing import Dict, Any, Optional
import streamlit as st
from services.supabase_client import get_authed_client, current_user, sign_out

PROFILE_KEY = "user_profile"
ROLE_KEY    = "user_role"


def load_profile_into_state() -> Optional[Dict[str, Any]]:
    user = current_user()
    if not user:
        st.session_state.pop(PROFILE_KEY, None)
        st.session_state.pop(ROLE_KEY, None)
        return None

    sb  = get_authed_client()
    uid = user["id"]

    # profiles tiene RLS deshabilitado y PK = user_id (FK a auth.users.id)
    res = (
        sb.table("profiles")
        .select("user_id, full_name, role, company_id, is_active, job_title, area_name")
        .eq("user_id", uid)
        .maybe_single()
        .execute()
    )

    prof = res.data
    if not prof:
        sign_out()
        return None

    if prof.get("is_active") is False:
        sign_out()
        return None

    st.session_state[PROFILE_KEY] = prof
    st.session_state[ROLE_KEY]    = prof.get("role")
    return prof


def ensure_auth_loaded() -> bool:
    if not current_user():
        return False
    # Si ya tenemos el perfil cargado en esta sesión, no releer
    if st.session_state.get(PROFILE_KEY):
        return True
    prof = load_profile_into_state()
    return bool(prof)


def role() -> Optional[str]:
    return st.session_state.get(ROLE_KEY)


def profile() -> Optional[Dict[str, Any]]:
    return st.session_state.get(PROFILE_KEY)


def company_id() -> Optional[str]:
    p = profile() or {}
    return p.get("company_id")
