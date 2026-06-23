"""
consulta_ruta.py — Cotizador Picus
Diseño homologado con Igloo (plataforma anterior como referencia):
  - Header azul "PICUS — Consulta Individual de Ruta"
  - Datos Generales → Resumen Utilidades → Utilidad en USD (si aplica)
    → Ingresos (con moneda/TC/convertido) → Costos Operativos
    → Costos Fijos → Otros Costos (con columna Cobrado)
  - Desglose UI en expander con st.caption()
  - Simulación via helpers.py
"""
from __future__ import annotations

import tempfile
from datetime import datetime

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from services.supabase_client import get_supabase_client
from ui.components import section_header, alert, divider, mostrar_resultados_ruta, banner_tarifa_sugerida

from .helpers import (
    cargar_datos_generales,
    safe_number,
    safe_float,
    calcular_diesel,
    calcular_utilidades,
    load_rutas_picus,
    filtrar_rutas_picus,
    label_ruta_picus,
)



# ─────────────────────────────────────────────
# PDF profesional (mismo estilo que plataforma anterior de Igloo)
# ─────────────────────────────────────────────

def _safe_txt(text: str) -> str:
    try:
        return str(text).encode("latin-1", "replace").decode("latin-1")
    except Exception:
        return str(text)


def _tabla_2col(data: list, col_w=None) -> Table:
    w = col_w or [3.5 * inch, 3.5 * inch]
    t = Table(data, colWidths=w)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor("#1B2266")),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 7),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("ALIGN",         (1, 1), (-1, -1), "RIGHT"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
    ]))
    return t


