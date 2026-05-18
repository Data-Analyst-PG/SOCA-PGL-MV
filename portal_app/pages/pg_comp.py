from modules.solicitudes.complementarias import captura, consulta
import streamlit as st
from ui.components import page_banner

page_banner("📋", "Complementarias", "Solicitudes de cargos complementarios")
tab1, tab2 = st.tabs(["➕ Nueva Solicitud", "🔍 Consultar Estatus"])
with tab1:
    captura.render()
with tab2:
    consulta.render()
