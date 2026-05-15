# portal_app/modules/auditoria/prorrateador.py
import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

from services.supabase_client import get_authed_client as get_supabase_client
from .shared import (
    get_empresa_config,
    normaliza_tipo_distribucion,
    find_column,
    build_flag_trailer,
    OPERADORES_EXCLUIR,
)


def render():
    from ui.components import page_banner, section_header, alert, divider
    page_banner("💹", "Rentabilidad Clientes", "Prorrateo de costos indirectos por cliente")


    st.markdown(
        """
Esta app te ayuda a:
1. Calcular, a partir de la **DATA detallada**, la tabla de viajes por cliente/año/mes
   (viajes totales, con remolque, con unidad, millas/kilómetros, tipo de cliente),
   excluyendo ciertos operadores logísticos (solo cuando aplique).
2. Repartir costos **no ligados a la operación** entre viajes con/sin unidad
   (y obtener costos unitarios).
3. Definir un catálogo de distribución para costos **ligados a la operación** (por empresa).
4. Prorratear esos costos entre clientes.
5. **Asignar los costos indirectos (CI) a nivel viaje**.
"""
    )

    # ============================================================
    # 0️⃣ SELECCIÓN DE EMPRESA + CONFIGURACIÓN
    # ============================================================
    section_header("🏢", "Empresa")

    empresas = ["Lincoln Freight", "Set Logis Plus", "Picus Carrier", "Igloo Carrier"]
    empresa = st.selectbox("Selecciona empresa", empresas, index=0)

    CFG = get_empresa_config(empresa)
    DIST_COL_NAME = CFG["dist_label"]  # "Millas" o "Kilómetros"

    supabase = get_supabase_client()
    if supabase is None:
        st.warning(
            "⚠️ Supabase no está configurado (secrets/env). "
            "Podrás correr cálculos, pero el catálogo no se podrá leer/guardar en la BD."
        )

    # ============================================================
    # Auxiliares: export excel
    # ============================================================
    def to_excel_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            for name, df in sheets.items():
                df.to_excel(writer, index=False, sheet_name=name[:31])
        return buffer.getvalue()

    # ============================================================
    # 1️⃣ CARGA DATA DETALLADA Y TABLA POR CLIENTE
    # ============================================================
    section_header("1️⃣", "Cargar DATA detallada de viajes y generar tabla por cliente")

    file_data = st.file_uploader(
        "Sube la DATA detallada de viajes",
        type=["xlsx"],
        key="data_file",
    )

    if file_data:
        try:
            xls = pd.ExcelFile(file_data)
            hoja_data = st.selectbox("Selecciona la hoja con la DATA detallada", xls.sheet_names)
            df_data = pd.read_excel(xls, sheet_name=hoja_data)
            df_data.columns = df_data.columns.astype(str)

            section_header("▸", "Vista previa DATA de viajes")
            st.dataframe(df_data.head(), use_container_width=True)

            col_fecha = find_column(df_data, CFG["candidates_fecha"])
            col_customer = find_column(df_data, CFG["candidates_customer"])
            col_trip = find_column(df_data, CFG["candidates_trip"])
            col_trailer = find_column(df_data, CFG["candidates_trailer"])
            col_unit = find_column(df_data, CFG["candidates_unit"])
            col_dist = find_column(df_data, CFG["candidates_dist"])

            col_logop = None
            if CFG["usa_operador"]:
                col_logop = find_column(df_data, CFG["candidates_operador"])

            faltan = []
            if col_fecha is None: faltan.append("Fecha")
            if col_customer is None: faltan.append("Customer/Cliente")
            if col_trip is None: faltan.append("Trip/Viaje")
            if col_trailer is None: faltan.append("Trailer/Remolque")
            if col_unit is None: faltan.append("Unit/Unidad")
            if col_dist is None: faltan.append(DIST_COL_NAME)
            if CFG["usa_operador"] and col_logop is None:
                faltan.append("Operador logístico")

            if faltan:
                st.error("No se encontraron columnas necesarias: " + ", ".join(faltan))
                st.stop()

            df_work = df_data.copy()
            df_work[col_fecha] = pd.to_datetime(df_work[col_fecha], errors="coerce")

            # Selección año/mes
            df_work = df_work[df_work[col_fecha].notna()].copy()
            anios = sorted(df_work[col_fecha].dt.year.dropna().unique().astype(int).tolist())
            if not anios:
                alert("error", "No se detectaron fechas válidas.")
                st.stop()

            anio_sel = st.selectbox("Año", anios, index=len(anios) - 1)
            meses = list(range(1, 13))
            mes_sel = st.selectbox("Mes", meses, index=meses.index(int(df_work[col_fecha].dt.month.mode().iloc[0])) if not df_work.empty else 0)

            st.session_state["anio_sel"] = int(anio_sel)
            st.session_state["mes_sel"] = int(mes_sel)

            mask_mes = (df_work[col_fecha].dt.year == int(anio_sel)) & (df_work[col_fecha].dt.month == int(mes_sel))
            df_mes = df_work[mask_mes].copy()

            st.write(f"Filtrado: **{len(df_mes):,}** viajes para {mes_sel:02d}/{anio_sel}.")
            st.dataframe(df_mes.head(), use_container_width=True)

            # Flags
            df_mes["Viaje"] = df_mes[col_trip].astype(str)
            df_mes["Customer"] = df_mes[col_customer].astype(str).str.strip()
            df_mes["Con unidad"] = df_mes[col_unit].astype(str).str.strip().ne("") & df_mes[col_unit].notna()
            df_mes["Con remolque"] = build_flag_trailer(df_mes[col_trailer], CFG["trailer_prefix"]).astype(bool)

            dist_num = pd.to_numeric(df_mes[col_dist], errors="coerce").fillna(0.0)
            df_mes[DIST_COL_NAME] = dist_num

            if CFG["usa_operador"]:
                op_upper = df_mes[col_logop].astype(str).str.upper().str.strip()
                df_mes["Excluido_por_operador"] = op_upper.isin(OPERADORES_EXCLUIR)
            else:
                df_mes["Excluido_por_operador"] = False

            # Tabla por cliente (agregada)
            df_mes_clientes = (
                df_mes.groupby(["Customer"], as_index=False)
                .agg(
                    Viajes=("Viaje", "count"),
                    **{
                        "Viajes con remolques": ("Con remolque", "sum"),
                        "Viajes con unidad": ("Con unidad", "sum"),
                        DIST_COL_NAME: (DIST_COL_NAME, "sum"),
                    },
                )
            )

            section_header("▸", "Tabla por cliente (mes seleccionado)")
            st.dataframe(df_mes_clientes, use_container_width=True)

            st.session_state["df_mes_clientes"] = df_mes_clientes
            st.session_state["df_data_original"] = df_data  # para paso 5
            st.session_state["df_data_mes_filtrada"] = df_mes

            st.download_button(
                "📥 Descargar tabla por cliente",
                data=to_excel_bytes({"Tabla_clientes": df_mes_clientes}),
                file_name="tabla_clientes_mes.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        except Exception as e:
            st.error(f"Error procesando DATA detallada: {e}")
            st.exception(e)

    # ============================================================
    # 2️⃣ COSTOS NO OPERATIVOS
    # ============================================================
    section_header("2️⃣", "Costos NO ligados a operación (unitarios)")

    file_no_op = st.file_uploader(
        "Sube el archivo de costos NO operativos (mismo formato: Concepto + meses)",
        type=["xlsx"],
        key="no_op_file",
    )

    if file_no_op:
        try:
            xls_no = pd.ExcelFile(file_no_op)
            hoja_no = st.selectbox("Hoja de costos NO operativos", xls_no.sheet_names, key="hoja_noop_sel")
            df_no = pd.read_excel(xls_no, sheet_name=hoja_no)
            df_no.columns = df_no.columns.astype(str).str.strip()

            section_header("▸", "Vista previa costos NO operativos")
            st.dataframe(df_no.head(), use_container_width=True)

            # Elegir columna mes
            columnas_mes_no = [c for c in df_no.columns if c.lower() not in ("concepto",)]
            mes_sel_global = st.session_state.get("mes_sel")

            idx_default = 0
            if mes_sel_global is not None and len(columnas_mes_no) > 0:
                mapa_meses = {1:"Ene",2:"Feb",3:"Mar",4:"Abr",5:"May",6:"Jun",7:"Jul",8:"Ago",9:"Sep",10:"Oct",11:"Nov",12:"Dic"}
                nombre_mes = mapa_meses.get(int(mes_sel_global))
                if nombre_mes in columnas_mes_no:
                    idx_default = columnas_mes_no.index(nombre_mes)

            col_mes_no = st.selectbox("Selecciona la columna del mes a prorratear", columnas_mes_no, index=idx_default, key="mes_noop")
            concepto_col = "Concepto" if "Concepto" in df_no.columns else df_no.columns[0]

            df_no["Concepto"] = df_no[concepto_col].astype(str).str.strip()
            df_no["Monto_mes"] = pd.to_numeric(df_no[col_mes_no], errors="coerce").fillna(0)

            st.write(f"**Total costos NO operativos ({col_mes_no}):** ${df_no['Monto_mes'].sum():,.2f}")

            if "df_mes_clientes" not in st.session_state:
                alert("info", "Primero completa el paso 1 para poder calcular unitarios (necesitamos viajes y distancia).")
            else:
                df_mes_clientes = st.session_state["df_mes_clientes"].copy()

                total_dist = float(df_mes_clientes[DIST_COL_NAME].sum())
                total_viajes = float(df_mes_clientes["Viajes"].sum())
                total_viajes_con_unidad = float(df_mes_clientes["Viajes con unidad"].sum())
                total_viajes_sin_unidad = float(total_viajes - total_viajes_con_unidad)

                total_cost_no_op = float(df_no["Monto_mes"].sum())

                # Reglas:
                # - viajes con unidad prorratean por distancia
                # - viajes sin unidad prorratean por viaje (flat)
                # - primero “separa” bolsas proporcionalmente a conteos (mismo criterio que tu script del paso 5)
                if total_viajes <= 0:
                    alert("error", "Total de viajes es 0. No se pueden calcular unitarios.")
                else:
                    pct_con_unidad = (total_viajes_con_unidad / total_viajes) if total_viajes else 0.0
                    pct_sin_unidad = (total_viajes_sin_unidad / total_viajes) if total_viajes else 0.0

                    bolsa_unidad = total_cost_no_op * pct_con_unidad
                    bolsa_sin = total_cost_no_op * pct_sin_unidad

                    costo_x_dist = (bolsa_unidad / total_dist) if total_dist > 0 else 0.0
                    costo_x_viaje_sin = (bolsa_sin / total_viajes_sin_unidad) if total_viajes_sin_unidad > 0 else 0.0

                    alert("success", "Unitarios calculados ✅")
                    st.metric(f"Costo unitario por {DIST_COL_NAME}", f"${costo_x_dist:,.6f}")
                    st.metric("Costo unitario por viaje sin unidad", f"${costo_x_viaje_sin:,.2f}")

                    st.session_state["costo_no_op_x_dist"] = float(costo_x_dist)
                    st.session_state["costo_no_op_x_viaje_sin"] = float(costo_x_viaje_sin)

        except Exception as e:
            st.error(f"Error procesando los costos no operativos: {e}")
            st.exception(e)

    # ============================================================
    # 3️⃣ CATÁLOGO COSTOS OPERACIÓN (SUPABASE POR EMPRESA)
    # ============================================================
    section_header("3️⃣", "Catálogo de costos ligados a la operación")

    tipos_distribucion = [
        "Volumen Viajes",
        "Viajes con Remolque",
        "Viajes con unidad",
        DIST_COL_NAME,
    ]

    catalogo_existente = pd.DataFrame()
    if supabase is not None:
        try:
            data_cat = (
                supabase.table("catalogo_costos_clientes")
                .select("*")
                .eq("empresa", empresa)
                .execute()
                .data
            )
            catalogo_existente = pd.DataFrame(data_cat)
        except Exception:
            catalogo_existente = pd.DataFrame()

    file_op = st.file_uploader(
        "Sube el archivo de costos ligados a operación (Concepto + meses)",
        type=["xlsx"],
        key="op_file",
    )

    if file_op:
        try:
            xls_op = pd.ExcelFile(file_op)
            hoja_op_sel = st.selectbox("Hoja de costos ligados a operación", xls_op.sheet_names, key="hoja_op_sel")
            df_op = pd.read_excel(xls_op, sheet_name=hoja_op_sel)
            df_op.columns = df_op.columns.astype(str).str.strip()

            section_header("▸", "Vista previa costos ligados a operación")
            st.dataframe(df_op.head(), use_container_width=True)

            columnas_mes_op = [c for c in df_op.columns if c.lower() not in ("concepto", "concepto ")]

            mes_sel_global = st.session_state.get("mes_sel")
            index_default_op = 0
            if mes_sel_global is not None and len(columnas_mes_op) > 0:
                mapa_meses = {1:"Ene",2:"Feb",3:"Mar",4:"Abr",5:"May",6:"Jun",7:"Jul",8:"Ago",9:"Sep",10:"Oct",11:"Nov",12:"Dic"}
                nombre_mes = mapa_meses.get(int(mes_sel_global))
                if nombre_mes in columnas_mes_op:
                    index_default_op = columnas_mes_op.index(nombre_mes)

            col_mes_op = st.selectbox(
                "Selecciona la columna del mes a prorratear (ej. 'Ene')",
                columnas_mes_op,
                index=index_default_op,
                key="mes_op",
            )

            concepto_col_op = "Concepto" if "Concepto" in df_op.columns else df_op.columns[0]
            df_op["Concepto"] = df_op[concepto_col_op].astype(str).str.strip()
            df_op["Monto_mes"] = pd.to_numeric(df_op[col_mes_op], errors="coerce").fillna(0)

            st.write(f"**Total costos ligados a operación ({col_mes_op}):** ${df_op['Monto_mes'].sum():,.2f}")

            conceptos = df_op[["Concepto"]].drop_duplicates().reset_index(drop=True)

            if not catalogo_existente.empty:
                cat = catalogo_existente.rename(
                    columns={"concepto": "Concepto", "tipo_distribucion": "Tipo distribución"}
                )
                cat["Tipo distribución"] = cat["Tipo distribución"].apply(normaliza_tipo_distribucion)
                merged_cat = conceptos.merge(cat[["Concepto", "Tipo distribución"]], on="Concepto", how="left")
            else:
                merged_cat = conceptos.copy()
                merged_cat["Tipo distribución"] = None

            section_header("▸", "Catálogo de distribución por concepto (por empresa)")
            merged_cat = merged_cat.sort_values(by=["Tipo distribución", "Concepto"], na_position="first").reset_index(drop=True)

            edited_cat = st.data_editor(
                merged_cat,
                use_container_width=True,
                column_config={
                    "Tipo distribución": st.column_config.SelectboxColumn(
                        label="Tipo de distribución",
                        options=tipos_distribucion,
                        required=True,
                    )
                },
                key="cat_editor",
            )

            can_save = supabase is not None
            if not can_save:
                alert("info", "Supabase no disponible: puedes editar el catálogo pero no se guardará en BD.")

            if st.button("💾 Guardar catálogo en Supabase", key="save_cat", disabled=not can_save):
                try:
                    registros = []
                    for _, row in edited_cat.iterrows():
                        if pd.notna(row["Tipo distribución"]):
                            concepto = str(row["Concepto"]).strip()
                            tipo = normaliza_tipo_distribucion(row["Tipo distribución"])

                            registros.append({
                                "empresa": empresa,
                                "concepto": concepto,
                                "tipo_distribucion": str(tipo).strip(),
                                "empresa,concepto": f"{empresa},{concepto}",
                            })

                    if registros:
                        supabase.table("catalogo_costos_clientes").upsert(
                            registros,
                            on_conflict="empresa,concepto",
                        ).execute()

                    alert("success", "Catálogo actualizado en Supabase (por empresa).")
                except Exception as e:
                    st.error(f"Error al guardar el catálogo: {e}")
                    st.exception(e)

            st.session_state["df_costos_op_mes"] = df_op[["Concepto", "Monto_mes"]]

        except Exception as e:
            st.error(f"Error procesando los costos ligados a operación: {e}")
            st.exception(e)

    # ============================================================
    # 4️⃣ PRORRATEO COSTOS OP ENTRE CLIENTES
    # ============================================================
    section_header("4️⃣", "Prorrateo de costos ligados a operación por cliente")

    if ("df_mes_clientes" not in st.session_state) or ("df_costos_op_mes" not in st.session_state):
        alert("info", "Necesitas completar los pasos 1 y 3 para poder prorratear.")
    else:
        df_mes_clientes = st.session_state["df_mes_clientes"].copy()
        df_op_mes = st.session_state["df_costos_op_mes"].copy()

        if supabase is None:
            alert("error", "Para el paso 4 necesitas catálogo desde Supabase (por ahora). Configura secrets/env.")
        else:
            data_cat = (
                supabase.table("catalogo_costos_clientes")
                .select("*")
                .eq("empresa", empresa)
                .execute()
                .data
            )
            catalogo = pd.DataFrame(data_cat)

            if catalogo.empty:
                alert("error", "No hay catálogo de distribución en 'catalogo_costos_clientes' para esta empresa.")
            else:
                catalogo = catalogo.rename(columns={"concepto": "Concepto", "tipo_distribucion": "Tipo distribución"})
                catalogo["Tipo distribución"] = catalogo["Tipo distribución"].apply(normaliza_tipo_distribucion)

                df_op_mes = df_op_mes.merge(catalogo[["Concepto", "Tipo distribución"]], on="Concepto", how="left")

                if df_op_mes["Tipo distribución"].isna().any():
                    faltan = df_op_mes.loc[df_op_mes["Tipo distribución"].isna(), "Concepto"].unique()
                    st.error("Hay conceptos sin tipo de distribución definido: " + ", ".join(faltan[:10]) + ("..." if len(faltan) > 10 else ""))
                else:
                    driver_map = {
                        "Volumen Viajes": "Viajes",
                        "Viajes con Remolque": "Viajes con remolques",
                        "Viajes con unidad": "Viajes con unidad",
                        DIST_COL_NAME: DIST_COL_NAME,
                    }

                    base_clientes = df_mes_clientes.groupby(["Customer"], as_index=False).agg(
                        {"Viajes": "sum", "Viajes con remolques": "sum", "Viajes con unidad": "sum", DIST_COL_NAME: "sum"}
                    )

                    asignaciones = []
                    for _, row in df_op_mes.iterrows():
                        concepto = row["Concepto"]
                        monto = float(row["Monto_mes"])
                        tipo_dist = row["Tipo distribución"]

                        col_driver = driver_map.get(tipo_dist)
                        if col_driver not in base_clientes.columns:
                            st.warning(f"Tipo '{tipo_dist}' requiere columna '{col_driver}', no existe. Se omite {concepto}.")
                            continue

                        df_driver = base_clientes[["Customer", col_driver]].copy()
                        total_driver = df_driver[col_driver].sum()

                        if total_driver == 0:
                            st.warning(f"Driver '{col_driver}' para {concepto} es 0. Se omite.")
                            continue

                        df_driver["%driver"] = df_driver[col_driver] / total_driver
                        df_driver["Concepto"] = concepto
                        df_driver["Tipo distribución"] = tipo_dist
                        df_driver["Costo asignado"] = df_driver["%driver"] * monto
                        asignaciones.append(df_driver)

                    if not asignaciones:
                        alert("warn", "No se pudo asignar ningún costo (revisa drivers y catálogo).")
                    else:
                        asignaciones_df = pd.concat(asignaciones, ignore_index=True)

                        section_header("▸", "Detalle de asignación por concepto y cliente")
                        st.dataframe(asignaciones_df, use_container_width=True)

                        pivot_clientes = (
                            asignaciones_df.pivot_table(
                                index=["Customer"],
                                columns="Concepto",
                                values="Costo asignado",
                                aggfunc="sum",
                                fill_value=0.0,
                            )
                            .reset_index()
                        )
                        pivot_clientes["Total costos ligados op"] = pivot_clientes.drop(columns=["Customer"]).sum(axis=1)

                        section_header("▸", "Totales por cliente (solo costos ligados a la operación)")
                        st.dataframe(pivot_clientes, use_container_width=True)

                        st.session_state["asignaciones_df"] = asignaciones_df
                        st.session_state["conceptos_tipos"] = df_op_mes[["Concepto", "Tipo distribución"]]
                        st.session_state["pivot_clientes_ci"] = pivot_clientes

                        st.download_button(
                            "📥 Descargar resultados (Excel clientes)",
                            data=to_excel_bytes(
                                {"Detalle_asignaciones": asignaciones_df, "Totales_por_cliente": pivot_clientes}
                            ),
                            file_name="prorrateo_costos_clientes.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        )

    # ============================================================
    # 5️⃣ ASIGNACIÓN CI A NIVEL VIAJE
    # ============================================================
    section_header("5️⃣", "Asignación de CI a nivel viaje")

    faltan_requisitos = []
    if st.session_state.get("costo_no_op_x_dist") is None:
        faltan_requisitos.append(f"Costo unitario por {DIST_COL_NAME.lower()} (paso 2).")
    if st.session_state.get("costo_no_op_x_viaje_sin") is None:
        faltan_requisitos.append("Costo unitario por viaje sin unidad (paso 2).")
    if "asignaciones_df" not in st.session_state or "conceptos_tipos" not in st.session_state:
        faltan_requisitos.append("Prorrateo por cliente (paso 4).")

    if faltan_requisitos:
        st.info("Para usar este apartado necesitas haber completado:\n- " + "\n- ".join(faltan_requisitos))
        return

    origen_trips = st.radio(
        "¿Qué base quieres usar para asignar CI?",
        ["Usar la misma DATA del paso 1", "Subir otro archivo"],
        index=0,
        key="origen_trips_radio",
    )

    df_trips = None
    file_trips = None

    if origen_trips == "Usar la misma DATA del paso 1":
        if "df_data_original" not in st.session_state:
            alert("error", "No se encontró la DATA del paso 1 en memoria. Vuelve a cargarla o sube otro archivo.")
            return
        df_trips = st.session_state["df_data_original"].copy()
    else:
        file_trips = st.file_uploader(
            "Sube la base de viajes a nivel detalle",
            type=["xlsx"],
            key="file_trips_ci",
        )

    if (df_trips is not None) or file_trips:
        try:
            if df_trips is None and file_trips is not None:
                xls_trips = pd.ExcelFile(file_trips)
                hoja_trips = st.selectbox("Hoja con los viajes detallados", xls_trips.sheet_names, key="hoja_trips_sel")
                df_trips = pd.read_excel(xls_trips, sheet_name=hoja_trips)
                df_trips.columns = df_trips.columns.astype(str)

            col_fecha = find_column(df_trips, CFG["candidates_fecha"])
            col_customer = find_column(df_trips, CFG["candidates_customer"])
            col_trip = find_column(df_trips, CFG["candidates_trip"])
            col_unit = find_column(df_trips, CFG["candidates_unit"])
            col_trailer = find_column(df_trips, CFG["candidates_trailer"])
            col_dist = find_column(df_trips, CFG["candidates_dist"])

            col_operador = None
            if CFG["usa_operador"]:
                col_operador = find_column(df_trips, CFG["candidates_operador"])

            # filtro por mes si aplica
            if col_fecha is not None and "anio_sel" in st.session_state and "mes_sel" in st.session_state:
                df_trips[col_fecha] = pd.to_datetime(df_trips[col_fecha], errors="coerce")
                anio_sel = int(st.session_state["anio_sel"])
                mes_sel = int(st.session_state["mes_sel"])
                mask_mes = (df_trips[col_fecha].dt.year == anio_sel) & (df_trips[col_fecha].dt.month == mes_sel)
                df_trips = df_trips[mask_mes].copy()
                st.write(f"Se usarán {df_trips.shape[0]} viajes del mes {mes_sel:02d}/{anio_sel}.")
            else:
                alert("warn", "No se encontró columna de fecha o no hay año/mes definido. Se usarán todos los viajes.")

            section_header("▸", "Vista previa viajes (después de filtro por mes)")
            st.dataframe(df_trips.head(), use_container_width=True)

            # Validaciones mínimas
            columnas_faltan = []
            if col_customer is None: columnas_faltan.append("Customer/Cliente")
            if col_trip is None: columnas_faltan.append("Trip Number/Viaje")
            if col_unit is None: columnas_faltan.append("Unit/Unidad")
            if col_trailer is None: columnas_faltan.append("Trailer/Remolque")
            if col_dist is None: columnas_faltan.append(DIST_COL_NAME)
            if CFG["usa_operador"] and col_operador is None:
                columnas_faltan.append("Operador logístico")

            if columnas_faltan:
                st.error("No se encontraron columnas necesarias en viajes: " + ", ".join(columnas_faltan))
                st.stop()

            df_trips_work = df_trips.copy()

            # Operadores excluidos: SOLO Lincoln
            if CFG["usa_operador"]:
                op_upper = df_trips_work[col_operador].astype(str).str.upper().str.strip()
                mask_excl = op_upper.isin(OPERADORES_EXCLUIR)
                df_trips_work["Excluido_por_operador"] = mask_excl
                st.write(
                    f"Viajes con operador en lista de 'excluidos': {int(mask_excl.sum())} "
                    f"de {len(df_trips_work)}."
                )
            else:
                df_trips_work["Excluido_por_operador"] = False

            # CI NO OPERATIVOS a nivel viaje
            costo_x_dist = float(st.session_state["costo_no_op_x_dist"])
            costo_x_viaje_sin = float(st.session_state["costo_no_op_x_viaje_sin"])

            has_unit = df_trips_work[col_unit].notna() & (df_trips_work[col_unit].astype(str).str.strip() != "")
            dist = pd.to_numeric(df_trips_work[col_dist], errors="coerce").fillna(0.0)

            ci_no_op = np.zeros(len(df_trips_work), dtype=float)

            idx_con_unidad = (has_unit & (dist > 0)).to_numpy()
            ci_no_op[idx_con_unidad] = costo_x_dist * dist.to_numpy()[idx_con_unidad]

            idx_sin_unidad = (~has_unit).to_numpy()
            ci_no_op[idx_sin_unidad] = costo_x_viaje_sin

            df_trips_work["CI_no_operativo"] = ci_no_op

            # CI LIGADOS A OPERACIÓN a nivel viaje
            asignaciones_df = st.session_state["asignaciones_df"].copy()
            conceptos_tipos = st.session_state["conceptos_tipos"].copy()

            tot_client_conc = (
                asignaciones_df.groupby(["Customer", "Concepto"], as_index=False)["Costo asignado"].sum()
            )
            tot_client_conc = tot_client_conc.merge(conceptos_tipos, on="Concepto", how="left")

            df_trips_work["CI_op_ligado_operacion"] = 0.0

            trailer_flag_trip = build_flag_trailer(df_trips_work[col_trailer], CFG["trailer_prefix"]).astype(bool)

            def asignar_op_por_subgrupo(df, mask_aplica, has_unit_s, dist_s, col_dest, monto):
                if monto == 0:
                    return
                mask_aplica = mask_aplica.fillna(False)
                n_total = int(mask_aplica.sum())
                if n_total == 0:
                    return

                n_u = int((mask_aplica & has_unit_s).sum())
                mask_su = mask_aplica & (~has_unit_s)
                n_su = int(mask_su.sum())

                pct_u = n_u / n_total
                pct_su = n_su / n_total

                bolsa_u = monto * pct_u
                bolsa_su = monto * pct_su

                if n_su > 0 and bolsa_su != 0:
                    df.loc[mask_su, col_dest] += (bolsa_su / n_su)

                mask_u_dist = mask_aplica & has_unit_s & (dist_s > 0)
                total_dist_u = float(dist_s.where(mask_u_dist, 0).sum())

                if total_dist_u > 0 and bolsa_u != 0:
                    costo_x = bolsa_u / total_dist_u
                    df.loc[mask_u_dist, col_dest] += costo_x * dist_s.where(mask_u_dist, 0)
                else:
                    mask_u_fallback = mask_aplica & has_unit_s
                    n_u_fallback = int(mask_u_fallback.sum())
                    if n_u_fallback > 0 and bolsa_u != 0:
                        df.loc[mask_u_fallback, col_dest] += (bolsa_u / n_u_fallback)

            for _, row in tot_client_conc.iterrows():
                cliente = str(row["Customer"])
                tipo_dist = row.get("Tipo distribución", "Volumen Viajes")
                monto_cliente = float(row["Costo asignado"]) if pd.notna(row["Costo asignado"]) else 0.0
                if monto_cliente == 0:
                    continue

                mask_base = df_trips_work[col_customer].astype(str) == cliente
                if not mask_base.any():
                    continue

                if tipo_dist == "Volumen Viajes":
                    mask_aplica = mask_base
                elif tipo_dist == "Viajes con unidad":
                    mask_aplica = mask_base & has_unit
                elif tipo_dist == "Viajes con Remolque":
                    mask_aplica = mask_base & trailer_flag_trip
                elif tipo_dist == DIST_COL_NAME:
                    mask_aplica = mask_base & has_unit
                else:
                    mask_aplica = mask_base

                asignar_op_por_subgrupo(
                    df=df_trips_work,
                    mask_aplica=mask_aplica,
                    has_unit_s=has_unit,
                    dist_s=dist,
                    col_dest="CI_op_ligado_operacion",
                    monto=monto_cliente,
                )

            df_trips_work["CI_total"] = df_trips_work["CI_no_operativo"] + df_trips_work["CI_op_ligado_operacion"]

            section_header("▸", "Vista previa con CI asignado")
            st.dataframe(df_trips_work.head(), use_container_width=True)

            st.download_button(
                "📥 Descargar viajes con CI asignado (Excel)",
                data=to_excel_bytes({"CI_por_viaje": df_trips_work}),
                file_name="viajes_con_CI_asignado.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        except Exception as e:
            st.error(f"Error procesando la base de viajes detallados: {e}")
            st.exception(e)
