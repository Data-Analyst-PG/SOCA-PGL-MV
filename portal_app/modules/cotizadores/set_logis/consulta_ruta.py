"""
consulta_ruta.py – Set Logis Plus
Patrón: filtros → selector → ajuste PxM → simular → resultados + PDF.
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
    return (
        f"{row.get('ID_Ruta', '')} | "
        f"{row.get('Fecha', '')} | "
        f"{row.get('Tipo_Viaje', '')} | "
        f"{row.get('Cliente', '')} | "
        f"{row.get('Ruta_USA', '')}"
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
# PDF CONSULTA INDIVIDUAL  (función de módulo, NO dentro de render)
# ─────────────────────────────────────────────────────────────────────────────
def _generar_pdf_consulta(ruta: dict, r: dict) -> bytes:
    """
    Genera PDF de consulta individual de una ruta Set Logis.
    ruta : dict con los campos guardados en Supabase.
    r    : dict resultado de calcular_ruta_setlogis (KPIs recalculados).
    """
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

    # ── Encabezado ───────────────────────────────────────────────
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

    # ── Datos generales ──────────────────────────────────────────
    story.append(Paragraph("Datos de la Ruta", sub_s))
    gen_data = [
        ["Campo",     "Valor",                         "Campo",       "Valor"],
        ["ID Ruta",   str(ruta.get("ID_Ruta", "")),    "Fecha",       str(ruta.get("Fecha", ""))],
        ["Tipo",      str(ruta.get("Tipo_Viaje", "")), "Modo",        str(ruta.get("Modo", ""))],
        ["Cliente",   str(ruta.get("Cliente", "")),    "Modalidad",   str(ruta.get("Modalidad", ""))],
        ["Ruta USA",  str(ruta.get("Ruta_USA", "")),   "Tipo Cruce",  str(ruta.get("Tipo_Cruce", ""))],
    ]
    origen_mx = str(ruta.get("Origen_MX", "")).strip()
    if origen_mx:
        gen_data.append(["Origen MX", origen_mx, "Destino MX", str(ruta.get("Destino_MX", ""))])

    def _tabla(data, col_widths):
        t = Table(data, colWidths=col_widths)
        t.setStyle(TableStyle([
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
        return t

    cw4 = [1.3 * inch, 2.1 * inch, 1.3 * inch, 2.1 * inch]
    story.append(_tabla(gen_data, cw4))
    story.append(Spacer(1, 8))

    # ── Millas y PxM ─────────────────────────────────────────────
    story.append(Paragraph("Millas y Precio por Milla", sub_s))
    mil_data = [
        ["Miles Load",  f"{safe(ruta.get('Miles_Load')):.0f} mi",
         "Short Miles", f"{safe(ruta.get('Short_Miles')):.0f} mi"],
        ["Miles Empty", f"{safe(ruta.get('Miles_Empty')):.0f} mi",
         "Millas Totales", f"{safe(r.get('Millas_Totales')):.0f} mi"],
        ["PxM Cargado", f"${safe(r.get('PxM_Cargado')):.4f}/mi",
         "PxM Vacío",   f"${safe(r.get('PxM_Vacio')):.4f}/mi"],
    ]
    t_mil = Table(mil_data, colWidths=cw4)
    t_mil.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, -1),  colors.HexColor("#EEF2FF")),
        ("BACKGROUND",    (2, 0), (2, -1),  colors.HexColor("#EEF2FF")),
        ("FONTNAME",      (0, 0), (0, -1),  "Helvetica-Bold"),
        ("FONTNAME",      (2, 0), (2, -1),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 7),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
    ]))
    story.append(t_mil)
    story.append(Spacer(1, 8))

    # ── Ingresos y Costos ─────────────────────────────────────────
    story.append(Paragraph("Ingresos y Costos", sub_s))
    fin_data = [
        ["Concepto",          "Monto USD",                         "Concepto",       "Monto USD"],
        ["Flete USA",         f"${safe(r.get('Flete_USA')):,.2f}",
         "Owner Cargado",     f"${safe(r.get('Pago_Owner_Cargado')):,.2f}"],
        ["Fuel",              f"${safe(r.get('Fuel')):,.2f}",
         "Owner Vacío",       f"${safe(r.get('Pago_Owner_Vacio')):,.2f}"],
        ["Ingreso Cruce",     f"${safe(r.get('Ingreso_Cruce')):,.2f}",
         "Costo Cruce",       f"${safe(r.get('Costo_Cruce')):,.2f}"],
        ["Ingreso MX",        f"${safe(r.get('Ingreso_MX')):,.2f}",
         "Costo MX",          f"${safe(r.get('Costo_MX')):,.2f}"],
        ["Extras (cobrados)", f"${safe(r.get('Extras_Ingreso')):,.2f}",
         "Extras (costo)",    f"${safe(r.get('Extras_Costo')):,.2f}"],
        ["",                  "",
         "Costo Indirecto",   f"${safe(r.get('Costo_Indirecto')):,.2f}"],
    ]
    t_fin = Table(fin_data, colWidths=[1.5 * inch, 1.8 * inch, 1.5 * inch, 1.8 * inch])
    t_fin.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor("#1B2266")),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("BACKGROUND",    (0, 1), (0, -1),  colors.HexColor("#EEF2FF")),
        ("BACKGROUND",    (2, 1), (2, -1),  colors.HexColor("#EEF2FF")),
        ("FONTNAME",      (0, 1), (0, -1),  "Helvetica-Bold"),
        ("FONTNAME",      (2, 1), (2, -1),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 7),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("ALIGN",         (1, 1), (1, -1),  "RIGHT"),
        ("ALIGN",         (3, 1), (3, -1),  "RIGHT"),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
    ]))
    story.append(t_fin)
    story.append(Spacer(1, 8))

    # ── Resumen de utilidad ───────────────────────────────────────
    story.append(Paragraph("Resumen de Utilidad", sub_s))
    ing    = safe(r.get("Ingreso_Global"))
    cd     = safe(r.get("Costo_Directo"))
    ci     = safe(r.get("Costo_Indirecto"))
    ub     = safe(r.get("Utilidad_Bruta"))
    un     = safe(r.get("Utilidad_Neta"))
    pct_cd = safe(r.get("Pct_Costo_Directo"))
    pct_ub = safe(r.get("Pct_Ut_Bruta"))
    pct_ci = safe(r.get("Pct_Costo_Indirecto"))
    pct_un = safe(r.get("Pct_Ut_Neta"))

    color_un_pdf = colors.HexColor("#28a745") if un >= 0 else colors.HexColor("#dc3545")
    res_data = [
        ["Concepto",        "Monto (USD)",    "%"],
        ["Ingreso Total",   f"${ing:,.2f}",   "100.00%"],
        ["Costo Directo",   f"${cd:,.2f}",    f"{pct_cd:.1f}%"],
        ["Ut. Bruta",        f"${ub:,.2f}",    f"{pct_ub:.1f}%"],
        ["Costo Indirecto", f"${ci:,.2f}",    f"{pct_ci:.1f}%"],
        ["Ut. Neta",         f"${un:,.2f}",    f"{pct_un:.1f}%"],
    ]
    t_res = Table(res_data, colWidths=[2.8 * inch, 2.2 * inch, 1.8 * inch])
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
    story.append(Spacer(1, 20))

    # ── Footer ────────────────────────────────────────────────────
    story.append(Paragraph(
        f"Reporte generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} — Set Logis Plus",
        foot_s,
    ))
    doc.build(story)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# MOSTRAR RESULTADOS
# ─────────────────────────────────────────────────────────────────────────────
def _mostrar_resultados(r: dict, ruta: pd.Series, es_simulacion: bool = False) -> None:
    if es_simulacion:
        alert("info", "Mostrando resultados con PxM ajustado (simulación).")

    pct_ut_b   = r.get("Pct_Ut_Bruta", 0.0)
    color_ut_b = "#16a34a" if pct_ut_b >= 15.0 else "#dc2626"

    ut_neta    = r.get("Utilidad_Neta", 0.0)
    ut_color   = "#16a34a" if ut_neta >= 0 else "#dc2626"

    section_header("📊", "Resultado de la Ruta")
    kpi_row([
        {"icono": "💵", "label": "Ingreso Total",   "valor": f"${r['Ingreso_Global']:,.2f} USD",
         "sub": "Flete + Cruce + MX + Extras",      "color": "#1B2266"},
        {"icono": "📉", "label": "Costo Directo",   "valor": f"${r['Costo_Directo']:,.2f} USD",
         "sub": f"{r['Pct_Costo_Directo']:.1f}% del ingreso", "color": r.get("Color_Directo", "#6B7280")},
        {"icono": "📈", "label": "Utilidad Bruta",  "valor": f"${r['Utilidad_Bruta']:,.2f} USD",
         "sub": f"{pct_ut_b:.1f}% del ingreso",     "color": color_ut_b},
        {"icono": "🔁", "label": "Costo Indirecto", "valor": f"${r['Costo_Indirecto']:,.2f} USD",
         "sub": f"{r['Pct_Costo_Indirecto']:.1f}% del ingreso", "color": r.get("Color_Indirecto", "#F59E0B")},
        {"icono": "🏆", "label": "Utilidad Neta",   "valor": f"${ut_neta:,.2f} USD",
         "sub": f"{r['Pct_Ut_Neta']:.1f}% del ingreso",        "color": ut_color},
    ])

    # Porcentajes
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("% Costo Directo",   f"{r.get('Pct_Costo_Directo', 0):.1f}%")
    p2.metric("% Costo Indirecto", f"{r.get('Pct_Costo_Indirecto', 0):.1f}%")
    p3.metric("% Ut. Bruta",       f"{r.get('Pct_Ut_Bruta', 0):.1f}%")
    p4.metric("% Ut. Neta",        f"{r.get('Pct_Ut_Neta', 0):.1f}%")

    divider()
    semaforos_ruta(r)

    # Desglose por tramo
    modalidad = str(ruta.get("Modalidad", "Flat"))
    cxm_f     = safe(ruta.get("CXM_Flete")) if modalidad == "Desglosada" else 0.0
    cxm_fu    = safe(ruta.get("CXM_Fuel"))  if modalidad == "Desglosada" else 0.0
    desglose_ruta(r, modalidad=modalidad, cxm_flete=cxm_f, cxm_fuel=cxm_fu)

    # Historial de modificaciones
    historial = ruta.get("historial") or []
    if isinstance(historial, list) and historial:
        divider()
        with st.expander(f"📜 Historial de modificaciones ({len(historial)})", expanded=False):
            for entrada in reversed(historial):
                ts  = str(entrada.get("timestamp", ""))[:16].replace("T", " ")
                usr = entrada.get("usuario", "—")
                mot = entrada.get("motivo", "—")
                st.caption(f"**{ts}** · {usr} · _{mot}_")
                prev = entrada.get("valores_anteriores", {})
                if prev:
                    hc1, hc2, hc3 = st.columns(3)
                    hc1.caption(f"Ingreso: **${safe(prev.get('Ingreso_Global')):,.2f}**")
                    hc1.caption(f"C. Directo: **${safe(prev.get('Costo_Directo')):,.2f}**")
                    hc2.caption(f"Ut. Bruta: **${safe(prev.get('Utilidad_Bruta')):,.2f}**")
                    hc2.caption(f"Ut. Neta: **${safe(prev.get('Utilidad_Neta')):,.2f}**")
                    hc3.caption(f"Short Miles: **{safe(prev.get('Short_Miles')):.0f}**")
                    hc3.caption(f"Miles Empty: **{safe(prev.get('Miles_Empty')):.0f}**")
                st.divider()

    # PDF
    divider()
    section_header("📥", "Descargar PDF")
    try:
        ruta_dict = ruta.to_dict() if hasattr(ruta, "to_dict") else dict(ruta)
        pdf_bytes = _generar_pdf_consulta(ruta_dict, r)
        nombre    = (
            f"Consulta_SL_{ruta.get('ID_Ruta','')}_"
            f"{str(ruta.get('Cliente','')).replace(' ','_')}.pdf"
        )
        st.download_button(
            label="📄 Descargar PDF de esta Ruta",
            data=pdf_bytes,
            file_name=nombre,
            mime="application/pdf",
            use_container_width=True,
            key=f"sl_cons_pdf_{ruta.get('ID_Ruta','')}",
        )
    except Exception as ex:
        alert("error", f"Error generando PDF: {ex}")


# ─────────────────────────────────────────────────────────────────────────────
# RENDER PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────
def render() -> None:
    sb = get_supabase_client()
    if sb is None:
        alert("error", "⚠️ Supabase no configurado.")
        return

    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("🔄 Recargar", key="sl_cons_reload"):
            _cargar_rutas.clear()
            st.rerun()
    with c2:
        st.caption("Carga cacheada 2 min.")

    df = _cargar_rutas(TABLE_RUTAS)
    if df.empty:
        alert("warn", "No hay rutas guardadas todavía.")
        alert("info", "Captura una ruta primero desde la pestaña Captura de Rutas.")
        return

    if "ID_Ruta" in df.columns:
        df = df.set_index("ID_Ruta", drop=False)

    st.markdown("### 🔎 Buscar Ruta")
    df_filtrado = _filtrar(df)

    if df_filtrado.empty:
        alert("info", "No hay rutas que coincidan con los filtros.")
        return

    idx_sel = st.selectbox(
        "Selecciona la ruta a consultar",
        options=df_filtrado.index.tolist(),
        format_func=lambda i: _label_ruta(df_filtrado.loc[i]),
        key="sl_cons_select",
    )

    ruta = df_filtrado.loc[idx_sel]

    pxm_cargado_reg = safe(ruta.get("PxM_Cargado"))
    pxm_vacio_reg   = safe(ruta.get("PxM_Vacio"))

    divider()
    section_header("⚙️", "Ajustes para Simulación de PxM")

    valores = cargar_datos_generales()

    aj1, aj2, aj3 = st.columns(3)
    pxm_cargado_sim = aj1.number_input(
        "PxM Owner Cargado ($/mi)",
        value=pxm_cargado_reg if pxm_cargado_reg > 0 else safe(valores.get("PxM Owner Subidas", DEFAULTS["PxM Owner Subidas"])),
        step=0.01, format="%.4f",
        key="sl_cons_pxm_carg",
    )
    pxm_vacio_sim = aj2.number_input(
        "PxM Owner Vacío ($/mi)",
        value=pxm_vacio_reg if pxm_vacio_reg > 0 else safe(valores.get("PxM Owner Vacio", DEFAULTS["PxM Owner Vacio"])),
        step=0.01, format="%.4f",
        key="sl_cons_pxm_vac",
    )
    aj3.markdown(
        f"**Registrado:**\n"
        f"- Cargado: **${pxm_cargado_reg:.4f}/mi**\n"
        f"- Vacío:   **${pxm_vacio_reg:.4f}/mi**",
    )

    # ── Botones de acción — sin asignar manualmente al session_state ──────────
    col_sim, col_reset = st.columns(2)
    with col_sim:
        simular = st.button("🔁 Simular con PxM ajustado", key="sl_cons_btn_sim", type="primary",
                             use_container_width=True)
    with col_reset:
        reset = st.button("↩️ Volver a valores reales",   key="sl_cons_btn_reset",
                           use_container_width=True)

    # Gestión del flag de simulación usando una key diferente al botón
    if simular:
        st.session_state["sl_cons_modo_sim"] = True
    if reset:
        st.session_state["sl_cons_modo_sim"] = False

    es_simulacion = st.session_state.get("sl_cons_modo_sim", False)

    # ── Construir valores para el cálculo ─────────────────────────────────────
    tipo_ruta = str(ruta.get("Tipo_Viaje", "NB"))
    modo      = str(ruta.get("Modo", "Sencillo"))

    vals_sim = dict(valores)
    if es_simulacion:
        if tipo_ruta in {"SB", "D2DSB"}:
            key_c = "PxM Owner Bajadas Team" if modo == "Team" else "PxM Owner Bajadas"
        else:
            key_c = "PxM Owner Subidas Team" if modo == "Team" else "PxM Owner Subidas"
        key_v = "PxM Owner Vacio Team" if modo == "Team" else "PxM Owner Vacio"
        vals_sim[key_c] = pxm_cargado_sim
        vals_sim[key_v] = pxm_vacio_sim

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
        valores              = vals_sim,
    )

    divider()
    _mostrar_resultados(r, ruta, es_simulacion=es_simulacion)
