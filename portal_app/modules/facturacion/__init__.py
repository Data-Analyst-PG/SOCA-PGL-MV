# portal_app/modules/facturacion/__init__.py
import streamlit as st

from . import estado_cuenta, cargar_datos
from services.auditoria import registrar_acceso_submodulo

ETIQUETAS_FACTURACION = ["📊 Estado de Cuenta", "📤 Cargar Datos"]
MODULOS_FACTURACION = [estado_cuenta, cargar_datos]


def render():
    from ui.components import page_banner
    page_banner("💳", "Facturación y Cobranza", "Estado de cuenta por cliente")

    def _on_cambio_seccion():
        registrar_acceso_submodulo("fact-estado-cuenta", st.session_state["fact_router_seccion"])

    seccion = st.segmented_control(
        "Sección",
        options=ETIQUETAS_FACTURACION,
        default=ETIQUETAS_FACTURACION[0],
        key="fact_router_seccion",
        on_change=_on_cambio_seccion,
    )
    seccion = seccion or ETIQUETAS_FACTURACION[0]

    idx = ETIQUETAS_FACTURACION.index(seccion)
    MODULOS_FACTURACION[idx].render()


# Alias para compatibilidad con imports existentes
def estado_cuenta_page():
    render()
