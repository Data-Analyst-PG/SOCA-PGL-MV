"""
simulador.py – Lincoln Freight (USA/MX)
Simulador de Vuelta Redonda — homologado con Igloo y Picus.

Flujo:
  Paso 1 → Selecciona ruta principal (NB / SB / D2DNB / D2DSB)
  Paso 2 → Sugerencias de regreso ordenadas por % Ut. Bruta combinada
            Candidatas: directas (sin empty) o con empty como puente
  Paso 3 → Botón "Simular" → resumen con banner_tarifa_sugerida + mostrar_resultados_ruta
  Paso 4 → Detalle de cada tramo en expanders
  Paso 5 → Descarga PDF

Modelo geográfico del road trip:
  _primer_punto:
    D2DNB → Origen_MX  (viene de México)
    otros → Origen (Origen_USA)

  _ultimo_punto:
    D2DSB → Destino_MX (termina en México)
    otros → Destino (Destino_USA)

  Tipos de regreso compatibles:
    NB    → SB, D2DSB
    SB    → NB, D2DNB
    D2DNB → SB, D2DSB
    D2DSB → NB, D2DNB

  Empty: siempre solo americana.
"""

from __future__ import annotations

import io
from datetime import datetime

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from services.supabase_client import get_supabase_client
from ui.components import (
    section_header, alert, divider,
)
from ._shared import (
    TABLE_RUTAS,
    UMBRAL_CD,
    UMBRAL_UB,
    UMBRAL_CI,
    UMBRAL_UN,
    DEFAULTS,
    safe,
    cargar_datos_generales,
    load_rutas_lincoln,
    label_ruta_lincoln,
    mostrar_resultados_lincoln,
)

TIPOS_PRINCIPAL = {"NB", "SB", "D2DNB", "D2DSB"}
TIPO_EMPTY      = "Empty"

_REGRESO: dict[str, set] = {
    "NB":    {"SB",  "D2DSB"},
    "SB":    {"NB",  "D2DNB"},
    "D2DNB": {"SB",  "D2DSB"},
    "D2DSB": {"NB",  "D2DNB"},
}


# ─────────────────────────────────────────────
# HELPERS GEOGRÁFICOS
# ─────────────────────────────────────────────
def _get(ruta, key: str) -> str:
    v = ruta.get(key, "") if hasattr(ruta, "get") else ""
    return str(v).strip().upper() if v else ""


def _primer_punto(ruta) -> str:
    """De dónde sale la ruta. D2DNB sale de Origen_MX; el resto de Origen."""
    if _get(ruta, "Tipo") == "D2DNB":
        return _get(ruta, "Origen_MX") or _get(ruta, "Origen")
    return _get(ruta, "Origen")


def _ultimo_punto(ruta) -> str:
    """Dónde termina la ruta. D2DSB termina en Destino_MX; el resto en Destino."""
    if _get(ruta, "Tipo") == "D2DSB":
        return _get(ruta, "Destino_MX") or _get(ruta, "Destino")
    return _get(ruta, "Destino")


