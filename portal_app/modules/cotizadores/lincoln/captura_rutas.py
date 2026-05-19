from ui.components import section_header, alert, divider
"""
captura_rutas.py – Lincoln Freight (USA/MX)
Versión final con:
- Otros Cargos con checkbox "¿Se pagó?" individual
- Diseño tipo Igloo exacto
- Lógica condicional por tipo de ruta
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timezone
import re

from services.supabase_client import get_supabase_client, get_authed_client, current_user
from ._shared import (
    TABLE_RUTAS, TIPOS_RUTA, EXTRAS_USA,
    DEFAULTS, cargar_datos_generales, guardar_datos_generales,
    limpiar_fila_json, safe,
)


# ─────────────────────────────────────────────
# UTILIDADES
# ─────────────────────────────────────────────
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


# ─────────────────────────────────────────────
# CONFIGURACIÓN POR TIPO DE RUTA
# ─────────────────────────────────────────────
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


# ─────────────────────────────────────────────
# CÁLCULO CON LÓGICA DE OTROS CARGOS
# ─────────────────────────────────────────────
def calcular_ruta_lincoln(millas_usa, millas_vacias, ingreso_x_milla_usd, fuel_surcharge_usd,
                          ingreso_cruce_usd, aplica_cruce, modo_viaje, tipo_cruce, tipo_carga_cruce,
                          costo_cruce_tercero_usd, ingreso_flete_mx_mxp, costo_flete_mx_mxp,
                          linea_mx, otros_cargos, otros_cargos_pagados, valores):
    """
    Calcula ruta con lógica de otros cargos:
    - Si tiene monto → suma a ingreso
    - Si checkbox "pagado" → suma también a costo
    """
    tc = float(valores.get("Tipo de Cambio USD/MXP", 18.5))
    mpg = float(valores.get("Truck Performance (mpg)", 7.0))
    diesel_precio = float(valores.get("Diesel Price ($/gal)", 3.60))
    isr_imss = float(valores.get("ISR/IMSS", 462.66))
    bono_por_milla = float(valores.get("Bono por milla cargada", 0.01))
    
    # Ingresos USA
    ingreso_flete_usa = ingreso_x_milla_usd * millas_usa
    ingreso_fuel_usa = fuel_surcharge_usd * millas_usa
    ingreso_total_usa = ingreso_flete_usa + ingreso_fuel_usa
    
    # Otros Cargos - INGRESO (todos los que tienen monto)
    otros_cargos_ingreso = sum(otros_cargos.values())
    
    # Otros Cargos - COSTO (solo los marcados como pagados)
    otros_cargos_costo = sum(
        monto for nombre, monto in otros_cargos.items() 
        if otros_cargos_pagados.get(nombre, False) and monto > 0
    )
    
    # Sueldo operador
    if modo_viaje == "Team":
        cxm_cargado = float(valores.get("CXM Team USA", 0.30))
        cxm_vacio = float(valores.get("CXM Team USA (Empty)", 0.25))
        factor = 2
    else:  # Sencillo
        cxm_cargado = float(valores.get("CXM Operador USA", 0.48))
        cxm_vacio = float(valores.get("CXM Operador USA (Empty)", 0.30))
        factor = 1
    
    sueldo_base = (millas_usa * cxm_cargado + millas_vacias * cxm_vacio) * factor
    bono_millas = (millas_usa * bono_por_milla) * factor
    sueldo_usa = sueldo_base + bono_millas
    
    # Diesel
    diesel_usa = ((millas_usa + millas_vacias) / mpg) * diesel_precio if mpg else 0.0
    
    # Cruce - SOLO SI APLICA
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
    pct_cd = (costo_directo_total / ingreso_total * 100) if ingreso_total > 0 else 0.0
    
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
        "costo_directo": costo_directo,
        "costo_directo_total": costo_directo_total,
        "utilidad_bruta": utilidad_bruta,
        "pct_bruta": pct_bruta,
        "costos_ind": costos_ind,
        "utilidad_neta": utilidad_neta,
        "pct_neta": pct_neta,
        "pct_cd": pct_cd,
        "tc": tc,
        "mpg": mpg,
        "diesel": diesel_precio,
        "cxm_cargado": cxm_cargado,
        "cxm_vacio": cxm_vacio,
        "bono_por_milla": bono_por_milla,
    }


# ─────────────────────────────────────────────
# ID GENERATOR
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=30)
def _ultimo_id(table: str):
    supabase = get_supabase_client()
    if supabase is None:
        return None
    resp = supabase.table(table).select("ID_Ruta").order("ID_Ruta", desc=True).limit(1).execute()
    return resp.data[0].get("ID_Ruta") if resp.data else None


def generar_id() -> str:
    ultimo = _ultimo_id(TABLE_RUTAS)
    if ultimo and isinstance(ultimo, str) and len(ultimo) >= 3:
        try:
            return f"LN{int(ultimo[2:]) + 1:06d}"
        except Exception:
            pass
    return "LN000001"


# ─────────────────────────────────────────────
# PANEL DATOS GENERALES
# ─────────────────────────────────────────────
def _panel_datos_generales(valores: dict) -> dict:
    with st.expander("⚙️ Configurar Datos Generales (Lincoln)", expanded=False):
        st.caption("💡 Estos valores se usan en todos los cálculos.")
        c1, c2, c3 = st.columns(3)
        keys = list(DEFAULTS.keys())
        for i, key in enumerate(keys):
            col = [c1, c2, c3][i % 3]
            valores[key] = col.number_input(
                key, 
                value=float(valores.get(key, DEFAULTS[key])),
                step=0.01 if "milla" in key.lower() else 0.1,
                key=f"ln_gen_{i}"
            )
        if st.button("💾 Guardar", key="ln_save_gen", type="primary"):
            guardar_datos_generales(valores)
            alert("success", "✅ Guardado")
    return valores


# ─────────────────────────────────────────────
# RESUMEN TIPO IGLOO EXACTO
# ─────────────────────────────────────────────
def _mostrar_resumen(r: dict):
    divider()
    st.markdown("## 📊 Resumen de Utilidades")
    
    # Estilo tipo Igloo
    st.markdown("""
    <style>
    .metric-card {
        background: white;
        padding: 1.5rem;
        border-radius: 8px;
        border: 1px solid #e5e7eb;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    .metric-label {
        font-size: 0.875rem;
        color: #6b7280;
        margin-bottom: 0.5rem;
    }
    .metric-value {
        font-size: 2rem;
        font-weight: 600;
        color: #111827;
    }
    .metric-pct {
        font-size: 0.875rem;
        color: #059669;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Grid 2×2
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">💰 Ingreso Total</div>
            <div class="metric-value">${r['ingreso_total']:,.2f}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        color = "#059669" if r["utilidad_bruta"] >= 0 else "#dc2626"
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">📊 Utilidad Bruta</div>
            <div class="metric-value" style="color: {color};">${r['utilidad_bruta']:,.2f}</div>
            <div class="metric-pct" style="color: {color};">+ {r['pct_bruta']:.2f}%</div>
        </div>
        """, unsafe_allow_html=True)
    
    col3, col4 = st.columns(2)
    
    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">💸 Costo Total</div>
            <div class="metric-value">${r['costo_directo_total']:,.2f}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">📈 Costos Indirectos (42% — VACÍO)</div>
            <div class="metric-value">${r['costos_ind']:,.2f}</div>
        </div>
        """, unsafe_allow_html=True)
    
    # Utilidad Neta destacada
    color_neta = "#059669" if r["utilidad_neta"] >= 0 else "#dc2626"
    color_fondo = "#fef2f2" if r["utilidad_neta"] < 0 else "#f0fdf4"
    
    st.markdown(f"""
    <div style="background: {color_fondo}; padding: 1.5rem; border-radius: 8px; 
                margin-top: 1rem; border-left: 4px solid {color_neta};">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <span style="color: #374151; font-weight: 500;">Utilidad Neta</span>
            <div>
                <span style="font-size: 2rem; font-weight: 600; color: {color_neta};">${r['utilidad_neta']:,.2f}</span>
                <span style="font-size: 1rem; color: {color_neta}; margin-left: 0.5rem;">{r['pct_neta']:.2f}%</span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Desglose
    with st.expander("🔍 Ver Desglose por Tramo", expanded=False):
        tab1, tab2, tab3 = st.tabs(["🇺🇸 Ruta Americana", "🛃 Cruce", "🇲🇽 Ruta Mexicana"])
        
        with tab1:
            col_a, col_b = st.columns(2)
            with col_a:
                st.write("**📈 Ingresos**")
                st.write(f"Flete: ${r['ingreso_flete_usa']:,.2f}")
                st.write(f"Fuel: ${r['ingreso_fuel_usa']:,.2f}")
                st.write(f"Otros Cargos: ${r['otros_cargos_ingreso']:,.2f}")
                st.write(f"**Total: ${r['ingreso_total_usa'] + r['otros_cargos_ingreso']:,.2f}**")
            with col_b:
                st.write("**📉 Costos**")
                st.write(f"Sueldo Base: ${r['sueldo_base']:,.2f}")
                st.write(f"Bono: ${r['bono_millas']:,.2f}")
                st.write(f"Diesel: ${r['diesel_usa']:,.2f}")
                st.write(f"Otros (Pagados): ${r['otros_cargos_costo']:,.2f}")
                st.write(f"ISR/IMSS: ${r['isr_imss']:,.2f}")
                total_costo_usa = r['sueldo_usa'] + r['diesel_usa'] + r['otros_cargos_costo'] + r['isr_imss']
                st.write(f"**Total: ${total_costo_usa:,.2f}**")
            
            util_usa = (r['ingreso_total_usa'] + r['otros_cargos_ingreso']) - total_costo_usa
            st.markdown(f"**Utilidad USA:** :{'green' if util_usa >= 0 else 'red'}[${util_usa:,.2f}]")
        
        with tab2:
            col_c, col_d = st.columns(2)
            with col_c:
                st.write(f"**Ingreso:** ${r['ingreso_cruce']:,.2f}")
            with col_d:
                st.write(f"**Costo:** ${r['costo_cruce']:,.2f}")
            util_cruce = r['ingreso_cruce'] - r['costo_cruce']
            st.markdown(f"**Utilidad:** :{'green' if util_cruce >= 0 else 'red'}[${util_cruce:,.2f}]")
        
        with tab3:
            col_e, col_f = st.columns(2)
            with col_e:
                st.write(f"**Ingreso:** ${r['ingreso_mx_usd']:,.2f}")
            with col_f:
                st.write(f"**Costo:** ${r['costo_mx_usd']:,.2f}")
            util_mx = r['ingreso_mx_usd'] - r['costo_mx_usd']
            st.markdown(f"**Utilidad:** :{'green' if util_mx >= 0 else 'red'}[${util_mx:,.2f}]")


# ─────────────────────────────────────────────
# RENDER PRINCIPAL
# ─────────────────────────────────────────────
def render():
    st.title("🚛 Captura de Rutas – Lincoln Freight")
    
    supabase = get_supabase_client()
    if supabase is None:
        alert("warn", "⚠️ Supabase no configurado.")
        return
    
    u = current_user() or {}
    user_id = u.get("id") or u.get("sub") or ""
    nombre_usuario = _get_profile_name(user_id) or u.get("email") or "Desconocido"
    
    st.session_state.setdefault("ln_resultado", None)
    st.session_state.setdefault("ln_form_data", {})
    
    valores = cargar_datos_generales()
    valores = _panel_datos_generales(valores)
    
    divider()
    section_header("🛣️", "Nueva Ruta")
    
    with st.form("ln_captura_ruta", clear_on_submit=False):
        
        # Datos generales
        st.markdown("### 📋 Información General")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            fecha = st.date_input("📅 Fecha", value=datetime.today(), key="ln_fecha")
        with col2:
            tipo_ruta = st.selectbox("🗺️ Tipo", TIPOS_RUTA, key="ln_tipo")
        with col3:
            cliente = st.text_input("👤 Cliente", key="ln_cliente")
        with col4:
            modo_viaje = st.selectbox("🚛 Modo", ["Sencillo", "Team"], key="ln_modo")
        
        config_ruta = obtener_config_tipo_ruta(tipo_ruta)
        
        # Ruta Americana
        if config_ruta["parte_usa"]:
            divider()
            st.markdown("### 🇺🇸 Ruta Americana")
            
            col_usa1, col_usa2 = st.columns(2)
            with col_usa1:
                origen_usa = st.text_input("📍 Origen", key="ln_ori_usa")
                destino_usa = st.text_input("📍 Destino", key="ln_dest_usa")
                millas_usa = st.number_input("🛣️ Millas Cargadas", min_value=0.0, step=10.0, key="ln_mi_usa")
                millas_vacias = st.number_input("🛣️ Millas Vacías", min_value=0.0, step=10.0, key="ln_mi_vac")
            
            with col_usa2:
                moneda_usa = st.selectbox("💵 Moneda", ["USD", "MXP"], key="ln_moneda_usa")
                modalidad = st.radio("💰 Modalidad:", ["🔢 Desglosada", "💵 Flat"], key="ln_mod", horizontal=True)
                
                if "Desglosada" in modalidad:
                    cxm_flete = st.number_input("CXM Flete", min_value=0.0, step=0.01, key="ln_cxm_f")
                    cxm_fuel = st.number_input("CXM Fuel", min_value=0.0, value=0.61, step=0.01, key="ln_cxm_fu")
                    tarifa_flat = 0.0
                else:
                    tarifa_flat = st.number_input("Tarifa Total", min_value=0.0, step=50.0, key="ln_flat")
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
                aplica_cruce = st.checkbox("✅ Incluye cruce", key="ln_apl_cruce")
            else:
                aplica_cruce = True
                alert("info", "ℹ️ Siempre incluye cruce")
            
            if aplica_cruce:
                col_cr1, col_cr2 = st.columns(2)
                with col_cr1:
                    tipo_cruce = st.selectbox("🚛 Tipo", ["Propio", "Tercero"], key="ln_t_cruce")
                    tipo_carga = st.selectbox("📦 Carga", ["Cargado", "Vacío"], key="ln_carga")
                    moneda_cruce = st.selectbox("💵 Moneda", ["USD", "MXP"], key="ln_mon_cruce")
                with col_cr2:
                    ingreso_cruce = st.number_input(f"💵 Ingreso ({moneda_cruce})", min_value=0.0, step=10.0, key="ln_ing_cruce")
                    if tipo_cruce == "Tercero":
                        costo_cruce_terc = st.number_input(f"💸 Costo ({moneda_cruce})", min_value=0.0, step=10.0, key="ln_c_cruce")
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
                linea_mx = st.selectbox("🚚 Línea", ["Propia", "Tercero"], key="ln_linea")
                origen_mx = st.text_input("📍 Origen", key="ln_ori_mx")
                destino_mx = st.text_input("📍 Destino", key="ln_dest_mx")
                moneda_mx = st.selectbox("💵 Moneda", ["MXP", "USD"], key="ln_mon_mx")
            with col_mx2:
                ingreso_mx = st.number_input(f"💵 Ingreso ({moneda_mx})", min_value=0.0, step=100.0, key="ln_ing_mx")
                if linea_mx == "Tercero":
                    costo_mx = st.number_input(f"💸 Costo ({moneda_mx})", min_value=0.0, step=100.0, key="ln_c_mx")
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
        st.caption("Si captura monto → se cobra al cliente. Marca ☑️ si también se pagó")
        
        otros_cargos = {}
        otros_cargos_pagados = {}
        
        cols = st.columns(3)
        for idx, campo in enumerate(EXTRAS_USA):
            with cols[idx % 3]:
                monto = st.number_input(campo, min_value=0.0, step=10.0, key=f"ln_oc_{idx}")
                otros_cargos[campo] = monto
                if monto > 0:
                    pagado = st.checkbox(f"☑️ Se pagó", key=f"ln_pag_{idx}")
                    otros_cargos_pagados[campo] = pagado
                else:
                    otros_cargos_pagados[campo] = False
        
        divider()
        submitted = st.form_submit_button("🔎 **Calcular**", type="primary", use_container_width=True)
    
    # Procesamiento
    if submitted:
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
        
        st.session_state["ln_resultado"] = r
        st.session_state["ln_form_data"] = {
            "fecha": str(fecha), "tipo_ruta": tipo_ruta, "cliente": normalizar_texto(cliente),
            "modo_viaje": modo_viaje, "origen_usa": normalizar_texto(origen_usa),
            "destino_usa": normalizar_texto(destino_usa), "millas_usa": millas_usa,
            "millas_vacias": millas_vacias, "moneda_usa": moneda_usa, "modalidad": modalidad,
            "cxm_flete": cxm_flete, "cxm_fuel": cxm_fuel, "tarifa_flat": tarifa_flat,
            "aplica_cruce": aplica_cruce, "tipo_cruce": tipo_cruce, "tipo_carga": tipo_carga,
            "moneda_cruce": moneda_cruce, "ingreso_cruce": ingreso_cruce,
            "costo_cruce_terc": costo_cruce_terc, "linea_mx": linea_mx,
            "origen_mx": normalizar_texto(origen_mx), "destino_mx": normalizar_texto(destino_mx),
            "moneda_mx": moneda_mx, "ingreso_mx": ingreso_mx, "costo_mx": costo_mx,
            "otros_cargos": otros_cargos, "otros_cargos_pagados": otros_cargos_pagados,
        }
    
    # Mostrar resultado
    if st.session_state["ln_resultado"]:
        r = st.session_state["ln_resultado"]
        fd = st.session_state["ln_form_data"]
        
        _mostrar_resumen(r)
        
        divider()
        if st.button("💾 **Guardar**", type="primary", use_container_width=True, key="ln_guardar"):
            nuevo_id = generar_id()
            _ultimo_id.clear()
            
            data_row = {
                "ID_Ruta": nuevo_id,
                "Fecha": fd["fecha"],
                "Tipo": fd["tipo_ruta"],
                "Cliente": fd["cliente"],
                "Modo_Viaje": fd["modo_viaje"],
                "Origen": fd["origen_usa"],
                "Destino": fd["destino_usa"],
                "Millas_USA": fd["millas_usa"],
                "Millas_Vacias": fd["millas_vacias"],
                "Moneda_Ingreso_USA": fd["moneda_usa"],
                "Modalidad_Tarifa": fd["modalidad"],
                "CXM_Flete": fd["cxm_flete"],
                "CXM_Fuel": fd["cxm_fuel"],
                "Tarifa_Flat": fd["tarifa_flat"],
                "Aplica_Cruce": fd["aplica_cruce"],
                "Tipo_Cruce": fd.get("tipo_cruce", ""),
                "Tipo_Carga_Cruce": fd.get("tipo_carga", ""),
                "Moneda_Cruce": fd["moneda_cruce"],
                "Ingreso_Cruce": fd["ingreso_cruce"],
                "Costo_Cruce_Tercero": fd["costo_cruce_terc"],
                "Linea_MX": fd.get("linea_mx", ""),
                "Origen_MX": fd["origen_mx"],
                "Destino_MX": fd["destino_mx"],
                "Moneda_MX": fd["moneda_mx"],
                "Ingreso_Flete_MX": fd["ingreso_mx"],
                "Costo_Flete_MX": fd["costo_mx"],
                "Ingreso_Flete_USA": r["ingreso_flete_usa"],
                "Ingreso_Fuel_USA": r["ingreso_fuel_usa"],
                "Ingreso_Total_USA": r["ingreso_total_usa"],
                "Ingreso_MX_USD": r["ingreso_mx_usd"],
                "Ingreso Total": r["ingreso_total"],
                "Sueldo_Base": r["sueldo_base"],
                "Bono_Millas": r["bono_millas"],
                "Sueldo_Operador": r["sueldo_usa"],
                "Diesel_USA": r["diesel_usa"],
                "Costo_Cruce": r["costo_cruce"],
                "Costo_MX_USD": r["costo_mx_usd"],
                "Otros_Cargos_Ingreso": r["otros_cargos_ingreso"],
                "Otros_Cargos_Costo": r["otros_cargos_costo"],
                "ISR_IMSS": r["isr_imss"],
                "Costo_Total_Ruta": r["costo_directo_total"],
                "Utilidad_Bruta": r["utilidad_bruta"],
                "Pct_Utilidad_Bruta": r["pct_bruta"],
                "Costos_Indirectos": r["costos_ind"],
                "Utilidad_Neta": r["utilidad_neta"],
                "Pct_Utilidad_Neta": r["pct_neta"],
                "TC_USD_MXP": r["tc"],
                "MPG": r["mpg"],
                "Precio_Diesel_USD": r["diesel"],
                "CXM_Operador": r["cxm_cargado"],
                "CXM_Vacio": r["cxm_vacio"],
                "Bono_Por_Milla": r["bono_por_milla"],
                **{f"Extra_{k.replace(' ','_')}": v for k, v in fd["otros_cargos"].items()},
                **{f"Extra_{k.replace(' ','_')}_Pagado": v for k, v in fd["otros_cargos_pagados"].items()},
                "created_by": nombre_usuario,
                "created_at": _now_iso(),
                "updated_by": None,
                "updated_at": None,
                "historial": [],
            }
            
            try:
                supabase.table(TABLE_RUTAS).insert(limpiar_fila_json(data_row)).execute()
                
                st.session_state.ln_ruta_guardada_id = nuevo_id
                st.session_state.ln_mostrar_modal = True
                
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ Error: {e}")
    
    # Modal
    @st.dialog("✅ Ruta Guardada", width="small")
    def mostrar_modal_guardado(id_ruta):
        alert("success", "**¡Ruta guardada correctamente!**")
        st.info(f"### 🆔 ID: `{id_ruta}`")
        
        if st.button("✅ Aceptar", type="primary", use_container_width=True):
            st.session_state.pop("ln_ruta_guardada_id", None)
            st.session_state.pop("ln_mostrar_modal", None)
            st.session_state.pop("ln_resultado", None)
            st.session_state.pop("ln_form_data", None)
            st.rerun()
    
    if st.session_state.get("ln_mostrar_modal") and st.session_state.get("ln_ruta_guardada_id"):
        mostrar_modal_guardado(st.session_state.ln_ruta_guardada_id)


if __name__ == "__main__":
    render()
