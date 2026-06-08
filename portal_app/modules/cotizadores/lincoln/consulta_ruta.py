"""
consulta_ruta.py – Lincoln Freight (USA/MX)
Patrón: filtros → selector → simulador de parámetros → resultados + PDF.
Alineado con Set Logis Plus.
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
from ui.components import section_header, alert, divider, kpi_row, semaforos_ruta, desglose_ruta
from ._shared import (
    TABLE_RUTAS,
    safe,
    cargar_datos_generales,
    calcular_ruta_lincoln,
    tiene_mx,
)


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
        if not df.empty and "Fecha" in df.columns:
            df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d")
        return df
    except Exception:
        return pd.DataFrame()


# ─────────────────────────────────────────────
# LABEL DE RUTA
# ─────────────────────────────────────────────
def _label_ruta(row: pd.Series) -> str:
    return (
        f"{row.get('ID_Ruta', '')} | "
        f"{row.get('Fecha', '')} | "
        f"{row.get('Tipo', '')} | "
        f"{row.get('Cliente', '')} | "
        f"{row.get('Origen', '')} → {row.get('Destino', '')}"
    )


# ─────────────────────────────────────────────
# FILTROS
# ─────────────────────────────────────────────
def _filtrar(df: pd.DataFrame) -> pd.DataFrame:
    with st.expander("🔎 Filtros de búsqueda (opcional)", expanded=False):
        fc1, fc2, fc3, fc4, fc5 = st.columns(5)

        tipos    = ["Todos"] + sorted(df["Tipo"].dropna().unique().tolist()) if "Tipo" in df.columns else ["Todos"]
        clientes = ["Todos"] + sorted(df["Cliente"].dropna().astype(str).unique().tolist()) if "Cliente" in df.columns else ["Todos"]

        f_tipo   = fc1.selectbox("Tipo",           tipos,    key="ln_cons_ftipo")
        f_cli    = fc2.selectbox("Cliente",         clientes, key="ln_cons_fcli")
        f_id     = fc3.text_input("Buscar ID",                key="ln_cons_fid").strip().upper()
        f_orig   = fc4.text_input("Origen contiene",          key="ln_cons_forig").strip().upper()
        f_dest   = fc5.text_input("Destino contiene",         key="ln_cons_fdest").strip().upper()

    out = df.copy()
    if f_tipo != "Todos":
        out = out[out["Tipo"] == f_tipo]
    if f_cli != "Todos":
        out = out[out["Cliente"].astype(str) == f_cli]
    if f_id:
        out = out[out["ID_Ruta"].astype(str).str.upper().str.contains(f_id, na=False)]
    if f_orig:
        out = out[out["Origen"].astype(str).str.upper().str.contains(f_orig, na=False)]
    if f_dest:
        out = out[out["Destino"].astype(str).str.upper().str.contains(f_dest, na=False)]
    return out


# ─────────────────────────────────────────────
# RECALCULAR DESDE FILA GUARDADA
# ─────────────────────────────────────────────
def _recalcular(ruta: pd.Series, valores: dict) -> dict:
    """
    Recalcula KPIs de una ruta guardada usando calcular_ruta_lincoln del _shared.
    Los ingresos USA se toman tal como fueron guardados (no se recalculan por CXM),
    pero diesel, sueldo, bono e ISR/IMSS sí se recalculan con los parámetros actuales.
    """
    tipo_ruta   = str(ruta.get("Tipo", "NB"))
    es_empty    = (tipo_ruta == "Empty")
    modo_viaje  = str(ruta.get("Modo_Viaje", "Sencillo"))
    millas_usa  = safe(ruta.get("Millas_USA", 0))
    millas_vac  = safe(ruta.get("Millas_Vacias", 0))

    # Ingresos guardados — se respetan tal cual
    ingreso_flete_usa = safe(ruta.get("Ingreso_Flete_USA", 0))
    ingreso_fuel_usa  = safe(ruta.get("Ingreso_Fuel_USA", 0))
    ingreso_cruce     = safe(ruta.get("Ingreso_Cruce", 0))
    ingreso_mx_usd    = safe(ruta.get("Ingreso_MX_USD", 0))
    otros_ing         = safe(ruta.get("Otros_Cargos_Ingreso", 0))

    # Para que calcular_ruta_lincoln no recalcule ingresos desde CXM,
    # derivamos el ingreso_x_milla_usd equivalente
    ing_x_milla = (ingreso_flete_usa / millas_usa) if millas_usa else 0.0
    fuel_sc     = (ingreso_fuel_usa  / millas_usa) if millas_usa else 0.0

    # Costos guardados para cruce y MX (no cambian con simulación de parámetros)
    aplica_cruce  = bool(ruta.get("Aplica_Cruce", False))
    tipo_cruce    = str(ruta.get("Tipo_Cruce", "Propio"))
    tipo_carga    = str(ruta.get("Tipo_Carga_Cruce", "Cargado"))
    costo_cruce_t = safe(ruta.get("Costo_Cruce", 0))   # tercero guardado
    ing_mx_mxp    = safe(ruta.get("Ingreso_MX_MXP", 0))
    costo_mx_mxp  = safe(ruta.get("Costo_MX_MXP", 0))
    linea_mx      = str(ruta.get("Linea_MX", "Propia"))
    otros_costo   = safe(ruta.get("Otros_Cargos_Costo", 0))

    # Si el cruce fue tercero ya tenemos el costo guardado,
    # así que lo pasamos como tercero para que lo use directamente
    if tipo_cruce == "Tercero":
        tipo_cruce_calc = "Tercero"
        costo_terc_calc = costo_cruce_t
    else:
        tipo_cruce_calc = tipo_cruce
        costo_terc_calc = 0.0

    return calcular_ruta_lincoln(
        tipo_ruta            = tipo_ruta,
        millas_usa           = millas_usa,
        millas_vacias        = millas_vac,
        ingreso_x_milla_usd  = ing_x_milla,
        fuel_surcharge_usd   = fuel_sc,
        ingreso_cruce_usd    = ingreso_cruce,
        aplica_cruce         = aplica_cruce,
        modo_viaje           = modo_viaje,
        tipo_cruce           = tipo_cruce_calc,
        tipo_carga_cruce     = tipo_carga,
        costo_cruce_tercero_usd = costo_terc_calc,
        ingreso_flete_mx_mxp = ing_mx_mxp,
        costo_flete_mx_mxp   = costo_mx_mxp,
        linea_mx             = linea_mx,
        otros_cargos         = {"Otros": otros_ing} if otros_ing > 0 else {},
        otros_cargos_pagados = {"Otros": True}       if otros_costo > 0 else {},
        valores              = valores,
    )


# ─────────────────────────────────────────────
# MOSTRAR RESULTADOS
# ─────────────────────────────────────────────
def _mostrar_resultados(r: dict, ruta: pd.Series, es_simulacion: bool = False) -> None:
    if es_simulacion:
        alert("info", "Mostrando resultados simulados con parámetros ajustados.")

    kpi_row([
        ("💰 Ingreso Total",     f"${r['ingreso_total']:,.2f}",     None),
        ("💸 Costo Directo",     f"${r['costo_directo_total']:,.2f}", None),
        ("📈 Utilidad Bruta",    f"${r['utilidad_bruta']:,.2f}",    f"{r['pct_bruta']:.1f}%"),
        ("📉 Costos Indirectos", f"${r['costos_ind']:,.2f}",         None),
        ("✅ Utilidad Neta",     f"${r['utilidad_neta']:,.2f}",      f"{r['pct_neta']:.1f}%"),
    ])

    semaforos_ruta(r)

    tipo_ruta = str(ruta.get("Tipo", "NB"))
    es_empty  = (tipo_ruta == "Empty")
    millas_usa = safe(ruta.get("Millas_USA", 0))
    millas_vac = safe(ruta.get("Millas_Vacias", 0))

    if es_empty:
        filas_costo = [
            (f"Operador Vacío ({millas_vac:.0f} mi × ${r['cxm_vacio']:.4f})", r["sueldo_base"]),
            ("Diesel (millas vacías)", r["diesel_usa"]),
        ]
    else:
        filas_costo = [
            (f"Sueldo Base ({millas_usa:.0f} mi carg + {millas_vac:.0f} mi vac)", r["sueldo_base"]),
            ("Bono por millas cargadas",  r["bono_millas"]),
            ("Diesel (cargado + vacío)",  r["diesel_usa"]),
            ("ISR/IMSS",                  r["isr_imss"]),
        ]
        if r.get("otros_cargos_costo", 0) > 0:
            filas_costo.append(("Otros Cargos (pagados)", r["otros_cargos_costo"]))

    desglose_ruta(r, filas_costo_americana=filas_costo)


# ─────────────────────────────────────────────
# PDF
# ─────────────────────────────────────────────
def _generar_pdf(ruta: pd.Series, r: dict, es_simulacion: bool = False) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
    )

    styles = getSampleStyleSheet()
    sub_s  = ParagraphStyle("S", parent=styles["Heading2"], fontSize=10,
                             textColor=colors.HexColor("#1B2266"), spaceBefore=10, spaceAfter=3)
    foot_s = ParagraphStyle("F", parent=styles["Normal"], fontSize=7,
                             textColor=colors.HexColor("#6c757d"), alignment=TA_CENTER)
    story  = []

    # ── Encabezado ────────────────────────────────────────────────
    hdr = Table([[
        Paragraph("<b>LINCOLN FREIGHT</b>",
                  ParagraphStyle("H", parent=styles["Normal"], fontSize=13, textColor=colors.white)),
        Paragraph("Consulta Individual de Ruta" + (" — SIMULACIÓN" if es_simulacion else ""),
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

    # ── Datos generales ───────────────────────────────────────────
    story.append(Paragraph("Datos de la Ruta", sub_s))
    gen = [
        ["ID Ruta",  str(ruta.get("ID_Ruta", "")),   "Fecha",    str(ruta.get("Fecha", ""))],
        ["Tipo",     str(ruta.get("Tipo", "")),       "Modo",     str(ruta.get("Modo_Viaje", ""))],
        ["Cliente",  str(ruta.get("Cliente", "")),    "T. Cambio",f"${r['tc']:,.2f}"],
        ["Origen",   str(ruta.get("Origen", "")),     "Destino",  str(ruta.get("Destino", ""))],
        ["Millas USA", f"{safe(ruta.get('Millas_USA')):,.0f}", "Millas Vacías", f"{safe(ruta.get('Millas_Vacias')):,.0f}"],
    ]
    t_gen = Table(gen, colWidths=[1.5*inch, 2.0*inch, 1.5*inch, 2.0*inch])
    t_gen.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (0, -1), colors.HexColor("#f0f0f0")),
        ("BACKGROUND",  (2, 0), (2, -1), colors.HexColor("#f0f0f0")),
        ("FONTNAME",    (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME",    (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, -1), 8),
        ("GRID",        (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("TOPPADDING",  (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t_gen)
    story.append(Spacer(1, 8))

    # ── Desglose de costos ────────────────────────────────────────
    story.append(Paragraph("Desglose de Costos", sub_s))
    tipo_ruta = str(ruta.get("Tipo", "NB"))
    es_empty  = (tipo_ruta == "Empty")

    if es_empty:
        costos_rows = [
            ["Operador Vacío", f"${r['sueldo_base']:,.2f}"],
            ["Diesel",         f"${r['diesel_usa']:,.2f}"],
        ]
    else:
        costos_rows = [
            ["Sueldo Base",          f"${r['sueldo_base']:,.2f}"],
            ["Bono por Millas",      f"${r['bono_millas']:,.2f}"],
            ["Sueldo Total Operador",f"${r['sueldo_usa']:,.2f}"],
            ["Diesel USA",           f"${r['diesel_usa']:,.2f}"],
            ["ISR/IMSS",             f"${r['isr_imss']:,.2f}"],
            ["Costo Cruce",          f"${r['costo_cruce']:,.2f}"],
            ["Costo Tramo MX",       f"${r['costo_mx_usd']:,.2f}"],
            ["Otros Cargos",         f"${r.get('otros_cargos_costo', 0):,.2f}"],
        ]
    costos_rows.append(["Total Costo Directo", f"${r['costo_directo_total']:,.2f}"])

    t_cos = Table(costos_rows, colWidths=[3.5*inch, 3.5*inch])
    t_cos.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, -1), colors.HexColor("#f0f0f0")),
        ("FONTNAME",      (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME",      (0, -1),(-1,-1), "Helvetica-Bold"),
        ("BACKGROUND",    (0, -1),(-1,-1), colors.HexColor("#dee2e6")),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("ALIGN",         (1, 0), (1, -1), "RIGHT"),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
    ]))
    story.append(t_cos)
    story.append(Spacer(1, 8))

    # ── Resumen de utilidades ──────────────────────────────────────
    story.append(Paragraph("Resumen de Utilidades", sub_s))
    color_un = colors.HexColor("#28a745") if r["utilidad_neta"] >= 0 else colors.HexColor("#dc3545")
    res_rows = [
        ["Concepto",         "Monto (USD)",                      "%"],
        ["Ingreso Total",    f"${r['ingreso_total']:,.2f}",      "100.00%"],
        ["Costo Directo",    f"${r['costo_directo_total']:,.2f}", f"{r['Pct_Costo_Directo']:.2f}%"],
        ["Ut. Bruta",        f"${r['utilidad_bruta']:,.2f}",     f"{r['pct_bruta']:.2f}%"],
        ["Costo Indirecto",  f"${r['costos_ind']:,.2f}",         f"{r['Pct_Costo_Indirecto']:.2f}%"],
        ["Ut. Neta",         f"${r['utilidad_neta']:,.2f}",      f"{r['pct_neta']:.2f}%"],
    ]
    t_res = Table(res_rows, colWidths=[2.8*inch, 2.2*inch, 2.0*inch])
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
    story.append(Spacer(1, 20))

    # ── Footer ────────────────────────────────────────────────────
    story.append(Paragraph(
        f"Reporte generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} — Lincoln Freight"
        + (" (SIMULACIÓN)" if es_simulacion else ""),
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
        if st.button("🔄 Recargar rutas", key="ln_cons_reload"):
            _cargar_rutas.clear()
            st.rerun()

    df = _cargar_rutas(TABLE_RUTAS)
    if df.empty:
        alert("info", "No hay rutas guardadas aún.")
        return

    valores = cargar_datos_generales()

    # ── Filtros y selector ────────────────────────────────────────
    section_header("📋", "Seleccionar Ruta")
    df_f = _filtrar(df)

    if df_f.empty:
        alert("warn", "No hay rutas con los filtros aplicados.")
        return

    st.caption(f"Rutas disponibles: {len(df_f)}")
    opciones = df_f.apply(_label_ruta, axis=1).tolist()
    sel      = st.selectbox("Ruta", opciones, key="ln_cons_sel")

    if not sel:
        return

    idx  = opciones.index(sel)
    ruta = df_f.iloc[idx]

    divider()

    # ── Simulador de parámetros ───────────────────────────────────
    section_header("⚙️", "Simulador de Parámetros")
    st.caption("Ajusta MPG y precio diesel para ver el impacto sin guardar.")

    s1, s2, s3 = st.columns(3)
    mpg_sim    = s1.number_input("Truck Performance (mpg)",
                                  value=float(valores.get("Truck Performance (mpg)", 7.0)),
                                  step=0.1, format="%.1f", key="ln_sim_mpg")
    diesel_sim = s2.number_input("Diesel Price ($/gal)",
                                  value=float(valores.get("Diesel Price ($/gal)", 3.60)),
                                  step=0.01, format="%.2f", key="ln_sim_diesel")
    tc_sim     = s3.number_input("Tipo de Cambio USD/MXP",
                                  value=float(valores.get("Tipo de Cambio USD/MXP", 18.50)),
                                  step=0.1, format="%.2f", key="ln_sim_tc")

    b1, b2 = st.columns(2)
    simular  = b1.button("🔁 Simular", type="primary", use_container_width=True, key="ln_sim_btn")
    resetear = b2.button("↩️ Valores reales", use_container_width=True, key="ln_sim_reset")

    if simular:
        st.session_state["ln_cons_simulacion"] = True
    if resetear:
        st.session_state["ln_cons_simulacion"] = False

    es_simulacion = st.session_state.get("ln_cons_simulacion", False)

    # ── Calcular ──────────────────────────────────────────────────
    if es_simulacion:
        vals_sim = valores.copy()
        vals_sim["Truck Performance (mpg)"]  = mpg_sim
        vals_sim["Diesel Price ($/gal)"]     = diesel_sim
        vals_sim["Tipo de Cambio USD/MXP"]   = tc_sim
    else:
        vals_sim = valores

    r = _recalcular(ruta, vals_sim)

    divider()
    _mostrar_resultados(r, ruta, es_simulacion)

    # ── Descarga PDF ──────────────────────────────────────────────
    divider()
    section_header("📥", "Descargar Reporte PDF")

    if st.button("📄 Generar PDF", type="primary", key="ln_cons_pdf"):
        try:
            pdf_bytes = _generar_pdf(ruta, r, es_simulacion)
            fname = (
                f"Lincoln_{ruta.get('ID_Ruta', '')}_{ruta.get('Cliente', '').replace(' ','_')}"
                f"_{ruta.get('Fecha', '')}.pdf"
            )
            st.download_button(
                "📥 Descargar PDF",
                data=pdf_bytes,
                file_name=fname,
                mime="application/pdf",
                use_container_width=True,
                key="ln_cons_dl_pdf",
            )
        except Exception as e:
            alert("error", f"Error generando PDF: {e}")
