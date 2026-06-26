# portal_app/modules/auditoria/rentabilidad_clientes.py
# ─────────────────────────────────────────────────────────────────────────────
# Router de Rentabilidad Clientes
# Estructura: 4 tabs, cada una en su propio módulo dentro de /rentabilidad/
#
# Para agregar una tab nueva:
#   1. Crear portal_app/modules/auditoria/rentabilidad/nueva_tab.py con render()
#   2. Importarla aquí y agregarla al st.tabs
# ─────────────────────────────────────────────────────────────────────────────
import streamlit as st
from ui.components import page_banner

from .rentabilidad import (
    dashboard,
    merma,
    catalogo_cuentas,
    catalogo_clientes,
)


def render():
    page_banner(
        "💹",
        "Rentabilidad Clientes",
        "Semáforo semanal · Merma por cliente · Catálogos de cuentas y clientes",
    )

    t1, t2, t3, t4 = st.tabs([
        "🚦 Semáforo Semanal",
        "💸 Merma por Cliente",
        "🧾 Catálogo de Cuentas",
        "🏢 Catálogo de Clientes",
    ])

    with t1:
        dashboard.render()

    with t2:
        merma.render()

    with t3:
        catalogo_cuentas.render()

    with t4:
        catalogo_clientes.render()
