from ui.components import section_header, alert, divider
"""
simulador.py  –  Set Freight LLC
Simulador de variaciones de precio sobre una ruta existente.
Permite ver qué pasa con la utilidad si cambian los conceptos.
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
    st.title("🔁 Simulador de Variación — Set Freight LLC")
    st.caption("Selecciona una ruta base y ajusta los valores para ver el impacto en la utilidad sin guardar.")

    sb = get_supabase_client()
    if sb is None:
        alert("warn", "⚠️ Supabase no configurado.")
        return

    df = _cargar(TABLE_RUTAS)
    if df.empty:
        alert("info", "ℹ️ No hay rutas. Captura primero.")
        return

    df["_label"] = (df.get("id_ruta","").fillna("") + " · " +
                    df.get("ruta_origen","").fillna("") + " — " +
                    df.get("ruta_destino","").fillna(""))

    sel = st.selectbox("Ruta base", df["_label"].tolist(), key="sf_sim_sel")
    if not sel:
        return

    row_base = df[df["_label"] == sel].iloc[0].to_dict()
    pct_base = safe(row_base.get("pct_indirecto"), 0.10)
    r_base   = calcular_ruta(row_base, pct_indirecto=pct_base)

    divider()
section_header("▸", "Ajusta los valores (simulación — no se guarda)")

    col_ing, col_cst = st.columns(2)

    with col_ing:
        st.markdown("**Ingresos (USD)**")
        ing_sim = {}
        for label, campo in CONCEPTOS_INGRESO.items():
            ing_sim[campo] = st.number_input(
                label, value=safe(row_base.get(campo)),
                step=0.01, format="%.2f", key=f"sf_sim_ing_{campo}"
            )

    with col_cst:
        st.markdown("**Costos (USD)**")
        cst_sim = {}
        for label, campo in CONCEPTOS_COSTO.items():
            cst_sim[campo] = st.number_input(
                label, value=safe(row_base.get(campo)),
                step=0.01, format="%.2f", key=f"sf_sim_cst_{campo}"
            )

    pct_sim = st.slider("% Costo indirecto", 0.0, 0.30, pct_base, step=0.005,
                         format="%.1%%", key="sf_sim_pct")

    # Calcular simulado
    row_sim = {**row_base, **ing_sim, **cst_sim}
    r_sim   = calcular_ruta(row_sim, pct_indirecto=pct_sim)

    divider()
section_header("📊", "Comparativa base vs simulado")

    metricas = [
        ("Ingreso total",   "ingreso_total"),
        ("Costo directo",   "costo_directo"),
        ("Costo indirecto", "costo_indirecto"),
        ("Utilidad neta",   "ut_neta"),
        ("% Ut. neta",      "pct_ut_neta"),
    ]

    cols = st.columns(len(metricas))
    for i, (label, key) in enumerate(metricas):
        base_v = r_base[key]
        sim_v  = r_sim[key]
        delta  = sim_v - base_v

        if "pct" in key:
            cols[i].metric(label,
                           f"{sim_v:.2%}",
                           delta=f"{delta:+.2%}",
                           delta_color="normal" if delta >= 0 else "inverse")
        else:
            cols[i].metric(label,
                           f"${sim_v:,.2f}",
                           delta=f"${delta:+,.2f}",
                           delta_color="normal" if delta >= 0 else "inverse")
