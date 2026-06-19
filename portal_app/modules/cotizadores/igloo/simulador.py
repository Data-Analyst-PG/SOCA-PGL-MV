"""
simulador.py — Cotizador Igloo
Simulador de Vuelta Redonda.
- Sin st.title(), recargar en col [1,4]
- filtrar_rutas_igloo / label_ruta_igloo desde helpers (sin duplicados)
- Detalle completo por ruta en expanders expanded=True
- Columnas con todos los campos de cada ruta
- mostrar_resultados_utilidad() para KPIs globales
- PDF original personalizado (versión aprobada)
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
from ui.components import section_header, alert, divider, mostrar_resultados_ruta

from .helpers import (
    safe_number,
    cargar_datos_generales,
    calcular_costos_indirectos,
    calcular_utilidades_vuelta_redonda,
    load_rutas_igloo,
    filtrar_rutas_igloo,
    label_ruta_igloo,
)


# ─────────────────────────────────────────────
# PDF ORIGINAL (versión aprobada)
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
    title_style  = ParagraphStyle("CustomTitle",    parent=styles["Title"],   fontSize=16, textColor=colors.HexColor("#1B2266"), spaceAfter=6)
    subtitle_style = ParagraphStyle("CustomSubtitle", parent=styles["Heading2"], fontSize=11, textColor=colors.HexColor("#1B2266"), spaceBefore=12, spaceAfter=4)
    normal       = ParagraphStyle("CustomNormal",   parent=styles["Normal"],  fontSize=9,  leading=12)
    compact_cell = ParagraphStyle("CompactCell",    parent=styles["Normal"],  fontSize=7,  leading=8, spaceBefore=0, spaceAfter=0)
    story = []

    # ── Encabezado ──
    header_data = [[
        Paragraph("<b>IGLOO TRANSPORT S DE RL DE CV</b>", ParagraphStyle(
            "Header", parent=styles["Normal"], fontSize=13, textColor=colors.white,
        )),
        Paragraph("Simulador de Vuelta Redonda", ParagraphStyle(
            "HeaderRight", parent=styles["Normal"], fontSize=9, textColor=colors.white, alignment=TA_RIGHT,
        )),
    ]]
    header_table = Table(header_data, colWidths=[5.0*inch, 2.0*inch])
    header_table.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), colors.HexColor("#1B2266")),
        ("TEXTCOLOR",     (0,0), (-1,-1), colors.white),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING",   (0,0), (0,-1),  12),
        ("RIGHTPADDING",  (-1,0),(-1,-1), 12),
        ("ROUNDEDCORNERS", [6,6,6,6]),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 12))

    # ── Resumen global ──
    story.append(Paragraph("📊 Resumen de Vuelta Redonda", subtitle_style))
    color_utilidad = colors.HexColor("#28a745") if utilidad_neta >= 0 else colors.HexColor("#dc3545")
    pct_costo      = (costo_total       / ingreso_total * 100) if ingreso_total > 0 else 0
    pct_indirectos = (costos_indirectos / ingreso_total * 100) if ingreso_total > 0 else 0
    resumen_data = [
        ["Concepto",          "Monto",                              "%"],
        ["Ingreso Total",     f"${ingreso_total:,.2f} MXP",         "100.00%"],
        ["Costo Directo",     f"${costo_total:,.2f} MXP",           f"{pct_costo:.2f}%"],
        ["Utilidad Bruta",    f"${utilidad_bruta:,.2f} MXP",        f"{pct_bruta:.2f}%"],
        ["Costos Indirectos", f"${costos_indirectos:,.2f} MXP",     f"{pct_indirectos:.2f}%"],
        ["Utilidad Neta",     f"${utilidad_neta:,.2f} MXP",         f"{pct_neta:.2f}%"],
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

    # ── Detalle de cada ruta ──
    story.append(Paragraph("📋 Detalle de Rutas", subtitle_style))
    for i, ruta in enumerate(rutas_seleccionadas, 1):
        tipo_ruta = str(ruta.get("Tipo", ""))
        story.append(Paragraph(
            f"<b>{i}. {tipo_ruta} — {ruta.get('Cliente', 'N/A')}</b>",
            ParagraphStyle("RutaHeader", parent=normal, fontSize=10, textColor=colors.HexColor("#1B2266")),
        ))
        story.append(Spacer(1, 4))

        ruta_info = [
            ["ID Ruta",  str(ruta.get("ID_Ruta", "")), "Fecha",    str(ruta.get("Fecha", ""))],
            ["Tipo",     tipo_ruta,                      "KM",       f"{safe_number(ruta.get('KM', 0)):,.2f}"],
            ["Cliente",  Paragraph(str(ruta.get("Cliente", "")), compact_cell), "Modo", str(ruta.get("Modo de Viaje", "Sencillo"))],
            ["Origen",   Paragraph(str(ruta.get("Origen",  "")), compact_cell),
             "Destino",  Paragraph(str(ruta.get("Destino", "")), compact_cell)],
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

        ing_orig       = safe_number(ruta.get("Ingreso_Original", 0))
        moneda         = str(ruta.get("Moneda", "MXP"))
        tc             = safe_number(ruta.get("Tipo de cambio", 1.0))
        ing_total_ruta = safe_number(ruta.get("Ingreso Total", 0))
        costo_ruta     = safe_number(ruta.get("Costo_Total_Ruta", 0))
        costos_ind_ruta = calcular_costos_indirectos(tipo_ruta, ing_total_ruta)

        financiera_data = [
            ["Ingreso Original",    f"${ing_orig:,.2f}"],
            ["Moneda",              moneda],
            ["Tipo de cambio",      f"{tc:,.2f}"],
            ["Ingreso Total",       f"${ing_total_ruta:,.2f} MXP"],
            ["Costo Directo Ruta",  f"${costo_ruta:,.2f} MXP"],
            ["Costos Indirectos (35%)" if costos_ind_ruta > 0 else "Costos Indirectos (0% - VACÍO)",
             f"${costos_ind_ruta:,.2f} MXP"],
        ]
        fin_table = Table(financiera_data, colWidths=[2.5*inch, 3.5*inch])
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

    # ── Footer ──
    usuario_nombre = "Usuario"
    if hasattr(st, "session_state") and "usuario" in st.session_state:
        usuario_data   = st.session_state.get("usuario", {})
        usuario_nombre = usuario_data.get("Nombre", "Usuario")
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        f"Reporte generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} por {usuario_nombre} — Igloo Transport",
        ParagraphStyle("Footer", parent=styles["Normal"], fontSize=7,
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
        if st.button("🔄 Recargar", key="igloo_sim_reload"):
            load_rutas_igloo.clear()
            st.rerun()
    with c2:
        st.caption("Carga cacheada 2 min. Usa 'Recargar' si acabas de guardar algo.")

    df = load_rutas_igloo(TABLE_RUTAS)
    if df.empty:
        alert("warn", "⚠️ No hay rutas registradas en Supabase.")
        return

    # ── Paso 1: Ruta principal ─────────────────────────────────────
    divider()
    section_header("📌", "Paso 1 — Ruta Principal")
    st.caption("Filtra las rutas disponibles y selecciona la ruta de ida.")
    df_filtrado_principal = filtrar_rutas_igloo(df, "ig_sim")

    if df_filtrado_principal.empty:
        alert("warn", "No hay rutas que cumplan con los filtros seleccionados.")
        return

    opciones_principal = [label_ruta_igloo(row) for _, row in df_filtrado_principal.iterrows()]
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
            st.markdown(f"**ID Ruta:** {ruta_principal.get('ID_Ruta', 'N/A')}")
            st.markdown(f"**Tipo:** {ruta_principal.get('Tipo', 'N/A')}")
            st.markdown(f"**Cliente:** {ruta_principal.get('Cliente', 'N/A')}")
            st.markdown(f"**Fecha:** {ruta_principal.get('Fecha', 'N/A')}")
        with c2:
            st.markdown(f"**Origen:** {ruta_principal.get('Origen', 'N/A')}")
            st.markdown(f"**Destino:** {ruta_principal.get('Destino', 'N/A')}")
            st.markdown(f"**Ingreso Total:** ${safe_number(ruta_principal.get('Ingreso Total', 0)):,.2f}")
            st.markdown(f"**Costo Directo:** ${safe_number(ruta_principal.get('Costo_Total_Ruta', 0)):,.2f}")

    # ── Paso 2: Sugerir combinaciones ──────────────────────────────
    divider()
    section_header("🔄", "Paso 2 — Selecciona el Regreso")

    tipo_principal    = str(ruta_principal["Tipo"]).strip().upper()
    destino_principal = str(ruta_principal["Destino"]).strip().upper()
    tipos_conector    = ["VACIO", "DOM MEX"]
    tipo_regreso      = "EXPORTACION" if tipo_principal == "IMPORTACION" else "IMPORTACION"

    sugerencias = []

    # 1) Rutas directas desde el destino principal
    if tipo_principal != "VACIO":
        rutas_directas = df[
            (df["Tipo"] == tipo_regreso) & (df["Origen"] == destino_principal)
        ].copy()
        for _, row in rutas_directas.iterrows():
            ingreso_t  = safe_number(ruta_principal["Ingreso Total"]) + safe_number(row["Ingreso Total"])
            costo_t    = safe_number(ruta_principal["Costo_Total_Ruta"]) + safe_number(row["Costo_Total_Ruta"])
            utilidad   = ingreso_t - costo_t
            porcentaje = (utilidad / ingreso_t * 100) if ingreso_t > 0 else 0
            sugerencias.append({
                "descripcion": (
                    f"{row.get('ID_Ruta','')} | {row['Fecha']} — "
                    f"{row['Cliente']} {row['Origen']} → {row['Destino']} ({porcentaje:.2f}%)"
                ),
                "tramos":     [row],
                "utilidad":   utilidad,
                "porcentaje": porcentaje,
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
                ingreso_t  = safe_number(ruta_principal["Ingreso Total"]) + safe_number(final_row["Ingreso Total"])
                costo_t    = (safe_number(ruta_principal["Costo_Total_Ruta"]) +
                              safe_number(con_row["Costo_Total_Ruta"]) +
                              safe_number(final_row["Costo_Total_Ruta"]))
                utilidad   = ingreso_t - costo_t
                porcentaje = (utilidad / ingreso_t * 100) if ingreso_t > 0 else 0
                label_con  = "Vacío" if tipo_con == "VACIO" else "Dom Mex"
                sugerencias.append({
                    "descripcion": (
                        f"{final_row.get('ID_Ruta','')} | {final_row['Fecha']} — "
                        f"{final_row['Cliente']} ({label_con} → "
                        f"{con_row['Origen']} → {con_row['Destino']}) → "
                        f"{final_row['Destino']} ({porcentaje:.2f}%)"
                    ),
                    "tramos":     [con_row, final_row],
                    "utilidad":   utilidad,
                    "porcentaje": porcentaje,
                })

    # 3) Si principal es VACIO o DOM MEX: buscar import/export desde su destino
    if tipo_principal in tipos_conector:
        rutas_finales = df[
            (df["Tipo"].isin(["IMPORTACION", "EXPORTACION"])) &
            (df["Origen"] == destino_principal)
        ].copy()
        for _, final_row in rutas_finales.iterrows():
            ingreso_t  = safe_number(ruta_principal["Ingreso Total"]) + safe_number(final_row["Ingreso Total"])
            costo_t    = safe_number(ruta_principal["Costo_Total_Ruta"]) + safe_number(final_row["Costo_Total_Ruta"])
            utilidad   = ingreso_t - costo_t
            porcentaje = (utilidad / ingreso_t * 100) if ingreso_t > 0 else 0
            sugerencias.append({
                "descripcion": (
                    f"{final_row.get('ID_Ruta','')} | {final_row['Fecha']} — "
                    f"{final_row['Cliente']} {final_row['Origen']} → "
                    f"{final_row['Destino']} ({porcentaje:.2f}%)"
                ),
                "tramos":     [final_row],
                "utilidad":   utilidad,
                "porcentaje": porcentaje,
            })

    sugerencias = sorted(sugerencias, key=lambda x: x["porcentaje"], reverse=True)

    if not sugerencias:
        alert("warn", "⚠️ No se encontraron combinaciones posibles.")
        return

    st.caption(f"📊 Se encontraron **{len(sugerencias)} combinaciones posibles**")
    descripciones  = [s["descripcion"] for s in sugerencias]
    seleccion_desc = st.selectbox(
        "Selecciona una opción de regreso sugerida",
        descripciones, index=0, key="sel_regreso_sugerido",
    )
    seleccion_obj      = next(s for s in sugerencias if s["descripcion"] == seleccion_desc)
    rutas_seleccionadas = [ruta_principal.to_dict()] + [t.to_dict() for t in seleccion_obj["tramos"]]

    # ── Botón simular ──────────────────────────────────────────────
    divider()
    b1, b2, b3 = st.columns([1, 2, 1])
    with b2:
        if st.button("🚛 Simular Vuelta Redonda", type="primary", use_container_width=True, key="igloo_sim_btn"):
            res = calcular_utilidades_vuelta_redonda(rutas_seleccionadas)
            st.session_state["igloo_sim_resultado"]      = res
            st.session_state["igloo_sim_rutas"]          = rutas_seleccionadas
            st.session_state.igloo_simulacion_realizada  = True
            st.rerun()

    # ── Resultados ─────────────────────────────────────────────────
    if st.session_state.igloo_simulacion_realizada:
        res   = st.session_state.get("igloo_sim_resultado", {})
        rutas = st.session_state.get("igloo_sim_rutas", [])
        divider()
        section_header("📊", "Resumen de Vuelta Redonda")
        for i, r in enumerate(rutas, 1):
            tipo_r   = str(r.get("Tipo", "")).strip().upper()
            ing_r    = safe_number(r.get("Ingreso Total", 0))
            costo_r  = safe_number(r.get("Costo_Total_Ruta", 0))
            ind_r    = calcular_costos_indirectos(tipo_r, ing_r)

            with st.expander(f"{i}. {tipo_r} — {r.get('Cliente', 'N/A')}", expanded=True):
                st.markdown(f"**ID Ruta:** {r.get('ID_Ruta', 'N/A')}")
                st.markdown(f"- Fecha: {r.get('Fecha', 'N/A')}")
                st.markdown(f"- {r.get('Origen','')} → {r.get('Destino','')}")
                st.markdown(f"- Ingreso Total: **${ing_r:,.2f}**")
                st.markdown(f"- Costo Directo Ruta: ${costo_r:,.2f}")
                if ind_r > 0:
                    st.markdown(f"- *Costos Indirectos (35%): ${ind_r:,.2f}*")
                else:
                    st.markdown("- *Costos Indirectos: $0.00 (VACÍO)*")

        # KPIs globales
        divider()
        mostrar_resultados_ruta(res)

        # Detalle completo por columnas
        divider()
        section_header("📋", "Detalle de Rutas")

        tipos_orden = ["IMPORTACION", "VACIO", "EXPORTACION", "DOM MEX"]
        rutas_con_tipo = [r for t in tipos_orden
                          for r in rutas
                          if r.get("Tipo") == t]

        if rutas_con_tipo:
            cols = st.columns(len(rutas_con_tipo))
            for col, ruta in zip(cols, rutas_con_tipo):
                with col:
                    st.markdown(f"**{ruta.get('Tipo', '')}**")
                    st.markdown(f"Fecha: {ruta.get('Fecha', 'N/A')}")
                    st.markdown(f"Cliente: {ruta.get('Cliente', 'N/A')}")
                    st.markdown(f"Ruta: {ruta.get('Origen', 'N/A')} → {ruta.get('Destino', 'N/A')}")
                    st.markdown(f"KM: {safe_number(ruta.get('KM')):,.2f}")
                    st.markdown(f"Ingreso Original: ${safe_number(ruta.get('Ingreso_Original')):,.2f}")
                    st.markdown(f"Moneda: {ruta.get('Moneda', 'N/A')}")
                    st.markdown(f"Tipo de cambio: {safe_number(ruta.get('Tipo de cambio')):,.2f}")
                    st.markdown(f"**Ingreso Flete: ${safe_number(ruta.get('Ingreso Flete')):,.2f}**")
                    st.markdown(f"Cruce Original: ${safe_number(ruta.get('Cruce_Original')):,.2f}")
                    st.markdown(f"**Ingreso Total: ${safe_number(ruta.get('Ingreso Total')):,.2f}**")
                    st.markdown(f"Costo Diesel: ${safe_number(ruta.get('Costo Diesel')):,.2f}")
                    st.markdown(f"Diesel Camión: ${safe_number(ruta.get('Costo_Diesel_Camion')):,.2f}")
                    st.markdown(f"Diesel Termo: ${safe_number(ruta.get('Costo_Diesel_Termo')):,.2f}")
                    st.markdown(f"Sueldo: ${safe_number(ruta.get('Sueldo_Operador')):,.2f}")
                    st.markdown(f"Casetas: ${safe_number(ruta.get('Casetas')):,.2f}")

        # ── PDF ────────────────────────────────────────────────────
        divider()
        section_header("📥", "Descargar PDF de la Simulación")
        b1, b2, b3 = st.columns([1, 2, 1])
        with b2:
            if st.button("📄 Generar PDF Profesional", key="btn_gen_pdf", use_container_width=True):
                try:
                    pdf_path = generar_pdf_vuelta_redonda(
                        rutas,
                        res["ingreso_total"],
                        res["costo_total"],
                        res["utilidad_bruta"],
                        res["costos_indirectos"],
                        res["utilidad_neta"],
                        res["porcentaje_bruta"],
                        res["porcentaje_neta"],
                    )
                    primer_ruta = rutas[0]
                    nombre_pdf   = f"Simulacion_VueltaRedonda_{primer_ruta.get('ID_Ruta', 'SinID')}.pdf"
                    with open(pdf_path, "rb") as f:
                        st.download_button(
                            label="📥 Descargar PDF",
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
                    st.exception(e)
