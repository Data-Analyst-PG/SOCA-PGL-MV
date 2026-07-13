"""
consulta_ruta.py — Cotizador Picus
PDF original personalizado (versión aprobada) +
render() homologado con Igloo / Lincoln:
  - mostrar_resultados_picus() centraliza banner + KPIs + semáforos
  - desglose_ruta() de components.py reemplaza el desglose manual de 3 columnas
  - Simulador de parámetros: diesel, rendimiento Y tipo de cambio (antes solo diesel/rendimiento)
  - Sin cambios en el diseño del PDF (versión aprobada, no se toca)
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
from ui.components import section_header, alert, divider, desglose_ruta

from ._helpers import (
    cargar_datos_generales,
    safe_number,
    safe_float,
    calcular_diesel,
    calcular_utilidades,
    load_rutas_picus,
    filtrar_rutas_picus,
    label_ruta_picus,
    mostrar_resultados_picus,
)


# ─────────────────────────────────────────────
# PDF profesional (mismo estilo que plataforma anterior de Igloo)
# — versión aprobada, NO se toca el diseño —
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

    rend_usado   = rend_sim if simulando and rend_sim else safe_number(ruta.get("Rendimiento Camion", 2.5))
    diesel_usado = diesel_sim if simulando and diesel_sim else safe_number(ruta.get("Costo Diesel", 24.0))

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
         _safe_txt("Rendimiento"), _safe_txt(f"{rend_usado:.2f} km/L")],
        [_safe_txt("Precio Diesel"), _safe_txt(f"${diesel_usado:,.2f}/L"),
         _safe_txt(""),              _safe_txt("")],
    ]
    info_t = Table(info_data, colWidths=[1.1*inch, 2.4*inch, 1.1*inch, 2.4*inch])
    info_t.setStyle(TableStyle([
        ("FONTNAME",      (0, 0), (0, -1),  "Helvetica-Bold"),
        ("FONTNAME",      (2, 0), (2, -1),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
    ]))
    story.append(info_t)
    story.append(Spacer(1, 8))

    # ── Resumen de Utilidades ──────────────────────────────────────
    story.append(Paragraph(_safe_txt("Resumen de Utilidades"), subtitle_s))
    color_un  = colors.HexColor("#28a745") if utilidad_neta >= 0 else colors.HexColor("#dc3545")
    resumen_data = [
        [_safe_txt("Ingreso Total"),      _safe_txt(f"${ingreso_total:,.2f}")],
        [_safe_txt("Costo Directo"),      _safe_txt(f"${costo_total:,.2f}")],
        [_safe_txt("Utilidad Bruta"),     _safe_txt(f"${utilidad_bruta:,.2f} ({pct_bruta:.1f}%)")],
        [_safe_txt("Costos Indirectos"),  _safe_txt(f"${costos_indirectos:,.2f}")],
        [_safe_txt("Utilidad Neta"),      _safe_txt(f"${utilidad_neta:,.2f} ({pct_neta:.1f}%)")],
    ]
    resumen_t = _tabla_2col(resumen_data)
    story.append(resumen_t)
    story.append(Spacer(1, 8))

    # ── Ingresos (con moneda / TC / convertido) ───────────────────
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
            _safe_txt("Extras cobrados"), "", "", "",
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

    # ── Otros Costos (conceptos frecuentes + extras) ──────────────
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
    tc_reg = float(safe_number(
        ruta.get("Tipo de cambio", valores.get("Tipo de cambio USD", 17.5))
    )) or safe_float(valores.get("Tipo de cambio USD", 17.5))

    # ── Simulación — diesel, rendimiento y tipo de cambio ─────────
    divider()
    section_header("⚙️", "Ajustes para Simulación")
    st.caption("Ajusta diesel, rendimiento y/o tipo de cambio para ver el impacto sin modificar la ruta.")

    sim1, sim2, sim3 = st.columns(3)
    costo_diesel_input = sim1.number_input(
        "Costo del Diesel ($/L)",
        value=float(valores.get("Costo Diesel", 24.0)),
        key="pic_cons_diesel",
    )
    rendimiento_input = sim2.number_input(
        "Rendimiento para Simulación (km/L)",
        value=float(rend_reg),
        key="pic_cons_rend",
    )
    tc_input = sim3.number_input(
        "Tipo de Cambio USD/MXP",
        value=float(tc_reg),
        key="pic_cons_tc",
    )
    st.caption(f"Registrados: **{rend_reg:.2f} km/L** · **${valores.get('Costo Diesel', 24.0):,.2f}/L** · **{tc_reg:.2f} MXP/USD**")

    colA, colB = st.columns(2)
    with colA:
        if st.button("🔁 Simular", key="pic_cons_sim"):
            st.session_state["pic_simular"] = True
    with colB:
        if st.button("🔄 Volver a valores reales", key="pic_cons_reset"):
            st.session_state["pic_simular"] = False
            st.rerun()

    simular = st.session_state.get("pic_simular", False)

    # ── Cálculo ──────────────────────────────────────────────────
    km = safe_number(ruta.get("KM", 0))

    moneda_flete       = str(ruta.get("Moneda", "MXP")).strip().upper()
    moneda_cruce       = str(ruta.get("Moneda_Cruce", "MXP")).strip().upper()
    moneda_costo_cruce = str(ruta.get("Moneda Costo Cruce", "MXP")).strip().upper()

    if simular:
        vals_sim = {"Rendimiento Camion": rendimiento_input, "Costo Diesel": costo_diesel_input}
        costo_diesel_camion = calcular_diesel(km, vals_sim)

        ingreso_flete_conv    = safe_number(ruta.get("Ingreso_Original", 0)) * (tc_input if moneda_flete       == "USD" else 1)
        ingreso_cruce_conv    = safe_number(ruta.get("Cruce_Original", 0))   * (tc_input if moneda_cruce       == "USD" else 1)
        costo_cruce_convertido = safe_number(ruta.get("Costo Cruce", 0))    * (tc_input if moneda_costo_cruce == "USD" else 1)

        ingreso_extras = safe_number(ruta.get("Ingresos_Extras", 0))
        ingreso_total  = ingreso_flete_conv + ingreso_cruce_conv + ingreso_extras

        alert("success", "🔧 Ves una **simulación** con diesel/rendimiento/TC ajustados.")
    else:
        costo_diesel_camion = safe_number(ruta.get("Costo_Diesel_Camion", 0))
        costo_cruce_convertido = safe_number(ruta.get("Costo Cruce Convertido", 0))
        ingreso_total = safe_number(ruta.get("Ingreso Total", 0))

    costo_total = (
        costo_diesel_camion
        + safe_number(ruta.get("Sueldo_Operador", 0))
        + safe_number(ruta.get("Bono", 0))
        + safe_number(ruta.get("Casetas", 0))
        + costo_cruce_convertido
        + safe_number(ruta.get("Costos_Fijos", 0))
        + safe_number(ruta.get("Costo_Extras", 0))
    )

    util = calcular_utilidades(ingreso_total, costo_total, tipo_ruta)

    # ── Resultados ───────────────────────────────────────────────
    divider()
    tc_usd = tc_input if simular else safe_float(valores.get("Tipo de cambio USD", 17.5))
    tc_val = tc_usd if moneda_flete == "USD" else 0.0
    mostrar_resultados_picus(util, tc_usd=tc_val)

    # ── Utilidad en USD ────────────────────────────────────────────
    if moneda_flete == "USD":
        tc_guardado = tc_input if simular else safe_number(ruta.get("Tipo de cambio", 0))
        if tc_guardado == 0:
            tc_guardado = safe_float(valores.get("Tipo de cambio USD", 17.5))
        if tc_guardado > 0:
            utilidad_neta_usd = util["utilidad_neta"] / tc_guardado
            st.info(
                f"**💵 Utilidad Neta en USD: ${utilidad_neta_usd:,.2f}**"
                f"  _  (TC: {tc_guardado:.2f} MXP/USD)_"
            )

    # ── Desglose — componente centralizado de ui/components.py ───
    # NOTA: verificar firma real de desglose_ruta() en components.py;
    # se invoca según lo especificado (moneda_mx="MXP", tc, umbral_cd).
    divider()
    with st.expander("📋 Desglose detallado de la ruta", expanded=False):
        desglose_ruta(
            ruta.to_dict(),
            moneda_mx=moneda_flete or "MXP",
            tc=tc_val,
            umbral_cd=util["umbral_cd"],
        )

    # ── PDF ──────────────────────────────────────────────────────
    divider()
    section_header("📥", "Generar PDF de esta Ruta")

    if st.button("📄 Generar PDF", key="pic_cons_pdf"):
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
                        "📥 Descargar PDF",
                        data=f.read(),
                        file_name=nombre,
                        mime="application/pdf",
                        key="pic_cons_dl_pdf",
                    )
                alert("success", "PDF generado exitosamente.")
            except Exception as e:
                alert("error", f"Error al generar PDF: {e}")
