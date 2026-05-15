# portal_app/modules/auditoria/prorrateador_resumen.py
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from services.supabase_client import get_authed_client as get_supabase_client
from .shared import to_excel_bytes_sheets, read_excel_cached


def _find_col(df, candidates):
    cols = list(df.columns)
    for c in candidates:
        if c in cols:
            return c
    for c in cols:
        for cand in candidates:
            if str(cand) in str(c):
                return c
    return None


def render():
    from ui.components import section_header, alert, divider
    section_header("📊", "Resúmenes")
    supabase = get_supabase_client()

    # --------
    # Tomar prorrateo completo desde memoria o subir
    # --------
    fuente = st.radio(
        "Fuente de datos",
        ["Usar prorrateo en memoria (recomendado)", "Subir prorrateo_completo.xlsx"],
        index=0,
        key="resumen_fuente",
    )

    prorr = None
    if fuente.startswith("Usar"):
        prorr = st.session_state.get("gg_prorrateo_completo")
        if prorr is None:
            alert("warn", "No hay prorrateo en memoria. Corre primero el tab 🧾 Prorrateo GG o sube el archivo.")
    else:
        up = st.file_uploader("Sube prorrateo_completo.xlsx", type=["xlsx"], key="resumen_upload_prorr")
        if up:
            dfp = read_excel_cached(up.getvalue(), sheet_name=0)
            dfp.columns = dfp.columns.astype(str).str.strip().str.upper()
            prorr = dfp

    if prorr is None:
        return

    prorr = prorr.copy()
    prorr.columns = prorr.columns.astype(str).str.strip().str.upper()

    if "SUCURSAL" not in prorr.columns or "CARGO ASIGNADO" not in prorr.columns or "TIPO COSTO" not in prorr.columns:
        alert("error", "El prorrateo debe tener columnas: SUCURSAL, CARGO ASIGNADO, TIPO COSTO.")
        return

    col_suc = "SUCURSAL"
    col_val = "CARGO ASIGNADO"
    col_tipo = "TIPO COSTO"

    # =======================
    # A) Generales/Indirectos/Consolidado
    # =======================
    st.markdown("### A) 📘 Generales e Indirectos (Consolidado)")

    comunes = prorr[prorr[col_tipo].isin(["COMUN INTERNO", "COMUN EXTERNO"])]

    pivot_comunes = (
        comunes.pivot_table(
            index=col_suc,
            columns=col_tipo,
            values=col_val,
            aggfunc="sum",
            fill_value=0.0,
        )
        .reset_index()
    )

    for expected in ["COMUN INTERNO", "COMUN EXTERNO"]:
        if expected not in pivot_comunes.columns:
            pivot_comunes[expected] = 0.0

    indirectos = (
        prorr[prorr[col_tipo] == "COSTO INDIRECTO"]
        .groupby(col_suc, as_index=False)[col_val]
        .sum()
        .rename(columns={col_val: "INDIRECTO"})
    )

    final = pivot_comunes.merge(indirectos, on=col_suc, how="outer").fillna(0.0)
    final["TOTAL"] = final["COMUN INTERNO"] + final["COMUN EXTERNO"] + final["INDIRECTO"]

    c1, c2 = st.columns(2)
    with c1:
        section_header("▸", "Generales por sucursal")
        st.dataframe(pivot_comunes[[col_suc, "COMUN INTERNO", "COMUN EXTERNO"]], use_container_width=True)
    with c2:
        section_header("▸", "Indirectos por sucursal")
        st.dataframe(indirectos, use_container_width=True)

    section_header("▸", "Consolidado final")
    st.dataframe(final[[col_suc, "COMUN INTERNO", "COMUN EXTERNO", "INDIRECTO", "TOTAL"]], use_container_width=True)

    st.download_button(
        "📥 Descargar Excel (Generales/Indirectos/Consolidado)",
        data=to_excel_bytes_sheets({
            "Generales": pivot_comunes[[col_suc, "COMUN INTERNO", "COMUN EXTERNO"]],
            "Indirectos": indirectos,
            "Consolidado": final[[col_suc, "COMUN INTERNO", "COMUN EXTERNO", "INDIRECTO", "TOTAL"]],
        }),
        file_name="generales_indirectos_consolidado.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    # =======================
    # B) Costo por sucursal (tablitas)
    # =======================
    divider()
    st.markdown("### B) 📅 Costo por sucursal (tablitas por mes)")

    # GTS desde memoria o upload
    df_gts = st.session_state.get("gg_df_gts")
    if df_gts is None:
        upg = st.file_uploader("Sube el Excel con hoja 'GTS' (si no lo cargaste en Prorrateo GG)", type=["xlsx"], key="resumen_upload_gts")
        if upg:
            df_gts = read_excel_cached(upg.getvalue(), sheet_name="GTS")
            df_gts.columns = df_gts.columns.astype(str).str.strip().str.upper()
            st.session_state["gg_df_gts"] = df_gts

    if df_gts is None:
        alert("info", "Carga GTS para habilitar el costo por sucursal.")
        return

    df_gts_local = df_gts.copy()
    df_gts_local.columns = df_gts_local.columns.astype(str).str.strip().str.upper()
    df_gts_local["SUCURSAL"] = df_gts_local["SUCURSAL"].astype(str).str.strip().str.upper()

    COL_FACT = _find_col(df_gts_local, ["FACTURACION DLLS", "FACTURACIÓN DLLS", "FACTURACION", "FACTURACIÓN"])
    COL_MC   = _find_col(df_gts_local, ["MC", "M.C.", "MARGEN", "MARGEN CONTRIBUCION", "MARGEN DE CONTRIBUCION"])
    if not COL_FACT or not COL_MC:
        alert("error", "No pude detectar columnas en GTS. Asegúrate de tener algo como 'FACTURACION DLLS' y 'MC'.")
        return

    # Catálogo (opcional, para mostrar tipo distribución)
    catalogo = pd.DataFrame()
    if supabase is not None:
        try:
            cat_resp = supabase.table("catalogo_distribucion").select("*").execute()
            catalogo = pd.DataFrame(cat_resp.data).rename(columns={
                "area_cuenta": "AREA/CUENTA",
                "tipo_distribucion": "TIPO DISTRIBUCIÓN"
            })
            if not catalogo.empty:
                catalogo["AREA/CUENTA"] = catalogo["AREA/CUENTA"].astype(str).str.strip().str.upper()
        except Exception:
            catalogo = pd.DataFrame()

    sucursales = sorted(df_gts_local["SUCURSAL"].dropna().unique().tolist())
    sucursal_sel = st.selectbox("Selecciona sucursal", sucursales, key="resumen_sucursal_sel")

    def generar_tablitas_mes_sucursal(sucursal: str):
        suc = str(sucursal).strip().upper()
        row_gts = df_gts_local[df_gts_local["SUCURSAL"].eq(suc)]
        if row_gts.empty:
            return None, None, None, f"No existe la sucursal '{suc}' en GTS."

        facturacion = float(row_gts.iloc[0][COL_FACT] or 0)
        mc = float(row_gts.iloc[0][COL_MC] or 0)

        costos_directos = facturacion - mc
        utilidad = mc

        gi = prorr[(prorr["SUCURSAL"].eq(suc)) & (prorr["TIPO COSTO"].eq("COSTO INDIRECTO"))].copy()
        tabla_gi = (
            gi.groupby("AREA/CUENTA", as_index=False)["CARGO ASIGNADO"]
              .sum()
              .rename(columns={"AREA/CUENTA": "GASTOS INDIRECTOS", "CARGO ASIGNADO": "IMPORTE"})
              .sort_values("IMPORTE", ascending=False)
              .reset_index(drop=True)
        )
        tabla_gi["%"] = np.where(facturacion != 0, tabla_gi["IMPORTE"] / facturacion, 0.0)

        total_ci = float(tabla_gi["IMPORTE"].sum())
        pct_ci = (total_ci / facturacion) if facturacion != 0 else 0.0

        ge = prorr[(prorr["SUCURSAL"].eq(suc)) & (prorr["TIPO COSTO"].isin(["COMUN EXTERNO", "COMUN INTERNO"]))].copy()
        tabla_ge = (
            ge.groupby("AREA/CUENTA", as_index=False)["CARGO ASIGNADO"]
              .sum()
              .rename(columns={"AREA/CUENTA": "AREA-TIPO GASTO", "CARGO ASIGNADO": "IMPORTE"})
        )

        if not catalogo.empty:
            tabla_ge["AREA_KEY"] = tabla_ge["AREA-TIPO GASTO"].astype(str).str.strip().str.upper()
            tabla_ge = tabla_ge.merge(
                catalogo[["AREA/CUENTA", "TIPO DISTRIBUCIÓN"]].rename(columns={"AREA/CUENTA": "AREA_KEY"}),
                on="AREA_KEY",
                how="left"
            ).drop(columns=["AREA_KEY"])

        tabla_ge["%"] = np.where(facturacion != 0, tabla_ge["IMPORTE"] / facturacion, 0.0)
        tabla_ge = tabla_ge.sort_values("IMPORTE", ascending=False).reset_index(drop=True)

        total_gn = float(tabla_ge["IMPORTE"].sum())
        pct_gn = (total_gn / facturacion) if facturacion != 0 else 0.0

        pct_ut_bruta = (utilidad / facturacion) if facturacion != 0 else 0.0
        ut_per = utilidad - total_ci - total_gn
        pct_ut_per = (ut_per / facturacion) if facturacion != 0 else 0.0

        tabla_top = pd.DataFrame([{
            "Sucursal": suc,
            "Facturación": facturacion,
            "Costos Directos": costos_directos,
            "Utilidad": utilidad,
            "% Ut Bruta": pct_ut_bruta,
            "Costos Indirectos": total_ci,
            "% CI": pct_ci,
            "Gastos Generales": total_gn,
            "% GN": pct_gn,
            "UT/PER": ut_per,
            "%UT/PER": pct_ut_per
        }])

        return tabla_top, tabla_gi, tabla_ge, None

    tabla_top, tabla_gi, tabla_ge, err = generar_tablitas_mes_sucursal(sucursal_sel)
    if err:
        st.error(err)
        return

    section_header("🧾", "Resumen superior")
    st.dataframe(tabla_top, use_container_width=True)

    section_header("📌", "GASTOS INDIRECTOS (Costo indirecto)")
    st.dataframe(tabla_gi, use_container_width=True)

    section_header("📌", "AREA-TIPO GASTO (Común interno + Común externo)")
    st.dataframe(tabla_ge, use_container_width=True)

    def exportar_costo_sucursal_excel(tabla_top, tabla_gi, tabla_ge, nombre_sucursal):
        from io import BytesIO
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            sheet = str(nombre_sucursal)[:31]
            tabla_top.to_excel(writer, sheet_name=sheet, index=False, startrow=0, startcol=0)
            tabla_gi.to_excel(writer, sheet_name=sheet, index=False, startrow=4, startcol=0)
            tabla_ge.to_excel(writer, sheet_name=sheet, index=False, startrow=4, startcol=6)
        return buffer.getvalue()

    st.download_button(
        "📥 Descargar Excel de esta sucursal",
        data=exportar_costo_sucursal_excel(tabla_top, tabla_gi, tabla_ge, sucursal_sel),
        file_name=f"costo_por_sucursal_{sucursal_sel}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
