from modules.solicitudes.tickets import crear, consultar
import streamlit as st
from ui.components import page_banner

page_banner("🎫", "Tickets", "Solicitudes al equipo de Análisis de Datos")
tab1, tab2 = st.tabs(["➕ Crear Ticket", "🔍 Consultar Estatus"])
with tab1:
    crear.render()
with tab2:
    consultar.render()
