"""
consulta_ruta.py – Set Logis Plus
Consulta y visualización de rutas guardadas.
Sin HTML propio: usa componentes de ui/components y helpers de _shared.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from services.supabase_client import get_supabase_client
from ui.components import section_header, alert, divider, kpi_row, status_badge
from ._shared import (
    TABLE_RUTAS,
    EXTRAS_USA,
    safe,
    cargar_datos_generales,
)


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES DE PRESENTACIÓN
# ─────────────────────────────────────────────────────────────────────────────
_TIPO_LABEL = {
    "NB":    "Subida NB",
    "SB":    "Bajada SB",
    "D2DNB": "Door D2D Subida",
    "D2DSB": "Door D2D Bajada",
    "Empty": "Vacío",
}

_TIPO_ICONO = {
    "NB":    "⬆️",
    "SB":    "⬇️",
    "D2DNB": "🚪⬆️",
    "D2DSB": "🚪⬇️",
    "Empty": "⬜",
}


# ─────────────────────────────────────────────────────────────────────────────
# CACHE
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=60)
def _cargar_rutas(table: str) -> pd.DataFrame:
    sb = get_supabase_client()
    if sb is None:
        return pd.DataFrame()
    try:
        resp = sb.table(table).select("*").order("Fecha", desc=True).execute()
        df = pd.DataFrame(resp.data or [])
        if not df.empty and "Fecha" in df.columns:
            df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d")
        return df
    except Exception:
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS DE FORMATO
# ─────────────────────────────────────────────────────────────────────────────
def _usd(v) -> str:
    return f"${safe(v):,.2f}"


def _pct(v) -> str:
    return f"{safe(v) * 100:.1f}%"


def _tipo_str(tipo: str) -> str:
    icono = _TIPO_ICONO.get(tipo, "🚛")
    label = _TIPO_LABEL.get(tipo, tipo)
    return f"{icono} {label}"


# ─────────────────────────────────────────────────────────────────────────────
# PANEL DE DETALLE (expander)
# ─────────────────────────────────────────────────────────────────────────────
def _panel_detalle(row: pd.Series) -> None:
    """Muestra el detalle financiero completo de una ruta dentro de un expander."""

    tipo      = str(row.get("Tipo_Viaje", ""))
    tiene_mx  = tipo in {"D2DNB", "D2DSB"}
    tiene_cruce = bool(row.get("Incluye_Cruce", False))

    # ── KPIs principales ────────────────────────────────────────────────────
    ut_neta  = safe(row.get("Utilidad_Neta"))
    ut_bruta = safe(row.get("Utilidad_Bruta"))
    ut_color = "#10b981" if ut_neta >= 0 else "#DC2626"

    kpi_row([
        {"icono": "💵", "label": "Ingreso Total",  "valor": _usd(row.get("Ingreso_Global")),  "color": "#1B2266"},
        {"icono": "📦", "label": "Costo Directo",  "valor": _usd(row.get("Costo_Directo")),   "color": "#6B7280"},
        {"icono": "📉", "label": "Costo Indirecto","valor": _usd(row.get("Costo_Indirecto")), "color": "#F59E0B"},
        {"icono": "📊", "label": "Ut. Bruta",      "valor": _usd(ut_bruta),                   "color": "#3B82F6"},
        {"icono": "✅", "label": "Ut. Neta",        "valor": _usd(ut_neta),                    "color": ut_color},
    ])

    # ── Columnas: Ingreso / Costo / Millas ──────────────────────────────────
    c1, c2, c3 = st.columns(3)

    with c1:
        section_header("💰", "Ingresos")
        st.caption(f"Flete USA:    **{_usd(row.get('Flete_USA'))}**")
        st.caption(f"Fuel:          **{_usd(row.get('Fuel'))}**")
        if tiene_cruce:
            st.caption(f"Cruce:         **{_usd(row.get('Ingreso_Cruce'))}**")
        if tiene_mx:
            st.caption(f"Flete MX:      **{_usd(row.get('Ingreso_MX'))}**")
        extras_ing = safe(row.get("Extras_Ingreso"))
        if extras_ing:
            st.caption(f"Extras cobrados: **{_usd(extras_ing)}**")

    with c2:
        section_header("💸", "Costos")
        st.caption(f"Pago Owner Cargado: **{_usd(row.get('Pago_Owner_Cargado'))}**")
        st.caption(f"Pago Owner Vacío:   **{_usd(row.get('Pago_Owner_Vacio'))}**")
        st.caption(f"Pago Owner Total:   **{_usd(row.get('Pago_Owner_Total'))}**")
        if tiene_cruce:
            st.caption(f"Costo Cruce:        **{_usd(row.get('Costo_Cruce'))}**")
        if tiene_mx:
            st.caption(f"Costo Flete MX:     **{_usd(row.get('Costo_MX'))}**")
        extras_costo = safe(row.get("Extras_Costo"))
        if extras_costo:
            st.caption(f"Extras (no cobrados): **{_usd(extras_costo)}**")

    with c3:
        section_header("🛣️", "Millas y Tarifa")
        st.caption(f"Miles Load:    **{safe(row.get('Miles_Load')):.0f} mi**")
        st.caption(f"Short Miles:   **{safe(row.get('Short_Miles')):.0f} mi**")
        st.caption(f"Miles Empty:   **{safe(row.get('Miles_Empty')):.0f} mi**")
        st.caption(f"Millas Totales:**{safe(row.get('Millas_Totales')):.0f} mi**")
        st.caption(f"PxM Cargado:   **{_usd(row.get('PxM_Cargado'))}/mi**")
        st.caption(f"PxM Vacío:     **{_usd(row.get('PxM_Vacio'))}/mi**")
        modalidad = str(row.get("Modalidad") or "")
        if modalidad == "Desglosada":
            st.caption(f"CXM Flete:     **{_usd(row.get('CXM_Flete'))}/mi**")
            st.caption(f"CXM Fuel:      **{_usd(row.get('CXM_Fuel'))}/mi**")
        else:
            st.caption(f"Flat:          **{_usd(row.get('Flete_Flat'))}**")

    divider()

    # ── Porcentajes ──────────────────────────────────────────────────────────
    pc1, pc2, pc3, pc4 = st.columns(4)
    pc1.metric("% Costo Directo",   _pct(row.get("Pct_Costo_Directo")))
    pc2.metric("% Costo Indirecto", _pct(row.get("Pct_Costo_Indirecto")))
    pc3.metric("% Ut. Bruta",       _pct(row.get("Pct_Ut_Bruta")))
    pc4.metric("% Ut. Neta",        _pct(row.get("Pct_Ut_Neta")))

    # ── Extras individuales ──────────────────────────────────────────────────
    extras_presentes = []
    for extra in EXTRAS_USA:
        col_monto   = f"Extra_{extra.replace(' ', '_')}"
        col_cobrado = f"Extra_{extra.replace(' ', '_')}_Cobrado"
        monto   = safe(row.get(col_monto, 0))
        cobrado = bool(row.get(col_cobrado, False))
        if monto > 0:
            extras_presentes.append((extra, monto, cobrado))

    if extras_presentes:
        divider()
        section_header("➕", "Extras aplicados")
        for nombre, monto, cobrado in extras_presentes:
            tag = status_badge("Cobrado al cliente", "concluido") if cobrado else status_badge("Solo costo", "pendiente")
            st.markdown(
                f"**{nombre}**: {_usd(monto)} &nbsp; {tag}",
                unsafe_allow_html=True,
            )

    # ── Datos de operación ───────────────────────────────────────────────────
    divider()
    section_header("📋", "Datos de Operación")
    op1, op2, op3 = st.columns(3)
    op1.caption(f"Modo:       **{row.get('Modo', '—')}**")
    op1.caption(f"Modalidad:  **{row.get('Modalidad', '—')}**")
    op1.caption(f"TC USD/MXP: **{safe(row.get('TC_USD_MXP')):.2f}**")
    op2.caption(f"Ruta USA:   **{row.get('Ruta_USA', '—')}**")
    if tiene_cruce:
        op2.caption(f"Tipo Cruce:  **{row.get('Tipo_Cruce', '—')}**")
        op2.caption(f"Carga Cruce: **{row.get('Tipo_Carga_Cruce', '—')}**")
    if tiene_mx:
        op3.caption(f"Origen MX:  **{row.get('Origen_MX', '—')}**")
        op3.caption(f"Destino MX: **{row.get('Destino_MX', '—')}**")
    op3.caption(f"Usuario:    **{row.get('Usuario', '—')}**")
    op3.caption(f"Fecha:      **{row.get('Fecha', '—')}**")


# ─────────────────────────────────────────────────────────────────────────────
# CARD DE RUTA (vista compacta en lista)
# ─────────────────────────────────────────────────────────────────────────────
def _ruta_card(row: pd.Series) -> None:
    """Tarjeta compacta con st.container + métricas nativas."""
    tipo     = str(row.get("Tipo_Viaje", ""))
    ut_neta  = safe(row.get("Utilidad_Neta"))
    pct_neta = safe(row.get("Pct_Ut_Neta")) * 100

    with st.container(border=True):
        # Encabezado
        h1, h2 = st.columns([3, 1])
        with h1:
            st.markdown(
                f"**{row.get('ID_Ruta', '—')}** &nbsp;·&nbsp; "
                f"{_tipo_str(tipo)} &nbsp;·&nbsp; "
                f"_{row.get('Cliente', '—')}_"
            )
            st.caption(f"🛣️ {row.get('Ruta_USA', '—')}  |  📅 {row.get('Fecha', '—')}  |  👤 {row.get('Usuario', '—')}")
        with h2:
            color_ut = "#10b981" if ut_neta >= 0 else "#DC2626"
            st.markdown(
                f'<div style="text-align:right;">'
                f'<div style="font-size:1.1rem;font-weight:800;color:{color_ut};">{_usd(ut_neta)}</div>'
                f'<div style="font-size:0.72rem;color:{color_ut};">{pct_neta:.1f}% Ut. Neta</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        # KPIs rápidos en columnas
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Ingreso",     _usd(row.get("Ingreso_Global")))
        m2.metric("Costo Total", _usd(row.get("Costo_Total")))
        m3.metric("Ut. Bruta",   _usd(row.get("Utilidad_Bruta")))
        m4.metric("Miles Load",  f"{safe(row.get('Miles_Load')):.0f} mi")

        # Detalle expandible
        with st.expander("Ver detalle completo"):
            _panel_detalle(row)


# ─────────────────────────────────────────────────────────────────────────────
# RENDER PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────
def render() -> None:
    sb = get_supabase_client()
    if sb is None:
        alert("error", "Supabase no configurado.")
        return

    # ── Controles superiores ─────────────────────────────────────────────────
    r1, r2 = st.columns([1, 5])
    with r1:
        if st.button("🔄 Recargar", key="sl_cons_reload"):
            _cargar_rutas.clear()
            st.rerun()

    df = _cargar_rutas(TABLE_RUTAS)

    if df.empty:
        alert("warn", "No hay rutas guardadas todavía.")
        alert("info", "Captura una ruta primero desde la pestaña Captura de Rutas.")
        return

    # ── KPIs resumen ─────────────────────────────────────────────────────────
    total_rutas   = len(df)
    ing_total     = df["Ingreso_Global"].apply(safe).sum() if "Ingreso_Global" in df.columns else 0
    ut_total      = df["Utilidad_Neta"].apply(safe).sum()  if "Utilidad_Neta"  in df.columns else 0
    pct_media     = (ut_total / ing_total * 100) if ing_total else 0

    kpi_row([
        {"icono": "🗂️", "label": "Rutas guardadas", "valor": str(total_rutas),           "color": "#1B2266"},
        {"icono": "💵", "label": "Ingreso acumulado","valor": _usd(ing_total),             "color": "#3B82F6"},
        {"icono": "✅", "label": "Ut. Neta acum.",   "valor": _usd(ut_total),              "color": "#10b981" if ut_total >= 0 else "#DC2626"},
        {"icono": "📊", "label": "% Ut. Neta media", "valor": f"{pct_media:.1f}%",         "color": "#F59E0B"},
    ])

    divider()

    # ── Filtros ───────────────────────────────────────────────────────────────
    section_header("🔍", "Filtros")
    f1, f2, f3, f4 = st.columns(4)

    tipos_disponibles = sorted(df["Tipo_Viaje"].dropna().unique().tolist()) if "Tipo_Viaje" in df.columns else []
    clientes_disp     = sorted(df["Cliente"].dropna().unique().tolist())    if "Cliente"    in df.columns else []

    f_tipo    = f1.selectbox("Tipo de viaje",  ["Todos"] + tipos_disponibles, key="sl_cons_tipo")
    f_cliente = f2.selectbox("Cliente",        ["Todos"] + clientes_disp,     key="sl_cons_cli")
    f_texto   = f3.text_input("Buscar ruta USA o ID", key="sl_cons_texto", placeholder="LAREDO, SL-001...")
    f_modo    = f4.selectbox("Vista",          ["Cards", "Tabla"], key="sl_cons_vista")

    # Aplicar filtros
    dff = df.copy()
    if f_tipo != "Todos":
        dff = dff[dff["Tipo_Viaje"] == f_tipo]
    if f_cliente != "Todos":
        dff = dff[dff["Cliente"] == f_cliente]
    if f_texto.strip():
        mask = (
            dff.get("Ruta_USA", pd.Series(dtype=str)).astype(str).str.contains(f_texto, case=False, na=False) |
            dff.get("ID_Ruta",  pd.Series(dtype=str)).astype(str).str.contains(f_texto, case=False, na=False)
        )
        dff = dff[mask]

    if dff.empty:
        alert("info", "No hay rutas que coincidan con los filtros aplicados.")
        return

    st.caption(f"Mostrando **{len(dff)}** de **{total_rutas}** rutas")
    divider()

    # ── Vista Cards ───────────────────────────────────────────────────────────
    if f_modo == "Cards":
        for _, row in dff.iterrows():
            _ruta_card(row)

    # ── Vista Tabla ───────────────────────────────────────────────────────────
    else:
        cols_tabla = [
            "ID_Ruta", "Fecha", "Tipo_Viaje", "Cliente", "Ruta_USA",
            "Miles_Load", "Ingreso_Global", "Costo_Directo",
            "Utilidad_Bruta", "Utilidad_Neta", "Pct_Ut_Neta",
            "Modo", "Modalidad", "Usuario",
        ]
        cols_presentes = [c for c in cols_tabla if c in dff.columns]
        df_tabla = dff[cols_presentes].copy()

        # Formatear columnas numéricas
        for col in ["Ingreso_Global", "Costo_Directo", "Utilidad_Bruta", "Utilidad_Neta"]:
            if col in df_tabla.columns:
                df_tabla[col] = df_tabla[col].apply(lambda v: f"${safe(v):,.2f}")
        if "Pct_Ut_Neta" in df_tabla.columns:
            df_tabla["Pct_Ut_Neta"] = df_tabla["Pct_Ut_Neta"].apply(lambda v: f"{safe(v)*100:.1f}%")
        if "Miles_Load" in df_tabla.columns:
            df_tabla["Miles_Load"] = df_tabla["Miles_Load"].apply(lambda v: f"{safe(v):.0f} mi")

        st.dataframe(df_tabla, use_container_width=True, hide_index=True)
