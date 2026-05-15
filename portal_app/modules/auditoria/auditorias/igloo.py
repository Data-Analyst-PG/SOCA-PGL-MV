# portal_app/modules/auditoria/auditorias/igloo.py
# ─────────────────────────────────────────────────────────────────────────────
# Auditoría igloo — En desarrollo
# ─────────────────────────────────────────────────────────────────────────────
import streamlit as st
from ui.components import section_header, alert


def render():
    section_header("🚧", "En desarrollo",
                   "Este módulo estará disponible próximamente")
    alert("info", "La auditoría de esta empresa está siendo desarrollada.")
