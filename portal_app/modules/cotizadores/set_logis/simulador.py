"""
simulador.py – Set Logis Plus
Homologado con Lincoln:
  - _cargar_rutas / _label_ruta eliminados — vienen de _shared.py
  - _resumen_vr() devuelve dict canónico con umbral_* → mostrar_resultados_ruta(res)
  - banner_tarifa_sugerida() antes de los 5 KPI cards
  - st.session_state["sl_sim_resultado"] = res
  - Prefijos sl_sim_* en todos los keys

Funciones locales que se CONSERVAN (complejas, únicas para Set Logis):
  - _construir_pasos()   → arma la lista de nodos para ruta_visual_nodos()
  - _sugerir_regresos()  → lógica de candidatas NB↔SB/D2D
  - _detalle_tramos()    → expanders por tramo con campos propios
  - _generar_pdf()       → reportlab VR

Flujo:
  Paso 1 → Selecciona ruta principal (NB / SB / D2DNB / D2DSB)
  Paso 2 → Sugerencias de regreso ordenadas por % Ut. Bruta combinada
  Paso 3 → Botón "Simular" → banner + 5 cards canónicas + semáforos
  Paso 4 → Detalle de cada tramo en expanders
  Paso 5 → Descarga PDF
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
from ui.components import (
    section_header, alert, divider, ruta_visual_nodos,
)
from ._helpers import (
    TABLE_RUTAS,
    UMBRAL_CD,
    UMBRAL_UB,
    UMBRAL_CI,
    UMBRAL_UN,
    DEFAULTS,
    safe,
    cargar_datos_generales,
    load_rutas_setlogis,
    label_ruta_setlogis,
    mostrar_resultados_setlogis,
)

TIPOS_PRINCIPAL = {"NB", "SB", "D2DNB", "D2DSB"}
TIPO_EMPTY      = "Empty"

_REGRESO = {
    "NB":    {"SB",  "D2DSB"},
    "SB":    {"NB",  "D2DNB"},
    "D2DNB": {"SB",  "D2DSB"},
    "D2DSB": {"NB",  "D2DNB"},
}


# ─────────────────────────────────────────────
# HELPERS GEOGRÁFICOS — locales, específicos del modelo road-trip
# ─────────────────────────────────────────────
def _get(ruta, key: str) -> str:
    v = ruta.get(key, "") if hasattr(ruta, "get") else ""
    return str(v).strip().upper() if v else ""


def _origen_usa(ruta) -> str:
    return _get(ruta, "Origen")


def _destino_usa(ruta) -> str:
    return _get(ruta, "Destino")


def _primer_punto(ruta) -> str:
    """De dónde sale la ruta (D2DNB sale de MX, el resto de USA)."""
    if _get(ruta, "Tipo_Viaje") == "D2DNB":
        return _get(ruta, "Origen_MX") or _origen_usa(ruta)
    return _origen_usa(ruta)


def _ultimo_punto(ruta) -> str:
    """Dónde termina la ruta (D2DSB termina en MX, el resto en USA)."""
    if _get(ruta, "Tipo_Viaje") == "D2DSB":
        return _get(ruta, "Destino_MX") or _destino_usa(ruta)
    return _destino_usa(ruta)


def _coincide(a: str, b: str) -> bool:
    return bool(a) and bool(b) and a.upper() == b.upper()


# ─────────────────────────────────────────────
# SUGERENCIAS DE REGRESO — lógica de negocio, local
# ─────────────────────────────────────────────
def _sugerir_regresos(
    df: pd.DataFrame,
    ruta_p: pd.Series,
) -> list[dict]:
    """Candidatas de regreso directas y con empty de puente, ordenadas por %Ut.B combinada."""
    tipo_p    = _get(ruta_p, "Tipo_Viaje")
    ing_p     = safe(ruta_p.get("Ingreso_Global", 0))
    ub_p      = safe(ruta_p.get("Utilidad_Bruta", 0))
    fin_p     = _ultimo_punto(ruta_p)
    tipos_reg = _REGRESO.get(tipo_p, set())

    df_regreso = df[df["Tipo_Viaje"].isin(tipos_reg)].copy() if "Tipo_Viaje" in df.columns else pd.DataFrame()
    df_empty   = df[df["Tipo_Viaje"] == TIPO_EMPTY].copy()   if "Tipo_Viaje" in df.columns else pd.DataFrame()

    candidatas: list[dict] = []

    # Opción A: Regreso directo sin empty
    for _, r in df_regreso.iterrows():
        if not _coincide(_primer_punto(r), fin_p):
            continue
        ing_r = safe(r.get("Ingreso_Global", 0))
        ub_r  = safe(r.get("Utilidad_Bruta", 0))
        ing_t = ing_p + ing_r
        ub_t  = ub_p  + ub_r
        pct   = (ub_t / ing_t * 100) if ing_t > 0 else 0.0
        candidatas.append({
            "label": (
                f"✅ DIRECTO · {r.get('ID_Ruta','')} | {r.get('Tipo_Viaje','')} | "
                f"{r.get('Cliente','—')} | {r.get('Origen','')} → {r.get('Destino','')} · "
                f"Ut.B comb. {pct:.1f}%"
            ),
            "ut_bruta":     ub_t,
            "pct_ut_bruta": pct,
            "ruta_r":       r.to_dict(),
            "ruta_e":       None,
        })

    # Opción B: Empty como puente + regreso
    for _, e in df_empty.iterrows():
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
                "label": (
                    f"🔄 CON VACÍO · [{e.get('ID_Ruta','')} {e.get('Origen','')} → {e.get('Destino','')}] + "
                    f"{r.get('ID_Ruta','')} | {r.get('Tipo_Viaje','')} | "
                    f"{r.get('Cliente','—')} | {r.get('Origen','')} → {r.get('Destino','')} · "
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
# CONSTRUIR PASOS PARA ruta_visual_nodos()
# Función auxiliar — solo usada en este módulo
# ─────────────────────────────────────────────
def _construir_pasos(ruta_p: pd.Series, ruta_e: pd.Series | None, ruta_r: pd.Series | None) -> list:
    tipo_p = _get(ruta_p, "Tipo_Viaje")
    pasos: list = []

    if tipo_p == "D2DNB":
        om = _get(ruta_p, "Origen_MX"); dm = _get(ruta_p, "Destino_MX")
        if om:
            pasos += [{"icono": "🇲🇽", "ciudad": om, "etiqueta": "Origen MX"}, "→"]
        if dm:
            pasos += [{"icono": "📍", "ciudad": dm, "etiqueta": "Destino MX"}, "→"]

    pasos += [
        {"icono": "🇺🇸", "ciudad": _origen_usa(ruta_p),  "etiqueta": f"Origen USA ({tipo_p})"},
        "→",
        {"icono": "📍",  "ciudad": _destino_usa(ruta_p), "etiqueta": "Destino USA"},
    ]

    if tipo_p == "D2DSB":
        om = _get(ruta_p, "Origen_MX"); dm = _get(ruta_p, "Destino_MX")
        if om:
            pasos += ["→", {"icono": "🛂", "ciudad": om, "etiqueta": "Origen MX"}]
        if dm:
            pasos += ["→", {"icono": "🇲🇽", "ciudad": dm, "etiqueta": "Destino MX"}]

    if ruta_e is not None:
        pasos += [
            "→",
            {"icono": "⬜", "ciudad": _origen_usa(ruta_e),  "etiqueta": f"Empty · {_get(ruta_e,'ID_Ruta')}"},
            "→",
            {"icono": "⬜", "ciudad": _destino_usa(ruta_e), "etiqueta": "Fin Empty"},
        ]

    if ruta_r is not None:
        tipo_r = _get(ruta_r, "Tipo_Viaje")
        if tipo_r == "D2DNB":
            om = _get(ruta_r, "Origen_MX")
            if om:
                pasos += ["→", {"icono": "🇲🇽", "ciudad": om, "etiqueta": "Origen MX Reg."}]
            pasos += [
                "→",
                {"icono": "🇺🇸", "ciudad": _origen_usa(ruta_r),  "etiqueta": f"Origen USA ({tipo_r})"},
                "→",
                {"icono": "🏁",  "ciudad": _destino_usa(ruta_r), "etiqueta": "Destino USA Reg."},
            ]
        else:
            pasos += ["→", {"icono": "🇺🇸", "ciudad": _origen_usa(ruta_r), "etiqueta": f"Origen USA ({tipo_r})"}, "→"]
            if tipo_r == "D2DSB":
                pasos.append({"icono": "📍", "ciudad": _destino_usa(ruta_r), "etiqueta": "Destino USA Reg."})
                dm = _get(ruta_r, "Destino_MX")
                if dm:
                    pasos += ["→", {"icono": "🏁", "ciudad": dm, "etiqueta": "Destino MX Reg."}]
            else:
                pasos.append({"icono": "🏁", "ciudad": _destino_usa(ruta_r), "etiqueta": "Destino Reg."})

    return pasos

# ─────────────────────────────────────────────
# RESUMEN VR — devuelve dict canónico para mostrar_resultados_ruta()
# ─────────────────────────────────────────────
def _resumen_vr(rutas: list[pd.Series], valores: dict) -> dict:
    def _s(campo):
        return sum(safe(r.get(campo, 0)) for r in rutas)

    ing = _s("Ingreso_Global")
    cd  = _s("Costo_Directo")
    ci  = _s("Costo_Indirecto")
    ct  = cd + ci
    ub  = ing - cd
    un  = ing - ct
    ml  = _s("Short_Miles") + _s("Miles_Empty")

    def _pct(n, d): return (n / d * 100) if d > 0 else 0.0

    pct_cd = _pct(cd, ing)
    pct_ci = _pct(ci, ing)
    pct_ub = _pct(ub, ing)
    pct_un = _pct(un, ing)

    # Colores con umbrales reales de Set Logis
    color_dir  = "#059669" if pct_cd <= UMBRAL_CD else "#DC2626"
    color_ind  = "#059669" if pct_ci <= UMBRAL_CI else "#D97706"
    color_ut_n = "#059669" if pct_un >= UMBRAL_UN else "#DC2626"

    # Métrica extra de ingreso por milla
    st.metric("📏 Ingreso/Milla VR", f"${(ing/ml):,.3f}" if ml > 0 else "—")

    return {
        # Alias canónicos requeridos por mostrar_resultados_ruta()
        "ingreso_total":       ing,
        "costo_directo":       cd,
        "utilidad_bruta":      ub,
        "costos_indirectos":   ci,
        "utilidad_neta":       un,
        "moneda_display":      "USD",
        # Porcentajes para las sub-labels de las cards
        "Pct_Costo_Directo":   pct_cd,
        "Pct_Ut_Bruta":        pct_ub,
        "Pct_Costo_Indirecto": pct_ci,
        "Pct_Ut_Neta":         pct_un,
        # Colores semáforo
        "Color_Directo":       color_dir,
        "Color_Indirecto":     color_ind,
        "Color_Ut_Neta":       color_ut_n,
        # Umbrales — viajan en el dict para semaforos_ruta()
        "umbral_cd":           UMBRAL_CD,
        "umbral_ub":           UMBRAL_UB,
        "umbral_ci":           UMBRAL_CI,
        "umbral_un":           UMBRAL_UN,
        # Campos extra para PDF y métricas adicionales
        "Ingreso_Global":      ing,
        "Costo_Directo":       cd,
        "Costo_Indirecto":     ci,
        "Costo_Total":         ct,
        "Utilidad_Bruta":      ub,
        "Utilidad_Neta":       un,
        "ml":                  ml,
        "pct_cd":              pct_cd,
        "pct_ci":              pct_ci,
        "pct_ub":              pct_ub,
        "pct_un":              pct_un,
        "TC":                  safe(valores.get("Tipo de Cambio USD/MXP", 18.50)),
    }


# ─────────────────────────────────────────────
# DETALLE POR TRAMO — local, muestra campos propios de Set Logis
# ─────────────────────────────────────────────
def _detalle_tramos(rutas: list[pd.Series], etiquetas: list[str]) -> None:
    divider()
    section_header("📋", "Detalle por Tramo")

    for i, (label, ruta) in enumerate(zip(etiquetas, rutas)):
        titulo = (
            f"{label} — {ruta.get('ID_Ruta','')} · "
            f"{ruta.get('Cliente','—')} · {ruta.get('Origen','')} → {ruta.get('Destino','')}"
        )
        with st.expander(titulo, expanded=(i == 0)):
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("**Ingresos**")
                st.caption(f"Flete USA: **${safe(ruta.get('Flete_USA')):,.2f}**")
                if safe(ruta.get("Fuel")) > 0:
                    st.caption(f"Fuel: **${safe(ruta.get('Fuel')):,.2f}**")
                if safe(ruta.get("Ingreso_Cruce")) > 0:
                    st.caption(f"Cruce: **${safe(ruta.get('Ingreso_Cruce')):,.2f}**")
                if safe(ruta.get("Ingreso_MX")) > 0:
                    st.caption(f"MX: **${safe(ruta.get('Ingreso_MX')):,.2f}**")
                if safe(ruta.get("Extras_Ingreso")) > 0:
                    st.caption(f"Extras: **${safe(ruta.get('Extras_Ingreso')):,.2f}**")
                st.markdown(f"**Total: ${safe(ruta.get('Ingreso_Global')):,.2f}**")
            with c2:
                st.markdown("**Costos**")
                st.caption(f"Owner Cargado: **${safe(ruta.get('Pago_Owner_Cargado')):,.2f}**")
                st.caption(f"Owner Vacío: **${safe(ruta.get('Pago_Owner_Vacio')):,.2f}**")
                if ruta.get("Fuel_Owner"):
                    st.caption(f"⛽ Fuel Owner: **${safe(ruta.get('Pago_Fuel_Owner')):,.2f}**")
                if safe(ruta.get("Costo_Cruce")) > 0:
                    st.caption(f"Cruce: **${safe(ruta.get('Costo_Cruce')):,.2f}**")
                if safe(ruta.get("Costo_MX")) > 0:
                    st.caption(f"MX: **${safe(ruta.get('Costo_MX')):,.2f}**")
                st.markdown(f"**C.Dir: ${safe(ruta.get('Costo_Directo')):,.2f}**")
            with c3:
                st.markdown("**Margen**")
                st.caption(f"Ut. Bruta: **${safe(ruta.get('Utilidad_Bruta')):,.2f}** ({safe(ruta.get('Pct_Ut_Bruta')):.1f}%)")
                st.caption(f"C. Indirecto: **${safe(ruta.get('Costo_Indirecto')):,.2f}** ({safe(ruta.get('Pct_Costo_Indirecto')):.1f}%)")
                st.caption(f"Ut. Neta: **${safe(ruta.get('Utilidad_Neta')):,.2f}** ({safe(ruta.get('Pct_Ut_Neta')):.1f}%)")
                st.caption(f"Short Mi: **{safe(ruta.get('Short_Miles')):.0f}** · Mi Vacías: **{safe(ruta.get('Miles_Empty')):.0f}**")


# ─────────────────────────────────────────────
# PDF VR — local, único para Set Logis
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
        leftMargin=0.6*inch, rightMargin=0.6*inch,
        topMargin=0.5*inch,  bottomMargin=0.5*inch,
    )
    styles   = getSampleStyleSheet()
    title_s  = ParagraphStyle("T", parent=styles["Title"],   fontSize=14,
                               textColor=colors.HexColor("#1B2266"), spaceAfter=4)
    sub_s    = ParagraphStyle("S", parent=styles["Heading2"], fontSize=10,
                               textColor=colors.HexColor("#1B2266"), spaceBefore=10, spaceAfter=3)
    normal_s = ParagraphStyle("N", parent=styles["Normal"],  fontSize=8, leading=11)
    footer_s = ParagraphStyle("F", parent=styles["Normal"],  fontSize=7,
                               textColor=colors.HexColor("#6c757d"), alignment=TA_CENTER)
    story = []

    # Encabezado
    hdr = Table([[
        Paragraph("<b>SET LOGIS PLUS</b>",
                  ParagraphStyle("H",  parent=styles["Normal"], fontSize=13, textColor=colors.white)),
        Paragraph("Simulador de Vuelta Redonda",
                  ParagraphStyle("HR", parent=styles["Normal"], fontSize=9,
                                 textColor=colors.white, alignment=TA_RIGHT)),
    ]], colWidths=[4.5*inch, 2.5*inch])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), colors.HexColor("#1B2266")),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0),(-1,-1), 10),
        ("BOTTOMPADDING", (0,0),(-1,-1), 10),
        ("LEFTPADDING",   (0,0),(0,-1),  12),
        ("RIGHTPADDING",  (-1,0),(-1,-1),12),
    ]))
    story += [hdr, Spacer(1, 10)]

    # Resumen global
    story.append(Paragraph("Resumen de Vuelta Redonda", sub_s))
    resumen_data = [
        ["Concepto",        "Monto (USD)",                    "%"],
        ["Ingreso Total",   f"${res['Ingreso_Global']:,.2f}", "100.00%"],
        ["Costo Directo",   f"${res['Costo_Directo']:,.2f}",  f"{res['pct_cd']:.2f}%"],
        ["Ut. Bruta",        f"${res['Utilidad_Bruta']:,.2f}",  f"{res['pct_ub']:.2f}%"],
        ["Costo Indirecto", f"${res['Costo_Indirecto']:,.2f}", f"{res['pct_ci']:.2f}%"],
        ["UT. NETA",        f"${res['Utilidad_Neta']:,.2f}",  f"{res['pct_un']:.2f}%"],
    ]
    t_res = Table(resumen_data, colWidths=[3.0*inch, 2.5*inch, 1.4*inch])
    t_res.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0),  colors.HexColor("#1B2266")),
        ("TEXTCOLOR",     (0,0),(-1,0),  colors.white),
        ("FONTNAME",      (0,0),(-1,0),  "Helvetica-Bold"),
        ("FONTNAME",      (0,-1),(-1,-1),"Helvetica-Bold"),
        ("FONTSIZE",      (0,0),(-1,-1), 8),
        ("ROWBACKGROUNDS",(0,1),(-1,-2), [colors.white, colors.HexColor("#F0F4FF")]),
        ("BACKGROUND",    (0,-1),(-1,-1),colors.HexColor("#E8F5E9")),
        ("GRID",          (0,0),(-1,-1), 0.3, colors.HexColor("#CCCCCC")),
        ("TOPPADDING",    (0,0),(-1,-1), 4),
        ("BOTTOMPADDING", (0,0),(-1,-1), 4),
        ("LEFTPADDING",   (0,0),(-1,-1), 6),
    ]))
    story += [t_res, Spacer(1, 8)]

    # Secuencia road trip
    story.append(Paragraph("Secuencia del Road Trip", sub_s))
    pasos_txt: list[str] = []
    tipo_p = _get(ruta_p, "Tipo_Viaje")
    if tipo_p == "D2DNB":
        om = _get(ruta_p, "Origen_MX")
        if om: pasos_txt.append(f"Origen MX: {om}")
    pasos_txt.append(f"Origen USA ({tipo_p}): {_origen_usa(ruta_p)}")
    pasos_txt.append(f"Destino USA: {_destino_usa(ruta_p)}")
    if tipo_p == "D2DSB":
        dm = _get(ruta_p, "Destino_MX")
        if dm: pasos_txt.append(f"Destino MX: {dm}")
    if ruta_e is not None:
        pasos_txt.append(f"Empty {_get(ruta_e,'ID_Ruta')}: {_origen_usa(ruta_e)} → {_destino_usa(ruta_e)}")
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
        story.append(Paragraph(
            f"<b>{label} — {ruta.get('ID_Ruta','')} · {ruta.get('Cliente','—')}</b>",
            normal_s,
        ))
        story.append(Spacer(1, 3))
        tramo_data = [
            ["Campo",       "Valor",                                    "Campo",       "Valor"],
            ["Tipo",        str(ruta.get("Tipo_Viaje","")),             "Fecha",       str(ruta.get("Fecha",""))],
            ["Ruta USA",    f"{ruta.get('Origen','')} → {ruta.get('Destino','')}",  "Modo",  str(ruta.get("Modo",""))],
            ["Short Miles", f"{safe(ruta.get('Short_Miles')):.0f} mi",  "Miles Empty", f"{safe(ruta.get('Miles_Empty')):.0f} mi"],
            ["Ingreso",     f"${safe(ruta.get('Ingreso_Global')):,.2f}","Costo Dir.",  f"${safe(ruta.get('Costo_Directo')):,.2f}"],
            ["Ut. Bruta",
             f"${safe(ruta.get('Utilidad_Bruta')):,.2f} ({safe(ruta.get('Pct_Ut_Bruta')):.1f}%)",
             "Ut. Neta",
             f"${safe(ruta.get('Utilidad_Neta')):,.2f} ({safe(ruta.get('Pct_Ut_Neta')):.1f}%)"],
        ]
        t_tramo = Table(tramo_data, colWidths=[1.4*inch, 2.0*inch, 1.4*inch, 2.0*inch])
        t_tramo.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,0),  colors.HexColor("#1B2266")),
            ("TEXTCOLOR",     (0,0),(-1,0),  colors.white),
            ("FONTNAME",      (0,0),(-1,0),  "Helvetica-Bold"),
            ("BACKGROUND",    (0,1),(0,-1),  colors.HexColor("#EEF2FF")),
            ("BACKGROUND",    (2,1),(2,-1),  colors.HexColor("#EEF2FF")),
            ("FONTNAME",      (0,1),(0,-1),  "Helvetica-Bold"),
            ("FONTNAME",      (2,1),(2,-1),  "Helvetica-Bold"),
            ("FONTSIZE",      (0,0),(-1,-1), 7),
            ("GRID",          (0,0),(-1,-1), 0.5, colors.HexColor("#dee2e6")),
            ("TOPPADDING",    (0,0),(-1,-1), 2),
            ("BOTTOMPADDING", (0,0),(-1,-1), 2),
            ("LEFTPADDING",   (0,0),(-1,-1), 5),
        ]))
        story += [t_tramo, Spacer(1, 8)]

    story += [Spacer(1, 16), Paragraph(
        f"Reporte generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} — Set Logis Plus",
        footer_s,
    )]
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
            load_rutas_setlogis.clear()
            st.rerun()
    with r2:
        st.caption("Carga cacheada 2 min.")

    st.session_state.setdefault("sl_sim_realizada", False)
    st.session_state.setdefault("sl_sim_datos",     None)
    st.session_state.setdefault("sl_sim_resultado", None)

    valores = cargar_datos_generales()
    tc      = safe(valores.get("Tipo de Cambio USD/MXP", DEFAULTS.get("Tipo de Cambio USD/MXP", 18.50)))

    df = load_rutas_setlogis(TABLE_RUTAS)
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

    idx_p = st.selectbox(
        f"Ruta principal ({len(df_pf)} disponibles)",
        options=df_pf.index.tolist(),
        format_func=lambda i: label_ruta_setlogis(df_pf.loc[i].to_dict()),
        key="sl_sim_sel_p",
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
            st.markdown(f"**Ruta USA:** {ruta_p.get('Origen','')} → {ruta_p.get('Destino','')}")
            st.markdown(f"**Último punto:** {_ultimo_punto(ruta_p)}")
            st.markdown(f"**Ingreso:** ${safe(ruta_p.get('Ingreso_Global')):,.2f}")
            st.markdown(f"**Costo Dir.:** ${safe(ruta_p.get('Costo_Directo')):,.2f}")
            st.markdown(f"**Ut. Bruta:** ${safe(ruta_p.get('Utilidad_Bruta')):,.2f} ({safe(ruta_p.get('Pct_Ut_Bruta')):.1f}%)")

    # ══════════════════════════════════════════════════════════════
    # PASO 2: Sugerencias de regreso
    # ══════════════════════════════════════════════════════════════
    divider()
    section_header("🔁", "Paso 2 — Selecciona el Regreso")

    candidatas = _sugerir_regresos(df, ruta_p)

    ruta_e     = None
    ruta_r_sel = None

    if candidatas:
        n_dir   = sum(1 for c in candidatas if c["ruta_e"] is None)
        n_vacio = len(candidatas) - n_dir
        st.caption(
            f"📊 **{len(candidatas)} combinaciones** encontradas — "
            f"{n_dir} directas · {n_vacio} con tramo vacío · ordenadas por Ut.B combinada"
        )
        opciones_labels = ["— Sin regreso —"] + [c["label"] for c in candidatas]
        sel_cand = st.selectbox(
            "Combinación de regreso",
            options=opciones_labels,
            label_visibility="collapsed",
            key="sl_sim_sel_r",
        )
        if sel_cand == "— Sin regreso —":
            ruta_e     = None
            ruta_r_sel = None
        else:
            cand       = candidatas[opciones_labels.index(sel_cand) - 1]
            ruta_r_sel = pd.Series(cand["ruta_r"]) if cand["ruta_r"] else None
            ruta_e     = pd.Series(cand["ruta_e"]) if cand["ruta_e"] else None
            with st.expander("📋 Ver detalle de la combinación seleccionada", expanded=False):
                if ruta_e is not None:
                    st.markdown(
                        f"**Tramo vacío:** {ruta_e.get('ID_Ruta','')} · "
                        f"{_origen_usa(ruta_e)} → {_destino_usa(ruta_e)} · "
                        f"Ut.B ${safe(ruta_e.get('Utilidad_Bruta')):,.2f} "
                        f"({safe(ruta_e.get('Pct_Ut_Bruta')):.1f}%)"
                    )
                if ruta_r_sel is not None:
                    st.markdown(
                        f"**Regreso:** {ruta_r_sel.get('ID_Ruta','')} · "
                        f"{ruta_r_sel.get('Tipo_Viaje','')} · "
                        f"{ruta_r_sel.get('Cliente','—')} · "
                        f"{_origen_usa(ruta_r_sel)} → {_destino_usa(ruta_r_sel)} · "
                        f"Ut.B ${safe(ruta_r_sel.get('Utilidad_Bruta')):,.2f} "
                        f"({safe(ruta_r_sel.get('Pct_Ut_Bruta')):.1f}%)"
                    )
                st.markdown(f"**Ut.B combinada:** ${cand['ut_bruta']:,.2f} ({cand['pct_ut_bruta']:.1f}%)")
    else:
        alert("info", "No se encontraron combinaciones de regreso compatibles con esta ruta.")

    # ══════════════════════════════════════════════════════════════
    # BOTÓN SIMULAR — solo cuando NO hay simulación activa
    # ══════════════════════════════════════════════════════════════
    if not st.session_state.get("sl_sim_realizada"):
        divider()
        b1, b2, b3 = st.columns([1, 2, 1])
        with b2:
            if st.button("🚛 Simular Vuelta Redonda", type="primary",
                         use_container_width=True, key="sl_sim_btn"):

                rutas_lista: list[dict] = [ruta_p.to_dict()]
                etiq_lista:  list[str]  = ["🚛 Ruta Principal"]

                if ruta_e is not None:
                    rutas_lista.append(ruta_e.to_dict())
                    etiq_lista.append("⬜ Tramo Vacío")

                if ruta_r_sel is not None:
                    rutas_lista.append(ruta_r_sel.to_dict())
                    etiq_lista.append("🔁 Regreso")

                st.session_state["sl_sim_datos"] = {
                    "rutas":     rutas_lista,
                    "etiquetas": etiq_lista,
                    "ruta_p":    ruta_p.to_dict(),
                    "ruta_e":    ruta_e.to_dict()     if ruta_e     is not None else None,
                    "ruta_r":    ruta_r_sel.to_dict() if ruta_r_sel is not None else None,
                }
                st.session_state["sl_sim_realizada"] = True
                st.session_state["sl_sim_resultado"]  = None
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

        # Calcular y guardar el dict canónico del VR
        res = _resumen_vr(rutas_series, valores)
        st.session_state["sl_sim_resultado"] = res

        # 1 línea — igual que Lincoln, sin desglose (ese va en _detalle_tramos)
        mostrar_resultados_setlogis(res, mostrar_desglose=False)

        divider()
        section_header("🗺️", "Secuencia del Road Trip")
        ruta_visual_nodos(_construir_pasos(ruta_p_s, ruta_e_s, ruta_r_s))

        _detalle_tramos(rutas_series, etiquetas)

        divider()
        section_header("📥", "Descargar Reporte")
        try:
            pdf_bytes = _generar_pdf(rutas_series, etiquetas, res, ruta_p_s, ruta_e_s, ruta_r_s)
            nombre_pdf = (
                f"VR_SetLogis_{datos['ruta_p'].get('ID_Ruta','')}_"
                f"{datos['ruta_p'].get('Cliente','').replace(' ','_')}.pdf"
            )
            st.download_button(
                label="📄 Descargar PDF Vuelta Redonda",
                data=pdf_bytes,
                file_name=nombre_pdf,
                mime="application/pdf",
                use_container_width=True,
                key="sl_sim_dl_pdf",
            )
        except Exception as ex:
            alert("error", f"Error generando PDF: {ex}")

        if st.button("🔄 Nueva simulación", key="sl_sim_nueva"):
            st.session_state.pop("sl_sim_realizada", None)
            st.session_state.pop("sl_sim_datos",     None)
            st.session_state.pop("sl_sim_resultado", None)
            st.rerun()
