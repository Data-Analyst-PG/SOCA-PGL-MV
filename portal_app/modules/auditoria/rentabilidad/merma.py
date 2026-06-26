# portal_app/modules/auditoria/rentabilidad/merma.py
# ─────────────────────────────────────────────────────────────────────────────
# Tab: Merma por Cliente
# Muestra cuánto le falta vender a cada cliente para cubrir sus costos
# indirectos reales. Lee los viajes cargados de la tabla rentabilidad_viajes
# y cruza con el catálogo de cuentas para aplicar el CI correcto por tipo.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

from io import BytesIO

import pandas as pd
import streamlit as st

from services.supabase_client import get_authed_client as get_supabase_client
from ui.components import section_header, alert, divider, kpi_row

# ── Constantes ────────────────────────────────────────────────────────────────
TABLE_VIAJES  = "rentabilidad_viajes"
TABLE_CUENTAS = "rentabilidad_cuentas"

# Tasas de respaldo (del CatalogoBV) si no hay cuentas en BD
CXKM_DEFAULT = {"T1": 4.005935, "T2": 3.174808, "T3": 3.079793, "T4": 3.502080}

TIPO_COLOR = {
    "T1": "#0077B6",
    "T2": "#2E7D32",
    "T3": "#6D28D9",
    "T4": "#B45309",
}
TIPO_LABEL = {
    "T1": "Retail/CEDIS",
    "T2": "Expo/Imp",
    "T3": "Dedicado",
    "T4": "Alimenticio",
}


