from ui.components import section_header, alert, divider
"""
captura_rutas.py – Set Logis
Captura de rutas con diseño moderno y formal
Modelo: Pago a owners por milla (cargada/vacía)
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timezone
import re

from services.supabase_client import get_supabase_client, get_authed_client, current_user
from ._shared import (
    TABLE_RUTAS, TIPOS_RUTA, DIRECCIONES,
    DEFAULTS, cargar_datos_generales, guardar_datos_generales,
    limpiar_fila_json, safe, calcular_ruta_setlogis,
)


# ─────────────────────────────────────────────
# ESTILOS MODERNOS
# ─────────────────────────────────────────────
def aplicar_estilos():
    st.markdown("""
    <style>
    /* Headers con gradiente */
    .header-gradient {
        background: linear-gradient(90deg, #dbeafe 0%, transparent 100%);
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #3b82f6;
        margin-bottom: 1.5rem;
    }
    
    /* Cards modernos */
    .metric-card {
        background: white;
        padding: 1.5rem;
        border-radius: 12px;
        border-left: 4px solid #3b82f6;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06);
        margin-bottom: 1rem;
    }
    
    .metric-label {
        font-size: 0.875rem;
        color: #64748b;
        font-weight: 500;
        margin-bottom: 0.5rem;
    }
    
    .metric-value {
        font-size: 2rem;
        font-weight: 700;
        color: #0f172a;
        margin-bottom: 0.25rem;
    }
    
    .metric-desc {
        font-size: 0.75rem;
        color: #94a3b8;
    }
    
    /* Badges de estado */
    .badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 600;
        margin-right: 0.5rem;
    }
    
    .badge-success {
        background: #d1fae5;
        color: #10b981;
    }
    
    .badge-warning {
        background: #fef3c7;
        color: #f59e0b;
    }
    
    .badge-info {
        background: #dbeafe;
        color: #3b82f6;
    }
    
    /* Secciones */
    .section-divider {
        border-top: 2px solid #e5e7eb;
        margin: 2rem 0;
    }
    
    /* Tooltips informativos */
    .info-tooltip {
        background: #f0f9ff;
        border-left: 3px solid #0ea5e9;
        padding: 0.75rem;
        border-radius: 4px;
        margin: 1rem 0;
        font-size: 0.875rem;
    }
    </style>
    """, unsafe_allow_html=True)


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
            return f"SL{int(ultimo[2:]) + 1:06d}"
        except Exception:
            pass
    return "SL000001"


# ─────────────────────────────────────────────
# COMPONENTES UI
# ─────────────────────────────────────────────
def card_metric(titulo, valor, descripcion="", color="#3b82f6"):
    """Muestra una métrica en card moderno"""
    st.markdown(f"""
    <div style='
        background: white;
        padding: 1.5rem;
        border-radius: 12px;
        border-left: 4px solid {color};
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06);
        margin-bottom: 1rem;
    '>
        <div style='font-size: 0.875rem; color: #64748b; font-weight: 500; margin-bottom: 0.5rem;'>
            {titulo}
        </div>
        <div style='font-size: 2rem; font-weight: 700; color: #0f172a; margin-bottom: 0.25rem;'>
            {valor}
        </div>
        <div style='font-size: 0.75rem; color: #94a3b8;'>
            {descripcion}
        </div>
    </div>
    """, unsafe_allow_html=True)


def badge_tipo_ruta(tipo):
    """Badge visual para tipo de ruta"""
    badges = {
        "NB": ("🔼 NB", "#3b82f6", "#dbeafe"),
        "SB": ("🔽 SB", "#8b5cf6", "#ede9fe"),
        "D2DNB": ("🚪 D2DNB", "#10b981", "#d1fae5"),
        "D2DSB": ("🚪 D2DSB", "#f59e0b", "#fef3c7"),
        "Empty": ("⚪ Empty", "#6b7280", "#f3f4f6"),
    }
    label, color, bg = badges.get(tipo, (tipo, "#6b7280", "#f3f4f6"))
    return f"<span style='background:{bg}; color:{color}; padding:0.25rem 0.75rem; border-radius:9999px; font-size:0.75rem; font-weight:600;'>{label}</span>"


# ─────────────────────────────────────────────
# PANEL DATOS GENERALES
# ─────────────────────────────────────────────
def _panel_datos_generales(valores: dict) -> dict:
    with st.expander("⚙️ Configurar Datos Generales (Set Logis)", expanded=False):
        st.markdown("""
        <div class='info-tooltip'>
        💡 Estos valores se usan en todos los cálculos. Los costos indirectos tienen dos métodos 
        para que puedas comparar cuál funciona mejor para tu operación.
        </div>
        """, unsafe_allow_html=True)
        
        # Pago a owners
        st.markdown("#### 💰 Pago a Owners (por milla)")
        c1, c2, c3 = st.columns(3)
        
        valores["PxM Owner Subidas"] = c1.number_input(
            "PxM Owner Subidas",
            value=float(valores.get("PxM Owner Subidas", 1.60)),
            step=0.01,
            help="Pago por milla cargada en rutas NB/D2DNB",
            key="sl_pxm_subida"
        )
        
        valores["PxM Owner Bajadas"] = c2.number_input(
            "PxM Owner Bajadas",
            value=float(valores.get("PxM Owner Bajadas", 1.40)),
            step=0.01,
            help="Pago por milla cargada en rutas SB/D2DSB",
            key="sl_pxm_bajada"
        )
        
        valores["PxM Owner Vacio"] = c3.number_input(
            "PxM Owner Vacio",
            value=float(valores.get("PxM Owner Vacio", 0.80)),
            step=0.01,
            help="Pago por milla vacía",
            key="sl_pxm_vacio"
        )
        
        divider()
        
        # Costos indirectos
        st.markdown("#### 📊 Costos Indirectos (dos métodos)")
        c4, c5, c6 = st.columns(3)
        
        valores["CXM Indirecto"] = c4.number_input(
            "CXM Indirecto",
            value=float(valores.get("CXM Indirecto", 0.10)),
            step=0.01,
            help="Costo indirecto por milla total (cargada + vacía)",
            key="sl_cxm_ind"
        )
        
        valores["% Costo Indirecto"] = c5.number_input(
            "% Costo Indirecto",
            value=float(valores.get("% Costo Indirecto", 0.15)),
            step=0.01,
            help="Porcentaje sobre ingreso total",
            key="sl_pct_ind"
        )
        
        valores["Tipo de Cambio USD/MXP"] = c6.number_input(
            "Tipo de Cambio USD/MXP",
            value=float(valores.get("Tipo de Cambio USD/MXP", 18.50)),
            step=0.10,
            key="sl_tc"
        )
        
        if st.button("💾 Guardar Configuración", key="sl_save_gen", type="primary"):
            guardar_datos_generales(valores)
            alert("success", "✅ Configuración guardada exitosamente")
            
    return valores


# ─────────────────────────────────────────────
# RESUMEN VISUAL
# ─────────────────────────────────────────────
def _mostrar_resumen(r: dict, tipo_ruta: str):
    st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)
    st.markdown("## 📊 Resumen Financiero")
    
    # Métricas principales
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        color = "#10b981" if r["Ingreso_Global"] > 0 else "#6b7280"
        st.metric(
            "Ingreso Global",
            f"${r['Ingreso_Global']:,.2f}",
            delta=None if tipo_ruta == "Empty" else "✓ Activo"
        )
    
    with col2:
        st.metric(
            "Costos Directos",
            f"${r['Total_Costos_Directos']:,.2f}",
            delta=f"{r['Pct_CD']:.1f}%" if r['Ingreso_Global'] > 0 else None,
            delta_color="inverse"
        )
    
    with col3:
        if tipo_ruta != "Empty":
            st.metric(
                "Costo Indirecto",
                f"${r['Costo_Indirecto']:,.2f}",
                delta=f"{r['Pct_CI']:.1f}%",
                delta_color="inverse"
            )
        else:
            alert("info", "⚪ Sin costos indirectos")
    
    with col4:
        color_ut = "#10b981" if r['Utilidad_Neta'] >= 0 else "#ef4444"
        st.metric(
            "Utilidad Neta",
            f"${r['Utilidad_Neta']:,.2f}",
            delta=f"{r['Pct_Ut_Neta']:.1f}%" if r['Ingreso_Global'] > 0 else None,
            delta_color="normal" if r['Utilidad_Neta'] >= 0 else "inverse"
        )
    
    # Detalles en expander
    with st.expander("📋 Ver Detalles de Cálculo", expanded=False):
        st.markdown("#### Ingresos")
        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric("Flete USA", f"${r['Flete_USA']:,.2f}")
        col_b.metric("Fuel", f"${r['Fuel']:,.2f}")
        col_c.metric("Flete + Fuel", f"${r['Flete_Fuel']:,.2f}")
        col_d.metric("Cruce", f"${r['Cruce']:,.2f}")
        
        divider()
        st.markdown("#### Costos Directos (Pago a Owner)")
        col_d, col_e, col_f = st.columns(3)
        col_d.metric("Tasa Cargado", f"${r['Tasa_Owner_Cargado']:.2f}/mi")
        col_e.metric("Sueldo Cargado", f"${r['Sueldo_Owner_Cargado']:,.2f}")
        col_f.metric("Sueldo Vacío", f"${r['Sueldo_Owner_Vacio']:,.2f}")
        
        if tipo_ruta != "Empty":
            divider()
            st.markdown("#### Costos Indirectos")
            if r.get('CXM_Indirecto', 0) > 0:
                metodo = f"CXM: ${r['CXM_Indirecto']:.2f} por milla"
            else:
                metodo = "Porcentaje sobre ingreso"
            st.info(f"📊 Método aplicado: **{metodo}**")


# ─────────────────────────────────────────────
# RENDER PRINCIPAL
# ─────────────────────────────────────────────
def render():
    aplicar_estilos()
    
    # Header con gradiente
    st.markdown("""
    <div class='header-gradient'>
        <h1 style='color: #1e40af; margin: 0;'>🚛 Cotizador Set Logis</h1>
        <p style='color: #64748b; margin: 0.5rem 0 0 0;'>Sistema de captura y cálculo de rutas</p>
    </div>
    """, unsafe_allow_html=True)
    
    supabase = get_supabase_client()
    if supabase is None:
        alert("error", "⚠️ Supabase no configurado. Verifica tu conexión.")
        return
    
    # Cargar valores
    valores = cargar_datos_generales()
    
    # Tabs principales
    tab1, tab2 = st.tabs(["📝 Nueva Ruta", "⚙️ Configuración"])
    
    with tab2:
        valores = _panel_datos_generales(valores)
    
    with tab1:
        # Generar ID
        id_ruta = generar_id()
        st.markdown(f"**ID de Ruta:** `{id_ruta}`")
        
        # Fecha
        fecha = st.date_input("📅 Fecha", value=datetime.now().date(), key="sl_fecha")
        
        divider()
        
        # Tipo de ruta con badges
        st.markdown("### 🛣️ Tipo de Ruta")
        tipo_ruta = st.selectbox(
            "Selecciona el tipo",
            TIPOS_RUTA,
            format_func=lambda x: {
                "NB": "🔼 NB - Northbound",
                "SB": "🔽 SB - Southbound",
                "D2DNB": "🚪 D2DNB - Door to Door Northbound",
                "D2DSB": "🚪 D2DSB - Door to Door Southbound",
                "Empty": "⚪ Empty - Ruta Vacía"
            }.get(x, x),
            key="sl_tipo"
        )
        
        # Dirección (solo si no es Empty)
        if tipo_ruta != "Empty":
            direccion = st.selectbox(
                "Dirección de Viaje",
                DIRECCIONES,
                key="sl_direccion",
                help="Subida usa PxM Owner Subidas, Bajada usa PxM Owner Bajadas"
            )
        else:
            direccion = "Subida"  # Default para Empty
            alert("info", "ℹ️ Las rutas vacías se calculan con tarifa de Subida")
        
        divider()
        
        # Cliente y rutas
        st.markdown("### 📍 Información de la Ruta")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if tipo_ruta != "Empty":
                cliente = st.text_input(
                    "👤 Cliente",
                    placeholder="Nombre del cliente",
                    key="sl_cliente"
                )
            else:
                st.markdown("**👤 Cliente**")
                st.markdown("""
                <div class='info-tooltip'>
                ⚪ Las rutas vacías no requieren cliente
                </div>
                """, unsafe_allow_html=True)
                cliente = ""
            
            ruta_usa = st.text_input(
                "🛣️ Ruta USA (Origen → Destino)",
                placeholder="Ej: Laredo, TX - Dallas, TX",
                key="sl_ruta_usa",
                help="Formato: Ciudad Origen - Ciudad Destino"
            )
        
        with col2:
            if tipo_ruta == "Empty":
                st.markdown("**📏 Miles Load (Millas Cargadas)**")
                st.markdown("""
                <div class='info-tooltip'>
                ⚪ Las rutas vacías no tienen millas cargadas
                </div>
                """, unsafe_allow_html=True)
                miles_load = 0.0
            else:
                miles_load = st.number_input(
                    "📏 Miles Load (Millas Cargadas)",
                    min_value=0.0,
                    step=1.0,
                    key="sl_miles_load"
                )
            
            miles_empty = st.number_input(
                "⚪ Miles Empty (Millas Vacías)",
                min_value=0.0,
                step=1.0,
                key="sl_miles_empty"
            )
        
        # Short Miles (calculado automáticamente o manual)
        short_miles = st.number_input(
            "📐 Short Miles",
            min_value=0.0,
            value=miles_load,  # Por defecto igual a miles load
            step=1.0,
            key="sl_short_miles",
            help="Millas para cálculo específico (usualmente = Miles Load)"
        )
        
        divider()
        
        # Ingresos (solo si no es Empty)
        if tipo_ruta != "Empty":
            st.markdown("### 💵 Ingresos")
            
            col3, col4, col5, col6 = st.columns(4)
            
            with col3:
                flete_usa = st.number_input(
                    "Flete USA ($)",
                    min_value=0.0,
                    step=100.0,
                    key="sl_flete_usa"
                )
            
            with col4:
                fuel = st.number_input(
                    "Fuel ($)",
                    min_value=0.0,
                    step=10.0,
                    key="sl_fuel"
                )
            
            with col5:
                cruce = st.number_input(
                    "Cruce ($)",
                    min_value=0.0,
                    step=10.0,
                    key="sl_cruce"
                )
            
            with col6:
                reembolso_cruce = st.number_input(
                    "Reembolso Cruce ($)",
                    min_value=0.0,
                    value=5.0,  # Valor común según tu BD
                    step=1.0,
                    key="sl_reembolso_cruce",
                    help="Usualmente $5.00"
                )
            
            divider()
            
            # Método de costo indirecto
            st.markdown("### 📊 Método de Costos Indirectos")
            modo_ci = st.radio(
                "Selecciona el método para esta ruta:",
                ["CXM", "Porcentaje"],
                horizontal=True,
                key="sl_modo_ci",
                help="CXM: Costo por milla total | Porcentaje: % sobre ingreso total"
            )
        else:
            flete_usa = 0.0
            fuel = 0.0
            cruce = 0.0
            reembolso_cruce = 5.0  # Valor por defecto
            modo_ci = "CXM"  # No importa para Empty
            
            st.markdown("""
            <div class='info-tooltip'>
            ℹ️ <strong>Rutas Empty</strong>: No generan ingresos y no se les aplican costos indirectos.
            Solo se calculan los costos directos (pago al owner por millas vacías).
            </div>
            """, unsafe_allow_html=True)
        
        divider()
        
        # Botón calcular
        if st.button("🧮 Calcular Ruta", key="sl_calc", type="primary", use_container_width=True):
            # Validaciones
            errores = []
            
            if not ruta_usa:
                errores.append("⚠️ Ingresa la ruta USA (Origen - Destino)")
            if tipo_ruta != "Empty" and not cliente:
                errores.append("⚠️ Ingresa el cliente")
            if tipo_ruta != "Empty" and miles_load <= 0:
                errores.append("⚠️ Ingresa miles load (millas cargadas)")
            if tipo_ruta == "Empty" and miles_empty <= 0:
                errores.append("⚠️ Las rutas Empty deben tener miles empty")
            
            if errores:
                for err in errores:
                    st.error(err)
            else:
                # Calcular
                resultado = calcular_ruta_setlogis(
                    tipo_ruta=tipo_ruta,
                    direccion=direccion,
                    ruta_usa=normalizar_texto(ruta_usa),
                    cliente=normalizar_texto(cliente),
                    miles_load=miles_load,
                    miles_empty=miles_empty,
                    flete_usa=flete_usa,
                    fuel=fuel,
                    cruce=cruce,
                    reembolso_cruce=reembolso_cruce,
                    modo_costo_indirecto=modo_ci,
                    valores=valores,
                )
                
                # Guardar en session state
                st.session_state["sl_resultado"] = resultado
                st.session_state["sl_datos"] = {
                    "id_ruta": id_ruta,
                    "fecha": str(fecha),
                    "tipo_ruta": tipo_ruta,
                    "direccion": direccion.upper(),
                    "cliente": normalizar_texto(cliente),
                    "ruta_usa": normalizar_texto(ruta_usa),
                    "miles_load": miles_load,
                    "miles_empty": miles_empty,
                    "short_miles": short_miles,
                }
                
                alert("success", "✅ Ruta calculada exitosamente")
        
        # Mostrar resultados
        if "sl_resultado" in st.session_state:
            _mostrar_resumen(st.session_state["sl_resultado"], st.session_state["sl_datos"]["tipo_ruta"])
            
            # Botón guardar
            divider()
            if st.button("💾 Guardar en Base de Datos", key="sl_save", type="primary", use_container_width=True):
                try:
                    datos = st.session_state["sl_datos"]
                    r = st.session_state["sl_resultado"]
                    
                    # Preparar fila según estructura de BD existente
                    fila = {
                        "ID_Ruta": datos["id_ruta"],
                        "Fecha": datos["fecha"],
                        "Tipo_Viaje": datos["tipo_ruta"],
                        "Direccion": datos["direccion"],
                        "Cliente": datos["cliente"],
                        "Ruta_MEX": "",  # No usado por ahora
                        "Ruta_USA": datos["ruta_usa"],
                        "Proveedor_MEX": "",  # No usado por ahora
                        
                        # Millas
                        "Miles_Load": datos["miles_load"],
                        "Miles_Empty": datos["miles_empty"],
                        "Short_Miles": datos["short_miles"],
                        
                        # Ingresos
                        "Flete_MEX": 0.0,  # No usado por ahora
                        "Flete_USA": r["Flete_USA"],
                        "Fuel": r["Fuel"],
                        "Flete_Fuel": r["Flete_Fuel"],
                        "Cruce": r["Cruce"],
                        "Ingreso_Global": r["Ingreso_Global"],
                        "Reembolso_Cruce": r["Reembolso_Cruce"],
                        
                        # Tasas y sueldos
                        "Tasa_Owner_Cargado": r["Tasa_Owner_Cargado"],
                        "Tasa_Owner_Vacio": r["Tasa_Owner_Vacio"],
                        "Sueldo_Owner_Cargado": r["Sueldo_Owner_Cargado"],
                        "Sueldo_Owner_Vacio": r["Sueldo_Owner_Vacio"],
                        "Total_Costos_Directos": r["Total_Costos_Directos"],
                        
                        # Costos indirectos
                        "CXM_Indirecto": r["CXM_Indirecto"],
                        "Costo_Indirecto": r["Costo_Indirecto"],
                        
                        # Utilidades y porcentajes
                        "Pct_CD": r["Pct_CD"],
                        "Ut_Bruta": r["Ut_Bruta"],
                        "Pct_Ut_Bruta": r["Pct_Ut_Bruta"],
                        "Pct_CI": r["Pct_CI"],
                        "Utilidad_Neta": r["Utilidad_Neta"],
                        "Pct_Ut_Neta": r["Pct_Ut_Neta"],
                        
                        # Metadata
                        "created_by": current_user(),
                        "created_at": _now_iso(),
                    }
                    
                    fila_limpia = limpiar_fila_json(fila)
                    resp = supabase.table(TABLE_RUTAS).insert(fila_limpia).execute()
                    
                    st.success(f"✅ Ruta {datos['id_ruta']} guardada exitosamente")
                    
                    # Limpiar session state
                    del st.session_state["sl_resultado"]
                    del st.session_state["sl_datos"]
                    
                    # Limpiar cache de ID
                    _ultimo_id.clear()
                    
                    st.balloons()
                    
                except Exception as e:
                    st.error(f"❌ Error al guardar: {str(e)}")
