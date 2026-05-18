from ui.components import section_header, alert, divider
import os
import tempfile

import pandas as pd
import streamlit as st
from fpdf import FPDF
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from services.supabase_client import get_supabase_client

from .helpers import (
    TIPOS_RUTA,
    safe_number,
    calcular_costos_indirectos,
    calcular_utilidades_vuelta_redonda,
    mostrar_resultados_utilidad,
    cargar_datos_generales,
    _project_root,
)


@st.cache_data(show_spinner=False, ttl=120)
def _load_rutas_igloo_cached(table_name: str):
    supabase = get_supabase_client()
    if supabase is None:
        return pd.DataFrame()

    resp = supabase.table(table_name).select("*").execute()
    df = pd.DataFrame(resp.data)
    if df.empty:
        return df

    for col in ["Origen", "Destino", "Cliente"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.upper()

    if "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d")

    df["Ingreso Total"] = pd.to_numeric(df.get("Ingreso Total", 0), errors="coerce").fillna(0.0)
    df["Costo_Total_Ruta"] = pd.to_numeric(df.get("Costo_Total_Ruta", 0), errors="coerce").fillna(0.0)

    df["Utilidad"] = df["Ingreso Total"] - df["Costo_Total_Ruta"]
    df["% Utilidad"] = (df["Utilidad"] / df["Ingreso Total"].replace(0, pd.NA) * 100).fillna(0).round(2)

    return df


# ═════════════════════════════════════════════
# FILTROS
# ═════════════════════════════════════════════
def _filtrar_rutas(df, prefix_key):
    """Muestra filtros opcionales y devuelve el DataFrame filtrado."""
    with st.expander("🔎 Filtros de búsqueda (opcional)", expanded=False):
        fc1, fc2, fc3, fc4 = st.columns(4)
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

    resultado = df.copy()
    if filtro_tipo != "Todos":
        resultado = resultado[resultado["Tipo"] == filtro_tipo]
    if filtro_cliente != "Todos":
        resultado = resultado[resultado["Cliente"].astype(str) == filtro_cliente]
    if filtro_origen.strip():
        resultado = resultado[resultado["Origen"].astype(str).str.contains(filtro_origen.strip(), case=False, na=False)]
    if filtro_destino.strip():
        resultado = resultado[resultado["Destino"].astype(str).str.contains(filtro_destino.strip(), case=False, na=False)]
    return resultado


def _format_ruta_label(row):
    """Formatea una ruta para que sea fácil de identificar CON ID_RUTA."""
    fecha = str(row.get("Fecha", ""))[:10]
    return (
        f"{row.get('ID_Ruta', '')} | {fecha} | "
        f"{row.get('Tipo', '')} | {row.get('Cliente', '')} | "
        f"{row.get('Origen', '')} → {row.get('Destino', '')}"
    )


