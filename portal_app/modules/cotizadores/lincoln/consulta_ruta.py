from ui.components import section_header, alert, divider
"""
consulta_ruta.py – Lincoln Freight (USA/MX)
Consulta individual con filtros, simulador de parámetros y descarga PDF
Versión actualizada con estructura Igloo + lógica Lincoln 2026
"""

import os
import tempfile

import pandas as pd
import streamlit as st

from services.supabase_client import get_supabase_client
from ._shared import (
    TABLE_RUTAS, EXTRAS_USA,
    cargar_datos_generales, safe,
)


def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


# ─────────────────────────────────────────────
# CACHE
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=120)
def _load_rutas_lincoln_cached(table_name: str):
    supabase = get_supabase_client()
    if supabase is None:
        return pd.DataFrame()
    try:
        resp = supabase.table(table_name).select("*").order("Fecha", desc=True).execute()
        return pd.DataFrame(resp.data)
    except Exception as e:
        st.error(f"Error consultando Supabase: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────
# FILTROS
# ─────────────────────────────────────────────
def _filtrar_rutas(df, prefix_key):
    """Muestra filtros opcionales y devuelve el DataFrame filtrado"""
    with st.expander("🔎 Filtros de búsqueda (opcional)", expanded=False):
        fc1, fc2, fc3, fc4, fc5 = st.columns(5)
    
        with fc1:
            tipos_disp = ["Todos"] + sorted(df["Tipo"].dropna().unique().tolist())
            filtro_tipo = st.selectbox("Tipo", tipos_disp, key=f"{prefix_key}_ftipo")
    
        with fc2:
            clientes_disp = ["Todos"] + sorted(df["Cliente"].dropna().astype(str).unique().tolist())
            filtro_cliente = st.selectbox("Cliente", clientes_disp, key=f"{prefix_key}_fcliente")
    
        with fc3:
            filtro_origen = st.text_input("Origen contiene", key=f"{prefix_key}_forigen")
    
        with fc4:
            filtro_destino = st.text_input("Destino contiene", key=f"{prefix_key}_fdestino")
    
        with fc5:
            filtro_id = st.text_input("ID Ruta", key=f"{prefix_key}_fid", placeholder="LN000123")

    resultado = df.copy()
    if filtro_tipo != "Todos":
        resultado = resultado[resultado["Tipo"] == filtro_tipo]
    if filtro_cliente != "Todos":
        resultado = resultado[resultado["Cliente"].astype(str) == filtro_cliente]
    if filtro_origen.strip():
        resultado = resultado[resultado["Origen"].astype(str).str.contains(filtro_origen.strip(), case=False, na=False)]
    if filtro_destino.strip():
        resultado = resultado[resultado["Destino"].astype(str).str.contains(filtro_destino.strip(), case=False, na=False)]
    if filtro_id.strip():
        resultado = resultado[resultado["ID_Ruta"].astype(str).str.contains(filtro_id.strip(), case=False, na=False)]
    return resultado


def _format_ruta_label(row):
    """Formatea una ruta para selectores"""
    fecha = str(row.get("Fecha", ""))[:10]
    return (
        f"{row.get('ID_Ruta', '')} | {fecha} | "
        f"{row.get('Tipo', '')} | {row.get('Cliente', '')} | "
        f"{row.get('Origen', '')} → {row.get('Destino', '')}"
    )


# ─────────────────────────────────────────────
# CÁLCULO DE RUTA CON SIMULACIÓN
# ─────────────────────────────────────────────
def calcular_ruta_lincoln_consulta(ruta, valores):
    """
    Recalcula la ruta con valores actuales o simulados
    Versión simplificada para consulta (sin otros_cargos_pagados)
    """
    tc = float(valores.get("Tipo de Cambio USD/MXP", 18.5))
    mpg = float(valores.get("Truck Performance (mpg)", 7.0))
    diesel_precio = float(valores.get("Diesel Price ($/gal)", 3.60))
    isr_imss = float(valores.get("ISR/IMSS", 462.66))
    bono_por_milla = float(valores.get("Bono por milla cargada", 0.01))
    
    millas_usa = safe(ruta.get("Millas_USA", 0))
    millas_vacias = safe(ruta.get("Millas_Vacias", 0))
    modo_viaje = str(ruta.get("Modo_Viaje", "Sencillo"))
    
    # Ingresos USA
    ingreso_flete_usa = safe(ruta.get("Ingreso_Flete_USA", 0))
    ingreso_fuel_usa = safe(ruta.get("Ingreso_Fuel_USA", 0))
    ingreso_cruce = safe(ruta.get("Ingreso_Cruce", 0))
    ingreso_mx_usd = safe(ruta.get("Ingreso_MX_USD", 0))
    otros_cargos_ingreso = safe(ruta.get("Otros_Cargos_Ingreso", 0))
    
    # Sueldo operador
    if modo_viaje == "Team":
        cxm_cargado = float(valores.get("CXM Team USA", 0.30))
        cxm_vacio = float(valores.get("CXM Team USA (Empty)", 0.25))
        factor = 2
    else:
        cxm_cargado = float(valores.get("CXM Operador USA", 0.48))
        cxm_vacio = float(valores.get("CXM Operador USA (Empty)", 0.30))
        factor = 1
    
    sueldo_base = (millas_usa * cxm_cargado + millas_vacias * cxm_vacio) * factor
    bono_millas = (millas_usa * bono_por_milla) * factor
    sueldo_usa = sueldo_base + bono_millas
    
    # Diesel
    diesel_usa = ((millas_usa + millas_vacias) / mpg) * diesel_precio if mpg else 0.0
    
    # Otros costos de la ruta guardada
    costo_cruce = safe(ruta.get("Costo_Cruce", 0))
    costo_mx_usd = safe(ruta.get("Costo_MX_USD", 0))
    otros_cargos_costo = safe(ruta.get("Otros_Cargos_Costo", 0))
    
    # TOTALES
    ingreso_total = ingreso_flete_usa + ingreso_fuel_usa + ingreso_cruce + ingreso_mx_usd + otros_cargos_ingreso
    costo_directo = sueldo_usa + diesel_usa + costo_cruce + costo_mx_usd + otros_cargos_costo
    costo_directo_total = costo_directo + isr_imss
    
    utilidad_bruta = ingreso_total - costo_directo_total
    pct_bruta = (utilidad_bruta / ingreso_total * 100) if ingreso_total > 0 else 0.0
    
    costos_ind = ingreso_total * 0.42
    utilidad_neta = utilidad_bruta - costos_ind
    pct_neta = (utilidad_neta / ingreso_total * 100) if ingreso_total > 0 else 0.0
    
    return {
        "ingreso_flete_usa": ingreso_flete_usa,
        "ingreso_fuel_usa": ingreso_fuel_usa,
        "ingreso_cruce": ingreso_cruce,
        "ingreso_mx_usd": ingreso_mx_usd,
        "otros_cargos_ingreso": otros_cargos_ingreso,
        "ingreso_total": ingreso_total,
        "sueldo_base": sueldo_base,
        "bono_millas": bono_millas,
        "sueldo_usa": sueldo_usa,
        "diesel_usa": diesel_usa,
        "costo_cruce": costo_cruce,
        "costo_mx_usd": costo_mx_usd,
        "otros_cargos_costo": otros_cargos_costo,
        "isr_imss": isr_imss,
        "costo_directo_total": costo_directo_total,
        "utilidad_bruta": utilidad_bruta,
        "pct_bruta": pct_bruta,
        "costos_ind": costos_ind,
        "utilidad_neta": utilidad_neta,
        "pct_neta": pct_neta,
    }


# ─────────────────────────────────────────────
# MOSTRAR RESULTADOS
# ─────────────────────────────────────────────
def _mostrar_resultados_utilidad(r: dict):
    """Muestra resumen de utilidades tipo Igloo"""
    divider()
    section_header("📊", "Resumen de Utilidades")
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("💰 Ingreso Total", f"${r['ingreso_total']:,.2f}")
    with col2:
        color_bruta = "normal" if r["utilidad_bruta"] >= 0 else "inverse"
        st.metric("📊 Utilidad Bruta", f"${r['utilidad_bruta']:,.2f}", f"{r['pct_bruta']:.2f}%", delta_color=color_bruta)
    
    col3, col4 = st.columns(2)
    with col3:
        st.metric("💸 Costo Total", f"${r['costo_directo_total']:,.2f}")
    with col4:
        st.metric("📈 Costos Indirectos (42%)", f"${r['costos_ind']:,.2f}")
    
    color_neta = "normal" if r["utilidad_neta"] >= 0 else "inverse"
    st.metric("✨ Utilidad Neta", f"${r['utilidad_neta']:,.2f}", f"{r['pct_neta']:.2f}%", delta_color=color_neta)


# ─────────────────────────────────────────────
# PDF PROFESIONAL
# ─────────────────────────────────────────────
def generar_pdf_lincoln(ruta, r, simulando=False, params_sim=None):
    """Genera PDF profesional con reportlab"""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    doc = SimpleDocTemplate(
        tmp.name, pagesize=letter,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
    )

    styles = getSampleStyleSheet()
    
    subtitle_style = ParagraphStyle(
        "CustomSubtitle", parent=styles["Heading2"],
        fontSize=11, textColor=colors.HexColor("#1B2266"),
        spaceBefore=12, spaceAfter=4,
    )
    normal = ParagraphStyle(
        "CustomNormal", parent=styles["Normal"],
        fontSize=9, leading=12,
    )

    story = []

    # Encabezado
    header_data = [[
        Paragraph("<b>LINCOLN FREIGHT</b>", ParagraphStyle(
            "Header", parent=styles["Normal"], fontSize=13,
            textColor=colors.white,
        )),
        Paragraph("Consulta Individual de Ruta", ParagraphStyle(
            "HeaderRight", parent=styles["Normal"], fontSize=9,
            textColor=colors.white, alignment=TA_RIGHT,
        )),
    ]]
    header_table = Table(header_data, colWidths=[5.0 * inch, 2.0 * inch])
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#1B2266")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (0, -1), 12),
        ("RIGHTPADDING", (-1, 0), (-1, -1), 12),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 12))

    if simulando:
        story.append(Paragraph(
            "<i>* Este reporte fue generado con valores de simulación</i>",
            ParagraphStyle("SimNote", parent=normal, textColor=colors.HexColor("#e67e22")),
        ))
        story.append(Spacer(1, 6))

    # Datos Generales
    story.append(Paragraph("Datos Generales de la Ruta", subtitle_style))
    
    datos_generales = [
        ["ID Ruta:", str(ruta.get("ID_Ruta", ""))],
        ["Fecha:", str(ruta.get("Fecha", ""))[:10]],
        ["Tipo:", str(ruta.get("Tipo", ""))],
        ["Cliente:", str(ruta.get("Cliente", ""))],
        ["Modo Viaje:", str(ruta.get("Modo_Viaje", ""))],
        ["Origen → Destino USA:", f"{ruta.get('Origen', '')} → {ruta.get('Destino', '')}"],
        ["Millas USA (Cargadas):", f"{safe(ruta.get('Millas_USA', 0)):,.0f}"],
        ["Millas Vacías:", f"{safe(ruta.get('Millas_Vacias', 0)):,.0f}"],
    ]
    
    if ruta.get("Origen_MX") or ruta.get("Destino_MX"):
        datos_generales.append(["Origen → Destino MX:", f"{ruta.get('Origen_MX', '')} → {ruta.get('Destino_MX', '')}"])
    
    table_datos = Table(datos_generales, colWidths=[2.0 * inch, 4.5 * inch])
    table_datos.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f0f0")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (0, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(table_datos)
    story.append(Spacer(1, 12))

    # Resumen Financiero
    story.append(Paragraph("Resumen Financiero", subtitle_style))
    
    resumen_data = [
        ["Ingreso Total:", f"${r['ingreso_total']:,.2f}"],
        ["Costo Directo Total:", f"${r['costo_directo_total']:,.2f}"],
        ["Utilidad Bruta:", f"${r['utilidad_bruta']:,.2f} ({r['pct_bruta']:.2f}%)"],
        ["Costos Indirectos (42%):", f"${r['costos_ind']:,.2f}"],
        ["Utilidad Neta:", f"${r['utilidad_neta']:,.2f} ({r['pct_neta']:.2f}%)"],
    ]
    
    table_resumen = Table(resumen_data, colWidths=[2.0 * inch, 4.5 * inch])
    table_resumen.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f0f0")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (0, -1), "RIGHT"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e8f5e9") if r['utilidad_neta'] >= 0 else colors.HexColor("#ffebee")),
    ]))
    story.append(table_resumen)
    story.append(Spacer(1, 12))

    # Desglose de Costos
    story.append(Paragraph("Desglose de Costos", subtitle_style))
    
    costos_data = [
        ["Sueldo Base:", f"${r['sueldo_base']:,.2f}"],
        ["Bono por Millas:", f"${r['bono_millas']:,.2f}"],
        ["Sueldo Total Operador:", f"${r['sueldo_usa']:,.2f}"],
        ["Diesel USA:", f"${r['diesel_usa']:,.2f}"],
        ["Costo Cruce:", f"${r['costo_cruce']:,.2f}"],
        ["Costo Tramo MX:", f"${r['costo_mx_usd']:,.2f}"],
        ["Otros Cargos (Pagados):", f"${r['otros_cargos_costo']:,.2f}"],
        ["ISR/IMSS:", f"${r['isr_imss']:,.2f}"],
    ]
    
    table_costos = Table(costos_data, colWidths=[2.0 * inch, 4.5 * inch])
    table_costos.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f0f0")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (0, -1), "RIGHT"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(table_costos)

    if simulando and params_sim:
        story.append(Spacer(1, 12))
        story.append(Paragraph(
            f"<i>Simulado con: MPG={params_sim['mpg']:.1f}, Diesel=${params_sim['diesel']:.2f}/gal, CXM=${params_sim['cxm']:.2f}/mi</i>",
            ParagraphStyle("SimFooter", parent=normal, fontSize=8, textColor=colors.grey),
        ))

    doc.build(story)
    return tmp.name


