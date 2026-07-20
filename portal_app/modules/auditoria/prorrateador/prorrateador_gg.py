# portal_app/modules/auditoria/prorrateador_gg.py
from __future__ import annotations

import re
import pandas as pd
import streamlit as st
from datetime import date

from services.supabase_client import get_authed_client as get_supabase_client
from .shared import to_excel_bytes_sheets, read_excel_cached, homologar_sucursales_con_gts, log_accion


TIPOS_DISTRIBUCION = [
    "Facturación Dlls", "MC", "Tráficos",
    "Empleado hub", "Empleados mv", "XTRALEASE", "Uso Cajas"
]

SUCURSALES_BASE = [
    "CAR-GAR", "CHICAGO", "CONSOLIDADO", "DALLAS", "GUADALAJARA",
    "LEON", "LINCOLN LOGISTICS", "MG HAULERS", "MONTERREY",
    "NUEVO LAREDO", "QUERETARO", "ROLANDO ALFARO"
]


def _suc_upper(s):
    return str(s).strip().upper()


def render():
    from ui.components import section_header, alert, divider
    section_header("🧾", "Prorrateo de Gastos Generales (GG)")

    supabase = get_supabase_client()
    if supabase is None:
        alert("warn", "⚠️ Supabase no configurado. Podrás calcular, pero no guardar/leer catálogo y tráficos.")

    # ================================
    # 1) PASO 1: subir archivo y resumen de comunes
    # ================================
    st.markdown("### 1) PASO 1 → Resumen de COMUNES (GASTO GENERAL / INTERNO / EXTERNO)")
    uploaded_file = st.file_uploader("Sube el Excel con la hoja 'PASO 1'", type=["xlsx"], key="gg_paso1")

    if uploaded_file:
        try:
            file_bytes = uploaded_file.getvalue()
            df = read_excel_cached(file_bytes, sheet_name="PASO 1")
            df.columns = df.columns.astype(str).str.strip().str.upper()

            required = {"SUCURSAL", "AREA/CUENTA", "CARGOS"}
            missing = required - set(df.columns)
            if missing:
                st.error(f"❌ Faltan columnas requeridas en PASO 1: {sorted(missing)}")
                st.stop()

            df["SUCURSAL"] = df["SUCURSAL"].astype(str).str.strip().str.upper()
            if "CONCEPTO" not in df.columns:
                df["CONCEPTO"] = ""

            st.session_state["gg_df_original"] = df

            comunes_base = df[df["SUCURSAL"].isin(["GASTO GENERAL", "INTERNO", "EXTERNO"])].copy()
            if comunes_base.empty:
                alert("error", "❌ No hay filas con SUCURSAL = GASTO GENERAL / INTERNO / EXTERNO.")
                st.stop()

            resumen = (
                comunes_base
                .groupby("AREA/CUENTA", as_index=False)["CARGOS"]
                .sum()
                .sort_values(by="CARGOS", ascending=False)
            )
            st.session_state["gg_resumen"] = resumen

            alert("success", "Resumen generado.")
            st.dataframe(resumen, use_container_width=True)

            descargado_resumen = st.download_button(
                "📥 Descargar resumen (Excel)",
                data=to_excel_bytes_sheets({"Resumen Gastos": resumen}),
                file_name="resumen_gastos_generales.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            if descargado_resumen:
                log_accion("aud-prorrateador", "exportar_excel", {"reporte": "resumen_gg", "filas": len(resumen)})

        except Exception as e:
            st.error(f"Error PASO 1: {e}")
            st.exception(e)

    # ================================
    # 2) Tráfico por sucursal
    # ================================
    st.markdown("### 2) 🚛 Tráfico por sucursal (guardar en Supabase)")
    fecha_global = st.date_input("📅 Fecha de tráfico", value=date.today(), key="gg_fecha_trafico")

    traficos_df = pd.DataFrame({"Sucursal": SUCURSALES_BASE, "Tráfico": ["" for _ in SUCURSALES_BASE]})
    edit_df = st.data_editor(traficos_df, use_container_width=True, num_rows="fixed", key="gg_trafico_editor")

    if st.button("💾 Guardar tráficos en Supabase", key="gg_save_traficos", disabled=(supabase is None)):
        try:
            df_to_save = edit_df.copy()
            faltan = df_to_save["Tráfico"].astype(str).str.strip().eq("")
            if faltan.any():
                alert("warn", "Completa todos los números de tráfico antes de guardar.")
            else:
                df_to_save["Sucursal"] = df_to_save["Sucursal"].astype(str).str.strip().str.upper()
                df_to_save["Trafico"]  = df_to_save["Tráfico"].astype(str).str.strip()
                df_to_save["Fecha"]    = pd.to_datetime(fecha_global).strftime("%Y-%m-%d")

                payload = df_to_save[["Sucursal", "Trafico", "Fecha"]].to_dict(orient="records")
                supabase.table("viajes_distribucion").insert(payload).execute()
                st.success(f"✅ Tráficos guardados ({len(payload)} filas).")
        except Exception as e:
            st.error(f"Error al guardar en Supabase: {e}")
            st.exception(e)

    # ================================
    # 3) Catálogo de distribución
    # ================================
    st.markdown("### 3) 📘 Catálogo de Distribución por AREA/CUENTA")
    if "gg_resumen" not in st.session_state:
        alert("info", "Primero genera el resumen en PASO 1 para poder editar el catálogo.")
    else:
        resumen = st.session_state["gg_resumen"][["AREA/CUENTA"]].drop_duplicates().reset_index(drop=True)

        catalogo_existente = pd.DataFrame()
        if supabase is not None:
            try:
                data_supabase = supabase.table("catalogo_distribucion").select("*").execute().data
                catalogo_existente = pd.DataFrame(data_supabase)
            except Exception:
                catalogo_existente = pd.DataFrame()

        if not catalogo_existente.empty:
            catalogo_existente = catalogo_existente.rename(columns={
                "area_cuenta": "AREA/CUENTA",
                "tipo_distribucion": "TIPO DISTRIBUCIÓN"
            })
            resumen_merged = resumen.merge(catalogo_existente, on="AREA/CUENTA", how="left")
        else:
            resumen_merged = resumen.copy()
            resumen_merged["TIPO DISTRIBUCIÓN"] = None

        section_header("▸", "Catálogo de Distribución")
        resumen_merged = resumen_merged.sort_values(by=["TIPO DISTRIBUCIÓN", "AREA/CUENTA"], na_position="first").reset_index(drop=True)

        edited_df = st.data_editor(
            resumen_merged,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "TIPO DISTRIBUCIÓN": st.column_config.SelectboxColumn(
                    label="Tipo de Distribución",
                    options=TIPOS_DISTRIBUCION,
                    required=True
                )
            },
            key="gg_cat_editor",
        )

        if st.button("💾 Guardar catálogo en Supabase", key="gg_save_catalogo", disabled=(supabase is None)):
            try:
                nuevos = edited_df[edited_df["TIPO DISTRIBUCIÓN"].notna()]
                payload = []
                for _, row in nuevos.iterrows():
                    payload.append({
                        "area_cuenta": str(row["AREA/CUENTA"]).strip().upper(),
                        "tipo_distribucion": str(row["TIPO DISTRIBUCIÓN"]).strip()
                    })
                if payload:
                    supabase.table("catalogo_distribucion").upsert(payload, on_conflict="area_cuenta").execute()
                alert("success", "Catálogo actualizado en Supabase.")
            except Exception as e:
                st.error(f"Error guardando catálogo: {e}")
                st.exception(e)

    # ================================
    # 4) GTS → porcentajes
    # ================================
    st.markdown("### 4) 📊 Cargar GTS y calcular porcentajes")
    archivo_gts = st.file_uploader("Sube el Excel con la hoja 'GTS'", type=["xlsx"], key="gg_gts")

    if archivo_gts:
        try:
            df_gts = read_excel_cached(archivo_gts.getvalue(), sheet_name="GTS")
            df_gts.columns = df_gts.columns.astype(str).str.strip().str.upper()
            st.session_state["gg_df_gts"] = df_gts

            section_header("▸", "Datos GTS")
            st.dataframe(df_gts.head(200), use_container_width=True)

            if "SUCURSAL" not in df_gts.columns:
                alert("error", "GTS debe contener columna SUCURSAL.")
                st.stop()

            tipo_cols = [c for c in df_gts.columns if c != "SUCURSAL"]
            totales = df_gts[tipo_cols].sum().rename("TOTAL").to_frame().T
            section_header("▸", "Totales por tipo")
            st.dataframe(totales, use_container_width=True)

            porcentajes = df_gts.copy()
            for col in tipo_cols:
                total = df_gts[col].sum()
                porcentajes[col] = (df_gts[col] / total) if total != 0 else 0

            porcentajes["SUCURSAL"] = porcentajes["SUCURSAL"].astype(str).str.strip().str.upper()
            st.session_state["gg_porcentajes"] = porcentajes.set_index("SUCURSAL")

            section_header("▸", "Porcentajes")
            st.dataframe(porcentajes.head(200), use_container_width=True)

        except Exception as e:
            st.error(f"Error GTS: {e}")
            st.exception(e)

    # ================================
    # 5) Prorrateo completo
    # ================================
    st.markdown("### 5) 🔄 Generar prorrateo completo (con Tráfico/Fecha)")

    if not all(k in st.session_state for k in ["gg_df_original", "gg_resumen", "gg_porcentajes"]):
        alert("info", "Completa pasos 1 y 4 para poder generar prorrateo completo.")
        return

    if st.button("✅ Generar prorrateo completo", key="gg_generar_prorrateo"):
        try:
            df_original = st.session_state["gg_df_original"].copy()
            porcentajes = st.session_state["gg_porcentajes"].copy()

            # traer catálogo
            if supabase is None:
                alert("error", "Necesitas Supabase para leer catálogo y viajes (por ahora).")
                st.stop()

            cat_resp = supabase.table("catalogo_distribucion").select("*").execute()
            catalogo = pd.DataFrame(cat_resp.data)
            if catalogo.empty:
                alert("error", "No hay datos en 'catalogo_distribucion'.")
                st.stop()

            catalogo = catalogo.rename(columns={
                "area_cuenta": "AREA/CUENTA",
                "tipo_distribucion": "TIPO DISTRIBUCIÓN"
            })
            catalogo["AREA/CUENTA"] = catalogo["AREA/CUENTA"].astype(str).str.strip().str.upper()

            # viajes/fecha
            viajes_resp = supabase.table("viajes_distribucion").select("*").execute()
            viajes = pd.DataFrame(viajes_resp.data)
            if viajes.empty:
                viajes = pd.DataFrame(columns=["Sucursal", "Trafico", "Fecha"])

            viajes = viajes.rename(columns={"Sucursal": "SUCURSAL", "Trafico": "TRAFICO", "Fecha": "FECHA"})
            viajes["SUCURSAL"] = viajes["SUCURSAL"].astype(str).str.upper().str.strip()
            viajes["FECHA"] = pd.to_datetime(viajes["FECHA"], errors="coerce")

            fechas_disp = sorted(viajes["FECHA"].dropna().dt.date.unique())
            fecha_elegida = st.date_input(
                "📅 Selecciona la FECHA de viajes_distribucion a usar",
                value=(fechas_disp[-1] if len(fechas_disp) else date.today()),
                key="gg_fecha_viajes_sel",
            )

            viajes_sel = viajes[viajes["FECHA"].dt.date.eq(fecha_elegida)].copy()
            viajes_sel["FECHA"] = pd.to_datetime(viajes_sel["FECHA"]).dt.strftime("%Y-%m-%d")
            viajes_sel = viajes_sel.drop_duplicates(subset=["SUCURSAL"], keep="last")

            def anexar_trafico_fecha(df: pd.DataFrame) -> pd.DataFrame:
                if df.empty:
                    return df.assign(TRAFICO=None, FECHA=None)
                return df.merge(viajes_sel[["SUCURSAL", "TRAFICO", "FECHA"]], on="SUCURSAL", how="left")

            # Homologación sucursales con GTS
            suc_validas = porcentajes.index.tolist()
            df_original, no_recon = homologar_sucursales_con_gts(df_original, suc_validas, col="SUCURSAL")
            if no_recon:
                st.warning(f"Sucursales NO reconocidas: {no_recon[:15]}{'...' if len(no_recon)>15 else ''}")

            # BLOQUE A: costos con sucursal (NO comunes)
            no_general = df_original[~df_original["SUCURSAL"].isin(["GASTO GENERAL", "INTERNO", "EXTERNO"])].copy()
            no_general["TIPO COSTO"] = "COSTO INDIRECTO"
            no_general["TIPO DISTRIBUCIÓN"] = "Costo fijo en sucursal"

            directos_agr = (
                no_general
                .assign(SUCURSAL=lambda d: d["SUCURSAL"].astype(str).str.upper().str.strip())
                .groupby(["AREA/CUENTA", "SUCURSAL", "TIPO DISTRIBUCIÓN", "TIPO COSTO"], as_index=False)["CARGOS"]
                .sum()
                .rename(columns={"CARGOS": "CARGO ASIGNADO"})
            )
            directos_agr = anexar_trafico_fecha(directos_agr)

            # BLOQUE B: comunes (GASTO GENERAL + INTERNO + EXTERNO)
            comunes = df_original[df_original["SUCURSAL"].isin(["GASTO GENERAL", "INTERNO", "EXTERNO"])].copy()
            if comunes.empty:
                alert("error", "❌ No hay comunes para prorratear.")
                st.stop()

            def tipo_costo_hibrido(row) -> str:
                suc = str(row.get("SUCURSAL", "")).strip().upper()
                if suc == "INTERNO":
                    return "COMUN INTERNO"
                if suc == "EXTERNO":
                    return "COMUN EXTERNO"
                if suc == "GASTO GENERAL":
                    c = str(row.get("CONCEPTO", "")).strip().upper()
                    if c.startswith("IN"):
                        return "COMUN INTERNO"
                    if c.startswith("EX"):
                        return "COMUN EXTERNO"
                    return "COMUN INTERNO"
                return "COMUN INTERNO"

            comunes["TIPO COSTO"] = comunes.apply(tipo_costo_hibrido, axis=1)

            gg_agr = (
                comunes
                .groupby(["AREA/CUENTA", "TIPO COSTO"], as_index=False)["CARGOS"]
                .sum()
                .rename(columns={"CARGOS": "TOTAL_AREA"})
            )

            gg_agr["AREA/CUENTA"] = gg_agr["AREA/CUENTA"].astype(str).str.strip().str.upper()
            gg_agr = gg_agr.merge(catalogo, on="AREA/CUENTA", how="left")

            if gg_agr["TIPO DISTRIBUCIÓN"].isna().any():
                falt = gg_agr.loc[gg_agr["TIPO DISTRIBUCIÓN"].isna(), "AREA/CUENTA"].unique().tolist()
                st.error(f"Faltan tipos de distribución en catálogo para: {falt[:10]}{'...' if len(falt)>10 else ''}")
                st.stop()

            prorr_rows = []
            for _, r in gg_agr.iterrows():
                area = r["AREA/CUENTA"]
                tipo_dist = str(r["TIPO DISTRIBUCIÓN"]).upper()
                tipo_costo = r["TIPO COSTO"]
                total = float(r["TOTAL_AREA"])

                if tipo_dist not in porcentajes.columns:
                    st.warning(f"No hay porcentajes para '{tipo_dist}'. Se omite {area}")
                    continue

                for suc, pct in porcentajes[tipo_dist].items():
                    if pct and float(pct) > 0:
                        prorr_rows.append({
                            "AREA/CUENTA": area,
                            "SUCURSAL": str(suc).upper().strip(),
                            "TIPO DISTRIBUCIÓN": r["TIPO DISTRIBUCIÓN"],
                            "TIPO COSTO": tipo_costo,
                            "CARGO ASIGNADO": round(total * float(pct), 2)
                        })

            prorr_gg = pd.DataFrame(prorr_rows)
            prorr_gg = anexar_trafico_fecha(prorr_gg)

            resultado = pd.concat([directos_agr, prorr_gg], ignore_index=True)

            st.session_state["gg_prorrateo_completo"] = resultado
            log_accion("aud-prorrateador", "ejecutar_prorrateo", {"filas": len(resultado)})
            alert("success", "✅ Prorrateo completo generado.")
            st.dataframe(resultado.head(200), use_container_width=True)

            descargado_prorrateo = st.download_button(
                "📥 Descargar prorrateo completo",
                data=to_excel_bytes_sheets({"Prorrateo": resultado}),
                file_name="prorrateo_completo.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            if descargado_prorrateo:
                log_accion("aud-prorrateador", "exportar_excel", {"reporte": "prorrateo_completo", "filas": len(resultado)})

        except Exception as e:
            st.error(f"Error generando prorrateo: {e}")
            st.exception(e)
