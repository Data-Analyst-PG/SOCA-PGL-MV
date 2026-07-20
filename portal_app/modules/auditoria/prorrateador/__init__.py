"""
modules/auditoria/prorrateador/__init__.py
Router de Prorrateador — homologado con auditorias/__init__.py:
segmented_control en vez de st.tabs(), con auditoría de navegación
vía registrar_acceso_submodulo.
"""

import streamlit as st

from ui.components import page_banner
from services.auditoria import registrar_acceso_submodulo

from . import prorrateador_gg, prorrateador_historico, prorrateador_resumen

ETIQUETAS_PRORRATEADOR = ["🧾 Prorrateo GG", "📚 Consolidar histórico", "📊 Resúmenes"]
MODULOS_PRORRATEADOR = [prorrateador_gg, prorrateador_historico, prorrateador_resumen]


def render():
    page_banner("🧮", "Prorrateador", "Prorrateo GG, historial consolidado y resúmenes")

    def _on_cambio_seccion():
        registrar_acceso_submodulo("aud-prorrateador", st.session_state["prorrateador_seccion"])

    seccion = st.segmented_control(
        "Sección",
        options=ETIQUETAS_PRORRATEADOR,
        default=ETIQUETAS_PRORRATEADOR[0],
        key="prorrateador_seccion",
        on_change=_on_cambio_seccion,
    )
    seccion = seccion or ETIQUETAS_PRORRATEADOR[0]

    idx = ETIQUETAS_PRORRATEADOR.index(seccion)
    MODULOS_PRORRATEADOR[idx].render()
