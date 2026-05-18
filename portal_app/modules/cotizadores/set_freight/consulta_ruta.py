from ui.components import section_header, alert, divider
"""
consulta_ruta.py  –  Set Freight LLC
Consulta individual de una ruta con desglose de ingresos y costos.
"""

import streamlit as st
import pandas as pd

from services.supabase_client import get_supabase_client
from ._shared import TABLE_RUTAS, CONCEPTOS_INGRESO, CONCEPTOS_COSTO, calcular_ruta, safe


@st.cache_data(show_spinner=False, ttl=120)
def _cargar(table: str) -> pd.DataFrame:
    sb = get_supabase_client()
    if sb is None:
        return pd.DataFrame()
    try:
        resp = sb.table(table).select("*").execute()
    except Exception:
        return pd.DataFrame()
    return pd.DataFrame(resp.data or [])


def render():
    st.title("🔍 Consulta de Ruta — Set Freight LLC")

    sb = get_supabase_client()
    if sb is None:
        alert("warn", "⚠️ Supabase no configurado.")
        return

    c_reload, _ = st.columns([1, 5])
    with c_reload:
        if st.button("🔄 Recargar", key="sf_cons_reload"):
            _cargar.clear()
            st.rerun()

    df = _cargar(TABLE_RUTAS)
    if df.empty:
        alert("info", "ℹ️ No hay rutas registradas todavía.")
        return

    # Selector de ruta
    df["_label"] = (df.get("id_ruta", "").fillna("") + " · " +
                    df.get("ruta_origen", "").fillna("") + " — " +
                    df.get("ruta_destino", "").fillna(""))
    sel = st.selectbox("Selecciona una ruta", df["_label"].tolist(), key="sf_cons_sel")
    if not sel:
        return

    row = df[df["_label"] == sel].iloc[0].to_dict()
    pct = safe(row.get("pct_indirecto"), 0.10)
    r   = calcular_ruta(row, pct_indirecto=pct)

    divider()
    section_header("📌", f"📌 {row.get('ruta_origen','')} — {row.get('ruta_destino','')}")
    st.caption(f"Tipo: {row.get('tipo_servicio','')}  ·  ID: {row.get('id_ruta','')}")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Ingreso total",   f"${r['ingreso_total']:,.2f}")
    m1.metric("Costo directo",   f"${r['costo_directo']:,.2f}")
    color_b = "normal" if r["ut_bruta"] >= 0 else "inverse"
    m2.metric("Utilidad bruta",  f"${r['ut_bruta']:,.2f}",  delta_color=color_b)
    m2.metric("% Ut. bruta",     f"{r['pct_ut_bruta']:.2%}")
    m3.metric("Costo indirecto", f"${r['costo_indirecto']:,.2f}")
    color_n = "normal" if r["ut_neta"] >= 0 else "inverse"
    m3.metric("Utilidad neta",   f"${r['ut_neta']:,.2f}",   delta_color=color_n)
    m4.metric("% Ut. neta",      f"{r['pct_ut_neta']:.2%}")
    m4.metric("% Costo directo", f"{r['pct_cd']:.2%}")

    with st.expander("🔎 Desglose completo"):
        ca, cb = st.columns(2)
        with ca:
            st.markdown("**INGRESOS (USD)**")
            for label, campo in CONCEPTOS_INGRESO.items():
                val = safe(row.get(campo))
                if val:
                    st.write(f"- {label}: ${val:,.2f}")
            st.markdown(f"**Total: ${r['ingreso_total']:,.2f}**")
        with cb:
            st.markdown("**COSTOS DIRECTOS (USD)**")
            for label, campo in CONCEPTOS_COSTO.items():
                val = safe(row.get(campo))
                if val:
                    st.write(f"- {label}: ${val:,.2f}")
            st.markdown(f"**Total CD: ${r['costo_directo']:,.2f}**")
            st.markdown(f"**Costo Indirecto ({pct:.1%}): ${r['costo_indirecto']:,.2f}**")

    if row.get("notas"):
        st.info(f"📝 {row['notas']}")
