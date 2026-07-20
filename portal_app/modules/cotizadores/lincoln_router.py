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
from services.auditoria import registrar_acceso_submodulo

ETIQUETAS_LINCOLN = [
    "🛣️ Captura de Rutas",
    "🔍 Consulta Ruta",
    "🗂️ Gestión de Rutas",
    "🔁 Simulador VR",
    "🗒️ Cotización",
]
MODULOS_LINCOLN = [captura_rutas, consulta_ruta, gestion_rutas, simulador, cotizacion]


def render():
    page_banner("🚛", "Cotizador Lincoln Freight", "Captura, análisis y programación de rutas USA/MX")

    def _on_cambio_seccion():
        registrar_acceso_submodulo("cot-lincoln", st.session_state["lincoln_router_seccion"])

    seccion = st.segmented_control(
        "Sección",
        options=ETIQUETAS_LINCOLN,
        default=ETIQUETAS_LINCOLN[0],
        key="lincoln_router_seccion",
        on_change=_on_cambio_seccion,
    )
    seccion = seccion or ETIQUETAS_LINCOLN[0]

    idx = ETIQUETAS_LINCOLN.index(seccion)
    MODULOS_LINCOLN[idx].render()
