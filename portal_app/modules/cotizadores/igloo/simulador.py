"""
simulador.py — Cotizador Igloo
Simulador de Vuelta Redonda.
Diseño homologado con Lincoln y Set Logis:
  - Sin st.title()
  - Botón recargar en col [1,4]
  - Resultados con mostrar_resultados_utilidad() → kpi_row + semaforos_ruta
  - Detalles de cada tramo en expanders con st.caption()
  - PDF sin cambios
"""

import tempfile
from datetime import datetime

import pandas as pd
import streamlit as st

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

from services.supabase_client import get_supabase_client
from ui.components import section_header, alert, divider

from .helpers import (
    safe_number,
    cargar_datos_generales,
    calcular_costos_indirectos,
    calcular_utilidades_vuelta_redonda,
    mostrar_resultados_utilidad,
)


# ─────────────────────────────────────────────
# CACHE
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=120)
def _load_rutas_igloo_cached(table_name: str) -> pd.DataFrame:
    supabase = get_supabase_client()
    if supabase is None:
        return pd.DataFrame()
    try:
        resp = supabase.table(table_name).select("*").order("Fecha", desc=True).execute()
        return pd.DataFrame(resp.data) if resp.data else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


# ─────────────────────────────────────────────
# FILTROS Y LABEL
# ─────────────────────────────────────────────
def _filtrar_rutas(df: pd.DataFrame, prefix_key: str) -> pd.DataFrame:
    with st.expander("🔎 Filtros de búsqueda (opcional)", expanded=False):
        fc1, fc2, fc3, fc4 = st.columns(4)
        tipos_disp    = ["Todos"] + sorted(df["Tipo"].dropna().unique().tolist()) if "Tipo" in df.columns else ["Todos"]
        clientes_disp = ["Todos"] + sorted(df["Cliente"].dropna().astype(str).unique().tolist()) if "Cliente" in df.columns else ["Todos"]
        filtro_tipo    = fc1.selectbox("Tipo",              tipos_disp,    key=f"{prefix_key}_ftipo")
        filtro_cliente = fc2.selectbox("Cliente",           clientes_disp, key=f"{prefix_key}_fcli")
        filtro_origen  = fc3.text_input("Origen contiene",                 key=f"{prefix_key}_forig")
        filtro_destino = fc4.text_input("Destino contiene",                key=f"{prefix_key}_fdest")

    resultado = df.copy()
    if filtro_tipo    != "Todos": resultado = resultado[resultado["Tipo"] == filtro_tipo]
    if filtro_cliente != "Todos": resultado = resultado[resultado["Cliente"].astype(str) == filtro_cliente]
    if filtro_origen.strip():     resultado = resultado[resultado["Origen"].astype(str).str.contains(filtro_origen.strip(), case=False, na=False)]
    if filtro_destino.strip():    resultado = resultado[resultado["Destino"].astype(str).str.contains(filtro_destino.strip(), case=False, na=False)]
    return resultado


def _format_ruta_label(row) -> str:
    fecha = str(row.get("Fecha", ""))[:10]
    return (
        f"{row.get('ID_Ruta', '')} | {fecha} | "
        f"{row.get('Tipo', '')} | {row.get('Cliente', '')} | "
        f"{row.get('Origen', '')} → {row.get('Destino', '')}"
    )


