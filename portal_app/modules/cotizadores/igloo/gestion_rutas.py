from ui.components import section_header, alert, divider
import os
from datetime import datetime, timezone
import re

import pandas as pd
import streamlit as st

from services.supabase_client import get_supabase_client, get_authed_client, current_user

from .helpers import (
    DEFAULTS, TIPOS_RUTA,
    cargar_datos_generales,
    safe_number, safe_float,
    calcular_sueldo_y_bono, calcular_diesel, calcular_extras,
    calcular_utilidades, mostrar_resultados_utilidad,
)


def _get_profile_name(user_id: str) -> str:
    if not user_id:
        return ""
    try:
        supabase = get_authed_client()
        res = supabase.table("profiles").select("full_name").eq("user_id", user_id).single().execute()
        return (res.data or {}).get("full_name") or ""
    except Exception:
        return ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@st.cache_data(show_spinner=False, ttl=120)
def _load_rutas_igloo_cached(table_name: str):
    supabase = get_supabase_client()
    if supabase is None:
        return pd.DataFrame()
    try:
        resp = supabase.table(table_name).select("*").order("Fecha", desc=True).execute()
        if resp.data:
            return pd.DataFrame(resp.data)
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def normalizar_texto(texto):
    """Normaliza texto para evitar duplicados."""
    if not texto:
        return ""
    texto = str(texto).upper().strip()
    texto = re.sub(r'\s+', ' ', texto)
    texto = re.sub(r'\s*,\s*', ', ', texto)
    return texto


