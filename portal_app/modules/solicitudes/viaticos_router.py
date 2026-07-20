"""
viaticos_router.py
Router de Viáticos — homologado con el patrón de cotizadores
(igloo_router.py / lincoln_router.py): segmented_control en vez de
st.tabs(), con auditoría de navegación vía registrar_acceso_submodulo.
"""

import streamlit as st

from ui.components import page_banner
from services.auditoria import registrar_acceso_submodulo

from .viaticos import crear, consultar

ETIQUETAS_VIATICOS = ["➕ Nueva Solicitud", "🔍 Consultar Estatus"]
MODULOS_VIATICOS = [crear, consultar]


def render():
    page_banner("💼", "Viáticos", "Solicitudes de viáticos")

    def _on_cambio_seccion():
        registrar_acceso_submodulo("viaticos", st.session_state["viat_router_seccion"])

    seccion = st.segmented_control(
        "Sección",
        options=ETIQUETAS_VIATICOS,
        default=ETIQUETAS_VIATICOS[0],
        key="viat_router_seccion",
        on_change=_on_cambio_seccion,
    )
    seccion = seccion or ETIQUETAS_VIATICOS[0]

    idx = ETIQUETAS_VIATICOS.index(seccion)
    MODULOS_VIATICOS[idx].render()
