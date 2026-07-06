"""
consulta_ruta.py – Set Logis Plus
Homologado con Lincoln:
  - Sin funciones locales duplicadas — cache, label y filtros vienen de _shared.py
  - mostrar_resultados_setlogis() de _shared — 5 cards + banner + desglose
  - Simulador de PxM con section_header + botones Simular / Resetear (igual que Lincoln)
  - Filtros dentro de st.expander
  - PDF profesional con reportlab

Diferencias Set Logis que se preservan:
  - Simulador ajusta PxM Owner (no MPG/diesel como Lincoln)
  - Fuel_Owner se lee de la ruta guardada y se mantiene en simulación
  - modo_costo_indirecto se lee de la ruta guardada (no hardcodeado)
"""

from __future__ import annotations

import io
from datetime import datetime

import streamlit as st
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from services.supabase_client import get_supabase_client
from ui.components import section_header, alert, divider
from ._shared import (
    TABLE_RUTAS,
    DEFAULTS,
    safe,
    cargar_datos_generales,
    calcular_ruta_setlogis,
    load_rutas_setlogis,
    filtrar_rutas_setlogis,
    label_ruta_setlogis,
    mostrar_resultados_setlogis,
)


# ─────────────────────────────────────────────────────────────────────────────
# PDF CONSULTA INDIVIDUAL — función local, única en este módulo
# ─────────────────────────────────────────────────────────────────────────────
def _generar_pdf_consulta(ruta: dict, r: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
        topMargin=0.5 * inch,  bottomMargin=0.5 * inch,
    )
    styles = getSampleStyleSheet()
    sub_s  = ParagraphStyle("S", parent=styles["Heading2"], fontSize=10,
                             textColor=colors.HexColor("#1B2266"), spaceBefore=10, spaceAfter=3)
    foot_s = ParagraphStyle("F", parent=styles["Normal"], fontSize=7,
                             textColor=colors.HexColor("#6c757d"), alignment=TA_CENTER)
    story  = []

    # Encabezado
    hdr = Table([[
        Paragraph("<b>SET LOGIS PLUS</b>",
                  ParagraphStyle("H",  parent=styles["Normal"], fontSize=13, textColor=colors.white)),
        Paragraph("Consulta Individual de Ruta",
                  ParagraphStyle("HR", parent=styles["Normal"], fontSize=9,
                                 textColor=colors.white, alignment=TA_RIGHT)),
    ]], colWidths=[4.5 * inch, 2.5 * inch])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#1B2266")),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (0,  -1), 12),
        ("RIGHTPADDING",  (-1, 0), (-1, -1), 12),
    ]))
    story += [hdr, Spacer(1, 10)]

    # Datos generales
    story.append(Paragraph("Datos de la Ruta", sub_s))
    fo_label = "Sí ⛽" if ruta.get("Fuel_Owner") else "No"
    gen_data = [
        ["Campo",        "Valor",                            "Campo",          "Valor"],
        ["ID Ruta",      str(ruta.get("ID_Ruta",   "")),    "Fecha",          str(ruta.get("Fecha",      ""))],
        ["Tipo",         str(ruta.get("Tipo_Viaje","")),    "Modo",           str(ruta.get("Modo",       ""))],
        ["Cliente",      str(ruta.get("Cliente",   "")),    "Ruta USA",       str(ruta.get("Ruta_USA",   ""))],
        ["Modalidad",    str(ruta.get("Modalidad", "")),    "Fuel Owner",     fo_label],
        ["Miles Load",   f"{safe(ruta.get('Miles_Load')):.0f}",
         "Short Miles",  f"{safe(ruta.get('Short_Miles')):.0f}"],
        ["Miles Empty",  f"{safe(ruta.get('Miles_Empty')):.0f}",
         "Millas Totales", f"{safe(ruta.get('Millas_Totales')):.0f}"],
    ]
    tbl = Table(gen_data, colWidths=[1.2*inch, 2.0*inch, 1.2*inch, 2.0*inch])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0),  colors.HexColor("#1B2266")),
        ("TEXTCOLOR",      (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",       (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F0F4FF")]),
        ("GRID",           (0, 0), (-1, -1), 0.3, colors.HexColor("#CCCCCC")),
        ("TOPPADDING",     (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
        ("LEFTPADDING",    (0, 0), (-1, -1), 6),
    ]))
    story += [tbl, Spacer(1, 8)]

    # Ingresos
    story.append(Paragraph("Ingresos (USD)", sub_s))
    ing_data = [
        ["Concepto",       "Monto (USD)"],
        ["Flete USA",      f"${safe(r.get('Flete_USA')):,.2f}"],
        ["Fuel",           f"${safe(r.get('Fuel')):,.2f}"],
        ["Ingreso Cruce",  f"${safe(r.get('Ingreso_Cruce')):,.2f}"],
        ["Ingreso MX",     f"${safe(r.get('Ingreso_MX')):,.2f}"],
        ["Extras Ingreso", f"${safe(r.get('Extras_Ingreso')):,.2f}"],
        ["TOTAL",          f"${safe(r.get('Ingreso_Global')):,.2f}"],
    ]
    tbl_ing = Table(ing_data, colWidths=[3.5*inch, 2.5*inch])
    tbl_ing.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0),  (-1, 0),  colors.HexColor("#1B2266")),
        ("TEXTCOLOR",      (0, 0),  (-1, 0),  colors.white),
        ("FONTNAME",       (0, 0),  (-1, 0),  "Helvetica-Bold"),
        ("FONTNAME",       (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0),  (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1),  (-1, -2), [colors.white, colors.HexColor("#F0F4FF")]),
        ("BACKGROUND",     (0, -1), (-1, -1), colors.HexColor("#E8F5E9")),
        ("GRID",           (0, 0),  (-1, -1), 0.3, colors.HexColor("#CCCCCC")),
        ("TOPPADDING",     (0, 0),  (-1, -1), 4),
        ("BOTTOMPADDING",  (0, 0),  (-1, -1), 4),
        ("LEFTPADDING",    (0, 0),  (-1, -1), 6),
    ]))
    story += [tbl_ing, Spacer(1, 8)]

    # Costos
    story.append(Paragraph("Costos Directos (USD)", sub_s))
    cos_data = [
        ["Concepto",        "Monto (USD)"],
        ["Owner Cargado",   f"${safe(r.get('Pago_Owner_Cargado')):,.2f}"],
        ["Owner Vacío",     f"${safe(r.get('Pago_Owner_Vacio')):,.2f}"],
        ["Fuel Owner",      f"${safe(r.get('Pago_Fuel_Owner')):,.2f}"],
        ["Costo Cruce",     f"${safe(r.get('Costo_Cruce')):,.2f}"],
        ["Costo MX",        f"${safe(r.get('Costo_MX')):,.2f}"],
        ["Extras Costo",    f"${safe(r.get('Extras_Costo_Total')):,.2f}"],
        ["Costo Directo",   f"${safe(r.get('Costo_Directo')):,.2f}"],
        ["Costo Indirecto", f"${safe(r.get('Costo_Indirecto')):,.2f}"],
        ["COSTO TOTAL",     f"${safe(r.get('Costo_Total')):,.2f}"],
    ]
    tbl_cos = Table(cos_data, colWidths=[3.5*inch, 2.5*inch])
    tbl_cos.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0),  (-1, 0),  colors.HexColor("#1B2266")),
        ("TEXTCOLOR",      (0, 0),  (-1, 0),  colors.white),
        ("FONTNAME",       (0, 0),  (-1, 0),  "Helvetica-Bold"),
        ("FONTNAME",       (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0),  (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1),  (-1, -2), [colors.white, colors.HexColor("#F0F4FF")]),
        ("BACKGROUND",     (0, -1), (-1, -1), colors.HexColor("#FDECEA")),
        ("GRID",           (0, 0),  (-1, -1), 0.3, colors.HexColor("#CCCCCC")),
        ("TOPPADDING",     (0, 0),  (-1, -1), 4),
        ("BOTTOMPADDING",  (0, 0),  (-1, -1), 4),
        ("LEFTPADDING",    (0, 0),  (-1, -1), 6),
    ]))
    story += [tbl_cos, Spacer(1, 8)]

    # Utilidades
    story.append(Paragraph("Resumen de Utilidades", sub_s))
    ut_data = [
        ["Concepto",        "Monto (USD)",                         "%"],
        ["Ingreso Global",  f"${safe(r.get('Ingreso_Global')):,.2f}", "100.0%"],
        ["Costo Directo",   f"${safe(r.get('Costo_Directo')):,.2f}",
         f"{safe(r.get('Pct_Costo_Directo')):.1f}%"],
        ["Utilidad Bruta",  f"${safe(r.get('Utilidad_Bruta')):,.2f}",
         f"{safe(r.get('Pct_Ut_Bruta')):.1f}%"],
        ["Costo Indirecto", f"${safe(r.get('Costo_Indirecto')):,.2f}",
         f"{safe(r.get('Pct_Costo_Indirecto')):.1f}%"],
        ["UTILIDAD NETA",   f"${safe(r.get('Utilidad_Neta')):,.2f}",
         f"{safe(r.get('Pct_Ut_Neta')):.1f}%"],
    ]
    tbl_ut = Table(ut_data, colWidths=[2.5*inch, 2.0*inch, 1.5*inch])
    tbl_ut.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0),  (-1, 0),  colors.HexColor("#1B2266")),
        ("TEXTCOLOR",      (0, 0),  (-1, 0),  colors.white),
        ("FONTNAME",       (0, 0),  (-1, 0),  "Helvetica-Bold"),
        ("FONTNAME",       (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0),  (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1),  (-1, -2), [colors.white, colors.HexColor("#F0F4FF")]),
        ("BACKGROUND",     (0, -1), (-1, -1), colors.HexColor("#E8F5E9")),
        ("GRID",           (0, 0),  (-1, -1), 0.3, colors.HexColor("#CCCCCC")),
        ("TOPPADDING",     (0, 0),  (-1, -1), 4),
        ("BOTTOMPADDING",  (0, 0),  (-1, -1), 4),
        ("LEFTPADDING",    (0, 0),  (-1, -1), 6),
    ]))
    story += [tbl_ut, Spacer(1, 12)]

    story.append(Paragraph(
        f"Reporte generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} — Set Logis Plus",
        foot_s,
    ))
    doc.build(story)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# RENDER PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────
