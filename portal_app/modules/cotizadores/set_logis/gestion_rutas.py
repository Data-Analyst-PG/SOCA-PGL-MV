from ui.components import section_header, alert, divider
"""
consulta_ruta.py – Set Logis
Consulta y visualización de rutas guardadas
"""

import streamlit as st
import pandas as pd

from services.supabase_client import get_supabase_client
from ._shared import TABLE_RUTAS, safe


# ─────────────────────────────────────────────
# CACHE DE DATOS
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=60)
def _cargar_rutas(table: str) -> pd.DataFrame:
    supabase = get_supabase_client()
    if supabase is None:
        return pd.DataFrame()
    try:
        resp = supabase.table(table).select("*").order("Fecha", desc=True).execute()
        df = pd.DataFrame(resp.data)
        if not df.empty and "Fecha" in df.columns:
            df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d")
        return df
    except Exception:
        return pd.DataFrame()


# ─────────────────────────────────────────────
# ESTILOS
# ─────────────────────────────────────────────
def aplicar_estilos():
    st.markdown("""
    <style>
    .ruta-card {
        background: white;
        padding: 1.5rem;
        border-radius: 12px;
        border-left: 4px solid #3b82f6;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin-bottom: 1rem;
    }
    
    .ruta-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 1rem;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid #e5e7eb;
    }
    
    .ruta-id {
        font-size: 1.25rem;
        font-weight: 700;
        color: #1e40af;
    }
    
    .ruta-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    
    .badge-nb { background: #dbeafe; color: #3b82f6; }
    .badge-sb { background: #ede9fe; color: #8b5cf6; }
    .badge-d2dnb { background: #d1fae5; color: #10b981; }
    .badge-d2dsb { background: #fef3c7; color: #f59e0b; }
    .badge-empty { background: #f3f4f6; color: #6b7280; }
    
    .ruta-info {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 0.75rem;
        margin-top: 1rem;
    }
    
    .info-item {
        font-size: 0.875rem;
    }
    
    .info-label {
        color: #64748b;
        font-weight: 500;
    }
    
    .info-value {
        color: #0f172a;
        font-weight: 600;
    }
    
    .metric-positive {
        color: #10b981;
        font-weight: 700;
    }
    
    .metric-negative {
        color: #ef4444;
        font-weight: 700;
    }
    </style>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────
# COMPONENTES
# ─────────────────────────────────────────────
def badge_tipo(tipo):
    badges = {
        "NB": ("🔼 NB", "badge-nb"),
        "SB": ("🔽 SB", "badge-sb"),
        "D2DNB": ("🚪 D2DNB", "badge-d2dnb"),
        "D2DSB": ("🚪 D2DSB", "badge-d2dsb"),
        "Empty": ("⚪ Empty", "badge-empty"),
    }
    label, clase = badges.get(tipo, (tipo, "badge-nb"))
    return f"<span class='ruta-badge {clase}'>{label}</span>"


def mostrar_ruta_card(row):
    """Muestra una ruta en formato card moderno"""
    util_neta = safe(row.get("Utilidad_Neta", 0))
    color_border = "#10b981" if util_neta >= 0 else "#ef4444"
    color_util = "metric-positive" if util_neta >= 0 else "metric-negative"
    
    st.markdown(f"""
    <div class='ruta-card' style='border-left-color: {color_border};'>
        <div class='ruta-header'>
            <div class='ruta-id'>{row.get('ID_Ruta', 'N/A')}</div>
            {badge_tipo(row.get('Tipo_Viaje', 'N/A'))}
        </div>
        
        <div class='ruta-info'>
            <div class='info-item'>
                <span class='info-label'>📅 Fecha:</span>
                <span class='info-value'>{row.get('Fecha', 'N/A')}</span>
            </div>
            
            <div class='info-item'>
                <span class='info-label'>👤 Cliente:</span>
                <span class='info-value'>{row.get('Cliente', 'N/A') or 'Sin cliente'}</span>
            </div>
            
            <div class='info-item'>
                <span class='info-label'>🛣️ Ruta USA:</span>
                <span class='info-value'>{row.get('Ruta_USA', 'N/A')}</span>
            </div>
            
            <div class='info-item'>
                <span class='info-label'>🔄 Dirección:</span>
                <span class='info-value'>{row.get('Direccion', 'N/A')}</span>
            </div>
            
            <div class='info-item'>
                <span class='info-label'>📏 Miles Load:</span>
                <span class='info-value'>{safe(row.get('Miles_Load', 0)):,.0f}</span>
            </div>
            
            <div class='info-item'>
                <span class='info-label'>⚪ Miles Empty:</span>
                <span class='info-value'>{safe(row.get('Miles_Empty', 0)):,.0f}</span>
            </div>
            
            <div class='info-item'>
                <span class='info-label'>💵 Ingreso Global:</span>
                <span class='info-value'>${safe(row.get('Ingreso_Global', 0)):,.2f}</span>
            </div>
            
            <div class='info-item'>
                <span class='info-label'>💰 Utilidad Neta:</span>
                <span class='{color_util}'>${util_neta:,.2f}</span>
                <span style='font-size: 0.75rem; color: #64748b;'>
                    ({safe(row.get('Pct_Ut_Neta', 0)):.1f}%)
                </span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────
# RENDER PRINCIPAL
# ─────────────────────────────────────────────
def render():
    aplicar_estilos()
    
    st.markdown("""
    <div style='background: linear-gradient(90deg, #dbeafe 0%, transparent 100%); 
                padding: 1rem; border-radius: 8px; border-left: 4px solid #3b82f6; margin-bottom: 1.5rem;'>
        <h1 style='color: #1e40af; margin: 0;'>🔍 Consulta de Rutas</h1>
        <p style='color: #64748b; margin: 0.5rem 0 0 0;'>Visualiza y filtra rutas guardadas</p>
    </div>
    """, unsafe_allow_html=True)
    
    supabase = get_supabase_client()
    if supabase is None:
        alert("error", "⚠️ Supabase no configurado")
        return
    
    # Botón recargar
    col_btn, _ = st.columns([1, 5])
    with col_btn:
        if st.button("🔄 Recargar", key="sl_reload", use_container_width=True):
            _cargar_rutas.clear()
            st.rerun()
    
    # Cargar datos
    df = _cargar_rutas(TABLE_RUTAS)
    
    if df.empty:
        alert("info", "📭 No hay rutas guardadas todavía")
        return
    
    # Filtros
    st.markdown("### 🔎 Filtros")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        tipos_disponibles = ["Todos"] + sorted(df["Tipo_Viaje"].dropna().unique().tolist())
        filtro_tipo = st.selectbox("Tipo de Ruta", tipos_disponibles, key="sl_filtro_tipo")
    
    with col2:
        clientes_disponibles = ["Todos"] + sorted(df["Cliente"].dropna().unique().tolist())
        filtro_cliente = st.selectbox("Cliente", clientes_disponibles, key="sl_filtro_cliente")
    
    with col3:
        meses = df["Fecha"].str[:7].unique().tolist() if "Fecha" in df.columns else []
        meses_disponibles = ["Todos"] + sorted(meses, reverse=True)
        filtro_mes = st.selectbox("Mes", meses_disponibles, key="sl_filtro_mes")
    
    # Aplicar filtros
    df_filtrado = df.copy()
    
    if filtro_tipo != "Todos":
        df_filtrado = df_filtrado[df_filtrado["Tipo_Viaje"] == filtro_tipo]
    
    if filtro_cliente != "Todos":
        df_filtrado = df_filtrado[df_filtrado["Cliente"] == filtro_cliente]
    
    if filtro_mes != "Todos":
        df_filtrado = df_filtrado[df_filtrado["Fecha"].str.startswith(filtro_mes)]
    
    st.markdown(f"**Mostrando {len(df_filtrado)} de {len(df)} rutas**")
    
    divider()
    
    # Vista de rutas
    modo_vista = st.radio(
        "Modo de visualización:",
        ["📋 Cards", "📊 Tabla"],
        horizontal=True,
        key="sl_modo_vista"
    )
    
    if modo_vista == "📋 Cards":
        # Vista de cards
        for _, row in df_filtrado.iterrows():
            mostrar_ruta_card(row)
    else:
        # Vista de tabla
        columnas_tabla = [
            "ID_Ruta", "Fecha", "Tipo_Viaje", "Direccion", "Cliente", 
            "Ruta_USA", "Miles_Load", "Miles_Empty",
            "Ingreso_Global", "Utilidad_Neta", "Pct_Ut_Neta"
        ]
        
        df_tabla = df_filtrado[columnas_tabla].copy()
        
        # Formatear columnas numéricas
        df_tabla["Miles_Load"] = df_tabla["Miles_Load"].apply(lambda x: f"{safe(x):,.0f}")
        df_tabla["Miles_Empty"] = df_tabla["Miles_Empty"].apply(lambda x: f"{safe(x):,.0f}")
        df_tabla["Ingreso_Global"] = df_tabla["Ingreso_Global"].apply(lambda x: f"${safe(x):,.2f}")
        df_tabla["Utilidad_Neta"] = df_tabla["Utilidad_Neta"].apply(lambda x: f"${safe(x):,.2f}")
        df_tabla["Pct_Ut_Neta"] = df_tabla["Pct_Ut_Neta"].apply(lambda x: f"{safe(x):.1f}%")
        
        st.dataframe(
            df_tabla,
            use_container_width=True,
            hide_index=True,
            column_config={
                "ID_Ruta": "ID",
                "Tipo_Viaje": "Tipo",
                "Direccion": "Dir",
                "Ruta_USA": "Ruta",
                "Miles_Load": "Mi. Load",
                "Miles_Empty": "Mi. Empty",
                "Ingreso_Global": "Ingreso",
                "Utilidad_Neta": "Utilidad",
                "Pct_Ut_Neta": "%",
            }
        )
    
    # Estadísticas
    divider()
    st.markdown("### 📊 Estadísticas del Filtro")
    
    col_a, col_b, col_c, col_d = st.columns(4)
    
    with col_a:
        total_rutas = len(df_filtrado)
        st.metric("Total Rutas", total_rutas)
    
    with col_b:
        total_millas = safe(df_filtrado["Miles_Load"].sum()) + safe(df_filtrado["Miles_Empty"].sum())
        st.metric("Total Millas", f"{total_millas:,.0f}")
    
    with col_c:
        total_ingreso = safe(df_filtrado["Ingreso_Global"].sum())
        st.metric("Ingreso Total", f"${total_ingreso:,.2f}")
    
    with col_d:
        total_utilidad = safe(df_filtrado["Utilidad_Neta"].sum())
        color = "normal" if total_utilidad >= 0 else "inverse"
        st.metric("Utilidad Total", f"${total_utilidad:,.2f}", delta_color=color)
