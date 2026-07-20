"""
complementarias_router.py
Router de Complementarias — homologado con el patrón de cotizadores
(igloo_router.py / lincoln_router.py): segmented_control en vez de
st.tabs(), con auditoría de navegación vía registrar_acceso_submodulo.
"""

import streamlit as st

from ui.components import page_banner
from services.auditoria import registrar_acceso_submodulo

from .complementarias import captura, consulta

ETIQUETAS_COMPLEMENTARIAS = ["➕ Nueva Solicitud", "🔍 Consultar Estatus"]
MODULOS_COMPLEMENTARIAS = [captura, consulta]


def render():
    page_banner("📋", "Complementarias", "Solicitudes de cargos complementarios")

    def _on_cambio_seccion():
        registrar_acceso_submodulo("complementarias", st.session_state["comp_router_seccion"])

    seccion = st.segmented_control(
        "Sección",
        options=ETIQUETAS_COMPLEMENTARIAS,
        default=ETIQUETAS_COMPLEMENTARIAS[0],
        key="comp_router_seccion",
        on_change=_on_cambio_seccion,
    )
    seccion = seccion or ETIQUETAS_COMPLEMENTARIAS[0]

    idx = ETIQUETAS_COMPLEMENTARIAS.index(seccion)
    MODULOS_COMPLEMENTARIAS[idx].render()
