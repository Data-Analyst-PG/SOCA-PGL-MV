"""
consulta_ruta.py – Set Logis Plus
Patrón: filtros → selector → ajuste PxM → simular → resultados + PDF.
CAMBIO: pasa fuel_owner desde la ruta guardada al recalcular.
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
from ui.components import section_header, alert, divider, kpi_row, semaforos_ruta, desglose_ruta
from ._shared import (
    TABLE_RUTAS,
    DEFAULTS,
    safe,
    cargar_datos_generales,
    calcular_ruta_setlogis,
    tiene_mx,
)


# ─────────────────────────────────────────────────────────────────────────────
# CACHE
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=120)
def _cargar_rutas(table: str) -> pd.DataFrame:
    sb = get_supabase_client()
    if sb is None:
        return pd.DataFrame()
    try:
        resp = sb.table(table).select("*").order("Fecha", desc=True).execute()
        df = pd.DataFrame(resp.data or [])
        if not df.empty and "Fecha" in df.columns:
            df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d")
        return df
    except Exception:
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# FORMATO DE ETIQUETA
# ─────────────────────────────────────────────────────────────────────────────
def _label_ruta(row: pd.Series) -> str:
    fo = " ⛽" if row.get("Fuel_Owner") else ""
    return (
        f"{row.get('ID_Ruta', '')} | "
        f"{row.get('Fecha', '')} | "
        f"{row.get('Tipo_Viaje', '')} | "
        f"{row.get('Cliente', '')} | "
        f"{row.get('Ruta_USA', '')}{fo}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# FILTROS
# ─────────────────────────────────────────────────────────────────────────────
def _filtrar(df: pd.DataFrame) -> pd.DataFrame:
    with st.expander("🔎 Filtros de búsqueda (opcional)", expanded=False):
        fc1, fc2, fc3, fc4 = st.columns(4)

        tipos    = ["Todos"] + sorted(df["Tipo_Viaje"].dropna().unique().tolist()) if "Tipo_Viaje" in df.columns else ["Todos"]
        clientes = ["Todos"] + sorted(df["Cliente"].dropna().astype(str).unique().tolist()) if "Cliente" in df.columns else ["Todos"]

        f_tipo   = fc1.selectbox("Tipo de viaje", tipos,    key="sl_cons_ftipo")
        f_cli    = fc2.selectbox("Cliente",        clientes, key="sl_cons_fcli")
        f_id     = fc3.text_input("Buscar ID",               key="sl_cons_fid").strip().upper()
        f_ruta   = fc4.text_input("Buscar Ruta USA",          key="sl_cons_fruta").strip().upper()

    out = df.copy()
    if f_tipo != "Todos":
        out = out[out["Tipo_Viaje"] == f_tipo]
    if f_cli != "Todos":
        out = out[out["Cliente"].astype(str) == f_cli]
    if f_id:
        out = out[out["ID_Ruta"].astype(str).str.upper().str.contains(f_id, na=False)]
    if f_ruta:
        out = out[out["Ruta_USA"].astype(str).str.upper().str.contains(f_ruta, na=False)]
    return out


# ─────────────────────────────────────────────────────────────────────────────
# PDF CONSULTA INDIVIDUAL
# ─────────────────────────────────────────────────────────────────────────────
def _generar_pdf_consulta(ruta: dict, r: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
    )
    styles = getSampleStyleSheet()
    sub_s  = ParagraphStyle("S", parent=styles["Heading2"], fontSize=10,
                             textColor=colors.HexColor("#1B2266"), spaceBefore=10, spaceAfter=3)
    foot_s = ParagraphStyle("F", parent=styles["Normal"],  fontSize=7,
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
        ("LEFTPADDING",   (0, 0), (0, -1),  12),
        ("RIGHTPADDING",  (-1, 0), (-1, -1), 12),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 10))

    # Datos generales
    story.append(Paragraph("Datos de la Ruta", sub_s))
    fo_label = "Sí ⛽" if ruta.get("Fuel_Owner") else "No"
    gen_data = [
        ["Campo",     "Valor",                         "Campo",       "Valor"],
        ["ID Ruta",   str(ruta.get("ID_Ruta", "")),    "Fecha",       str(ruta.get("Fecha", ""))],
        ["Tipo",      str(ruta.get("Tipo_Viaje", "")), "Modo",        str(ruta.get("Modo", ""))],
        ["Cliente",   str(ruta.get("Cliente", "")),    "Ruta USA",    str(ruta.get("Ruta_USA", ""))],
        ["Modalidad", str(ruta.get("Modalidad", "")),  "Fuel Owner",  fo_label],
        ["Miles Load",  f"{safe(ruta.get('Miles_Load')):.0f}",
         "Short Miles",  f"{safe(ruta.get('Short_Miles')):.0f}"],
        ["Miles Empty", f"{safe(ruta.get('Miles_Empty')):.0f}",
         "Millas Totales", f"{safe(ruta.get('Millas_Totales')):.0f}"],
    ]
    t = Table(gen_data, colWidths=[1.2*inch, 2.1*inch, 1.2*inch, 2.1*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1B2266")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTSIZE",   (0, 0), (-1, -1), 8),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8f9fa")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))

    # KPIs financieros
    story.append(Paragraph("Resumen Financiero (USD)", sub_s))
    kpi_data = [
        ["Concepto", "Monto USD", "Concepto", "Monto USD"],
        ["Ingreso Global",   f"${r.get('Ingreso_Global',0):,.2f}",
         "Costo Directo",    f"${r.get('Costo_Directo',0):,.2f}"],
        ["Pago Owner",       f"${r.get('Pago_Owner_Total',0):,.2f}",
         "Fuel al Owner",    f"${r.get('Pago_Fuel_Owner',0):,.2f}"],
        ["Costo Indirecto",  f"${r.get('Costo_Indirecto',0):,.2f}",
         "Costo Total",      f"${r.get('Costo_Total',0):,.2f}"],
        ["Utilidad Bruta",   f"${r.get('Utilidad_Bruta',0):,.2f} ({r.get('Pct_Ut_Bruta',0):.1f}%)",
         "Utilidad Neta",    f"${r.get('Utilidad_Neta',0):,.2f} ({r.get('Pct_Ut_Neta',0):.1f}%)"],
    ]
    t2 = Table(kpi_data, colWidths=[1.5*inch, 1.8*inch, 1.5*inch, 1.8*inch])
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1B2266")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTSIZE",   (0, 0), (-1, -1), 8),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
    ]))
    story.append(t2)

    # Pie
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        f"Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} — Set Logis Plus",
        foot_s,
    ))

    doc.build(story)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# MOSTRAR RESULTADOS
# ─────────────────────────────────────────────────────────────────────────────
def _mostrar_resultados(r: dict, ruta: dict, es_simulacion: bool = False) -> None:
    titulo = "🔁 Resultado Simulado" if es_simulacion else "📊 Resultado de la Ruta"
    section_header("📊", titulo)

    kpi_row([
        {"icono": "💰", "label": "Ingreso Global",  "valor": f"${r['Ingreso_Global']:,.2f}",  "sub": "USD", "color": "#1B2266"},
        {"icono": "📉", "label": "Costo Directo",   "valor": f"${r['Costo_Directo']:,.2f}",   "sub": f"{r['Pct_Costo_Directo']:.1f}%", "color": r.get("Color_Directo","#dc2626")},
        {"icono": "📊", "label": "Costo Indirecto", "valor": f"${r['Costo_Indirecto']:,.2f}", "sub": f"{r['Pct_Costo_Indirecto']:.1f}%", "color": r.get("Color_Indirecto","#dc2626")},
        {"icono": "✅", "label": "Utilidad Neta",   "valor": f"${r['Utilidad_Neta']:,.2f}",   "sub": f"{r['Pct_Ut_Neta']:.1f}%", "color": r.get("Color_Ut_Neta","#dc2626")},
    ])

    if r.get("Fuel_Owner"):
        st.info(f"⛽ **Fuel pagado al Owner:** ${r.get('Pago_Fuel_Owner', 0):,.2f} USD — incluido en Costo Directo")

    divider()
    semaforos_ruta(r)
    divider()
    modalidad = str(ruta.get("Modalidad", "Flat"))
    cxm_flete = safe(ruta.get("CXM_Flete", 0.0))
    cxm_fuel  = safe(ruta.get("CXM_Fuel",  0.0))
    desglose_ruta(r, modalidad=modalidad, cxm_flete=cxm_flete, cxm_fuel=cxm_fuel)


# ─────────────────────────────────────────────────────────────────────────────
# RENDER
# ─────────────────────────────────────────────────────────────────────────────
def render() -> None:
    supabase = get_supabase_client()
    if supabase is None:
        alert("error", "⚠️ Supabase no configurado.")
        return

    cr, _ = st.columns([1, 4])
    with cr:
        if st.button("🔄 Recargar", key="sl_cons_reload"):
            _cargar_rutas.clear()
            st.rerun()

    df = _cargar_rutas(TABLE_RUTAS)
    if df.empty:
        alert("info", "ℹ️ No hay rutas guardadas.")
        return

    valores = cargar_datos_generales()

    df_fil = _filtrar(df)
    if df_fil.empty:
        alert("warn", "⚠️ No hay rutas con esos filtros.")
        return

    opciones = df_fil.apply(_label_ruta, axis=1).tolist()
    ids      = df_fil["ID_Ruta"].tolist()

    sel_label = st.selectbox(
        "Selecciona una ruta",
        options=[""] + opciones,
        format_func=lambda x: "— Elige una ruta —" if x == "" else x,
        key="sl_cons_sel",
    )
    if not sel_label:
        return

    idx = opciones.index(sel_label)
    ruta = df_fil.iloc[idx].to_dict()

    divider()
    section_header("🔍", f"Detalle: {ruta.get('ID_Ruta','')} — {ruta.get('Cliente','')}")

    # ── Simulador de PxM ──────────────────────────────────────────────────────
    tipo_ruta = str(ruta.get("Tipo_Viaje", "NB"))
    modo      = str(ruta.get("Modo", "Individual"))

    with st.expander("🎛️ Simular cambios de PxM", expanded=False):
        vals_sim = valores.copy()
        es_sim   = False

        sc1, sc2, sc3 = st.columns(3)
        if tipo_ruta in {"SB", "D2DSB"}:
            key_c = "PxM Owner Bajadas Team" if modo == "Team" else "PxM Owner Bajadas"
        else:
            key_c = "PxM Owner Subidas Team" if modo == "Team" else "PxM Owner Subidas"
        key_v = "PxM Owner Vacio Team" if modo == "Team" else "PxM Owner Vacio"

        pxm_cargado_sim = sc1.number_input(
            "PxM Cargado (simulado)", value=float(valores.get(key_c, 1.60)),
            step=0.01, format="%.4f", key="sl_cons_sim_pxmc",
        )
        pxm_vacio_sim = sc2.number_input(
            "PxM Vacío (simulado)", value=float(valores.get(key_v, 0.80)),
            step=0.01, format="%.4f", key="sl_cons_sim_pxmv",
        )
        es_sim = sc3.checkbox("Activar simulación", key="sl_cons_sim_activa")

        vals_sim[key_c] = pxm_cargado_sim
        vals_sim[key_v] = pxm_vacio_sim

    # ── Recalcular ─────────────────────────────────────────────────────────────
    # fuel_owner se lee de la ruta guardada; en simulación se mantiene igual
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
        tipo_cruce           = str(ruta.get("Tipo_Cruce", "Propio")),
        tipo_carga_cruce     = str(ruta.get("Tipo_Carga_Cruce", "Cargado")),
        ingreso_cruce        = safe(ruta.get("Ingreso_Cruce")),
        costo_cruce_externo  = safe(ruta.get("Costo_Cruce")),
        ingreso_mx           = safe(ruta.get("Ingreso_MX")),
        costo_mx             = safe(ruta.get("Costo_MX")),
        extras_ingreso       = safe(ruta.get("Extras_Ingreso")),
        extras_costo         = safe(ruta.get("Extras_Costo")),
        modo_costo_indirecto = "CXM",
        valores              = vals_sim if es_sim else valores,
        fuel_owner           = bool(ruta.get("Fuel_Owner", False)),
        incluye_cruce        = bool(ruta.get("Incluye_Cruce", False)),
    )

    divider()
    _mostrar_resultados(r, ruta, es_simulacion=es_sim)

    # ── Descarga PDF ──────────────────────────────────────────────────────────
    divider()
    section_header("📥", "Descargar PDF")
    try:
        pdf_bytes = _generar_pdf_consulta(ruta, r)
        nombre_pdf = f"Consulta_{ruta.get('ID_Ruta','SL')}_{ruta.get('Cliente','').replace(' ','_')}.pdf"
        st.download_button(
            label="📄 Descargar PDF de esta ruta",
            data=pdf_bytes,
            file_name=nombre_pdf,
            mime="application/pdf",
            use_container_width=True,
        )
    except Exception as ex:
        alert("error", f"❌ Error generando PDF: {ex}")