def render() -> None:
    supabase = get_supabase_client()
    if supabase is None:
        alert("error", "⚠️ Supabase no configurado.")
        return

    # ── Recargar ───────────────────────────────────────────────────────────────
    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("🔄 Recargar", key="sl_cons_reload"):
            load_rutas_setlogis.clear()
            st.rerun()
    with c2:
        st.caption("Carga cacheada 2 min. Usa 'Recargar' si acabas de guardar algo.")

    df = load_rutas_setlogis(TABLE_RUTAS)
    if df.empty:
        alert("info", "ℹ️ No hay rutas guardadas.")
        return

    valores = cargar_datos_generales()

    # ── Filtros dentro de expander (igual que Lincoln) ─────────────────────────
    with st.expander("🔍 Filtros de búsqueda", expanded=False):
        df_fil = filtrar_rutas_setlogis(df, "sl_cons")
    if df_fil.empty:
        alert("warn", "⚠️ No hay rutas con esos filtros.")
        return

    # ── Selector de ruta ───────────────────────────────────────────────────────
    opciones = df_fil["ID_Ruta"].dropna().astype(str).tolist()
    st.caption(f"Rutas disponibles: **{len(opciones)}**")

    idx_sel = st.selectbox(
        "Selecciona la ruta a consultar",
        options=[""] + opciones,
        format_func=lambda i: "— Elige una ruta —" if i == "" else label_ruta_setlogis(
            df_fil[df_fil["ID_Ruta"] == i].iloc[0].to_dict()
        ),
        key="sl_cons_sel",
    )
    if not idx_sel:
        return

    ruta = df_fil[df_fil["ID_Ruta"] == idx_sel].iloc[0].to_dict()

    # ── Simulador de PxM — estructura idéntica a Lincoln ──────────────────────
    tipo_ruta = str(ruta.get("Tipo_Viaje", "NB"))
    modo      = str(ruta.get("Modo", "Individual"))

    divider()
    section_header("⚙️", "Ajustes para Simulación")
    st.caption("Ajusta PxM cargado o vacío para ver el impacto sin modificar la ruta guardada.")

    # Determinar claves de PxM según tipo y modo
    if tipo_ruta in {"SB", "D2DSB"}:
        key_c = "PxM Owner Bajadas Team" if modo == "Team" else "PxM Owner Bajadas"
    else:
        key_c = "PxM Owner Subidas Team" if modo == "Team" else "PxM Owner Subidas"
    key_v = "PxM Owner Vacio Team" if modo == "Team" else "PxM Owner Vacio"

    sc1, sc2 = st.columns(2)
    pxm_cargado_sim = sc1.number_input(
        "PxM Cargado (simulado)",
        value=float(valores.get(key_c, 1.60)),
        step=0.01, format="%.4f", key="sl_cons_sim_pxmc",
    )
    pxm_vacio_sim = sc2.number_input(
        "PxM Vacío (simulado)",
        value=float(valores.get(key_v, 0.80)),
        step=0.01, format="%.4f", key="sl_cons_sim_pxmv",
    )

    b1, b2 = st.columns(2)
    simular  = b1.button("🔁 Simular",        type="primary", use_container_width=True, key="sl_cons_sim_btn")
    resetear = b2.button("↩️ Valores reales", use_container_width=True,               key="sl_cons_sim_reset")

    if simular:
        st.session_state["sl_cons_simulacion"] = True
    if resetear:
        st.session_state["sl_cons_simulacion"] = False

    es_sim   = st.session_state.get("sl_cons_simulacion", False)

    vals_sim = valores.copy()
    if es_sim:
        vals_sim[key_c] = pxm_cargado_sim
        vals_sim[key_v] = pxm_vacio_sim

    # ── Recalcular — lee modo_costo_indirecto y fuel_owner de la ruta guardada
    r = calcular_ruta_setlogis(
        tipo_ruta            = tipo_ruta,
        modo                 = modo,
        ruta_usa             = str(ruta.get("Ruta_USA", "")),
        cliente              = str(ruta.get("Cliente", "")),
        miles_load           = safe(ruta.get("Miles_Load")),
        miles_empty          = safe(ruta.get("Miles_Empty")),
        short_miles          = safe(ruta.get("Short_Miles")),
        flete_usa            = safe(ruta.get("Flete_USA")),
        fuel                 = safe(ruta.get("Fuel")),
        tipo_cruce           = str(ruta.get("Tipo_Cruce",       "Propio")),
        tipo_carga_cruce     = str(ruta.get("Tipo_Carga_Cruce", "Cargado")),
        ingreso_cruce        = safe(ruta.get("Ingreso_Cruce")),
        costo_cruce_externo  = safe(ruta.get("Costo_Cruce")),
        ingreso_mx           = safe(ruta.get("Ingreso_MX")),
        costo_mx             = safe(ruta.get("Costo_MX")),
        extras_ingreso       = safe(ruta.get("Extras_Ingreso")),
        extras_costo         = safe(ruta.get("Extras_Costo")),
        modo_costo_indirecto = str(ruta.get("Modo_Costo_Indirecto", "CXM")),  # ← leído de DB
        valores              = vals_sim if es_sim else valores,
        fuel_owner           = bool(ruta.get("Fuel_Owner", False)),
        incluye_cruce        = bool(ruta.get("Incluye_Cruce", False)),
    )

    # ── Resultados ─────────────────────────────────────────────────────────────
    divider()
    mostrar_resultados_setlogis(
        r,
        modalidad     = str(ruta.get("Modalidad", "Flat")),
        miles_load    = safe(ruta.get("Miles_Load", 0.0)),
        cxm_flete     = safe(ruta.get("CXM_Flete", 0.0)),
        cxm_fuel      = safe(ruta.get("CXM_Fuel",  0.0)),
        es_simulacion = es_sim,
    )

    if ruta.get("Capturado_Por"):
        st.caption(f"👤 Capturado por: **{ruta.get('Capturado_Por')}**")

    # ── PDF ────────────────────────────────────────────────────────────────────
    divider()
    section_header("📥", "Descargar PDF de la Consulta")
    if st.button("📄 Generar PDF", type="primary", key="sl_cons_pdf_btn"):
        try:
            pdf_bytes = _generar_pdf_consulta(ruta, r)
            nombre_pdf = (
                f"Consulta_{ruta.get('ID_Ruta','SL')}_"
                f"{str(ruta.get('Cliente','')).replace(' ','_')}"
                f"_{ruta.get('Fecha','')}"
                + ("_SIM" if es_sim else "") + ".pdf"
            )
            st.download_button(
                label="📥 Descargar PDF",
                data=pdf_bytes,
                file_name=nombre_pdf,
                mime="application/pdf",
                use_container_width=True,
                key="sl_cons_dl_pdf",
            )
        except Exception as ex:
            alert("error", f"❌ Error generando PDF: {ex}")
