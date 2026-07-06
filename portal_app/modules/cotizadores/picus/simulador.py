"""
simulador.py — Cotizador Picus
Simulador de Vuelta Redonda.
Diseño homologado con plataforma anterior de Igloo (referencia gerencial):
  - Sin st.title()
  - Recargar en col [1,4]
  - Filtros en expander para ruta principal
  - Selector con label completo (ID | Fecha | Tipo | Cliente | Origen → Destino)
  - Expander de detalle ruta seleccionada
  - Sugerencias con descripcion: ID | Fecha — Cliente Origen → Destino (%)
  - Botón Simular centrado
  - Resultado: expanders por ruta (expanded=True) + mostrar_resultados_utilidad
  - Detalle por columnas con st.markdown (igual al antiguo de Igloo)
  - PDF con header azul, resumen y detalle de cada ruta con tabla financiera
"""
from __future__ import annotations

import tempfile
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
from ui.components import section_header, alert, divider, mostrar_resultados_ruta, banner_tarifa_sugerida

from ._helpers import (
    safe_number,
    calcular_costos_indirectos,
    calcular_utilidades_vuelta_redonda,
    load_rutas_picus,
    filtrar_rutas_picus,
    label_ruta_picus,
)


# ─────────────────────────────────────────────
# Sugerencias de regreso
# ─────────────────────────────────────────────

def _sugerir_regresos(ruta_1: dict, df: pd.DataFrame) -> list[dict]:
    tipo_principal = str(ruta_1.get("Tipo", "")).strip().upper()
    destino_1      = str(ruta_1.get("Destino", "")).strip().upper()

    if tipo_principal == "IMPORTACION":
        tipo_regreso = "EXPORTACION"
    elif tipo_principal == "EXPORTACION":
        tipo_regreso = "IMPORTACION"
    else:
        tipo_regreso = None

    sugerencias = []

    # 1) Regreso directo
    if tipo_regreso:
        directas = df[(df["Tipo"] == tipo_regreso) & (df["Origen"] == destino_1)]
        for _, row in directas.iterrows():
            tramos = [ruta_1, row.to_dict()]
            util   = calcular_utilidades_vuelta_redonda(tramos)
            pct    = util["porcentaje_bruta"]
            sugerencias.append({
                "descripcion": (
                    f"{row.get('ID_Ruta','')} | {row.get('Fecha','')} — "
                    f"{row.get('Cliente','')} {row.get('Origen','')} → "
                    f"{row.get('Destino','')} ({pct:.2f}%)"
                ),
                "tramos":  [row.to_dict()],
                "util":    util,
                "pct":     pct,
            })

    # 2) Regreso con VACIO como puente
    if tipo_regreso:
        vacios = df[(df["Tipo"] == "VACIO") & (df["Origen"] == destino_1)]
        for _, vacio in vacios.iterrows():
            origen_post = str(vacio.get("Destino", "")).strip().upper()
            candidatos  = df[(df["Tipo"] == tipo_regreso) & (df["Origen"] == origen_post)]
            for _, final in candidatos.iterrows():
                tramos = [ruta_1, vacio.to_dict(), final.to_dict()]
                util   = calcular_utilidades_vuelta_redonda(tramos)
                pct    = util["porcentaje_bruta"]
                sugerencias.append({
                    "descripcion": (
                        f"{final.get('ID_Ruta','')} | {final.get('Fecha','')} — "
                        f"{final.get('Cliente','')} (Vacio {vacio.get('Origen','')}→"
                        f"{vacio.get('Destino','')}) → {final.get('Destino','')} ({pct:.2f}%)"
                    ),
                    "tramos":  [vacio.to_dict(), final.to_dict()],
                    "util":    util,
                    "pct":     pct,
                })

    # 3) Principal VACIO → buscar IMPORT/EXPORT desde su destino
    if tipo_principal == "VACIO":
        candidatos = df[
            (df["Tipo"].isin(["IMPORTACION", "EXPORTACION"])) &
            (df["Origen"] == destino_1)
        ]
        for _, final in candidatos.iterrows():
            tramos = [ruta_1, final.to_dict()]
            util   = calcular_utilidades_vuelta_redonda(tramos)
            pct    = util["porcentaje_bruta"]
            sugerencias.append({
                "descripcion": (
                    f"{final.get('ID_Ruta','')} | {final.get('Fecha','')} — "
                    f"{final.get('Cliente','')} {final.get('Origen','')} → "
                    f"{final.get('Destino','')} ({pct:.2f}%)"
                ),
                "tramos":  [final.to_dict()],
                "util":    util,
                "pct":     pct,
            })

    return sorted(sugerencias, key=lambda x: x["pct"], reverse=True)


