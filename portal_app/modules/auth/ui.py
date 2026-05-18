# portal_app/modules/auth/ui.py
# ─────────────────────────────────────────────────────────────────────────────
# Pantalla de login — Portal Palos Garza Logistics
# Flujo:
#   1. Usuario ingresa email + contraseña → login normal
#   2. Clic en "¿Olvidaste tu contraseña?" → form inline de recuperación
#   3. Supabase envía correo con OTP → usuario ingresa el código aquí mismo
#   4. Nueva contraseña guardada y redirige al login
# ─────────────────────────────────────────────────────────────────────────────
from pathlib import Path
import base64
import streamlit as st

from services.supabase_client import (
    sign_in_email_password,
    get_supabase_anon_client,
)
from services.authz import ensure_auth_loaded
from ui.theme import PGL_NAVY, PGL_RED, PGL_NAVY_LT

# ── Inyectar CSS del login una sola vez ──────────────────────────────────────
def _inject_login_css():
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"] {{
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        background: linear-gradient(145deg, {PGL_NAVY} 0%, #252D80 60%, #1a1f5e 100%) !important;
        min-height: 100vh;
    }}
    [data-testid="stSidebar"], [data-testid="collapsedControl"] {{ display: none !important; }}
    [data-testid="stHeader"] {{ display: none !important; }}
    #MainMenu, footer {{ visibility: hidden; }}
    .block-container {{
        padding: 2rem 1rem !important;
        max-width: 480px !important;
        margin: 0 auto !important;
    }}
    div[data-testid="stForm"] {{ border: none !important; padding: 0 !important; background: transparent !important; }}
    div[data-testid="stFormSubmitButton"] button {{
        width: 100% !important;
        background: linear-gradient(135deg, {PGL_RED}, #E02424) !important;
        color: white !important; font-weight: 700 !important;
        font-size: 0.95rem !important; border-radius: 10px !important;
        border: none !important; padding: 0.65rem !important;
        margin-top: 0.5rem !important;
    }}
    .stButton > button {{
        width: 100% !important; border-radius: 10px !important;
        font-weight: 600 !important; font-size: 0.88rem !important;
        color: {PGL_NAVY} !important; background: transparent !important;
        border: 1.5px solid #D1D8E8 !important; padding: 0.55rem !important;
    }}
    .stButton > button:hover {{ background: #F0F2FA !important; border-color: {PGL_NAVY} !important; }}
    </style>
    """, unsafe_allow_html=True)


<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {{
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    background: linear-gradient(145deg, {PGL_NAVY} 0%, {PGL_NAVY_LT} 60%, #1a1f5e 100%) !important;
    min-height: 100vh;
}}

[data-testid="stSidebar"],
[data-testid="collapsedControl"] {{ display: none !important; }}
[data-testid="stHeader"]         {{ display: none !important; }}
#MainMenu, footer                {{ visibility: hidden; }}

.block-container {{
    padding: 2rem 1rem !important;
    max-width: 480px !important;
    margin: 0 auto !important;
}}

/* Tarjeta login */
.login-card {{
    background: rgba(255,255,255,0.97);
    border-radius: 20px;
    padding: 2.2rem 2rem 1.8rem;
    box-shadow: 0 20px 60px rgba(0,0,0,0.35);
    margin-top: 1rem;
}}

/* Logo */
.logo-wrap {{
    display: flex; justify-content: center;
    margin-bottom: 1.5rem;
}}
.logo-wrap img {{
    max-width: 220px; width: 100%; height: auto;
}}

/* Título */
.login-title {{
    text-align: center;
    font-size: 1.5rem;
    font-weight: 800;
    color: {PGL_NAVY};
    margin-bottom: 0.25rem;
}}
.login-subtitle {{
    text-align: center;
    font-size: 0.82rem;
    color: #6B7280;
    margin-bottom: 1.5rem;
}}

/* Inputs */
div[data-testid="stTextInput"] label {{
    font-weight: 600 !important;
    font-size: 0.85rem !important;
    color: {PGL_NAVY} !important;
}}
div[data-testid="stTextInput"] input {{
    border-radius: 10px !important;
    border: 1.5px solid #D1D8E8 !important;
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    font-size: 0.9rem !important;
    padding: 0.6rem 0.8rem !important;
}}
div[data-testid="stTextInput"] input:focus {{
    border-color: {PGL_NAVY} !important;
    box-shadow: 0 0 0 3px rgba(27,34,102,0.12) !important;
}}

/* Formulario sin borde */
div[data-testid="stForm"] {{
    border: none !important;
    padding: 0 !important;
    background: transparent !important;
}}

/* Botón submit */
div[data-testid="stFormSubmitButton"] button {{
    width: 100% !important;
    background: linear-gradient(135deg, {PGL_RED}, #E02424) !important;
    color: white !important;
    font-weight: 700 !important;
    font-size: 0.95rem !important;
    border-radius: 10px !important;
    border: none !important;
    padding: 0.65rem !important;
    margin-top: 0.5rem !important;
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    transition: all 0.2s;
}}
div[data-testid="stFormSubmitButton"] button:hover {{
    background: linear-gradient(135deg, #a81818, {PGL_RED}) !important;
    box-shadow: 0 4px 16px rgba(204,30,30,0.4) !important;
}}

/* Botón ghost (olvidaste contraseña / volver) */
.stButton > button {{
    width: 100% !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    font-size: 0.88rem !important;
    color: {PGL_NAVY} !important;
    background: transparent !important;
    border: 1.5px solid #D1D8E8 !important;
    padding: 0.55rem !important;
}}
.stButton > button:hover {{
    background: #F0F2FA !important;
    border-color: {PGL_NAVY} !important;
}}

/* Footer */
.login-footer {{
    text-align: center;
    font-size: 0.78rem;
    color: #9CA3AF;
    margin-top: 1.2rem;
}}

/* Responsivo móvil */
@media (max-width: 500px) {{
    .block-container {{
        padding: 1rem 0.5rem !important;
    }}
    .login-card {{
        padding: 1.5rem 1.2rem 1.3rem;
        border-radius: 16px;
    }}
}}
</style>
"""


# ── Logo ──────────────────────────────────────────────────────────────────────
def _logo_html() -> str:
    logo_path = Path(__file__).resolve().parents[2] / "img" / "Color PGL MS.png"
    if logo_path.exists():
        b64 = base64.b64encode(logo_path.read_bytes()).decode()
        return f'<div class="logo-wrap"><img src="data:image/png;base64,{b64}"></div>'
    # Fallback texto si no existe la imagen
    return f"""
    <div class="logo-wrap" style="flex-direction:column; gap:4px;">
        <span style="font-size:2.5rem;">🚚</span>
        <div style="font-weight:800; font-size:1.1rem; color:{PGL_NAVY};">PALOS GARZA</div>
        <div style="font-weight:600; font-size:0.75rem; color:{PGL_RED};
                    letter-spacing:2px; text-transform:uppercase;">Logistics</div>
    </div>
    """


# ═════════════════════════════════════════════════════════════════════════════
# PANTALLA: LOGIN NORMAL
# ═════════════════════════════════════════════════════════════════════════════
def render_login_page() -> None:
    _inject_login_css()

    # Enrutar a recuperación si está activo
    if st.session_state.get("mostrar_forgot"):
        _render_forgot_inline()
        return

    # Tarjeta centrada
    st.markdown(f"""
    <div class="login-card">
        {_logo_html()}
        <div class="login-title">Iniciar sesión</div>
        <div class="login-subtitle">Portal interno · Palos Garza Logistics</div>
    </div>
    """, unsafe_allow_html=True)

    # Formulario fuera del HTML para que Streamlit lo maneje
    with st.form("login_form", clear_on_submit=False):
        email    = st.text_input("Correo electrónico", placeholder="usuario@palosgarza.com")
        password = st.text_input("Contraseña", type="password", placeholder="••••••••")
        submitted = st.form_submit_button("Ingresar →")

    if submitted:
        if not email or not password:
            st.error("Ingresa tu correo y contraseña.")
        else:
            with st.spinner("Verificando..."):
                try:
                    sign_in_email_password(email.strip(), password)
                    if not ensure_auth_loaded():
                        st.error("Usuario no autorizado o inactivo. Contacta al administrador.")
                    else:
                        st.rerun()
                except Exception:
                    st.error("Correo o contraseña incorrectos.")

    st.markdown("<br>", unsafe_allow_html=True)

    if st.button("🔑 ¿Olvidaste tu contraseña?", key="btn_forgot"):
        st.session_state["mostrar_forgot"] = True
        st.rerun()

    st.markdown(
        '<div class="login-footer">¿Problemas para entrar? Contacta al equipo de Análisis de Datos.</div>',
        unsafe_allow_html=True,
    )


# ═════════════════════════════════════════════════════════════════════════════
# PANTALLA: RECUPERAR CONTRASEÑA
# ═════════════════════════════════════════════════════════════════════════════
def _render_forgot_inline() -> None:
    st.markdown(f"""
    <div class="login-card">
        {_logo_html()}
        <div class="login-title">🔐 Recuperar contraseña</div>
        <div class="login-subtitle">Te enviaremos un código a tu correo</div>
    </div>
    """, unsafe_allow_html=True)

    reset_email = st.text_input(
        "Correo electrónico",
        placeholder="usuario@palosgarza.com",
        key="reset_email",
    )

    col1, col2 = st.columns(2)
    with col1:
        send_code = st.button("📨 Enviar código", key="btn_send_code", use_container_width=True)
    with col2:
        back_btn = st.button("← Volver", key="btn_back_forgot", use_container_width=True)

    if send_code:
        if not reset_email:
            st.warning("Ingresa tu correo primero.")
        else:
            try:
                sb = get_supabase_anon_client()
                sb.auth.reset_password_for_email(reset_email.strip())
            except Exception:
                pass
            finally:
                # Siempre mostramos éxito para no revelar si el email existe
                st.success("Si el correo existe, recibirás el código en breve.")

    st.divider()
    st.markdown("**Paso 2 — Ingresa el código y tu nueva contraseña**")

    recovery_code    = st.text_input("Código de recuperación", placeholder="Ej: 482910", key="recovery_code")
    new_password     = st.text_input("Nueva contraseña",  type="password", key="new_password_reset")
    confirm_password = st.text_input("Confirmar contraseña", type="password", key="confirm_password_reset")

    update_clicked = st.button("✅ Actualizar contraseña", key="btn_update_pass", use_container_width=True)

    if update_clicked:
        # Validaciones
        if not reset_email:
            st.error("Falta el correo electrónico.")
            st.stop()
        if not recovery_code:
            st.error("Ingresa el código de recuperación.")
            st.stop()
        if not new_password:
            st.error("Ingresa una nueva contraseña.")
            st.stop()
        if new_password != confirm_password:
            st.error("Las contraseñas no coinciden.")
            st.stop()
        if len(new_password) < 8:
            st.error("La contraseña debe tener al menos 8 caracteres.")
            st.stop()

        try:
            sb = get_supabase_anon_client()
            sb.auth.verify_otp({
                "email": reset_email.strip(),
                "token": recovery_code.strip(),
                "type": "recovery",
            })
            sb.auth.update_user({"password": new_password})
            sb.auth.sign_out()

            st.success("✅ Contraseña actualizada. Ya puedes iniciar sesión.")
            st.session_state.pop("mostrar_forgot", None)
            st.rerun()

        except Exception as e:
            err = str(e).lower()
            if "expired" in err or "invalid" in err:
                st.error("El código es inválido o ya expiró. Solicita uno nuevo.")
            else:
                st.error(f"No se pudo actualizar: {e}")

    if back_btn:
        st.session_state.pop("mostrar_forgot", None)
        st.rerun()

    st.markdown(
        '<div class="login-footer">¿Problemas? Contacta al equipo de Análisis de Datos.</div>',
        unsafe_allow_html=True,
    )
