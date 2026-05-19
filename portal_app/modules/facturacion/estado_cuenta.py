# portal_app/modules/facturacion/estado_cuenta.py
# Dashboard de estado de cuenta por cliente.
import streamlit as st
from datetime import date

from modules.facturacion.data_source import get_clientes, get_facturas_cliente
from modules.facturacion.facturacion import perfil_riesgo, generar_pdf_estado_cuenta, LOGO_B64
from ui.components import (
    page_banner, section_header, divider,
    kpi_card, client_header, gauge_riesgo,
    credit_bar, facturas_table, payment_info,
)


def render():
    page_banner("💳", "Facturación y Cobranza", "Estado de cuenta por cliente — Beta")

    clientes = get_clientes()
    nombres  = [c["nombre"] for c in clientes]

    st.markdown(
        '<div style="font-size:0.70rem;color:#9CA3AF;font-weight:700;'
        'text-transform:uppercase;letter-spacing:0.5px;margin-bottom:0.3rem;">'
        '🏢 SELECCIONAR CLIENTE</div>',
        unsafe_allow_html=True,
    )
    st.markdown("""
    <style>
    div[data-testid="stSelectbox"]:first-of-type > div > div {
        background: white !important;
        border: 2px solid #1B2266 !important;
        border-radius: 10px !important;
        font-weight: 700 !important;
        color: #1B2266 !important;
        box-shadow: 0 2px 8px rgba(27,34,102,0.10) !important;
        font-size: 1rem !important;
    }
    </style>
    """, unsafe_allow_html=True)

    seleccion = st.selectbox("Cliente", nombres, label_visibility="collapsed", key="fact_sel_cliente")

    cliente  = next(c for c in clientes if c["nombre"] == seleccion)
    facturas = get_facturas_cliente(cliente["id"])

    total     = sum(f["importe"] for f in facturas)
    dias_max  = max((f["dias_vencido"] for f in facturas), default=0)
    pct_usado = total / cliente["limite_credito"] * 100 if cliente["limite_credito"] else 0
    estado, color_r, angulo = perfil_riesgo(dias_max, pct_usado)

    # Encabezado cliente
    client_header(cliente, estado, color_r, LOGO_B64)

    # KPIs
    k1, k2, k3, k4 = st.columns(4)
    kpi_card(k1, "Límite de Crédito", f"${cliente['limite_credito']:,.0f} USD", "#1B2266")
    kpi_card(k2, "Condiciones",        cliente["condiciones_pago"],               "#6B7280")
    kpi_card(k3, "Total Balance",      f"${total:,.0f} USD",                      color_r)
    kpi_card(k4, "Facturas Activas",   f"{len(facturas)} facturas",               "#1B2266")

    st.markdown("<br>", unsafe_allow_html=True)

    # Tabla + Panel lateral
    col_tabla, col_panel = st.columns([6, 3])

    with col_tabla:
        fc1, fc2 = st.columns([3, 1])
        with fc1:
            st.markdown(
                '<div style="font-weight:700;font-size:1rem;color:#1B2266;margin-bottom:0.5rem;">'
                f'📄 FACTURAS &nbsp;<span style="background:#F1F5F9;color:#9CA3AF;font-size:0.72rem;'
                f'padding:3px 10px;border-radius:6px;font-family:monospace;font-weight:400;">'
                f'As of {date.today().strftime("%d %B %Y")}</span></div>',
                unsafe_allow_html=True,
            )
        with fc2:
            filtro = st.selectbox(
                "Filtrar", ["Todas", "Vencidas", "Al corriente"],
                label_visibility="collapsed", key="fact_filtro",
            )

        facturas_table(facturas, filtro)

        st.markdown(
            '<div style="display:flex;justify-content:flex-end;align-items:center;gap:1rem;'
            'padding:0.8rem 1rem;margin-top:0.3rem;background:white;border-radius:10px;border:1px solid #E5E9F0;">'
            '<span style="font-size:0.85rem;font-weight:600;color:#6B7280;">TOTAL BALANCE</span>'
            f'<span style="font-size:1.2rem;font-weight:800;color:{color_r};">${total:,.0f} USD</span>'
            '</div>',
            unsafe_allow_html=True,
        )

        # Botón PDF
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("📄 Generar PDF para cliente", type="primary", key="fact_gen_pdf"):
            with st.spinner("Generando PDF..."):
                pdf_bytes = generar_pdf_estado_cuenta(cliente, facturas, total, estado, color_r)
            nombre_pdf = f"EstadoCuenta_{cliente['nombre'].replace(' ', '_')}_{date.today()}.pdf"
            st.download_button(
                label="⬇️ Descargar Estado de Cuenta",
                data=pdf_bytes,
                file_name=nombre_pdf,
                mime="application/pdf",
                key="fact_download_pdf",
            )

    with col_panel:
        st.markdown(
            '<div style="font-size:0.65rem;color:#9CA3AF;font-weight:700;'
            'text-transform:uppercase;letter-spacing:0.5px;margin-bottom:0.3rem;">PERFIL DE RIESGO</div>',
            unsafe_allow_html=True,
        )
        with st.container(border=True):
            gauge_riesgo(estado, color_r, angulo)

        st.markdown("<br>", unsafe_allow_html=True)

        st.markdown(
            '<div style="font-size:0.65rem;color:#9CA3AF;font-weight:700;'
            'text-transform:uppercase;letter-spacing:0.5px;margin-bottom:0.3rem;">LÍNEA DE CRÉDITO</div>',
            unsafe_allow_html=True,
        )
        with st.container(border=True):
            credit_bar(total, cliente["limite_credito"], color_r)

        st.markdown("<br>", unsafe_allow_html=True)

        st.markdown(
            '<div style="font-size:0.65rem;color:#9CA3AF;font-weight:700;'
            'text-transform:uppercase;letter-spacing:0.5px;margin-bottom:0.3rem;">INFORMACIÓN DE PAGO</div>',
            unsafe_allow_html=True,
        )
        payment_info(cliente)