def generar_pdf_profesional(
    ruta: dict,
    ingreso_total:     float,
    costo_total:       float,
    utilidad_bruta:    float,
    costos_indirectos: float,
    utilidad_neta:     float,
    pct_bruta:         float,
    pct_neta:          float,
    simulando:         bool  = False,
    rend_sim:          float = 0.0,
    diesel_sim:        float = 0.0,
) -> str:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    doc = SimpleDocTemplate(
        tmp.name, pagesize=letter,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
        topMargin=0.5 * inch,  bottomMargin=0.5 * inch,
    )

    styles     = getSampleStyleSheet()
    AZUL       = colors.HexColor("#1B2266")
    compact    = ParagraphStyle("CC", parent=styles["Normal"], fontSize=7, leading=8)
    subtitle_s = ParagraphStyle("S", parent=styles["Normal"], fontSize=11,
                                fontName="Helvetica-Bold", textColor=AZUL,
                                spaceBefore=8, spaceAfter=2)
    normal_s   = ParagraphStyle("N", parent=styles["Normal"], fontSize=9, leading=10)
    footer_s   = ParagraphStyle("F", parent=styles["Normal"], fontSize=7,
                                textColor=colors.HexColor("#6c757d"), alignment=TA_CENTER)

    story = []

    # ── Header azul (igual que plataforma anterior) ───────────────
    header_data = [[
        Paragraph(_safe_txt("PICUS S. A. DE C. V."), ParagraphStyle(
            "HL", parent=styles["Normal"], fontSize=13, textColor=colors.white,
        )),
        Paragraph(_safe_txt("Consulta Individual de Ruta"), ParagraphStyle(
            "HR", parent=styles["Normal"], fontSize=9,
            textColor=colors.white, alignment=TA_RIGHT,
        )),
    ]]
    header_t = Table(header_data, colWidths=[5.0 * inch, 2.0 * inch])
    header_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), AZUL),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (0, -1),  12),
        ("RIGHTPADDING",  (-1, 0), (-1, -1), 12),
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
    ]))
    story.append(header_t)
    story.append(Spacer(1, 12))

    if simulando:
        story.append(Paragraph(
            _safe_txt("* Este reporte fue generado con valores de simulacion"),
            ParagraphStyle("SN", parent=normal_s, textColor=colors.HexColor("#e67e22")),
        ))
        story.append(Spacer(1, 6))

    # ── Datos Generales ───────────────────────────────────────────
    story.append(Paragraph(_safe_txt("Datos Generales de la Ruta"), subtitle_s))

    rend_usado = rend_sim if simulando and rend_sim else safe_number(ruta.get("Rendimiento Camion", 2.5))
    diesel_usado = diesel_sim if simulando and diesel_sim else safe_number(ruta.get("Costo Diesel", 24.0))

    # Tabla 4 columnas x 6 filas (igual al Excel de referencia)
    # Col 0: etiqueta | Col 1: valor | Col 2: etiqueta | Col 3: valor
    info_data = [
        [_safe_txt("ID Ruta"),     _safe_txt(str(ruta.get("ID_Ruta", ""))),
         _safe_txt("Fecha"),       _safe_txt(str(ruta.get("Fecha", ""))[:10])],
        [_safe_txt("Tipo"),        _safe_txt(str(ruta.get("Tipo", ""))),
         _safe_txt("Ruta Tipo"),   _safe_txt(str(ruta.get("Ruta_Tipo", "")))],
        [_safe_txt("Modo"),        _safe_txt(str(ruta.get("Modo de Viaje", ""))),
         _safe_txt("Cliente"),     Paragraph(_safe_txt(str(ruta.get("Cliente", ""))), compact)],
        [_safe_txt("Origen"),      Paragraph(_safe_txt(str(ruta.get("Origen", ""))), compact),
         _safe_txt("Destino"),     Paragraph(_safe_txt(str(ruta.get("Destino", ""))), compact)],
        [_safe_txt("KM"),          _safe_txt(f"{safe_number(ruta.get('KM', 0)):,.0f}"),
         _safe_txt("Pago x KM"),   _safe_txt(f"${safe_number(ruta.get('Pago por KM', 0)):,.4f}")],
        [_safe_txt("Rendimiento"), _safe_txt(f"{rend_usado:.2f} km/L"),
         _safe_txt("Diesel"),      _safe_txt(f"${diesel_usado:.2f}/L")],
    ]
    info_t = Table(info_data, colWidths=[1.3*inch, 2.2*inch, 1.3*inch, 2.2*inch])
    info_t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f2f6")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f0f2f6")),
        ("FONTNAME",   (0, 0), (0, -1),  "Helvetica-Bold"),
        ("FONTNAME",   (2, 0), (2, -1),  "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 7),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",      (1, 0), (1, -1),  "LEFT"),
        ("ALIGN",      (3, 0), (3, -1),  "LEFT"),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
    ]))
    story.append(info_t)
    story.append(Spacer(1, 10))

    # ── Resumen de Utilidades ────────────────────────────────────
    story.append(Paragraph(_safe_txt("Resumen de Utilidades (MXP)"), subtitle_s))
    color_un   = colors.HexColor("#28a745") if utilidad_neta >= 0 else colors.HexColor("#dc3545")
    pct_costo  = (costo_total / ingreso_total * 100) if ingreso_total else 0
    pct_ind    = (costos_indirectos / ingreso_total * 100) if ingreso_total else 0

    res_data = [
        ["Concepto",          "Valor",                          "%"],
        ["Ingreso Total",     f"${ingreso_total:,.2f} MXP",     "100.00%"],
        ["Costo Directo",     f"${costo_total:,.2f} MXP",       f"{pct_costo:.2f}%"],
        ["Utilidad Bruta",    f"${utilidad_bruta:,.2f} MXP",    f"{pct_bruta:.2f}%"],
        ["Costos Indirectos", f"${costos_indirectos:,.2f} MXP", f"{pct_ind:.2f}%"],
        ["Utilidad Neta",     f"${utilidad_neta:,.2f} MXP",     f"{pct_neta:.2f}%"],
    ]
    res_t = Table(res_data, colWidths=[2.5 * inch, 2.5 * inch, 2.0 * inch])
    res_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  AZUL),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 7),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("ALIGN",         (1, 1), (-1, -1), "RIGHT"),
        ("BACKGROUND",    (0, 5), (-1, 5),  color_un),
        ("TEXTCOLOR",     (0, 5), (-1, 5),  colors.white),
        ("FONTNAME",      (0, 5), (-1, 5),  "Helvetica-Bold"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
    ]))
    story.append(res_t)
    story.append(Spacer(1, 8))

    # ── Utilidad en USD (si flete es USD) ────────────────────────
    moneda_flete = str(ruta.get("Moneda", "MXP")).strip().upper()
    if moneda_flete == "USD":
        tc = safe_number(ruta.get("Tipo de cambio", 0))
        if tc == 0:
            tc = safe_float(cargar_datos_generales().get("Tipo de cambio USD", 17.5))
        if tc > 0:
            ut_usd = utilidad_neta / tc
            story.append(Paragraph(
                _safe_txt("* Utilidad convertida a USD usando el tipo de cambio de esta ruta"),
                ParagraphStyle("NU", parent=normal_s, textColor=colors.HexColor("#6c757d"), fontSize=8),
            ))
            story.append(Spacer(1, 4))
            usd_data = [
                [_safe_txt("Utilidad Neta (USD)"), _safe_txt(f"${ut_usd:,.2f} USD")],
                [_safe_txt("Tipo de Cambio"),      _safe_txt(f"${tc:,.2f} MXP")],
            ]
            usd_t = Table(usd_data, colWidths=[3.5 * inch, 3.5 * inch])
            usd_t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8f4f8")),
                ("FONTNAME",   (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE",   (0, 0), (-1, -1), 7),
                ("GRID",       (0, 0), (-1, -1), 0.5, colors.HexColor("#0d6efd")),
                ("ALIGN",      (1, 0), (1, -1), "RIGHT"),
                ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING",    (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ]))
            story.append(usd_t)
            story.append(Spacer(1, 8))

    # ── Ingresos (con moneda / TC / convertido como Igloo) ───────
    story.append(Paragraph(_safe_txt("Ingresos"), subtitle_s))
    ing_data = [
        ["Concepto", "Moneda", "Original", "Tipo Cambio", "Convertido (MXP)"],
        [
            _safe_txt("Flete"),
            _safe_txt(str(ruta.get("Moneda", ""))),
            _safe_txt(f"${safe_number(ruta.get('Ingreso_Original', 0)):,.2f}"),
            _safe_txt(f"{safe_number(ruta.get('Tipo de cambio', 0)):,.2f}"),
            _safe_txt(f"${safe_number(ruta.get('Ingreso Flete', 0)):,.2f}"),
        ],
        [
            _safe_txt("Cruce"),
            _safe_txt(str(ruta.get("Moneda_Cruce", ""))),
            _safe_txt(f"${safe_number(ruta.get('Cruce_Original', 0)):,.2f}"),
            _safe_txt(f"{safe_number(ruta.get('Tipo cambio Cruce', 0)):,.2f}"),
            _safe_txt(f"${safe_number(ruta.get('Ingreso Cruce', 0)):,.2f}"),
        ],
    ]
    if safe_number(ruta.get("Ingresos_Extras", 0)) > 0:
        ing_data.append([
            _safe_txt("Extras cobrados"), "", "",  "",
            _safe_txt(f"${safe_number(ruta.get('Ingresos_Extras', 0)):,.2f}"),
        ])
    ing_t = Table(ing_data, colWidths=[1.2*inch, 0.8*inch, 1.4*inch, 1.2*inch, 1.6*inch])
    ing_t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 7),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("ALIGN",      (2, 1), (-1, -1), "RIGHT"),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
    ]))
    story.append(ing_t)
    story.append(Spacer(1, 8))

    # ── Costos Operativos ────────────────────────────────────────
    story.append(Paragraph(_safe_txt("Costos Operativos"), subtitle_s))
    cos_data = [
        ["Concepto", "Monto"],
        [_safe_txt(f"Diesel Camion ({rend_usado:.2f} km/L)"),
         _safe_txt(f"${safe_number(ruta.get('Costo_Diesel_Camion', 0)):,.2f}")],
        [_safe_txt("Sueldo Operador"),
         _safe_txt(f"${safe_number(ruta.get('Sueldo_Operador', 0)):,.2f}")],
        [_safe_txt("Bono ISR/IMSS"),
         _safe_txt(f"${safe_number(ruta.get('Bono', 0)):,.2f}")],
        [_safe_txt("Casetas"),
         _safe_txt(f"${safe_number(ruta.get('Casetas', 0)):,.2f}")],
        [_safe_txt("Costo Cruce"),
         _safe_txt(f"${safe_number(ruta.get('Costo Cruce Convertido', 0)):,.2f}")],
    ]
    story.append(_tabla_2col(cos_data))
    story.append(Spacer(1, 8))

    # ── Otros Costos (conceptos frecuentes + extras) igual que Igloo
    story.append(Paragraph(_safe_txt("Otros Costos"), subtitle_s))
    otros_data = [["Concepto", "Monto"]]

    for label, campo in [
        ("Puntualidad",      "Puntualidad"),
        ("Movimiento Local", "Movimiento_Local"),
        ("Pension",          "Pension"),
        ("Estancia",         "Estancia"),
        ("Fianza",           "Fianza"),
    ]:
        val = safe_number(ruta.get(campo, 0))
        if val > 0:
            otros_data.append([_safe_txt(label), _safe_txt(f"${val:,.2f}")])

    for label, campo, campo_cob in [
        ("Pistas Extra", "Pistas_Extra", "Pistas_Cobrado"),
        ("Stop",         "Stop",         "Stop_Cobrado"),
        ("Falso",        "Falso",        "Falso_Cobrado"),
        ("Gatas",        "Gatas",        "Gatas_Cobrado"),
        ("Accesorios",   "Accesorios",   "Accesorios_Cobrado"),
        ("Guias",        "Guias",        "Guias_Cobrado"),
    ]:
        val = safe_number(ruta.get(campo, 0))
        if val > 0:
            cob_txt = " (cobrado)" if bool(ruta.get(campo_cob, False)) else ""
            otros_data.append([_safe_txt(f"{label}{cob_txt}"), _safe_txt(f"${val:,.2f}")])

    if len(otros_data) == 1:
        otros_data.append([_safe_txt("(Sin costos extras en esta ruta)"), ""])

    story.append(_tabla_2col(otros_data))
    story.append(Spacer(1, 20))

    # ── Footer ───────────────────────────────────────────────────
    story.append(Paragraph(
        _safe_txt(
            f"Reporte generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} "
            f"-- Picus" + (" (SIMULACION)" if simulando else "")
        ),
        footer_s,
    ))

    doc.build(story)
    return tmp.name


