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
from ui.components import section_header, alert, divider

from .helpers import (
    cargar_datos_generales,
    safe_number,
    safe_float,
    calcular_diesel,
    calcular_utilidades,
    mostrar_resultados_utilidad,
)


# ─────────────────────────────────────────────
# Cache
# ─────────────────────────────────────────────

@st.cache_data(show_spinner=False, ttl=120)
def _load_rutas_picus_cached() -> pd.DataFrame:
    supabase = get_supabase_client()
    if supabase is None:
        return pd.DataFrame()
    try:
        resp = supabase.table("Rutas_Picus").select("*").order("Fecha", desc=True).execute()
        return pd.DataFrame(resp.data) if resp.data else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


# ─────────────────────────────────────────────
# Filtros y label
# ─────────────────────────────────────────────

def _filtrar_rutas(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    with st.expander("\U0001f50e Filtros de busqueda (opcional)", expanded=False):
        fc1, fc2, fc3, fc4, fc5 = st.columns(5)
        tipos    = ["Todos"] + sorted(df["Tipo"].dropna().unique().tolist())             if "Tipo"    in df.columns else ["Todos"]
        clientes = ["Todos"] + sorted(df["Cliente"].dropna().astype(str).unique().tolist()) if "Cliente" in df.columns else ["Todos"]
        f_tipo   = fc1.selectbox("Tipo",              tipos,    key=f"{prefix}_ftipo")
        f_cli    = fc2.selectbox("Cliente",           clientes, key=f"{prefix}_fcli")
        f_ori    = fc3.text_input("Origen contiene",            key=f"{prefix}_fori")
        f_dest   = fc4.text_input("Destino contiene",           key=f"{prefix}_fdest")
        f_id     = fc5.text_input("ID contiene",                key=f"{prefix}_fid")

    r = df.copy()
    if f_tipo  != "Todos": r = r[r["Tipo"].astype(str) == f_tipo]
    if f_cli   != "Todos": r = r[r["Cliente"].astype(str) == f_cli]
    if f_ori:  r = r[r["Origen"].astype(str).str.upper().str.contains(f_ori.upper(),   na=False)]
    if f_dest: r = r[r["Destino"].astype(str).str.upper().str.contains(f_dest.upper(), na=False)]
    if f_id:   r = r[r["ID_Ruta"].astype(str).str.upper().str.contains(f_id.upper(),   na=False)]
    return r


def _label_ruta(row) -> str:
    return (
        f"{row.get('ID_Ruta','')} | {str(row.get('Fecha',''))[:10]} | "
        f"{row.get('Tipo','')} | {row.get('Cliente','')} | "
        f"{row.get('Origen','')} -> {row.get('Destino','')}"
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
                                spaceBefore=12, spaceAfter=4)
    normal_s   = ParagraphStyle("N", parent=styles["Normal"], fontSize=9, leading=12)
    footer_s   = ParagraphStyle("F", parent=styles["Normal"], fontSize=7,
                                textColor=colors.HexColor("#6c757d"), alignment=TA_CENTER)

    story = []

    # ── Header azul (igual que plataforma anterior) ───────────────
    header_data = [[
        Paragraph(_safe_txt("PICUS"), ParagraphStyle(
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

    # 8 columnas: etiqueta | valor | etiqueta | valor | etiqueta | valor | etiqueta | valor
    # Anchos: etiquetas angostas, valores más anchos
    W = [0.85*inch, 0.95*inch, 0.7*inch, 0.85*inch, 0.85*inch, 0.85*inch, 0.85*inch, 0.85*inch]
    GRIS = colors.HexColor("#f0f2f6")
    GRID_C = colors.HexColor("#dee2e6")

    origen_p  = Paragraph(_safe_txt(str(ruta.get("Origen",  ""))), compact)
    destino_p = Paragraph(_safe_txt(str(ruta.get("Destino", ""))), compact)
    cliente_p = Paragraph(_safe_txt(str(ruta.get("Cliente", ""))), compact)

    info_data = [
        # Fila 1: ID | val | Fecha | val | Tipo | val | Ruta Tipo | val
        [_safe_txt("ID Ruta"),   _safe_txt(str(ruta.get("ID_Ruta",""))),
         _safe_txt("Fecha"),     _safe_txt(str(ruta.get("Fecha",""))[:10]),
         _safe_txt("Tipo"),      _safe_txt(str(ruta.get("Tipo",""))),
         _safe_txt("Ruta Tipo"), _safe_txt(str(ruta.get("Ruta_Tipo","")))],
        # Fila 2: Modo | val | Cliente | val (span 5 cols)
        [_safe_txt("Modo"),      _safe_txt(str(ruta.get("Modo de Viaje",""))),
         _safe_txt("Cliente"),   cliente_p,
         "", "", "", ""],
        # Fila 3: Origen → Destino sin etiqueta (span completo)
        [origen_p, "", "", _safe_txt("->"), destino_p, "", "", ""],
        # Fila 4: KM | val | Pago x KM | val | Rendimiento | val | Costo Diesel | val
        [_safe_txt("KM"),        _safe_txt(f"{safe_number(ruta.get('KM',0)):,.0f}"),
         _safe_txt("Pago x KM"), _safe_txt(f"${safe_number(ruta.get('Pago por KM',0)):,.4f}"),
         _safe_txt("Rendimiento"),_safe_txt(f"{rend_usado:.2f} km/L"),
         _safe_txt("Diesel"),    _safe_txt(f"${diesel_usado:.2f}/L")],
    ]
    info_t = Table(info_data, colWidths=W)
    info_t.setStyle(TableStyle([
        # Fondo gris en columnas de etiqueta (0, 2, 4, 6)
        ("BACKGROUND", (0, 0), (0, -1), GRIS),
        ("BACKGROUND", (2, 0), (2, -1), GRIS),
        ("BACKGROUND", (4, 0), (4, -1), GRIS),
        ("BACKGROUND", (6, 0), (6, -1), GRIS),
        # Negrita en etiquetas
        ("FONTNAME",   (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME",   (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTNAME",   (4, 0), (4, -1), "Helvetica-Bold"),
        ("FONTNAME",   (6, 0), (6, -1), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 7),
        ("GRID",       (0, 0), (-1, -1), 0.5, GRID_C),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        # Fila 2: Cliente ocupa cols 3 a 7
        ("SPAN",  (3, 1), (7, 1)),
        # Fila 3 (origen → destino): origen cols 0-2, flecha col 3, destino cols 4-7
        ("SPAN",  (0, 2), (2, 2)),
        ("SPAN",  (4, 2), (7, 2)),
        ("ALIGN", (3, 2), (3, 2), "CENTER"),
        ("FONTNAME", (0, 2), (7, 2), "Helvetica-Bold"),
        ("BACKGROUND", (0, 2), (7, 2), colors.HexColor("#eef0f8")),
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

    # ── Costos Fijos ─────────────────────────────────────────────
    story.append(Paragraph(_safe_txt("Costos Fijos"), subtitle_s))
    fijos = [
        ("Movimiento Local", "Movimiento_Local"),
        ("Puntualidad",      "Puntualidad"),
        ("Pension",          "Pension"),
        ("Estancia",         "Estancia"),
        ("Fianza",           "Fianza"),
    ]
    fijos_data = [["Concepto", "Monto"]]
    for label, campo in fijos:
        val = safe_number(ruta.get(campo, 0))
        if val > 0:
            fijos_data.append([_safe_txt(label), _safe_txt(f"${val:,.2f}")])
    if len(fijos_data) == 1:
        fijos_data.append([_safe_txt("(Sin costos fijos en esta ruta)"), ""])
    story.append(_tabla_2col(fijos_data))
    story.append(Spacer(1, 8))

    # ── Otros Costos (con columna Cobrado) ───────────────────────
    story.append(Paragraph(_safe_txt("Otros Costos"), subtitle_s))
    extras = [
        ("Pistas Extra",  "Pistas_Extra",  "Pistas_Cobrado"),
        ("Stop",          "Stop",          "Stop_Cobrado"),
        ("Falso",         "Falso",         "Falso_Cobrado"),
        ("Gatas",         "Gatas",         "Gatas_Cobrado"),
        ("Accesorios",    "Accesorios",    "Accesorios_Cobrado"),
        ("Guias",         "Guias",         "Guias_Cobrado"),
    ]
    otros_data = [["Concepto", "Monto", "Cobrado al cliente"]]
    for label, campo, campo_cob in extras:
        val = safe_number(ruta.get(campo, 0))
        if val > 0:
            cob = "Si" if bool(ruta.get(campo_cob, False)) else "No"
            otros_data.append([_safe_txt(label), _safe_txt(f"${val:,.2f}"), _safe_txt(cob)])
    if len(otros_data) == 1:
        otros_data.append([_safe_txt("(Sin costos extras en esta ruta)"), "", ""])
    otros_t = Table(otros_data, colWidths=[2.5*inch, 2.5*inch, 2.2*inch])
    otros_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  AZUL),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 7),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("ALIGN",         (1, 1), (1, -1),  "RIGHT"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
    ]))
    story.append(otros_t)
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
        if st.button("\U0001f504 Recargar rutas", key="pic_cons_reload"):
            _load_rutas_picus_cached.clear()
            st.rerun()
    with rc2:
        st.caption("Carga cacheada 2 min. Usa Recargar si acabas de guardar algo.")

    valores = cargar_datos_generales()
    df      = _load_rutas_picus_cached()

    if df.empty:
        alert("warn", "No hay rutas guardadas todavia.")
        return

    if "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.date
    if "ID_Ruta" in df.columns:
        df.set_index("ID_Ruta", inplace=True, drop=False)

    df_filtrado = _filtrar_rutas(df, "pic_cons")
    if df_filtrado.empty:
        alert("info", "No hay rutas que coincidan con los filtros.")
        return

    st.caption(f"Rutas disponibles: **{len(df_filtrado)}**")
    opciones = df_filtrado.apply(_label_ruta, axis=1).tolist()
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
    section_header("\U0001f4ca", "Resultado de la Ruta")

    tc_usd = safe_float(valores.get("Tipo de cambio USD", 17.5))
    mostrar_resultados_utilidad(
        st,
        ingreso_total, costo_total,
        util["utilidad_bruta"], util["costos_indirectos"],
        util["utilidad_neta"], util["porcentaje_bruta"], util["porcentaje_neta"],
        tipo=tipo_ruta,
        tc_usd=tc_usd if str(ruta.get("Moneda", "")) == "USD" else 0.0,
    )

    # ── Desglose UI ──────────────────────────────────────────────
    divider()
    with st.expander("\U0001f4cb Desglose detallado de la ruta", expanded=False):
        c1, c2, c3 = st.columns(3)

        with c1:
            st.markdown("### \U0001f4cb Informacion General")
            st.caption(f"**ID:** {ruta.get('ID_Ruta','')}")
            st.caption(f"**Fecha:** {str(ruta.get('Fecha',''))[:10]}")
            st.caption(f"**Tipo:** {ruta.get('Tipo','')}")
            st.caption(f"**Ruta Tipo:** {ruta.get('Ruta_Tipo','')}")
            st.caption(f"**Modo de Viaje:** {ruta.get('Modo de Viaje','')}")
            st.caption(f"**Cliente:** {ruta.get('Cliente','')}")
            st.caption(f"**Origen Destino:** {ruta.get('Origen','')} -> {ruta.get('Destino','')}")
            st.caption(f"**KM:** {safe_number(ruta.get('KM')):,.0f}")
            st.caption(f"**Rendimiento:** {rend_reg:.2f} km/L")
            st.caption(f"**Precio Diesel:** ${safe_number(ruta.get('Costo Diesel', 0)):,.2f}/L")

            st.markdown("### \U0001f4b0 Ingresos")
            st.caption(f"**Moneda Flete:** {ruta.get('Moneda','')}")
            st.caption(f"**Ingreso Flete Original:** ${safe_number(ruta.get('Ingreso_Original')):,.2f}")
            st.caption(f"**TC Flete:** {safe_number(ruta.get('Tipo de cambio')):,.4f}")
            st.caption(f"**Ingreso Flete Convertido:** ${safe_number(ruta.get('Ingreso Flete')):,.2f}")
            st.caption(f"**Moneda Cruce:** {ruta.get('Moneda_Cruce','')}")
            st.caption(f"**Ingreso Cruce Original:** ${safe_number(ruta.get('Cruce_Original')):,.2f}")
            st.caption(f"**TC Cruce:** {safe_number(ruta.get('Tipo cambio Cruce')):,.4f}")
            st.caption(f"**Ingreso Cruce Convertido:** ${safe_number(ruta.get('Ingreso Cruce')):,.2f}")
            st.caption(f"**Ingresos Extras:** ${safe_number(ruta.get('Ingresos_Extras')):,.2f}")
            st.caption(f"**Ingreso Total:** ${ingreso_total:,.2f}")

        with c2:
            st.markdown("### \U0001f4c9 Costos Operativos")
            st.caption(f"**Diesel Camion:** ${costo_diesel_camion:,.2f}")
            st.caption(f"**Sueldo Operador:** ${safe_number(ruta.get('Sueldo_Operador')):,.2f}")
            st.caption(f"**Bono ISR/IMSS:** ${safe_number(ruta.get('Bono')):,.2f}")
            st.caption(f"**Casetas:** ${safe_number(ruta.get('Casetas')):,.2f}")
            st.caption(f"**Costo Cruce:** ${safe_number(ruta.get('Costo Cruce')):,.2f}")
            st.caption(f"**Costo Cruce Convertido:** ${safe_number(ruta.get('Costo Cruce Convertido')):,.2f}")

            st.markdown("### \U0001f512 Costos Fijos")
            st.caption(f"**Movimiento Local:** ${safe_number(ruta.get('Movimiento_Local')):,.2f}")
            st.caption(f"**Puntualidad:** ${safe_number(ruta.get('Puntualidad')):,.2f}")
            st.caption(f"**Pension:** ${safe_number(ruta.get('Pension')):,.2f}")
            st.caption(f"**Estancia:** ${safe_number(ruta.get('Estancia')):,.2f}")
            st.caption(f"**Fianza:** ${safe_number(ruta.get('Fianza')):,.2f}")
            st.caption(f"**Total Costos Fijos:** ${safe_number(ruta.get('Costos_Fijos')):,.2f}")

        with c3:
            st.markdown("### \U0001f9fe Otros Costos")
            extras_items = [
                ("Pistas Extra",  "Pistas_Extra",  "Pistas_Cobrado"),
                ("Stop",          "Stop",          "Stop_Cobrado"),
                ("Falso",         "Falso",         "Falso_Cobrado"),
                ("Gatas",         "Gatas",         "Gatas_Cobrado"),
                ("Accesorios",    "Accesorios",    "Accesorios_Cobrado"),
                ("Guias",         "Guias",         "Guias_Cobrado"),
            ]
            for label, campo, campo_cob in extras_items:
                val     = safe_number(ruta.get(campo, 0))
                cobrado = bool(ruta.get(campo_cob, False))
                if val > 0:
                    icono = "cobrado" if cobrado else "costo interno"
                    st.caption(f"**{label}:** ${val:,.2f} _{icono}_")
            st.caption(f"**Total Costo Extras:** ${safe_number(ruta.get('Costo_Extras')):,.2f}")
            st.caption(f"**Total Ingreso Extras:** ${safe_number(ruta.get('Ingresos_Extras')):,.2f}")

            st.markdown("### \U0001f4ca Utilidades")
            st.caption(f"**Costo Total:** ${costo_total:,.2f}")
            st.caption(f"**Utilidad Bruta:** ${util['utilidad_bruta']:,.2f} ({util['porcentaje_bruta']:.1f}%)")
            st.caption(f"**Costos Indirectos:** ${util['costos_indirectos']:,.2f}")
            st.caption(f"**Utilidad Neta:** ${util['utilidad_neta']:,.2f} ({util['porcentaje_neta']:.1f}%)")

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
