from ui.components import section_header, alert, divider
"""
gestion_rutas.py – Lincoln Freight (USA/MX)
Vista tabular, edición con historial y exportación
Versión actualizada con estructura Igloo + formulario Lincoln 2026
"""

import os
from datetime import datetime, timezone
from io import BytesIO
import re

import pandas as pd
import streamlit as st

from services.supabase_client import get_supabase_client, get_authed_client, current_user
from ._shared import (
    TABLE_RUTAS, TIPOS_RUTA, EXTRAS_USA,
    DEFAULTS, cargar_datos_generales,
    limpiar_fila_json, safe,
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


def normalizar_texto(texto):
    if not texto:
        return ""
    texto = str(texto).upper().strip()
    texto = re.sub(r'\s+', ' ', texto)
    texto = re.sub(r'\s*,\s*', ', ', texto)
    return texto


@st.cache_data(show_spinner=False, ttl=120)
def _load_rutas_lincoln_cached(table_name: str):
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


def obtener_config_tipo_ruta(tipo_ruta: str) -> dict:
    configs = {
        "NB": {"parte_usa": True, "cruce": "opcional", "parte_mx": False},
        "SB": {"parte_usa": True, "cruce": "opcional", "parte_mx": False},
        "D2DNB": {"parte_usa": True, "cruce": True, "parte_mx": True},
        "D2DSB": {"parte_usa": True, "cruce": True, "parte_mx": True},
        "DOM USA": {"parte_usa": True, "cruce": False, "parte_mx": False},
        "DOM MEX": {"parte_usa": False, "cruce": False, "parte_mx": True}
    }
    return configs.get(tipo_ruta, configs["NB"])


def calcular_ruta_lincoln(millas_usa, millas_vacias, ingreso_x_milla_usd, fuel_surcharge_usd,
                          ingreso_cruce_usd, aplica_cruce, modo_viaje, tipo_cruce, tipo_carga_cruce,
                          costo_cruce_tercero_usd, ingreso_flete_mx_mxp, costo_flete_mx_mxp,
                          linea_mx, otros_cargos, otros_cargos_pagados, valores):
    """Calcula todos los valores de la ruta"""
    tc = float(valores.get("Tipo de Cambio USD/MXP", 18.5))
    mpg = float(valores.get("Truck Performance (mpg)", 7.0))
    diesel_precio = float(valores.get("Diesel Price ($/gal)", 3.60))
    isr_imss = float(valores.get("ISR/IMSS", 462.66))
    bono_por_milla = float(valores.get("Bono por milla cargada", 0.01))
    
    # Ingresos USA
    ingreso_flete_usa = ingreso_x_milla_usd * millas_usa
    ingreso_fuel_usa = fuel_surcharge_usd * millas_usa
    ingreso_total_usa = ingreso_flete_usa + ingreso_fuel_usa
    
    # Otros Cargos
    otros_cargos_ingreso = sum(otros_cargos.values())
    otros_cargos_costo = sum(
        monto for nombre, monto in otros_cargos.items() 
        if otros_cargos_pagados.get(nombre, False) and monto > 0
    )
    
    # Sueldo operador
    if modo_viaje == "Team":
        cxm_cargado = float(valores.get("CXM Team USA", 0.30))
        cxm_vacio = float(valores.get("CXM Team USA (Empty)", 0.25))
        factor = 2
    else:
        cxm_cargado = float(valores.get("CXM Operador USA", 0.48))
        cxm_vacio = float(valores.get("CXM Operador USA (Empty)", 0.30))
        factor = 1
    
    sueldo_base = (millas_usa * cxm_cargado + millas_vacias * cxm_vacio) * factor
    bono_millas = (millas_usa * bono_por_milla) * factor
    sueldo_usa = sueldo_base + bono_millas
    
    # Diesel
    diesel_usa = ((millas_usa + millas_vacias) / mpg) * diesel_precio if mpg else 0.0
    
    # Cruce
    if aplica_cruce:
        if tipo_cruce == "Propio":
            if tipo_carga_cruce == "Cargado":
                costo_cruce = float(valores.get("Cruce Propio (Cargado)", 50.0))
            else:
                costo_cruce = float(valores.get("Cruce Propio (Vacío)", 30.0))
        else:
            costo_cruce = costo_cruce_tercero_usd
    else:
        costo_cruce = 0.0
        ingreso_cruce_usd = 0.0
    
    # Tramo MX
    ingreso_mx_usd = ingreso_flete_mx_mxp / tc if tc else 0.0
    costo_mx_usd = costo_flete_mx_mxp / tc if tc else 0.0
    
    # TOTALES
    ingreso_total = ingreso_total_usa + ingreso_cruce_usd + ingreso_mx_usd + otros_cargos_ingreso
    costo_directo = sueldo_usa + diesel_usa + costo_cruce + costo_mx_usd + otros_cargos_costo
    costo_directo_total = costo_directo + isr_imss
    
    utilidad_bruta = ingreso_total - costo_directo_total
    pct_bruta = (utilidad_bruta / ingreso_total * 100) if ingreso_total > 0 else 0.0
    
    costos_ind = ingreso_total * 0.42
    utilidad_neta = utilidad_bruta - costos_ind
    pct_neta = (utilidad_neta / ingreso_total * 100) if ingreso_total > 0 else 0.0
    
    return {
        "ingreso_flete_usa": ingreso_flete_usa,
        "ingreso_fuel_usa": ingreso_fuel_usa,
        "ingreso_total_usa": ingreso_total_usa,
        "ingreso_cruce": ingreso_cruce_usd,
        "ingreso_mx_usd": ingreso_mx_usd,
        "otros_cargos_ingreso": otros_cargos_ingreso,
        "ingreso_total": ingreso_total,
        "sueldo_base": sueldo_base,
        "bono_millas": bono_millas,
        "sueldo_usa": sueldo_usa,
        "diesel_usa": diesel_usa,
        "costo_cruce": costo_cruce,
        "costo_mx_usd": costo_mx_usd,
        "otros_cargos_costo": otros_cargos_costo,
        "isr_imss": isr_imss,
        "costo_directo_total": costo_directo_total,
        "utilidad_bruta": utilidad_bruta,
        "pct_bruta": pct_bruta,
        "costos_ind": costos_ind,
        "utilidad_neta": utilidad_neta,
        "pct_neta": pct_neta,
        "tc": tc,
        "mpg": mpg,
        "diesel": diesel_precio,
        "cxm_cargado": cxm_cargado,
        "cxm_vacio": cxm_vacio,
        "bono_por_milla": bono_por_milla,
    }


def _to_excel_bytes(df_exportar):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_exportar.to_excel(writer, index=False, sheet_name="Rutas Lincoln")
    output.seek(0)
    return output.getvalue()


def render():
    st.title("🗂️ Gestión de Rutas Guardadas (Lincoln)")

    supabase = get_supabase_client()
    if supabase is None:
        alert("warn", "⚠️ Supabase no configurado.")
        return

    u = current_user() or {}
    user_id = u.get("id") or u.get("sub") or ""
    nombre_usuario = _get_profile_name(user_id) or u.get("email") or "Desconocido"

    c1, c2 = st.columns([1, 3])
    with c1:
        if st.button("🔄 Recargar rutas", key="lincoln_gestion_reload"):
            _load_rutas_lincoln_cached.clear()
            st.rerun()
    with c2:
        st.caption("Carga cacheada 2 min. Usa 'Recargar' si acabas de guardar/editar algo.")

    valores = cargar_datos_generales()
    df = _load_rutas_lincoln_cached(TABLE_RUTAS)

    if df.empty:
        alert("info", "No hay rutas guardadas aún.")
        return

    # ══════════════════════════════════════════════════════════════
    # FILTROS
    # ══════════════════════════════════════════════════════════════
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
                filtro_id = st.text_input("ID Ruta", key=f"{prefix_key}_fid", placeholder="LN000123")

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

    # ══════════════════════════════════════════════════════════════
    # TABLA DE RUTAS
    # ══════════════════════════════════════════════════════════════
    section_header("📋", "Rutas Registradas")

    df_filtrado_tabla = _filtrar_rutas(df, "gestion_tabla")

    columnas_orden = [
        "ID_Ruta", "Fecha", "Tipo", "Cliente", "Modo_Viaje", "Origen", "Destino",
        "Millas_USA", "Millas_Vacias", "CXM_Flete", "CXM_Fuel",
        "Ingreso Total", "Sueldo_Operador", "Diesel_USA",
        "Costo_Total_Ruta", "Utilidad_Bruta", "Pct_Utilidad_Bruta",
        "Utilidad_Neta", "Pct_Utilidad_Neta",
        "created_by", "created_at", "updated_by", "updated_at"
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
        file_name=f"rutas_lincoln_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    # ══════════════════════════════════════════════════════════════
    # EDITAR RUTA
    # ══════════════════════════════════════════════════════════════
    divider()
    section_header("✏️", "Editar Ruta Existente")

    df_filtrado_edicion = _filtrar_rutas(df, "gestion_edicion")
    
    if df_filtrado_edicion.empty:
        alert("info", "No hay rutas con los filtros aplicados.")
        return

    ids_disponibles = sorted(df_filtrado_edicion["ID_Ruta"].dropna().astype(str).unique().tolist(), reverse=True)
    ruta_seleccionada = st.selectbox(
        "Selecciona ruta a editar:",
        ids_disponibles,
        key="lincoln_ruta_editar_select"
    )

    if not ruta_seleccionada:
        return

    ruta = df[df["ID_Ruta"] == ruta_seleccionada].iloc[0]

    with st.form("lincoln_editar_ruta_form", clear_on_submit=False):
        
        # Datos Generales
        st.markdown("### 📋 Información General")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            fecha_val = pd.to_datetime(ruta.get("Fecha"), errors="coerce")
            if pd.isna(fecha_val):
                fecha_val = datetime.today()
            fecha = st.date_input("📅 Fecha", value=fecha_val.date(), key="ln_edit_fecha")
        with col2:
            tipo = st.selectbox("🗺️ Tipo", TIPOS_RUTA, index=TIPOS_RUTA.index(ruta.get("Tipo", "NB")) if ruta.get("Tipo") in TIPOS_RUTA else 0, key="ln_edit_tipo")
        with col3:
            cliente = st.text_input("👤 Cliente", value=str(ruta.get("Cliente", "")), key="ln_edit_cliente")
        with col4:
            modo_viaje = st.selectbox("🚛 Modo", ["Sencillo", "Team"], index=["Sencillo", "Team"].index(ruta.get("Modo_Viaje", "Sencillo")) if ruta.get("Modo_Viaje") in ["Sencillo", "Team"] else 0, key="ln_edit_modo")

        config_ruta = obtener_config_tipo_ruta(tipo)

        # Ruta Americana
        if config_ruta["parte_usa"]:
            divider()
            st.markdown("### 🇺🇸 Ruta Americana")
            
            col_usa1, col_usa2 = st.columns(2)
            with col_usa1:
                origen_usa = st.text_input("📍 Origen", value=str(ruta.get("Origen", "")), key="ln_edit_ori_usa")
                destino_usa = st.text_input("📍 Destino", value=str(ruta.get("Destino", "")), key="ln_edit_dest_usa")
                millas_usa = st.number_input("🛣️ Millas Cargadas", value=float(safe(ruta.get("Millas_USA", 0))), step=10.0, key="ln_edit_mi_usa")
                millas_vacias = st.number_input("🛣️ Millas Vacías", value=float(safe(ruta.get("Millas_Vacias", 0))), step=10.0, key="ln_edit_mi_vac")
            
            with col_usa2:
                moneda_usa = st.selectbox("💵 Moneda", ["USD", "MXP"], index=["USD", "MXP"].index(ruta.get("Moneda_Ingreso_USA", "USD")) if ruta.get("Moneda_Ingreso_USA") in ["USD", "MXP"] else 0, key="ln_edit_moneda_usa")
                modalidad = st.radio("💰 Modalidad:", ["🔢 Desglosada", "💵 Flat"], index=0 if "Desglosada" in str(ruta.get("Modalidad_Tarifa", "Desglosada")) else 1, key="ln_edit_mod", horizontal=True)
                
                if "Desglosada" in modalidad:
                    cxm_flete = st.number_input("CXM Flete", value=float(safe(ruta.get("CXM_Flete", 0))), step=0.01, key="ln_edit_cxm_f")
                    cxm_fuel = st.number_input("CXM Fuel", value=float(safe(ruta.get("CXM_Fuel", 0.61))), step=0.01, key="ln_edit_cxm_fu")
                    tarifa_flat = 0.0
                else:
                    tarifa_flat = st.number_input("Tarifa Total", value=float(safe(ruta.get("Tarifa_Flat", 0))), step=50.0, key="ln_edit_flat")
                    cxm_flete = 0.0
                    cxm_fuel = 0.0
        else:
            origen_usa = destino_usa = ""
            millas_usa = millas_vacias = 0.0
            moneda_usa = "USD"
            modalidad = "Desglosada"
            cxm_flete = cxm_fuel = tarifa_flat = 0.0

        # Cruce
        if config_ruta["cruce"] != False:
            divider()
            st.markdown("### 🛃 Cruce")
            
            if config_ruta["cruce"] == "opcional":
                aplica_cruce = st.checkbox("✅ Incluye cruce", value=bool(ruta.get("Aplica_Cruce", False)), key="ln_edit_apl_cruce")
            else:
                aplica_cruce = True
                alert("info", "ℹ️ Siempre incluye cruce")
            
            if aplica_cruce:
                col_cr1, col_cr2 = st.columns(2)
                with col_cr1:
                    tipo_cruce = st.selectbox("🚛 Tipo", ["Propio", "Tercero"], index=["Propio", "Tercero"].index(ruta.get("Tipo_Cruce", "Propio")) if ruta.get("Tipo_Cruce") in ["Propio", "Tercero"] else 0, key="ln_edit_t_cruce")
                    tipo_carga = st.selectbox("📦 Carga", ["Cargado", "Vacío"], index=["Cargado", "Vacío"].index(ruta.get("Tipo_Carga_Cruce", "Cargado")) if ruta.get("Tipo_Carga_Cruce") in ["Cargado", "Vacío"] else 0, key="ln_edit_carga")
                    moneda_cruce = st.selectbox("💵 Moneda", ["USD", "MXP"], index=["USD", "MXP"].index(ruta.get("Moneda_Cruce", "USD")) if ruta.get("Moneda_Cruce") in ["USD", "MXP"] else 0, key="ln_edit_mon_cruce")
                with col_cr2:
                    ingreso_cruce = st.number_input(f"💵 Ingreso ({moneda_cruce})", value=float(safe(ruta.get("Ingreso_Cruce", 0))), step=10.0, key="ln_edit_ing_cruce")
                    if tipo_cruce == "Tercero":
                        costo_cruce_terc = st.number_input(f"💸 Costo ({moneda_cruce})", value=float(safe(ruta.get("Costo_Cruce_Tercero", 0))), step=10.0, key="ln_edit_c_cruce")
                    else:
                        alert("info", "ℹ️ Propio: sin costo")
                        costo_cruce_terc = 0.0
            else:
                tipo_cruce = tipo_carga = None
                moneda_cruce = "USD"
                ingreso_cruce = costo_cruce_terc = 0.0
        else:
            aplica_cruce = False
            tipo_cruce = tipo_carga = None
            moneda_cruce = "USD"
            ingreso_cruce = costo_cruce_terc = 0.0

        # Ruta Mexicana
        if config_ruta["parte_mx"]:
            divider()
            st.markdown("### 🇲🇽 Ruta Mexicana")
            
            col_mx1, col_mx2 = st.columns(2)
            with col_mx1:
                linea_mx = st.selectbox("🚚 Línea", ["Propia", "Tercero"], index=["Propia", "Tercero"].index(ruta.get("Linea_MX", "Propia")) if ruta.get("Linea_MX") in ["Propia", "Tercero"] else 0, key="ln_edit_linea")
                origen_mx = st.text_input("📍 Origen", value=str(ruta.get("Origen_MX", "")), key="ln_edit_ori_mx")
                destino_mx = st.text_input("📍 Destino", value=str(ruta.get("Destino_MX", "")), key="ln_edit_dest_mx")
                moneda_mx = st.selectbox("💵 Moneda", ["MXP", "USD"], index=["MXP", "USD"].index(ruta.get("Moneda_MX", "MXP")) if ruta.get("Moneda_MX") in ["MXP", "USD"] else 0, key="ln_edit_mon_mx")
            with col_mx2:
                ingreso_mx = st.number_input(f"💵 Ingreso ({moneda_mx})", value=float(safe(ruta.get("Ingreso_Flete_MX", 0))), step=100.0, key="ln_edit_ing_mx")
                if linea_mx == "Tercero":
                    costo_mx = st.number_input(f"💸 Costo ({moneda_mx})", value=float(safe(ruta.get("Costo_Flete_MX", 0))), step=100.0, key="ln_edit_c_mx")
                else:
                    alert("info", "ℹ️ Propia: calculado")
                    costo_mx = 0.0
        else:
            linea_mx = None
            origen_mx = destino_mx = ""
            moneda_mx = "MXP"
            ingreso_mx = costo_mx = 0.0

        # Otros Cargos
        divider()
        st.markdown("### 💵 Otros Cargos")
        
        otros_cargos = {}
        otros_cargos_pagados = {}
        
        cols = st.columns(3)
        for idx, campo in enumerate(EXTRAS_USA):
            with cols[idx % 3]:
                campo_db = f"Extra_{campo.replace(' ','_')}"
                monto = st.number_input(campo, value=float(safe(ruta.get(campo_db, 0))), step=10.0, key=f"ln_edit_oc_{idx}")
                otros_cargos[campo] = monto
                if monto > 0:
                    campo_pag = f"{campo_db}_Pagado"
                    pagado = st.checkbox(f"☑️ Se pagó", value=bool(ruta.get(campo_pag, False)), key=f"ln_edit_pag_{idx}")
                    otros_cargos_pagados[campo] = pagado
                else:
                    otros_cargos_pagados[campo] = False

        # Motivo de edición
        divider()
        st.markdown("### 📝 Motivo de Edición")
        motivo_edicion = st.text_area(
            "¿Por qué se está editando esta ruta? (Obligatorio)",
            placeholder="Ej: Corrección de millas incorrectas, actualización de tarifas, etc.",
            key="ln_edit_motivo"
        )

        divider()
        submitted = st.form_submit_button("🔎 **Revisar Cambios**", type="primary", use_container_width=True)

    # Procesamiento
    if submitted:
        if not motivo_edicion.strip():
            alert("error", "⚠️ Debes especificar el motivo de la edición.")
            return

        tc = float(valores.get("Tipo de Cambio USD/MXP", 18.5))

        # Convertir todo a USD
        if "Desglosada" in modalidad:
            ing_x_milla = cxm_flete
            fuel_sc = cxm_fuel
        else:
            ing_x_milla = tarifa_flat / millas_usa if millas_usa > 0 else 0.0
            fuel_sc = 0.0

        if moneda_usa == "MXP":
            ing_x_milla_usd = ing_x_milla / tc
            fuel_sc_usd = fuel_sc / tc
        else:
            ing_x_milla_usd = ing_x_milla
            fuel_sc_usd = fuel_sc

        if aplica_cruce:
            if moneda_cruce == "MXP":
                ing_cruce_usd = ingreso_cruce / tc
                costo_cruce_usd = costo_cruce_terc / tc if tipo_cruce == "Tercero" else 0.0
            else:
                ing_cruce_usd = ingreso_cruce
                costo_cruce_usd = costo_cruce_terc if tipo_cruce == "Tercero" else 0.0
        else:
            ing_cruce_usd = costo_cruce_usd = 0.0
            tipo_cruce = tipo_cruce or "Propio"
            tipo_carga = tipo_carga or "Cargado"

        if config_ruta["parte_mx"]:
            if moneda_mx == "USD":
                ing_mx_mxp = ingreso_mx * tc
                costo_mx_mxp = costo_mx * tc if linea_mx == "Tercero" else 0.0
            else:
                ing_mx_mxp = ingreso_mx
                costo_mx_mxp = costo_mx if linea_mx == "Tercero" else 0.0
        else:
            ing_mx_mxp = costo_mx_mxp = 0.0
            linea_mx = linea_mx or "Propia"

        r = calcular_ruta_lincoln(
            millas_usa, millas_vacias, ing_x_milla_usd, fuel_sc_usd,
            ing_cruce_usd, aplica_cruce, modo_viaje, tipo_cruce, tipo_carga,
            costo_cruce_usd, ing_mx_mxp, costo_mx_mxp, linea_mx,
            otros_cargos, otros_cargos_pagados, valores
        )

        # Guardar en session_state
        st.session_state["lincoln_datos_edicion"] = {
            "id_ruta": ruta_seleccionada,
            "fecha": str(fecha),
            "tipo": tipo,
            "cliente": normalizar_texto(cliente),
            "modo_viaje": modo_viaje,
            "origen_usa": normalizar_texto(origen_usa),
            "destino_usa": normalizar_texto(destino_usa),
            "millas_usa": millas_usa,
            "millas_vacias": millas_vacias,
            "moneda_usa": moneda_usa,
            "modalidad": modalidad,
            "cxm_flete": cxm_flete,
            "cxm_fuel": cxm_fuel,
            "tarifa_flat": tarifa_flat,
            "aplica_cruce": aplica_cruce,
            "tipo_cruce": tipo_cruce,
            "tipo_carga": tipo_carga,
            "moneda_cruce": moneda_cruce,
            "ingreso_cruce": ingreso_cruce,
            "costo_cruce_terc": costo_cruce_terc,
            "linea_mx": linea_mx,
            "origen_mx": normalizar_texto(origen_mx),
            "destino_mx": normalizar_texto(destino_mx),
            "moneda_mx": moneda_mx,
            "ingreso_mx": ingreso_mx,
            "costo_mx": costo_mx,
            "otros_cargos": otros_cargos,
            "otros_cargos_pagados": otros_cargos_pagados,
            "motivo": motivo_edicion.strip(),
        }
        st.session_state["lincoln_calc_edicion"] = r
        st.session_state.lincoln_revisar_edicion = True

    # ══════════════════════════════════════════════════════════════
    # MOSTRAR RESUMEN DE CAMBIOS
    # ══════════════════════════════════════════════════════════════
    if st.session_state.get("lincoln_revisar_edicion", False):
        r = st.session_state.get("lincoln_calc_edicion", {})
        
        divider()
        section_header("📊", "Resumen de Cambios")
        
        # Resumen tipo Igloo
        col1, col2 = st.columns(2)
        with col1:
            st.metric("💰 Ingreso Total", f"${r['ingreso_total']:,.2f}")
        with col2:
            color = "normal" if r["utilidad_bruta"] >= 0 else "inverse"
            st.metric("📊 Utilidad Bruta", f"${r['utilidad_bruta']:,.2f}", f"{r['pct_bruta']:.2f}%", delta_color=color)
        
        col3, col4 = st.columns(2)
        with col3:
            st.metric("💸 Costo Total", f"${r['costo_directo_total']:,.2f}")
        with col4:
            st.metric("📈 Costos Indirectos (42%)", f"${r['costos_ind']:,.2f}")
        
        color_neta = "normal" if r["utilidad_neta"] >= 0 else "inverse"
        st.metric("✨ Utilidad Neta", f"${r['utilidad_neta']:,.2f}", f"{r['pct_neta']:.2f}%", delta_color=color_neta)

    # ══════════════════════════════════════════════════════════════
    # GUARDAR CAMBIOS
    # ══════════════════════════════════════════════════════════════
    if st.session_state.get("lincoln_revisar_edicion", False):
        if st.button("💾 Guardar Cambios", key="lincoln_confirmar_edicion"):
            d = st.session_state.get("lincoln_datos_edicion", {})
            calc = st.session_state.get("lincoln_calc_edicion", {})
            
            if not d:
                alert("error", "No hay datos de edición.")
                return

            # Historial
            historial_anterior = ruta.get("historial", [])
            if historial_anterior is None:
                historial_anterior = []

            nueva_entrada_historial = {
                "timestamp": _now_iso(),
                "usuario": nombre_usuario,
                "motivo": d["motivo"],
                "cambios_anteriores": {
                    "Cliente": ruta.get("Cliente"),
                    "Origen": ruta.get("Origen"),
                    "Destino": ruta.get("Destino"),
                    "Millas_USA": ruta.get("Millas_USA"),
                    "Ingreso Total": ruta.get("Ingreso Total"),
                    "Costo_Total_Ruta": ruta.get("Costo_Total_Ruta"),
                    "Utilidad_Neta": ruta.get("Utilidad_Neta"),
                }
            }
            historial_actualizado = historial_anterior + [nueva_entrada_historial]

            # Construir ruta actualizada
            ruta_actualizada = {
                "Fecha": d["fecha"],
                "Tipo": d["tipo"],
                "Cliente": d["cliente"],
                "Modo_Viaje": d["modo_viaje"],
                "Origen": d["origen_usa"],
                "Destino": d["destino_usa"],
                "Millas_USA": d["millas_usa"],
                "Millas_Vacias": d["millas_vacias"],
                "Moneda_Ingreso_USA": d["moneda_usa"],
                "Modalidad_Tarifa": d["modalidad"],
                "CXM_Flete": d["cxm_flete"],
                "CXM_Fuel": d["cxm_fuel"],
                "Tarifa_Flat": d["tarifa_flat"],
                "Aplica_Cruce": d["aplica_cruce"],
                "Tipo_Cruce": d.get("tipo_cruce", ""),
                "Tipo_Carga_Cruce": d.get("tipo_carga", ""),
                "Moneda_Cruce": d["moneda_cruce"],
                "Ingreso_Cruce": d["ingreso_cruce"],
                "Costo_Cruce_Tercero": d["costo_cruce_terc"],
                "Linea_MX": d.get("linea_mx", ""),
                "Origen_MX": d["origen_mx"],
                "Destino_MX": d["destino_mx"],
                "Moneda_MX": d["moneda_mx"],
                "Ingreso_Flete_MX": d["ingreso_mx"],
                "Costo_Flete_MX": d["costo_mx"],
                "Ingreso_Flete_USA": calc["ingreso_flete_usa"],
                "Ingreso_Fuel_USA": calc["ingreso_fuel_usa"],
                "Ingreso_Total_USA": calc["ingreso_total_usa"],
                "Ingreso_MX_USD": calc["ingreso_mx_usd"],
                "Ingreso Total": calc["ingreso_total"],
                "Sueldo_Base": calc["sueldo_base"],
                "Bono_Millas": calc["bono_millas"],
                "Sueldo_Operador": calc["sueldo_usa"],
                "Diesel_USA": calc["diesel_usa"],
                "Costo_Cruce": calc["costo_cruce"],
                "Costo_MX_USD": calc["costo_mx_usd"],
                "Otros_Cargos_Ingreso": calc["otros_cargos_ingreso"],
                "Otros_Cargos_Costo": calc["otros_cargos_costo"],
                "ISR_IMSS": calc["isr_imss"],
                "Costo_Total_Ruta": calc["costo_directo_total"],
                "Utilidad_Bruta": calc["utilidad_bruta"],
                "Pct_Utilidad_Bruta": calc["pct_bruta"],
                "Costos_Indirectos": calc["costos_ind"],
                "Utilidad_Neta": calc["utilidad_neta"],
                "Pct_Utilidad_Neta": calc["pct_neta"],
                "TC_USD_MXP": calc["tc"],
                "MPG": calc["mpg"],
                "Precio_Diesel_USD": calc["diesel"],
                "CXM_Operador": calc["cxm_cargado"],
                "CXM_Vacio": calc["cxm_vacio"],
                "Bono_Por_Milla": calc["bono_por_milla"],
                **{f"Extra_{k.replace(' ','_')}": v for k, v in d["otros_cargos"].items()},
                **{f"Extra_{k.replace(' ','_')}_Pagado": v for k, v in d["otros_cargos_pagados"].items()},
                "updated_by": nombre_usuario,
                "updated_at": _now_iso(),
                "historial": historial_actualizado,
            }

            try:
                supabase.table(TABLE_RUTAS).update(limpiar_fila_json(ruta_actualizada)).eq("ID_Ruta", d["id_ruta"]).execute()
                
                st.session_state.lincoln_ruta_editada_id = d["id_ruta"]
                st.session_state.lincoln_mostrar_modal_edicion = True
                
                _load_rutas_lincoln_cached.clear()
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ Error al actualizar: {e}")
                st.exception(e)

    # ══════════════════════════════════════════════════════════════
    # HISTORIAL DE MODIFICACIONES
    # ══════════════════════════════════════════════════════════════
    if ruta_seleccionada:
        divider()
        section_header("📝", "Historial de modificaciones")
        
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
                            st.caption(f"Millas USA: {cambios.get('Millas_USA', 'N/A')}")
                        with col_hist2:
                            st.caption(f"Ingreso Total: {cambios.get('Ingreso Total', 'N/A')}")
                            st.caption(f"Costo Total: {cambios.get('Costo_Total_Ruta', 'N/A')}")
                            st.caption(f"Utilidad Neta: {cambios.get('Utilidad_Neta', 'N/A')}")
        else:
            alert("info", "Esta ruta no tiene modificaciones registradas.")

    # ══════════════════════════════════════════════════════════════
    # MODAL DE CONFIRMACIÓN
    # ══════════════════════════════════════════════════════════════
    @st.dialog("✅ Ruta Actualizada", width="small")
    def mostrar_modal_edicion(id_ruta):
        alert("success", "**¡La ruta se actualizó correctamente!**")
        st.info(f"### 🆔 ID: `{id_ruta}`")
        st.caption("Los cambios se guardaron en el historial")
        
        if st.button("✅ Aceptar", type="primary", use_container_width=True):
            st.session_state.pop("lincoln_ruta_editada_id", None)
            st.session_state.pop("lincoln_mostrar_modal_edicion", None)
            st.session_state.pop("lincoln_datos_edicion", None)
            st.session_state.pop("lincoln_calc_edicion", None)
            st.session_state.lincoln_revisar_edicion = False
            st.rerun()
    
    if st.session_state.get("lincoln_mostrar_modal_edicion") and st.session_state.get("lincoln_ruta_editada_id"):
        mostrar_modal_edicion(st.session_state.lincoln_ruta_editada_id)

    # ══════════════════════════════════════════════════════════════
    # ELIMINAR RUTA
    # ══════════════════════════════════════════════════════════════
    divider()
    section_header("🗑️", "Eliminar Ruta")
    
    with st.expander("⚠️ Zona de Peligro - Eliminar Ruta", expanded=False):
        alert("warn", "⚠️ **ADVERTENCIA:** Esta acción es permanente y no se puede deshacer.")
        
        col_del1, col_del2 = st.columns(2)
        
        with col_del1:
            id_eliminar = st.text_input(
                "ID de ruta a eliminar (escribe exacto):",
                key="lincoln_del_id",
                placeholder="LN000123"
            ).strip()
        
        with col_del2:
            if id_eliminar:
                # Verificar si existe
                if id_eliminar in df["ID_Ruta"].astype(str).values:
                    ruta_eliminar = df[df["ID_Ruta"] == id_eliminar].iloc[0]
                    st.info(f"**Ruta encontrada:**\n- Cliente: {ruta_eliminar.get('Cliente', 'N/A')}\n- Fecha: {ruta_eliminar.get('Fecha', 'N/A')}\n- Utilidad: ${safe(ruta_eliminar.get('Utilidad_Neta', 0)):,.2f}")
                else:
                    alert("error", "❌ ID no encontrado")
        
        confirmar_eliminacion = st.checkbox(
            "✅ Confirmo que quiero eliminar esta ruta PERMANENTEMENTE",
            key="lincoln_del_confirmar"
        )
        
        motivo_eliminacion = st.text_area(
            "Motivo de eliminación (Obligatorio):",
            placeholder="Ej: Ruta duplicada, creada por error, datos incorrectos irrecuperables, etc.",
            key="lincoln_del_motivo"
        )
        
        col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 2])
        
        with col_btn1:
            if st.button("🗑️ **ELIMINAR**", key="lincoln_del_btn", type="primary"):
                if not id_eliminar:
                    alert("error", "❌ Debes escribir el ID de la ruta.")
                elif not confirmar_eliminacion:
                    alert("error", "❌ Debes marcar la casilla de confirmación.")
                elif not motivo_eliminacion.strip():
                    alert("error", "❌ Debes especificar el motivo de eliminación.")
                elif id_eliminar not in df["ID_Ruta"].astype(str).values:
                    st.error(f"❌ La ruta {id_eliminar} no existe.")
                else:
                    try:
                        # Obtener datos de la ruta antes de eliminar
                        ruta_a_eliminar = df[df["ID_Ruta"] == id_eliminar].iloc[0]
                        
                        # Registrar eliminación (opcional: guardar en tabla de auditoría)
                        registro_eliminacion = {
                            "id_ruta_eliminada": id_eliminar,
                            "cliente": ruta_a_eliminar.get("Cliente"),
                            "fecha_ruta": str(ruta_a_eliminar.get("Fecha")),
                            "ingreso_total": safe(ruta_a_eliminar.get("Ingreso Total")),
                            "utilidad_neta": safe(ruta_a_eliminar.get("Utilidad_Neta")),
                            "motivo_eliminacion": motivo_eliminacion.strip(),
                            "eliminado_por": nombre_usuario,
                            "eliminado_en": _now_iso(),
                        }
                        
                        # Eliminar de la base de datos
                        supabase.table(TABLE_RUTAS).delete().eq("ID_Ruta", id_eliminar).execute()
                        
                        # Limpiar cache
                        _load_rutas_lincoln_cached.clear()
                        
                        # Mostrar modal de confirmación
                        st.session_state.lincoln_ruta_eliminada_id = id_eliminar
                        st.session_state.lincoln_mostrar_modal_eliminacion = True
                        
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ Error al eliminar la ruta: {e}")
                        st.exception(e)
        
        with col_btn2:
            if st.button("❌ Cancelar", key="lincoln_del_cancel"):
                alert("info", "Operación cancelada")

    # ══════════════════════════════════════════════════════════════
    # MODAL DE CONFIRMACIÓN DE ELIMINACIÓN
    # ══════════════════════════════════════════════════════════════
    @st.dialog("✅ Ruta Eliminada", width="small")
    def mostrar_modal_eliminacion(id_ruta):
        alert("success", "**¡La ruta se eliminó correctamente!**")
        st.info(f"### 🗑️ Ruta eliminada\n`{id_ruta}`")
        st.caption("Esta acción no se puede deshacer")
        
        if st.button("✅ Aceptar", type="primary", use_container_width=True):
            st.session_state.pop("lincoln_ruta_eliminada_id", None)
            st.session_state.pop("lincoln_mostrar_modal_eliminacion", None)
            st.rerun()
    
    if st.session_state.get("lincoln_mostrar_modal_eliminacion") and st.session_state.get("lincoln_ruta_eliminada_id"):
        mostrar_modal_eliminacion(st.session_state.lincoln_ruta_eliminada_id)


if __name__ == "__main__":
    render()
