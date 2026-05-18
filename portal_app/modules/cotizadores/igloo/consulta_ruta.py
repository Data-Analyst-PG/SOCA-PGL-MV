from ui.components import section_header, alert, divider
import os
import tempfile

import pandas as pd
import streamlit as st

from services.supabase_client import get_supabase_client

from .helpers import (
    TIPOS_RUTA,
    cargar_datos_generales,
    safe_number, safe_float,
    calcular_utilidades,
    calcular_costos_indirectos,
    mostrar_resultados_utilidad,
)


# ─────────────────────────────────────────────
# Cache de rutas
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=120)
def _load_rutas_igloo_cached(table_name: str):
    supabase = get_supabase_client()
    if supabase is None:
        return pd.DataFrame()
    try:
        resp = supabase.table(table_name).select("*").execute()
        return pd.DataFrame(resp.data)
    except Exception as e:
        st.error(f"Error consultando Supabase: {e}")
        return pd.DataFrame()


def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


# ─────────────────────────────────────────────
# FUNCIÓN NUEVA: Filtrar rutas igual que en editar/eliminar
# ─────────────────────────────────────────────
def _filtrar_rutas(df, prefix_key):
    """
    Muestra filtros opcionales y devuelve el DataFrame filtrado.
    Igual que en gestion_rutas.py
    """
    with st.expander("🔎 Filtros de búsqueda (opcional)", expanded=False):
        fc1, fc2, fc3, fc4, fc5 = st.columns(5)  # ← 5 columnas
    
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
    
        with fc5:  # ← Nueva columna
            filtro_id = st.text_input(
                "ID Ruta",
                key=f"{prefix_key}_fid",
                placeholder="IG000123"
            )

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
    """Formatea una ruta para que sea fácil de identificar en selectores."""
    fecha = str(row.get("Fecha", ""))[:10]
    return (
        f"{row.get('ID_Ruta', '')} | {fecha} | "
        f"{row.get('Tipo', '')} | {row.get('Cliente', '')} | "
        f"{row.get('Origen', '')} → {row.get('Destino', '')}"
    )