# ─────────────────────────────────────────────
# Render principal
# ─────────────────────────────────────────────

def render() -> None:
    supabase = get_supabase_client()
    if supabase is None:
        alert("error", "Supabase no configurado.")
        return

    rc1, rc2 = st.columns([1, 4])
    with rc1:
        if st.button("🔄 Recargar rutas", key="pic_cons_reload"):
            load_rutas_picus.clear()
            st.rerun()
    with rc2:
        st.caption("Carga cacheada 2 min. Usa Recargar si acabas de guardar algo.")

    valores = cargar_datos_generales()
    df      = load_rutas_picus()

    if df.empty:
        alert("warn", "No hay rutas guardadas todavia.")
        return

    if "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.date
    if "ID_Ruta" in df.columns:
        df.set_index("ID_Ruta", inplace=True, drop=False)

    df_filtrado = filtrar_rutas_picus(df, "pic_cons")
    if df_filtrado.empty:
        alert("info", "No hay rutas que coincidan con los filtros.")
        return

    st.caption(f"Rutas disponibles: **{len(df_filtrado)}**")
    opciones = [label_ruta_picus(row) for _, row in df_filtrado.iterrows()]
    sel      = st.selectbox("Selecciona la ruta a consultar", opciones, key="pic_cons_sel")
    if not sel:
        return

    idx       = opciones.index(sel)
    ruta      = df_filtrado.iloc[idx]
    tipo_ruta = str(ruta.get("Tipo", "")).strip().upper()

    rend_reg = float(safe_number(
        ruta.get("Rendimiento Camion", valores.get("Rendimiento Camion", 2.5))
    ))

    # ── Simulacion ───────────────────────────────────────────────
    divider()
    section_header("\u2699\ufe0f", "Ajustes para Simulacion")
    st.caption("Ajusta diesel y rendimiento para ver el impacto sin modificar la ruta.")

    sim1, sim2 = st.columns(2)
    costo_diesel_input = sim1.number_input(
        "Costo del Diesel ($/L)",
        value=float(valores.get("Costo Diesel", 24.0)),
        key="pic_cons_diesel",
    )
    st.markdown(f"> Rendimiento registrado: **{rend_reg:.2f} km/L**")
    rendimiento_input = sim2.number_input(
        "Rendimiento para Simulacion (km/L)",
        value=float(rend_reg),
        key="pic_cons_rend",
    )

    colA, colB = st.columns(2)
    with colA:
        if st.button("\U0001f501 Simular", key="pic_cons_sim"):
            st.session_state["pic_simular"] = True
    with colB:
        if st.button("\U0001f504 Volver a valores reales", key="pic_cons_reset"):
            st.session_state["pic_simular"] = False
            st.rerun()

    simular = st.session_state.get("pic_simular", False)

    # ── Calculo ──────────────────────────────────────────────────
    ingreso_total = safe_number(ruta.get("Ingreso Total", 0))
    km            = safe_number(ruta.get("KM", 0))

    if simular:
        vals_sim = {"Rendimiento Camion": rendimiento_input, "Costo Diesel": costo_diesel_input}
        costo_diesel_camion = calcular_diesel(km, vals_sim)
        alert("success", "\U0001f527 Ves una **simulacion** con diesel/rendimiento ajustados.")
    else:
        costo_diesel_camion = safe_number(ruta.get("Costo_Diesel_Camion", 0))

    costo_total = (
        costo_diesel_camion
        + safe_number(ruta.get("Sueldo_Operador", 0))
        + safe_number(ruta.get("Bono", 0))
        + safe_number(ruta.get("Casetas", 0))
        + safe_number(ruta.get("Costo Cruce Convertido", 0))
        + safe_number(ruta.get("Costos_Fijos", 0))
        + safe_number(ruta.get("Costo_Extras", 0))
    )

    util = calcular_utilidades(ingreso_total, costo_total, tipo_ruta)

    # ── Resultados ───────────────────────────────────────────────
    divider()
    tc_usd      = safe_float(valores.get("Tipo de cambio USD", 17.5))
    tc_val      = tc_usd if str(ruta.get("Moneda", "")) == "USD" else 0.0
    _umbral     = util["umbral_cd"]
    _tarifa_sug = util["costo_directo"] / (_umbral / 100)
    _tarifa_usd = (_tarifa_sug / tc_val) if tc_val > 0 else 0.0
    banner_tarifa_sugerida(util["costo_directo"], ingreso_total, _umbral, "MXP", _tarifa_usd)
    mostrar_resultados_ruta(util, titulo="Resultado de la Ruta")
  
    # ── Utilidad en USD (igual que Igloo) ────────────────────────
    moneda_flete = str(ruta.get("Moneda", "MXP")).strip().upper()
    if moneda_flete == "USD":
        tc_guardado = safe_number(ruta.get("Tipo de cambio", 0))
        if tc_guardado == 0:
            tc_guardado = safe_float(valores.get("Tipo de cambio USD", 17.5))
        if tc_guardado > 0:
            utilidad_neta_usd = util["utilidad_neta"] / tc_guardado
            st.info(
                f"**💵 Utilidad Neta en USD: ${utilidad_neta_usd:,.2f}**"
                f"  _  (TC: {tc_guardado:.2f} MXP/USD)_"
            )

    # ── Desglose UI — 3 columnas igual a Igloo ───────────────────
    divider()
    with st.expander("📋 Desglose detallado de la ruta", expanded=False):
        c1, c2, c3 = st.columns(3)

        # COL 1 — Información General
        with c1:
            st.markdown("### 📋 Información General")
            st.write(f"**Fecha:** {str(ruta.get('Fecha',''))[:10]}")
            st.write(f"**ID de Ruta:** {ruta.get('ID_Ruta','')}")
            st.write(f"**Tipo:** {ruta.get('Tipo','')}")
            st.write(f"**Ruta Tipo:** {ruta.get('Ruta_Tipo','')}")
            st.write(f"**Modo:** {ruta.get('Modo de Viaje','')}")
            st.write(f"**Cliente:** {ruta.get('Cliente','')}")
            st.write(f"**Origen → Destino:** {ruta.get('Origen','')} → {ruta.get('Destino','')}")
            st.write(f"**KM:** {safe_number(ruta.get('KM')):,.0f}")
            st.write(f"**Rendimiento Camión:** {rend_reg:.2f} km/L")
            st.write(f"**Precio Diesel:** ${safe_number(ruta.get('Costo Diesel', 0)):,.2f}/L")

        # COL 2 — Ingresos
        with c2:
            st.markdown("### 💰 Ingresos")
            st.write(f"**Moneda Flete:** {ruta.get('Moneda','')}")
            st.write(f"**Ingreso Flete Original:** ${safe_number(ruta.get('Ingreso_Original')):,.2f}")
            st.write(f"**Tipo de cambio:** {safe_number(ruta.get('Tipo de cambio')):,.2f}")
            st.write(f"**Ingreso Flete Convertido:** ${safe_number(ruta.get('Ingreso Flete')):,.2f}")
            st.write(f"**Moneda Cruce:** {ruta.get('Moneda_Cruce','')}")
            st.write(f"**Ingreso Cruce Original:** ${safe_number(ruta.get('Cruce_Original')):,.2f}")
            st.write(f"**Ingreso Cruce Convertido:** ${safe_number(ruta.get('Ingreso Cruce')):,.2f}")
            st.write(f"**Costo Cruce Convertido:** ${safe_number(ruta.get('Costo Cruce Convertido')):,.2f}")
            st.write(f"**Ingreso Total:** ${ingreso_total:,.2f}")

        # COL 3 — Costos Directos (operativos + conceptos de costos + otros cobrados)
        with c3:
            st.markdown("### 📉 Costos Directos")
            st.write(f"**Diesel Camión:** ${costo_diesel_camion:,.2f}")
            st.write(f"**Sueldo Operador:** ${safe_number(ruta.get('Sueldo_Operador')):,.2f}")
            st.write(f"**Bono ISR/IMSS:** ${safe_number(ruta.get('Bono')):,.2f}")
            st.write(f"**Casetas:** ${safe_number(ruta.get('Casetas')):,.2f}")
            st.write(f"**Costo Cruce:** ${safe_number(ruta.get('Costo Cruce Convertido')):,.2f}")

            # Conceptos de costos frecuentes (todos van al costo)
            conceptos_costos = {
                "Movimiento Local": safe_number(ruta.get("Movimiento_Local", 0)),
                "Puntualidad":      safe_number(ruta.get("Puntualidad", 0)),
                "Pension":          safe_number(ruta.get("Pension", 0)),
                "Estancia":         safe_number(ruta.get("Estancia", 0)),
                "Fianza":           safe_number(ruta.get("Fianza", 0)),
            }
            for label, val in conceptos_costos.items():
                if val > 0:
                    st.write(f"**{label}:** ${val:,.2f}")

            # Otros costos (cobrados o no)
            extras_items = [
                ("Pistas Extra", "Pistas_Extra", "Pistas_Cobrado"),
                ("Stop",         "Stop",         "Stop_Cobrado"),
                ("Falso",        "Falso",        "Falso_Cobrado"),
                ("Gatas",        "Gatas",        "Gatas_Cobrado"),
                ("Accesorios",   "Accesorios",   "Accesorios_Cobrado"),
                ("Guias",        "Guias",        "Guias_Cobrado"),
            ]
            for label, campo, campo_cob in extras_items:
                val     = safe_number(ruta.get(campo, 0))
                cobrado = bool(ruta.get(campo_cob, False))
                if val > 0:
                    sufijo = " _(cobrado al cliente)_" if cobrado else ""
                    st.write(f"**{label}:** ${val:,.2f}{sufijo}")

    # ── PDF ──────────────────────────────────────────────────────
    divider()
    section_header("\U0001f4e5", "Generar PDF de esta Ruta")

    if st.button("\U0001f4c4 Generar PDF", key="pic_cons_pdf"):
        with st.spinner("Generando PDF..."):
            try:
                pdf_path = generar_pdf_profesional(
                    ruta.to_dict(),
                    ingreso_total, costo_total,
                    util["utilidad_bruta"], util["costos_indirectos"],
                    util["utilidad_neta"], util["porcentaje_bruta"], util["porcentaje_neta"],
                    simulando=simular,
                    rend_sim=rendimiento_input,
                    diesel_sim=costo_diesel_input,
                )
                nombre = (
                    f"Consulta_{ruta.get('Cliente','Picus')}_{ruta.get('Origen','')}_{ruta.get('Destino','')}"
                    .replace("/", "-").replace(" ", "_") +
                    ("_SIM" if simular else "") + ".pdf"
                )
                with open(pdf_path, "rb") as f:
                    st.download_button(
                        "\U0001f4e5 Descargar PDF",
                        data=f.read(),
                        file_name=nombre,
                        mime="application/pdf",
                        key="pic_cons_dl_pdf",
                    )
                alert("success", "PDF generado exitosamente.")
            except Exception as e:
                alert("error", f"Error al generar PDF: {e}")
