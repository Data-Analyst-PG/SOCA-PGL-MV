import streamlit as st
from ui.components import page_banner, alert, divider

def render():
    page_banner("🧪", "Módulo de Pruebas", "Sandbox de desarrollo — solo acceso autorizado")
    divider()
    st.info("Aquí irán los módulos en prueba. Por ahora el módulo está vacío.")
