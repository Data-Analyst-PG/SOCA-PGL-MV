# portal_app/pages/pg_reset_password.py
#
# Esta página es invocada por app.py cuando detecta un token de recovery.
# NO hace st.set_page_config (app.py ya lo hizo).
# NO necesita leer query_params ni inyectar JS (app.py ya lo hizo).
# Solo lee st.session_state["reset_token"] y muestra el formulario.

import time
from pathlib import Path
import base64

import streamlit as st
from services.supabase_client import (
    get_supabase_anon_client,
    set_session_in_state,
)

# ─── Estilos ──────────────────────────────────────────────────────
st.markdown("""
<style>
  [data-testid="stSidebar"]    { display: none !important; }
  [data-testid="stNavigation"] { display: none !important; }
  .block-container {
    padding-top: 2rem !important;
    max-width: 480px !important;
    margin: 0 auto !important;
  }
  .pg-logo-wrap {
    width: 100%; display: flex;
    justify-content: center; align-items: center;
    margin-bottom: 1.2rem;
  }
  .pg-logo-img {
    display: block; max-width: 300px;
    width: 100%; height: auto; object-fit: contain;
  }
  .reset-card {
    border: 1px solid #E5E9F0;
    border-radius: 18px;
    padding: 1.8rem 1.6rem 1.4rem;
    background: #ffffff;
    box-shadow: 0 4px 24px rgba(27,34,102,0.10);
  }
  .reset-title {
    text-align: center;
    font-size: 1.55rem;
    font-weight: 800;
    color: #1B2266;
    margin-bottom: 0.3rem;
  }
  .reset-sub {
    text-align: center;
    font-size: 0.88rem;
    color: #6B7280;
    margin-bottom: 1.2rem;
  }
  div[data-testid="stForm"] {
    border: none !important; padding: 0 !important;
    background: transparent !important;
  }
  div[data-testid="stTextInput"] { margin-bottom: 0.5rem; }
  div[data-testid="stTextInput"] label { font-weight: 600; color: #1B2266; }
  div[data-testid="stFormSubmitButton"] button {
    width: 100%; border-radius: 10px; font-weight: 700;
    background: linear-gradient(135deg, #CC1E1E, #E02424) !important;
    color: white !important; border: none !important;
    font-size: 1rem !important; padding: 0.6rem !important;
  }
  div[data-testid="stFormSubmitButton"] button:hover {
    background: linear-gradient(135deg, #a81818, #CC1E1E) !important;
    box-shadow: 0 4px 14px rgba(204,30,30,0.35) !important;
  }
  .foot-note {
    text-align: center; font-size: 0.78rem;
    color: #9CA3AF; margin-top: 1.2rem;
  }
</style>
""", unsafe_allow_html=True)

# ─── Logo ──────────────────────────────────────────────────────────
logo_path = Path(__file__).resolve().parents[1] / "img" / "Color PGL MS.png"
if logo_path.exists():
    logo_b64 = base64.b64encode(logo_path.read_bytes()).decode()
    st.markdown(f"""
    <div class="pg-logo-wrap">
        <img src="data:image/png;base64,{logo_b64}" class="pg-logo-img">
    </div>
    """, unsafe_allow_html=True)

# ─── Obtener token desde session_state (lo puso app.py) ───────────
token = st.session_state.get("reset_token", "")

# ══════════════════════════════════════════════════════════════════
# Sin token → enlace inválido o expirado
# ══════════════════════════════════════════════════════════════════
if not token:
    st.markdown("<div class='reset-card'>", unsafe_allow_html=True)
    st.markdown("<div class='reset-title'>🔐 Cambio de contraseña</div>",
                unsafe_allow_html=True)
    st.warning(
        "⚠️ **Enlace inválido o expirado.**\n\n"
        "Este link solo funciona una vez y caduca en 1 hora. "
        "Solicita uno nuevo desde la pantalla de inicio de sesión."
    )
    if st.button("← Ir al inicio de sesión", use_container_width=True):
        st.session_state.pop("reset_token", None)
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

# ══════════════════════════════════════════════════════════════════
# Con token → mostrar formulario de nueva contraseña
# ══════════════════════════════════════════════════════════════════
if st.session_state.get("reset_done"):
    # Pantalla de éxito
    st.markdown("<div class='reset-card'>", unsafe_allow_html=True)
    st.markdown("<div class='reset-title'>✅ ¡Listo!</div>", unsafe_allow_html=True)
    st.success("Tu contraseña fue actualizada correctamente.")
    st.info("Redirigiendo al inicio de sesión...")
    st.balloons()
    time.sleep(3)
    st.session_state.pop("reset_token", None)
    st.session_state.pop("reset_done", None)
    set_session_in_state(None)
    st.rerun()
else:
    st.markdown("<div class='reset-card'>", unsafe_allow_html=True)
    st.markdown("<div class='reset-title'>🔐 Crear nueva contraseña</div>",
                unsafe_allow_html=True)
    st.markdown("<div class='reset-sub'>Ingresa tu nueva contraseña para <strong>Portal PGL</strong></div>",
                unsafe_allow_html=True)

    with st.form("form_nueva_password", clear_on_submit=False):
        nueva     = st.text_input("Nueva contraseña",     type="password",
                                   placeholder="Mínimo 8 caracteres")
        confirmar = st.text_input("Confirmar contraseña", type="password",
                                   placeholder="Repite tu nueva contraseña")
        submitted = st.form_submit_button("💾 Guardar nueva contraseña",
                                          use_container_width=True)

    if submitted:
        if not nueva or not confirmar:
            st.error("❌ Por favor llena ambos campos.")
        elif nueva != confirmar:
            st.error("❌ Las contraseñas no coinciden.")
        elif len(nueva) < 8:
            st.error("❌ La contraseña debe tener al menos 8 caracteres.")
        else:
            try:
                sb  = get_supabase_anon_client()
                res = sb.auth.set_session(token, "")

                if not getattr(res, "session", None):
                    st.error("❌ El enlace expiró o ya fue usado. Pide uno nuevo.")
                    st.session_state.pop("reset_token", None)
                    st.stop()

                # Guardar sesión temporal para poder hacer el update
                set_session_in_state({
                    "access_token":  res.session.access_token,
                    "refresh_token": res.session.refresh_token,
                    "expires_at":    getattr(res.session, "expires_at", None),
                    "user": {
                        "id":    res.user.id,
                        "email": res.user.email,
                    } if getattr(res, "user", None) else None,
                })

                sb.auth.update_user({"password": nueva})

                # Limpiar sesión temporal y marcar éxito
                set_session_in_state(None)
                st.session_state["reset_done"] = True
                st.rerun()

            except Exception as e:
                err = str(e).lower()
                if any(x in err for x in ("expired", "invalid", "jwt")):
                    st.error("❌ El enlace expiró o ya fue usado. Regresa al login y pide uno nuevo.")
                    st.session_state.pop("reset_token", None)
                else:
                    st.error(f"❌ Error inesperado: {e}")

    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div class='foot-note'>Portal de Palos Garza Logistics · Área de Análisis de Datos</div>",
            unsafe_allow_html=True)
