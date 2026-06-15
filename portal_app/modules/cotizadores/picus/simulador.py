"""
simulador.py — Cotizador Picus
Simulador de Vuelta Redonda — diseño homologado con Igloo:
  - Sin st.title()
  - Botón recargar en col [1,4]
  - Filtros en expander para ruta principal y regreso
  - Selector con label completo (ID | Fecha | Tipo | Cliente | Origen → Destino)
  - Expander de detalle de ruta seleccionada
  - Sugerencias ordenadas por % utilidad combinada
  - Resultados con mostrar_resultados_utilidad() → kpi_row + semaforos_ruta
  - Detalle de cada tramo en expanders con st.caption()
  - PDF con reportlab (mismo estilo que Igloo)
"""
from __future__ import annotations

import tempfile
from datetime import datetime

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from services.supabase_client import get_supabase_client
from ui.components import section_header, alert, divider

from .helpers import (
    safe_number,
    calcular_costos_indirectos,
    calcular_utilidades_vuelta_redonda,
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
# Filtros y label (igual que Igloo)
# ─────────────────────────────────────────────

def _filtrar_rutas(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    with st.expander("🔎 Filtros de búsqueda (opcional)", expanded=False):
        fc1, fc2, fc3, fc4 = st.columns(4)
        tipos_disp    = ["Todos"] + sorted(df["Tipo"].dropna().unique().tolist())    if "Tipo"    in df.columns else ["Todos"]
        clientes_disp = ["Todos"] + sorted(df["Cliente"].dropna().astype(str).unique().tolist()) if "Cliente" in df.columns else ["Todos"]
        f_tipo    = fc1.selectbox("Tipo",              tipos_disp,    key=f"{prefix}_ftipo")
        f_cliente = fc2.selectbox("Cliente",           clientes_disp, key=f"{prefix}_fcli")
        f_origen  = fc3.text_input("Origen contiene",                 key=f"{prefix}_fori")
        f_destino = fc4.text_input("Destino contiene",                key=f"{prefix}_fdest")

    r = df.copy()
    if f_tipo    != "Todos": r = r[r["Tipo"].astype(str) == f_tipo]
    if f_cliente != "Todos": r = r[r["Cliente"].astype(str) == f_cliente]
    if f_origen.strip():  r = r[r["Origen"].astype(str).str.upper().str.contains(f_origen.upper(),  na=False)]
    if f_destino.strip(): r = r[r["Destino"].astype(str).str.upper().str.contains(f_destino.upper(), na=False)]
    return r


def _label(row) -> str:
    return (
        f"{row.get('ID_Ruta','')} | {str(row.get('Fecha',''))[:10]} | "
        f"{row.get('Tipo','')} | {row.get('Cliente','')} | "
        f"{row.get('Origen','')} → {row.get('Destino','')}"
    )


# ─────────────────────────────────────────────
# Sugerencias de regreso
# ─────────────────────────────────────────────

def _sugerir_regresos(ruta_1: dict, df: pd.DataFrame) -> list[dict]:
    """
    Genera combinaciones de regreso ordenadas por % utilidad combinada.
    Picus: IMPORTACION ↔ EXPORTACION, VACIO como puente.
    """
    tipo_principal = str(ruta_1.get("Tipo", "")).strip().upper()
    destino_1      = str(ruta_1.get("Destino", "")).strip().upper()

    if tipo_principal == "IMPORTACION":
        tipo_regreso = "EXPORTACION"
    elif tipo_principal == "EXPORTACION":
        tipo_regreso = "IMPORTACION"
    else:
        tipo_regreso = None  # VACIO principal → busca IMPORT/EXPORT

    sugerencias = []

    # 1) Regreso directo (sin vacío)
    if tipo_regreso:
        directas = df[(df["Tipo"] == tipo_regreso) & (df["Origen"] == destino_1)]
        for _, row in directas.iterrows():
            tramos = [ruta_1, row.to_dict()]
            util   = calcular_utilidades_vuelta_redonda(tramos)
            sugerencias.append({
                "descripcion": (
                    f"{row.get('Fecha','')} — {row.get('Cliente','')} | "
                    f"{row.get('Origen','')} → {row.get('Destino','')} "
                    f"({util['porcentaje_bruta']:.1f}% Ut.Bruta)"
                ),
                "tramos":    [row.to_dict()],
                "ingreso":   util["ingreso_total"],
                "costo":     util["costo_total"],
                "pct_bruta": util["porcentaje_bruta"],
                "pct_neta":  util["porcentaje_neta"],
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
                sugerencias.append({
                    "descripcion": (
                        f"{final.get('Fecha','')} — {final.get('Cliente','')} "
                        f"(Vacío {vacio.get('Origen','')}→{vacio.get('Destino','')}) "
                        f"→ {final.get('Destino','')} "
                        f"({util['porcentaje_bruta']:.1f}% Ut.Bruta)"
                    ),
                    "tramos":    [vacio.to_dict(), final.to_dict()],
                    "ingreso":   util["ingreso_total"],
                    "costo":     util["costo_total"],
                    "pct_bruta": util["porcentaje_bruta"],
                    "pct_neta":  util["porcentaje_neta"],
                })

    # 3) Si principal es VACIO: busca IMPORT/EXPORT desde su destino
    if tipo_principal == "VACIO":
        candidatos = df[
            (df["Tipo"].isin(["IMPORTACION", "EXPORTACION"])) &
            (df["Origen"] == destino_1)
        ]
        for _, final in candidatos.iterrows():
            tramos = [ruta_1, final.to_dict()]
            util   = calcular_utilidades_vuelta_redonda(tramos)
            sugerencias.append({
                "descripcion": (
                    f"{final.get('Fecha','')} — {final.get('Cliente','')} "
                    f"{final.get('Origen','')} → {final.get('Destino','')} "
                    f"({util['porcentaje_bruta']:.1f}% Ut.Bruta)"
                ),
                "tramos":    [final.to_dict()],
                "ingreso":   util["ingreso_total"],
                "costo":     util["costo_total"],
                "pct_bruta": util["porcentaje_bruta"],
                "pct_neta":  util["porcentaje_neta"],
            })

    return sorted(sugerencias, key=lambda x: (x["pct_bruta"], x["pct_neta"]), reverse=True)


# ─────────────────────────────────────────────
# PDF Vuelta Redonda (reportlab, estilo Igloo)
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

    styles   = getSampleStyleSheet()
    AZUL     = colors.HexColor("#1B2266")
    title_s  = ParagraphStyle("T", parent=styles["Normal"], fontSize=14,
                               fontName="Helvetica-Bold", textColor=AZUL, spaceAfter=4)
    sub_s    = ParagraphStyle("S", parent=styles["Normal"], fontSize=10,
                               fontName="Helvetica-Bold", textColor=AZUL,
                               spaceBefore=10, spaceAfter=3)
    footer_s = ParagraphStyle("F", parent=styles["Normal"], fontSize=7,
                               textColor=colors.HexColor("#6c757d"), alignment=TA_CENTER)

    def tabla(data, col_w):
        t = Table(data, colWidths=col_w)
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),  AZUL),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, -1), 7),
            ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
            ("ALIGN",         (1, 1), (-1, -1), "RIGHT"),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ]))
        return t

    story = []

    # ── Encabezado ────────────────────────────────────────────────
    story.append(Paragraph(_safe_txt("Picus — Simulacion Vuelta Redonda"), title_s))
    story.append(HRFlowable(width="100%", thickness=1, color=AZUL))
    story.append(Spacer(1, 8))

    # ── Resumen de Utilidades ────────────────────────────────────
    story.append(Paragraph(_safe_txt("Resumen General"), sub_s))
    color_un  = colors.HexColor("#28a745") if utilidad_neta >= 0 else colors.HexColor("#dc3545")
    pct_costo = (costo_total / ingreso_total * 100) if ingreso_total else 0
    pct_ind   = (costos_indirectos / ingreso_total * 100) if ingreso_total else 0

    res_data = [
        ["Concepto",          "Valor",                          "%"],
        ["Ingreso Total",     f"${ingreso_total:,.2f} MXP",     "100.00%"],
        ["Costo Directo",     f"${costo_total:,.2f} MXP",       f"{pct_costo:.2f}%"],
        ["Utilidad Bruta",    f"${utilidad_bruta:,.2f} MXP",    f"{pct_bruta:.2f}%"],
        ["Costos Indirectos", f"${costos_indirectos:,.2f} MXP", f"{pct_ind:.2f}%"],
        ["Utilidad Neta",     f"${utilidad_neta:,.2f} MXP",     f"{pct_neta:.2f}%"],
    ]
    res_t = Table(res_data, colWidths=[2.5*inch, 2.5*inch, 2.0*inch])
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
    story.append(Spacer(1, 10))

    # ── Detalle de cada tramo ────────────────────────────────────
    story.append(Paragraph(_safe_txt("Detalle de Rutas"), sub_s))

    for i, r in enumerate(rutas_seleccionadas, 1):
        tipo_tramo  = str(r.get("Tipo", "")).strip().upper()
        ing_tramo   = safe_number(r.get("Ingreso Total", 0))
        costo_tramo = safe_number(r.get("Costo_Total_Ruta", 0))
        ind_tramo   = calcular_costos_indirectos(tipo_tramo, ing_tramo)
        ut_tramo    = ing_tramo - costo_tramo

        story.append(Paragraph(
            _safe_txt(f"Tramo {i}: {r.get('Tipo','')} — {r.get('Cliente','')}"),
            ParagraphStyle("TH", parent=styles["Normal"], fontSize=8,
                           fontName="Helvetica-Bold", textColor=AZUL,
                           spaceBefore=6, spaceAfter=2),
        ))
        tramo_data = [
            ["Campo", "Valor", "Campo", "Valor"],
            [_safe_txt("ID Ruta"),  _safe_txt(str(r.get("ID_Ruta",""))),
             _safe_txt("Fecha"),    _safe_txt(str(r.get("Fecha",""))[:10])],
            [_safe_txt("Origen"),   _safe_txt(str(r.get("Origen",""))),
             _safe_txt("Destino"),  _safe_txt(str(r.get("Destino","")))],
            [_safe_txt("Ingreso"),  _safe_txt(f"${ing_tramo:,.2f}"),
             _safe_txt("Costo"),    _safe_txt(f"${costo_tramo:,.2f}")],
            [_safe_txt("Ut. Bruta"), _safe_txt(f"${ut_tramo:,.2f}"),
             _safe_txt("Costos Ind."), _safe_txt(f"${ind_tramo:,.2f}" if ind_tramo > 0 else "$0.00 (VACIO)")],
        ]
        tramo_t = Table(tramo_data, colWidths=[1.2*inch, 2.1*inch, 1.2*inch, 2.1*inch])
        tramo_t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0),  colors.HexColor("#e8f4f8")),
            ("FONTNAME",   (0, 0), (0, -1),  "Helvetica-Bold"),
            ("FONTNAME",   (2, 0), (2, -1),  "Helvetica-Bold"),
            ("FONTSIZE",   (0, 0), (-1, -1), 7),
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
            ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("ALIGN",      (1, 0), (1, -1),  "RIGHT"),
            ("ALIGN",      (3, 0), (3, -1),  "RIGHT"),
        ]))
        story.append(tramo_t)
        story.append(Spacer(1, 4))

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

    # ── Recargar ─────────────────────────────────────────────────────
    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("🔄 Recargar", key="pic_sim_reload"):
            _load_rutas_picus_cached.clear()
            st.rerun()
    with c2:
        st.caption("Carga cacheada 2 min. Usa 'Recargar' si acabas de guardar algo.")

    df = _load_rutas_picus_cached()
    if df.empty:
        alert("warn", "⚠️ No hay rutas registradas en Supabase.")
        return

    for col in ["Origen", "Destino", "Cliente", "Tipo"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.upper()

    if "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d")

    # ── Paso 1: Ruta Principal ────────────────────────────────────────
    divider()
    section_header("📌", "Paso 1 — Ruta Principal")
    st.caption("Filtra y selecciona la ruta de ida.")

    df_principal = _filtrar_rutas(df, "pic_sim_p1")

    if df_principal.empty:
        alert("warn", "No hay rutas que cumplan los filtros.")
        return

    opciones_p1 = [_label(row) for _, row in df_principal.iterrows()]
    sel_p1      = st.selectbox(
        f"Selecciona la ruta principal ({len(df_principal)} disponibles)",
        opciones_p1,
        key="pic_sim_sel_p1",
    )
    idx_p1      = opciones_p1.index(sel_p1)
    ruta_p1_row = df_principal.iloc[idx_p1]
    ruta_1      = ruta_p1_row.to_dict()

    with st.expander("📋 Ver detalles de la ruta seleccionada", expanded=False):
        d1, d2 = st.columns(2)
        with d1:
            st.caption(f"**ID Ruta:** {ruta_1.get('ID_Ruta','')}")
            st.caption(f"**Tipo:** {ruta_1.get('Tipo','')}")
            st.caption(f"**Cliente:** {ruta_1.get('Cliente','')}")
            st.caption(f"**Fecha:** {ruta_1.get('Fecha','')}")
        with d2:
            st.caption(f"**Origen:** {ruta_1.get('Origen','')}")
            st.caption(f"**Destino:** {ruta_1.get('Destino','')}")
            st.caption(f"**Ingreso Total:** ${safe_number(ruta_1.get('Ingreso Total',0)):,.2f}")
            st.caption(f"**Costo Directo:** ${safe_number(ruta_1.get('Costo_Total_Ruta',0)):,.2f}")

    # ── Paso 2: Sugerencias de regreso ───────────────────────────────
    divider()
    section_header("🔄", "Paso 2 — Selecciona el Regreso")
    st.caption("Combinaciones sugeridas ordenadas por % utilidad combinada.")

    sugerencias = _sugerir_regresos(ruta_1, df)

    if not sugerencias:
        alert("warn", "⚠️ No hay rutas de regreso disponibles desde el destino de la ruta principal.")
        return

    opciones_reg = {s["descripcion"]: s for s in sugerencias}
    sel_reg      = st.selectbox(
        f"Opciones de regreso ({len(sugerencias)} combinaciones)",
        list(opciones_reg.keys()),
        key="pic_sim_sel_reg",
    )
    seleccion          = opciones_reg[sel_reg]
    rutas_seleccionadas = [ruta_1] + seleccion["tramos"]

    # ── Botón Simular ─────────────────────────────────────────────────
    divider()
    if st.button("🚛 Simular Vuelta Redonda", key="pic_sim_run", type="primary", use_container_width=True):
        st.session_state["pic_sim_realizada"]        = True
        st.session_state["pic_sim_rutas"]            = rutas_seleccionadas
        st.session_state["pic_sim_resultado"]        = calcular_utilidades_vuelta_redonda(rutas_seleccionadas)

    # ── Resultados ────────────────────────────────────────────────────
    if st.session_state.get("pic_sim_realizada") and st.session_state.get("pic_sim_resultado"):
        util   = st.session_state["pic_sim_resultado"]
        rutas  = st.session_state.get("pic_sim_rutas", rutas_seleccionadas)

        divider()
        section_header("📊", "Resultado de la Vuelta Redonda")

        mostrar_resultados_utilidad(
            st,
            util["ingreso_total"],
            util["costo_total"],
            util["utilidad_bruta"],
            util["costos_indirectos"],
            util["utilidad_neta"],
            util["porcentaje_bruta"],
            util["porcentaje_neta"],
            tipo="IMPORTACION",   # indirectos ya calculados por tramo en calcular_utilidades_vuelta_redonda
        )

        # ── Detalle por tramo ─────────────────────────────────────────
        divider()
        section_header("🛣️", "Detalle por Tramo")

        for i, r in enumerate(rutas, 1):
            tipo_tramo  = str(r.get("Tipo", "")).strip().upper()
            ing_tramo   = safe_number(r.get("Ingreso Total", 0))
            costo_tramo = safe_number(r.get("Costo_Total_Ruta", 0))
            ind_tramo   = calcular_costos_indirectos(tipo_tramo, ing_tramo)
            ut_bruta    = ing_tramo - costo_tramo
            ut_neta     = ut_bruta - ind_tramo

            with st.expander(
                f"Tramo {i}: {r.get('Tipo','')} — {r.get('Cliente','')} | "
                f"{r.get('Origen','')} → {r.get('Destino','')}",
                expanded=(i == 1),
            ):
                tc1, tc2 = st.columns(2)
                with tc1:
                    st.caption(f"**ID Ruta:** {r.get('ID_Ruta','')}")
                    st.caption(f"**Fecha:** {r.get('Fecha','')}")
                    st.caption(f"**Tipo:** {r.get('Tipo','')}")
                    st.caption(f"**Cliente:** {r.get('Cliente','')}")
                    st.caption(f"**Origen → Destino:** {r.get('Origen','')} → {r.get('Destino','')}")
                    st.caption(f"**KM:** {safe_number(r.get('KM',0)):,.0f}")
                with tc2:
                    st.caption(f"**Ingreso Total:** ${ing_tramo:,.2f}")
                    st.caption(f"**Costo Directo:** ${costo_tramo:,.2f}")
                    st.caption(f"**Ut. Bruta tramo:** ${ut_bruta:,.2f}")
                    if ind_tramo > 0:
                        st.caption(f"**Costos Ind. (35%):** ${ind_tramo:,.2f}")
                    else:
                        st.caption("**Costos Ind.:** $0.00 (VACÍO)")
                    st.caption(f"**Ut. Neta tramo:** ${ut_neta:,.2f}")
                    st.caption(f"**Moneda:** {r.get('Moneda','MXP')}")

        # ── PDF ───────────────────────────────────────────────────────
        divider()
        section_header("📥", "Descargar Reporte")
        b1, b2, b3 = st.columns([1, 2, 1])
        with b2:
            if st.button("📄 Generar PDF", key="pic_sim_pdf", use_container_width=True):
                try:
                    pdf_path = generar_pdf_vuelta_redonda(
                        rutas,
                        util["ingreso_total"], util["costo_total"],
                        util["utilidad_bruta"], util["costos_indirectos"],
                        util["utilidad_neta"], util["porcentaje_bruta"], util["porcentaje_neta"],
                    )
                    primer_ruta = rutas[0]
                    nombre_pdf  = f"VR_Picus_{primer_ruta.get('ID_Ruta','SinID')}.pdf"
                    with open(pdf_path, "rb") as f:
                        st.download_button(
                            "📥 Descargar PDF",
                            data=f.read(),
                            file_name=nombre_pdf,
                            mime="application/pdf",
                            type="primary",
                            use_container_width=True,
                            key="pic_sim_dl_pdf",
                        )
                    alert("success", "✅ PDF generado exitosamente.")
                except Exception as e:
                    alert("error", f"❌ Error generando PDF: {e}")