# ─────────────────────────────────────────────
# PDF VUELTA REDONDA (sin cambios en lógica)
# ─────────────────────────────────────────────
def generar_pdf_vuelta_redonda(rutas_seleccionadas, ingreso_total, costo_total,
                                utilidad_bruta, costos_indirectos, utilidad_neta,
                                pct_bruta, pct_neta):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    doc = SimpleDocTemplate(
        tmp.name, pagesize=letter,
        leftMargin=0.6*inch, rightMargin=0.6*inch,
        topMargin=0.5*inch,  bottomMargin=0.5*inch,
    )
    styles       = getSampleStyleSheet()
    title_style  = ParagraphStyle("T",  parent=styles["Title"],   fontSize=16, textColor=colors.HexColor("#1B2266"), spaceAfter=6)
    subtitle_style = ParagraphStyle("S", parent=styles["Heading2"], fontSize=11, textColor=colors.HexColor("#1B2266"), spaceBefore=12, spaceAfter=4)
    compact_cell = ParagraphStyle("C",  parent=styles["Normal"],  fontSize=7, leading=8)
    story = []

    # Encabezado
    header_data = [[
        Paragraph("<b>IGLOO TRANSPORT S DE RL DE CV</b>",
                  ParagraphStyle("H",  parent=styles["Normal"], fontSize=13, textColor=colors.white)),
        Paragraph("Simulador de Vuelta Redonda",
                  ParagraphStyle("HR", parent=styles["Normal"], fontSize=9,  textColor=colors.white, alignment=TA_RIGHT)),
    ]]
    header_table = Table(header_data, colWidths=[5.0*inch, 2.0*inch])
    header_table.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), colors.HexColor("#1B2266")),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING",   (0,0), (0,-1),  12),
        ("RIGHTPADDING",  (-1,0),(-1,-1), 12),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles["Normal"]))
    story.append(Spacer(1, 8))

    # Resumen global
    story.append(Paragraph("📊 Resumen de Vuelta Redonda", subtitle_style))
    color_utilidad = colors.HexColor("#28a745") if utilidad_neta >= 0 else colors.HexColor("#dc3545")
    pct_costo      = (costo_total       / ingreso_total * 100) if ingreso_total > 0 else 0
    pct_indirectos = (costos_indirectos / ingreso_total * 100) if ingreso_total > 0 else 0

    resumen_data = [
        ["Concepto",        "Monto",                    "%"],
        ["Ingreso Total",   f"${ingreso_total:,.2f} MXP",   "100.00%"],
        ["Costo Directo",   f"${costo_total:,.2f} MXP",     f"{pct_costo:.2f}%"],
        ["Utilidad Bruta",  f"${utilidad_bruta:,.2f} MXP",  f"{pct_bruta:.2f}%"],
        ["Costos Indirectos", f"${costos_indirectos:,.2f} MXP", f"{pct_indirectos:.2f}%"],
        ["Utilidad Neta",   f"${utilidad_neta:,.2f} MXP",   f"{pct_neta:.2f}%"],
    ]
    resumen_table = Table(resumen_data, colWidths=[2.5*inch, 2.5*inch, 2.0*inch])
    resumen_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0),  colors.HexColor("#1B2266")),
        ("TEXTCOLOR",  (0,0), (-1,0),  colors.white),
        ("FONTNAME",   (0,0), (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,-1), 7),
        ("GRID",       (0,0), (-1,-1), 0.5, colors.HexColor("#dee2e6")),
        ("ALIGN",      (1,1), (-1,-1), "RIGHT"),
        ("BACKGROUND", (0,5), (-1,5),  color_utilidad),
        ("TEXTCOLOR",  (0,5), (-1,5),  colors.white),
        ("FONTNAME",   (0,5), (-1,5),  "Helvetica-Bold"),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0), (-1,-1), 2),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2),
    ]))
    story.append(resumen_table)
    story.append(Spacer(1, 14))

    # Detalle de cada ruta
    story.append(Paragraph("📋 Detalle de Rutas", subtitle_style))
    for i, ruta in enumerate(rutas_seleccionadas, 1):
        tipo_ruta = str(ruta.get("Tipo", ""))
        story.append(Paragraph(
            f"<b>{i}. {tipo_ruta} — {ruta.get('Cliente', 'N/A')}</b>",
            ParagraphStyle("RH", parent=styles["Normal"], fontSize=10, textColor=colors.HexColor("#1B2266")),
        ))
        story.append(Spacer(1, 4))

        ruta_info = [
            ["ID Ruta", str(ruta.get("ID_Ruta", "")),    "Fecha",    str(ruta.get("Fecha", ""))],
            ["Tipo",    tipo_ruta,                         "KM",       f"{safe_number(ruta.get('KM',0)):,.2f}"],
            ["Cliente", Paragraph(str(ruta.get("Cliente","")), compact_cell), "Modo", str(ruta.get("Modo de Viaje",""))],
            ["Origen",  Paragraph(str(ruta.get("Origen", "")), compact_cell),
             "Destino", Paragraph(str(ruta.get("Destino","")), compact_cell)],
        ]
        ruta_table = Table(ruta_info, colWidths=[1.2*inch, 2.0*inch, 1.2*inch, 2.0*inch])
        ruta_table.setStyle(TableStyle([
            ("BACKGROUND", (0,0),(0,-1), colors.HexColor("#f0f2f6")),
            ("BACKGROUND", (2,0),(2,-1), colors.HexColor("#f0f2f6")),
            ("FONTSIZE",   (0,0),(-1,-1), 7),
            ("FONTNAME",   (0,0),(0,-1),  "Helvetica-Bold"),
            ("FONTNAME",   (2,0),(2,-1),  "Helvetica-Bold"),
            ("GRID",       (0,0),(-1,-1), 0.5, colors.HexColor("#dee2e6")),
            ("VALIGN",     (0,0),(-1,-1), "MIDDLE"),
            ("TOPPADDING",    (0,0),(-1,-1), 1),
            ("BOTTOMPADDING", (0,0),(-1,-1), 1),
            ("LEFTPADDING",   (0,0),(-1,-1), 6),
        ]))
        story.append(ruta_table)
        story.append(Spacer(1, 6))

        ing_total_ruta = safe_number(ruta.get("Ingreso Total", 0))
        costo_ruta     = safe_number(ruta.get("Costo_Total_Ruta", 0))
        costos_ind_ruta = calcular_costos_indirectos(tipo_ruta, ing_total_ruta)

        fin_data = [
            ["Ingreso Original",   f"${safe_number(ruta.get('Ingreso_Original',0)):,.2f}"],
            ["Moneda",              str(ruta.get("Moneda", "MXP"))],
            ["Tipo de cambio",      f"{safe_number(ruta.get('Tipo de cambio',1.0)):,.2f}"],
            ["Ingreso Total",       f"${ing_total_ruta:,.2f} MXP"],
            ["Costo Directo Ruta",  f"${costo_ruta:,.2f} MXP"],
            ["Costos Indirectos (35%)" if costos_ind_ruta > 0 else "Costos Indirectos (0% — VACÍO)",
             f"${costos_ind_ruta:,.2f} MXP"],
        ]
        fin_table = Table(fin_data, colWidths=[2.5*inch, 3.5*inch])
        fin_table.setStyle(TableStyle([
            ("BACKGROUND", (0,0),(0,-1), colors.HexColor("#e8f4f8")),
            ("FONTSIZE",   (0,0),(-1,-1), 7),
            ("FONTNAME",   (0,0),(0,-1),  "Helvetica-Bold"),
            ("GRID",       (0,0),(-1,-1), 0.5, colors.HexColor("#dee2e6")),
            ("VALIGN",     (0,0),(-1,-1), "MIDDLE"),
            ("TOPPADDING",    (0,0),(-1,-1), 2),
            ("BOTTOMPADDING", (0,0),(-1,-1), 2),
            ("LEFTPADDING",   (0,0),(-1,-1), 6),
            ("ALIGN",      (1,0),(1,-1),  "RIGHT"),
        ]))
        story.append(fin_table)
        story.append(Spacer(1, 10))

    # Footer
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        f"Reporte generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} — Igloo Transport",
        ParagraphStyle("F", parent=styles["Normal"], fontSize=7,
                       textColor=colors.HexColor("#6c757d"), alignment=TA_CENTER),
    ))
    doc.build(story)
    return tmp.name


