"""
consulta_ruta.py — Cotizador Picus
Diseño homologado con Igloo:
  - Sin st.title()
  - Botón recargar en col [1,4]
  - Filtros con expander
  - Selector por label completo (ID | Fecha | Tipo | Cliente | Origen → Destino)
  - Simulación con helpers.py (calcular_diesel + calcular_utilidades)
  - Resultados con mostrar_resultados_utilidad → kpi_row + semaforos_ruta
  - Desglose con st.caption() separado en secciones
  - PDF sin cambios de lógica
"""
from __future__ import annotations

import tempfile
from datetime import datetime

import pandas as pd
import streamlit as st
from fpdf import FPDF

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
        tipos    = ["Todos"] + sorted(df["Tipo"].dropna().unique().tolist())    if "Tipo"    in df.columns else ["Todos"]
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
# PDF helper
# ─────────────────────────────────────────────

def safe_text(text: str) -> str:
    try:
        return str(text).encode("latin-1", "replace").decode("latin-1")
    except Exception:
        return str(text)


def _generar_pdf(ruta, ingreso_total, costo_total, utilidad_bruta,
                 costos_indirectos, utilidad_neta, pct_bruta, pct_neta,
                 es_simulacion: bool = False) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, safe_text("Consulta Individual de Ruta — Picus"), ln=True)
    if es_simulacion:
        pdf.set_font("Arial", "I", 10)
        pdf.cell(0, 8, safe_text("(SIMULACIÓN — valores de diesel/rendimiento ajustados)"), ln=True)
    pdf.ln(3)

    pdf.set_font("Arial", "", 11)
    campos = [
        ("ID de Ruta",        ruta.get("ID_Ruta", "")),
        ("Fecha",             str(ruta.get("Fecha", ""))[:10]),
        ("Tipo",              ruta.get("Tipo", "")),
        ("Ruta Tipo",         ruta.get("Ruta_Tipo", "")),
        ("Modo de Viaje",     ruta.get("Modo de Viaje", "")),
        ("Cliente",           ruta.get("Cliente", "")),
        ("Origen → Destino",  f"{ruta.get('Origen','')} → {ruta.get('Destino','')}"),
        ("KM",                f"{safe_number(ruta.get('KM')):,.0f}"),
    ]
    for label, val in campos:
        pdf.cell(0, 8, safe_text(f"{label}: {val}"), ln=True)

    pdf.ln(4)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, safe_text("Resultados de Utilidad:"), ln=True)
    pdf.set_font("Arial", "", 11)
    resultados = [
        ("Ingreso Total",       f"${ingreso_total:,.2f}"),
        ("Costo Total",         f"${costo_total:,.2f}"),
        ("Utilidad Bruta",      f"${utilidad_bruta:,.2f}  ({pct_bruta:.1f}%)"),
        ("Costos Indirectos",   f"${costos_indirectos:,.2f}"),
        ("Utilidad Neta",       f"${utilidad_neta:,.2f}  ({pct_neta:.1f}%)"),
    ]
    for label, val in resultados:
        pdf.cell(0, 8, safe_text(f"{label}: {val}"), ln=True)

    pdf.ln(4)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, safe_text("Desglose de Costos:"), ln=True)
    pdf.set_font("Arial", "", 10)
    costos = [
        ("Diesel Camión",    safe_number(ruta.get("Costo_Diesel_Camion"))),
        ("Sueldo Operador",  safe_number(ruta.get("Sueldo_Operador"))),
        ("Bono ISR/IMSS",    safe_number(ruta.get("Bono"))),
        ("Casetas",          safe_number(ruta.get("Casetas"))),
        ("Costo Cruce",      safe_number(ruta.get("Costo Cruce Convertido"))),
        ("Mov. Local",       safe_number(ruta.get("Movimiento_Local"))),
        ("Puntualidad",      safe_number(ruta.get("Puntualidad"))),
        ("Pensión",          safe_number(ruta.get("Pension"))),
        ("Estancia",         safe_number(ruta.get("Estancia"))),
        ("Fianza",           safe_number(ruta.get("Fianza"))),
        ("Extras",           safe_number(ruta.get("Costo_Extras"))),
    ]
    for label, val in costos:
        if val:
            pdf.cell(0, 7, safe_text(f"  {label}: ${val:,.2f}"), ln=True)

    pdf.ln(4)
    pdf.set_font("Arial", "I", 9)
    pdf.cell(0, 8, safe_text(
        f"Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} — Cotizador Picus"
    ), ln=True)

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        pdf.output(tmp.name)
        tmp.seek(0)
        return open(tmp.name, "rb").read()


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

    idx      = opciones.index(sel)
    ruta     = df_filtrado.iloc[idx]
    tipo_ruta = str(ruta.get("Tipo", "")).strip().upper()

    rend_reg = float(safe_number(
        ruta.get("Rendimiento Camion", valores.get("Rendimiento Camion", 2.5))
    ))

    # ── Ajustes para simulación ───────────────────────────────────────
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

    # ── Cálculo de resultados ─────────────────────────────────────────
    ingreso_total = safe_number(ruta.get("Ingreso Total", 0))
    km            = safe_number(ruta.get("KM", 0))

    if simular:
        valores_sim = {
            "Rendimiento Camion": rendimiento_input,
            "Costo Diesel":       costo_diesel_input,
        }
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
        ingreso_total,
        costo_total,
        util["utilidad_bruta"],
        util["costos_indirectos"],
        util["utilidad_neta"],
        util["porcentaje_bruta"],
        util["porcentaje_neta"],
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
            st.markdown("### 📉 Costos Directos")
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
            st.markdown("### 🧾 Extras")
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
                    icono = "✅" if cobrado else "—"
                    st.caption(f"**{label}:** ${val:,.2f} {icono}")
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
        try:
            pdf_bytes = _generar_pdf(
                ruta,
                ingreso_total, costo_total,
                util["utilidad_bruta"], util["costos_indirectos"],
                util["utilidad_neta"], util["porcentaje_bruta"], util["porcentaje_neta"],
                es_simulacion=simular,
            )
            nombre = f"ruta_{ruta.get('ID_Ruta','picus')}{'_sim' if simular else ''}.pdf"
            st.download_button(
                "⬇️ Descargar PDF",
                data=pdf_bytes,
                file_name=nombre,
                mime="application/pdf",
                key="pic_cons_dl_pdf",
            )
        except Exception as e:
            alert("error", f"❌ Error generando PDF: {e}")
