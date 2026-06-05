"""
simulador.py – Set Logis Plus
Simulador de Vuelta Redonda.

Flujo (igual que Igloo):
  Paso 1 → Selecciona ruta principal (NB / SB / D2DNB / D2DSB)
  Paso 2 → Sugerencias de tramo Empty ordenadas por % Ut. Bruta
            (sin contar millas vacías adicionales)
  Paso 3 → Botón "Simular" → resumen con kpi_row + semáforos
  Paso 4 → Detalle de cada tramo en expanders
  Paso 5 → Descarga PDF

Estructura de ruta visual:
  NB / D2DNB : Origen USA → Destino USA → [Origen E → Destino E] → [Origen MX → Destino MX]
  SB / D2DSB : [Origen MX → Destino MX] → [Origen E → Destino E] → Origen USA → Destino USA

Cálculo combinado:
  - Se usan los valores guardados de cada ruta (Ingreso_Global, Costo_Directo,
    Costo_Indirecto, Utilidad_Bruta, Utilidad_Neta, Pct_Ut_*)
  - NO se recalculan millas vacías: la ruta Empty ya trae su propio costo.
"""

from __future__ import annotations

import io
import tempfile
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
    TIPOS_BAJADA,
    safe,
)

TIPOS_PRINCIPAL = {"NB", "SB", "D2DNB", "D2DSB"}
TIPO_EMPTY      = "Empty"


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
        nums = ["Ingreso_Global", "Costo_Directo", "Costo_Indirecto",
                "Costo_Total", "Utilidad_Bruta", "Utilidad_Neta",
                "Pct_Ut_Bruta", "Pct_Ut_Neta", "Pct_Costo_Directo",
                "Pct_Costo_Indirecto", "Miles_Load", "Short_Miles", "Miles_Empty"]
        for col in nums:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        if "Fecha" in df.columns:
            df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d")
        return df
    except Exception:
        return pd.DataFrame()


# ─────────────────────────────────────────────
# HELPERS DE RUTA
# ─────────────────────────────────────────────
def _origen_usa(ruta: pd.Series | dict) -> str:
    s = str(ruta.get("Ruta_USA", "") if hasattr(ruta, "get") else "")
    return s.split(" - ")[0].strip().upper()


def _destino_usa(ruta: pd.Series | dict) -> str:
    s = str(ruta.get("Ruta_USA", "") if hasattr(ruta, "get") else "")
    parts = s.split(" - ")
    return parts[-1].strip().upper()


def _label_ruta(row: pd.Series | dict, mostrar_pct: bool = True) -> str:
    g = row.get if hasattr(row, "get") else row.__getitem__
    pct = f" | {safe(g('Pct_Ut_Bruta')):.1f}% Ut.B" if mostrar_pct else ""
    return (
        f"{g('ID_Ruta')} | {g('Fecha')} | {g('Tipo_Viaje')} | "
        f"{g('Cliente')} | {g('Ruta_USA')}{pct}"
    )


def _palabras(s: str, n: int = 2) -> str:
    return " ".join(str(s).upper().strip().split()[:n])


def _coincide(a: str, b: str) -> bool:
    return bool(a and b and _palabras(a) == _palabras(b))


# Tipo de regreso según la principal
_REGRESO = {
    "NB":    {"SB", "D2DSB"},
    "D2DNB": {"SB", "D2DSB"},
    "SB":    {"NB", "D2DNB"},
    "D2DSB": {"NB", "D2DNB"},
}


