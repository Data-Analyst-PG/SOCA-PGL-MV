"""
simulador.py – Lincoln Freight (USA/MX)
Simulador de Vuelta Redonda.

Flujo:
  Paso 1 → Selecciona ruta principal (NB / SB / D2DNB / D2DSB)
  Paso 2 → Sugerencias de regreso ordenadas por % Ut. Bruta combinada
            Candidatas: directas (sin empty) o con empty como puente
  Paso 3 → Botón "Simular" → resumen con kpi_row + semáforos
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
from ui.components import section_header, alert, divider, kpi_row, semaforos_ruta
from ._shared import (
    TABLE_RUTAS,
    safe,
)

TIPOS_PRINCIPAL = {"NB", "SB", "D2DNB", "D2DSB"}
TIPO_EMPTY      = "Empty"

_REGRESO: dict[str, set] = {
    "NB":    {"SB", "D2DSB"},
    "SB":    {"NB", "D2DNB"},
    "D2DNB": {"SB", "D2DSB"},
    "D2DSB": {"NB", "D2DNB"},
}


# ─────────────────────────────────────────────
# CACHE
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=120)
def _cargar_rutas(table: str) -> pd.DataFrame:
    sb = get_supabase_client()
    if sb is None:
        return pd.DataFrame()
    try:
        resp = sb.table(table).select("*").order("Fecha", desc=True).execute()
        df = pd.DataFrame(resp.data or [])
        if df.empty:
            return df
        nums = [
            "Ingreso_Total", "Costo_Directo_Total", "Utilidad_Bruta",
            "Pct_Utilidad_Bruta", "Costos_Indirectos", "Utilidad_Neta",
            "Pct_Utilidad_Neta", "Millas_USA", "Millas_Vacias",
        ]
        for col in nums:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        if "Fecha" in df.columns:
            df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d")
        return df
    except Exception:
        return pd.DataFrame()


# ─────────────────────────────────────────────
# HELPERS GEOGRÁFICOS
# ─────────────────────────────────────────────
def _get(ruta, key: str) -> str:
    v = ruta.get(key, "") if hasattr(ruta, "get") else ""
    return str(v).strip().upper() if v else ""


def _primer_punto(ruta) -> str:
    """De dónde sale la ruta. D2DNB sale de Origen_MX; el resto de Origen."""
    tipo = _get(ruta, "Tipo")
    if tipo == "D2DNB":
        return _get(ruta, "Origen_MX") or _get(ruta, "Origen")
    return _get(ruta, "Origen")


def _ultimo_punto(ruta) -> str:
    """Dónde termina la ruta. D2DSB termina en Destino_MX; el resto en Destino."""
    tipo = _get(ruta, "Tipo")
    if tipo == "D2DSB":
        return _get(ruta, "Destino_MX") or _get(ruta, "Destino")
    return _get(ruta, "Destino")


def _palabras(s: str, n: int = 2) -> str:
    return " ".join(str(s).upper().strip().split()[:n])


def _coincide(a: str, b: str) -> bool:
    return bool(a and b and _palabras(a) == _palabras(b))


def _label_ruta(row) -> str:
    pct = safe(row.get("Pct_Utilidad_Bruta", 0))
    return (
        f"{row.get('ID_Ruta', '')} | {row.get('Fecha', '')} | "
        f"{row.get('Tipo', '')} | {row.get('Cliente', '—')} | "
        f"{row.get('Origen', '')} → {row.get('Destino', '')} | "
        f"{pct:.1f}% Ut.B"
    )


# ─────────────────────────────────────────────
# MOTOR DE SUGERENCIAS
# ─────────────────────────────────────────────
def _sugerir_candidatas(df_all: pd.DataFrame, ruta_p: pd.Series) -> list[dict]:
    tipo_p  = _get(ruta_p, "Tipo")
    tipos_r = _REGRESO.get(tipo_p, set())
    fin_p   = _ultimo_punto(ruta_p)

    ing_p = safe(ruta_p.get("Ingreso_Total", 0))
    ub_p  = safe(ruta_p.get("Utilidad_Bruta", 0))

    df_reg   = df_all[df_all["Tipo"].isin(tipos_r)].copy()   if "Tipo" in df_all.columns else pd.DataFrame()
    df_empty = df_all[df_all["Tipo"] == TIPO_EMPTY].copy()   if "Tipo" in df_all.columns else pd.DataFrame()

    candidatas: list[dict] = []

    # ── Opción A: Regreso DIRECTO ─────────────────────────────────
    for _, r in df_reg.iterrows():
        if not _coincide(_primer_punto(r), fin_p):
            continue
        ing_r = safe(r.get("Ingreso_Total", 0))
        ub_r  = safe(r.get("Utilidad_Bruta", 0))
        ing_t = ing_p + ing_r
        ub_t  = ub_p  + ub_r
        pct   = (ub_t / ing_t * 100) if ing_t > 0 else 0.0
        candidatas.append({
            "label": (
                f"✅ DIRECTO · "
                f"{r.get('ID_Ruta', '')} | {r.get('Fecha', '')} | "
                f"{r.get('Tipo', '')} | {r.get('Cliente', '—')} | "
                f"{r.get('Origen', '')} → {r.get('Destino', '')} · "
                f"Ut.B comb. {pct:.1f}%"
            ),
            "ut_bruta":     ub_t,
            "pct_ut_bruta": pct,
            "ruta_r":       r.to_dict(),
            "ruta_e":       None,
        })

    # ── Opción B: Empty como puente + Regreso ────────────────────
    for _, e in df_empty.iterrows():
        if not _coincide(_get(e, "Origen"), fin_p):
            continue
        fin_e = _get(e, "Destino")
        ing_e = safe(e.get("Ingreso_Total", 0))
        ub_e  = safe(e.get("Utilidad_Bruta", 0))

        for _, r in df_reg.iterrows():
            if not _coincide(_primer_punto(r), fin_e):
                continue
            ing_r = safe(r.get("Ingreso_Total", 0))
            ub_r  = safe(r.get("Utilidad_Bruta", 0))
            ing_t = ing_p + ing_e + ing_r
            ub_t  = ub_p  + ub_e  + ub_r
            pct   = (ub_t / ing_t * 100) if ing_t > 0 else 0.0
            candidatas.append({
                "label": (
                    f"🔄 CON VACÍO · "
                    f"[{e.get('ID_Ruta', '')} {e.get('Origen', '')}→{e.get('Destino', '')}] + "
                    f"{r.get('ID_Ruta', '')} | {r.get('Tipo', '')} | "
                    f"{r.get('Cliente', '—')} | "
                    f"{r.get('Origen', '')} → {r.get('Destino', '')} · "
                    f"Ut.B comb. {pct:.1f}%"
                ),
                "ut_bruta":     ub_t,
                "pct_ut_bruta": pct,
                "ruta_r":       r.to_dict(),
                "ruta_e":       e.to_dict(),
            })

    candidatas.sort(key=lambda x: x["pct_ut_bruta"], reverse=True)
    return candidatas


# ─────────────────────────────────────────────
# RUTA VISUAL
# ─────────────────────────────────────────────
def _ruta_visual(ruta_p: pd.Series, ruta_e: pd.Series | None, ruta_r: pd.Series | None) -> None:
    tipo_p = _get(ruta_p, "Tipo")

    def nodo(icono: str, ciudad: str, etiqueta: str) -> str:
        return (
            f'<div style="text-align:center;min-width:90px">'
            f'<div style="font-size:1.4rem">{icono}</div>'
            f'<div style="font-weight:700;font-size:.78rem;color:#1B2266">{ciudad}</div>'
            f'<div style="font-size:.68rem;color:#6B7280">{etiqueta}</div>'
            f'</div>'
        )

    flecha = '<div style="font-size:1.3rem;padding:0 4px;align-self:center">→</div>'
    pasos: list[str] = []

    # MX inicial si D2DNB
    if tipo_p == "D2DNB":
        om = _get(ruta_p, "Origen_MX")
        dm = _get(ruta_p, "Destino_MX")
        if om:
            pasos += [nodo("🇲🇽", om, "Origen MX"), flecha]
        if dm:
            pasos += [nodo("📍", dm, "Destino MX"), flecha]

    # USA principal
    pasos += [
        nodo("🇺🇸", _get(ruta_p, "Origen"), f"Origen USA ({tipo_p})"),
        flecha,
        nodo("📍", _get(ruta_p, "Destino"), "Destino USA"),
    ]

    # MX final si D2DSB
    if tipo_p == "D2DSB":
        om = _get(ruta_p, "Origen_MX")
        dm = _get(ruta_p, "Destino_MX")
        if om:
            pasos += [flecha, nodo("🛂", om, "Origen MX")]
        if dm:
            pasos += [flecha, nodo("🇲🇽", dm, "Destino MX")]

    # Empty
    if ruta_e is not None:
        pasos += [
            flecha,
            nodo("⬜", _get(ruta_e, "Origen"), f"Empty · {_get(ruta_e, 'ID_Ruta')}"),
            flecha,
            nodo("⬜", _get(ruta_e, "Destino"), "Fin Empty"),
        ]

    # Regreso
    if ruta_r is not None:
        tipo_r = _get(ruta_r, "Tipo")
        if tipo_r == "D2DNB":
            om = _get(ruta_r, "Origen_MX")
            if om:
                pasos += [flecha, nodo("🇲🇽", om, "Origen MX Reg.")]
        pasos += [
            flecha,
            nodo("🔁", _get(ruta_r, "Origen"), f"Origen Reg. ({tipo_r})"),
            flecha,
            nodo("🏁", _get(ruta_r, "Destino"), "Destino Final"),
        ]
        if tipo_r == "D2DSB":
            dm = _get(ruta_r, "Destino_MX")
            if dm:
                pasos += [flecha, nodo("🇲🇽", dm, "Destino MX Reg.")]

    html = (
        '<div style="display:flex;flex-wrap:wrap;align-items:center;'
        'gap:4px;padding:12px;background:#f8f9fa;border-radius:8px;'
        'border:1px solid #dee2e6">' + "".join(pasos) + "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


# ─────────────────────────────────────────────
# RESUMEN VR
# ─────────────────────────────────────────────
def _resumen_vr(rutas: list[pd.Series]) -> dict:
    ing = sum(safe(r.get("Ingreso_Total", 0))      for r in rutas)
    cd  = sum(safe(r.get("Costo_Directo_Total", 0)) for r in rutas)
    ub  = sum(safe(r.get("Utilidad_Bruta", 0))      for r in rutas)
    ci  = sum(safe(r.get("Costos_Indirectos", 0))   for r in rutas)
    un  = sum(safe(r.get("Utilidad_Neta", 0))        for r in rutas)
    mi  = sum(safe(r.get("Millas_USA", 0))           for r in rutas)
    mv  = sum(safe(r.get("Millas_Vacias", 0))        for r in rutas)

    return {
        "ing":     ing,
        "cd":      cd,
        "ub":      ub,
        "ci":      ci,
        "un":      un,
        "mi":      mi,
        "mv":      mv,
        "pct_cd":  (cd  / ing * 100) if ing else 0.0,
        "pct_ub":  (ub  / ing * 100) if ing else 0.0,
        "pct_ci":  (ci  / ing * 100) if ing else 0.0,
        "pct_un":  (un  / ing * 100) if ing else 0.0,
    }


# ─────────────────────────────────────────────
# DETALLE DE TRAMOS
# ─────────────────────────────────────────────
def _detalle_tramos(rutas: list[pd.Series], etiquetas: list[str]) -> None:
    divider()
    section_header("🗺️", "Detalle por Tramo")
    for ruta, etiq in zip(rutas, etiquetas):
        tipo = _get(ruta, "Tipo")
        ub   = safe(ruta.get("Utilidad_Bruta", 0))
        pct  = safe(ruta.get("Pct_Utilidad_Bruta", 0))
        un   = safe(ruta.get("Utilidad_Neta", 0))
        color_n = "#28a745" if un >= 0 else "#dc3545"
        with st.expander(
            f"{etiq} · {ruta.get('ID_Ruta', '')} | {ruta.get('Cliente', '—')} | "
            f"{ruta.get('Origen', '')} → {ruta.get('Destino', '')} | "
            f"Ut.B ${ub:,.2f} ({pct:.1f}%)",
            expanded=False,
        ):
            c1, c2, c3 = st.columns(3)
            c1.caption(f"**Tipo:** {tipo}")
            c1.caption(f"**Cliente:** {ruta.get('Cliente', '—')}")
            c1.caption(f"**Fecha:** {ruta.get('Fecha', '—')}")
            c1.caption(f"**Modo:** {ruta.get('Modo_Viaje', '—')}")
            c2.caption(f"**Millas USA:** {safe(ruta.get('Millas_USA')):,.0f}")
            c2.caption(f"**Millas Vacías:** {safe(ruta.get('Millas_Vacias')):,.0f}")
            c2.caption(f"**Ingreso:** ${safe(ruta.get('Ingreso_Total')):,.2f}")
            c2.caption(f"**Costo Directo:** ${safe(ruta.get('Costo_Directo_Total')):,.2f}")
            c3.caption(f"**Ut. Bruta:** ${ub:,.2f} ({pct:.1f}%)")
            c3.caption(f"**Costos Ind.:** ${safe(ruta.get('Costos_Indirectos')):,.2f}")
            c3.markdown(
                f'<span style="color:{color_n}">**Ut. Neta: ${un:,.2f} '
                f"({safe(ruta.get('Pct_Utilidad_Neta')):.1f}%)**</span>",
                unsafe_allow_html=True,
            )


# ─────────────────────────────────────────────
# PDF
# ─────────────────────────────────────────────
def _generar_pdf(
    rutas: list[pd.Series],
    etiquetas: list[str],
    res: dict,
    ruta_p: pd.Series,
    ruta_e: pd.Series | None,
    ruta_r: pd.Series | None,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
    )

    styles  = getSampleStyleSheet()
    title_s = ParagraphStyle("T",  parent=styles["Title"],   fontSize=14,
                              textColor=colors.HexColor("#1B2266"), spaceAfter=4)
    sub_s   = ParagraphStyle("S",  parent=styles["Heading2"], fontSize=10,
                              textColor=colors.HexColor("#1B2266"), spaceBefore=10, spaceAfter=3)
    norm_s  = ParagraphStyle("N",  parent=styles["Normal"],  fontSize=8,  leading=11)
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
        ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#1B2266")),
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
        ["Concepto",         "Monto (USD)",              "%"],
        ["Ingreso Total",    f"${res['ing']:,.2f}",      "100.00%"],
        ["Costo Directo",    f"${res['cd']:,.2f}",       f"{res['pct_cd']:.2f}%"],
        ["Ut. Bruta",        f"${res['ub']:,.2f}",       f"{res['pct_ub']:.2f}%"],
        ["Costo Indirecto",  f"${res['ci']:,.2f}",       f"{res['pct_ci']:.2f}%"],
        ["Ut. Neta",         f"${res['un']:,.2f}",       f"{res['pct_un']:.2f}%"],
        ["Millas Cargadas",  f"{res['mi']:,.0f}",        ""],
        ["Millas Vacías",    f"{res['mv']:,.0f}",        ""],
    ]
    t_res = Table(res_rows, colWidths=[2.8 * inch, 2.2 * inch, 2.0 * inch])
    t_res.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor("#1B2266")),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("ALIGN",         (1, 1), (-1, -1), "RIGHT"),
        ("BACKGROUND",    (0, 5), (-1, 5),  color_un),
        ("TEXTCOLOR",     (0, 5), (-1, 5),  colors.white),
        ("FONTNAME",      (0, 5), (-1, 5),  "Helvetica-Bold"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
    ]))
    story.append(t_res)
    story.append(Spacer(1, 10))

    # Detalle por tramo
    for ruta, etiq in zip(rutas, etiquetas):
        story.append(Paragraph(etiq, sub_s))
        tipo = _get(ruta, "Tipo")
        tramo_rows = [
            ["ID",          str(ruta.get("ID_Ruta", ""))],
            ["Tipo",        tipo],
            ["Cliente",     str(ruta.get("Cliente", ""))],
            ["Origen",      str(ruta.get("Origen", ""))],
            ["Destino",     str(ruta.get("Destino", ""))],
            ["Millas USA",  f"{safe(ruta.get('Millas_USA')):,.0f}"],
            ["Millas Vac.", f"{safe(ruta.get('Millas_Vacias')):,.0f}"],
            ["Ingreso",     f"${safe(ruta.get('Ingreso_Total')):,.2f}"],
            ["Costo Dir.",  f"${safe(ruta.get('Costo_Directo_Total')):,.2f}"],
            ["Ut. Bruta",   f"${safe(ruta.get('Utilidad_Bruta')):,.2f} ({safe(ruta.get('Pct_Utilidad_Bruta')):.1f}%)"],
            ["Ut. Neta",    f"${safe(ruta.get('Utilidad_Neta')):,.2f} ({safe(ruta.get('Pct_Utilidad_Neta')):.1f}%)"],
        ]
        t_tr = Table(tramo_rows, colWidths=[2.0 * inch, 5.0 * inch])
        t_tr.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (0, -1), colors.HexColor("#f0f0f0")),
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
        f"Reporte generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} — Lincoln Freight",
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
            _cargar_rutas.clear()
            st.rerun()

    df = _cargar_rutas(TABLE_RUTAS)
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

    # Filtro rápido de tipo
    tipos_disp = ["Todos"] + sorted(df_princ["Tipo"].dropna().unique().tolist())
    f_tipo = st.selectbox("Filtrar por tipo", tipos_disp, key="ln_sim_ftipo")
    if f_tipo != "Todos":
        df_princ = df_princ[df_princ["Tipo"] == f_tipo]

    opciones_p = df_princ.apply(_label_ruta, axis=1).tolist()
    if not opciones_p:
        alert("warn", "Sin rutas con ese filtro.")
        return

    sel_p = st.selectbox("Ruta principal", opciones_p, key="ln_sim_sel_p")
    idx_p = opciones_p.index(sel_p)
    ruta_p = df_princ.iloc[idx_p]

    with st.expander("📋 Ver detalle de la ruta principal", expanded=False):
        c1, c2, c3 = st.columns(3)
        c1.caption(f"**ID:** {ruta_p.get('ID_Ruta', '')}")
        c1.caption(f"**Tipo:** {ruta_p.get('Tipo', '')}")
        c1.caption(f"**Cliente:** {ruta_p.get('Cliente', '—')}")
        c2.caption(f"**Millas USA:** {safe(ruta_p.get('Millas_USA')):,.0f}")
        c2.caption(f"**Millas Vacías:** {safe(ruta_p.get('Millas_Vacias')):,.0f}")
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
                        f"**Tramo vacío:** {ruta_e.get('ID_Ruta', '')} · "
                        f"{ruta_e.get('Origen', '')} → {ruta_e.get('Destino', '')} · "
                        f"Ut.B ${safe(ruta_e.get('Utilidad_Bruta')):,.2f} "
                        f"({safe(ruta_e.get('Pct_Utilidad_Bruta')):.1f}%)"
                    )
                st.markdown(
                    f"**Regreso:** {ruta_r_sel.get('ID_Ruta', '')} · "
                    f"{ruta_r_sel.get('Tipo', '')} · "
                    f"{ruta_r_sel.get('Cliente', '—')} · "
                    f"{ruta_r_sel.get('Origen', '')} → {ruta_r_sel.get('Destino', '')} · "
                    f"Ut.B ${safe(ruta_r_sel.get('Utilidad_Bruta')):,.2f} "
                    f"({safe(ruta_r_sel.get('Pct_Utilidad_Bruta')):.1f}%)"
                )
                st.markdown(f"**Ut. Bruta combinada estimada:** ${cand['ut_bruta']:,.2f} ({cand['pct_ut_bruta']:.1f}%)")

    # ══════════════════════════════════════════════════════════════
    # BOTÓN SIMULAR — solo visible cuando NO hay simulación activa
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
        res = _resumen_vr(rutas_series)

        kpi_row([
            dict(icono="💰", label="Ingreso Total",    valor=f"${res['ing']:,.2f}", color="#1B2266"),
            dict(icono="💸", label="Costo Directo",    valor=f"${res['cd']:,.2f}", color="#DC2626"),
            dict(icono="📈", label="Ut. Bruta",        valor=f"${res['ub']:,.2f}", sub=f"{res['pct_ub']:.1f}%", color="#059669"),
            dict(icono="📉", label="Costo Indirecto",  valor=f"${res['ci']:,.2f}", color="#D97706"),
            dict(icono="✅", label="Ut. Neta",         valor=f"${res['un']:,.2f}", sub=f"{res['pct_un']:.1f}%", color="#059669" if res['un'] >= 0 else "#DC2626"),
        ])

        # Semáforo combinado manual (usa el dict de res)
        semaforos_ruta({
            "Pct_Costo_Directo":   res["pct_cd"],
            "Pct_Ut_Bruta":        res["pct_ub"],
            "Pct_Costo_Indirecto": res["pct_ci"],
            "Pct_Ut_Neta":         res["pct_un"],
        })

        divider()
        section_header("🗺️", "Secuencia del Road Trip")
        _ruta_visual(ruta_p_s, ruta_e_s, ruta_r_s)

        _detalle_tramos(rutas_series, etiquetas)

        divider()
        section_header("📥", "Descargar Reporte")
        try:
            pdf_bytes = _generar_pdf(rutas_series, etiquetas, res, ruta_p_s, ruta_e_s, ruta_r_s)
            nombre_pdf = (
                f"VR_Lincoln_{datos['ruta_p'].get('ID_Ruta', '')}_"
                f"{datos['ruta_p'].get('Cliente', '').replace(' ', '_')}.pdf"
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
            st.session_state.pop("ln_sim_datos", None)
            st.rerun()