def render():
    st.title("🗂️ Gestión de Rutas Guardadas (Igloo)")

    supabase = get_supabase_client()
    if supabase is None:
        alert("warn", "⚠️ Supabase no configurado. No se pueden cargar/editar/eliminar rutas.")
        return

    u = current_user() or {}
    user_id = u.get("id") or u.get("sub") or ""
    nombre_usuario = _get_profile_name(user_id) or u.get("email") or "Desconocido"

    TABLE_RUTAS = "Rutas"

    c1, c2 = st.columns([1, 3])
    with c1:
        if st.button("🔄 Recargar rutas", key="igloo_gestion_reload"):
            _load_rutas_igloo_cached.clear()
            st.rerun()
    with c2:
        st.caption("Carga cacheada 2 min. Usa 'Recargar' si acabas de guardar/editar algo.")

    valores = cargar_datos_generales()
    df = _load_rutas_igloo_cached(TABLE_RUTAS)

    if df.empty:
        alert("info", "No hay rutas guardadas aún.")
        return

    from io import BytesIO

    def _filtrar_rutas(df, prefix_key):
        with st.expander("🔍 Filtros de búsqueda (opcional)", expanded=False):
            fc1, fc2, fc3, fc4, fc5 = st.columns(5)

            with fc1:
                tipos_disp = ["Todos"] + sorted(df["Tipo"].dropna().unique().tolist())
                filtro_tipo = st.selectbox("Tipo", tipos_disp, key=f"{prefix_key}_ftipo")

            with fc2:
                clientes_disp = ["Todos"] + sorted(df["Cliente"].dropna().astype(str).unique().tolist())
                filtro_cliente = st.selectbox("Cliente", clientes_disp, key=f"{prefix_key}_fcliente")

            with fc3:
                filtro_origen = st.text_input("Origen contiene", key=f"{prefix_key}_forigen")

            with fc4:
                filtro_destino = st.text_input("Destino contiene", key=f"{prefix_key}_fdestino")

            with fc5:
                filtro_id = st.text_input("ID Ruta", key=f"{prefix_key}_fid", placeholder="IG000123")

        resultado = df.copy()

        if filtro_tipo != "Todos":
            resultado = resultado[resultado["Tipo"] == filtro_tipo]

        if filtro_cliente != "Todos":
            resultado = resultado[resultado["Cliente"].astype(str) == filtro_cliente]

        if filtro_origen.strip():
            resultado = resultado[resultado["Origen"].astype(str).str.contains(filtro_origen.strip(), case=False, na=False)]

        if filtro_destino.strip():
            resultado = resultado[resultado["Destino"].astype(str).str.contains(filtro_destino.strip(), case=False, na=False)]

        if filtro_id.strip():
            resultado = resultado[resultado["ID_Ruta"].astype(str).str.contains(filtro_id.strip(), case=False, na=False)]

        return resultado


    def _to_excel_bytes(df_exportar):
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df_exportar.to_excel(writer, index=False, sheet_name="Rutas")
        output.seek(0)
        return output.getvalue()


    # ══════════════════════════════════════════════════════════════
    # TABLA DE RUTAS REGISTRADAS
    # ══════════════════════════════════════════════════════════════
    section_header("📋", "Rutas Registradas")

    df_filtrado_tabla = _filtrar_rutas(df, "gestion_tabla")

    columnas_orden = [
        "ID_Ruta", "Fecha", "Tipo", "Cliente", "Origen", "Destino", "Modo de Viaje",
        "KM", "Moneda", "Ingreso_Original", "Tipo de cambio", "Ingreso Flete",
        "Moneda_Cruce", "Cruce_Original", "Tipo cambio Cruce", "Ingreso Cruce",
        "Moneda Costo Cruce", "Costo Cruce", "Costo Cruce Convertido",
        "Ingreso Total", "Pago por KM", "Sueldo_Operador", "Bono", "Casetas",
        "Horas_Termo", "Lavado_Termo", "Movimiento_Local", "Puntualidad",
        "Pension", "Estancia", "Fianza_Termo", "Renta_Termo",
        "Pistas_Extra", "Stop", "Falso", "Gatas", "Accesorios", "Guias",
        "Costo_Diesel_Camion", "Costo_Diesel_Termo", "Costo_Extras",
        "Costo_Total_Ruta", "Costos_Indirectos", "Utilidad_Bruta", "Utilidad_Neta",
        "Porcentaje_Utilidad_Bruta", "Porcentaje_Utilidad_Neta",
        "Modo_Pago_Dom", "Extras_Cobrados", "created_by", "created_at",
        "updated_by", "updated_at"
    ]

    columnas_disponibles = [col for col in columnas_orden if col in df_filtrado_tabla.columns]
    df_tabla = df_filtrado_tabla[columnas_disponibles].copy()

    for col in df_tabla.columns:
        if df_tabla[col].dtype in ['float64', 'int64']:
            df_tabla[col] = df_tabla[col].round(2)

    st.dataframe(
        df_tabla,
        use_container_width=True,
        hide_index=True,
    )

    st.caption(f"Total de rutas mostradas: {len(df_tabla)} de {len(df)}")

    excel_data = _to_excel_bytes(df_tabla)

    st.download_button(
        label="📥 Descargar rutas en Excel (.xlsx)",
        data=excel_data,
        file_name=f"rutas_filtradas_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    # ══════════════════════════════════════════════════════════════
    # ELIMINAR RUTAS
    # ══════════════════════════════════════════════════════════════
    divider()
    section_header("🗑️", "Eliminar rutas")

    # FILTROS PARA ELIMINAR
    with st.expander("🔍 Filtros de búsqueda (opcional)", expanded=False):
        fcols_elim = st.columns(5)
        
        with fcols_elim[0]:
            tipos_unicos = ["Todos"] + sorted(df["Tipo"].dropna().unique().tolist())
            filtro_tipo_elim = st.selectbox("Tipo", tipos_unicos, key="elim_filtro_tipo")
        
        with fcols_elim[1]:
            clientes_unicos = ["Todos"] + sorted(df["Cliente"].dropna().unique().tolist())
            filtro_cliente_elim = st.selectbox("Cliente", clientes_unicos, key="elim_filtro_cliente")
        
        with fcols_elim[2]:
            filtro_origen_elim = st.text_input(
                "Origen contiene",
                key="elim_filtro_origen",
                placeholder="Ej: LAREDO"
            )
        
        with fcols_elim[3]:
            filtro_destino_elim = st.text_input(
                "Destino contiene",
                key="elim_filtro_destino",
                placeholder="Ej: MONTERREY"
            )
        
        with fcols_elim[4]:
            filtro_id_elim = st.text_input(
                "ID Ruta",
                key="elim_filtro_id",
                placeholder="IG000508"
            )

    # Aplicar filtros para eliminar
    df_filtrado_elim = df.copy()

    if filtro_tipo_elim != "Todos":
        df_filtrado_elim = df_filtrado_elim[df_filtrado_elim["Tipo"] == filtro_tipo_elim]

    if filtro_cliente_elim != "Todos":
        df_filtrado_elim = df_filtrado_elim[df_filtrado_elim["Cliente"] == filtro_cliente_elim]

    if filtro_origen_elim:
        df_filtrado_elim = df_filtrado_elim[
            df_filtrado_elim["Origen"].str.contains(filtro_origen_elim, case=False, na=False)
        ]

    if filtro_destino_elim:
        df_filtrado_elim = df_filtrado_elim[
            df_filtrado_elim["Destino"].str.contains(filtro_destino_elim, case=False, na=False)
        ]

    if filtro_id_elim:
        df_filtrado_elim = df_filtrado_elim[
            df_filtrado_elim["ID_Ruta"].str.contains(filtro_id_elim, case=False, na=False)
        ]

    if df_filtrado_elim.empty:
        alert("info", "No hay rutas que coincidan con los filtros.")
    else:
        opciones_eliminar = df_filtrado_elim.apply(
            lambda row: f"{row['ID_Ruta']} | {row['Fecha']} | {row['Tipo']} | {row['Cliente']} | {row['Origen']} → {row['Destino']}",
            axis=1,
        ).tolist()

        ruta_eliminar = st.selectbox(
            f"Selecciona ruta(s) a eliminar ({len(df_filtrado_elim)} encontrada(s))",
            options=[""] + opciones_eliminar,
            key="igloo_ruta_eliminar",
        )

        if ruta_eliminar:
            id_ruta_eliminar = ruta_eliminar.split(" | ")[0]
            st.warning(f"⚠️ ¿Estás seguro de eliminar la ruta **{id_ruta_eliminar}**?")
            
            if st.button("🗑️ Confirmar Eliminación", type="primary", key="confirmar_eliminar"):
                try:
                    supabase.table(TABLE_RUTAS).delete().eq("ID_Ruta", id_ruta_eliminar).execute()
                    st.success(f"✅ Ruta {id_ruta_eliminar} eliminada exitosamente.")
                    _load_rutas_igloo_cached.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error al eliminar ruta: {e}")

    # ══════════════════════════════════════════════════════════════
    # EDITAR RUTAS
    # ══════════════════════════════════════════════════════════════
    divider()
    section_header("✏️", "Editar ruta")

    # FILTROS PARA EDITAR
    with st.expander("🔍 Filtros de búsqueda (opcional)", expanded=False):
        fcols_edit = st.columns(5)
        
        with fcols_edit[0]:
            filtro_tipo_edit = st.selectbox("Tipo", tipos_unicos, key="edit_filtro_tipo")
        
        with fcols_edit[1]:
            filtro_cliente_edit = st.selectbox("Cliente", clientes_unicos, key="edit_filtro_cliente")
        
        with fcols_edit[2]:
            filtro_origen_edit = st.text_input(
                "Origen contiene",
                key="edit_filtro_origen",
                placeholder="Ej: LAREDO"
            )
        
        with fcols_edit[3]:
            filtro_destino_edit = st.text_input(
                "Destino contiene",
                key="edit_filtro_destino",
                placeholder="Ej: MONTERREY"
            )
        
        with fcols_edit[4]:
            filtro_id_edit = st.text_input(
                "ID Ruta",
                key="edit_filtro_id",
                placeholder="IG000508"
            )

    # Aplicar filtros para editar
    df_filtrado_edit = df.copy()

    if filtro_tipo_edit != "Todos":
        df_filtrado_edit = df_filtrado_edit[df_filtrado_edit["Tipo"] == filtro_tipo_edit]

    if filtro_cliente_edit != "Todos":
        df_filtrado_edit = df_filtrado_edit[df_filtrado_edit["Cliente"] == filtro_cliente_edit]

    if filtro_origen_edit:
        df_filtrado_edit = df_filtrado_edit[
            df_filtrado_edit["Origen"].str.contains(filtro_origen_edit, case=False, na=False)
        ]

    if filtro_destino_edit:
        df_filtrado_edit = df_filtrado_edit[
            df_filtrado_edit["Destino"].str.contains(filtro_destino_edit, case=False, na=False)
        ]

    if filtro_id_edit:
        df_filtrado_edit = df_filtrado_edit[
            df_filtrado_edit["ID_Ruta"].str.contains(filtro_id_edit, case=False, na=False)
        ]

    st.write("Selecciona la ruta a editar")

    # Opciones con formato: ID | Fecha | Tipo | Cliente | Ruta
    opciones_editar = df_filtrado_edit.apply(
        lambda row: f"{row['ID_Ruta']} | {row['Fecha']} | {row['Tipo']} | {row['Cliente']} | {row['Origen']} → {row['Destino']}",
        axis=1,
    ).tolist()

    ruta_seleccionada = st.selectbox(
        "Selecciona ruta",
        options=[""] + opciones_editar,
        key="igloo_ruta_editar",
        label_visibility="collapsed"
    )

    if not ruta_seleccionada:
        alert("info", "👆 Selecciona una ruta para editarla")
        return

    id_ruta = ruta_seleccionada.split(" | ")[0]
    ruta = df_filtrado_edit[df_filtrado_edit["ID_Ruta"] == id_ruta].iloc[0].to_dict()

    st.caption(f"🖊️ Creada por: {ruta.get('created_by', 'N/A')} el {ruta.get('created_at', 'N/A')}")

    tipo_index = TIPOS_RUTA.index(ruta["Tipo"]) if ruta["Tipo"] in TIPOS_RUTA else 0

    if "igloo_revisar_edicion" not in st.session_state:
        st.session_state.igloo_revisar_edicion = False

    with st.form("igloo_editar_ruta_form"):
        # ══════════════════════════════════════════════════════
        # ✅ CORRECCIÓN: USAR EXACTAMENTE EL MISMO EXPANDER QUE CAPTURA
        # ══════════════════════════════════════════════════════
        with st.expander("⚙️ Configurar Datos Generales", expanded=False):
            st.caption("Estos valores se guardaron originalmente con esta ruta")
            
            # ✅ Usar el mismo código que captura_rutas__3_.py
            col1, col2, col3 = st.columns(3)
            claves = list(DEFAULTS.keys())
            
            for i, key in enumerate(claves):
                col = [col1, col2, col3][i % 3]
                # ✅ CORRECCIÓN: Primero buscar en la ruta guardada, luego en valores generales
                valores[key] = col.number_input(
                    key,
                    value=float(ruta.get(key, valores.get(key, DEFAULTS[key]))),
                    step=0.1,
                    key=f"igloo_edit_gen_{key}",
                )
        
        # ══════════════════════════════════════════════════════
        # CAMPOS DE EDICIÓN
        # ══════════════════════════════════════════════════════
        col1, col2 = st.columns(2)

        with col1:
            fecha = st.date_input("Fecha", ruta.get("Fecha"))
            tipo = st.selectbox("Tipo", TIPOS_RUTA, index=tipo_index)
            cliente = st.text_input("Cliente", value=str(ruta.get("Cliente", "")), placeholder="NOMBRE DE LA EMPRESA")
            origen = st.text_input("Origen", value=str(ruta.get("Origen", "")), placeholder="CIUDAD, ESTADO")
            destino = st.text_input("Destino", value=str(ruta.get("Destino", "")), placeholder="CIUDAD, ESTADO")
            modo_viaje = st.selectbox(
                "Modo de Viaje", ["Operador", "Team"],
                index=["Operador", "Team"].index(str(ruta.get("Modo de Viaje", "Operador"))),
            )
            km = st.number_input("Kilómetros", min_value=0.0, value=float(safe_number(ruta.get("KM"))))
            moneda_ingreso = st.selectbox("Moneda Flete", ["MXP", "USD"], index=["MXP", "USD"].index(str(ruta.get("Moneda", "MXP"))))
            ingreso_flete = st.number_input("Ingreso Flete", min_value=0.0, value=float(safe_number(ruta.get("Ingreso_Original"))))
            moneda_cruce = st.selectbox("Moneda Cruce", ["MXP", "USD"], index=["MXP", "USD"].index(str(ruta.get("Moneda_Cruce", "MXP"))))
            ingreso_cruce = st.number_input("Ingreso Cruce", min_value=0.0, value=float(safe_number(ruta.get("Cruce_Original"))))

        with col2:
            moneda_costo_cruce = st.selectbox("Moneda Costo Cruce", ["MXP", "USD"], index=["MXP", "USD"].index(str(ruta.get("Moneda Costo Cruce", "MXP"))))
            costo_cruce = st.number_input("Costo Cruce", min_value=0.0, value=float(safe_number(ruta.get("Costo Cruce"))))
            horas_termo = st.number_input("Horas Termo", min_value=0.0, value=float(safe_number(ruta.get("Horas_Termo"))))
            lavado_termo = st.number_input("Lavado Termo (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Lavado_Termo"))))
            movimiento_local = st.number_input("Movimiento Local (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Movimiento_Local"))))
            puntualidad_original = st.number_input("Puntualidad (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Puntualidad", 0)) / (2 if ruta.get("Modo de Viaje") == "Team" else 1)))
            pension = st.number_input("Pensión (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Pension"))))
            estancia = st.number_input("Estancia (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Estancia"))))
            fianza_termo = st.number_input("Fianza Termo (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Fianza_Termo"))))
            renta_termo = st.number_input("Renta Termo (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Renta_Termo"))))
            casetas = st.number_input("Casetas (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Casetas"))))

            if tipo == "DOM MEX":
                modo_pago_actual = ruta.get("Modo_Pago_Dom", "km")
                modo_pago_dom = st.selectbox(
                    "Modo de pago al operador (DOM MEX)",
                    ["km", "fijo"],
                    format_func=lambda x: "Por kilómetro" if x == "km" else "Pago fijo",
                    index=["km", "fijo"].index(modo_pago_actual),
                )
            else:
                modo_pago_dom = "km"

        divider()
        section_header("🧾", "Otros costos")

        col3, col4 = st.columns(2)
        with col3:
            pistas_extra = st.number_input("Pistas Extra (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Pistas_Extra"))))
            stop = st.number_input("Stop (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Stop"))))
            falso = st.number_input("Falso (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Falso"))))
            costos_extras_cobrados = st.checkbox(
                "✅ ¿Costos Extras fueron cobrados al cliente?",
                value=bool(ruta.get("Extras_Cobrados", False)),
            )
        with col4:
            gatas = st.number_input("Gatas (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Gatas"))))
            accesorios = st.number_input("Accesorios (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Accesorios"))))
            guias = st.number_input("Guías (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Guias"))))

        divider()
        motivo = st.text_area(
            "📝 Motivo de la modificación (obligatorio)",
            placeholder="Ej: Corrección de kilómetros, actualización de costos, etc.",
            key="igloo_motivo_edicion"
        )

        revisar = st.form_submit_button("🔍 Revisar Cambios")

    # ══════════════════════════════════════════════════════════════
    # CÁLCULOS AL REVISAR
    # ══════════════════════════════════════════════════════════════
    if revisar:
        if not motivo or not motivo.strip():
            alert("error", "⚠️ Debes especificar un motivo para la modificación.")
            return

        # NORMALIZAR texto antes de guardar
        cliente_norm = normalizar_texto(cliente)
        origen_norm = normalizar_texto(origen)
        destino_norm = normalizar_texto(destino)

        st.session_state.igloo_revisar_edicion = True

        st.session_state.igloo_datos_edicion = {
            "id_ruta": id_ruta,
            "fecha": fecha,
            "tipo": tipo,
            "cliente": cliente_norm,
            "origen": origen_norm,
            "destino": destino_norm,
            "modo_viaje": modo_viaje,
            "km": km,
            "moneda_ingreso": moneda_ingreso,
            "ingreso_flete": ingreso_flete,
            "moneda_cruce": moneda_cruce,
            "ingreso_cruce": ingreso_cruce,
            "moneda_costo_cruce": moneda_costo_cruce,
            "costo_cruce": costo_cruce,
            "horas_termo": horas_termo,
            "lavado_termo": lavado_termo,
            "movimiento_local": movimiento_local,
            "puntualidad": puntualidad_original,
            "pension": pension,
            "estancia": estancia,
            "fianza_termo": fianza_termo,
            "renta_termo": renta_termo,
            "casetas": casetas,
            "pistas_extra": pistas_extra,
            "stop": stop,
            "falso": falso,
            "gatas": gatas,
            "accesorios": accesorios,
            "guias": guias,
            "costos_extras_cobrados": costos_extras_cobrados,
            "modo_pago_dom": modo_pago_dom,
            "motivo": motivo,
        }

        factor = 2 if modo_viaje == "Team" else 1
        puntualidad_val = puntualidad_original * factor

        extras = calcular_extras(
            lavado_termo, movimiento_local, puntualidad_val, pension, estancia,
            fianza_termo, renta_termo, pistas_extra, stop, falso,
            gatas, accesorios, guias,
        )

        tc_usd = float(valores.get("Tipo de cambio USD", 19.5))
        ingreso_total = ingreso_flete * (tc_usd if moneda_ingreso == "USD" else 1)
        ingreso_total += ingreso_cruce * (tc_usd if moneda_cruce == "USD" else 1)
        if costos_extras_cobrados:
            ingreso_total += extras

        costo_cruce_convertido = costo_cruce * (tc_usd if moneda_costo_cruce == "USD" else 1)
        diesel_camion, diesel_termo = calcular_diesel(km, horas_termo, valores)
        pago_km, sueldo, bono = calcular_sueldo_y_bono(tipo, km, modo_viaje, valores, modo_pago_dom)

        costo_total = diesel_camion + diesel_termo + sueldo + bono + casetas + extras + costo_cruce_convertido

        util = calcular_utilidades(ingreso_total, costo_total, tipo)

        st.session_state.igloo_calc_edicion = {
            "tipo_cambio_flete": tc_usd if moneda_ingreso == "USD" else 1.0,
            "tipo_cambio_cruce": tc_usd if moneda_cruce == "USD" else 1.0,
            "tipo_cambio_costo_cruce": tc_usd if moneda_costo_cruce == "USD" else 1.0,
            "ingreso_flete_convertido": ingreso_flete * (tc_usd if moneda_ingreso == "USD" else 1),
            "ingreso_cruce_convertido": ingreso_cruce * (tc_usd if moneda_cruce == "USD" else 1),
            "costo_cruce_convertido": costo_cruce_convertido,
            "ingreso_total": ingreso_total,
            "costo_diesel_camion": diesel_camion,
            "costo_diesel_termo": diesel_termo,
            "pago_km": pago_km,
            "sueldo": sueldo,
            "bono": bono,
            "puntualidad_val": puntualidad_val,
            "extras": extras,
            "costo_total": costo_total,
            "costos_indirectos": util["costos_indirectos"],
            "utilidad_bruta": util["utilidad_bruta"],
            "utilidad_neta": util["utilidad_neta"],
            "porcentaje_bruta": util["porcentaje_bruta"],
            "porcentaje_neta": util["porcentaje_neta"],
        }

        # Mostrar resumen
        mostrar_resultados_utilidad(
            st, ingreso_total, costo_total,
            util["utilidad_bruta"], util["costos_indirectos"],
            util["utilidad_neta"], util["porcentaje_bruta"], util["porcentaje_neta"],
            tipo=tipo,
        )

    # ══════════════════════════════════════════════════════════════
    # GUARDAR CAMBIOS (después de revisar)
    # ══════════════════════════════════════════════════════════════
    if st.session_state.get("igloo_revisar_edicion", False):
        if st.button("💾 Guardar Cambios", key="igloo_confirmar_edicion"):
            d = st.session_state.get("igloo_datos_edicion", {})
            calc = st.session_state.get("igloo_calc_edicion", {})
            
            if not d:
                alert("error", "No hay datos de edición.")
                return

            # Obtener historial anterior
            historial_anterior = ruta.get("historial", [])
            if historial_anterior is None:
                historial_anterior = []

            # Crear entrada de historial con el ESTADO ANTERIOR
            nueva_entrada_historial = {
                "timestamp": _now_iso(),
                "usuario": nombre_usuario,
                "motivo": d["motivo"],
                "cambios_anteriores": {
                    "Cliente": ruta.get("Cliente"),
                    "Origen": ruta.get("Origen"),
                    "Destino": ruta.get("Destino"),
                    "KM": ruta.get("KM"),
                    "Ingreso_Original": ruta.get("Ingreso_Original"),
                    "Cruce_Original": ruta.get("Cruce_Original"),
                    "Costo_Total_Ruta": ruta.get("Costo_Total_Ruta"),
                    "Utilidad_Neta": ruta.get("Utilidad_Neta"),
                }
            }
            historial_actualizado = historial_anterior + [nueva_entrada_historial]

            # Construir ruta actualizada con los datos del session_state
            ruta_actualizada = {
                "Fecha": str(d["fecha"]),
                "Tipo": d["tipo"],
                "Cliente": d["cliente"],
                "Origen": d["origen"],
                "Destino": d["destino"],
                "Modo de Viaje": d["modo_viaje"],
                "KM": d["km"],
                "Moneda": d["moneda_ingreso"],
                "Ingreso_Original": d["ingreso_flete"],
                "Tipo de cambio": calc.get("tipo_cambio_flete"),
                "Ingreso Flete": calc.get("ingreso_flete_convertido"),
                "Moneda_Cruce": d["moneda_cruce"],
                "Cruce_Original": d["ingreso_cruce"],
                "Tipo cambio Cruce": calc.get("tipo_cambio_cruce"),
                "Ingreso Cruce": calc.get("ingreso_cruce_convertido"),
                "Moneda Costo Cruce": d["moneda_costo_cruce"],
                "Costo Cruce": d["costo_cruce"],
                "Costo Cruce Convertido": calc.get("costo_cruce_convertido"),
                "Ingreso Total": calc.get("ingreso_total"),
                "Pago por KM": calc.get("pago_km"),
                "Sueldo_Operador": calc.get("sueldo"),
                "Bono": calc.get("bono"),
                "Casetas": d["casetas"],
                "Horas_Termo": d["horas_termo"],
                "Lavado_Termo": d["lavado_termo"],
                "Movimiento_Local": d["movimiento_local"],
                "Puntualidad": calc.get("puntualidad_val"),
                "Pension": d["pension"],
                "Estancia": d["estancia"],
                "Fianza_Termo": d["fianza_termo"],
                "Renta_Termo": d["renta_termo"],
                "Pistas_Extra": d["pistas_extra"],
                "Stop": d["stop"],
                "Falso": d["falso"],
                "Gatas": d["gatas"],
                "Accesorios": d["accesorios"],
                "Guias": d["guias"],
                "Costo_Diesel_Camion": calc.get("costo_diesel_camion"),
                "Costo_Diesel_Termo": calc.get("costo_diesel_termo"),
                "Costo_Extras": calc.get("extras"),
                "Costo_Total_Ruta": calc.get("costo_total"),
                "Costos_Indirectos": calc.get("costos_indirectos"),
                "Utilidad_Bruta": calc.get("utilidad_bruta"),
                "Utilidad_Neta": calc.get("utilidad_neta"),
                "Porcentaje_Utilidad_Bruta": calc.get("porcentaje_bruta"),
                "Porcentaje_Utilidad_Neta": calc.get("porcentaje_neta"),
                "Modo_Pago_Dom": d.get("modo_pago_dom", "km"),
                # ✅ GUARDAR LOS DATOS GENERALES CON LA RUTA
                "Costo Diesel": float(valores.get("Costo Diesel", 24.0)),
                "Rendimiento Camion": float(valores.get("Rendimiento Camion", 2.5)),
                "Rendimiento Termo": float(valores.get("Rendimiento Termo", 3.0)),
                "Extras_Cobrados": bool(d.get("costos_extras_cobrados", False)),
                "updated_by": nombre_usuario,
                "updated_at": _now_iso(),
                "historial": historial_actualizado,
            }

            try:
                supabase.table(TABLE_RUTAS).update(ruta_actualizada).eq("ID_Ruta", d["id_ruta"]).execute()
                
                # Guardar ID para mostrar modal
                st.session_state.igloo_ruta_editada_id = d["id_ruta"]
                st.session_state.igloo_mostrar_modal_edicion = True
                
                _load_rutas_igloo_cached.clear()
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ Error al actualizar la ruta: {e}")
                st.exception(e)

    # ── Mostrar historial de modificaciones ──────────────────────
    if ruta_seleccionada:
        divider()
        section_header("📝", "Historial de modificaciones de esta ruta")
        
        historial = ruta.get("historial", [])
        
        if historial and len(historial) > 0:
            for i, entrada in enumerate(reversed(historial), 1):
                with st.expander(f"Modificación #{len(historial) - i + 1} - {entrada.get('timestamp', 'N/A')[:10]}", expanded=False):
                    st.write(f"**Usuario:** {entrada.get('usuario', 'N/A')}")
                    st.write(f"**Fecha/Hora:** {entrada.get('timestamp', 'N/A')}")
                    st.write(f"**Motivo:** {entrada.get('motivo', 'N/A')}")
                    
                    if "cambios_anteriores" in entrada:
                        st.write("**Valores anteriores:**")
                        cambios = entrada["cambios_anteriores"]
                        col_hist1, col_hist2 = st.columns(2)
                        with col_hist1:
                            st.caption(f"Cliente: {cambios.get('Cliente', 'N/A')}")
                            st.caption(f"Origen: {cambios.get('Origen', 'N/A')}")
                            st.caption(f"Destino: {cambios.get('Destino', 'N/A')}")
                            st.caption(f"KM: {cambios.get('KM', 'N/A')}")
                        with col_hist2:
                            st.caption(f"Ingreso Original: {cambios.get('Ingreso_Original', 'N/A')}")
                            st.caption(f"Cruce Original: {cambios.get('Cruce_Original', 'N/A')}")
                            st.caption(f"Costo Total: {cambios.get('Costo_Total_Ruta', 'N/A')}")
                            st.caption(f"Utilidad Neta: {cambios.get('Utilidad_Neta', 'N/A')}")
        else:
            alert("info", "Esta ruta no tiene modificaciones registradas aún.")

    # ── Modal de confirmación de edición ──────────────────────────
    @st.dialog("✅ Ruta Actualizada Exitosamente", width="small")
    def mostrar_modal_edicion(id_ruta):
        alert("success", "**¡La ruta se actualizó correctamente!**")
        st.info(f"### 🆔 ID de la ruta\n`{id_ruta}`")
        st.caption("Los cambios se han guardado en el historial")
        
        if st.button("✅ Aceptar", type="primary", use_container_width=True):
            st.session_state.pop("igloo_ruta_editada_id", None)
            st.session_state.pop("igloo_mostrar_modal_edicion", None)
            st.session_state.pop("igloo_datos_edicion", None)
            st.session_state.pop("igloo_calc_edicion", None)
            st.session_state.igloo_revisar_edicion = False
            st.rerun()
    
    if st.session_state.get("igloo_mostrar_modal_edicion") and st.session_state.get("igloo_ruta_editada_id"):
        mostrar_modal_edicion(st.session_state.igloo_ruta_editada_id)
