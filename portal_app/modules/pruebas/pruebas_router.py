from __future__ import annotations
import streamlit as st
from ui.components import page_banner

def render():
    page_banner("🧪", "Módulo de Pruebas — Banxico", "Diagnóstico de tipo de cambio FIX")

    from services.banxico import get_tipo_cambio_fix

    token = st.secrets.get("TOKEN_BMX", "")
    st.write(f"**Token encontrado:** {'✅ Sí' if token else '❌ No'}")
    st.write(f"**Token (primeros 8 chars):** `{token[:8]}...`")

    tc = get_tipo_cambio_fix(token) if token else None
    st.write(f"**Banxico devuelve:** `{tc}`")

    if tc:
        st.success(f"✅ TC FIX del día: **${tc:,.4f} MXP/USD**")
    else:
        st.error("❌ Banxico devolvió None — revisa token o conexión")
