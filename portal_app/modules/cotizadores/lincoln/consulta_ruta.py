"""
consulta_ruta.py – Lincoln Freight (USA/MX)
Homologado con Igloo y Picus:
  - Sin funciones locales duplicadas — cache, label y filtros vienen de _shared.py
  - banner_tarifa_sugerida() + mostrar_resultados_ruta() de components
  - Simulador de parámetros (MPG, diesel, TC) sin modificar la ruta
  - PDF profesional con reportlab
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
    mostrar_resultados_ruta, banner_tarifa_sugerida, desglose_ruta,
)
from ._shared import (
    TABLE_RUTAS,
    safe,
    cargar_datos_generales,
    calcular_ruta_lincoln,
    load_rutas_lincoln,
    filtrar_rutas_lincoln,
    label_ruta_lincoln,
)


# ─────────────────────────────────────────────
# RECALCULAR DESDE FILA DB
# ─────────────────────────────────────────────
def _recalcular(ruta: pd.Series, valores: dict) -> dict:
    tipo_ruta   = str(ruta.get("Tipo", "NB"))
    modo_viaje  = str(ruta.get("Modo_Viaje", "Sencillo"))
    miles_load  = safe(ruta.get("Miles_Load")  or ruta.get("Millas_USA",    0))
    short_miles = safe(ruta.get("Short_Miles") or ruta.get("Millas_USA",    0))
    miles_empty = safe(ruta.get("Miles_Empty") or ruta.get("Millas_Vacias", 0))

    ingreso_flete_usa = safe(ruta.get("Ingreso_Flete_USA", 0))
    ingreso_fuel_usa  = safe(ruta.get("Ingreso_Fuel_USA",  0))
    ingreso_cruce     = safe(ruta.get("Ingreso_Cruce",     0))
    ing_mx_mxp        = safe(ruta.get("Ingreso_MX_MXP",    0))
    costo_mx_mxp      = safe(ruta.get("Costo_MX_MXP",      0))
    otros_ing         = safe(ruta.get("Otros_Cargos_Ingreso", 0))
    otros_costo       = safe(ruta.get("Otros_Cargos_Costo",   0))

    ing_x_milla = (ingreso_flete_usa / miles_load) if miles_load else 0.0
    fuel_sc     = (ingreso_fuel_usa  / miles_load) if miles_load else 0.0

    aplica_cruce  = bool(ruta.get("Aplica_Cruce", False))
    tipo_cruce    = str(ruta.get("Tipo_Cruce",       "Propio"))
    tipo_carga    = str(ruta.get("Tipo_Carga_Cruce", "Cargado"))
    costo_cruce_t = safe(ruta.get("Costo_Cruce", 0))
    linea_mx      = str(ruta.get("Linea_MX", "Propia"))
    costo_terc    = costo_cruce_t if tipo_cruce == "Tercero" else 0.0

    return calcular_ruta_lincoln(
        tipo_ruta               = tipo_ruta,
        miles_load              = miles_load,
        short_miles             = short_miles,
        miles_empty             = miles_empty,
        ingreso_x_milla_usd     = ing_x_milla,
        tarifa_flat_usd         = 0.0,
        fuel_surcharge_usd      = fuel_sc,
        ingreso_cruce_usd       = ingreso_cruce,
        aplica_cruce            = aplica_cruce,
        modo_viaje              = modo_viaje,
        tipo_cruce              = tipo_cruce,
        tipo_carga_cruce        = tipo_carga,
        costo_cruce_tercero_usd = costo_terc,
        ingreso_flete_mx_mxp    = ing_mx_mxp,
        costo_flete_mx_mxp      = costo_mx_mxp,
        linea_mx                = linea_mx,
        otros_cargos            = {"Otros": otros_ing}   if otros_ing  > 0 else {},
        otros_cargos_cobrados   = {"Otros": True}        if otros_costo > 0 else {},
        valores                 = valores,
    )


# ─────────────────────────────────────────────
# MOSTRAR KPIs + DESGLOSE
# ─────────────────────────────────────────────
def _mostrar_kpis(r: dict, es_simulacion: bool = False) -> None:
    if es_simulacion:
        alert("info", "🔧 Estás viendo una simulación con parámetros ajustados.")
    tc_usd       = r.get("tc", 18.50)
    _umbral      = r["umbral_cd"]
    _costo_ame   = r.get("costo_directo_americana", r["costo_directo"])
    _tarifa_sug  = _costo_ame / (_umbral / 100)
    _tarifa_mxp  = _tarifa_sug * tc_usd
    divider()
    banner_tarifa_sugerida(
        _costo_ame, r["ingreso_total"],
        _umbral, "USD", _tarifa_mxp,
        modalidad=str(r.get("modalidad") or "Flat"),
        miles_load=safe(r.get("miles_load", 0.0)),
        fuel_capturado=r.get("ingreso_fuel_usa", 0.0),
    )
    mostrar_resultados_ruta(r)


def _mostrar_detalles(r: dict, ruta: pd.Series) -> None:
    section_header("📋", "Detalles y Costos de la Ruta")

    tipo_ruta   = str(ruta.get("Tipo", "NB"))
    es_empty    = (tipo_ruta == "Empty")
    short_miles = safe(ruta.get("Short_Miles") or ruta.get("Millas_USA",    0))
    miles_empty = safe(ruta.get("Miles_Empty") or ruta.get("Millas_Vacias", 0))
    modo_viaje  = str(ruta.get("Modo_Viaje", "Sencillo"))
    factor      = 2 if modo_viaje == "Team" else 1

    if es_empty:
        filas = [
            (f"Operador Vacío ({miles_empty:.0f} mi × ${r['cxm_vacio']:.4f})", r["sueldo_base"]),
            (f"Diesel ({miles_empty:.0f} mi vacías)", r["diesel_usa"]),
        ]
    else:
        filas = [
            (f"Sueldo Cargado ({short_miles:.0f} Short Mi × ${r['cxm_cargado']:.4f})",
             short_miles * r["cxm_cargado"] * factor),
            (f"Sueldo Vacío ({miles_empty:.0f} Mi Vacías × ${r['cxm_vacio']:.4f})",
             miles_empty * r["cxm_vacio"] * factor),
            (f"Bono ({short_miles:.0f} Short Mi × ${r['bono_por_milla']:.3f})", r["bono_millas"]),
            (f"Diesel ({short_miles:.0f} SM + {miles_empty:.0f} ME)", r["diesel_usa"]),
            ("ISR/IMSS", r["isr_imss"]),
        ]
        if r.get("otros_cargos_costo", 0) > 0:
            filas.append(("Otros Conceptos (Lincoln pagó)", r["otros_cargos_costo"]))

    modalidad = str(ruta.get("Modalidad") or ruta.get("Modalidad_Tarifa") or "Flat")

    desglose_ruta(
        r,
        filas_costo_americana=filas,
        modalidad=modalidad,
        cxm_flete=safe(ruta.get("CXM_Flete", 0)),
        cxm_fuel=safe(ruta.get("CXM_Fuel", 0)),
    )

    if ruta.get("Capturado_Por"):
        st.caption(f"👤 Capturado por: **{ruta.get('Capturado_Por')}**")


# ─────────────────────────────────────────────
# PDF PROFESIONAL
# ─────────────────────────────────────────────
def _generar_pdf(ruta: pd.Series, r: dict, es_simulacion: bool = False) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
    )
    styles = getSampleStyleSheet()
    AZUL   = colors.HexColor("#1B2266")
    AZUL_L = colors.HexColor("#dee6f5")
    GRIS   = colors.HexColor("#f5f5f5")

    sub_s  = ParagraphStyle("S", parent=styles["Heading2"], fontSize=10,
                             textColor=AZUL, spaceBefore=10, spaceAfter=3)
    foot_s = ParagraphStyle("F", parent=styles["Normal"], fontSize=7,
                             textColor=colors.HexColor("#6c757d"), alignment=TA_CENTER)

    def _tabla(data, col_widths, header_color=AZUL):
        t = Table(data, colWidths=col_widths)
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),  header_color),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTNAME",      (0, 1), (0, -1),  "Helvetica-Bold"),
            ("BACKGROUND",    (0, 1), (0, -1),  GRIS),
            ("FONTSIZE",      (0, 0), (-1, -1), 8),
            ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
            ("ALIGN",         (1, 1), (-1, -1), "RIGHT"),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ]))
        return t

    story = []

    # Encabezado
    hdr = Table([[
        Paragraph("<b>LINCOLN FREIGHT</b>",
                  ParagraphStyle("H", parent=styles["Normal"], fontSize=13, textColor=colors.white)),
        Paragraph(
            "Consulta Individual de Ruta" + (" — SIMULACIÓN" if es_simulacion else ""),
            ParagraphStyle("HR", parent=styles["Normal"], fontSize=9,
                           textColor=colors.white, alignment=TA_RIGHT),
        ),
    ]], colWidths=[4.5 * inch, 2.5 * inch])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), AZUL),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (0, -1),  12),
        ("RIGHTPADDING",  (-1, 0), (-1, -1), 12),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 8))

    # Datos generales
    story.append(Paragraph("Información de la Ruta", sub_s))
    tipo_ruta   = str(ruta.get("Tipo", "NB"))
    miles_load  = safe(ruta.get("Miles_Load")  or ruta.get("Millas_USA",    0))
    short_miles = safe(ruta.get("Short_Miles") or ruta.get("Millas_USA",    0))
    miles_empty = safe(ruta.get("Miles_Empty") or ruta.get("Millas_Vacias", 0))

    gen_data = [
        ["Campo", "Valor", "Campo", "Valor"],
        ["ID Ruta",     str(ruta.get("ID_Ruta", "")),       "Fecha",       str(ruta.get("Fecha", ""))],
        ["Tipo",        tipo_ruta,                           "Modo",        str(ruta.get("Modo_Viaje", "Sencillo"))],
        ["Cliente",     str(ruta.get("Cliente", "")),        "T. Cambio",   f"${r['tc']:,.2f}"],
        ["Origen",      str(ruta.get("Origen", "")),         "Destino",     str(ruta.get("Destino", ""))],
        ["Miles Load",  f"{miles_load:,.0f} mi",             "Short Miles", f"{short_miles:,.0f} mi"],
        ["Miles Empty", f"{miles_empty:,.0f} mi",            "MPG",         f"{r['mpg']:.1f}"],
        ["Diesel",      f"${r['diesel']:,.2f}/gal",          "CXM Oper.",   f"${r['cxm_cargado']:,.4f}/mi"],
    ]
    story.append(_tabla(gen_data, [1.5*inch, 2.0*inch, 1.5*inch, 2.0*inch], AZUL))
    story.append(Spacer(1, 6))

    # Tramo MX si aplica
    if ruta.get("Origen_MX") or ruta.get("Destino_MX"):
        story.append(Paragraph("Tramo Mexicano", sub_s))
        mx_data = [
            ["Campo", "Valor", "Campo", "Valor"],
            ["Línea MX",   str(ruta.get("Linea_MX", "")),   "Moneda MX",   str(ruta.get("Moneda_MX", "MXP"))],
            ["Origen MX",  str(ruta.get("Origen_MX", "")),  "Destino MX",  str(ruta.get("Destino_MX", ""))],
            ["Ingreso MXP", f"${safe(ruta.get('Ingreso_MX_MXP')):,.2f}",
             "Costo MXP",   f"${safe(ruta.get('Costo_MX_MXP')):,.2f}"],
        ]
        story.append(_tabla(mx_data, [1.5*inch, 2.0*inch, 1.5*inch, 2.0*inch], AZUL))
        story.append(Spacer(1, 6))

    # Cruce si aplica
    if ruta.get("Aplica_Cruce"):
        story.append(Paragraph("Cruce Fronterizo", sub_s))
        cruce_data = [
            ["Tipo Cruce", "Tipo Carga", "Moneda", "Ingreso", "Costo"],
            [
                str(ruta.get("Tipo_Cruce", "")),
                str(ruta.get("Tipo_Carga_Cruce", "")),
                str(ruta.get("Moneda_Cruce", "USD")),
                f"${r['ingreso_cruce']:,.2f}",
                f"${r['costo_cruce']:,.2f}",
            ],
        ]
        story.append(_tabla(cruce_data, [1.4*inch, 1.4*inch, 1.2*inch, 1.7*inch, 1.3*inch], AZUL))
        story.append(Spacer(1, 6))

    # Ingresos
    story.append(Paragraph("Ingresos (USD)", sub_s))
    ing_data = [
        ["Concepto", "Monto USD"],
        ["Flete USA",         f"${r['ingreso_flete_usa']:,.2f}"],
        ["Fuel Surcharge",    f"${r['ingreso_fuel_usa']:,.2f}"],
        ["Cruce",             f"${r['ingreso_cruce']:,.2f}"],
        ["Tramo MX",          f"${r['ingreso_mx_usd']:,.2f}"],
        ["Otros (cobrados)",  f"${r['otros_cargos_ingreso']:,.2f}"],
        ["TOTAL INGRESO",     f"${r['ingreso_total']:,.2f}"],
    ]
    story.append(_tabla(ing_data, [4.5*inch, 2.5*inch], AZUL))
    story.append(Spacer(1, 6))

    # Costos directos
    story.append(Paragraph("Costos Directos (USD)", sub_s))
    es_empty = (tipo_ruta == "Empty")
    factor   = 2 if str(ruta.get("Modo_Viaje", "Sencillo")) == "Team" else 1
    if es_empty:
        costo_rows = [
            ["Operador Vacío", f"${r['sueldo_base']:,.2f}"],
            ["Diesel",         f"${r['diesel_usa']:,.2f}"],
        ]
    else:
        costo_rows = [
            ["Sueldo Cargado",  f"${short_miles * r['cxm_cargado'] * factor:,.2f}"],
            ["Sueldo Vacío",    f"${miles_empty * r['cxm_vacio']   * factor:,.2f}"],
            ["Bono Millas",     f"${r['bono_millas']:,.2f}"],
            ["Diesel",          f"${r['diesel_usa']:,.2f}"],
            ["ISR/IMSS",        f"${r['isr_imss']:,.2f}"],
            ["Cruce",           f"${r['costo_cruce']:,.2f}"],
            ["Tramo MX",        f"${r['costo_mx_usd']:,.2f}"],
            ["Otros (pagados)", f"${r['otros_cargos_costo']:,.2f}"],
        ]
    costo_data = [["Concepto", "Monto USD"]] + costo_rows + [
        ["COSTO DIRECTO", f"${r['costo_directo']:,.2f}"]
    ]
    story.append(_tabla(costo_data, [4.5*inch, 2.5*inch], AZUL))
    story.append(Spacer(1, 6))

    # Resultados finales
    story.append(Paragraph("Resultados", sub_s))
    color_un = colors.HexColor("#28a745") if r["utilidad_neta"] >= 0 else colors.HexColor("#dc3545")
    res_data = [
        ["Concepto",          "Monto USD",                    "%"],
        ["Ingreso Total",     f"${r['ingreso_total']:,.2f}",  "100.00%"],
        ["Costo Directo",     f"${r['costo_directo']:,.2f}",  f"{r['Pct_Costo_Directo']:.1f}%"],
        ["Utilidad Bruta",    f"${r['utilidad_bruta']:,.2f}", f"{r['Pct_Ut_Bruta']:.1f}%"],
        ["Costos Indirectos", f"${r['costos_ind']:,.2f}",     f"{r['Pct_Costo_Indirecto']:.1f}%"],
        ["Utilidad Neta",     f"${r['utilidad_neta']:,.2f}",  f"{r['Pct_Ut_Neta']:.1f}%"],
    ]
    t_res = Table(res_data, colWidths=[3.5*inch, 2.0*inch, 1.5*inch])
    t_res.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),   AZUL),
        ("TEXTCOLOR",     (0, 0), (-1, 0),   colors.white),
        ("FONTNAME",      (0, 0), (-1, 0),   "Helvetica-Bold"),
        ("FONTNAME",      (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND",    (0, -1), (-1, -1), AZUL_L),
        ("TEXTCOLOR",     (1, -1), (1, -1),  color_un),
        ("FONTSIZE",      (0, 0), (-1, -1),  8),
        ("GRID",          (0, 0), (-1, -1),  0.5, colors.HexColor("#dee2e6")),
        ("ALIGN",         (1, 1), (-1, -1),  "RIGHT"),
        ("TOPPADDING",    (0, 0), (-1, -1),  3),
        ("BOTTOMPADDING", (0, 0), (-1, -1),  3),
        ("LEFTPADDING",   (0, 0), (-1, -1),  6),
    ]))
    story.append(t_res)

    if es_simulacion:
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            f"⚠️ SIMULACIÓN — MPG: {r['mpg']:.1f} | Diesel: ${r['diesel']:,.2f}/gal | TC: ${r['tc']:,.2f}",
            ParagraphStyle("W", parent=styles["Normal"], fontSize=8,
                           textColor=colors.HexColor("#856404")),
        ))

    story.append(Spacer(1, 12))
    story.append(Paragraph(
        f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')} — SOCA · Palos Garza Logistics",
        foot_s,
    ))

    doc.build(story)
    buf.seek(0)
    return buf.read()


# ─────────────────────────────────────────────
# RENDER PRINCIPAL
# ─────────────────────────────────────────────
def render() -> None:
    sb = get_supabase_client()
    if sb is None:
        alert("error", "Supabase no configurado.")
        return

    # Recargar
    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("🔄 Recargar", key="ln_cons_reload"):
            load_rutas_lincoln.clear()
            st.rerun()
    with c2:
        st.caption("Carga cacheada 2 min. Usa 'Recargar' si acabas de guardar algo.")

    valores = cargar_datos_generales()
    df      = load_rutas_lincoln(TABLE_RUTAS)

    if df.empty:
        alert("info", "No hay rutas guardadas.")
        return

    # Filtros
    df_f = filtrar_rutas_lincoln(df, "ln_cons")

    if df_f.empty:
        alert("info", "No hay rutas con los filtros aplicados.")
        return

    st.caption(f"Rutas disponibles: **{len(df_f)}**")
    opciones = df_f.apply(lambda row: label_ruta_lincoln(row.to_dict()), axis=1).tolist()
    sel      = st.selectbox("Selecciona la ruta a consultar", opciones, key="ln_cons_sel")

    if not sel:
        return

    idx  = opciones.index(sel)
    ruta = df_f.iloc[idx]

    divider()

    # ── Simulador de parámetros ───────────────────────────────────
    section_header("⚙️", "Ajustes para Simulación")
    st.caption("Ajusta MPG, diesel o tipo de cambio para ver el impacto sin modificar la ruta.")

    s1, s2, s3 = st.columns(3)
    mpg_sim    = s1.number_input("Truck Performance (mpg)",
                                  value=float(valores.get("Truck Performance (mpg)", 7.0)),
                                  step=0.1, format="%.1f", key="ln_cons_sim_mpg")
    diesel_sim = s2.number_input("Diesel Price ($/gal)",
                                  value=float(valores.get("Diesel Price ($/gal)", 3.60)),
                                  step=0.01, format="%.2f", key="ln_cons_sim_diesel")
    tc_sim     = s3.number_input("Tipo de Cambio USD/MXP",
                                  value=float(valores.get("Tipo de Cambio USD/MXP", 18.50)),
                                  step=0.1, format="%.2f", key="ln_cons_sim_tc")

    b1, b2 = st.columns(2)
    simular  = b1.button("🔁 Simular",        type="primary", use_container_width=True, key="ln_cons_sim_btn")
    resetear = b2.button("↩️ Valores reales", use_container_width=True,               key="ln_cons_sim_reset")

    if simular:
        st.session_state["ln_cons_simulacion"] = True
    if resetear:
        st.session_state["ln_cons_simulacion"] = False

    es_simulacion = st.session_state.get("ln_cons_simulacion", False)

    vals_sim = valores.copy()
    if es_simulacion:
        vals_sim["Truck Performance (mpg)"] = mpg_sim
        vals_sim["Diesel Price ($/gal)"]    = diesel_sim
        vals_sim["Tipo de Cambio USD/MXP"]  = tc_sim

    # ── Calcular y mostrar ────────────────────────────────────────
    r = _recalcular(ruta, vals_sim)

    _mostrar_kpis(r, es_simulacion)
    _mostrar_detalles(r, ruta)

    # ── PDF ───────────────────────────────────────────────────────
    divider()
    section_header("📥", "Descargar PDF de la Consulta")

    if st.button("📄 Generar PDF", type="primary", key="ln_cons_pdf"):
        try:
            pdf_bytes = _generar_pdf(ruta, r, es_simulacion)
            fname = (
                f"Consulta_Lincoln_{ruta.get('ID_Ruta', '')}_"
                f"{str(ruta.get('Cliente', '')).replace(' ', '_')}"
                f"_{ruta.get('Fecha', '')}"
                + ("_SIM" if es_simulacion else "") + ".pdf"
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
