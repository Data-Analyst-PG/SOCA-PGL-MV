from modules.solicitudes.viaticos import crear, consultar
import streamlit as st
from ui.components import page_banner

page_banner("💼", "Viáticos", "Solicitudes de viáticos")
tab1, tab2 = st.tabs(["➕ Nueva Solicitud", "🔍 Consultar Estatus"])
with tab1:
    crear.render()
with tab2:
    consultar.render()
