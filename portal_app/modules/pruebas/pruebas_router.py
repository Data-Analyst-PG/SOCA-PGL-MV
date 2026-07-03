from __future__ import annotations

import streamlit as st
from ui.components import page_banner
from services.zoho_token_test import generar_refresh_token


def render():
    page_banner("🧪", "Módulo de Pruebas — Zoho Analytics", "Generación de token para inventario")

    st.subheader("Paso 1 — Generar Refresh Token de Zoho")

    client_id = st.secrets.get("ZOHO_CLIENT_ID", "")
    client_secret = st.secrets.get("ZOHO_CLIENT_SECRET", "")
    accounts_url = st.secrets.get("ZOHO_ACCOUNTS_URL", "https://accounts.zoho.com")

    st.write(f"**Client ID encontrado:** {'✅ Sí' if client_id else '❌ No'}")
    st.write(f"**Client Secret encontrado:** {'✅ Sí' if client_secret else '❌ No'}")

    grant_token = st.text_input(
        "Pega aquí el código temporal que te dio Zoho",
        type="password"
    )

    if st.button("Generar refresh token"):
        if not client_id or not client_secret:
            st.error("Faltan ZOHO_CLIENT_ID o ZOHO_CLIENT_SECRET en secrets.")
            return

        if not grant_token:
            st.warning("Primero pega el código temporal de Zoho.")
            return

        data = generar_refresh_token(
            client_id=client_id,
            client_secret=client_secret,
            grant_token=grant_token,
            accounts_url=accounts_url
        )

        st.write(data)

        if "refresh_token" in data:
            st.success("✅ Refresh token generado correctamente.")
            st.code(data["refresh_token"])
            st.warning("Copia este refresh token y guárdalo en secrets como ZOHO_REFRESH_TOKEN.")
        else:
            st.error("❌ No se pudo generar el refresh token. Revisa el error que aparece arriba.")
