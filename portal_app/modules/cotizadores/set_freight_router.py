from ui.components import page_banner, section_header, alert, divider
"""
set_freight_router.py  –  Set Freight LLC
Router principal con tabs horizontal.
SIN programación de viajes ni viajes concluidos.
"""

import streamlit as st

from .set_freight import captura_rutas, consulta_ruta, gestion_rutas, simulador, cotizacion

TAB_NAMES = [
    "🛣️ Captura de Rutas",
    "🔍 Consulta Ruta",
    "🗂️ Gestión de Rutas",
    "🔁 Simulador",
    "🗒️ Cotización PDF",
]

TAB_MODULES = [
    captura_rutas,
    consulta_ruta,
    gestion_rutas,
    simulador,
    cotizacion,
]


def render():
    page_banner("📦", "Set Freight LLC", "Cotizador · 16 Sucursales · Aislamiento por sucursal")

    tab_activo = st.radio(
        "Módulo",
        TAB_NAMES,
        horizontal=True,
        label_visibility="collapsed",
        key="sf_tab_activo",
    )
    divider()

    idx = TAB_NAMES.index(tab_activo)
    TAB_MODULES[idx].render()