# ─────────────────────────────────────────────
# SUGERENCIAS DE CANDIDATAS
# ─────────────────────────────────────────────
def _sugerir_candidatas(df: pd.DataFrame, ruta_p: pd.Series) -> list[dict]:
    """
    Devuelve lista de candidatas de regreso ordenadas por Ut. Bruta combinada.
    Cada candidata: {label, ruta_e, ruta_r, ut_bruta, pct_ut_bruta}
    """
    tipo_p   = _get(ruta_p, "Tipo")
    fin_p    = _ultimo_punto(ruta_p)
    tipos_ok = _REGRESO.get(tipo_p, set())

    df_cand = df[df["Tipo"].isin(tipos_ok)].copy()
    if df_cand.empty:
        return []

    ub_p = safe(ruta_p.get("Utilidad_Bruta", 0))
    candidatas = []

    for _, r in df_cand.iterrows():
        inicio_r = _primer_punto(r)
        if inicio_r == fin_p:
            # Candidata directa
            ub_r    = safe(r.get("Utilidad_Bruta", 0))
            ub_comb = ub_p + ub_r
            ing_comb = safe(ruta_p.get("Ingreso_Total", 0)) + safe(r.get("Ingreso_Total", 0))
            pct_comb = (ub_comb / ing_comb * 100) if ing_comb else 0.0
            candidatas.append({
                "label":        (
                    f"✅ DIRECTO · {r.get('ID_Ruta','')} · {_get(r,'Tipo')} · "
                    f"{r.get('Cliente','—')} · {_get(r,'Origen')} → {_get(r,'Destino')} · "
                    f"Ut.B {pct_comb:.1f}%"
                ),
                "ruta_e":       None,
                "ruta_r":       r.to_dict(),
                "ut_bruta":     ub_comb,
                "pct_ut_bruta": pct_comb,
            })
        else:
            # Buscar empty como puente
            df_empty = df[df["Tipo"] == TIPO_EMPTY].copy()
            for _, e in df_empty.iterrows():
                inicio_e = _primer_punto(e)
                fin_e    = _ultimo_punto(e)
                if inicio_e == fin_p and fin_e == inicio_r:
                    ub_e    = safe(e.get("Utilidad_Bruta", 0))
                    ub_r    = safe(r.get("Utilidad_Bruta", 0))
                    ub_comb = ub_p + ub_e + ub_r
                    ing_comb = (
                        safe(ruta_p.get("Ingreso_Total", 0))
                        + safe(e.get("Ingreso_Total", 0))
                        + safe(r.get("Ingreso_Total", 0))
                    )
                    pct_comb = (ub_comb / ing_comb * 100) if ing_comb else 0.0
                    candidatas.append({
                        "label": (
                            f"⬜ VACÍO · {e.get('ID_Ruta','')} → "
                            f"{r.get('ID_Ruta','')} · {_get(r,'Tipo')} · "
                            f"{r.get('Cliente','—')} · Ut.B {pct_comb:.1f}%"
                        ),
                        "ruta_e":       e.to_dict(),
                        "ruta_r":       r.to_dict(),
                        "ut_bruta":     ub_comb,
                        "pct_ut_bruta": pct_comb,
                    })

    candidatas.sort(key=lambda x: x["pct_ut_bruta"], reverse=True)
    return candidatas


# ─────────────────────────────────────────────
# RESUMEN VR
# ─────────────────────────────────────────────
def _resumen_vr(rutas: list[pd.Series], valores: dict | None = None) -> dict:
    from ._shared import UMBRAL_CD, UMBRAL_UB, UMBRAL_CI, UMBRAL_UN
    valores = valores or {}
    ing = sum(safe(r.get("Ingreso_Total",       0)) for r in rutas)
    cd  = sum(safe(r.get("Costo_Directo_Total", 0)) for r in rutas)
    ub  = sum(safe(r.get("Utilidad_Bruta",      0)) for r in rutas)
    ci  = sum(safe(r.get("Costos_Indirectos",   0)) for r in rutas)
    un  = sum(safe(r.get("Utilidad_Neta",       0)) for r in rutas)
    mi  = sum(safe(r.get("Miles_Load",  0) or r.get("Millas_USA",    0)) for r in rutas)
    mv  = sum(safe(r.get("Miles_Empty", 0) or r.get("Millas_Vacias", 0)) for r in rutas)

    def _pct(n, d): return (n / d * 100) if d > 0 else 0.0
    pct_cd = _pct(cd, ing)
    pct_ci = _pct(ci, ing)
    pct_ub = _pct(ub, ing)
    pct_un = _pct(un, ing)

    return {
        # Alias canónicos — requeridos por mostrar_resultados_ruta()
        "ingreso_total":       ing,
        "costo_directo":       cd,
        "utilidad_bruta":      ub,
        "costos_indirectos":   ci,
        "utilidad_neta":       un,
        "moneda_display":      "USD",
        # Porcentajes para sub-labels de las cards
        "Pct_Costo_Directo":   pct_cd,
        "Pct_Ut_Bruta":        pct_ub,
        "Pct_Costo_Indirecto": pct_ci,
        "Pct_Ut_Neta":         pct_un,
        # Colores con umbrales Lincoln
        "Color_Directo":   "#059669" if pct_cd <= 50.0 else "#DC2626",
        "Color_Indirecto": "#059669" if pct_ci <= 35.0 else "#D97706",
        "Color_Ut_Neta":   "#059669" if pct_un >= 15.0 else "#DC2626",
        # Umbrales viajan en el dict
        "umbral_cd": 50.0,
        "umbral_ub": 50.0,
        "umbral_ci": 35.0,
        "umbral_un": 15.0,
        # Campos extra para PDF
        "ing": ing, "cd": cd, "ub": ub, "ci": ci, "un": un,
        "mi": mi,   "mv": mv,
        "pct_cd": pct_cd, "pct_ci": pct_ci,
        "pct_ub": pct_ub, "pct_un": pct_un,
        "ml_total": mi + mv,
    }

