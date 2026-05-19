from ui.components import section_header, alert, divider
"""
simulador.py – Lincoln Freight (USA/MX)
Simulador de tráfico: combina ruta de ida con mejor opción de regreso
según tipo de ruta y utilidad proyectada
"""

import tempfile
from datetime import datetime

import pandas as pd
import streamlit as st

from services.supabase_client import get_supabase_client
from ._shared import TABLE_RUTAS, cargar_datos_generales, safe


# ─────────────────────────────────────────────
# CACHE
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=120)
def _load_rutas_lincoln_cached(table_name: str):
    supabase = get_supabase_client()
    if supabase is None:
        return pd.DataFrame()
    try:
        resp = supabase.table(table_name).select("*").execute()
        return pd.DataFrame(resp.data)
    except Exception:
        return pd.DataFrame()


# ─────────────────────────────────────────────
# LÓGICA DE EMPAREJAMIENTO
# ─────────────────────────────────────────────
def obtener_tipos_compatibles(tipo_ruta: str) -> list:
    """
    Retorna los tipos de ruta compatibles para el regreso
    
    NB / D2DNB → DOM USA, SB, D2DSB
    SB / D2DSB → NB, D2DNB
    """
    compatibilidad = {
        "NB": ["DOM USA", "SB", "D2DSB"],
        "D2DNB": ["DOM USA", "SB", "D2DSB"],
        "SB": ["NB", "D2DNB"],
        "D2DSB": ["NB", "D2DNB"],
        "DOM USA": [],  # No necesita regreso
        "DOM MEX": [],  # No necesita regreso
    }
    return compatibilidad.get(tipo_ruta, [])


# ─────────────────────────────────────────────
# CÁLCULO DE UTILIDAD COMBINADA
# ─────────────────────────────────────────────
def calcular_utilidad_combinada(ruta_ida, ruta_regreso, valores):
    """
    Calcula utilidad combinada de ida + regreso
    Considera parámetros simulados si aplica
    """
    # Obtener utilidades de cada ruta
    util_ida = safe(ruta_ida.get("Utilidad_Neta", 0))
    util_regreso = safe(ruta_regreso.get("Utilidad_Neta", 0))
    
    # Si hay parámetros de simulación, recalcular
    mpg = float(valores.get("Truck Performance (mpg)", 7.0))
    diesel_precio = float(valores.get("Diesel Price ($/gal)", 3.60))
    
    # Recalcular diesel con parámetros actuales
    millas_totales_ida = safe(ruta_ida.get("Millas_USA", 0)) + safe(ruta_ida.get("Millas_Vacias", 0))
    diesel_ida_nuevo = (millas_totales_ida / mpg) * diesel_precio if mpg > 0 else 0
    diesel_ida_original = safe(ruta_ida.get("Diesel_USA", 0))
    ajuste_ida = diesel_ida_nuevo - diesel_ida_original
    
    millas_totales_regreso = safe(ruta_regreso.get("Millas_USA", 0)) + safe(ruta_regreso.get("Millas_Vacias", 0))
    diesel_regreso_nuevo = (millas_totales_regreso / mpg) * diesel_precio if mpg > 0 else 0
    diesel_regreso_original = safe(ruta_regreso.get("Diesel_USA", 0))
    ajuste_regreso = diesel_regreso_nuevo - diesel_regreso_original
    
    # Ajustar utilidades
    util_ida_ajustada = util_ida - ajuste_ida
    util_regreso_ajustada = util_regreso - ajuste_regreso
    
    utilidad_total = util_ida_ajustada + util_regreso_ajustada
    
    ingreso_ida = safe(ruta_ida.get("Ingreso Total", 0))
    ingreso_regreso = safe(ruta_regreso.get("Ingreso Total", 0))
    ingreso_total = ingreso_ida + ingreso_regreso
    
    pct_total = (utilidad_total / ingreso_total * 100) if ingreso_total > 0 else 0.0
    
    return {
        "util_ida": util_ida_ajustada,
        "util_regreso": util_regreso_ajustada,
        "utilidad_total": utilidad_total,
        "ingreso_total": ingreso_total,
        "pct_total": pct_total,
        "millas_totales": millas_totales_ida + millas_totales_regreso,
    }