# ── Carga de datos ────────────────────────────────────────────────────────────
@st.cache_data(ttl=120, show_spinner=False)
def _cargar_viajes(periodo: str) -> pd.DataFrame:
    sb = get_supabase_client()
    if sb is None:
        return pd.DataFrame()
    try:
        res = (
            sb.table(TABLE_VIAJES)
            .select("cliente,tipo_cliente,kms,tarifa_mxp,cd_real,operacion,fecha")
            .eq("periodo", periodo)
            .execute()
        )
        return pd.DataFrame(res.data or [])
    except Exception as e:
        st.error(f"Error cargando viajes: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=120, show_spinner=False)
def _cargar_tasas_ci() -> dict[str, float]:
    """Devuelve {tipo: costo_por_km} calculado desde el catálogo de cuentas."""
    sb = get_supabase_client()
    if sb is None:
        return CXKM_DEFAULT
    try:
        res = sb.table(TABLE_CUENTAS).select("*").eq("activa", True).eq("driver", "km").execute()
        cuentas = res.data or []
        if not cuentas:
            return CXKM_DEFAULT
        totales = {"T1": 0.0, "T2": 0.0, "T3": 0.0, "T4": 0.0}
        map_pct = {"T1": "pct_t1", "T2": "pct_t2", "T3": "pct_t3", "T4": "pct_t4"}
        for c in cuentas:
            cxkm_cuenta = float(c.get("cxkm_mensual") or 0)
            for tipo, col in map_pct.items():
                totales[tipo] += cxkm_cuenta * float(c.get(col) or 0)
        return totales if any(v > 0 for v in totales.values()) else CXKM_DEFAULT
    except Exception:
        return CXKM_DEFAULT


@st.cache_data(ttl=60, show_spinner=False)
def _periodos_disponibles() -> list[str]:
    sb = get_supabase_client()
    if sb is None:
        return []
    try:
        res = sb.table(TABLE_VIAJES).select("periodo").execute()
        periodos = sorted({r["periodo"] for r in (res.data or []) if r.get("periodo")}, reverse=True)
        return periodos
    except Exception:
        return []


# ── Motor de cálculo ──────────────────────────────────────────────────────────
def _calcular_merma(df: pd.DataFrame, tasas: dict[str, float]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    for col in ["kms", "tarifa_mxp", "cd_real"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df["ci_km"] = df.apply(
        lambda r: r["kms"] * tasas.get(r.get("tipo_cliente", "T2"), CXKM_DEFAULT["T2"]),
        axis=1,
    )
    df["margen_bruto"] = df["tarifa_mxp"] - df["cd_real"]
    df["ut_neta"]      = df["margen_bruto"] - df["ci_km"]
    df["merma"]        = -df["ut_neta"]   # positivo = no cubre, negativo = excedente

    grp = df.groupby(["cliente", "tipo_cliente"]).agg(
        viajes       =("cliente", "count"),
        kms          =("kms", "sum"),
        tarifa       =("tarifa_mxp", "sum"),
        cd_real      =("cd_real", "sum"),
        ci_km        =("ci_km", "sum"),
        margen_bruto =("margen_bruto", "sum"),
        ut_neta      =("ut_neta", "sum"),
        merma        =("merma", "sum"),
    ).reset_index()

    grp["mb_pct"] = grp.apply(
        lambda r: r["margen_bruto"] / r["tarifa"] if r["tarifa"] else 0, axis=1
    )
    grp["ut_pct"] = grp.apply(
        lambda r: r["ut_neta"] / r["tarifa"] if r["tarifa"] else 0, axis=1
    )
    return grp.sort_values("merma", ascending=False).reset_index(drop=True)


# ── Render ────────────────────────────────────────────────────────────────────
def render():
    section_header("💸", "Merma por Cliente",
                   "Cuánto le falta a cada cliente para cubrir sus costos indirectos")

    # ── Selector de periodo ───────────────────────────────────────────────────
    periodos = _periodos_disponibles()

    col_p, col_r = st.columns([2, 1])
    with col_p:
        if periodos:
            periodo_sel = st.selectbox("Periodo", options=periodos, key="m_periodo")
        else:
            periodo_sel = st.text_input(
                "Periodo (YYYY-MM)",
                value="2026-06",
                key="m_periodo_manual",
                help="No hay periodos en BD. Ingresa el periodo manualmente.",
            )
    with col_r:
        st.write("")
        if st.button("🔄 Recargar", key="m_reload"):
            st.cache_data.clear()
            st.rerun()

    # ── Carga ─────────────────────────────────────────────────────────────────
    df_raw = _cargar_viajes(periodo_sel)
    tasas  = _cargar_tasas_ci()

    if df_raw.empty:
        alert("info", f"No hay viajes cargados para el periodo {periodo_sel}. "
                      "Ve al tab Semáforo Semanal para subir data operativa.")
        return

    df = _calcular_merma(df_raw.copy(), tasas)
    if df.empty:
        alert("warn", "No se pudo calcular la merma. Verifica los datos.")
        return

    # ── KPIs empresa ─────────────────────────────────────────────────────────
    tot_tarifa = df["tarifa"].sum()
    tot_cd     = df["cd_real"].sum()
    tot_mb     = df["margen_bruto"].sum()
    tot_ci     = df["ci_km"].sum()
    tot_ut     = df["ut_neta"].sum()
    tot_merma  = df["merma"].sum()

    kpi_row([
        {"icono": "💵", "label": "Ingresos totales",  "valor": f"${tot_tarifa:,.0f}",
         "color": "#1B2266"},
        {"icono": "📉", "label": "Costos directos",   "valor": f"${tot_cd:,.0f}",
         "color": "#CC1E1E"},
        {"icono": "📊", "label": "Margen bruto",
         "valor": f"${tot_mb:,.0f}  ({tot_mb/tot_tarifa*100:.1f}%)" if tot_tarifa else "$0",
         "color": "#0077B6"},
        {"icono": "🧮", "label": "CI asignado (km)",  "valor": f"${tot_ci:,.0f}",
         "color": "#E65100"},
        {"icono": "✅" if tot_ut >= 0 else "⚠️",
         "label": "Utilidad neta empresa",
         "valor": f"${tot_ut:,.0f}  ({tot_ut/tot_tarifa*100:.1f}%)" if tot_tarifa else "$0",
         "color": "#2E7D32" if tot_ut >= 0 else "#CC1E1E"},
    ])

    divider()

    # ── Filtros ───────────────────────────────────────────────────────────────
    col_f1, col_f2 = st.columns([2, 2])
    with col_f1:
        buscar = st.text_input("🔍 Buscar cliente", key="m_buscar")
    with col_f2:
        filtro_tipo = st.multiselect(
            "Tipo de cliente",
            options=list(TIPO_LABEL.keys()),
            format_func=lambda t: f"{t} – {TIPO_LABEL[t]}",
            key="m_tipo",
        )

    df_view = df.copy()
    if buscar:
        df_view = df_view[df_view["cliente"].str.contains(buscar, case=False, na=False)]
    if filtro_tipo:
        df_view = df_view[df_view["tipo_cliente"].isin(filtro_tipo)]

    # ── Tabla de merma ────────────────────────────────────────────────────────
    section_header("📋", "Detalle por cliente",
                   "Rojo = no cubre indirectos · Verde = genera excedente")

    COL_WIDTHS = [2.5, 1.5, 1, 1.5, 1.8, 1.8, 1.8, 1.8, 1.5, 1.5]
    HEADERS    = ["Cliente", "Tipo", "Viajes", "KMS",
                  "Ingreso", "CD Real", "Margen Bruto", "CI Asignado",
                  "Ut. Neta", "Merma / Excedente"]

    col_objs = st.columns(COL_WIDTHS)
    for col, hdr in zip(col_objs, HEADERS):
        col.markdown(
            f'<div style="font-size:0.72rem;font-weight:700;color:#6B7280;'
            f'text-transform:uppercase;padding-bottom:4px;">{hdr}</div>',
            unsafe_allow_html=True,
        )

    for _, row in df_view.iterrows():
        cols = st.columns(COL_WIDTHS)
        tipo     = row.get("tipo_cliente") or "T2"
        t_color  = TIPO_COLOR.get(tipo, "#6B7280")
        t_label  = TIPO_LABEL.get(tipo, tipo)
        merma_v  = row["merma"]
        m_color  = "#CC1E1E" if merma_v > 0 else "#2E7D32"
        ut_color = "#CC1E1E" if row["ut_neta"] < 0 else "#2E7D32"

        cols[0].markdown(
            f'<div style="font-weight:600;color:#1B2266;font-size:0.88rem;">'
            f'{row["cliente"]}</div>', unsafe_allow_html=True)
        cols[1].markdown(
            f'<span style="background:{t_color}18;color:{t_color};font-size:0.72rem;'
            f'font-weight:700;padding:2px 8px;border-radius:10px;">'
            f'{t_label}</span>', unsafe_allow_html=True)
        cols[2].markdown(f'<div style="font-size:0.88rem;">{int(row["viajes"]):,}</div>',
                         unsafe_allow_html=True)
        cols[3].markdown(f'<div style="font-size:0.88rem;">{row["kms"]:,.0f}</div>',
                         unsafe_allow_html=True)
        cols[4].markdown(f'<div style="font-size:0.88rem;">${row["tarifa"]:,.0f}</div>',
                         unsafe_allow_html=True)
        cols[5].markdown(f'<div style="font-size:0.88rem;">${row["cd_real"]:,.0f}</div>',
                         unsafe_allow_html=True)
        cols[6].markdown(
            f'<div style="font-size:0.88rem;">${row["margen_bruto"]:,.0f} '
            f'<span style="font-size:0.75rem;color:#6B7280;">({row["mb_pct"]*100:.1f}%)</span>'
            f'</div>', unsafe_allow_html=True)
        cols[7].markdown(f'<div style="font-size:0.88rem;">${row["ci_km"]:,.0f}</div>',
                         unsafe_allow_html=True)
        cols[8].markdown(
            f'<div style="font-size:0.88rem;font-weight:600;color:{ut_color};">'
            f'${row["ut_neta"]:,.0f} '
            f'<span style="font-size:0.75rem;">({row["ut_pct"]*100:.1f}%)</span>'
            f'</div>', unsafe_allow_html=True)
        cols[9].markdown(
            f'<div style="font-size:0.88rem;font-weight:700;color:{m_color};">'
            f'{"▲" if merma_v > 0 else "▼"} ${abs(merma_v):,.0f}</div>',
            unsafe_allow_html=True)

        st.divider()

    # ── Descarga ──────────────────────────────────────────────────────────────
    if not df_view.empty:
        buf = BytesIO()
        df_view.rename(columns={
            "cliente": "Cliente", "tipo_cliente": "Tipo", "viajes": "Viajes",
            "kms": "KMS", "tarifa": "Ingreso MXP", "cd_real": "CD Real",
            "margen_bruto": "Margen Bruto", "mb_pct": "MB%",
            "ci_km": "CI Asignado (km)", "ut_neta": "Ut. Neta",
            "ut_pct": "UT%", "merma": "Merma / Excedente",
        }).to_excel(buf, index=False, sheet_name="Merma")
        st.download_button(
            "📥 Descargar Excel",
            data=buf.getvalue(),
            file_name=f"merma_clientes_{periodo_sel}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="m_download",
        )
