"""
simulador.py — Cotizador Picus
Simulador de Vuelta Redonda.
Homologado con Igloo:
  - mostrar_resultados_picus() centraliza banner + KPIs + semáforos (antes
    banner_tarifa_sugerida() + mostrar_resultados_ruta() sueltos)
  - ruta_visual_nodos() de components.py agrega la secuencia visual de la
    vuelta redonda (antes no existía en Picus)
  - _detalle_tramos() extraído como función reutilizable (antes vivía inline
    dentro de render(), igual que en Igloo homologado)
  - PDF con header azul — versión aprobada, NO se toca el diseño
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
from ui.components import section_header, alert, divider, ruta_visual_nodos

from ._helpers import (
    safe_number,
    cargar_datos_generales,
    calcular_costos_indirectos,
    calcular_utilidades_vuelta_redonda,
    load_rutas_picus,
    filtrar_rutas_picus,
    label_ruta_picus,
    mostrar_resultados_picus,
    log_accion,
)


# ─────────────────────────────────────────────
# Sugerencias de regreso — SIN CAMBIOS
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
# Detalle de rutas por columnas — extraído de render() (antes inline)
# ─────────────────────────────────────────────
def _detalle_tramos(rutas: list[dict]) -> None:
    st.subheader("📋 Detalle de Rutas")

    tipos_orden = ["IMPORTACION", "VACIO", "EXPORTACION"]
    rutas_por_tipo = {
        tipo: next((r for r in rutas if str(r.get("Tipo", "")).strip().upper() == tipo), None)
        for tipo in tipos_orden
    }
    cols_activas = [t for t in tipos_orden if rutas_por_tipo[t] is not None]

    if not cols_activas:
        return

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


# ─────────────────────────────────────────────
# PDF (igual estructura que plataforma anterior de Igloo)
# — versión aprobada, NO se toca el diseño —
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
    pct_costo = (costo_total / ingreso_total * 100) if ingreso_total else 0.0

    resumen_data = [
        [_safe_txt("Ingreso Total"),     _safe_txt(f"${ingreso_total:,.2f}")],
        [_safe_txt("Costo Directo"),     _safe_txt(f"${costo_total:,.2f} ({pct_costo:.1f}%)")],
        [_safe_txt("Utilidad Bruta"),    _safe_txt(f"${utilidad_bruta:,.2f} ({pct_bruta:.1f}%)")],
        [_safe_txt("Costos Indirectos"), _safe_txt(f"${costos_indirectos:,.2f}")],
        [_safe_txt("Utilidad Neta"),     _safe_txt(f"${utilidad_neta:,.2f} ({pct_neta:.1f}%)")],
    ]
    resumen_t = Table(resumen_data, colWidths=[3.5*inch, 3.5*inch])
    resumen_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), AZUL),
        ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("ALIGN",         (1, 1), (-1, -1), "RIGHT"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("TEXTCOLOR",     (1, -1), (1, -1), color_un),
    ]))
    story.append(resumen_t)
    story.append(Spacer(1, 12))

    # ── Detalle de cada ruta ────────────────────────────────────────
    story.append(Paragraph(_safe_txt("Detalle de Rutas de la Vuelta Redonda"), subtitle_s))
    for i, r in enumerate(rutas_seleccionadas, 1):
        tipo_r = str(r.get("Tipo", "")).strip().upper()
        fin_data = [
            [_safe_txt(f"{i}. {tipo_r}"), _safe_txt(str(r.get("Cliente", "")))],
            [_safe_txt("Ruta"), _safe_txt(f"{r.get('Origen','')} → {r.get('Destino','')}")],
            [_safe_txt("Ingreso Total"), _safe_txt(f"${safe_number(r.get('Ingreso Total', 0)):,.2f}")],
            [_safe_txt("Costo Directo"), _safe_txt(f"${safe_number(r.get('Costo_Total_Ruta', 0)):,.2f}")],
        ]
        fin_table = Table(fin_data, colWidths=[2.0*inch, 5.0*inch])
        fin_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), AZUL_LIGHT),
            ("FONTNAME",   (0, 0), (0, -1), "Helvetica-Bold"),
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
            ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("ALIGN",      (1, 0), (1, -1), "RIGHT"),
        ]))
        story.append(fin_table)
        story.append(Spacer(1, 10))

    # ── Footer ──
    usuario_nombre = "Usuario"
    if hasattr(st, "session_state") and "usuario" in st.session_state:
        usuario_data   = st.session_state.get("usuario", {})
        usuario_nombre = usuario_data.get("Nombre", "Usuario")
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        f"Reporte generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} por {usuario_nombre} — Picus",
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

    rc1, rc2 = st.columns([1, 4])
    with rc1:
        if st.button("🔄 Recargar rutas", key="pic_sim_reload"):
            load_rutas_picus.clear()
            st.rerun()
    with rc2:
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
            log_accion("simular_ruta", {"id_ruta": ruta_1.get("ID_Ruta", "")})
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

        # ── Secuencia visual de la vuelta redonda ───────────────────
        # NOTA: verificar firma real de ruta_visual_nodos() en components.py.
        divider()
        section_header("🗺️", "Secuencia de la Vuelta Redonda")
        pasos = [
            {
                "nombre":    r.get("Tipo", ""),
                "subtitulo": f"{r.get('Origen','')} → {r.get('Destino','')}",
            }
            for r in rutas
        ]
        ruta_visual_nodos(pasos)

        # Utilidades globales — centralizado con mostrar_resultados_picus()
        divider()
        valores_gen = cargar_datos_generales()
        tc_usd      = safe_number(valores_gen.get("Tipo de cambio USD", 17.5))
        mostrar_resultados_picus(res, tc_usd=tc_usd)

        # Detalle de rutas por columnas — extraído a _detalle_tramos()
        divider()
        _detalle_tramos(rutas)

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
                    log_accion("generar_pdf", {"id_ruta": primer_ruta.get("ID_Ruta", "SinID")})
                    with open(pdf_path, "rb") as f:
                        pdf_bytes = f.read()
                    descargado = st.download_button(
                        "📥 Descargar PDF",
                        data=pdf_bytes,
                        file_name=nombre_pdf,
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True,
                        key="pic_sim_dl_pdf",
                    )
                    if descargado:
                        log_accion("descargar_archivo", {"id_ruta": primer_ruta.get("ID_Ruta", "SinID")})
                    alert("success", "✅ PDF generado exitosamente.")
                except Exception as e:
                    alert("error", f"❌ Error generando PDF: {e}")