# ═════════════════════════════════════════════
# GENERAR PDF PROFESIONAL (igual que consulta_ruta)
# ═════════════════════════════════════════════
def generar_pdf_vuelta_redonda(rutas_seleccionadas, ingreso_total, costo_total,
                                utilidad_bruta, costos_indirectos, utilidad_neta,
                                pct_bruta, pct_neta):
    """Genera PDF profesional con diseño similar a consulta_ruta."""
    
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
    header_data = [[
        Paragraph("<b>IGLOO TRANSPORT S DE RL DE CV</b>", ParagraphStyle(
            "Header", parent=styles["Normal"], fontSize=13,
            textColor=colors.white,
        )),
        Paragraph("Simulador de Vuelta Redonda", ParagraphStyle(
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

    # ══════════════════════════════════════════
    # Resumen de Utilidades GLOBAL
    # ══════════════════════════════════════════
    story.append(Paragraph("📊 Resumen de Vuelta Redonda", subtitle_style))
    
    color_utilidad = colors.HexColor("#28a745") if utilidad_neta >= 0 else colors.HexColor("#dc3545")
    
    pct_costo = (costo_total / ingreso_total * 100) if ingreso_total > 0 else 0
    pct_indirectos = (costos_indirectos / ingreso_total * 100) if ingreso_total > 0 else 0
    
    resumen_data = [
        ["Concepto", "Monto", "%"],
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
    story.append(Spacer(1, 14))

    # ══════════════════════════════════════════
    # Detalle de cada Ruta
    # ══════════════════════════════════════════
    story.append(Paragraph("📋 Detalle de Rutas", subtitle_style))

    for i, ruta in enumerate(rutas_seleccionadas, 1):
        tipo_ruta = str(ruta.get("Tipo", ""))
        
        # Encabezado de ruta
        ruta_header = Paragraph(
            f"<b>{i}. {tipo_ruta} — {ruta.get('Cliente', 'N/A')}</b>",
            ParagraphStyle("RutaHeader", parent=normal, fontSize=10, textColor=colors.HexColor("#1B2266"))
        )
        story.append(ruta_header)
        story.append(Spacer(1, 4))
        
        cliente_texto = Paragraph(str(ruta.get("Cliente", "")), compact_cell)
        origen_texto = Paragraph(str(ruta.get("Origen", "")), compact_cell)
        destino_texto = Paragraph(str(ruta.get("Destino", "")), compact_cell)
        
        # Datos básicos
        ruta_info = [
            ["ID Ruta", str(ruta.get("ID_Ruta", "")), "Fecha", str(ruta.get("Fecha", ""))],
            ["Tipo", tipo_ruta, "KM", f"{safe_number(ruta.get('KM', 0)):,.2f}"],
            ["Cliente", cliente_texto, "Modo", str(ruta.get("Modo de Viaje", "Operador"))],
            ["Origen", origen_texto, "Destino", destino_texto],
        ]
        
        ruta_table = Table(ruta_info, colWidths=[1.2 * inch, 2.0 * inch, 1.2 * inch, 2.0 * inch])
        ruta_table.setStyle(TableStyle([
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
        story.append(ruta_table)
        story.append(Spacer(1, 6))
        
        # Ingresos y costos de esta ruta
        ing_orig = safe_number(ruta.get("Ingreso_Original", 0))
        moneda = str(ruta.get("Moneda", "MXP"))
        tc = safe_number(ruta.get("Tipo de cambio", 1.0))
        ing_total_ruta = safe_number(ruta.get("Ingreso Total", 0))
        costo_ruta = safe_number(ruta.get("Costo_Total_Ruta", 0))
        
        costos_ind_ruta = calcular_costos_indirectos(tipo_ruta, ing_total_ruta)
        
        financiera_data = [
            ["Ingreso Original", f"${ing_orig:,.2f}"],
            ["Moneda", moneda],
            ["Tipo de cambio", f"{tc:,.2f}"],
            ["Ingreso Total", f"${ing_total_ruta:,.2f} MXP"],
            ["Costo Directo Ruta", f"${costo_ruta:,.2f} MXP"],
            ["Costos Indirectos (35%)" if costos_ind_ruta > 0 else "Costos Indirectos (0% - VACÍO)", 
             f"${costos_ind_ruta:,.2f} MXP"],
        ]
        
        financiera_table = Table(financiera_data, colWidths=[2.5 * inch, 3.5 * inch])
        financiera_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8f4f8")),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ]))
        story.append(financiera_table)
        story.append(Spacer(1, 10))

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

    # Construir PDF
    doc.build(story)
    return tmp.name


def render():
    st.title("🔁 Simulador de Vuelta Redonda (Igloo)")

    supabase = get_supabase_client()
    if supabase is None:
        alert("warn", "⚠️ Supabase no configurado. No se pueden cargar rutas.")
        return

    TABLE_RUTAS = "Rutas"
    st.session_state.setdefault("igloo_simulacion_realizada", False)

    # ═══════════════════════════════════════════════
    # BOTÓN RECARGAR RUTAS
    # ═══════════════════════════════════════════════
    if st.button("🔄 Recargar rutas desde Supabase", key="reload_rutas_simulador"):
        _load_rutas_igloo_cached.clear()
        alert("success", "✅ Cache limpiado. Las rutas se recargarán.")
        st.rerun()

    # ═══════════════════════════════════════════════
    # CARGAR RUTAS
    # ═══════════════════════════════════════════════
    df = _load_rutas_igloo_cached(TABLE_RUTAS)
    if df.empty:
        alert("warn", "⚠️ No hay rutas registradas en Supabase.")
        return

    # ═══════════════════════════════════════════════
    # PASO 1: SELECCIONA LA RUTA PRINCIPAL
    # ═══════════════════════════════════════════════
    divider()
section_header("📌", "Selecciona la Ruta Principal")

    st.write("**Paso 1:** Filtra las rutas (opcional)")
    df_filtrado_principal = _filtrar_rutas(df, "principal")

    st.write(f"**Paso 2:** Selecciona una ruta ({len(df_filtrado_principal)} disponibles)")

    if df_filtrado_principal.empty:
        alert("warn", "No hay rutas que cumplan con los filtros seleccionados.")
        return

    opciones_principal = [_format_ruta_label(row) for _, row in df_filtrado_principal.iterrows()]
    
    ruta_principal_label = st.selectbox(
        "Ruta Principal",
        options=opciones_principal,
        key="sel_ruta_principal"
    )

    idx_principal = opciones_principal.index(ruta_principal_label)
    ruta_principal = df_filtrado_principal.iloc[idx_principal]

    # Mostrar detalles de ruta seleccionada
    with st.expander("📋 Ver detalles de la ruta seleccionada", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**ID Ruta:** {ruta_principal.get('ID_Ruta', 'N/A')}")
            st.markdown(f"**Tipo:** {ruta_principal.get('Tipo', 'N/A')}")
            st.markdown(f"**Cliente:** {ruta_principal.get('Cliente', 'N/A')}")
            st.markdown(f"**Fecha:** {ruta_principal.get('Fecha', 'N/A')}")
        with col2:
            st.markdown(f"**Origen:** {ruta_principal.get('Origen', 'N/A')}")
            st.markdown(f"**Destino:** {ruta_principal.get('Destino', 'N/A')}")
            st.markdown(f"**Ingreso Total:** ${safe_number(ruta_principal.get('Ingreso Total', 0)):,.2f}")
            st.markdown(f"**Costo Directo:** ${safe_number(ruta_principal.get('Costo_Total_Ruta', 0)):,.2f}")

    # ═══════════════════════════════════════════════
    # PASO 2: SUGERIR COMBINACIONES
    # ═══════════════════════════════════════════════
    divider()
section_header("🔄", "Rutas sugeridas (combinaciones con o sin vacío)")

    tipo_principal = str(ruta_principal["Tipo"]).strip().upper()
    destino_principal = str(ruta_principal["Destino"]).strip().upper()

    tipos_conector = ["VACIO", "DOM MEX"]
    tipo_regreso = "EXPORTACION" if tipo_principal == "IMPORTACION" else "IMPORTACION"

    sugerencias = []

    # 1) Rutas directas desde el destino principal
    if tipo_principal != "VACIO":
        rutas_directas = df[
            (df["Tipo"] == tipo_regreso) & (df["Origen"] == destino_principal)
        ].copy()
        for _, row in rutas_directas.iterrows():
            ingreso_total = safe_number(ruta_principal["Ingreso Total"]) + safe_number(row["Ingreso Total"])
            costo_total = safe_number(ruta_principal["Costo_Total_Ruta"]) + safe_number(row["Costo_Total_Ruta"])
            utilidad = ingreso_total - costo_total
            porcentaje = (utilidad / ingreso_total * 100) if ingreso_total > 0 else 0
            
            # AGREGAR ID_RUTA en la descripción
            descripcion = (
                f"{row.get('ID_Ruta', '')} | {row['Fecha']} — "
                f"{row['Cliente']} {row['Origen']} → {row['Destino']} ({porcentaje:.2f}%)"
            )
            sugerencias.append({
                "descripcion": descripcion,
                "tramos": [row],
                "utilidad": utilidad,
                "porcentaje": porcentaje
            })

    # 2) Rutas con VACÍO o DOM MEX + ruta cliente
    for tipo_con in tipos_conector:
        rutas_conector = df[(df["Tipo"] == tipo_con) & (df["Origen"] == destino_principal)].copy()
        for _, con_row in rutas_conector.iterrows():
            destino_con = str(con_row["Destino"]).strip().upper()
            rutas_finales = df[
                (df["Tipo"] == tipo_regreso) & (df["Origen"] == destino_con)
            ].copy()
            for _, final_row in rutas_finales.iterrows():
                ingreso_total = (
                    safe_number(ruta_principal["Ingreso Total"]) + 
                    safe_number(final_row["Ingreso Total"])
                )
                costo_total = (
                    safe_number(ruta_principal["Costo_Total_Ruta"]) + 
                    safe_number(con_row["Costo_Total_Ruta"]) + 
                    safe_number(final_row["Costo_Total_Ruta"])
                )
                utilidad = ingreso_total - costo_total
                porcentaje = (utilidad / ingreso_total * 100) if ingreso_total > 0 else 0
                
                label_con = "Vacío" if tipo_con == "VACIO" else "Dom Mex"
                # AGREGAR ID_RUTA de la ruta final
                descripcion = (
                    f"{final_row.get('ID_Ruta', '')} | {final_row['Fecha']} — "
                    f"{final_row['Cliente']} ({label_con} → "
                    f"{con_row['Origen']} → {con_row['Destino']}) → "
                    f"{final_row['Destino']} ({porcentaje:.2f}%)"
                )
                sugerencias.append({
                    "descripcion": descripcion,
                    "tramos": [con_row, final_row],
                    "utilidad": utilidad,
                    "porcentaje": porcentaje
                })

    # 3) Si principal es VACIO o DOM MEX: buscar import/export desde su destino
    if tipo_principal in tipos_conector:
        rutas_finales = df[
            (df["Tipo"].isin(["IMPORTACION", "EXPORTACION"])) & 
            (df["Origen"] == destino_principal)
        ].copy()
        for _, final_row in rutas_finales.iterrows():
            ingreso_total = (
                safe_number(ruta_principal["Ingreso Total"]) + 
                safe_number(final_row["Ingreso Total"])
            )
            costo_total = (
                safe_number(ruta_principal["Costo_Total_Ruta"]) + 
                safe_number(final_row["Costo_Total_Ruta"])
            )
            utilidad = ingreso_total - costo_total
            porcentaje = (utilidad / ingreso_total * 100) if ingreso_total > 0 else 0
            
            # AGREGAR ID_RUTA
            descripcion = (
                f"{final_row.get('ID_Ruta', '')} | {final_row['Fecha']} — "
                f"{final_row['Cliente']} {final_row['Origen']} → "
                f"{final_row['Destino']} ({porcentaje:.2f}%)"
            )
            sugerencias.append({
                "descripcion": descripcion,
                "tramos": [final_row],
                "utilidad": utilidad,
                "porcentaje": porcentaje
            })

    # Ordenar por utilidad
    sugerencias = sorted(sugerencias, key=lambda x: x["porcentaje"], reverse=True)

    if not sugerencias:
        alert("warn", "⚠️ No se encontraron combinaciones posibles.")
        return

    st.markdown(f"📊 Se encontraron **{len(sugerencias)} combinaciones posibles**")

    descripciones = [s["descripcion"] for s in sugerencias]
    seleccion_desc = st.selectbox(
        "Selecciona una opción de regreso sugerida",
        descripciones,
        index=0,
        key="sel_regreso_sugerido"
    )

    seleccion_obj = next(s for s in sugerencias if s["descripcion"] == seleccion_desc)
    rutas_seleccionadas = [ruta_principal.to_dict()] + [t.to_dict() for t in seleccion_obj["tramos"]]

    # ═══════════════════════════════════════════════
    # BOTÓN: SIMULAR VUELTA REDONDA
    # ═══════════════════════════════════════════════
    divider()
    
    col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
    with col_btn2:
        if st.button("🚛 Simular Vuelta Redonda", type="primary", use_container_width=True):
            # Calcular utilidades usando el helper (que ya considera VACIO sin 35%)
            res = calcular_utilidades_vuelta_redonda(rutas_seleccionadas)
            
            st.session_state.ingreso_total = res["ingreso_total"]
            st.session_state.costo_total = res["costo_total"]
            st.session_state.utilidad_bruta = res["utilidad_bruta"]
            st.session_state.costos_indirectos = res["costos_indirectos"]
            st.session_state.utilidad_neta = res["utilidad_neta"]
            st.session_state.pct_bruta = res["porcentaje_bruta"]
            st.session_state.pct_neta = res["porcentaje_neta"]
            st.session_state.rutas_seleccionadas = rutas_seleccionadas
            st.session_state.igloo_simulacion_realizada = True
            st.rerun()

    # ═══════════════════════════════════════════════
    # MOSTRAR RESULTADOS SI YA SE SIMULÓ
    # ═══════════════════════════════════════════════
    if st.session_state.igloo_simulacion_realizada:
        divider()
        
        # RESUMEN DE VUELTA REDONDA (antes era "Detalle de Rutas")
    section_header("📊", "Resumen de Vuelta Redonda")
        
        for i, r in enumerate(st.session_state.rutas_seleccionadas, 1):
            with st.expander(f"{i}. {r['Tipo']} — {r.get('Cliente', 'N/A')}", expanded=True):
                st.markdown(f"**ID Ruta:** {r.get('ID_Ruta', 'N/A')}")
                st.markdown(f"- Fecha: {r.get('Fecha', 'N/A')}")
                st.markdown(f"- {r['Origen']} → {r['Destino']}")
                st.markdown(f"- Ingreso Total: **${safe_number(r.get('Ingreso Total', 0)):,.2f}**")
                st.markdown(f"- Costo Directo Ruta: ${safe_number(r.get('Costo_Total_Ruta', 0)):,.2f}")
                
                # Mostrar costos indirectos por ruta
                tipo_r = str(r.get("Tipo", "")).strip().upper()
                ing_r = safe_number(r.get("Ingreso Total", 0))
                costos_ind_r = calcular_costos_indirectos(tipo_r, ing_r)
                
                if costos_ind_r > 0:
                    st.markdown(f"- *Costos Indirectos (35%): ${costos_ind_r:,.2f}*")
                else:
                    st.markdown(f"- *Costos Indirectos: $0.00 (VACÍO)*")

        # UTILIDADES GLOBALES
        divider()
        mostrar_resultados_utilidad(
            st,
            st.session_state.ingreso_total,
            st.session_state.costo_total,
            st.session_state.utilidad_bruta,
            st.session_state.costos_indirectos,
            st.session_state.utilidad_neta,
            st.session_state.pct_bruta,
            st.session_state.pct_neta,
        )

        # ═══════════════════════════════════════════════
        # DETALLE DE RUTAS (antes era "Resumen de Rutas")
        # ═══════════════════════════════════════════════
        divider()
    section_header("📋", "Detalle de Rutas")

        tipos_orden = ["IMPORTACION", "VACIO", "EXPORTACION", "DOM MEX"]
        cols = st.columns(len([t for t in tipos_orden if any(r["Tipo"] == t for r in st.session_state.rutas_seleccionadas)]))

        col_idx = 0
        for tipo in tipos_orden:
            ruta = next((r for r in st.session_state.rutas_seleccionadas if r["Tipo"] == tipo), None)
            if ruta is None:
                continue
                
            with cols[col_idx]:
                st.markdown(f"**{tipo}**")
                st.markdown(f"Fecha: {ruta.get('Fecha', 'N/A')}")
                st.markdown(f"Cliente: {ruta.get('Cliente', 'N/A')}")
                st.markdown(f"Ruta: {ruta.get('Origen', 'N/A')} → {ruta.get('Destino', 'N/A')}")
                st.markdown(f"KM: {safe_number(ruta.get('KM')):,.2f}")
                st.markdown(f"Ingreso Original: ${safe_number(ruta.get('Ingreso_Original')):,.2f}")
                st.markdown(f"Moneda: {ruta.get('Moneda', 'N/A')}")
                st.markdown(f"Tipo de cambio: {safe_number(ruta.get('Tipo de cambio')):,.2f}")
                st.markdown(f"**Ingreso Flete: ${safe_number(ruta.get('Ingreso Flete')):,.2f}**", unsafe_allow_html=True)
                st.markdown(f"Cruce Original: ${safe_number(ruta.get('Cruce_Original')):,.2f}")
                st.markdown(f"**Ingreso Total: ${safe_number(ruta.get('Ingreso Total')):,.2f}**", unsafe_allow_html=True)
                st.markdown(f"Costo Diesel: ${safe_number(ruta.get('Costo Diesel')):,.2f}")
                st.markdown(f"Diesel Camión: ${safe_number(ruta.get('Costo_Diesel_Camion')):,.2f}")
                st.markdown(f"Diesel Termo: ${safe_number(ruta.get('Costo_Diesel_Termo')):,.2f}")
                st.markdown(f"Sueldo: ${safe_number(ruta.get('Sueldo_Operador')):,.2f}")
                st.markdown(f"Casetas: ${safe_number(ruta.get('Casetas')):,.2f}")
                
            col_idx += 1

        # ═══════════════════════════════════════════════
        # GENERAR PDF PROFESIONAL
        # ═══════════════════════════════════════════════
        divider()
    section_header("📥", "Generar PDF de la Simulación")
        
        col_pdf1, col_pdf2, col_pdf3 = st.columns([1, 2, 1])
        with col_pdf2:
            if st.button("📄 Generar PDF Profesional", key="btn_gen_pdf"):
                try:
                    pdf_path = generar_pdf_vuelta_redonda(
                        st.session_state.rutas_seleccionadas,
                        st.session_state.ingreso_total,
                        st.session_state.costo_total,
                        st.session_state.utilidad_bruta,
                        st.session_state.costos_indirectos,
                        st.session_state.utilidad_neta,
                        st.session_state.pct_bruta,
                        st.session_state.pct_neta,
                    )
                    
                    with open(pdf_path, "rb") as f:
                        pdf_bytes = f.read()
                    
                    primer_ruta = st.session_state.rutas_seleccionadas[0]
                    nombre_archivo = f"Simulacion_VueltaRedonda_{primer_ruta.get('ID_Ruta', 'SinID')}.pdf"
                    
                    st.download_button(
                        label="📥 Descargar PDF",
                        data=pdf_bytes,
                        file_name=nombre_archivo,
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True
                    )
                    
                    alert("success", "✅ PDF generado exitosamente")
                    
                except Exception as e:
                    st.error(f"❌ Error generando PDF: {e}")
                    st.exception(e)