# ─────────────────────────────────────────────
# PDF MEJORADO: Resumen primero, luego detalles
# ─────────────────────────────────────────────
def generar_pdf_profesional(ruta, ingreso_total, costo_total,
                             utilidad_bruta, costos_indirectos,
                             utilidad_neta, pct_bruta, pct_neta,
                             simulando=False, rend_sim=None, diesel_sim=None):
    """
    Genera un PDF profesional con reportlab.
    
    MEJORAS:
    1. Utilidad en USD cuando el flete es en USD
    2. Horas Termo y Costo Diesel en Datos Generales
    3. Diesel sin precio repetido en Costos Operativos
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable,
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    doc = SimpleDocTemplate(
        tmp.name, pagesize=letter,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
    )

    styles = getSampleStyleSheet()

    # Estilos personalizados
    title_style = ParagraphStyle(
        "CustomTitle", parent=styles["Title"],
        fontSize=16, textColor=colors.HexColor("#1B2266"),
        spaceAfter=6,
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
    small_right = ParagraphStyle(
        "SmallRight", parent=styles["Normal"],
        fontSize=8, alignment=TA_RIGHT, textColor=colors.grey,
    )
                                 
    compact_cell = ParagraphStyle(
        "CompactCell",
        parent=styles["Normal"],
        fontSize=7,
        leading=8,
        spaceBefore=0,
        spaceAfter=0,
    )

    story = []

    # ── Encabezado ──
    logo_path = os.path.join(_project_root(), "img", "Igloo White.png")
    if not os.path.exists(logo_path):
        logo_path = os.path.join(_project_root(), "img", "Igloo Original.png")

    header_data = [[
        Paragraph("<b>IGLOO TRANSPORT S DE RL DE CV</b>", ParagraphStyle(
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
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 12))

    if simulando:
        sim_note = Paragraph(
            "<i>* Este reporte fue generado con valores de simulaci&oacute;n</i>",
            ParagraphStyle("SimNote", parent=normal, textColor=colors.HexColor("#e67e22")),
        )
        story.append(sim_note)
        story.append(Spacer(1, 6))

    # ── Datos Generales de la Ruta ──
    story.append(Paragraph("Datos Generales de la Ruta", subtitle_style))

    tipo_ruta = str(ruta.get("Tipo", ""))
    
    cliente_texto = Paragraph(str(ruta.get("Cliente", "")), compact_cell)
    origen_texto = Paragraph(str(ruta.get("Origen", "")), compact_cell)
    destino_texto = Paragraph(str(ruta.get("Destino", "")), compact_cell)
    
    info_data = [
        ["ID de Ruta", str(ruta.get("ID_Ruta", "")),
         "Fecha", str(ruta.get("Fecha", ""))],
        ["Tipo", tipo_ruta,
         "Modo de Viaje", str(ruta.get("Modo de Viaje", "Operador"))],
        ["Cliente", cliente_texto,
         "KM", f"{safe_number(ruta.get('KM', 0)):,.2f}"],
        ["Origen", origen_texto,
         "Destino", destino_texto],
        # ✅ MEJORA 2: Agregar Costo Diesel/L y Horas Termo
        ["Costo Diesel/L", f"${safe_number(ruta.get('Costo Diesel', 0)):,.2f}",
         "Horas Termo", f"{safe_number(ruta.get('Horas_Termo', 0)):,.2f} hrs"],
    ]

    if tipo_ruta == "DOM MEX":
        modo_pago = str(ruta.get("Modo_Pago_Dom", "km"))
        label_pago = "Por kilómetro" if modo_pago == "km" else "Pago fijo"
        info_data.append(["Modo Pago DOM MEX", label_pago, "", ""])

    info_table = Table(info_data, colWidths=[1.4 * inch, 2.1 * inch, 1.4 * inch, 2.1 * inch])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f2f6")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f0f2f6")),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 10))

    # ══════════════════════════════════════════
    # Resumen de Utilidades (MXP)
    # ══════════════════════════════════════════
    story.append(Paragraph("Resumen de Utilidades (MXP)", subtitle_style))
    
    color_utilidad = colors.HexColor("#28a745") if utilidad_neta >= 0 else colors.HexColor("#dc3545")
    
    # Calcular porcentajes sobre ingreso total
    pct_costo = (costo_total / ingreso_total * 100) if ingreso_total > 0 else 0
    pct_indirectos = (costos_indirectos / ingreso_total * 100) if ingreso_total > 0 else 0
    
    resumen_data = [
        ["Concepto", "Valor", "%"],
        ["Ingreso Total", f"${ingreso_total:,.2f} MXP", "100.00%"],
        ["Costo Directo", f"${costo_total:,.2f} MXP", f"{pct_costo:.2f}%"],
        ["Utilidad Bruta", f"${utilidad_bruta:,.2f} MXP", f"{pct_bruta:.2f}%"],
        ["Costos Indirectos", f"${costos_indirectos:,.2f} MXP", f"{pct_indirectos:.2f}%"],
        ["Utilidad Neta", f"${utilidad_neta:,.2f} MXP", f"{pct_neta:.2f}%"],
    ]
    
    resumen_table = Table(resumen_data, colWidths=[2.5 * inch, 2.5 * inch, 2 * inch])
    resumen_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1B2266")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("BACKGROUND", (0, 5), (-1, 5), color_utilidad),
        ("TEXTCOLOR", (0, 5), (-1, 5), colors.white),
        ("FONTNAME", (0, 5), (-1, 5), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(resumen_table)
    story.append(Spacer(1, 8))

    # ══════════════════════════════════════════
    # ✅ MEJORA 1: Utilidad en USD (si aplica)
    # ══════════════════════════════════════════
    moneda_flete = str(ruta.get("Moneda", "MXP")).strip().upper()
    if moneda_flete == "USD":
        tipo_cambio_flete = safe_number(ruta.get("Tipo de cambio", 0))
        
        # Si no tiene TC guardado, usar el actual
        if tipo_cambio_flete == 0:
            valores_gen = cargar_datos_generales()
            tipo_cambio_flete = safe_number(valores_gen.get("Tipo de cambio USD", 19.5))
        
        if tipo_cambio_flete > 0:
            utilidad_neta_usd = utilidad_neta / tipo_cambio_flete
            
            nota_usd = Paragraph(
                "<i>* Utilidad convertida a USD usando el tipo de cambio de esta ruta</i>",
                ParagraphStyle("NotaUSD", parent=normal, textColor=colors.HexColor("#6c757d"), fontSize=8)
            )
            story.append(nota_usd)
            story.append(Spacer(1, 4))
            
            usd_data = [
                ["Utilidad Neta (USD)", f"${utilidad_neta_usd:,.2f} USD"],
                ["Tipo de Cambio", f"${tipo_cambio_flete:,.2f} MXP"],
            ]
            
            usd_table = Table(usd_data, colWidths=[3.5 * inch, 3.5 * inch])
            usd_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8f4f8")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#0d6efd")),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]))
            story.append(usd_table)
            story.append(Spacer(1, 8))

    story.append(Spacer(1, 6))

    # ── Ingresos ──
    story.append(Paragraph("Ingresos", subtitle_style))

    ingresos_data = [
        ["Concepto", "Moneda", "Original", "Tipo Cambio", "Convertido (MXP)"],
        [
            "Flete",
            str(ruta.get("Moneda", "")),
            f"${safe_number(ruta.get('Ingreso_Original', 0)):,.2f}",
            f"{safe_number(ruta.get('Tipo de cambio', 0)):,.2f}",
            f"${safe_number(ruta.get('Ingreso Flete', 0)):,.2f}",
        ],
        [
            "Cruce",
            str(ruta.get("Moneda_Cruce", "")),
            f"${safe_number(ruta.get('Cruce_Original', 0)):,.2f}",
            f"{safe_number(ruta.get('Tipo cambio Cruce', 0)):,.2f}",
            f"${safe_number(ruta.get('Ingreso Cruce', 0)):,.2f}",
        ],
    ]
    ing_table = Table(ingresos_data, colWidths=[1.2 * inch, 0.8 * inch, 1.4 * inch, 1.2 * inch, 1.6 * inch])
    ing_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1B2266")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    story.append(ing_table)
    story.append(Spacer(1, 8))

    # ── Costos Operativos ──
    story.append(Paragraph("Costos Operativos", subtitle_style))

    # ✅ MEJORA 3: Diesel SIN precio repetido
    costos_op_data = [
        ["Concepto", "Monto"],
        ["Diesel Camión ({:.2f} Km/L)".format(safe_number(ruta.get('Rendimiento Camion', 0))), f"${safe_number(ruta.get('Costo_Diesel_Camion', 0)):,.2f}"],
        ["Diesel Termo ({:.2f} Hrs*L)".format(safe_number(ruta.get('Rendimiento Termo', 0))), f"${safe_number(ruta.get('Costo_Diesel_Termo', 0)):,.2f}"],
        ["Sueldo Operador", f"${safe_number(ruta.get('Sueldo_Operador', 0)):,.2f}"],
        ["Bono ISR/IMSS", f"${safe_number(ruta.get('Bono', 0)):,.2f}"],
        ["Casetas", f"${safe_number(ruta.get('Casetas', 0)):,.2f}"],
        ["Costo Cruce", f"${safe_number(ruta.get('Costo Cruce Convertido', 0)):,.2f}"],
    ]
    costos_table = Table(costos_op_data, colWidths=[3.5 * inch, 3.5 * inch])
    costos_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1B2266")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    story.append(costos_table)
    story.append(Spacer(1, 8))

    # ── Otros Costos ──
    story.append(Paragraph("Otros Costos", subtitle_style))

    otros_items = [
        ("Puntualidad", safe_number(ruta.get("Puntualidad", 0))),
        ("Fianza Termo", safe_number(ruta.get("Fianza_Termo", 0))),
        ("Lavado Termo", safe_number(ruta.get("Lavado_Termo", 0))),
        ("Movimiento Local", safe_number(ruta.get("Movimiento_Local", 0))),
        ("Pensión", safe_number(ruta.get("Pension", 0))),
        ("Estancia", safe_number(ruta.get("Estancia", 0))),
        ("Renta Termo", safe_number(ruta.get("Renta_Termo", 0))),
        ("Pistas Extra", safe_number(ruta.get("Pistas_Extra", 0))),
        ("Stop", safe_number(ruta.get("Stop", 0))),
        ("Falso", safe_number(ruta.get("Falso", 0))),
        ("Gatas", safe_number(ruta.get("Gatas", 0))),
        ("Accesorios", safe_number(ruta.get("Accesorios", 0))),
        ("Guías", safe_number(ruta.get("Guias", 0))),
    ]

    otros_data = [["Concepto", "Monto"]]
    total_otros = 0.0
    for concepto, monto in otros_items:
        if monto > 0:
            otros_data.append([concepto, f"${monto:,.2f}"])
            total_otros += monto

    if len(otros_data) == 1:
        otros_data.append(["(Sin costos extras en esta ruta)", ""])

    otros_table = Table(otros_data, colWidths=[3.5 * inch, 3.5 * inch])
    otros_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1B2266")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    story.append(otros_table)
    story.append(Spacer(1, 12))

    # ── Footer con fecha/hora de generación y usuario ──
    from datetime import datetime
    
    fecha_generacion = datetime.now().strftime("%d/%m/%Y %H:%M")
    
    # Obtener usuario de session_state si existe
    usuario_nombre = "Usuario"
    if hasattr(st, "session_state") and "usuario" in st.session_state:
        usuario_data = st.session_state.get("usuario", {})
        usuario_nombre = usuario_data.get("Nombre", "Usuario")
    
    footer_text = f"Reporte generado el {fecha_generacion} por {usuario_nombre} — Igloo Transport"
    footer_style = ParagraphStyle(
        "Footer",
        parent=styles["Normal"],
        fontSize=7,
        textColor=colors.HexColor("#6c757d"),
        alignment=TA_CENTER,
    )
    story.append(Spacer(1, 20))
    story.append(Paragraph(footer_text, footer_style))

    # ── Build PDF ──
    doc.build(story)
    return tmp.name


# ─────────────────────────────────────────────
# Render principal
# ─────────────────────────────────────────────
def render():
    st.title("🔍 Consulta Individual de Ruta (Igloo)")

    supabase = get_supabase_client()
    if supabase is None:
        alert("warn", "⚠️ Supabase no configurado.")
        return

    TABLE_RUTAS = "Rutas"
    valores = cargar_datos_generales()

    c1, c2 = st.columns([1, 3])
    with c1:
        if st.button("🔄 Recargar rutas", key="igloo_cons_reload"):
            _load_rutas_igloo_cached.clear()
            st.rerun()
    with c2:
        st.caption("Carga cacheada 2 min para que sea rápido.")

    df = _load_rutas_igloo_cached(TABLE_RUTAS)
    if df.empty:
        alert("warn", "⚠️ No hay rutas guardadas todavía.")
        return

    if "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.date

    if "ID_Ruta" in df.columns:
        df.set_index("ID_Ruta", inplace=True, drop=False)

    # ═══════════════════════════════════════════
    # NUEVO: Filtros mejorados + Selección de ruta
    # ═══════════════════════════════════════════
    st.markdown("### 🔎 Buscar Ruta")
    
    df_filtrado = _filtrar_rutas(df, "igloo_cons")
    
    if df_filtrado.empty:
        alert("info", "No hay rutas que coincidan con los filtros.")
        return
    
    # Seleccionar ruta del dataframe filtrado
    opciones = df_filtrado.index.tolist()
    index_sel = st.selectbox(
        "Selecciona la ruta a consultar",
        opciones,
        format_func=lambda i: _format_ruta_label(df_filtrado.loc[i]),
        key="igloo_cons_select",
    )
    
    ruta = df_filtrado.loc[index_sel]

    # ── Rendimiento registrado ──
    rend_reg = float(safe_number(
        ruta.get("Rendimiento_Camion", ruta.get("Rendimiento Camion", valores.get("Rendimiento Camion", 2.5)))
    ))

    # ── Ajustes simulación ──
    divider()
section_header("⚙️", "Ajustes para Simulación")
    costo_diesel_input = st.number_input("Costo del Diesel ($/L)", value=float(valores.get("Costo Diesel", 24.0)), key="igloo_cons_diesel")
    st.markdown(f"> Rendimiento Camión **registrado**: **{rend_reg:.2f} km/L** (solo consulta)")
    rendimiento_input = st.number_input(
        "Rendimiento Camión para Simulación (km/L)",
        value=float(valores.get("Rendimiento Camion", rend_reg)),
        key="igloo_cons_rend_sim",
    )
    if st.button("🔁 Simular", key="igloo_cons_sim"):
        st.session_state["igloo_simular"] = True

    # ── Obtener tipo para cálculo correcto de indirectos ──
    tipo_ruta = str(ruta.get("Tipo", "")).strip().upper()

    # ── Resultados ──
    if st.session_state.get("igloo_simular", False):
        ingreso_total = safe_number(ruta["Ingreso Total"])
        km = safe_number(ruta.get("KM", 0))
        horas_termo = safe_number(ruta.get("Horas_Termo", 0))
        rend_termo = float(valores.get("Rendimiento Termo", 3.0))

        costo_diesel_camion = (km / rendimiento_input) * costo_diesel_input if rendimiento_input else 0
        costo_diesel_termo = horas_termo * rend_termo * costo_diesel_input

        costo_total = (
            costo_diesel_camion + costo_diesel_termo +
            safe_number(ruta.get("Sueldo_Operador", 0)) +
            safe_number(ruta.get("Bono", 0)) +
            safe_number(ruta.get("Casetas", 0)) +
            safe_number(ruta.get("Costo Cruce Convertido", 0)) +
            safe_number(ruta.get("Costo_Extras", 0))
        )

        util = calcular_utilidades(ingreso_total, costo_total, tipo_ruta)
        utilidad_bruta = util["utilidad_bruta"]
        costos_indirectos = util["costos_indirectos"]
        utilidad_neta = util["utilidad_neta"]
        porcentaje_bruta = util["porcentaje_bruta"]
        porcentaje_neta = util["porcentaje_neta"]

        alert("success", "🔧 Estás viendo una simulación. Los valores se ajustaron con los parámetros ingresados.")
        mostrar_resultados_utilidad(
            st, ingreso_total, costo_total,
            utilidad_bruta, costos_indirectos, utilidad_neta,
            porcentaje_bruta, porcentaje_neta, tipo=tipo_ruta,
        )

        if st.button("🔄 Volver a valores reales", key="igloo_cons_back_real"):
            st.session_state["igloo_simular"] = False
            st.rerun()
    else:
        ingreso_total = safe_number(ruta["Ingreso Total"])
        costo_total = safe_number(ruta.get("Costo_Total_Ruta", 0))

        util = calcular_utilidades(ingreso_total, costo_total, tipo_ruta)
        utilidad_bruta = util["utilidad_bruta"]
        costos_indirectos = util["costos_indirectos"]
        utilidad_neta = util["utilidad_neta"]
        porcentaje_bruta = util["porcentaje_bruta"]
        porcentaje_neta = util["porcentaje_neta"]

        mostrar_resultados_utilidad(
            st, ingreso_total, costo_total,
            utilidad_bruta, costos_indirectos, utilidad_neta,
            porcentaje_bruta, porcentaje_neta, tipo=tipo_ruta,
        )

    # ✅ MEJORA 1: Mostrar utilidad en USD en la UI (si aplica)
    moneda_flete = str(ruta.get("Moneda", "MXP")).strip().upper()
    if moneda_flete == "USD":
        tipo_cambio = safe_number(ruta.get("Tipo de cambio", 0))
        
        # Si no tiene TC guardado, usar el actual con advertencia
        if tipo_cambio == 0:
            tipo_cambio = safe_number(valores.get("Tipo de cambio USD", 19.5))
            st.warning(f"⚠️ Esta ruta no tiene tipo de cambio guardado. Se usa el actual: ${tipo_cambio:,.2f}")
        
        if tipo_cambio > 0:
            utilidad_neta_usd = utilidad_neta / tipo_cambio
            
            divider()
            st.info(f"""
            **💵 Utilidad en Dólares**
            
            Utilidad Neta: **${utilidad_neta_usd:,.2f} USD**  
            _(Convertida con TC: ${tipo_cambio:,.2f} MXP)_
            """)

    # ── Detalles y costos ──
    divider()
section_header("📋", "Detalles y Costos de la Ruta")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.write(f"**Fecha:** {ruta.get('Fecha', '')}")
        st.write(f"**ID de Ruta:** {ruta.get('ID_Ruta', '')}")
        st.write(f"**Tipo:** {ruta.get('Tipo', '')}")
        st.write(f"**Modo:** {ruta.get('Modo de Viaje', 'Operador')}")
        st.write(f"**Cliente:** {ruta.get('Cliente', '')}")
        st.write(f"**Origen → Destino:** {ruta.get('Origen', '')} → {ruta.get('Destino', '')}")
        st.write(f"**KM:** {safe_number(ruta.get('KM', 0)):,.2f}")
        st.write(f"**Horas Termo:** {safe_number(ruta.get('Horas_Termo', 0)):,.2f} hrs")
        st.write(f"**Rendimiento Camión (registrado):** {rend_reg:.2f} km/L")
        st.write(f"**Precio Diesel:** ${safe_number(ruta.get('Costo Diesel', 0)):,.2f} L")
        if tipo_ruta == "DOM MEX":
            modo_p = ruta.get("Modo_Pago_Dom", "km")
            st.write(f"**Modo Pago DOM MEX:** {'Por km' if modo_p == 'km' else 'Fijo'}")

    with col2:
        st.write(f"**Moneda Flete:** {ruta.get('Moneda', '')}")
        st.write(f"**Ingreso Flete Original:** ${safe_number(ruta.get('Ingreso_Original', 0)):,.2f}")
        st.write(f"**Tipo de cambio:** {safe_number(ruta.get('Tipo de cambio', 0)):,.2f}")
        st.write(f"**Ingreso Flete Convertido:** ${safe_number(ruta.get('Ingreso Flete', 0)):,.2f}")
        st.write(f"**Moneda Cruce:** {ruta.get('Moneda_Cruce', '')}")
        st.write(f"**Ingreso Cruce Original:** ${safe_number(ruta.get('Cruce_Original', 0)):,.2f}")
        st.write(f"**Ingreso Cruce Convertido:** ${safe_number(ruta.get('Ingreso Cruce', 0)):,.2f}")
        st.write(f"**Costo Cruce Convertido:** ${safe_number(ruta.get('Costo Cruce Convertido', 0)):,.2f}")
        st.write(f"**Diesel Camión:** ${safe_number(ruta.get('Costo_Diesel_Camion', 0)):,.2f}")
        st.write(f"**Diesel Termo:** ${safe_number(ruta.get('Costo_Diesel_Termo', 0)):,.2f}")
        st.write(f"**Sueldo Operador:** ${safe_number(ruta.get('Sueldo_Operador', 0)):,.2f}")
        st.write(f"**Bono:** ${safe_number(ruta.get('Bono', 0)):,.2f}")
        st.write(f"**Casetas:** ${safe_number(ruta.get('Casetas', 0)):,.2f}")

    with col3:
        st.write("**Otros Costos:**")
        extras_items = [
            ("Lavado Termo", "Lavado_Termo"), ("Movimiento Local", "Movimiento_Local"),
            ("Puntualidad", "Puntualidad"), ("Pensión", "Pension"),
            ("Estancia", "Estancia"), ("Fianza Termo", "Fianza_Termo"),
            ("Renta Termo", "Renta_Termo"), ("Pistas Extra", "Pistas_Extra"),
            ("Stop", "Stop"), ("Falso", "Falso"),
            ("Gatas", "Gatas"), ("Accesorios", "Accesorios"),
            ("Guías", "Guias"),
        ]
        for label, key in extras_items:
            st.write(f"- {label}: ${safe_number(ruta.get(key, 0)):,.2f}")

    # ── PDF Profesional ──
    divider()
section_header("📥", "Descargar PDF de la Consulta")

    simulando = st.session_state.get("igloo_simular", False)

    try:
        pdf_path = generar_pdf_profesional(
            ruta, ingreso_total, costo_total,
            utilidad_bruta, costos_indirectos, utilidad_neta,
            porcentaje_bruta, porcentaje_neta,
            simulando=simulando,
            rend_sim=rendimiento_input if simulando else None,
            diesel_sim=costo_diesel_input if simulando else None,
        )
        file_name = f"Consulta_{ruta.get('Cliente', 'Cliente')}_{ruta.get('Origen', '')}_{ruta.get('Destino', '')}.pdf".replace("/", "-")
        with open(pdf_path, "rb") as f:
            st.download_button(
                label="📄 Descargar PDF Profesional",
                data=f,
                file_name=file_name,
                mime="application/pdf",
            )
    except Exception as e:
        st.error(f"Error generando PDF: {e}")
        st.caption("Asegúrate de tener instalado `reportlab` (pip install reportlab).")
