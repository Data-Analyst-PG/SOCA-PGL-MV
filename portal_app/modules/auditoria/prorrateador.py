# portal_app/modules/auditoria/prorrateador.py
import streamlit as st
from . import prorrateador_gg, prorrateador_historico, prorrateador_resumen


def render():
    from ui.components import page_banner
    page_banner("🧮", "Prorrateador", "Prorrateo GG, historial consolidado y resúmenes")


    t1, t2, t3 = st.tabs(["🧾 Prorrateo GG", "📚 Consolidar histórico", "📊 Resúmenes"])

    with t1:
        prorrateador_gg.render()

    with t2:
        prorrateador_historico.render()

    with t3:
        prorrateador_resumen.render()
