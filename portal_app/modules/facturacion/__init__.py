# portal_app/modules/facturacion/__init__.py
from . import estado_cuenta, cargar_datos

def render():
    from ui.components import page_banner
    import streamlit as st

    page_banner("💳", "Facturación y Cobranza", "Estado de cuenta por cliente")

    t1, t2 = st.tabs(["📊 Estado de Cuenta", "📤 Cargar Datos"])

    with t1:
        estado_cuenta.render()

    with t2:
        cargar_datos.render()

# Alias para compatibilidad con imports existentes
def estado_cuenta_page():
    render()
