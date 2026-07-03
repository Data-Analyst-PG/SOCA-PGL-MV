from __future__ import annotations

import streamlit as st
from ui.components import page_banner
from services.zoho_analytics_inventory import (
    generar_inventario_zoho,
    get_access_token,
    get_workspaces,
)


def render():
    page_banner(
        "🧪",
        "Módulo de Pruebas — Inventario Zoho Analytics",
        "Genera un Excel con Workspaces, tablas, reportes, dashboards y query tables"
    )

    st.subheader("Inventario automático de Zoho Analytics")

    client_id = st.secrets.get("ZOHO_CLIENT_ID", "")
    client_secret = st.secrets.get("ZOHO_CLIENT_SECRET", "")
    refresh_token = st.secrets.get("ZOHO_REFRESH_TOKEN", "")
    accounts_url = st.secrets.get("ZOHO_ACCOUNTS_URL", "https://accounts.zoho.com")
    analytics_api_url = st.secrets.get("ZOHO_ANALYTICS_API_URL", "https://analyticsapi.zoho.com")

    st.write(f"**Client ID encontrado:** {'✅ Sí' if client_id else '❌ No'}")
    st.write(f"**Client Secret encontrado:** {'✅ Sí' if client_secret else '❌ No'}")
    st.write(f"**Refresh Token encontrado:** {'✅ Sí' if refresh_token else '❌ No'}")

    st.info(
        "Este proceso solo consulta metadata de Zoho Analytics. "
        "No modifica, elimina ni actualiza información."
    )

    if st.button("Probar Workspaces disponibles"):
        if not client_id or not client_secret or not refresh_token:
            st.error("Faltan credenciales de Zoho en secrets.")
            return

        try:
            access_token = get_access_token(
                client_id=client_id,
                client_secret=client_secret,
                refresh_token=refresh_token,
                accounts_url=accounts_url
            )

            workspaces = get_workspaces(
                access_token=access_token,
                analytics_api_url=analytics_api_url
            )

            st.write(f"Workspaces encontrados: {len(workspaces)}")
            st.dataframe(workspaces, use_container_width=True)

        except Exception as e:
            st.error("Ocurrió un error al consultar los Workspaces.")
            st.exception(e)

    if st.button("Generar inventario Zoho"):
        if not client_id or not client_secret or not refresh_token:
            st.error("Faltan credenciales de Zoho en secrets.")
            return

        with st.spinner("Consultando Zoho Analytics y generando Excel..."):
            try:
                df, excel_file = generar_inventario_zoho(
                    client_id=client_id,
                    client_secret=client_secret,
                    refresh_token=refresh_token,
                    accounts_url=accounts_url,
                    analytics_api_url=analytics_api_url
                )

                st.success(f"✅ Inventario generado correctamente. Registros encontrados: {len(df)}")

                st.dataframe(df, use_container_width=True)

                st.download_button(
                    label="📥 Descargar Excel",
                    data=excel_file,
                    file_name="Inventario_Zoho_Analytics.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            except Exception as e:
                st.error("Ocurrió un error al generar el inventario.")
                st.exception(e)
