# portal_app/modules/auth/ui.py
from pathlib import Path
import base64
import streamlit as st

from services.supabase_client import sign_in_email_password, get_supabase_anon_client
from services.authz import ensure_auth_loaded
from ui.theme import PGL_NAVY, PGL_RED, PGL_NAVY_LT


def _inject_login_css():
    navy  = PGL_NAVY
    red   = PGL_RED
    navy2 = PGL_NAVY_LT
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"] {{
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        background: linear-gradient(145deg, {navy} 0%, {navy2} 60%, #1a1f5e 100%) !important;
        min-height: 100vh;
    }}
    [data-testid="stSidebar"],[data-testid="collapsedControl"]{{display:none!important;}}
    [data-testid="stHeader"]{{display:none!important;}}
    #MainMenu,footer{{visibility:hidden;}}
    .block-container{{padding:2rem 1rem!important;max-width:480px!important;margin:0 auto!important;}}
    .login-card{{background:rgba(255,255,255,0.97);border-radius:20px;padding:2.2rem 2rem 1.8rem;box-shadow:0 20px 60px rgba(0,0,0,0.35);margin-top:1rem;}}
    .logo-wrap{{display:flex;justify-content:center;margin-bottom:1.5rem;}}
    .logo-wrap img{{max-width:220px;width:100%;height:auto;}}
    .login-title{{text-align:center;font-size:1.5rem;font-weight:800;color:{navy};margin-bottom:0.25rem;}}
    .login-subtitle{{text-align:center;font-size:0.82rem;color:#6B7280;margin-bottom:1.5rem;}}
    .login-footer{{text-align:center;font-size:0.78rem;color:#9CA3AF;margin-top:1.2rem;}}
    div[data-testid="stForm"]{{border:none!important;padding:0!important;background:transparent!important;}}
    div[data-testid="stFormSubmitButton"] button{{
        width:100%!important;background:linear-gradient(135deg,{red},#E02424)!important;
        color:white!important;font-weight:700!important;font-size:0.95rem!important;
        border-radius:10px!important;border:none!important;padding:0.65rem!important;margin-top:0.5rem!important;
    }}
    .stButton>button{{
        width:100%!important;border-radius:10px!important;font-weight:600!important;
        font-size:0.88rem!important;color:{navy}!important;background:transparent!important;
        border:1.5px solid #D1D8E8!important;padding:0.55rem!important;
    }}
    .stButton>button:hover{{background:#F0F2FA!important;border-color:{navy}!important;}}
    </style>
    """, unsafe_allow_html=True)


def _logo_html() -> str:
    logo_path = Path(__file__).resolve().parents[2] / "img" / "Color PGL MS.png"
    if logo_path.exists():
        b64 = base64.b64encode(logo_path.read_bytes()).decode()
        return f'<div class="logo-wrap"><img src="data:image/png;base64,{b64}"></div>'
    navy = PGL_NAVY
    red  = PGL_RED
    return (
        '<div class="logo-wrap" style="flex-direction:column;gap:4px;text-align:center;">'
        '<span style="font-size:2.5rem;">&#x1F69A;</span>'
        f'<div style="font-weight:800;font-size:1.1rem;color:{navy};">PALOS GARZA</div>'
        f'<div style="font-weight:600;font-size:0.75rem;color:{red};letter-spacing:2px;text-transform:uppercase;">Logistics</div>'
        '</div>'
    )


def render_login_page() -> None:
    _inject_login_css()

    auth_token = st.query_params.get("auth_token")
    auth_email = st.query_params.get("auth_email")
    if auth_token and auth_email:
        _render_set_password_from_token(auth_email, auth_token)
        return

    if st.session_state.get("mostrar_forgot"):
        _render_forgot_inline()
        return
    logo = _logo_html()
    st.markdown(f"""
    <div class="login-card">
        {logo}
        <div class="login-title">Iniciar sesi&#xF3;n</div>
        <div class="login-subtitle">Portal interno &middot; Palos Garza Logistics</div>
    </div>
    """, unsafe_allow_html=True)

    with st.form("login_form", clear_on_submit=False):
        email    = st.text_input("Correo electr&#xF3;nico", placeholder="usuario@palosgarza.com")
        password = st.text_input("Contrase&#xF1;a", type="password", placeholder="••••••••")
        submitted = st.form_submit_button("Ingresar →")

    if submitted:
        if not email or not password:
            st.error("Ingresa tu correo y contrase\u00f1a.")
        else:
            with st.spinner("Verificando..."):
                try:
                    sign_in_email_password(email.strip(), password)
                    if not ensure_auth_loaded():
                        st.error("Usuario no autorizado. Contacta al administrador.")
                    else:
                        st.rerun()
                except Exception:
                    st.error("Correo o contrase\u00f1a incorrectos.")

    st.markdown("<br>", unsafe_allow_html=True)

    if st.button("\U0001f511 \u00bfOlvidaste tu contrase\u00f1a?", key="btn_forgot"):
        st.session_state["mostrar_forgot"] = True
        st.rerun()

    st.markdown(
        '<div class="login-footer">\u00bfProblemas para entrar? Contacta al equipo de An\u00e1lisis de Datos.</div>',
        unsafe_allow_html=True,
    )


def _render_forgot_inline() -> None:
    _inject_login_css()
    logo = _logo_html()

    st.markdown(f"""
    <div class="login-card">
        {logo}
        <div class="login-title">&#x1F510; Recuperar contrase&#xF1;a</div>
        <div class="login-subtitle">Te enviaremos un enlace a tu correo</div>
    </div>
    """, unsafe_allow_html=True)

    reset_email = st.text_input(
        "Correo electr\u00f3nico", placeholder="usuario@palosgarza.com", key="reset_email",
    )

    col1, col2 = st.columns(2)
    with col1:
        send_link = st.button("\U0001f4e8 Enviar enlace", key="btn_send_code", use_container_width=True)
    with col2:
        back_btn = st.button("\u2190 Volver", key="btn_back_forgot", use_container_width=True)

    if send_link:
        if not reset_email:
            st.warning("Ingresa tu correo primero.")
        else:
            from services.auth_admin import enviar_link_password
            try:
                enviar_link_password(reset_email.strip(), reset_email.strip(), es_bienvenida=False)
            except Exception:
                pass
            st.success("Si el correo existe, recibir\u00e1s un enlace en breve. Rev\u00edsalo y da clic para continuar.")

    if back_btn:
        st.session_state.pop("mostrar_forgot", None)
        st.rerun()

    st.markdown(
        '<div class="login-footer">\u00bfProblemas? Contacta al equipo de An\u00e1lisis de Datos.</div>',
        unsafe_allow_html=True,
    )

def _render_set_password_from_token(email: str, token_hash: str) -> None:
    _inject_login_css()
    logo = _logo_html()

    st.markdown(f"""
    <div class="login-card">
        {logo}
        <div class="login-title">&#x1F511; Establece tu contrase&#xF1;a</div>
        <div class="login-subtitle">{email}</div>
    </div>
    """, unsafe_allow_html=True)

    new_password     = st.text_input("Nueva contrase\u00f1a", type="password", key="np_token")
    confirm_password = st.text_input("Confirmar contrase\u00f1a", type="password", key="cp_token")

    if st.button("\u2705 Guardar contrase\u00f1a", key="btn_save_token", use_container_width=True):
        if not new_password:
            st.error("Ingresa una contrase\u00f1a.")
        elif new_password != confirm_password:
            st.error("Las contrase\u00f1as no coinciden.")
        elif len(new_password) < 8:
            st.error("La contrase\u00f1a debe tener al menos 8 caracteres.")
        else:
            try:
                sb = get_supabase_anon_client()
                sb.auth.verify_otp({"token_hash": token_hash, "type": "recovery"})
                sb.auth.update_user({"password": new_password})
                sb.auth.sign_out()
                st.success("\u2705 Contrase\u00f1a guardada. Redirigiendo...")
                st.query_params.clear()
                st.session_state.pop("mostrar_forgot", None)
                st.rerun()
            except Exception as e:
                err = str(e).lower()
                if "expired" in err or "invalid" in err:
                    st.error("El enlace es inv\u00e1lido o ya expir\u00f3. Solicita uno nuevo desde 'Olvid\u00e9 mi contrase\u00f1a'.")
                else:
                    st.error(f"No se pudo actualizar: {e}")

    st.markdown(
        '<div class="login-footer">\u00bfProblemas? Contacta al equipo de An\u00e1lisis de Datos.</div>',
        unsafe_allow_html=True,
    )
