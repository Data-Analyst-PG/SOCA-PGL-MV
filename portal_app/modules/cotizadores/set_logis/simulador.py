"""
simulador.py – Set Logis Plus
Simulador de Vuelta Redonda.

Flujo:
  Paso 1 → Selecciona ruta principal (NB / SB / D2DNB / D2DSB)
  Paso 2 → Sugerencias de regreso ordenadas por % Ut. Bruta combinada
            Candidatas: directas (sin empty) o con empty como puente
  Paso 3 → Botón "Simular" → resumen con kpi_row + semáforos
  Paso 4 → Detalle de cada tramo en expanders
  Paso 5 → Descarga PDF

Modelo geográfico del road trip:
  Cada ruta tiene un PRIMER PUNTO (de dónde sale) y un ÚLTIMO PUNTO (dónde termina).
  El regreso debe tener su PRIMER PUNTO igual al ÚLTIMO PUNTO de la principal.
  El empty actúa de puente cuando no hay conexión directa.

  _primer_punto:
    D2DNB → Origen_MX   (viene de México)
    otros → Origen_USA

  _ultimo_punto:
    D2DSB → Destino_MX  (termina en México)
    otros → Destino_USA

  Tipos de regreso compatibles:
    NB    → SB, D2DSB
    SB    → NB, D2DNB
    D2DNB → SB, D2DSB
    D2DSB → NB, D2DNB

  Empty: siempre solo americana (Origen_USA → Destino_USA)
"""

from __future__ import annotations

import io
from datetime import datetime

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)
from reportlab.lib.enums import TA_RIGHT, TA_CENTER

from services.supabase_client import get_supabase_client
from ui.components import section_header, alert, divider, kpi_row, semaforos_ruta
from ._shared import (
    TABLE_RUTAS,
    TIPOS_SUBIDA,
    safe,
)

TIPOS_PRINCIPAL = {"NB", "SB", "D2DNB", "D2DSB"}
TIPO_EMPTY      = "Empty"