# ─────────────────────────────────────────────
# RENDER PRINCIPAL
# ─────────────────────────────────────────────
def render():
    supabase = get_supabase_client()
    if supabase is None:
        alert("warn", "⚠️ Supabase no configurado. No se pueden cargar rutas.")
        return

    TABLE_RUTAS = "Rutas"
    st.session_state.setdefault("igloo_simulacion_realizada", False)

    # ── Recargar ──────────────────────────────────────────────────
    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("🔄 Recargar", key="reload_rutas_simulador"):
            _load_rutas_igloo_cached.clear()
            st.rerun()
    with c2:
        st.caption("Carga cacheada 2 min. Usa 'Recargar' si acabas de guardar algo.")

    df = _load_rutas_igloo_cached(TABLE_RUTAS)
    if df.empty:
        alert("warn", "⚠️ No hay rutas registradas en Supabase.")
        return

    # Normalizar texto
    for col in ["Origen", "Destino", "Cliente", "Tipo"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.upper()

    if "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d")

    # ── Paso 1: Ruta principal ────────────────────────────────────
    divider()
    section_header("📌", "Paso 1 — Ruta Principal")
    st.caption("Filtra las rutas disponibles y selecciona la ruta de ida.")
    df_filtrado_principal = _filtrar_rutas(df, "principal")

    if df_filtrado_principal.empty:
        alert("warn", "No hay rutas que cumplan con los filtros seleccionados.")
        return

    opciones_principal = [_format_ruta_label(row) for _, row in df_filtrado_principal.iterrows()]
    ruta_principal_label = st.selectbox(
        f"Selecciona la ruta principal ({len(df_filtrado_principal)} disponibles)",
        options=opciones_principal,
        key="sel_ruta_principal",
    )

    idx_principal  = opciones_principal.index(ruta_principal_label)
    ruta_principal = df_filtrado_principal.iloc[idx_principal]

    with st.expander("📋 Ver detalles de la ruta seleccionada", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            st.caption(f"**ID Ruta:** {ruta_principal.get('ID_Ruta', 'N/A')}")
            st.caption(f"**Tipo:** {ruta_principal.get('Tipo', 'N/A')}")
            st.caption(f"**Cliente:** {ruta_principal.get('Cliente', 'N/A')}")
            st.caption(f"**Fecha:** {ruta_principal.get('Fecha', 'N/A')}")
        with c2:
            st.caption(f"**Origen:** {ruta_principal.get('Origen', 'N/A')}")
            st.caption(f"**Destino:** {ruta_principal.get('Destino', 'N/A')}")
            st.caption(f"**Ingreso Total:** ${safe_number(ruta_principal.get('Ingreso Total', 0)):,.2f}")
            st.caption(f"**Costo Directo:** ${safe_number(ruta_principal.get('Costo_Total_Ruta', 0)):,.2f}")

    # ── Paso 2: Sugerir combinaciones ─────────────────────────────
    divider()
    section_header("🔄", "Paso 2 — Selecciona el Regreso")
    st.caption("Combinaciones sugeridas ordenadas por % utilidad combinada.")

    tipo_principal     = str(ruta_principal.get("Tipo", "")).strip().upper()
    destino_principal  = str(ruta_principal.get("Destino", "")).strip().upper()
    origen_principal   = str(ruta_principal.get("Origen",  "")).strip().upper()
    tipos_directos     = ["IMPORTACION", "EXPORTACION"]
    tipos_conector     = ["VACIO", "DOM MEX"]

    sugerencias = []

    # Rutas directas de regreso (origen del regreso = destino de la principal)
    rutas_directas = df[
        (df["Tipo"].isin(tipos_directos)) &
        (df["Origen"] == destino_principal)
    ].copy()

    for _, regreso_row in rutas_directas.iterrows():
        ingreso_t = safe_number(ruta_principal["Ingreso Total"]) + safe_number(regreso_row["Ingreso Total"])
        costo_t   = safe_number(ruta_principal["Costo_Total_Ruta"]) + safe_number(regreso_row["Costo_Total_Ruta"])
        utilidad  = ingreso_t - costo_t
        porcentaje = (utilidad / ingreso_t * 100) if ingreso_t > 0 else 0
        descripcion = (
            f"{regreso_row.get('ID_Ruta','')} | {regreso_row['Fecha']} — "
            f"{regreso_row['Cliente']} {regreso_row['Origen']} → "
            f"{regreso_row['Destino']} ({porcentaje:.2f}%)"
        )
        sugerencias.append({
            "descripcion": descripcion,
            "tramos":      [regreso_row],
            "utilidad":    utilidad,
            "porcentaje":  porcentaje,
        })

    # Rutas con vacío como puente
    rutas_vacio = df[
        (df["Tipo"] == "VACIO") &
        (df["Origen"] == destino_principal)
    ].copy()

    for _, vacio_row in rutas_vacio.iterrows():
        destino_vacio = str(vacio_row.get("Destino", "")).strip().upper()
        rutas_finales = df[
            (df["Tipo"].isin(tipos_directos)) &
            (df["Origen"] == destino_vacio)
        ].copy()
        for _, final_row in rutas_finales.iterrows():
            ingreso_t = (safe_number(ruta_principal["Ingreso Total"]) +
                         safe_number(vacio_row["Ingreso Total"]) +
                         safe_number(final_row["Ingreso Total"]))
            costo_t   = (safe_number(ruta_principal["Costo_Total_Ruta"]) +
                         safe_number(vacio_row["Costo_Total_Ruta"]) +
                         safe_number(final_row["Costo_Total_Ruta"]))
            utilidad  = ingreso_t - costo_t
            porcentaje = (utilidad / ingreso_t * 100) if ingreso_t > 0 else 0
            descripcion = (
                f"[VACÍO] {vacio_row.get('ID_Ruta','')} + "
                f"{final_row.get('ID_Ruta','')} | {final_row['Cliente']} "
                f"{final_row['Origen']} → {final_row['Destino']} ({porcentaje:.2f}%)"
            )
            sugerencias.append({
                "descripcion": descripcion,
                "tramos":      [vacio_row, final_row],
                "utilidad":    utilidad,
                "porcentaje":  porcentaje,
            })

    # Rutas tipo conector como final
    if tipo_principal in tipos_directos:
        rutas_conector = df[
            (df["Tipo"].isin(tipos_conector)) &
            (df["Origen"] == destino_principal)
        ].copy()
        for _, con_row in rutas_conector.iterrows():
            ingreso_t = safe_number(ruta_principal["Ingreso Total"]) + safe_number(con_row["Ingreso Total"])
            costo_t   = safe_number(ruta_principal["Costo_Total_Ruta"]) + safe_number(con_row["Costo_Total_Ruta"])
            utilidad  = ingreso_t - costo_t
            porcentaje = (utilidad / ingreso_t * 100) if ingreso_t > 0 else 0
            descripcion = (
                f"{con_row.get('ID_Ruta','')} | {con_row['Fecha']} — "
                f"{con_row['Tipo']} {con_row['Origen']} → "
                f"{con_row['Destino']} ({porcentaje:.2f}%)"
            )
            sugerencias.append({
                "descripcion": descripcion,
                "tramos":      [con_row],
                "utilidad":    utilidad,
                "porcentaje":  porcentaje,
            })

    sugerencias = sorted(sugerencias, key=lambda x: x["porcentaje"], reverse=True)

    if not sugerencias:
        alert("warn", "⚠️ No se encontraron combinaciones posibles para esta ruta.")
        return

    st.caption(f"📊 Se encontraron **{len(sugerencias)} combinaciones posibles**")
    descripciones    = [s["descripcion"] for s in sugerencias]
    seleccion_desc   = st.selectbox(
        "Selecciona una opción de regreso",
        descripciones,
        index=0,
        key="sel_regreso_sugerido",
    )
    seleccion_obj    = next(s for s in sugerencias if s["descripcion"] == seleccion_desc)
    rutas_seleccionadas = [ruta_principal.to_dict()] + [t.to_dict() for t in seleccion_obj["tramos"]]

    # ── Botón simular ─────────────────────────────────────────────
    divider()
    b1, b2, b3 = st.columns([1, 2, 1])
    with b2:
        if st.button("🚛 Simular Vuelta Redonda", type="primary", use_container_width=True, key="igloo_sim_btn"):
            res = calcular_utilidades_vuelta_redonda(rutas_seleccionadas)
            st.session_state.ingreso_total           = res["ingreso_total"]
            st.session_state.costo_total             = res["costo_total"]
            st.session_state.utilidad_bruta          = res["utilidad_bruta"]
            st.session_state.costos_indirectos       = res["costos_indirectos"]
            st.session_state.utilidad_neta           = res["utilidad_neta"]
            st.session_state.pct_bruta               = res["porcentaje_bruta"]
            st.session_state.pct_neta                = res["porcentaje_neta"]
            st.session_state.rutas_seleccionadas     = rutas_seleccionadas
            st.session_state.igloo_simulacion_realizada = True
            st.rerun()

    # ── Resultados ────────────────────────────────────────────────
    if st.session_state.igloo_simulacion_realizada:
        divider()
        section_header("📊", "Resumen de Vuelta Redonda")

        ingreso_total     = st.session_state.ingreso_total
        costo_total       = st.session_state.costo_total
        utilidad_bruta    = st.session_state.utilidad_bruta
        costos_indirectos = st.session_state.costos_indirectos
        utilidad_neta     = st.session_state.utilidad_neta
        pct_bruta         = st.session_state.pct_bruta
        pct_neta          = st.session_state.pct_neta

        # Tipo combinado: usar el de la ruta principal para los umbrales
        tipo_combinado = str(st.session_state.rutas_seleccionadas[0].get("Tipo", "IMPORTACION"))

        mostrar_resultados_utilidad(
            st,
            ingreso_total, costo_total,
            utilidad_bruta, costos_indirectos,
            utilidad_neta, pct_bruta, pct_neta,
            tipo=tipo_combinado,
            tc_usd=0.0,  # vuelta redonda siempre MXP
        )

        # ── Detalle de cada tramo ─────────────────────────────────
        divider()
        section_header("🗺️", "Detalle de Tramos")
        for i, r in enumerate(st.session_state.rutas_seleccionadas, 1):
            tipo_tramo = str(r.get("Tipo", ""))
            ing_ruta   = safe_number(r.get("Ingreso Total", 0))
            costo_ruta = safe_number(r.get("Costo_Total_Ruta", 0))
            ind_ruta   = calcular_costos_indirectos(tipo_tramo, ing_ruta)
            ut_ruta    = ing_ruta - costo_ruta

            etiqueta = f"{'🔵' if tipo_tramo == 'IMPORTACION' else '🟠' if tipo_tramo == 'EXPORTACION' else '⚪'} Tramo {i}: {tipo_tramo} — {r.get('Cliente','N/A')} | {r.get('Origen','')} → {r.get('Destino','')}"
            with st.expander(etiqueta, expanded=False):
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.caption(f"**ID:** {r.get('ID_Ruta','')}")
                    st.caption(f"**Fecha:** {r.get('Fecha','')}")
                    st.caption(f"**KM:** {safe_number(r.get('KM',0)):,.2f}")
                    st.caption(f"**Modo:** {r.get('Modo de Viaje','')}")
                with c2:
                    st.caption(f"**Ingreso Total:** ${ing_ruta:,.2f}")
                    st.caption(f"**Costo Directo:** ${costo_ruta:,.2f}")
                    st.caption(f"**Utilidad Bruta:** ${ut_ruta:,.2f}")
                with c3:
                    st.caption(f"**Costos Ind. (35%):** ${ind_ruta:,.2f}" if ind_ruta > 0 else "**Costos Ind.:** $0.00 (VACÍO)")
                    st.caption(f"**Ut. Neta tramo:** ${ut_ruta - ind_ruta:,.2f}")
                    st.caption(f"**Moneda:** {r.get('Moneda','MXP')}")

        # ── PDF ───────────────────────────────────────────────────
        divider()
        section_header("📥", "Descargar Reporte")
        b1, b2, b3 = st.columns([1, 2, 1])
        with b2:
            if st.button("📄 Generar PDF", key="btn_gen_pdf", use_container_width=True):
                try:
                    pdf_path = generar_pdf_vuelta_redonda(
                        st.session_state.rutas_seleccionadas,
                        ingreso_total, costo_total,
                        utilidad_bruta, costos_indirectos,
                        utilidad_neta, pct_bruta, pct_neta,
                    )
                    primer_ruta  = st.session_state.rutas_seleccionadas[0]
                    nombre_pdf   = f"VR_Igloo_{primer_ruta.get('ID_Ruta','SinID')}.pdf"
                    with open(pdf_path, "rb") as f:
                        st.download_button(
                            "📥 Descargar PDF",
                            data=f.read(),
                            file_name=nombre_pdf,
                            mime="application/pdf",
                            type="primary",
                            use_container_width=True,
                            key="igloo_sim_dl_pdf",
                        )
                    alert("success", "✅ PDF generado exitosamente.")
                except Exception as e:
                    alert("error", f"❌ Error generando PDF: {e}")
