from ui.components import page_banner, section_header, alert, divider
"""
lincoln_router.py
Router principal del Cotizador Lincoln.
Incluye encabezado de marca y navegación por tabs.
"""

import streamlit as st

from .lincoln import (
    captura_rutas,
    consulta_ruta,
    gestion_rutas,
    simulador,
    cotizacion,
)


def render():
    page_banner("🚛", "Cotizador Lincoln Freight", "Captura, análisis y programación de rutas USA/MX")

    tabs = st.tabs([
        "🛣️ Captura de Rutas",
        "🔍 Consulta Ruta",
        "🗂️ Gestión de Rutas",
        "🔁 Simulador VR",
        "🗒️ Cotización",
    ])

    with tabs[0]: captura_rutas.render()
    with tabs[1]: consulta_ruta.render()
    with tabs[2]: gestion_rutas.render()
    with tabs[3]: simulador.render()
    with tabs[4]: cotizacion.render()
    with tabs[5]: programacion_viajes.render()
    with tabs[6]: viajes_concluidos.render()