# ─────────────────────────────────────────────
# MOSTRAR CARD DE RUTA INDIVIDUAL
# ─────────────────────────────────────────────
def _mostrar_card_ruta(ruta, etiqueta: str, utilidad: float):
    """Muestra card individual con información de la ruta"""
    
    color_borde = "#059669" if utilidad >= 0 else "#dc2626"
    color_fondo = "#f0fdf4" if utilidad >= 0 else "#fef2f2"
    
    st.markdown(f"""
    <div style="
        border: 2px solid {color_borde};
        border-radius: 8px;
        padding: 1rem;
        background: {color_fondo};
        margin-bottom: 0.5rem;
    ">
        <div style="font-weight: 600; color: #374151; margin-bottom: 0.5rem;">
            {etiqueta}
        </div>
        <div style="font-size: 0.875rem; color: #6b7280;">
            <strong>ID:</strong> {ruta.get('ID_Ruta', 'N/A')}<br>
            <strong>Tipo:</strong> {ruta.get('Tipo', 'N/A')}<br>
            <strong>Cliente:</strong> {ruta.get('Cliente', 'N/A')}<br>
            <strong>Ruta:</strong> {ruta.get('Origen', 'N/A')} → {ruta.get('Destino', 'N/A')}<br>
            <strong>Millas:</strong> {safe(ruta.get('Millas_USA', 0)):,.0f}<br>
            <strong>Ingreso:</strong> ${safe(ruta.get('Ingreso Total', 0)):,.2f}<br>
            <strong style="color: {color_borde};">Utilidad Neta:</strong> 
            <span style="color: {color_borde}; font-weight: 600;">${utilidad:,.2f}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────
# GENERAR PDF DE SIMULACIÓN
# ─────────────────────────────────────────────
def generar_pdf_simulacion(ruta_ida, ruta_regreso, resultado, valores, params_sim):
    """Genera PDF profesional de la simulación"""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    doc = SimpleDocTemplate(
        tmp.name, pagesize=letter,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
    )

    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        "CustomTitle", parent=styles["Heading1"],
        fontSize=16, textColor=colors.HexColor("#1B2266"),
        alignment=TA_CENTER, spaceAfter=12,
    )
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
        Paragraph("Simulación de Tráfico Combinado", ParagraphStyle(
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

    # Fecha y parámetros
    story.append(Paragraph(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}", normal))
    if params_sim:
        story.append(Paragraph(
            f"<i>Parámetros simulados: MPG={params_sim['mpg']:.1f}, "
            f"Diesel=${params_sim['diesel']:.2f}/gal, CXM=${params_sim['cxm']:.2f}/mi</i>",
            ParagraphStyle("SimNote", parent=normal, textColor=colors.HexColor("#e67e22")),
        ))
    story.append(Spacer(1, 12))

    # Resumen Global
    story.append(Paragraph("Resumen de Tráfico Combinado", subtitle_style))
    
    resumen_data = [
        ["Utilidad Total:", f"${resultado['utilidad_total']:,.2f}"],
        ["Porcentaje Utilidad:", f"{resultado['pct_total']:.2f}%"],
        ["Ingreso Total:", f"${resultado['ingreso_total']:,.2f}"],
        ["Millas Totales:", f"{resultado['millas_totales']:,.0f}"],
    ]
    
    table_resumen = Table(resumen_data, colWidths=[2.5 * inch, 4.0 * inch])
    table_resumen.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#1B2266")),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (0, 0), (0, -1), "RIGHT"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 1, colors.grey),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(table_resumen)
    story.append(Spacer(1, 16))

    # Ruta de Ida
    story.append(Paragraph("🚛 Ruta de Ida", subtitle_style))
    
    ida_data = [
        ["ID:", str(ruta_ida.get('ID_Ruta', ''))],
        ["Tipo:", str(ruta_ida.get('Tipo', ''))],
        ["Cliente:", str(ruta_ida.get('Cliente', ''))],
        ["Origen → Destino:", f"{ruta_ida.get('Origen', '')} → {ruta_ida.get('Destino', '')}"],
        ["Millas USA:", f"{safe(ruta_ida.get('Millas_USA', 0)):,.0f}"],
        ["Ingreso Total:", f"${safe(ruta_ida.get('Ingreso Total', 0)):,.2f}"],
        ["Utilidad Neta:", f"${resultado['util_ida']:,.2f}"],
    ]
    
    table_ida = Table(ida_data, colWidths=[2.5 * inch, 4.0 * inch])
    table_ida.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f0f0")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (0, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(table_ida)
    story.append(Spacer(1, 12))

    # Ruta de Regreso
    story.append(Paragraph("🔄 Ruta de Regreso", subtitle_style))
    
    regreso_data = [
        ["ID:", str(ruta_regreso.get('ID_Ruta', ''))],
        ["Tipo:", str(ruta_regreso.get('Tipo', ''))],
        ["Cliente:", str(ruta_regreso.get('Cliente', ''))],
        ["Origen → Destino:", f"{ruta_regreso.get('Origen', '')} → {ruta_regreso.get('Destino', '')}"],
        ["Millas USA:", f"{safe(ruta_regreso.get('Millas_USA', 0)):,.0f}"],
        ["Ingreso Total:", f"${safe(ruta_regreso.get('Ingreso Total', 0)):,.2f}"],
        ["Utilidad Neta:", f"${resultado['util_regreso']:,.2f}"],
    ]
    
    table_regreso = Table(regreso_data, colWidths=[2.5 * inch, 4.0 * inch])
    table_regreso.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f0f0")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (0, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(table_regreso)

    doc.build(story)
    return tmp.name


# ─────────────────────────────────────────────
# RENDER
# ─────────────────────────────────────────────
def render():
    st.title("🔄 Simulador de Tráfico – Lincoln Freight")
    st.caption("Combina tu ruta de ida con la mejor opción de regreso según tipo y utilidad")

    supabase = get_supabase_client()
    if supabase is None:
        alert("warn", "⚠️ Supabase no configurado.")
        return

    c_reload, _ = st.columns([1, 4])
    with c_reload:
        if st.button("🔄 Recargar rutas", key="sim_reload"):
            _load_rutas_lincoln_cached.clear()
            st.rerun()

    df = _load_rutas_lincoln_cached(TABLE_RUTAS)
    if df.empty:
        alert("info", "No hay rutas guardadas para simular.")
        return

    valores = cargar_datos_generales()

    # ══════════════════════════════════════════════════════════════
    # PASO 1: SELECCIONAR RUTA DE IDA
    # ══════════════════════════════════════════════════════════════
    section_header("1️⃣", "Selecciona la Ruta de Ida")
    
    # Filtrar solo rutas que tienen regreso compatible
    tipos_validos = ["NB", "D2DNB", "SB", "D2DSB"]
    df_ida = df[df["Tipo"].isin(tipos_validos)].copy()
    
    if df_ida.empty:
        alert("warn", "No hay rutas con tipo compatible para simular tráfico.")
        return

    col_ida1, col_ida2 = st.columns(2)
    
    with col_ida1:
        tipo_ida = st.selectbox(
            "Tipo de Ruta de Ida",
            sorted(df_ida["Tipo"].unique().tolist()),
            key="sim_tipo_ida"
        )
    
    with col_ida2:
        df_ida_filtrado = df_ida[df_ida["Tipo"] == tipo_ida]
        
        ruta_ida_idx = st.selectbox(
            "Selecciona Ruta de Ida",
            df_ida_filtrado.index.tolist(),
            format_func=lambda i: f"{df_ida_filtrado.loc[i, 'ID_Ruta']} | "
                                   f"{df_ida_filtrado.loc[i, 'Cliente']} | "
                                   f"{df_ida_filtrado.loc[i, 'Origen']} → {df_ida_filtrado.loc[i, 'Destino']}",
            key="sim_ruta_ida"
        )
    
    ruta_ida = df_ida_filtrado.loc[ruta_ida_idx]
    
    # Mostrar card de ida
    _mostrar_card_ruta(ruta_ida, "🚛 Ruta de Ida Seleccionada", safe(ruta_ida.get("Utilidad_Neta", 0)))

    # ══════════════════════════════════════════════════════════════
    # PASO 2: PARÁMETROS DE SIMULACIÓN
    # ══════════════════════════════════════════════════════════════
    divider()
    section_header("2️⃣", "Ajustar Parámetros de Simulación (Opcional)")
    
    col_sim1, col_sim2, col_sim3 = st.columns(3)
    
    with col_sim1:
        mpg_sim = st.number_input(
            "Truck Performance (mpg)",
            value=float(valores.get("Truck Performance (mpg)", 7.0)),
            step=0.1,
            key="sim_mpg"
        )
    
    with col_sim2:
        diesel_sim = st.number_input(
            "Diesel Price ($/gal)",
            value=float(valores.get("Diesel Price ($/gal)", 3.60)),
            step=0.01,
            key="sim_diesel"
        )
    
    with col_sim3:
        cxm_sim = st.number_input(
            "CXM Operador ($/mi)",
            value=float(valores.get("CXM Operador USA", 0.48)),
            step=0.01,
            key="sim_cxm"
        )

    # Actualizar valores
    val_sim = dict(valores)
    val_sim["Truck Performance (mpg)"] = mpg_sim
    val_sim["Diesel Price ($/gal)"] = diesel_sim
    val_sim["CXM Operador USA"] = cxm_sim
    
    params_diferentes = (
        mpg_sim != float(valores.get("Truck Performance (mpg)", 7.0)) or
        diesel_sim != float(valores.get("Diesel Price ($/gal)", 3.60)) or
        cxm_sim != float(valores.get("CXM Operador USA", 0.48))
    )
    
    if params_diferentes:
        alert("info", "🔧 Usando parámetros simulados (diferentes a los valores guardados)")

    # ══════════════════════════════════════════════════════════════
    # PASO 3: ENCONTRAR MEJORES RUTAS DE REGRESO
    # ══════════════════════════════════════════════════════════════
    divider()
    section_header("3️⃣", "Mejores Opciones de Regreso")
    
    tipos_compatibles = obtener_tipos_compatibles(tipo_ida)
    
    if not tipos_compatibles:
        st.warning(f"El tipo de ruta '{tipo_ida}' no requiere regreso.")
        return
    
    st.caption(f"Buscando rutas tipo: {', '.join(tipos_compatibles)}")
    
    # Filtrar rutas compatibles
    df_regreso = df[df["Tipo"].isin(tipos_compatibles)].copy()
    
    if df_regreso.empty:
        alert("warn", "No hay rutas compatibles para el regreso.")
        return
    
    # Calcular utilidad combinada para cada opción
    opciones = []
    for idx in df_regreso.index:
        ruta_reg = df_regreso.loc[idx]
        resultado = calcular_utilidad_combinada(ruta_ida, ruta_reg, val_sim)
        opciones.append({
            "idx": idx,
            "ruta": ruta_reg,
            "resultado": resultado
        })
    
    # Ordenar por utilidad total (mayor a menor)
    opciones_ordenadas = sorted(opciones, key=lambda x: x["resultado"]["utilidad_total"], reverse=True)
    
    # Mostrar top 5
    st.write(f"**Se encontraron {len(opciones_ordenadas)} opciones, mostrando las mejores:**")
    
    num_mostrar = min(5, len(opciones_ordenadas))
    
    for i, opcion in enumerate(opciones_ordenadas[:num_mostrar], 1):
        ruta_reg = opcion["ruta"]
        res = opcion["resultado"]
        
        with st.expander(
            f"#{i} - {ruta_reg.get('ID_Ruta')} | "
            f"{ruta_reg.get('Tipo')} | "
            f"{ruta_reg.get('Cliente')} | "
            f"Utilidad Total: ${res['utilidad_total']:,.2f} ({res['pct_total']:.1f}%)",
            expanded=(i == 1)
        ):
            col_det1, col_det2 = st.columns(2)
            
            with col_det1:
                _mostrar_card_ruta(ruta_ida, "🚛 Ida", res["util_ida"])
            
            with col_det2:
                _mostrar_card_ruta(ruta_reg, "🔄 Regreso", res["util_regreso"])
            
            # Card global diferenciada
            color_global = "#059669" if res["utilidad_total"] >= 0 else "#dc2626"
            color_fondo_global = "#ecfdf5" if res["utilidad_total"] >= 0 else "#fef2f2"
            
            st.markdown(f"""
            <div style="
                border: 3px solid {color_global};
                border-radius: 12px;
                padding: 1.5rem;
                background: {color_fondo_global};
                margin-top: 1rem;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            ">
                <div style="text-align: center;">
                    <div style="font-size: 1.1rem; font-weight: 600; color: #374151; margin-bottom: 1rem;">
                        💼 RESUMEN TRÁFICO COMBINADO
                    </div>
                    <div style="font-size: 2rem; font-weight: 700; color: {color_global};">
                        ${res['utilidad_total']:,.2f}
                    </div>
                    <div style="font-size: 1rem; color: {color_global}; margin-top: 0.25rem;">
                        {res['pct_total']:.2f}% de utilidad
                    </div>
                    <div style="margin-top: 1rem; padding-top: 1rem; border-top: 1px solid {color_global};">
                        <div style="font-size: 0.875rem; color: #6b7280;">
                            <strong>Ingreso Total:</strong> ${res['ingreso_total']:,.2f} | 
                            <strong>Millas Totales:</strong> {res['millas_totales']:,.0f}
                        </div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # Botón para descargar PDF de esta simulación
            if st.button(f"📥 Descargar PDF de esta Simulación", key=f"pdf_{i}_{opcion['idx']}"):
                pdf_path = generar_pdf_simulacion(
                    ruta_ida, ruta_reg, res, val_sim,
                    {"mpg": mpg_sim, "diesel": diesel_sim, "cxm": cxm_sim} if params_diferentes else None
                )
                
                fname = f"Simulacion_Lincoln_{ruta_ida.get('ID_Ruta')}_{ruta_reg.get('ID_Ruta')}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
                
                with open(pdf_path, "rb") as f:
                    st.download_button(
                        "📄 Descargar PDF",
                        data=f,
                        file_name=fname,
                        mime="application/pdf",
                        key=f"dl_pdf_{i}_{opcion['idx']}"
                    )


if __name__ == "__main__":
    render()
