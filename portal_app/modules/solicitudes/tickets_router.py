"""
tickets_router.py
Router de Tickets — homologado con el patrón de cotizadores
(igloo_router.py / lincoln_router.py): segmented_control en vez de
st.tabs(), con auditoría de navegación vía registrar_acceso_submodulo.
"""

import streamlit as st

from ui.components import page_banner
from services.auditoria import registrar_acceso_submodulo

from .tickets import crear, consultar

ETIQUETAS_TICKETS = ["➕ Crear Ticket", "🔍 Consultar Estatus"]
MODULOS_TICKETS = [crear, consultar]


def render():
    page_banner("🎫", "Tickets", "Solicitudes al equipo de Análisis de Datos")

    def _on_cambio_seccion():
        registrar_acceso_submodulo("tickets", st.session_state["tickets_router_seccion"])

    seccion = st.segmented_control(
        "Sección",
        options=ETIQUETAS_TICKETS,
        default=ETIQUETAS_TICKETS[0],
        key="tickets_router_seccion",
        on_change=_on_cambio_seccion,
    )
    seccion = seccion or ETIQUETAS_TICKETS[0]

    idx = ETIQUETAS_TICKETS.index(seccion)
    MODULOS_TICKETS[idx].render()
