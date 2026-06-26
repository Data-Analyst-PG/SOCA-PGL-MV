import streamlit as st
from ui.components import section_header, alert


def render():
    section_header("📊", "Dashboard",
                   "Este módulo estará disponible próximamente")
    alert("info", "🚧 El dashboard está siendo desarrollado.")