def _sugerir_candidatas(df_all: pd.DataFrame, ruta_p: pd.Series) -> list[dict]:
    """
    Genera lista de candidatas de regreso ordenadas por % Ut. Bruta combinada.
    Cada candidata es un dict con:
        label       : texto para el selector
        ut_bruta    : utilidad bruta combinada (principal + regreso [+ empty])
        pct_ut_bruta: % ut. bruta combinada
        ruta_r      : dict de la ruta de regreso
        ruta_e      : dict de la ruta empty (o None si es directo)
    """
    tipo_p   = str(ruta_p.get("Tipo_Viaje", ""))
    tipos_r  = _REGRESO.get(tipo_p, set())
    es_sub   = tipo_p in TIPOS_SUBIDA

    # Punto de conexión: destino de la principal si sube, origen si baja
    ref_loc  = _destino_usa(ruta_p) if es_sub else _origen_usa(ruta_p)

    ing_p  = safe(ruta_p.get("Ingreso_Global", 0))
    ub_p   = safe(ruta_p.get("Utilidad_Bruta", 0))

    df_regreso = df_all[df_all["Tipo_Viaje"].isin(tipos_r)].copy() if "Tipo_Viaje" in df_all.columns else pd.DataFrame()
    df_empty   = df_all[df_all["Tipo_Viaje"] == "Empty"].copy()    if "Tipo_Viaje" in df_all.columns else pd.DataFrame()

    candidatas: list[dict] = []

    # ── Opción A: regreso DIRECTO (sin empty) ────────────────────
    for _, r in df_regreso.iterrows():
        # El regreso debe empezar donde termina la principal (o viceversa)
        origen_r = _origen_usa(r) if es_sub else _destino_usa(r)
        if not _coincide(origen_r, ref_loc):
            continue
        ing_r  = safe(r.get("Ingreso_Global", 0))
        ub_r   = safe(r.get("Utilidad_Bruta", 0))
        ing_t  = ing_p + ing_r
        ub_t   = ub_p + ub_r
        pct    = (ub_t / ing_t * 100) if ing_t > 0 else 0.0
        candidatas.append({
            "label":        f"✅ DIRECTO · {r.get('ID_Ruta','')} | {r.get('Fecha','')} | {r.get('Tipo_Viaje','')} | {r.get('Cliente','—')} | {r.get('Ruta_USA','')} → Ut.B combinada {pct:.1f}%",
            "ut_bruta":     ub_t,
            "pct_ut_bruta": pct,
            "ruta_r":       r.to_dict(),
            "ruta_e":       None,
        })

    # ── Opción B: empty + regreso ────────────────────────────────
    for _, e in df_empty.iterrows():
        # El empty debe salir del punto de conexión de la principal
        origen_e = _origen_usa(e) if es_sub else _destino_usa(e)
        if not _coincide(origen_e, ref_loc):
            continue
        # Destino del empty = nuevo punto de conexión para el regreso
        dest_e   = _destino_usa(e) if es_sub else _origen_usa(e)
        ing_e    = safe(e.get("Ingreso_Global", 0))
        ub_e     = safe(e.get("Utilidad_Bruta", 0))

        for _, r in df_regreso.iterrows():
            origen_r = _origen_usa(r) if es_sub else _destino_usa(r)
            if not _coincide(origen_r, dest_e):
                continue
            ing_r  = safe(r.get("Ingreso_Global", 0))
            ub_r   = safe(r.get("Utilidad_Bruta", 0))
            ing_t  = ing_p + ing_e + ing_r
            ub_t   = ub_p + ub_e + ub_r
            pct    = (ub_t / ing_t * 100) if ing_t > 0 else 0.0
            candidatas.append({
                "label":        f"🔄 CON VACÍO · {e.get('ID_Ruta','')} ({e.get('Ruta_USA','')}) + {r.get('ID_Ruta','')} | {r.get('Cliente','—')} | {r.get('Ruta_USA','')} → Ut.B combinada {pct:.1f}%",
                "ut_bruta":     ub_t,
                "pct_ut_bruta": pct,
                "ruta_r":       r.to_dict(),
                "ruta_e":       e.to_dict(),
            })