# ─────────────────────────────────────────────
# VISUAL DE NODOS DE RUTA
# ─────────────────────────────────────────────
def _ruta_visual(ruta_p: pd.Series, ruta_e: pd.Series | None, ruta_r: pd.Series | None) -> None:
    def nodo(icono: str, lugar: str, etiq: str) -> str:
        lugar = lugar or "—"
        return (
            f'<div style="text-align:center;min-width:80px">'
            f'<div style="font-size:1.4rem">{icono}</div>'
            f'<div style="font-size:0.7rem;font-weight:700;color:#1B2266">{lugar}</div>'
            f'<div style="font-size:0.6rem;color:#6c757d">{etiq}</div>'
            f'</div>'
        )
    flecha = '<div style="font-size:1.2rem;color:#adb5bd;padding:0 4px">→</div>'

    tipo_p = _get(ruta_p, "Tipo")
    pasos  = []

    if tipo_p == "D2DNB":
        pasos.append(nodo("🇲🇽", _get(ruta_p, "Origen_MX"), "Origen MX"))
        pasos.append(flecha)
    pasos.append(nodo("🚦", _get(ruta_p, "Origen"), "Inicio USA"))
    pasos.append(flecha)
    pasos.append(nodo("🚛", _get(ruta_p, "Destino"), f"Destino ({tipo_p})"))
    if tipo_p == "D2DSB" and _get(ruta_p, "Destino_MX"):
        pasos += [flecha, nodo("🇲🇽", _get(ruta_p, "Destino_MX"), "Destino MX")]

    if ruta_e is not None:
        pasos += [
            flecha,
            nodo("⬜", _get(ruta_e, "Origen"), "Vacío Origen"),
            flecha,
            nodo("⬜", _get(ruta_e, "Destino"), "Vacío Destino"),
        ]

    if ruta_r is not None:
        tipo_r = _get(ruta_r, "Tipo")
        pasos += [
            flecha,
            nodo("🔁", _get(ruta_r, "Origen"), f"Regreso ({tipo_r})"),
            flecha,
            nodo("🏁", _get(ruta_r, "Destino"), "Destino Final"),
        ]
        if tipo_r == "D2DSB" and _get(ruta_r, "Destino_MX"):
            pasos += [flecha, nodo("🇲🇽", _get(ruta_r, "Destino_MX"), "Destino MX Reg.")]

    html = (
        '<div style="display:flex;flex-wrap:wrap;align-items:center;'
        'gap:4px;padding:12px;background:#f8f9fa;border-radius:8px;'
        'border:1px solid #dee2e6">' + "".join(pasos) + "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


# ─────────────────────────────────────────────
# DETALLE DE TRAMOS
# ─────────────────────────────────────────────
def _detalle_tramos(rutas: list[pd.Series], etiquetas: list[str]) -> None:
    divider()
    section_header("📋", "Detalle por Tramo")
    for ruta, etiq in zip(rutas, etiquetas):
        ub    = safe(ruta.get("Utilidad_Bruta",      0))
        pct   = safe(ruta.get("Pct_Utilidad_Bruta",  0))
        un    = safe(ruta.get("Utilidad_Neta",        0))
        color_n = "#28a745" if un >= 0 else "#dc3545"
        with st.expander(
            f"{etiq} · {ruta.get('ID_Ruta','')} | {ruta.get('Cliente','—')} | "
            f"{_get(ruta,'Origen')} → {_get(ruta,'Destino')} | "
            f"Ut.B ${ub:,.2f} ({pct:.1f}%)",
            expanded=False,
        ):
            c1, c2, c3 = st.columns(3)
            c1.caption(f"**Tipo:** {_get(ruta,'Tipo')}")
            c1.caption(f"**Cliente:** {ruta.get('Cliente','—')}")
            c1.caption(f"**Fecha:** {ruta.get('Fecha','—')}")
            c1.caption(f"**Modo:** {ruta.get('Modo_Viaje','—')}")
            miles_l = safe(ruta.get("Miles_Load",  0) or ruta.get("Millas_USA",    0))
            miles_e = safe(ruta.get("Miles_Empty", 0) or ruta.get("Millas_Vacias", 0))
            c2.caption(f"**Miles Load:** {miles_l:,.0f} mi")
            c2.caption(f"**Miles Empty:** {miles_e:,.0f} mi")
            c2.caption(f"**Ingreso:** ${safe(ruta.get('Ingreso_Total')):,.2f}")
            c2.caption(f"**Costo Directo:** ${safe(ruta.get('Costo_Directo_Total')):,.2f}")
            c3.caption(f"**Ut. Bruta:** ${ub:,.2f} ({pct:.1f}%)")
            c3.caption(f"**Costos Ind.:** ${safe(ruta.get('Costos_Indirectos')):,.2f}")
            c3.markdown(
                f'<span style="color:{color_n}">**Ut. Neta: ${un:,.2f} '
                f"({safe(ruta.get('Pct_Utilidad_Neta')):.1f}%)**</span>",
                unsafe_allow_html=True,
            )
            if _get(ruta, "Origen_MX") or _get(ruta, "Destino_MX"):
                st.caption(
                    f"🇲🇽 Tramo MX: {_get(ruta,'Origen_MX')} → {_get(ruta,'Destino_MX')} "
                    f"· Línea: {ruta.get('Linea_MX','—')}"
                )


# ─────────────────────────────────────────────
# PDF
# ─────────────────────────────────────────────
def _generar_pdf(
    rutas:     list[pd.Series],
    etiquetas: list[str],
    res:       dict,
    ruta_p:    pd.Series,
    ruta_e:    pd.Series | None,
    ruta_r:    pd.Series | None,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
    )
    styles  = getSampleStyleSheet()
    AZUL    = colors.HexColor("#1B2266")
    AZUL_L  = colors.HexColor("#dee6f5")
    GRIS    = colors.HexColor("#f5f5f5")
    title_s = ParagraphStyle("T",  parent=styles["Title"],   fontSize=14,
                              textColor=AZUL, spaceAfter=4)
    sub_s   = ParagraphStyle("S",  parent=styles["Heading2"], fontSize=10,
                              textColor=AZUL, spaceBefore=10, spaceAfter=3)
    norm_s  = ParagraphStyle("N",  parent=styles["Normal"],  fontSize=8, leading=11)
    foot_s  = ParagraphStyle("F",  parent=styles["Normal"],  fontSize=7,
                              textColor=colors.HexColor("#6c757d"), alignment=TA_CENTER)
    story   = []

    # Encabezado
    hdr = Table([[
        Paragraph("<b>LINCOLN FREIGHT</b>",
                  ParagraphStyle("H",  parent=styles["Normal"], fontSize=13, textColor=colors.white)),
        Paragraph("Simulador de Vuelta Redonda",
                  ParagraphStyle("HR", parent=styles["Normal"], fontSize=9,
                                 textColor=colors.white, alignment=TA_RIGHT)),
    ]], colWidths=[4.5 * inch, 2.5 * inch])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), AZUL),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (0, -1),  12),
        ("RIGHTPADDING",  (-1, 0), (-1, -1), 12),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}", norm_s))
    story.append(Spacer(1, 8))

    # Resumen global
    story.append(Paragraph("Resumen de Vuelta Redonda", sub_s))
    color_un = colors.HexColor("#28a745") if res["un"] >= 0 else colors.HexColor("#dc3545")
    res_rows = [
        ["Concepto",          "Monto (USD)",              "%"],
        ["Ingreso Total",     f"${res['ing']:,.2f}",      "100.00%"],
        ["Costo Directo",     f"${res['cd']:,.2f}",       f"{res['pct_cd']:.2f}%"],
        ["Ut. Bruta",         f"${res['ub']:,.2f}",       f"{res['pct_ub']:.2f}%"],
        ["Costos Indirectos", f"${res['ci']:,.2f}",       f"{res['pct_ci']:.2f}%"],
        ["Ut. Neta",          f"${res['un']:,.2f}",       f"{res['pct_un']:.2f}%"],
        ["Millas Cargadas",   f"{res['mi']:,.0f} mi",     ""],
        ["Millas Vacías",     f"{res['mv']:,.0f} mi",     ""],
    ]
    t_res = Table(res_rows, colWidths=[3.5 * inch, 2.0 * inch, 1.5 * inch])
    t_res.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),   AZUL),
        ("TEXTCOLOR",     (0, 0), (-1, 0),   colors.white),
        ("FONTNAME",      (0, 0), (-1, 0),   "Helvetica-Bold"),
        ("FONTNAME",      (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND",    (0, -3), (-1, -3), AZUL_L),
        ("TEXTCOLOR",     (1, -3), (1, -3),  color_un),
        ("FONTSIZE",      (0, 0), (-1, -1),  8),
        ("GRID",          (0, 0), (-1, -1),  0.5, colors.HexColor("#dee2e6")),
        ("ALIGN",         (1, 1), (-1, -1),  "RIGHT"),
        ("TOPPADDING",    (0, 0), (-1, -1),  3),
        ("BOTTOMPADDING", (0, 0), (-1, -1),  3),
        ("LEFTPADDING",   (0, 0), (-1, -1),  6),
    ]))
    story.append(t_res)
    story.append(Spacer(1, 8))

    # Detalle por tramo
    for ruta, etiq in zip(rutas, etiquetas):
        story.append(Paragraph(etiq, sub_s))
        miles_l = safe(ruta.get("Miles_Load",  0) or ruta.get("Millas_USA",    0))
        miles_e = safe(ruta.get("Miles_Empty", 0) or ruta.get("Millas_Vacias", 0))
        tramo_rows = [
            ["Campo",       "Valor"],
            ["ID Ruta",     str(ruta.get("ID_Ruta", ""))],
            ["Tipo",        _get(ruta, "Tipo")],
            ["Cliente",     str(ruta.get("Cliente", "—"))],
            ["Fecha",       str(ruta.get("Fecha",   ""))],
            ["Origen",      _get(ruta, "Origen")],
            ["Destino",     _get(ruta, "Destino")],
            ["Miles Load",  f"{miles_l:,.0f} mi"],
            ["Miles Empty", f"{miles_e:,.0f} mi"],
            ["Ingreso",     f"${safe(ruta.get('Ingreso_Total')):,.2f}"],
            ["Costo Dir.",  f"${safe(ruta.get('Costo_Directo_Total')):,.2f}"],
            ["Ut. Bruta",   f"${safe(ruta.get('Utilidad_Bruta')):,.2f} ({safe(ruta.get('Pct_Utilidad_Bruta')):.1f}%)"],
            ["Ut. Neta",    f"${safe(ruta.get('Utilidad_Neta')):,.2f} ({safe(ruta.get('Pct_Utilidad_Neta')):.1f}%)"],
        ]
        t_tr = Table(tramo_rows, colWidths=[2.0 * inch, 5.0 * inch])
        t_tr.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (0, -1), GRIS),
            ("FONTNAME",      (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, -1), 8),
            ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
            ("TOPPADDING",    (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ]))
        story.append(t_tr)
        story.append(Spacer(1, 8))

    story.append(Paragraph(
        f"Reporte generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} — Lincoln Freight · SOCA",
        foot_s,
    ))

    doc.build(story)
    return buf.getvalue()