# Tipos de regreso compatibles por tipo de principal
_REGRESO = {
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
            "Ingreso_Global", "Costo_Directo", "Costo_Indirecto",
            "Costo_Total", "Utilidad_Bruta", "Utilidad_Neta",
            "Pct_Ut_Bruta", "Pct_Ut_Neta", "Pct_Costo_Directo",
            "Pct_Costo_Indirecto", "Miles_Load", "Short_Miles", "Miles_Empty",
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


def _origen_usa(ruta) -> str:
    s = _get(ruta, "Ruta_USA")
    return s.split(" - ")[0].strip() if " - " in s else s


def _destino_usa(ruta) -> str:
    s = _get(ruta, "Ruta_USA")
    parts = s.split(" - ")
    return parts[-1].strip() if len(parts) > 1 else s


def _primer_punto(ruta) -> str:
    """De dónde sale la ruta. D2DNB sale de Origen_MX; el resto de Origen_USA."""
    tipo = _get(ruta, "Tipo_Viaje")
    if tipo == "D2DNB":
        return _get(ruta, "Origen_MX") or _origen_usa(ruta)
    return _origen_usa(ruta)


def _ultimo_punto(ruta) -> str:
    """Dónde termina la ruta. D2DSB termina en Destino_MX; el resto en Destino_USA."""
    tipo = _get(ruta, "Tipo_Viaje")
    if tipo == "D2DSB":
        return _get(ruta, "Destino_MX") or _destino_usa(ruta)
    return _destino_usa(ruta)


def _palabras(s: str, n: int = 2) -> str:
    return " ".join(str(s).upper().strip().split()[:n])


def _coincide(a: str, b: str) -> bool:
    """Compara las primeras 2 palabras de dos ubicaciones (tolerante a variaciones menores)."""
    return bool(a and b and _palabras(a) == _palabras(b))


def _label_ruta(row) -> str:
    pct = safe(row.get("Pct_Ut_Bruta")) if hasattr(row, "get") else 0.0
    return (
        f"{row.get('ID_Ruta','')} | {row.get('Fecha','')} | "
        f"{row.get('Tipo_Viaje','')} | {row.get('Cliente','—')} | "
        f"{row.get('Ruta_USA','')} | {pct:.1f}% Ut.B"
    )


# ─────────────────────────────────────────────
# MOTOR DE SUGERENCIAS
# ─────────────────────────────────────────────
def _sugerir_candidatas(df_all: pd.DataFrame, ruta_p: pd.Series) -> list[dict]:
    """
    Genera candidatas de regreso ordenadas por % Ut. Bruta combinada.

    Lógica:
      1. El regreso califica si _primer_punto(regreso) == _ultimo_punto(principal)
      2. Si no hay directas, el Empty actúa de puente:
           _primer_punto(empty) == _ultimo_punto(principal)
           _primer_punto(regreso) == _ultimo_punto(empty)
      3. Ordena todo por pct_ut_bruta combinada descendente.

    Cada candidata devuelve:
        label, ut_bruta, pct_ut_bruta, ruta_r (dict), ruta_e (dict|None)
    """
    tipo_p   = _get(ruta_p, "Tipo_Viaje")
    tipos_r  = _REGRESO.get(tipo_p, set())
    fin_p    = _ultimo_punto(ruta_p)

    ing_p = safe(ruta_p.get("Ingreso_Global", 0))
    ub_p  = safe(ruta_p.get("Utilidad_Bruta", 0))

    df_regreso = df_all[df_all["Tipo_Viaje"].isin(tipos_r)].copy() if "Tipo_Viaje" in df_all.columns else pd.DataFrame()
    df_empty   = df_all[df_all["Tipo_Viaje"] == TIPO_EMPTY].copy() if "Tipo_Viaje" in df_all.columns else pd.DataFrame()

    candidatas: list[dict] = []

    # ── Opción A: Regreso DIRECTO (sin empty) ────────────────────
    for _, r in df_regreso.iterrows():
        if not _coincide(_primer_punto(r), fin_p):
            continue
        ing_r = safe(r.get("Ingreso_Global", 0))
        ub_r  = safe(r.get("Utilidad_Bruta", 0))
        ing_t = ing_p + ing_r
        ub_t  = ub_p  + ub_r
        pct   = (ub_t / ing_t * 100) if ing_t > 0 else 0.0
        candidatas.append({
            "label":        (
                f"✅ DIRECTO · "
                f"{r.get('ID_Ruta','')} | {r.get('Fecha','')} | "
                f"{r.get('Tipo_Viaje','')} | {r.get('Cliente','—')} | "
                f"{r.get('Ruta_USA','')} · Ut.B comb. {pct:.1f}%"
            ),
            "ut_bruta":     ub_t,
            "pct_ut_bruta": pct,
            "ruta_r":       r.to_dict(),
            "ruta_e":       None,
        })

    # ── Opción B: Empty como puente + Regreso ────────────────────
    for _, e in df_empty.iterrows():
        # El empty debe salir del último punto de la principal
        if not _coincide(_origen_usa(e), fin_p):
            continue
        fin_e = _destino_usa(e)
        ing_e = safe(e.get("Ingreso_Global", 0))
        ub_e  = safe(e.get("Utilidad_Bruta", 0))

        for _, r in df_regreso.iterrows():
            if not _coincide(_primer_punto(r), fin_e):
                continue
            ing_r = safe(r.get("Ingreso_Global", 0))
            ub_r  = safe(r.get("Utilidad_Bruta", 0))
            ing_t = ing_p + ing_e + ing_r
            ub_t  = ub_p  + ub_e  + ub_r
            pct   = (ub_t / ing_t * 100) if ing_t > 0 else 0.0
            candidatas.append({
                "label":        (
                    f"🔄 CON VACÍO · "
                    f"[{e.get('ID_Ruta','')} {e.get('Ruta_USA','')}] + "
                    f"{r.get('ID_Ruta','')} | {r.get('Tipo_Viaje','')} | "
                    f"{r.get('Cliente','—')} | {r.get('Ruta_USA','')} · "
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
    """
    Construye la secuencia visual del road trip completo.

    Esquema general (todos los tramos opcionales salvo USA principal):
      [MX principal] → [USA principal] → [Empty USA] → [MX/USA regreso]

    Casos:
      NB principal    : Origen_USA → Destino_USA
      D2DNB principal : Origen_MX → Origen_USA → Destino_USA
      SB principal    : Origen_USA → Destino_USA
      D2DSB principal : Origen_USA → Destino_USA → Destino_MX
    """
    tipo_p = _get(ruta_p, "Tipo_Viaje")

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

    # ── Parte MX de la principal (si D2DNB, va al inicio) ────────
    if tipo_p == "D2DNB":
        om = _get(ruta_p, "Origen_MX")
        dm = _get(ruta_p, "Destino_MX")
        if om:
            pasos.append(nodo("🇲🇽", om, "Origen MX"))
            pasos.append(flecha)
        if dm:
            pasos.append(nodo("📍", dm, "Destino MX"))
            pasos.append(flecha)

    # ── Parte USA de la principal ─────────────────────────────────
    pasos.append(nodo("🇺🇸", _origen_usa(ruta_p), f"Origen USA ({tipo_p})"))
    pasos.append(flecha)
    pasos.append(nodo("📍", _destino_usa(ruta_p), "Destino USA"))

    # ── Parte MX de la principal (si D2DSB, va al final) ─────────
    if tipo_p == "D2DSB":
        om = _get(ruta_p, "Origen_MX")
        dm = _get(ruta_p, "Destino_MX")
        if om:
            pasos.append(flecha)
            pasos.append(nodo("🛂", om, "Origen MX"))
        if dm:
            pasos.append(flecha)
            pasos.append(nodo("🇲🇽", dm, "Destino MX"))

    # ── Tramo Empty (si existe) ───────────────────────────────────
    if ruta_e is not None:
        pasos.append(flecha)
        pasos.append(nodo("⬜", _origen_usa(ruta_e), f"Empty · {_get(ruta_e,'ID_Ruta')}"))
        pasos.append(flecha)
        pasos.append(nodo("⬜", _destino_usa(ruta_e), "Fin Empty"))

    # ── Parte de regreso ──────────────────────────────────────────
    if ruta_r is not None:
        tipo_r = _get(ruta_r, "Tipo_Viaje")

        # Si el regreso es D2DNB, empieza en MX
        if tipo_r == "D2DNB":
            om = _get(ruta_r, "Origen_MX")
            if om:
                pasos.append(flecha)
                pasos.append(nodo("🇲🇽", om, "Origen MX Reg."))
            pasos.append(flecha)
            pasos.append(nodo("🇺🇸", _origen_usa(ruta_r), f"Origen USA ({tipo_r})"))
            pasos.append(flecha)
            pasos.append(nodo("🏁", _destino_usa(ruta_r), "Destino USA Reg."))
        else:
            pasos.append(flecha)
            pasos.append(nodo("🇺🇸", _origen_usa(ruta_r), f"Origen USA ({tipo_r})"))
            pasos.append(flecha)
            # Si el regreso es D2DSB termina en MX
            if tipo_r == "D2DSB":
                pasos.append(nodo("📍", _destino_usa(ruta_r), "Destino USA Reg."))
                dm = _get(ruta_r, "Destino_MX")
                if dm:
                    pasos.append(flecha)
                    pasos.append(nodo("🏁", dm, "Destino MX Reg."))
            else:
                pasos.append(nodo("🏁", _destino_usa(ruta_r), "Destino Reg."))

    html = (
        '<div style="display:flex;flex-wrap:wrap;align-items:center;'
        'gap:4px;padding:12px 8px;background:#F8FAFF;border-radius:8px;'
        'border:1px solid #E0E7FF">'
        + "".join(pasos)
        + '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


# ─────────────────────────────────────────────
# RESUMEN VR
# ─────────────────────────────────────────────
def _resumen_vr(rutas: list[pd.Series]) -> dict:
    def _s(campo):
        return sum(safe(r.get(campo, 0)) for r in rutas)

    ing = _s("Ingreso_Global")
    cd  = _s("Costo_Directo")
    ci  = _s("Costo_Indirecto")
    ct  = _s("Costo_Total")
    ub  = _s("Utilidad_Bruta")
    un  = _s("Utilidad_Neta")
    ml  = _s("Short_Miles") + _s("Miles_Empty")

    pct_cd = (cd / ing * 100) if ing else 0.0
    pct_ci = (ci / ing * 100) if ing else 0.0
    pct_ub = (ub / ing * 100) if ing else 0.0
    pct_un = (un / ing * 100) if ing else 0.0

    color_ub = "#10b981" if ub >= 0 else "#dc2626"
    color_un = "#10b981" if un >= 0 else "#dc2626"

    kpi_row([
        {"icono": "💵", "label": "Ingreso VR",      "valor": f"${ing:,.2f}", "color": "#1B2266"},
        {"icono": "📦", "label": "Costo Directo",   "valor": f"${cd:,.2f}",  "color": "#6B7280"},
        {"icono": "🔁", "label": "Costo Indirecto", "valor": f"${ci:,.2f}",  "color": "#F59E0B"},
        {"icono": "📈", "label": "Ut. Bruta",        "valor": f"${ub:,.2f}",  "color": color_ub},
        {"icono": "🏆", "label": "Ut. Neta",         "valor": f"${un:,.2f}",  "color": color_un},
    ])

    p1, p2, p3, p4, p5 = st.columns(5)
    p1.metric("% C. Directo",   f"{pct_cd:.1f}%")
    p2.metric("% C. Indirecto", f"{pct_ci:.1f}%")
    p3.metric("% Ut. Bruta",    f"{pct_ub:.1f}%")
    p4.metric("% Ut. Neta",     f"{pct_un:.1f}%")
    p5.metric("Ingreso/Milla",  f"${(ing / ml):,.3f}" if ml > 0 else "—")

    divider()
    semaforos_ruta({
        "Pct_Costo_Directo":   pct_cd,
        "Pct_Ut_Bruta":        pct_ub,
        "Pct_Costo_Indirecto": pct_ci,
        "Pct_Ut_Neta":         pct_un,
    })

    return {
        "ing": ing, "cd": cd, "ci": ci, "ct": ct,
        "ub": ub, "un": un, "ml": ml,
        "pct_cd": pct_cd, "pct_ci": pct_ci,
        "pct_ub": pct_ub, "pct_un": pct_un,
    }


# ─────────────────────────────────────────────
# DETALLE POR TRAMO
# ─────────────────────────────────────────────
def _detalle_tramos(rutas: list[pd.Series], etiquetas: list[str]) -> None:
    divider()
    section_header("📋", "Detalle por Tramo")

    for i, (label, ruta) in enumerate(zip(etiquetas, rutas)):
        titulo = (
            f"{label} — {ruta.get('ID_Ruta','')} · "
            f"{ruta.get('Cliente','—')} · {ruta.get('Ruta_USA','')}"
        )
        with st.expander(titulo, expanded=(i == 0)):
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("**Ingresos**")
                st.caption(f"Flete USA: **${safe(ruta.get('Flete_USA')):,.2f}**")
                if safe(ruta.get("Fuel")) > 0:
                    st.caption(f"Fuel:      **${safe(ruta.get('Fuel')):,.2f}**")
                if safe(ruta.get("Ingreso_Cruce")) > 0:
                    st.caption(f"Cruce:     **${safe(ruta.get('Ingreso_Cruce')):,.2f}**")
                if safe(ruta.get("Ingreso_MX")) > 0:
                    st.caption(f"MX:        **${safe(ruta.get('Ingreso_MX')):,.2f}**")
                if safe(ruta.get("Extras_Ingreso")) > 0:
                    st.caption(f"Extras:    **${safe(ruta.get('Extras_Ingreso')):,.2f}**")
                st.markdown(f"**Total: ${safe(ruta.get('Ingreso_Global')):,.2f}**")
            with c2:
                st.markdown("**Costos**")
                st.caption(f"Owner Cargado: **${safe(ruta.get('Pago_Owner_Cargado')):,.2f}**")
                st.caption(f"Owner Vacío:   **${safe(ruta.get('Pago_Owner_Vacio')):,.2f}**")
                if safe(ruta.get("Costo_Cruce")) > 0:
                    st.caption(f"Cruce:         **${safe(ruta.get('Costo_Cruce')):,.2f}**")
                if safe(ruta.get("Costo_MX")) > 0:
                    st.caption(f"MX:            **${safe(ruta.get('Costo_MX')):,.2f}**")
                if safe(ruta.get("Extras_Costo")) > 0:
                    st.caption(f"Extras:        **${safe(ruta.get('Extras_Costo')):,.2f}**")
                st.caption(f"Indirecto:     **${safe(ruta.get('Costo_Indirecto')):,.2f}**")
                st.markdown(f"**Total: ${safe(ruta.get('Costo_Total')):,.2f}**")
            with c3:
                st.markdown("**Millas**")
                st.caption(f"Miles Load:  **{safe(ruta.get('Miles_Load')):.0f} mi**")
                st.caption(f"Short Miles: **{safe(ruta.get('Short_Miles')):.0f} mi**")
                st.caption(f"Miles Empty: **{safe(ruta.get('Miles_Empty')):.0f} mi**")
                st.divider()
                st.markdown("**Resultado**")
                ut_b = safe(ruta.get("Utilidad_Bruta"))
                ut_n = safe(ruta.get("Utilidad_Neta"))
                pct_b = safe(ruta.get("Pct_Ut_Bruta"))
                pct_n = safe(ruta.get("Pct_Ut_Neta"))
                color_b = "#16a34a" if ut_b >= 0 else "#dc2626"
                color_n = "#16a34a" if ut_n >= 0 else "#dc2626"
                st.markdown(
                    f'<span style="color:{color_b}">**Ut. Bruta: ${ut_b:,.2f} ({pct_b:.1f}%)**</span>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'<span style="color:{color_n}">**Ut. Neta:  ${ut_n:,.2f} ({pct_n:.1f}%)**</span>',
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

    styles = getSampleStyleSheet()
    title_s  = ParagraphStyle("T", parent=styles["Title"],   fontSize=14, textColor=colors.HexColor("#1B2266"), spaceAfter=4)
    sub_s    = ParagraphStyle("S", parent=styles["Heading2"], fontSize=10, textColor=colors.HexColor("#1B2266"), spaceBefore=10, spaceAfter=3)
    normal_s = ParagraphStyle("N", parent=styles["Normal"],  fontSize=8,  leading=11)
    footer_s = ParagraphStyle("F", parent=styles["Normal"],  fontSize=7,  textColor=colors.HexColor("#6c757d"), alignment=TA_CENTER)

    story = []

    # Encabezado
    hdr = Table([[
        Paragraph("<b>SET LOGIS PLUS</b>", ParagraphStyle("H",  parent=styles["Normal"], fontSize=13, textColor=colors.white)),
        Paragraph("Simulador de Vuelta Redonda", ParagraphStyle("HR", parent=styles["Normal"], fontSize=9, textColor=colors.white, alignment=TA_RIGHT)),
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

    # Resumen global
    story.append(Paragraph("Resumen de Vuelta Redonda", sub_s))
    color_un_pdf = colors.HexColor("#28a745") if res["un"] >= 0 else colors.HexColor("#dc3545")
    resumen_data = [
        ["Concepto",        "Monto (USD)",           "%"],
        ["Ingreso Total",   f"${res['ing']:,.2f}",   "100.00%"],
        ["Costo Directo",   f"${res['cd']:,.2f}",    f"{res['pct_cd']:.2f}%"],
        ["Ut. Bruta",        f"${res['ub']:,.2f}",    f"{res['pct_ub']:.2f}%"],
        ["Costo Indirecto", f"${res['ci']:,.2f}",    f"{res['pct_ci']:.2f}%"],
        ["Ut. Neta",         f"${res['un']:,.2f}",    f"{res['pct_un']:.2f}%"],
    ]
    t_res = Table(resumen_data, colWidths=[2.8 * inch, 2.2 * inch, 2.0 * inch])
    t_res.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor("#1B2266")),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("ALIGN",         (1, 1), (-1, -1), "RIGHT"),
        ("BACKGROUND",    (0, 5), (-1, 5),  color_un_pdf),
        ("TEXTCOLOR",     (0, 5), (-1, 5),  colors.white),
        ("FONTNAME",      (0, 5), (-1, 5),  "Helvetica-Bold"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
    ]))
    story.append(t_res)
    story.append(Spacer(1, 10))

    # Secuencia de ruta (texto)
    story.append(Paragraph("Secuencia del Road Trip", sub_s))
    tipo_p = _get(ruta_p, "Tipo_Viaje")
    pasos_txt: list[str] = []
    if tipo_p == "D2DNB":
        om = _get(ruta_p, "Origen_MX")
        dm = _get(ruta_p, "Destino_MX")
        if om: pasos_txt.append(f"Origen MX: {om}")
        if dm: pasos_txt.append(f"Destino MX: {dm}")
    pasos_txt.append(f"Origen USA ({tipo_p}): {_origen_usa(ruta_p)}")
    pasos_txt.append(f"Destino USA: {_destino_usa(ruta_p)}")
    if tipo_p == "D2DSB":
        dm = _get(ruta_p, "Destino_MX")
        if dm: pasos_txt.append(f"Destino MX: {dm}")
    if ruta_e is not None:
        pasos_txt.append(f"Empty origen: {_origen_usa(ruta_e)}")
        pasos_txt.append(f"Empty destino: {_destino_usa(ruta_e)}")
    if ruta_r is not None:
        tipo_r = _get(ruta_r, "Tipo_Viaje")
        if tipo_r == "D2DNB":
            om = _get(ruta_r, "Origen_MX")
            if om: pasos_txt.append(f"Origen MX Reg.: {om}")
        pasos_txt.append(f"Origen USA Reg. ({tipo_r}): {_origen_usa(ruta_r)}")
        pasos_txt.append(f"Destino USA Reg.: {_destino_usa(ruta_r)}")
        if tipo_r == "D2DSB":
            dm = _get(ruta_r, "Destino_MX")
            if dm: pasos_txt.append(f"Destino MX Reg.: {dm}")
    story.append(Paragraph(" → ".join(pasos_txt), normal_s))
    story.append(Spacer(1, 10))

    # Detalle por tramo
    story.append(Paragraph("Detalle por Tramo", sub_s))
    for label, ruta in zip(etiquetas, rutas):
        story.append(Paragraph(f"<b>{label} — {ruta.get('ID_Ruta', '')} · {ruta.get('Cliente', '—')}</b>", normal_s))
        story.append(Spacer(1, 3))
        tramo_data = [
            ["Campo",       "Valor",                                    "Campo",        "Valor"],
            ["Tipo",        str(ruta.get("Tipo_Viaje", "")),            "Fecha",        str(ruta.get("Fecha", ""))],
            ["Ruta USA",    str(ruta.get("Ruta_USA", "")),              "Modo",         str(ruta.get("Modo", ""))],
            ["Short Miles", f"{safe(ruta.get('Short_Miles')):.0f} mi",  "Miles Empty",  f"{safe(ruta.get('Miles_Empty')):.0f} mi"],
            ["Ingreso",     f"${safe(ruta.get('Ingreso_Global')):,.2f}", "Costo Dir.",  f"${safe(ruta.get('Costo_Directo')):,.2f}"],
            ["Ut. Bruta",   f"${safe(ruta.get('Utilidad_Bruta')):,.2f} ({safe(ruta.get('Pct_Ut_Bruta')):.1f}%)",
             "Ut. Neta",   f"${safe(ruta.get('Utilidad_Neta')):,.2f} ({safe(ruta.get('Pct_Ut_Neta')):.1f}%)"],
        ]
        t_tramo = Table(tramo_data, colWidths=[1.4 * inch, 2.0 * inch, 1.4 * inch, 2.0 * inch])
        t_tramo.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor("#1B2266")),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("BACKGROUND",    (0, 1), (0, -1),  colors.HexColor("#EEF2FF")),
            ("BACKGROUND",    (2, 1), (2, -1),  colors.HexColor("#EEF2FF")),
            ("FONTNAME",      (0, 1), (0, -1),  "Helvetica-Bold"),
            ("FONTNAME",      (2, 1), (2, -1),  "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, -1), 7),
            ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
            ("TOPPADDING",    (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ]))
        story.append(t_tramo)
        story.append(Spacer(1, 8))

    story.append(Spacer(1, 16))
    story.append(Paragraph(
        f"Reporte generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} — Set Logis Plus",
        footer_s,
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

    r1, r2 = st.columns([1, 4])
    with r1:
        if st.button("🔄 Recargar", key="sl_sim_reload"):
            _cargar_rutas.clear()
            st.rerun()
    with r2:
        st.caption("Carga cacheada 2 min.")

    st.session_state.setdefault("sl_sim_realizada", False)
    st.session_state.setdefault("sl_sim_datos", None)

    df = _cargar_rutas(TABLE_RUTAS)
    if df.empty:
        alert("warn", "No hay rutas guardadas todavía.")
        return

    df_prin = df[df["Tipo_Viaje"].isin(TIPOS_PRINCIPAL)].copy() if "Tipo_Viaje" in df.columns else pd.DataFrame()
    if df_prin.empty:
        alert("warn", "No hay rutas NB / SB / D2DNB / D2DSB guardadas.")
        return
    df_prin = df_prin.set_index("ID_Ruta", drop=False)

    # ══════════════════════════════════════════════════════════════
    # PASO 1: Ruta principal
    # ══════════════════════════════════════════════════════════════
    divider()
    section_header("📌", "Paso 1 — Selecciona la Ruta Principal")
    st.write("Filtra las rutas (opcional):")

    fp1, fp2 = st.columns(2)
    tipos_d    = sorted(df_prin["Tipo_Viaje"].dropna().unique().tolist())
    clientes_d = sorted(df_prin["Cliente"].dropna().astype(str).unique().tolist())
    f_tipo = fp1.selectbox("Tipo",    ["Todos"] + tipos_d,    key="sl_sim_ftipo")
    f_cli  = fp2.selectbox("Cliente", ["Todos"] + clientes_d, key="sl_sim_fcli")

    df_pf = df_prin.copy()
    if f_tipo != "Todos":
        df_pf = df_pf[df_pf["Tipo_Viaje"] == f_tipo]
    if f_cli != "Todos":
        df_pf = df_pf[df_pf["Cliente"].astype(str) == f_cli]

    if df_pf.empty:
        alert("info", "No hay rutas con esos filtros.")
        return

    st.write(f"Selecciona una ruta ({len(df_pf)} disponibles):")
    idx_p = st.selectbox(
        "Ruta principal",
        options=df_pf.index.tolist(),
        format_func=lambda i: _label_ruta(df_pf.loc[i]),
        key="sl_sim_sel_p",
        label_visibility="collapsed",
    )
    ruta_p = df_pf.loc[idx_p]

    with st.expander("📋 Ver detalles de la ruta seleccionada", expanded=False):
        d1, d2 = st.columns(2)
        with d1:
            st.markdown(f"**ID:** {ruta_p.get('ID_Ruta','')}")
            st.markdown(f"**Tipo:** {ruta_p.get('Tipo_Viaje','')}")
            st.markdown(f"**Cliente:** {ruta_p.get('Cliente','—')}")
            st.markdown(f"**Fecha:** {ruta_p.get('Fecha','')}")
            if _get(ruta_p, "Origen_MX"):
                st.markdown(f"**Origen MX:** {ruta_p.get('Origen_MX','')}")
                st.markdown(f"**Destino MX:** {ruta_p.get('Destino_MX','')}")
        with d2:
            st.markdown(f"**Ruta USA:** {ruta_p.get('Ruta_USA','')}")
            st.markdown(f"**Ultimo punto:** {_ultimo_punto(ruta_p)}")
            st.markdown(f"**Ingreso:** ${safe(ruta_p.get('Ingreso_Global')):,.2f}")
            st.markdown(f"**Costo Dir.:** ${safe(ruta_p.get('Costo_Directo')):,.2f}")
            st.markdown(f"**Ut. Bruta:** ${safe(ruta_p.get('Utilidad_Bruta')):,.2f} ({safe(ruta_p.get('Pct_Ut_Bruta')):.1f}%)")

    # ══════════════════════════════════════════════════════════════
    # PASO 2: Sugerencias de regreso
    # ══════════════════════════════════════════════════════════════
    divider()
    fin_p = _ultimo_punto(ruta_p)
    section_header("🔁", f"Paso 2 — Regreso desde {fin_p} (con o sin vacío)")

    candidatas = _sugerir_candidatas(df, ruta_p)

    if not candidatas:
        alert("info", f"No se encontraron rutas de regreso desde **{fin_p}**. Puedes simular solo la ruta principal.")
        ruta_e     = None
        ruta_r_sel = None
    else:
        n_dir   = sum(1 for c in candidatas if c["ruta_e"] is None)
        n_vacio = sum(1 for c in candidatas if c["ruta_e"] is not None)
        st.caption(
            f"📊 **{len(candidatas)} combinaciones** encontradas — "
            f"{n_dir} directas · {n_vacio} con tramo vacío · ordenadas por Ut. Bruta combinada"
        )

        opciones_labels = ["— Sin regreso —"] + [c["label"] for c in candidatas]
        sel_label = st.selectbox(
            "Combinación de regreso",
            options=opciones_labels,
            key="sl_sim_sel_cand",
            label_visibility="collapsed",
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
                        f"{ruta_e.get('Ruta_USA','')} · "
                        f"Ut.B ${safe(ruta_e.get('Utilidad_Bruta')):,.2f} ({safe(ruta_e.get('Pct_Ut_Bruta')):.1f}%)"
                    )
                if ruta_r_sel is not None:
                    st.markdown(
                        f"**Regreso:** {ruta_r_sel.get('ID_Ruta','')} · "
                        f"{ruta_r_sel.get('Tipo_Viaje','')} · "
                        f"{ruta_r_sel.get('Cliente','—')} · "
                        f"{ruta_r_sel.get('Ruta_USA','')} · "
                        f"Ut.B ${safe(ruta_r_sel.get('Utilidad_Bruta')):,.2f} ({safe(ruta_r_sel.get('Pct_Ut_Bruta')):.1f}%)"
                    )
                st.markdown(f"**Ut. Bruta combinada estimada:** ${cand['ut_bruta']:,.2f} ({cand['pct_ut_bruta']:.1f}%)")

    # ══════════════════════════════════════════════════════════════
    # BOTÓN SIMULAR
    # ══════════════════════════════════════════════════════════════
    divider()
    b1, b2, b3 = st.columns([1, 2, 1])
    with b2:
        if st.button("🚛 Simular Vuelta Redonda", type="primary",
                     use_container_width=True, key="sl_sim_btn"):

            # Construir lista ordenada de tramos
            rutas_lista: list[dict] = [ruta_p.to_dict()]
            etiq_lista:  list[str]  = ["🚛 Ruta Principal"]

            if ruta_e is not None:
                rutas_lista.append(ruta_e.to_dict())
                etiq_lista.append("⬜ Tramo Vacío")

            if ruta_r_sel is not None:
                rutas_lista.append(ruta_r_sel.to_dict())
                etiq_lista.append("🔁 Regreso")

            st.session_state["sl_sim_datos"] = {
                "rutas":    rutas_lista,
                "etiquetas": etiq_lista,
                "ruta_p":   ruta_p.to_dict(),
                "ruta_e":   ruta_e.to_dict()   if ruta_e     is not None else None,
                "ruta_r":   ruta_r_sel.to_dict() if ruta_r_sel is not None else None,
            }
            st.session_state["sl_sim_realizada"] = True
            st.rerun()

    # ══════════════════════════════════════════════════════════════
    # RESULTADOS
    # ══════════════════════════════════════════════════════════════
    if st.session_state.get("sl_sim_realizada"):
        datos = st.session_state.get("sl_sim_datos")
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

        divider()
        section_header("🗺️", "Secuencia del Road Trip")
        _ruta_visual(ruta_p_s, ruta_e_s, ruta_r_s)

        _detalle_tramos(rutas_series, etiquetas)

        divider()
        section_header("📥", "Descargar Reporte")
        try:
            pdf_bytes = _generar_pdf(rutas_series, etiquetas, res, ruta_p_s, ruta_e_s, ruta_r_s)
            nombre_pdf = (
                f"VR_SetLogis_{datos['ruta_p'].get('ID_Ruta','')}_{datos['ruta_p'].get('Cliente','').replace(' ','_')}.pdf"
            )
            st.download_button(
                label="📄 Descargar PDF Vuelta Redonda",
                data=pdf_bytes,
                file_name=nombre_pdf,
                mime="application/pdf",
                use_container_width=True,
            )
        except Exception as ex:
            alert("error", f"Error generando PDF: {ex}")