# ─────────────────────────────────────────────
# RUTA VISUAL
# ─────────────────────────────────────────────
def _ruta_visual(ruta_p: pd.Series, ruta_e: pd.Series | None) -> None:
    tipo = str(ruta_p.get("Tipo_Viaje", ""))
    es_sub = tipo in TIPOS_SUBIDA

    orig_usa  = _origen_usa(ruta_p)
    dest_usa  = _destino_usa(ruta_p)
    orig_mx   = str(ruta_p.get("Origen_MX", "")).strip()
    dest_mx   = str(ruta_p.get("Destino_MX", "")).strip()
    tiene_mx  = bool(orig_mx and dest_mx)

    orig_e = _origen_usa(ruta_e)  if ruta_e is not None else None
    dest_e = _destino_usa(ruta_e) if ruta_e is not None else None

    if es_sub:
        pasos = [
            ("🇺🇸", orig_usa, "Origen USA"),
            ("📍", dest_usa,  "Destino USA"),
        ]
        if orig_e:
            pasos += [("⬜", orig_e, "Inicio Vacío"), ("⬜", dest_e, "Fin Vacío")]
        if tiene_mx:
            pasos += [("🇲🇽", orig_mx, "Origen MX"), ("🇲🇽", dest_mx, "Destino MX")]
    else:
        pasos = []
        if tiene_mx:
            pasos += [("🇲🇽", orig_mx, "Origen MX"), ("🇲🇽", dest_mx, "Destino MX")]
        if orig_e:
            pasos += [("⬜", orig_e, "Inicio Vacío"), ("⬜", dest_e, "Fin Vacío")]
        pasos += [
            ("🇺🇸", orig_usa, "Origen USA"),
            ("📍", dest_usa,  "Destino USA"),
        ]

    bloques = []
    for icono, lugar, etiqueta in pasos:
        bloques.append(
            f'<div style="text-align:center;min-width:90px;">'
            f'<div style="font-size:0.68rem;color:#6B7280;">{etiqueta}</div>'
            f'<div style="font-weight:700;font-size:0.85rem;">{icono} {lugar or "—"}</div>'
            f'</div>'
        )

    sep = '<div style="color:#1B2266;font-size:1.3rem;padding:0 4px;">→</div>'
    st.markdown(
        f'<div style="background:#EEF2FF;border-radius:8px;padding:10px 16px;'
        f'display:flex;flex-wrap:wrap;align-items:center;gap:4px;">'
        + sep.join(bloques)
        + '</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────
# TARJETA DE TRAMO
# ─────────────────────────────────────────────
def _tarjeta_tramo(titulo: str, ruta: pd.Series) -> None:
    ub  = safe(ruta.get("Utilidad_Bruta"))
    pct = safe(ruta.get("Pct_Ut_Bruta"))
    color = "#10b981" if ub >= 0 else "#dc2626"
    with st.container(border=True):
        h1, h2 = st.columns([3, 1])
        with h1:
            st.markdown(f"**{titulo}**")
            st.caption(
                f"{ruta.get('ID_Ruta','')} · {ruta.get('Tipo_Viaje','')} · "
                f"{ruta.get('Cliente','—')} · {ruta.get('Ruta_USA','')}"
            )
        with h2:
            st.markdown(
                f'<div style="text-align:right;color:{color};">'
                f'<div style="font-size:1rem;font-weight:800;">${ub:,.2f}</div>'
                f'<div style="font-size:0.7rem;">{pct:.1f}% Ut. Bruta</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Ingreso",    f"${safe(ruta.get('Ingreso_Global')):,.2f}")
        m2.metric("Costo Dir.", f"${safe(ruta.get('Costo_Directo')):,.2f}")
        m3.metric("Ut. Neta",  f"${safe(ruta.get('Utilidad_Neta')):,.2f}")
        m4.metric("Miles Load", f"{safe(ruta.get('Miles_Load')):.0f} mi")


# ─────────────────────────────────────────────
# RESUMEN VR (kpi_row + semáforos)
# ─────────────────────────────────────────────
def _resumen_vr(rutas: list[pd.Series]) -> dict:
    def _s(campo):
        return sum(safe(r.get(campo)) for r in rutas)

    ing = _s("Ingreso_Global")
    cd  = _s("Costo_Directo")
    ci  = _s("Costo_Indirecto")
    ct  = _s("Costo_Total")
    ub  = _s("Utilidad_Bruta")
    un  = _s("Utilidad_Neta")
    ml  = _s("Miles_Load") + _s("Short_Miles")

    pct_cd = (cd / ing * 100) if ing else 0.0
    pct_ci = (ci / ing * 100) if ing else 0.0
    pct_ub = (ub / ing * 100) if ing else 0.0
    pct_un = (un / ing * 100) if ing else 0.0

    color_ub = "#10b981" if ub >= 0 else "#dc2626"
    color_un = "#10b981" if un >= 0 else "#dc2626"

    kpi_row([
        {"icono": "💵", "label": "Ingreso VR",       "valor": f"${ing:,.2f}", "color": "#1B2266"},
        {"icono": "📦", "label": "Costo Directo",    "valor": f"${cd:,.2f}",  "color": "#6B7280"},
        {"icono": "🔁", "label": "Costo Indirecto",  "valor": f"${ci:,.2f}",  "color": "#F59E0B"},
        {"icono": "📈", "label": "Ut. Bruta",         "valor": f"${ub:,.2f}",  "color": color_ub},
        {"icono": "🏆", "label": "Ut. Neta",          "valor": f"${un:,.2f}",  "color": color_un},
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
# DETALLE POR TRAMO (expanders)
# ─────────────────────────────────────────────
def _detalle_tramos(rutas: list[pd.Series], ruta_p: pd.Series, ruta_e: pd.Series | None) -> None:
    divider()
    section_header("📋", "Detalle por Tramo")

    etiquetas = ["🚛 Ruta Principal"]
    if ruta_e is not None:
        etiquetas.append("⬜ Tramo Vacío")

    for i, (label, ruta) in enumerate(zip(etiquetas, rutas)):
        with st.expander(f"{label} — {ruta.get('ID_Ruta','')} · {ruta.get('Cliente','—')} · {ruta.get('Ruta_USA','')}", expanded=(i == 0)):
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("**Ingresos**")
                st.caption(f"Flete USA: **${safe(ruta.get('Flete_USA')):,.2f}**")
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
                    st.caption(f"Extras costo:  **${safe(ruta.get('Extras_Costo')):,.2f}**")
                st.caption(f"Indirecto:     **${safe(ruta.get('Costo_Indirecto')):,.2f}**")
                st.markdown(f"**Total: ${safe(ruta.get('Costo_Total')):,.2f}**")
            with c3:
                st.markdown("**Millas**")
                st.caption(f"Miles Load:    **{safe(ruta.get('Miles_Load')):.0f} mi**")
                st.caption(f"Short Miles:   **{safe(ruta.get('Short_Miles')):.0f} mi**")
                st.caption(f"Miles Empty:   **{safe(ruta.get('Miles_Empty')):.0f} mi**")
                st.caption(f"PxM Cargado:   **${safe(ruta.get('PxM_Cargado')):.4f}**")
                st.caption(f"PxM Vacío:     **${safe(ruta.get('PxM_Vacio')):.4f}**")
                st.markdown(f"**Ut. Neta: ${safe(ruta.get('Utilidad_Neta')):,.2f} ({safe(ruta.get('Pct_Ut_Neta')):.1f}%)**")


# ─────────────────────────────────────────────
# PDF
# ─────────────────────────────────────────────
def _generar_pdf(
    rutas: list[pd.Series],
    res: dict,
    ruta_p: pd.Series,
    ruta_e: pd.Series | None,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
    )

    styles = getSampleStyleSheet()
    title_s  = ParagraphStyle("T", parent=styles["Title"],   fontSize=14, textColor=colors.HexColor("#1B2266"), spaceAfter=4)
    sub_s    = ParagraphStyle("S", parent=styles["Heading2"],fontSize=10, textColor=colors.HexColor("#1B2266"), spaceBefore=10, spaceAfter=3)
    normal_s = ParagraphStyle("N", parent=styles["Normal"],  fontSize=8,  leading=11)
    footer_s = ParagraphStyle("F", parent=styles["Normal"],  fontSize=7,  textColor=colors.HexColor("#6c757d"), alignment=TA_CENTER)

    story = []

    # ── Encabezado ───────────────────────────────────────────────
    hdr = Table([[
        Paragraph("<b>SET LOGIS PLUS</b>", ParagraphStyle("H", parent=styles["Normal"], fontSize=13, textColor=colors.white)),
        Paragraph("Simulador de Vuelta Redonda", ParagraphStyle("HR", parent=styles["Normal"], fontSize=9, textColor=colors.white, alignment=TA_RIGHT)),
    ]], colWidths=[4.5*inch, 2.5*inch])
    hdr.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,-1), colors.HexColor("#1B2266")),
        ("VALIGN",     (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0),(-1,-1), 10),
        ("BOTTOMPADDING",(0,0),(-1,-1), 10),
        ("LEFTPADDING", (0,0),(0,-1), 12),
        ("RIGHTPADDING",(-1,0),(-1,-1), 12),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 10))

    # ── Resumen global ───────────────────────────────────────────
    story.append(Paragraph("Resumen de Vuelta Redonda", sub_s))
    color_un = colors.HexColor("#28a745") if res["un"] >= 0 else colors.HexColor("#dc3545")
    resumen_data = [
        ["Concepto", "Monto (USD)", "%"],
        ["Ingreso Total",    f"${res['ing']:,.2f}", "100.00%"],
        ["Costo Directo",   f"${res['cd']:,.2f}",  f"{res['pct_cd']:.2f}%"],
        ["Ut. Bruta",        f"${res['ub']:,.2f}",  f"{res['pct_ub']:.2f}%"],
        ["Costo Indirecto", f"${res['ci']:,.2f}",  f"{res['pct_ci']:.2f}%"],
        ["Ut. Neta",         f"${res['un']:,.2f}",  f"{res['pct_un']:.2f}%"],
    ]
    t_res = Table(resumen_data, colWidths=[2.8*inch, 2.2*inch, 2.0*inch])
    t_res.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0),  colors.HexColor("#1B2266")),
        ("TEXTCOLOR",     (0,0),(-1,0),  colors.white),
        ("FONTNAME",      (0,0),(-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0,0),(-1,-1), 8),
        ("GRID",          (0,0),(-1,-1), 0.5, colors.HexColor("#dee2e6")),
        ("ALIGN",         (1,1),(-1,-1), "RIGHT"),
        ("BACKGROUND",    (0,5),(-1,5),  color_un),
        ("TEXTCOLOR",     (0,5),(-1,5),  colors.white),
        ("FONTNAME",      (0,5),(-1,5),  "Helvetica-Bold"),
        ("TOPPADDING",    (0,0),(-1,-1), 3),
        ("BOTTOMPADDING", (0,0),(-1,-1), 3),
        ("LEFTPADDING",   (0,0),(-1,-1), 6),
    ]))
    story.append(t_res)
    story.append(Spacer(1, 10))

    # ── Secuencia de ruta ────────────────────────────────────────
    story.append(Paragraph("Secuencia de la Ruta", sub_s))
    tipo = str(ruta_p.get("Tipo_Viaje", ""))
    es_sub = tipo in TIPOS_SUBIDA
    pasos_txt = []
    if es_sub:
        pasos_txt.append(f"Origen USA: {_origen_usa(ruta_p)}")
        pasos_txt.append(f"Destino USA: {_destino_usa(ruta_p)}")
        if ruta_e is not None:
            pasos_txt.append(f"Inicio Vacío: {_origen_usa(ruta_e)}")
            pasos_txt.append(f"Fin Vacío: {_destino_usa(ruta_e)}")
        if str(ruta_p.get("Origen_MX","")).strip():
            pasos_txt.append(f"Origen MX: {ruta_p.get('Origen_MX','')}")
            pasos_txt.append(f"Destino MX: {ruta_p.get('Destino_MX','')}")
    else:
        if str(ruta_p.get("Origen_MX","")).strip():
            pasos_txt.append(f"Origen MX: {ruta_p.get('Origen_MX','')}")
            pasos_txt.append(f"Destino MX: {ruta_p.get('Destino_MX','')}")
        if ruta_e is not None:
            pasos_txt.append(f"Inicio Vacío: {_origen_usa(ruta_e)}")
            pasos_txt.append(f"Fin Vacío: {_destino_usa(ruta_e)}")
        pasos_txt.append(f"Origen USA: {_origen_usa(ruta_p)}")
        pasos_txt.append(f"Destino USA: {_destino_usa(ruta_p)}")
    story.append(Paragraph(" → ".join(pasos_txt), normal_s))
    story.append(Spacer(1, 10))

    # ── Detalle por tramo ────────────────────────────────────────
    story.append(Paragraph("Detalle por Tramo", sub_s))
    etiquetas = ["Ruta Principal"]
    if ruta_e is not None:
        etiquetas.append("Tramo Vacío")

    for label, ruta in zip(etiquetas, rutas):
        story.append(Paragraph(f"<b>{label} — {ruta.get('ID_Ruta','')} · {ruta.get('Cliente','—')}</b>", normal_s))
        story.append(Spacer(1, 3))
        tramo_data = [
            ["Campo", "Valor", "Campo", "Valor"],
            ["Tipo",       str(ruta.get("Tipo_Viaje","")),   "Fecha",   str(ruta.get("Fecha",""))],
            ["Ruta USA",   str(ruta.get("Ruta_USA","")),     "Modo",    str(ruta.get("Modo",""))],
            ["Miles Load", f"{safe(ruta.get('Miles_Load')):.0f} mi",
             "Miles Empty", f"{safe(ruta.get('Miles_Empty')):.0f} mi"],
            ["Ingreso",    f"${safe(ruta.get('Ingreso_Global')):,.2f}",
             "Costo Dir.", f"${safe(ruta.get('Costo_Directo')):,.2f}"],
            ["Ut. Bruta",  f"${safe(ruta.get('Utilidad_Bruta')):,.2f} ({safe(ruta.get('Pct_Ut_Bruta')):.1f}%)",
             "Ut. Neta",   f"${safe(ruta.get('Utilidad_Neta')):,.2f} ({safe(ruta.get('Pct_Ut_Neta')):.1f}%)"],
        ]
        t_tramo = Table(tramo_data, colWidths=[1.4*inch, 2.0*inch, 1.4*inch, 2.0*inch])
        t_tramo.setStyle(TableStyle([
            ("BACKGROUND",  (0,0),(-1,0),  colors.HexColor("#1B2266")),
            ("TEXTCOLOR",   (0,0),(-1,0),  colors.white),
            ("FONTNAME",    (0,0),(-1,0),  "Helvetica-Bold"),
            ("BACKGROUND",  (0,1),(0,-1),  colors.HexColor("#EEF2FF")),
            ("BACKGROUND",  (2,1),(2,-1),  colors.HexColor("#EEF2FF")),
            ("FONTNAME",    (0,1),(0,-1),  "Helvetica-Bold"),
            ("FONTNAME",    (2,1),(2,-1),  "Helvetica-Bold"),
            ("FONTSIZE",    (0,0),(-1,-1), 7),
            ("GRID",        (0,0),(-1,-1), 0.5, colors.HexColor("#dee2e6")),
            ("TOPPADDING",  (0,0),(-1,-1), 2),
            ("BOTTOMPADDING",(0,0),(-1,-1), 2),
            ("LEFTPADDING", (0,0),(-1,-1), 5),
        ]))
        story.append(t_tramo)
        story.append(Spacer(1, 8))

    # ── Footer ───────────────────────────────────────────────────
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

    # Recargar
    r1, r2 = st.columns([1, 4])
    with r1:
        if st.button("🔄 Recargar", key="sl_sim_reload"):
            _cargar_rutas.clear()
            st.rerun()
    with r2:
        st.caption("Carga cacheada 2 min.")

    # Session state
    st.session_state.setdefault("sl_sim_realizada", False)
    st.session_state.setdefault("sl_sim_rutas", [])
    st.session_state.setdefault("sl_sim_ruta_p", None)
    st.session_state.setdefault("sl_sim_ruta_e", None)

    df = _cargar_rutas(TABLE_RUTAS)
    if df.empty:
        alert("warn", "No hay rutas guardadas todavía.")
        return

    df_prin  = df[df["Tipo_Viaje"].isin(TIPOS_PRINCIPAL)].copy() if "Tipo_Viaje" in df.columns else pd.DataFrame()
    df_empty = df[df["Tipo_Viaje"] == TIPO_EMPTY].copy()          if "Tipo_Viaje" in df.columns else pd.DataFrame()

    if df_prin.empty:
        alert("warn", "No hay rutas NB / SB / D2DNB / D2DSB guardadas.")
        return

    df_prin = df_prin.set_index("ID_Ruta", drop=False)

    # ── PASO 1: Ruta principal ────────────────────────────────────
    divider()
    section_header("📌", "Paso 1 — Selecciona la Ruta Principal")
    st.write("Filtra las rutas (opcional):")

    fp1, fp2 = st.columns(2)
    tipos_d   = sorted(df_prin["Tipo_Viaje"].dropna().unique().tolist())
    clientes_d = sorted(df_prin["Cliente"].dropna().astype(str).unique().tolist())
    f_tipo = fp1.selectbox("Tipo", ["Todos"] + tipos_d, key="sl_sim_ftipo")
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
        with d2:
            st.markdown(f"**Ruta USA:** {ruta_p.get('Ruta_USA','')}")
            st.markdown(f"**Ingreso:** ${safe(ruta_p.get('Ingreso_Global')):,.2f}")
            st.markdown(f"**Costo Dir.:** ${safe(ruta_p.get('Costo_Directo')):,.2f}")
            st.markdown(f"**Ut. Bruta:** ${safe(ruta_p.get('Utilidad_Bruta')):,.2f} ({safe(ruta_p.get('Pct_Ut_Bruta')):.1f}%)")

    # ── PASO 2: Tramo Empty ───────────────────────────────────────
    divider()
    section_header("⬜", "Paso 2 — Tramo Vacío (opcional)")

    tipo_p    = str(ruta_p.get("Tipo_Viaje", ""))
    es_subida = tipo_p in TIPOS_SUBIDA
    ref_loc   = _destino_usa(ruta_p) if es_subida else _origen_usa(ruta_p)

    if df_empty.empty:
        alert("info", "No hay rutas Empty guardadas. Puedes simular sin tramo vacío.")
        ruta_e = None
    else:
        df_empty_idx = df_empty.set_index("ID_Ruta", drop=False)
        df_sug = _sugerir_empty(df_empty_idx, ruta_p)

        hay_match = not df_sug.empty and _coincide(
            _origen_usa(df_sug.iloc[0]) if es_subida else _destino_usa(df_sug.iloc[0]),
            ref_loc,
        )
        n_sug = len(df_sug)
        st.markdown(
            f"📊 Se encontraron **{n_sug} rutas Empty posibles**"
            + (f" — ✅ {len(df_sug[df_sug.apply(lambda r: _coincide(_origen_usa(r) if es_subida else _destino_usa(r), ref_loc), axis=1)])} "
               f"con {'origen' if es_subida else 'destino'} en **{ref_loc}**" if hay_match else
               f" — ℹ️ Ninguna coincide exactamente con **{ref_loc}**, se muestran todas ordenadas.")
        )

        idx_e = st.selectbox(
            "Selecciona ruta Empty sugerida",
            options=[""] + df_sug.index.tolist(),
            format_func=lambda i: "— Sin tramo vacío —" if i == "" else _label_ruta(df_sug.loc[i]),
            key="sl_sim_sel_e",
        )
        ruta_e = df_sug.loc[idx_e] if idx_e else None

        if ruta_e is not None:
            with st.expander("📋 Ver detalles del tramo vacío seleccionado", expanded=False):
                e1, e2 = st.columns(2)
                with e1:
                    st.markdown(f"**ID:** {ruta_e.get('ID_Ruta','')}")
                    st.markdown(f"**Ruta USA:** {ruta_e.get('Ruta_USA','')}")
                with e2:
                    st.markdown(f"**Miles Load:** {safe(ruta_e.get('Miles_Load')):.0f} mi")
                    st.markdown(f"**Ingreso:** ${safe(ruta_e.get('Ingreso_Global')):,.2f}")
                    st.markdown(f"**Ut. Bruta:** ${safe(ruta_e.get('Utilidad_Bruta')):,.2f} ({safe(ruta_e.get('Pct_Ut_Bruta')):.1f}%)")

    # ── BOTÓN SIMULAR ─────────────────────────────────────────────
    divider()
    b1, b2, b3 = st.columns([1, 2, 1])
    with b2:
        if st.button("🚛 Simular Vuelta Redonda", type="primary", use_container_width=True, key="sl_sim_btn"):
            rutas = [ruta_p] + ([ruta_e] if ruta_e is not None else [])
            st.session_state["sl_sim_rutas"]   = [r.to_dict() for r in rutas]
            st.session_state["sl_sim_ruta_p"]  = ruta_p.to_dict()
            st.session_state["sl_sim_ruta_e"]  = ruta_e.to_dict() if ruta_e is not None else None
            st.session_state["sl_sim_realizada"] = True
            st.rerun()

    # ── RESULTADOS ────────────────────────────────────────────────
    if st.session_state.get("sl_sim_realizada"):
        rutas_dict  = st.session_state["sl_sim_rutas"]
        ruta_p_dict = st.session_state["sl_sim_ruta_p"]
        ruta_e_dict = st.session_state["sl_sim_ruta_e"]

        rutas_series = [pd.Series(r) for r in rutas_dict]
        ruta_p_s     = pd.Series(ruta_p_dict)
        ruta_e_s     = pd.Series(ruta_e_dict) if ruta_e_dict else None

        divider()
        section_header("📊", "Resumen de Vuelta Redonda")
        res = _resumen_vr(rutas_series)

        # Ruta visual
        divider()
        section_header("🗺️", "Secuencia de la Ruta Completa")
        _ruta_visual(ruta_p_s, ruta_e_s)

        # Detalle por tramo
        _detalle_tramos(rutas_series, ruta_p_s, ruta_e_s)

        # PDF
        divider()
        section_header("📥", "Descargar Reporte")
        try:
            pdf_bytes = _generar_pdf(rutas_series, res, ruta_p_s, ruta_e_s)
            nombre_pdf = (
                f"VR_SetLogis_{ruta_p_dict.get('ID_Ruta','')}_{ruta_p_dict.get('Cliente','').replace(' ','_')}.pdf"
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
