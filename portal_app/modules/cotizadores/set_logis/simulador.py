from ui.components import section_header, alert, divider
"""
simulador.py  –  Set Logis Plus
Simulador de Vuelta Redonda: combina una SUBIDA + una BAJADA
y calcula rentabilidad combinada con tasas ajustables.
"""

import pandas as pd
import streamlit as st

from services.supabase_client import get_supabase_client
from ._shared import (
    TABLE_RUTAS,
    cargar_datos_generales,
    calcular_ruta_setlogis,
    safe,
)

TIPOS_SUBIDA = ["NB", "D2DNB"]
TIPOS_BAJADA = ["SB", "D2DSB"]


@st.cache_data(show_spinner=False, ttl=120)
def _cargar_rutas(table: str) -> pd.DataFrame:
    supabase = get_supabase_client()
    if supabase is None:
        return pd.DataFrame()
    try:
        resp = supabase.table(table).select("*").execute()
    except Exception:
        return pd.DataFrame()
    df = pd.DataFrame(resp.data)
    if df.empty:
        return df
    for col in ["Ingreso_Global", "Total_Costos_Directos", "Ut_Bruta", "Utilidad_Neta"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    if "Tipo_Viaje" in df.columns:
        df["Utilidad_%"] = (df["Ut_Bruta"] / df["Ingreso_Global"].replace(0, pd.NA) * 100).fillna(0).round(2)
    return df


def _calc_row(ruta, valores: dict) -> dict:
    calcular_ruta_setlogis(
        tipo_viaje=str(ruta.get("Tipo_Viaje", "NB")),
        miles_load=safe(ruta.get("Miles_Load")),
        miles_empty=safe(ruta.get("Miles_Empty")),
        short_miles=safe(ruta.get("Short_Miles")),
        flete_mex=safe(ruta.get("Flete_MEX")),
        flete_usa=safe(ruta.get("Flete_USA")),
        fuel=safe(ruta.get("Fuel")),
        cruce=safe(ruta.get("Cruce")),
        valores=valores,
    )
    r.update({"miles_load": safe(ruta.get("Miles_Load")),
               "miles_empty": safe(ruta.get("Miles_Empty")),
               "short_miles": safe(ruta.get("Short_Miles"))})
    return r


def _tarjeta(label: str, ruta, r: dict):
    with st.container(border=True):
        st.markdown(f"**{label}**")
        st.caption(f"{ruta.get('ID_Ruta','')} · {ruta.get('Tipo_Viaje','')} · {ruta.get('Cliente','')} · {ruta.get('Ruta_USA','')}")
        c1, c2 = st.columns(2)
        c1.metric("Ingreso", f"${r['ingreso_global']:,.2f}")
        c1.metric("Costo D.", f"${r['total_cd']:,.2f}")
        db = "normal" if r["ut_bruta"] >= 0 else "inverse"
        c2.metric("Ut. Bruta", f"${r['ut_bruta']:,.2f} ({r['pct_ut_bruta']:.1%})", delta_color=db)
        dn = "normal" if r["ut_neta"] >= 0 else "inverse"
        c2.metric("Ut. Neta",  f"${r['ut_neta']:,.2f} ({r['pct_ut_neta']:.1%})", delta_color=dn)


def render():
    st.title("🔁 Simulador Vuelta Redonda – Set Logis Plus")

    supabase = get_supabase_client()
    if supabase is None:
        alert("warn", "⚠️ Supabase no configurado.")
        return

    cr, _ = st.columns([1, 4])
    with cr:
        if st.button("🔄 Recargar", key="sl_sim_reload"):
            _cargar_rutas.clear()
            st.rerun()

    df = _cargar_rutas(TABLE_RUTAS)
    if df.empty:
        alert("warn", "⚠️ No hay rutas guardadas en Supabase.")
        alert("info", "💡 Captura rutas primero para poder simular una Vuelta Redonda.")
        return

    valores = cargar_datos_generales()

    # ── Ajuste de parámetros ──
    with st.expander("⚙️ Ajustar Parámetros de Simulación", expanded=False):
        p1, p2, p3, p4 = st.columns(4)
        tc_s = p1.number_input("Tasa Cargado Subida",  value=float(valores.get("Tasa Owner Cargado Subida ($/mi)", 1.60)), step=0.01, key="sl_sim_tcs")
        tc_b = p2.number_input("Tasa Cargado Bajada",  value=float(valores.get("Tasa Owner Cargado Bajada ($/mi)", 1.40)), step=0.01, key="sl_sim_tcb")
        tv   = p3.number_input("Tasa Vacío",           value=float(valores.get("Tasa Owner Vacío ($/mi)", 0.80)),           step=0.01, key="sl_sim_tv")
        cxm  = p4.number_input("CXM Indirecto",        value=float(valores.get("CXM Indirecto ($/mi)", 0.1001)),            step=0.0001, format="%.4f", key="sl_sim_cxm")

    val_sim = dict(valores)
    val_sim["Tasa Owner Cargado Subida ($/mi)"] = tc_s
    val_sim["Tasa Owner Cargado Bajada ($/mi)"] = tc_b
    val_sim["Tasa Owner Vacío ($/mi)"]           = tv
    val_sim["CXM Indirecto ($/mi)"]              = cxm

    # ── SUBIDA ──
    section_header("⬆️", "Tramo Subida (hacia USA)")
    df_sub = df[df["Tipo_Viaje"].isin(TIPOS_SUBIDA)].copy() if "Tipo_Viaje" in df.columns else pd.DataFrame()
    if df_sub.empty:
        alert("warn", "No hay rutas de SUBIDA guardadas.")
    else:
        clientes_s = sorted(df_sub["Cliente"].dropna().unique().tolist())
        cli_s = st.selectbox("Cliente Subida", ["Todos"] + clientes_s, key="sl_sim_cli_s")
        df_sub_f = df_sub if cli_s == "Todos" else df_sub[df_sub["Cliente"] == cli_s]
        idx_s = st.selectbox("Ruta Subida:", df_sub_f.index.tolist(),
                             format_func=lambda i: f"{df_sub_f.loc[i,'ID_Ruta']} | {df_sub_f.loc[i,'Tipo_Viaje']} | {df_sub_f.loc[i,'Ruta_USA']} | {df_sub_f.loc[i,'Utilidad_%']:.1f}%",
                             key="sl_sim_ruta_s")
        ruta_s = df_sub_f.loc[idx_s]
        r_s = _calc_row(ruta_s, val_sim)
        _tarjeta("Tramo Subida", ruta_s, r_s)

    # ── BAJADA ──
    section_header("⬇️", "Tramo Bajada (hacia México)")
    df_baj = df[df["Tipo_Viaje"].isin(TIPOS_BAJADA)].copy() if "Tipo_Viaje" in df.columns else pd.DataFrame()
    if df_baj.empty:
        alert("warn", "No hay rutas de BAJADA guardadas.")
    else:
        clientes_b = sorted(df_baj["Cliente"].dropna().unique().tolist())
        cli_b = st.selectbox("Cliente Bajada", ["Todos"] + clientes_b, key="sl_sim_cli_b")
        df_baj_f = df_baj if cli_b == "Todos" else df_baj[df_baj["Cliente"] == cli_b]
        idx_b = st.selectbox("Ruta Bajada:", df_baj_f.index.tolist(),
                             format_func=lambda i: f"{df_baj_f.loc[i,'ID_Ruta']} | {df_baj_f.loc[i,'Tipo_Viaje']} | {df_baj_f.loc[i,'Ruta_USA']} | {df_baj_f.loc[i,'Utilidad_%']:.1f}%",
                             key="sl_sim_ruta_b")
        ruta_b = df_baj_f.loc[idx_b]
        r_b = _calc_row(ruta_b, val_sim)
        _tarjeta("Tramo Bajada", ruta_b, r_b)

    # ── Resultado combinado ──
    if not df_sub.empty and not df_baj.empty:
        divider()
        section_header("🏁", "Vuelta Redonda Combinada")

        ing_vr  = r_s["ingreso_global"] + r_b["ingreso_global"]
        cd_vr   = r_s["total_cd"]       + r_b["total_cd"]
        ci_vr   = r_s["costo_ind"]      + r_b["costo_ind"]
        ub_vr   = r_s["ut_bruta"]       + r_b["ut_bruta"]
        un_vr   = r_s["ut_neta"]        + r_b["ut_neta"]
        pct_ub  = ub_vr / ing_vr * 100 if ing_vr else 0
        pct_un  = un_vr / ing_vr * 100 if ing_vr else 0
        mi_vr   = r_s["miles_load"] + r_b["miles_load"]

        cc1, cc2, cc3, cc4 = st.columns(4)
        cc1.metric("Ingreso VR",    f"${ing_vr:,.2f}")
        cc1.metric("Costo Dir. VR", f"${cd_vr:,.2f}")
        db = "normal" if ub_vr >= 0 else "inverse"
        cc2.metric("Ut. Bruta VR",  f"${ub_vr:,.2f}", delta_color=db)
        cc2.metric("% Ut. Bruta",   f"{pct_ub:.2f}%")
        cc3.metric("CI VR",         f"${ci_vr:,.2f}")
        dn = "normal" if un_vr >= 0 else "inverse"
        cc3.metric("Ut. Neta VR",   f"${un_vr:,.2f}", delta_color=dn)
        cc4.metric("% Ut. Neta",    f"{pct_un:.2f}%")
        if mi_vr > 0:
            cc4.metric("Ingreso/Milla", f"${ing_vr/mi_vr:,.3f}")
