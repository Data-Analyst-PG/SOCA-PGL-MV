"""
consulta_ruta.py — Cotizador Picus
Diseño homologado con Igloo:
  - Sin st.title(), filtros con expander, selector label completo
  - Simulación via helpers.py
  - Resultados con mostrar_resultados_utilidad
  - Desglose en expander con st.caption()
  - PDF profesional con reportlab (mismo estilo que Igloo, campos de Picus)
"""
from __future__ import annotations

import tempfile
from datetime import datetime
from io import BytesIO

import pandas as pd
import streamlit as st
from reportlab.lib import colors
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
    with st.expander("🔎 Filtros de búsqueda (opcional)", expanded=False):
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
        f"{row.get('Origen','')} → {row.get('Destino','')}"
    )


# ─────────────────────────────────────────────
# PDF profesional (mismo estilo que Igloo)
# ─────────────────────────────────────────────

def _safe_txt(text: str) -> str:
    try:
        return str(text).encode("latin-1", "replace").decode("latin-1")
    except Exception:
        return str(text)


def _tabla_std(data: list, col_widths: list) -> Table:
    """Tabla con header azul oscuro, filas alternas y números alineados a la derecha."""
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor("#1B2266")),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTNAME",      (0, 1), (0, -1),  "Helvetica-Bold"),
        ("BACKGROUND",    (0, 1), (0, -1),  colors.HexColor("#f5f5f5")),
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
    """Genera el PDF y devuelve la ruta al archivo temporal."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    doc = SimpleDocTemplate(
        tmp.name, pagesize=letter,
        leftMargin=0.5 * inch, rightMargin=0.5 * inch,
        topMargin=0.5 * inch,  bottomMargin=0.5 * inch,
    )

    styles = getSampleStyleSheet()
    AZUL   = colors.HexColor("#1B2266")

    title_s    = ParagraphStyle("T",  parent=styles["Normal"], fontSize=14,
                                fontName="Helvetica-Bold", textColor=AZUL, spaceAfter=4)
    subtitle_s = ParagraphStyle("S",  parent=styles["Normal"], fontSize=10,
                                fontName="Helvetica-Bold", textColor=AZUL,
                                spaceBefore=8, spaceAfter=3)
    normal_s   = ParagraphStyle("N",  parent=styles["Normal"], fontSize=8)
    footer_s   = ParagraphStyle("F",  parent=styles["Normal"], fontSize=7,
                                textColor=colors.HexColor("#6c757d"), alignment=1)

    story = []

    # ── Encabezado ────────────────────────────────────────────────
    story.append(Paragraph(_safe_txt("Picus — Reporte de Ruta"), title_s))
    if simulando:
        story.append(Paragraph(
            _safe_txt(f"SIMULACION — Rendimiento: {rend_sim:.2f} km/L · Diesel: ${diesel_sim:.2f}/L"),
            normal_s,
        ))
    story.append(HRFlowable(width="100%", thickness=1, color=AZUL))
    story.append(Spacer(1, 6))

    # ── Datos Generales ───────────────────────────────────────────
    story.append(Paragraph(_safe_txt("Datos Generales"), subtitle_s))
    gen_data = [
        [_safe_txt("ID Ruta"),    _safe_txt(str(ruta.get("ID_Ruta",""))),
         _safe_txt("Fecha"),      _safe_txt(str(ruta.get("Fecha",""))[:10])],
        [_safe_txt("Tipo"),       _safe_txt(str(ruta.get("Tipo",""))),
         _safe_txt("Ruta Tipo"),  _safe_txt(str(ruta.get("Ruta_Tipo","")))],
        [_safe_txt("Modo"),       _safe_txt(str(ruta.get("Modo de Viaje",""))),
         _safe_txt("Cliente"),    _safe_txt(str(ruta.get("Cliente","")))],
        [_safe_txt("Origen"),     _safe_txt(str(ruta.get("Origen",""))),
         _safe_txt("Destino"),    _safe_txt(str(ruta.get("Destino","")))],
        [_safe_txt("KM"),         _safe_txt(f"{safe_number(ruta.get('KM',0)):,.0f}"),
         _safe_txt("Pago x KM"),  _safe_txt(f"${safe_number(ruta.get('Pago por KM',0)):,.4f}")],
    ]
    gen_t = Table(gen_data, colWidths=[1.4*inch, 2.2*inch, 1.4*inch, 2.2*inch])
    gen_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, -1), colors.HexColor("#EEF0F8")),
        ("BACKGROUND",    (2, 0), (2, -1), colors.HexColor("#EEF0F8")),
        ("FONTNAME",      (0, 0), (-1, -1), "Helvetica"),
        ("FONTNAME",      (0, 0), (0, -1),  "Helvetica-Bold"),
        ("FONTNAME",      (2, 0), (2, -1),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 7),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
    ]))
    story.append(gen_t)
    story.append(Spacer(1, 6))

    # ── Ingresos ─────────────────────────────────────────────────
    story.append(Paragraph(_safe_txt("Ingresos"), subtitle_s))
    ing_data = [["Concepto", "Monto"]]
    ing_data.append([_safe_txt("Ingreso Flete"),
                     _safe_txt(f"${safe_number(ruta.get('Ingreso Flete',0)):,.2f}")])
    ing_data.append([_safe_txt("Ingreso Cruce"),
                     _safe_txt(f"${safe_number(ruta.get('Ingreso Cruce',0)):,.2f}")])
    if safe_number(ruta.get("Ingresos_Extras", 0)) > 0:
        ing_data.append([_safe_txt("Ingresos Extras cobrados"),
                         _safe_txt(f"${safe_number(ruta.get('Ingresos_Extras',0)):,.2f}")])
    ing_data.append([_safe_txt("INGRESO TOTAL"),
                     _safe_txt(f"${ingreso_total:,.2f}")])
    story.append(_tabla_std(ing_data, [3.5*inch, 3.5*inch]))
    story.append(Spacer(1, 6))

    # ── Costos Operativos ─────────────────────────────────────────
    story.append(Paragraph(_safe_txt("Costos Operativos"), subtitle_s))
    rend_usado = rend_sim if simulando and rend_sim else safe_number(ruta.get("Rendimiento Camion", 2.5))
    cos_data = [["Concepto", "Monto"]]
    cos_data.append([_safe_txt(f"Diesel Camion ({rend_usado:.2f} km/L)"),
                     _safe_txt(f"${safe_number(ruta.get('Costo_Diesel_Camion',0)):,.2f}")])
    cos_data.append([_safe_txt("Sueldo Operador"),
                     _safe_txt(f"${safe_number(ruta.get('Sueldo_Operador',0)):,.2f}")])
    cos_data.append([_safe_txt("Bono ISR/IMSS"),
                     _safe_txt(f"${safe_number(ruta.get('Bono',0)):,.2f}")])
    cos_data.append([_safe_txt("Casetas"),
                     _safe_txt(f"${safe_number(ruta.get('Casetas',0)):,.2f}")])
    cos_data.append([_safe_txt("Costo Cruce"),
                     _safe_txt(f"${safe_number(ruta.get('Costo Cruce Convertido',0)):,.2f}")])
    story.append(_tabla_std(cos_data, [3.5*inch, 3.5*inch]))
    story.append(Spacer(1, 6))

    # ── Costos Fijos ─────────────────────────────────────────────
    story.append(Paragraph(_safe_txt("Costos Fijos"), subtitle_s))
    fijos_items = [
        ("Movimiento Local",  "Movimiento_Local"),
        ("Puntualidad",       "Puntualidad"),
        ("Pension",           "Pension"),
        ("Estancia",          "Estancia"),
        ("Fianza",            "Fianza"),
    ]
    fijos_data = [["Concepto", "Monto"]]
    hay_fijos = False
    for label, campo in fijos_items:
        val = safe_number(ruta.get(campo, 0))
        if val > 0:
            fijos_data.append([_safe_txt(label), _safe_txt(f"${val:,.2f}")])
            hay_fijos = True
    if not hay_fijos:
        fijos_data.append([_safe_txt("(Sin costos fijos en esta ruta)"), ""])
    story.append(_tabla_std(fijos_data, [3.5*inch, 3.5*inch]))
    story.append(Spacer(1, 6))

    # ── Otros Costos (Extras) ─────────────────────────────────────
    story.append(Paragraph(_safe_txt("Otros Costos"), subtitle_s))
    extras_items = [
        ("Pistas Extra",  "Pistas_Extra",  "Pistas_Cobrado"),
        ("Stop",          "Stop",          "Stop_Cobrado"),
        ("Falso",         "Falso",         "Falso_Cobrado"),
        ("Gatas",         "Gatas",         "Gatas_Cobrado"),
        ("Accesorios",    "Accesorios",    "Accesorios_Cobrado"),
        ("Guias",         "Guias",         "Guias_Cobrado"),
    ]
    otros_data = [["Concepto", "Monto", "Cobrado al cliente"]]
    hay_extras = False
    for label, campo, campo_cob in extras_items:
        val = safe_number(ruta.get(campo, 0))
        if val > 0:
            cobrado = "Si" if bool(ruta.get(campo_cob, False)) else "No"
            otros_data.append([_safe_txt(label), _safe_txt(f"${val:,.2f}"), _safe_txt(cobrado)])
            hay_extras = True
    if not hay_extras:
        otros_data.append([_safe_txt("(Sin costos extras en esta ruta)"), "", ""])
    story.append(_tabla_std(otros_data, [2.5*inch, 2.5*inch, 2.2*inch]))
    story.append(Spacer(1, 8))

    # ── Resumen de Utilidades ────────────────────────────────────
    story.append(Paragraph(_safe_txt("Resumen de Utilidades"), subtitle_s))
    color_un = colors.HexColor("#16a34a") if utilidad_neta >= 0 else colors.HexColor("#dc2626")
    pct_costo = (costo_total / ingreso_total * 100) if ingreso_total else 0
    pct_ind   = (costos_indirectos / ingreso_total * 100) if ingreso_total else 0

    util_data = [
        ["Concepto",             "Monto",                        "%"],
        ["Ingreso Total",        f"${ingreso_total:,.2f} MXP",   "100.00%"],
        ["Costo Directo",        f"${costo_total:,.2f} MXP",     f"{pct_costo:.1f}%"],
        ["Utilidad Bruta",       f"${utilidad_bruta:,.2f} MXP",  f"{pct_bruta:.1f}%"],
        ["Costos Indirectos",    f"${costos_indirectos:,.2f} MXP", f"{pct_ind:.1f}%"],
        ["Utilidad Neta",        f"${utilidad_neta:,.2f} MXP",   f"{pct_neta:.1f}%"],
    ]
    util_t = Table(util_data, colWidths=[2.5*inch, 2.5*inch, 2.2*inch])
    util_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor("#1B2266")),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTNAME",      (0, 1), (0, -1),  "Helvetica-Bold"),
        ("BACKGROUND",    (0, 1), (0, -1),  colors.HexColor("#f5f5f5")),
        ("BACKGROUND",    (0, 5), (-1, 5),  color_un),
        ("TEXTCOLOR",     (0, 5), (-1, 5),  colors.white),
        ("FONTNAME",      (0, 5), (-1, 5),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 7),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("ALIGN",         (1, 1), (-1, -1), "RIGHT"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
    ]))
    story.append(util_t)
    story.append(Spacer(1, 12))

    # ── Footer ───────────────────────────────────────────────────
    story.append(Paragraph(
        _safe_txt(
            f"Reporte generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} — Picus"
            + (" (SIMULACION)" if simulando else "")
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

    # ── Recargar ─────────────────────────────────────────────────────
    rc1, rc2 = st.columns([1, 4])
    with rc1:
        if st.button("🔄 Recargar rutas", key="pic_cons_reload"):
            _load_rutas_picus_cached.clear()
            st.rerun()
    with rc2:
        st.caption("Carga cacheada 2 min. Usa 'Recargar' si acabas de guardar algo.")

    valores = cargar_datos_generales()
    df      = _load_rutas_picus_cached()

    if df.empty:
        alert("warn", "⚠️ No hay rutas guardadas todavía.")
        return

    if "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.date
    if "ID_Ruta" in df.columns:
        df.set_index("ID_Ruta", inplace=True, drop=False)

    # ── Filtros y selector ────────────────────────────────────────────
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

    # ── Simulación ────────────────────────────────────────────────────
    divider()
    section_header("⚙️", "Ajustes para Simulación")
    st.caption("Ajusta diesel y rendimiento para ver el impacto sin modificar la ruta.")

    sim1, sim2 = st.columns(2)
    costo_diesel_input = sim1.number_input(
        "Costo del Diesel ($/L)",
        value=float(valores.get("Costo Diesel", 24.0)),
        key="pic_cons_diesel",
    )
    st.markdown(f"> Rendimiento registrado: **{rend_reg:.2f} km/L**")
    rendimiento_input = sim2.number_input(
        "Rendimiento para Simulación (km/L)",
        value=float(rend_reg),
        key="pic_cons_rend",
    )

    colA, colB = st.columns(2)
    with colA:
        if st.button("🔁 Simular", key="pic_cons_sim"):
            st.session_state["pic_simular"] = True
    with colB:
        if st.button("🔄 Volver a valores reales", key="pic_cons_reset"):
            st.session_state["pic_simular"] = False
            st.rerun()

    simular = st.session_state.get("pic_simular", False)

    # ── Cálculo ───────────────────────────────────────────────────────
    ingreso_total = safe_number(ruta.get("Ingreso Total", 0))
    km            = safe_number(ruta.get("KM", 0))

    if simular:
        valores_sim = {"Rendimiento Camion": rendimiento_input, "Costo Diesel": costo_diesel_input}
        costo_diesel_camion = calcular_diesel(km, valores_sim)
        alert("success", "🔧 Estás viendo una **simulación** con diesel/rendimiento ajustados.")
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

    # ── Resultados ────────────────────────────────────────────────────
    divider()
    section_header("📊", "Resultado de la Ruta")

    tc_usd = safe_float(valores.get("Tipo de cambio USD", 17.5))
    mostrar_resultados_utilidad(
        st,
        ingreso_total, costo_total,
        util["utilidad_bruta"], util["costos_indirectos"],
        util["utilidad_neta"], util["porcentaje_bruta"], util["porcentaje_neta"],
        tipo=tipo_ruta,
        tc_usd=tc_usd if str(ruta.get("Moneda", "")) == "USD" else 0.0,
    )

    # ── Desglose detallado ────────────────────────────────────────────
    divider()
    with st.expander("📋 Desglose detallado de la ruta", expanded=False):
        c1, c2, c3 = st.columns(3)

        with c1:
            st.markdown("### 📋 Información General")
            st.caption(f"**ID:** {ruta.get('ID_Ruta','')}")
            st.caption(f"**Fecha:** {str(ruta.get('Fecha',''))[:10]}")
            st.caption(f"**Tipo:** {ruta.get('Tipo','')}")
            st.caption(f"**Ruta Tipo:** {ruta.get('Ruta_Tipo','')}")
            st.caption(f"**Modo de Viaje:** {ruta.get('Modo de Viaje','')}")
            st.caption(f"**Cliente:** {ruta.get('Cliente','')}")
            st.caption(f"**Origen → Destino:** {ruta.get('Origen','')} → {ruta.get('Destino','')}")
            st.caption(f"**KM:** {safe_number(ruta.get('KM')):,.0f}")

            st.markdown("### 💰 Ingresos")
            st.caption(f"**Moneda Flete:** {ruta.get('Moneda','')}")
            st.caption(f"**Ingreso Flete Original:** ${safe_number(ruta.get('Ingreso_Original')):,.2f}")
            st.caption(f"**TC Flete:** {safe_number(ruta.get('Tipo de cambio')):.4f}")
            st.caption(f"**Ingreso Flete Convertido:** ${safe_number(ruta.get('Ingreso Flete')):,.2f}")
            st.caption(f"**Moneda Cruce:** {ruta.get('Moneda_Cruce','')}")
            st.caption(f"**Ingreso Cruce Original:** ${safe_number(ruta.get('Cruce_Original')):,.2f}")
            st.caption(f"**TC Cruce:** {safe_number(ruta.get('Tipo cambio Cruce')):.4f}")
            st.caption(f"**Ingreso Cruce Convertido:** ${safe_number(ruta.get('Ingreso Cruce')):,.2f}")
            st.caption(f"**Ingresos Extras:** ${safe_number(ruta.get('Ingresos_Extras')):,.2f}")
            st.caption(f"**Ingreso Total:** ${ingreso_total:,.2f}")

        with c2:
            st.markdown("### 📉 Costos Operativos")
            st.caption(f"**Diesel Camión:** ${costo_diesel_camion:,.2f}")
            st.caption(f"**Sueldo Operador:** ${safe_number(ruta.get('Sueldo_Operador')):,.2f}")
            st.caption(f"**Bono ISR/IMSS:** ${safe_number(ruta.get('Bono')):,.2f}")
            st.caption(f"**Casetas:** ${safe_number(ruta.get('Casetas')):,.2f}")
            st.caption(f"**Costo Cruce:** ${safe_number(ruta.get('Costo Cruce')):,.2f}")
            st.caption(f"**Costo Cruce Convertido:** ${safe_number(ruta.get('Costo Cruce Convertido')):,.2f}")

            st.markdown("### 🔒 Costos Fijos")
            st.caption(f"**Movimiento Local:** ${safe_number(ruta.get('Movimiento_Local')):,.2f}")
            st.caption(f"**Puntualidad:** ${safe_number(ruta.get('Puntualidad')):,.2f}")
            st.caption(f"**Pensión:** ${safe_number(ruta.get('Pension')):,.2f}")
            st.caption(f"**Estancia:** ${safe_number(ruta.get('Estancia')):,.2f}")
            st.caption(f"**Fianza:** ${safe_number(ruta.get('Fianza')):,.2f}")
            st.caption(f"**Total Costos Fijos:** ${safe_number(ruta.get('Costos_Fijos')):,.2f}")

        with c3:
            st.markdown("### 🧾 Otros Costos")
            extras_items = [
                ("Pistas Extra",  "Pistas_Extra",  "Pistas_Cobrado"),
                ("Stop",          "Stop",          "Stop_Cobrado"),
                ("Falso",         "Falso",         "Falso_Cobrado"),
                ("Gatas",         "Gatas",         "Gatas_Cobrado"),
                ("Accesorios",    "Accesorios",    "Accesorios_Cobrado"),
                ("Guías",         "Guias",         "Guias_Cobrado"),
            ]
            for label, campo, campo_cob in extras_items:
                val = safe_number(ruta.get(campo, 0))
                cobrado = bool(ruta.get(campo_cob, False))
                if val > 0:
                    icono = "✅ cobrado" if cobrado else "— costo interno"
                    st.caption(f"**{label}:** ${val:,.2f} _{icono}_")
            st.caption(f"**Total Costo Extras:** ${safe_number(ruta.get('Costo_Extras')):,.2f}")
            st.caption(f"**Total Ingreso Extras:** ${safe_number(ruta.get('Ingresos_Extras')):,.2f}")

            st.markdown("### 📊 Utilidades")
            st.caption(f"**Costo Total:** ${costo_total:,.2f}")
            st.caption(f"**Utilidad Bruta:** ${util['utilidad_bruta']:,.2f} ({util['porcentaje_bruta']:.1f}%)")
            st.caption(f"**Costos Indirectos:** ${util['costos_indirectos']:,.2f}")
            st.caption(f"**Utilidad Neta:** ${util['utilidad_neta']:,.2f} ({util['porcentaje_neta']:.1f}%)")

    # ── PDF ───────────────────────────────────────────────────────────
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
                with open(pdf_path, "rb") as f:
                    st.download_button(
                        "📥 Descargar PDF",
                        data=f.read(),
                        file_name=f"ruta_{ruta.get('ID_Ruta','picus')}{'_sim' if simular else ''}.pdf",
                        mime="application/pdf",
                        key="pic_cons_dl_pdf",
                    )
                alert("success", "✅ PDF generado exitosamente.")
            except Exception as e:
                alert("error", f"❌ Error al generar PDF: {e}")