# ─────────────────────────────────────────────
# RENDER PRINCIPAL
# ─────────────────────────────────────────────
def render() -> None:
    sb = get_supabase_client()
    if sb is None:
        alert("error", "Supabase no configurado.")
        return

    c_reload, _ = st.columns([1, 5])
    with c_reload:
        if st.button("🔄 Recargar rutas", key="ln_sim_reload"):
            load_rutas_lincoln.clear()
            st.rerun()

    valores = cargar_datos_generales()
    df      = load_rutas_lincoln(TABLE_RUTAS)

    if df.empty:
        alert("info", "No hay rutas guardadas para simular.")
        return

    if "Tipo" not in df.columns:
        alert("error", "La tabla no tiene columna 'Tipo'.")
        return

    # ══════════════════════════════════════════════════════════════
    # PASO 1: Ruta principal
    # ══════════════════════════════════════════════════════════════
    section_header("📌", "Paso 1 — Selecciona la Ruta Principal")

    df_princ = df[df["Tipo"].isin(TIPOS_PRINCIPAL)].copy()
    if df_princ.empty:
        alert("info", "No hay rutas NB / SB / D2DNB / D2DSB guardadas.")
        return

    tipos_disp = ["Todos"] + sorted(df_princ["Tipo"].dropna().unique().tolist())
    f_tipo     = st.selectbox("Filtrar por tipo", tipos_disp, key="ln_sim_ftipo")
    if f_tipo != "Todos":
        df_princ = df_princ[df_princ["Tipo"] == f_tipo]

    opciones_p = df_princ.apply(lambda row: label_ruta_lincoln(row.to_dict()), axis=1).tolist()
    if not opciones_p:
        alert("warn", "Sin rutas con ese filtro.")
        return

    sel_p  = st.selectbox("Ruta principal", opciones_p, key="ln_sim_sel_p")
    idx_p  = opciones_p.index(sel_p)
    ruta_p = df_princ.iloc[idx_p]

    with st.expander("📋 Ver detalle de la ruta principal", expanded=False):
        c1, c2, c3 = st.columns(3)
        c1.caption(f"**ID:** {ruta_p.get('ID_Ruta','')}")
        c1.caption(f"**Tipo:** {ruta_p.get('Tipo','')}")
        c1.caption(f"**Cliente:** {ruta_p.get('Cliente','—')}")
        miles_l = safe(ruta_p.get("Miles_Load",  0) or ruta_p.get("Millas_USA",    0))
        miles_e = safe(ruta_p.get("Miles_Empty", 0) or ruta_p.get("Millas_Vacias", 0))
        c2.caption(f"**Miles Load:** {miles_l:,.0f} mi")
        c2.caption(f"**Miles Empty:** {miles_e:,.0f} mi")
        c2.caption(f"**Ingreso:** ${safe(ruta_p.get('Ingreso_Total')):,.2f}")
        c3.caption(f"**Ut. Bruta:** ${safe(ruta_p.get('Utilidad_Bruta')):,.2f} ({safe(ruta_p.get('Pct_Utilidad_Bruta')):.1f}%)")
        c3.caption(f"**Ut. Neta:** ${safe(ruta_p.get('Utilidad_Neta')):,.2f} ({safe(ruta_p.get('Pct_Utilidad_Neta')):.1f}%)")

    # ══════════════════════════════════════════════════════════════
    # PASO 2: Sugerencias de regreso
    # ══════════════════════════════════════════════════════════════
    divider()
    fin_p = _ultimo_punto(ruta_p)
    section_header("🔁", f"Paso 2 — Regreso desde {fin_p}")

    candidatas = _sugerir_candidatas(df, ruta_p)

    if not candidatas:
        alert("info", f"No se encontraron rutas de regreso desde **{fin_p}**. "
                      "Puedes simular solo la ruta principal.")
        ruta_e     = None
        ruta_r_sel = None
    else:
        n_dir   = sum(1 for c in candidatas if c["ruta_e"] is None)
        n_vacio = len(candidatas) - n_dir
        st.caption(
            f"📊 **{len(candidatas)} combinaciones** encontradas — "
            f"{n_dir} directas · {n_vacio} con tramo vacío · ordenadas por Ut. Bruta combinada"
        )

        opciones_labels = ["— Sin regreso —"] + [c["label"] for c in candidatas]
        sel_label = st.selectbox(
            "Combinación de regreso",
            options=opciones_labels,
            label_visibility="collapsed",
            key="ln_sim_sel_cand",
        )

        if sel_label == "— Sin regreso —":
            ruta_e     = None
            ruta_r_sel = None
        else:
            sel_idx    = opciones_labels.index(sel_label) - 1
            cand       = candidatas[sel_idx]
            ruta_e     = pd.Series(cand["ruta_e"]) if cand["ruta_e"] else None
            ruta_r_sel = pd.Series(cand["ruta_r"])

            with st.expander("📋 Ver detalle de la combinación seleccionada", expanded=False):
                if ruta_e is not None:
                    st.markdown(
                        f"**Tramo vacío:** {ruta_e.get('ID_Ruta','')} · "
                        f"{_get(ruta_e,'Origen')} → {_get(ruta_e,'Destino')} · "
                        f"Ut.B ${safe(ruta_e.get('Utilidad_Bruta')):,.2f} "
                        f"({safe(ruta_e.get('Pct_Utilidad_Bruta')):.1f}%)"
                    )
                st.markdown(
                    f"**Regreso:** {ruta_r_sel.get('ID_Ruta','')} · "
                    f"{_get(ruta_r_sel,'Tipo')} · "
                    f"{ruta_r_sel.get('Cliente','—')} · "
                    f"{_get(ruta_r_sel,'Origen')} → {_get(ruta_r_sel,'Destino')} · "
                    f"Ut.B ${safe(ruta_r_sel.get('Utilidad_Bruta')):,.2f} "
                    f"({safe(ruta_r_sel.get('Pct_Utilidad_Bruta')):.1f}%)"
                )
                st.markdown(f"**Ut. Bruta combinada:** ${cand['ut_bruta']:,.2f} ({cand['pct_ut_bruta']:.1f}%)")

    # ══════════════════════════════════════════════════════════════
    # BOTÓN SIMULAR — solo cuando NO hay simulación activa
    # ══════════════════════════════════════════════════════════════
    if not st.session_state.get("ln_sim_realizada"):
        divider()
        b1, b2, b3 = st.columns([1, 2, 1])
        with b2:
            if st.button("🚛 Simular Vuelta Redonda", type="primary",
                         use_container_width=True, key="ln_sim_btn"):

                rutas_lista: list[dict] = [ruta_p.to_dict()]
                etiq_lista:  list[str]  = ["🚛 Ruta Principal"]

                if ruta_e is not None:
                    rutas_lista.append(ruta_e.to_dict())
                    etiq_lista.append("⬜ Tramo Vacío")

                if ruta_r_sel is not None:
                    rutas_lista.append(ruta_r_sel.to_dict())
                    etiq_lista.append("🔁 Regreso")

                st.session_state["ln_sim_datos"] = {
                    "rutas":     rutas_lista,
                    "etiquetas": etiq_lista,
                    "ruta_p":    ruta_p.to_dict(),
                    "ruta_e":    ruta_e.to_dict()     if ruta_e     is not None else None,
                    "ruta_r":    ruta_r_sel.to_dict() if ruta_r_sel is not None else None,
                }
                st.session_state["ln_sim_realizada"] = True
                st.rerun()

    # ══════════════════════════════════════════════════════════════
    # RESULTADOS
    # ══════════════════════════════════════════════════════════════
    if st.session_state.get("ln_sim_realizada"):
        datos = st.session_state.get("ln_sim_datos")
        if not datos:
            return

        rutas_series = [pd.Series(r) for r in datos["rutas"]]
        etiquetas    = datos["etiquetas"]
        ruta_p_s     = pd.Series(datos["ruta_p"])
        ruta_e_s     = pd.Series(datos["ruta_e"]) if datos["ruta_e"] else None
        ruta_r_s     = pd.Series(datos["ruta_r"]) if datos["ruta_r"] else None

        divider()
        section_header("📊", "Resumen de Vuelta Redonda")
        res = _resumen_vr(rutas_series, valores)

        # Simulador VR — sin $/mi (modalidad=""), sin desglose de tramo
        mostrar_resultados_lincoln(res, modalidad="", miles_load=0.0)

        divider()
        section_header("🗺️", "Secuencia del Road Trip")
        _ruta_visual(ruta_p_s, ruta_e_s, ruta_r_s)

        _detalle_tramos(rutas_series, etiquetas)

        divider()
        section_header("📥", "Descargar Reporte")
        try:
            pdf_bytes = _generar_pdf(rutas_series, etiquetas, res, ruta_p_s, ruta_e_s, ruta_r_s)
            nombre_pdf = (
                f"VR_Lincoln_{datos['ruta_p'].get('ID_Ruta','')}_"
                f"{datos['ruta_p'].get('Cliente','').replace(' ','_')}.pdf"
            )
            st.download_button(
                label="📄 Descargar PDF Vuelta Redonda",
                data=pdf_bytes,
                file_name=nombre_pdf,
                mime="application/pdf",
                use_container_width=True,
                key="ln_sim_dl_pdf",
            )
        except Exception as ex:
            alert("error", f"Error generando PDF: {ex}")

        if st.button("🔄 Nueva simulación", key="ln_sim_nueva"):
            st.session_state.pop("ln_sim_realizada", None)
            st.session_state.pop("ln_sim_datos",     None)
            st.rerun()