# ─────────────────────────────────────────────
# RENDER
# ─────────────────────────────────────────────
def render():
    st.title("🔍 Consulta Individual de Ruta (Lincoln)")

    supabase = get_supabase_client()
    if supabase is None:
        alert("warn", "⚠️ Supabase no configurado.")
        return

    c_reload, _ = st.columns([1, 4])
    with c_reload:
        if st.button("🔄 Recargar rutas", key="lincoln_consulta_reload"):
            _load_rutas_lincoln_cached.clear()
            st.rerun()

    df = _load_rutas_lincoln_cached(TABLE_RUTAS)
    if df.empty:
        alert("info", "No hay rutas guardadas aún.")
        return

    valores = cargar_datos_generales()

    # Filtros y selección
    section_header("📋", "Seleccionar Ruta")
    
    df_filtrado = _filtrar_rutas(df, "consulta")
    
    if df_filtrado.empty:
        alert("warn", "No hay rutas con los filtros aplicados.")
        return

    st.caption(f"Rutas disponibles: {len(df_filtrado)}")

    ruta_seleccionada = st.selectbox(
        "Selecciona una ruta:",
        df_filtrado.index.tolist(),
        format_func=lambda i: _format_ruta_label(df_filtrado.loc[i]),
        key="lincoln_consulta_select"
    )

    ruta = df_filtrado.loc[ruta_seleccionada]

    # Simulador de parámetros
    divider()
    section_header("⚙️", "Simulador de Parámetros")
    
    st.session_state.setdefault("lincoln_consulta_simular", False)
    
    col_sim1, col_sim2, col_sim3 = st.columns(3)
    
    with col_sim1:
        mpg_sim = st.number_input(
            "Truck Performance (mpg)",
            value=float(valores.get("Truck Performance (mpg)", 7.0)),
            step=0.1,
            key="lincoln_sim_mpg"
        )
    
    with col_sim2:
        diesel_sim = st.number_input(
            "Diesel Price ($/gal)",
            value=float(valores.get("Diesel Price ($/gal)", 3.60)),
            step=0.01,
            key="lincoln_sim_diesel"
        )
    
    with col_sim3:
        cxm_sim = st.number_input(
            "CXM Operador ($/mi)",
            value=float(valores.get("CXM Operador USA", 0.48)),
            step=0.01,
            key="lincoln_sim_cxm"
        )

    col_btn1, col_btn2 = st.columns(2)
    
    with col_btn1:
        if st.button("🔁 Simular con estos parámetros", key="lincoln_sim_apply", type="primary"):
            st.session_state.lincoln_consulta_simular = True
    
    with col_btn2:
        if st.button("↩️ Volver a valores reales", key="lincoln_sim_reset"):
            st.session_state.lincoln_consulta_simular = False

    # Cálculo
    if st.session_state.lincoln_consulta_simular:
        alert("info", "🔧 Mostrando simulación con parámetros ajustados")
        val_sim = dict(valores)
        val_sim["Truck Performance (mpg)"] = mpg_sim
        val_sim["Diesel Price ($/gal)"] = diesel_sim
        val_sim["CXM Operador USA"] = cxm_sim
        val_sim["CXM Team USA"] = cxm_sim
        valores_calc = val_sim
        simulando = True
        params_sim = {"mpg": mpg_sim, "diesel": diesel_sim, "cxm": cxm_sim}
    else:
        valores_calc = valores
        simulando = False
        params_sim = None

    r = calcular_ruta_lincoln_consulta(ruta, valores_calc)

    # Mostrar resultados
    _mostrar_resultados_utilidad(r)

    # Detalles de la ruta
    divider()
    section_header("📋", "Detalle de la Ruta")
    
    tab1, tab2, tab3 = st.tabs(["🇺🇸 Ruta Americana", "🛃 Cruce", "🇲🇽 Ruta Mexicana"])
    
    with tab1:
        col_a, col_b = st.columns(2)
        with col_a:
            st.write("**📈 Ingresos**")
            st.write(f"• Flete: ${r['ingreso_flete_usa']:,.2f}")
            st.write(f"• Fuel: ${r['ingreso_fuel_usa']:,.2f}")
            st.write(f"• Otros Cargos: ${r['otros_cargos_ingreso']:,.2f}")
            st.write(f"**Total: ${r['ingreso_flete_usa'] + r['ingreso_fuel_usa'] + r['otros_cargos_ingreso']:,.2f}**")
        with col_b:
            st.write("**📉 Costos**")
            st.write(f"• Sueldo Base: ${r['sueldo_base']:,.2f}")
            st.write(f"• Bono: ${r['bono_millas']:,.2f}")
            st.write(f"• Diesel: ${r['diesel_usa']:,.2f}")
            st.write(f"• Otros (Pagados): ${r['otros_cargos_costo']:,.2f}")
            st.write(f"• ISR/IMSS: ${r['isr_imss']:,.2f}")
            total_usa = r['sueldo_usa'] + r['diesel_usa'] + r['otros_cargos_costo'] + r['isr_imss']
            st.write(f"**Total: ${total_usa:,.2f}**")
    
    with tab2:
        col_c, col_d = st.columns(2)
        with col_c:
            st.write(f"**Ingreso:** ${r['ingreso_cruce']:,.2f}")
            st.write(f"**Tipo:** {ruta.get('Tipo_Cruce', '')}")
            st.write(f"**Carga:** {ruta.get('Tipo_Carga_Cruce', '')}")
        with col_d:
            st.write(f"**Costo:** ${r['costo_cruce']:,.2f}")
    
    with tab3:
        col_e, col_f = st.columns(2)
        with col_e:
            st.write(f"**Ingreso:** ${r['ingreso_mx_usd']:,.2f}")
            st.write(f"**Línea:** {ruta.get('Linea_MX', '')}")
            st.write(f"**Origen:** {ruta.get('Origen_MX', '')}")
            st.write(f"**Destino:** {ruta.get('Destino_MX', '')}")
        with col_f:
            st.write(f"**Costo:** ${r['costo_mx_usd']:,.2f}")

    # Generar PDF
    divider()
    section_header("📥", "Descargar Reporte PDF")
    
    if st.button("📄 Generar PDF Profesional", key="lincoln_gen_pdf", type="primary"):
        pdf_path = generar_pdf_lincoln(ruta, r, simulando, params_sim)
        
        fname = f"Lincoln_{ruta.get('ID_Ruta', '')}_{ruta.get('Cliente', '')}_{ruta.get('Fecha', '')}.pdf".replace(" ", "_").replace("/", "-")
        
        with open(pdf_path, "rb") as f:
            st.download_button(
                "📥 Descargar PDF",
                data=f,
                file_name=fname,
                mime="application/pdf",
                type="primary"
            )


if __name__ == "__main__":
    render()