# ─────────────────────────────────────────────
# PDF (igual estructura que plataforma anterior de Igloo)
# ─────────────────────────────────────────────

def _safe_txt(text: str) -> str:
    try:
        return str(text).encode("latin-1", "replace").decode("latin-1")
    except Exception:
        return str(text)


def generar_pdf_vuelta_redonda(
    rutas_seleccionadas: list,
    ingreso_total:     float,
    costo_total:       float,
    utilidad_bruta:    float,
    costos_indirectos: float,
    utilidad_neta:     float,
    pct_bruta:         float,
    pct_neta:          float,
) -> str:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    doc = SimpleDocTemplate(
        tmp.name, pagesize=letter,
        leftMargin=0.6*inch, rightMargin=0.6*inch,
        topMargin=0.5*inch,  bottomMargin=0.5*inch,
    )

    styles     = getSampleStyleSheet()
    AZUL       = colors.HexColor("#1B2266")
    GRIS       = colors.HexColor("#f0f2f6")
    AZUL_LIGHT = colors.HexColor("#e8f4f8")

    normal_s   = ParagraphStyle("N", parent=styles["Normal"], fontSize=9, leading=12)
    subtitle_s = ParagraphStyle("S", parent=styles["Heading2"], fontSize=11,
                                textColor=AZUL, spaceBefore=12, spaceAfter=4)
    compact    = ParagraphStyle("C", parent=styles["Normal"], fontSize=7, leading=8)
    footer_s   = ParagraphStyle("F", parent=styles["Normal"], fontSize=7,
                                textColor=colors.HexColor("#6c757d"), alignment=TA_CENTER)

    story = []

    # ── Header azul (igual que plataforma anterior de Igloo) ─────
    header_data = [[
        Paragraph(_safe_txt("<b>PICUS</b>"), ParagraphStyle(
            "HL", parent=styles["Normal"], fontSize=13, textColor=colors.white,
        )),
        Paragraph(_safe_txt("Simulador de Vuelta Redonda"), ParagraphStyle(
            "HR", parent=styles["Normal"], fontSize=9,
            textColor=colors.white, alignment=TA_RIGHT,
        )),
    ]]
    header_t = Table(header_data, colWidths=[5.0*inch, 2.0*inch])
    header_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), AZUL),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (0, -1),  12),
        ("RIGHTPADDING",  (-1, 0), (-1, -1), 12),
    ]))
    story.append(header_t)
    story.append(Spacer(1, 12))

    # ── Resumen de Vuelta Redonda ─────────────────────────────────
    story.append(Paragraph(_safe_txt("Resumen de Vuelta Redonda"), subtitle_s))

    color_un  = colors.HexColor("#28a745") if utilidad_neta >= 0 else colors.HexColor("#dc3545")
    pct_costo = (costo_total / ingreso_total * 100) if ingreso_total else 0
    pct_ind   = (costos_indirectos / ingreso_total * 100) if ingreso_total else 0

    resumen_data = [
        ["Concepto",          "Monto",                          "%"],
        ["Ingreso Total",     f"${ingreso_total:,.2f} MXP",     "100.00%"],
        ["Costo Directo",     f"${costo_total:,.2f} MXP",       f"{pct_costo:.2f}%"],
        ["Utilidad Bruta",    f"${utilidad_bruta:,.2f} MXP",    f"{pct_bruta:.2f}%"],
        ["Costos Indirectos", f"${costos_indirectos:,.2f} MXP", f"{pct_ind:.2f}%"],
        ["Utilidad Neta",     f"${utilidad_neta:,.2f} MXP",     f"{pct_neta:.2f}%"],
    ]
    res_t = Table(resumen_data, colWidths=[2.5*inch, 2.5*inch, 2.0*inch])
    res_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  AZUL),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 7),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("ALIGN",         (1, 1), (-1, -1), "RIGHT"),
        ("BACKGROUND",    (0, 5), (-1, 5),  color_un),
        ("TEXTCOLOR",     (0, 5), (-1, 5),  colors.white),
        ("FONTNAME",      (0, 5), (-1, 5),  "Helvetica-Bold"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
    ]))
    story.append(res_t)
    story.append(Spacer(1, 14))

    # ── Detalle de cada ruta ────────────────────────────────────
    story.append(Paragraph(_safe_txt("Detalle de Rutas"), subtitle_s))

    for i, ruta in enumerate(rutas_seleccionadas, 1):
        tipo_ruta = str(ruta.get("Tipo", ""))

        # Encabezado de ruta
        story.append(Paragraph(
            _safe_txt(f"{i}. {tipo_ruta} -- {ruta.get('Cliente', '')}"),
            ParagraphStyle("RH", parent=normal_s, fontSize=10,
                           textColor=AZUL, spaceBefore=8, spaceAfter=4),
        ))

        # Tabla datos básicos (4 columnas)
        cliente_p = Paragraph(_safe_txt(str(ruta.get("Cliente", ""))), compact)
        origen_p  = Paragraph(_safe_txt(str(ruta.get("Origen",  ""))), compact)
        destino_p = Paragraph(_safe_txt(str(ruta.get("Destino", ""))), compact)

        ruta_info = [
            [_safe_txt("ID Ruta"), _safe_txt(str(ruta.get("ID_Ruta", ""))),
             _safe_txt("Fecha"),   _safe_txt(str(ruta.get("Fecha", ""))[:10])],
            [_safe_txt("Tipo"),    _safe_txt(tipo_ruta),
             _safe_txt("KM"),      _safe_txt(f"{safe_number(ruta.get('KM', 0)):,.0f}")],
            [_safe_txt("Cliente"), cliente_p,
             _safe_txt("Modo"),    _safe_txt(str(ruta.get("Modo de Viaje", "Operador")))],
            [_safe_txt("Origen"),  origen_p,
             _safe_txt("Destino"), destino_p],
        ]
        ruta_t = Table(ruta_info, colWidths=[1.2*inch, 2.0*inch, 1.2*inch, 2.0*inch])
        ruta_t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), GRIS),
            ("BACKGROUND", (2, 0), (2, -1), GRIS),
            ("FONTNAME",   (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME",   (2, 0), (2, -1), "Helvetica-Bold"),
            ("FONTSIZE",   (0, 0), (-1, -1), 7),
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
            ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ]))
        story.append(ruta_t)
        story.append(Spacer(1, 6))

        # Tabla financiera (igual que plataforma anterior de Igloo)
        ing_orig    = safe_number(ruta.get("Ingreso_Original", 0))
        moneda      = str(ruta.get("Moneda", "MXP"))
        tc          = safe_number(ruta.get("Tipo de cambio", 1.0))
        ing_total   = safe_number(ruta.get("Ingreso Total", 0))
        costo_ruta  = safe_number(ruta.get("Costo_Total_Ruta", 0))
        ind_ruta    = calcular_costos_indirectos(tipo_ruta, ing_total)
        label_ind   = "Costos Indirectos (35%)" if ind_ruta > 0 else "Costos Indirectos (0% - VACIO)"

        fin_data = [
            [_safe_txt("Ingreso Original"),    _safe_txt(f"${ing_orig:,.2f}")],
            [_safe_txt("Moneda"),              _safe_txt(moneda)],
            [_safe_txt("Tipo de cambio"),      _safe_txt(f"{tc:,.2f}")],
            [_safe_txt("Ingreso Total"),       _safe_txt(f"${ing_total:,.2f} MXP")],
            [_safe_txt("Costo Directo Ruta"),  _safe_txt(f"${costo_ruta:,.2f} MXP")],
            [_safe_txt(label_ind),             _safe_txt(f"${ind_ruta:,.2f} MXP")],
        ]
        fin_t = Table(fin_data, colWidths=[2.5*inch, 3.5*inch])
        fin_t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), AZUL_LIGHT),
            ("FONTNAME",   (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE",   (0, 0), (-1, -1), 7),
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
            ("ALIGN",      (1, 0), (1, -1), "RIGHT"),
            ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ]))
        story.append(fin_t)
        story.append(Spacer(1, 10))

    # ── Footer ───────────────────────────────────────────────────
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        _safe_txt(f"Reporte generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} -- Picus"),
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
        alert("warn", "⚠️ Supabase no configurado.")
        return

    st.session_state.setdefault("pic_sim_realizada", False)

    # ── Recargar ─────────────────────────────────────────────────
    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("🔄 Recargar", key="pic_sim_reload"):
            load_rutas_picus.clear()
            st.rerun()
    with c2:
        st.caption("Carga cacheada 2 min. Usa 'Recargar' si acabas de guardar algo.")

    df = load_rutas_picus()
    if df.empty:
        alert("warn", "⚠️ No hay rutas registradas en Supabase.")
        return

    # ── Paso 1: Ruta Principal ────────────────────────────────────
    divider()
    section_header("📌", "Selecciona la Ruta Principal")
    st.caption("Filtra las rutas disponibles y selecciona la ruta de ida.")

    df_principal = filtrar_rutas_picus(df, "pic_sim_p1")

    if df_principal.empty:
        alert("warn", "No hay rutas que cumplan los filtros.")
        return

    st.write(f"**Selecciona una ruta ({len(df_principal)} disponibles)**")
    opciones_p1 = [label_ruta_picus(row) for _, row in df_principal.iterrows()]
    sel_p1      = st.selectbox("Ruta Principal", opciones_p1, key="pic_sim_sel_p1")
    idx_p1      = opciones_p1.index(sel_p1)
    ruta_p1_row = df_principal.iloc[idx_p1]
    ruta_1      = ruta_p1_row.to_dict()

    with st.expander("📋 Ver detalles de la ruta seleccionada", expanded=False):
        d1, d2 = st.columns(2)
        with d1:
            st.markdown(f"**ID Ruta:** {ruta_1.get('ID_Ruta','')}")
            st.markdown(f"**Tipo:** {ruta_1.get('Tipo','')}")
            st.markdown(f"**Cliente:** {ruta_1.get('Cliente','')}")
            st.markdown(f"**Fecha:** {ruta_1.get('Fecha','')}")
        with d2:
            st.markdown(f"**Origen:** {ruta_1.get('Origen','')}")
            st.markdown(f"**Destino:** {ruta_1.get('Destino','')}")
            st.markdown(f"**Ingreso Total:** ${safe_number(ruta_1.get('Ingreso Total',0)):,.2f}")
            st.markdown(f"**Costo Directo:** ${safe_number(ruta_1.get('Costo_Total_Ruta',0)):,.2f}")

    # ── Paso 2: Sugerencias de regreso ───────────────────────────
    divider()
    section_header("🔄", "Rutas sugeridas (combinaciones con o sin vacío)")

    sugerencias = _sugerir_regresos(ruta_1, df)

    if not sugerencias:
        alert("warn", "⚠️ No hay rutas de regreso disponibles desde el destino de la ruta principal.")
        return

    st.markdown(f"📊 Se encontraron **{len(sugerencias)} combinaciones posibles**")

    opciones_reg = {s["descripcion"]: s for s in sugerencias}
    sel_reg      = st.selectbox(
        "Selecciona una opción de regreso sugerida",
        list(opciones_reg.keys()),
        index=0,
        key="pic_sim_sel_reg",
    )
    seleccion           = opciones_reg[sel_reg]
    rutas_seleccionadas = [ruta_1] + seleccion["tramos"]

    # ── Botón Simular ─────────────────────────────────────────────
    divider()
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("🚛 Simular Vuelta Redonda", type="primary",
                     use_container_width=True, key="pic_sim_run"):
            res = calcular_utilidades_vuelta_redonda(rutas_seleccionadas)
            st.session_state["pic_sim_realizada"]  = True
            st.session_state["pic_sim_rutas"]      = rutas_seleccionadas
            st.session_state["pic_sim_resultado"]  = res
            st.rerun()

    # ── Resultados ────────────────────────────────────────────────
    if st.session_state.get("pic_sim_realizada") and st.session_state.get("pic_sim_resultado"):
        res   = st.session_state["pic_sim_resultado"]
        rutas = st.session_state.get("pic_sim_rutas", rutas_seleccionadas)

        divider()
        st.subheader("📊 Resumen de Vuelta Redonda")

        # Expanders por ruta (expanded=True, igual que plataforma anterior de Igloo)
        for i, r in enumerate(rutas, 1):
            tipo_r  = str(r.get("Tipo", "")).strip().upper()
            ing_r   = safe_number(r.get("Ingreso Total", 0))
            ind_r   = calcular_costos_indirectos(tipo_r, ing_r)
            with st.expander(f"{i}. {r.get('Tipo','')} — {r.get('Cliente','')}", expanded=True):
                st.markdown(f"**ID Ruta:** {r.get('ID_Ruta','')}")
                st.markdown(f"- Fecha: {r.get('Fecha','')}")
                st.markdown(f"- {r.get('Origen','')} → {r.get('Destino','')}")
                st.markdown(f"- Ingreso Total: **${ing_r:,.2f}**")
                st.markdown(f"- Costo Directo Ruta: ${safe_number(r.get('Costo_Total_Ruta',0)):,.2f}")
                if ind_r > 0:
                    st.markdown(f"- *Costos Indirectos (35%): ${ind_r:,.2f}*")
                else:
                    st.markdown("- *Costos Indirectos: $0.00 (VACÍO)*")

        # Utilidades globales
        divider()
        _umbral     = res["umbral_cd"]
        _tarifa_sug = res["costo_directo"] / (_umbral / 100)
        banner_tarifa_sugerida(res["costo_directo"], res["ingreso_total"], _umbral, "MXP", 0.0)
        mostrar_resultados_ruta(res, titulo="Resultado de la Vuelta Redonda")

        # Detalle de rutas por columnas (igual que plataforma anterior de Igloo)
        divider()
        st.subheader("📋 Detalle de Rutas")

        tipos_orden = ["IMPORTACION", "VACIO", "EXPORTACION"]
        rutas_por_tipo = {
            tipo: next((r for r in rutas if str(r.get("Tipo","")).upper() == tipo), None)
            for tipo in tipos_orden
        }
        cols_activas = [t for t in tipos_orden if rutas_por_tipo[t] is not None]

        if cols_activas:
            cols = st.columns(len(cols_activas))
            for idx, tipo in enumerate(cols_activas):
                r = rutas_por_tipo[tipo]
                with cols[idx]:
                    st.markdown(f"**{tipo}**")
                    st.markdown(f"Fecha: {r.get('Fecha','')}")
                    st.markdown(f"Cliente: {r.get('Cliente','')}")
                    st.markdown(f"Ruta: {r.get('Origen','')} → {r.get('Destino','')}")
                    st.markdown(f"KM: {safe_number(r.get('KM',0)):,.0f}")
                    st.markdown(f"Ingreso Original: ${safe_number(r.get('Ingreso_Original',0)):,.2f}")
                    st.markdown(f"Moneda: {r.get('Moneda','MXP')}")
                    st.markdown(f"Tipo de cambio: {safe_number(r.get('Tipo de cambio',1)):,.2f}")
                    st.markdown(f"**Ingreso Total: ${safe_number(r.get('Ingreso Total',0)):,.2f}**")
                    st.markdown(f"Costo Directo: ${safe_number(r.get('Costo_Total_Ruta',0)):,.2f}")

        # ── PDF ───────────────────────────────────────────────────
        divider()
        section_header("📥", "Generar PDF de la Simulación")
        col_p1, col_p2, col_p3 = st.columns([1, 2, 1])
        with col_p2:
            if st.button("📄 Generar PDF", key="pic_sim_pdf", use_container_width=True):
                try:
                    pdf_path = generar_pdf_vuelta_redonda(
                        rutas,
                        res["ingreso_total"], res["costo_total"],
                        res["utilidad_bruta"], res["costos_indirectos"],
                        res["utilidad_neta"], res["porcentaje_bruta"], res["porcentaje_neta"],
                    )
                    primer_ruta = rutas[0]
                    nombre_pdf  = f"Simulacion_VueltaRedonda_{primer_ruta.get('ID_Ruta','SinID')}.pdf"
                    with open(pdf_path, "rb") as f:
                        pdf_bytes = f.read()
                    st.download_button(
                        "📥 Descargar PDF",
                        data=pdf_bytes,
                        file_name=nombre_pdf,
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True,
                        key="pic_sim_dl_pdf",
                    )
                    alert("success", "✅ PDF generado exitosamente.")
                except Exception as e:
                    alert("error", f"❌ Error generando PDF: {e}")
