"""
consulta_ruta.py – Set Logis Plus
Patrón: filtros → selector → ajuste PxM → simular → resultados.
Sin HTML propio. Sin cálculos directos: usa calcular_ruta_setlogis de _shared.
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
from ui.components import section_header, alert, divider, kpi_row, status_badge
from ._shared import (
    TABLE_RUTAS,
    EXTRAS_USA,
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
# FORMATO DE ETIQUETA EN SELECTOR
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

        tipos     = ["Todos"] + sorted(df["Tipo_Viaje"].dropna().unique().tolist()) if "Tipo_Viaje" in df.columns else ["Todos"]
        clientes  = ["Todos"] + sorted(df["Cliente"].dropna().astype(str).unique().tolist()) if "Cliente" in df.columns else ["Todos"]

        f_tipo    = fc1.selectbox("Tipo de viaje", tipos,    key="sl_cons_ftipo")
        f_cliente = fc2.selectbox("Cliente",        clientes, key="sl_cons_fcli")
        f_origen  = fc3.text_input("Ruta USA contiene", placeholder="LAREDO, DALLAS…", key="sl_cons_forig")
        f_id      = fc4.text_input("ID Ruta",            placeholder="SL000001",        key="sl_cons_fid")

    out = df.copy()
    if f_tipo != "Todos":
        out = out[out["Tipo_Viaje"] == f_tipo]
    if f_cliente != "Todos":
        out = out[out["Cliente"].astype(str) == f_cliente]
    if f_origen.strip():
        out = out[out.get("Ruta_USA", pd.Series(dtype=str)).astype(str).str.contains(f_origen.strip(), case=False, na=False)]
    if f_id.strip():
        out = out[out.get("ID_Ruta", pd.Series(dtype=str)).astype(str).str.contains(f_id.strip(), case=False, na=False)]
    return out


# ─────────────────────────────────────────────────────────────────────────────
# PANEL DE RESULTADOS
# ─────────────────────────────────────────────────────────────────────────────
def _mostrar_resultados(r: dict, ruta: pd.Series, es_simulacion: bool) -> None:
    """Muestra el resultado registrado o simulado de una ruta."""

    if es_simulacion:
        alert("info", "Estás viendo una simulación con PxM ajustado. Los valores registrados no cambian.")

    # ── KPIs principales ────────────────────────────────────────────────────
    ut_neta  = safe(r.get("Utilidad_Neta"))
    ut_color = "#10b981" if ut_neta >= 0 else "#DC2626"

    kpi_row([
        {"icono": "💵", "label": "Ingreso Total",   "valor": f"${safe(r.get('Ingreso_Global')):,.2f}",  "color": "#1B2266"},
        {"icono": "📦", "label": "Costo Directo",   "valor": f"${safe(r.get('Costo_Directo')):,.2f}",   "color": "#6B7280"},
        {"icono": "📉", "label": "Costo Indirecto", "valor": f"${safe(r.get('Costo_Indirecto')):,.2f}", "color": "#F59E0B"},
        {"icono": "📊", "label": "Ut. Bruta",       "valor": f"${safe(r.get('Utilidad_Bruta')):,.2f}",  "color": "#3B82F6"},
        {"icono": "✅", "label": "Ut. Neta",         "valor": f"${ut_neta:,.2f}",                        "color": ut_color},
    ])

    # ── Porcentajes ──────────────────────────────────────────────────────────
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("% Costo Directo",   f"{safe(r.get('Pct_Costo_Directo')):.1f}%")
    p2.metric("% Costo Indirecto", f"{safe(r.get('Pct_Costo_Indirecto')):.1f}%")
    p3.metric("% Ut. Bruta",       f"{safe(r.get('Pct_Ut_Bruta')):.1f}%")
    p4.metric("% Ut. Neta",        f"{safe(r.get('Pct_Ut_Neta')):.1f}%")

    divider()

    # ── Desglose por secciones ───────────────────────────────────────────────
    tipo = str(ruta.get("Tipo_Viaje", ""))
    aplica_mx    = tiene_mx(tipo)
    aplica_cruce = bool(ruta.get("Incluye_Cruce", False))

    # Definir tabs según qué tramos aplican
    tab_labels = ["🇺🇸 Ruta Americana"]
    if aplica_cruce:
        tab_labels.append("🛂 Cruce")
    if aplica_mx:
        tab_labels.append("🇲🇽 Ruta Mexicana")

    tabs = st.tabs(tab_labels)

    # Tab USA
    with tabs[0]:
        ci, cc = st.columns(2)
        with ci:
            section_header("💰", "Ingresos USA")
            flete = safe(r.get("Flete_USA"))
            fuel  = safe(r.get("Fuel"))
            st.caption(f"Flete USA:  **${flete:,.2f}**")
            if fuel > 0:
                st.caption(f"Fuel:       **${fuel:,.2f}**")
            st.caption(f"**Total: ${safe(r.get('Flete_Fuel')):,.2f}**")
        with cc:
            section_header("💸", "Costos Owner")
            ml  = safe(r.get("Miles_Load"))
            sm  = safe(r.get("Short_Miles"))
            me  = safe(r.get("Miles_Empty"))
            pxc = safe(r.get("PxM_Cargado"))
            pxv = safe(r.get("PxM_Vacio"))
            st.caption(f"Owner Cargado ({sm:.0f} mi × ${pxc:.4f}): **${safe(r.get('Pago_Owner_Cargado')):,.2f}**")
            st.caption(f"Owner Vacío   ({me:.0f} mi × ${pxv:.4f}): **${safe(r.get('Pago_Owner_Vacio')):,.2f}**")
            ec = safe(r.get("Extras_Costo"))
            if ec > 0:
                st.caption(f"Extras costo: **${ec:,.2f}**")
            st.caption(f"Indirecto: **${safe(r.get('Costo_Indirecto')):,.2f}**")
            st.caption(f"**Pago Owner Total: ${safe(r.get('Pago_Owner_Total')):,.2f}**")

    # Tab Cruce
    if aplica_cruce and len(tabs) > 1:
        with tabs[tab_labels.index("🛂 Cruce")]:
            ci2, cc2 = st.columns(2)
            with ci2:
                section_header("💰", "Ingreso Cruce")
                st.caption(f"Ingreso: **${safe(r.get('Ingreso_Cruce')):,.2f}**")
            with cc2:
                section_header("💸", "Costo Cruce")
                st.caption(f"Tipo: **{ruta.get('Tipo_Cruce', '—')}**")
                st.caption(f"Costo: **${safe(r.get('Costo_Cruce')):,.2f}**")

    # Tab MX
    if aplica_mx:
        with tabs[tab_labels.index("🇲🇽 Ruta Mexicana")]:
            ci3, cc3 = st.columns(2)
            with ci3:
                section_header("💰", "Ingreso MX")
                st.caption(f"Ingreso: **${safe(r.get('Ingreso_MX')):,.2f}**")
            with cc3:
                section_header("💸", "Costo MX")
                st.caption(f"Costo: **${safe(r.get('Costo_MX')):,.2f}**")

    # ── Extras individuales ──────────────────────────────────────────────────
    extras_presentes = []
    for extra in EXTRAS_USA:
        col_monto   = f"Extra_{extra.replace(' ', '_')}"
        col_cobrado = f"Extra_{extra.replace(' ', '_')}_Cobrado"
        monto   = safe(ruta.get(col_monto, 0))
        cobrado = bool(ruta.get(col_cobrado, False))
        if monto > 0:
            extras_presentes.append((extra, monto, cobrado))

    if extras_presentes:
        divider()
        section_header("➕", "Extras aplicados")
        for nombre, monto, cobrado in extras_presentes:
            tag = (
                status_badge("Cobrado al cliente", "concluido")
                if cobrado
                else status_badge("Solo costo", "pendiente")
            )
            st.markdown(f"**{nombre}**: ${monto:,.2f} &nbsp; {tag}", unsafe_allow_html=True)

    # ── Datos de operación ───────────────────────────────────────────────────
    divider()
    section_header("📋", "Datos de Operación")
    op1, op2, op3 = st.columns(3)
    op1.caption(f"Modo:        **{ruta.get('Modo', '—')}**")
    op1.caption(f"Modalidad:   **{ruta.get('Modalidad', '—')}**")
    op1.caption(f"TC USD/MXP:  **{safe(ruta.get('TC_USD_MXP')):.2f}**")
    op2.caption(f"Millas Load:   **{safe(ruta.get('Miles_Load')):.0f} mi**")
    op2.caption(f"Short Miles:   **{safe(ruta.get('Short_Miles')):.0f} mi**")
    op2.caption(f"Millas Empty:  **{safe(ruta.get('Miles_Empty')):.0f} mi**")
    op3.caption(f"Usuario:  **{ruta.get('Usuario', '—')}**")
    op3.caption(f"Fecha:    **{ruta.get('Fecha', '—')}**")
    op3.caption(f"ID:       **{ruta.get('ID_Ruta', '—')}**")


# ─────────────────────────────────────────────────────────────────────────────
# RENDER PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────
def render() -> None:
    sb = get_supabase_client()
    if sb is None:
        alert("error", "Supabase no configurado.")
        return

    # ── Recargar ─────────────────────────────────────────────────────────────
    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("🔄 Recargar rutas", key="sl_cons_reload"):
            _cargar_rutas.clear()
            st.rerun()
    with c2:
        st.caption("Carga cacheada 2 min para que sea rápido.")

    df = _cargar_rutas(TABLE_RUTAS)
    if df.empty:
        alert("warn", "No hay rutas guardadas todavía.")
        alert("info", "Captura una ruta primero desde la pestaña Captura de Rutas.")
        return

    if "ID_Ruta" in df.columns:
        df = df.set_index("ID_Ruta", drop=False)

    # ── Buscar ruta ───────────────────────────────────────────────────────────
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

    # ── Valores PxM registrados ───────────────────────────────────────────────
    pxm_cargado_reg = safe(ruta.get("PxM_Cargado"))
    pxm_vacio_reg   = safe(ruta.get("PxM_Vacio"))

    # ── Panel de ajuste ───────────────────────────────────────────────────────
    divider()
    section_header("⚙️", "Ajustes para Simulación")

    valores = cargar_datos_generales()

    aj1, aj2, aj3 = st.columns(3)
    pxm_cargado_sim = aj1.number_input(
        "PxM Owner Cargado ($/mi)",
        value=pxm_cargado_reg if pxm_cargado_reg > 0 else safe(valores.get("PxM Owner Subidas", DEFAULTS["PxM Owner Subidas"])),
        step=0.01,
        format="%.4f",
        key="sl_cons_pxm_carg",
    )
    pxm_vacio_sim = aj2.number_input(
        "PxM Owner Vacío ($/mi)",
        value=pxm_vacio_reg if pxm_vacio_reg > 0 else safe(valores.get("PxM Owner Vacio", DEFAULTS["PxM Owner Vacio"])),
        step=0.01,
        format="%.4f",
        key="sl_cons_pxm_vac",
    )
    aj3.markdown(
        f"**Registrado:**\n"
        f"- Cargado: **${pxm_cargado_reg:.4f}/mi**\n"
        f"- Vacío: **${pxm_vacio_reg:.4f}/mi**",
    )

    simular = st.button("🔁 Simular con PxM ajustado", key="sl_cons_simular", type="primary")
    if simular:
        st.session_state["sl_cons_simular"] = True

    # ── Construir valores para el cálculo ────────────────────────────────────
    # Tomamos los datos de ingreso, cruce y MX exactamente como se guardaron.
    # Solo el PxM del owner cambia en simulación.
    tipo_ruta = str(ruta.get("Tipo_Viaje", "NB"))
    modo      = str(ruta.get("Modo", "Sencillo"))

    # Determinar qué PxM usar
    simulando = st.session_state.get("sl_cons_simular", False)
    if simulando:
        vals_sim = dict(valores)
        # Inyectar el PxM ajustado según dirección y modo
        if tipo_ruta in {"SB", "D2DSB"}:
            key_c = "PxM Owner Bajadas Team" if modo == "Team" else "PxM Owner Bajadas"
        else:
            key_c = "PxM Owner Subidas Team" if modo == "Team" else "PxM Owner Subidas"
        key_v = "PxM Owner Vacio Team" if modo == "Team" else "PxM Owner Vacio"
        vals_sim[key_c] = pxm_cargado_sim
        vals_sim[key_v] = pxm_vacio_sim
    else:
        vals_sim = dict(valores)

    # Recalcular con los valores guardados de ingresos y costos de la ruta
    r = calcular_ruta_setlogis(
        tipo_ruta           = tipo_ruta,
        modo                = modo,
        ruta_usa            = str(ruta.get("Ruta_USA", "")),
        cliente             = str(ruta.get("Cliente", "")),
        miles_load          = safe(ruta.get("Miles_Load")),
        miles_empty         = safe(ruta.get("Miles_Empty")),
        short_miles         = safe(ruta.get("Short_Miles")),
        flete_usa           = safe(ruta.get("Flete_USA")),
        fuel                = safe(ruta.get("Fuel")),
        tipo_cruce          = str(ruta.get("Tipo_Cruce", "Propio")),
        tipo_carga_cruce    = str(ruta.get("Tipo_Carga_Cruce", "Cargado")),
        ingreso_cruce       = safe(ruta.get("Ingreso_Cruce")),
        costo_cruce_externo = safe(ruta.get("Costo_Cruce")),
        ingreso_mx          = safe(ruta.get("Ingreso_MX")),
        costo_mx            = safe(ruta.get("Costo_MX")),
        extras_ingreso      = safe(ruta.get("Extras_Ingreso")),
        extras_costo        = safe(ruta.get("Extras_Costo")),
        modo_costo_indirecto= "CXM",   # por defecto; ajustable si se guarda en la ruta
        valores             = vals_sim,
    )

    # ── Mostrar resultados ────────────────────────────────────────────────────
    divider()
    # ─────────────────────────────────────────────────────────────────────────────
    # PDF CONSULTA INDIVIDUAL
    # ─────────────────────────────────────────────────────────────────────────────
    def _generar_pdf_consulta(ruta: dict, r: dict) -> bytes:
        """
        Genera PDF de consulta individual de una ruta Set Logis.
        ruta: dict con los campos guardados en Supabase.
        r:    dict resultado de calcular_ruta_setlogis (KPIs recalculados).
        """
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=letter,
            leftMargin=0.6 * inch, rightMargin=0.6 * inch,
            topMargin=0.5 * inch, bottomMargin=0.5 * inch,
        )
        styles  = getSampleStyleSheet()
        sub_s   = ParagraphStyle("S", parent=styles["Heading2"], fontSize=10,
                              textColor=colors.HexColor("#1B2266"), spaceBefore=10, spaceAfter=3)
        norm_s  = ParagraphStyle("N", parent=styles["Normal"],  fontSize=8, leading=11)
        foot_s  = ParagraphStyle("F", parent=styles["Normal"],  fontSize=7,
                              textColor=colors.HexColor("#6c757d"), alignment=TA_CENTER)
        story   = []

        # ── Encabezado ──────────────────────────────────────────────────────────
        hdr = Table([[
            Paragraph("<b>SET LOGIS PLUS</b>",
                      ParagraphStyle("H", parent=styles["Normal"], fontSize=13, textColor=colors.white)),
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

        # ── Datos generales ──────────────────────────────────────────────────────
        story.append(Paragraph("Datos de la Ruta", sub_s))
        gen_data = [
            ["Campo",        "Valor",                          "Campo",        "Valor"],
            ["ID Ruta",      str(ruta.get("ID_Ruta", "")),     "Fecha",        str(ruta.get("Fecha", ""))],
            ["Tipo",         str(ruta.get("Tipo_Viaje", "")),  "Modo",         str(ruta.get("Modo", ""))],
            ["Cliente",      str(ruta.get("Cliente", "")),     "Modalidad",    str(ruta.get("Modalidad", ""))],
            ["Ruta USA",     str(ruta.get("Ruta_USA", "")),    "Tipo Cruce",   str(ruta.get("Tipo_Cruce", ""))],
        ]
        origen_mx = str(ruta.get("Origen_MX", "")).strip()
        if origen_mx:
            gen_data.append(["Origen MX", origen_mx, "Destino MX", str(ruta.get("Destino_MX", ""))])

        t_gen = Table(gen_data, colWidths=[1.3 * inch, 2.1 * inch, 1.3 * inch, 2.1 * inch])
        t_gen.setStyle(TableStyle([
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
        story.append(t_gen)
        story.append(Spacer(1, 8))

        # ── Millas y PxM ────────────────────────────────────────────────────────
        story.append(Paragraph("Millas y Precio por Milla", sub_s))
        mil_data = [
            ["Miles Load",  f"{safe(ruta.get('Miles_Load')):.0f} mi",
             "Short Miles", f"{safe(ruta.get('Short_Miles')):.0f} mi"],
            ["Miles Empty", f"{safe(ruta.get('Miles_Empty')):.0f} mi",
             "Millas Totales", f"{safe(r.get('Millas_Totales')):.0f} mi"],
            ["PxM Cargado", f"${safe(r.get('PxM_Cargado')):.4f}/mi",
             "PxM Vacío",   f"${safe(r.get('PxM_Vacio')):.4f}/mi"],
        ]
        t_mil = Table(mil_data, colWidths=[1.3 * inch, 2.1 * inch, 1.3 * inch, 2.1 * inch])
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

        # ── Ingresos y Costos ────────────────────────────────────────────────────
        story.append(Paragraph("Ingresos y Costos", sub_s))
        fin_data = [
            ["Concepto",          "Monto USD",                        "Concepto",        "Monto USD"],
            ["Flete USA",         f"${safe(r.get('Flete_USA')):,.2f}",
             "Owner Cargado",    f"${safe(r.get('Pago_Owner_Cargado')):,.2f}"],
            ["Fuel",              f"${safe(r.get('Fuel')):,.2f}",
             "Owner Vacío",      f"${safe(r.get('Pago_Owner_Vacio')):,.2f}"],
            ["Ingreso Cruce",     f"${safe(r.get('Ingreso_Cruce')):,.2f}",
             "Costo Cruce",      f"${safe(r.get('Costo_Cruce')):,.2f}"],
            ["Ingreso MX",        f"${safe(r.get('Ingreso_MX')):,.2f}",
             "Costo MX",         f"${safe(r.get('Costo_MX')):,.2f}"],
            ["Extras (cobrados)", f"${safe(r.get('Extras_Ingreso')):,.2f}",
             "Extras (costo)",   f"${safe(r.get('Extras_Costo')):,.2f}"],
            ["",                  "",
             "Costo Indirecto",  f"${safe(r.get('Costo_Indirecto')):,.2f}"],
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

        # ── Resumen financiero ───────────────────────────────────────────────────
        story.append(Paragraph("Resumen de Utilidad", sub_s))
        ing  = safe(r.get("Ingreso_Global"))
        cd   = safe(r.get("Costo_Directo"))
        ci   = safe(r.get("Costo_Indirecto"))
        ub   = safe(r.get("Utilidad_Bruta"))
        un   = safe(r.get("Utilidad_Neta"))
        pct_cd = safe(r.get("Pct_Costo_Directo"))
        pct_ub = safe(r.get("Pct_Ut_Bruta"))
        pct_ci = safe(r.get("Pct_Costo_Indirecto"))
        pct_un = safe(r.get("Pct_Ut_Neta"))

        color_un_pdf = colors.HexColor("#28a745") if un >= 0 else colors.HexColor("#dc3545")
        res_data = [
            ["Concepto",        "Monto (USD)",       "%"],
            ["Ingreso Total",   f"${ing:,.2f}",      "100.00%"],
            ["Costo Directo",   f"${cd:,.2f}",       f"{pct_cd:.1f}%"],
            ["Ut. Bruta",        f"${ub:,.2f}",       f"{pct_ub:.1f}%"],
            ["Costo Indirecto", f"${ci:,.2f}",       f"{pct_ci:.1f}%"],
            ["Ut. Neta",         f"${un:,.2f}",       f"{pct_un:.1f}%"],
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

        # ── Footer ───────────────────────────────────────────────────────────────
        story.append(Paragraph(
            f"Reporte generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} — Set Logis Plus",
            foot_s,
        ))
        doc.build(story)
        return buf.getvalue()
