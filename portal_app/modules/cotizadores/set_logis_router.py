from ui.components import page_banner, section_header, alert, divider
"""
set_logis_router.py  –  Set Logis Plus
Router principal. Lazy loading vía radio horizontal.
"""

import streamlit as st

from .set_logis import (
    captura_rutas,
    consulta_ruta,
    gestion_rutas,
    simulador,
    cotizacion,
    programacion_viajes,
    viajes_concluidos,
)

TAB_NAMES = [
    "🛣️ Captura de Rutas",
    "🔍 Consulta Ruta",
    "🗂️ Gestión de Rutas",
    "🔁 Simulador VR",
    "🗒️ Cotización",
]

TAB_MODULES = [
    captura_rutas,
    consulta_ruta,
    gestion_rutas,
    simulador,
    cotizacion,
]


def render():
    page_banner("🚚", "Set Logis Plus", "Cotizador Owner-Operator · Subidas & Bajadas USA/MX")

    tab_activo = st.radio(
        "Módulo",
        TAB_NAMES,
        horizontal=True,
        label_visibility="collapsed",
        key="sl_tab_activo",
    )
    divider()

    idx = TAB_NAMES.index(tab_activo)
    TAB_MODULES[idx].render()
