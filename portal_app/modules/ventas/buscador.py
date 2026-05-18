from ui.components import section_header, alert, divider
"""
buscador.py  –  Módulo Ventas
El vendedor filtra por ruta y el sistema busca en TODAS las empresas
devolviendo: empresa, sucursal, ingreso total, y costo por concepto.
El nombre del cliente nunca aparece aquí.
"""

import streamlit as st
import pandas as pd

from services.supabase_client import get_supabase_client


@st.cache_data(show_spinner=False, ttl=120)
def _cargar_todas() -> pd.DataFrame:
    """Lee la vista ventas_buscador_rutas que une todas las empresas."""
    sb = get_supabase_client()
    if sb is None:
        return pd.DataFrame()
    try:
        resp = sb.table("ventas_buscador_rutas").select("*").execute()
        return pd.DataFrame(resp.data or [])
    except Exception as e:
        st.error(f"❌ Error cargando rutas: {e}")
        return pd.DataFrame()


EMPRESA_LABELS = {
    "set_logis":   "🏭 Set Logis Plus",
    "set_freight": "📦 Set Freight LLC",
    "picus":       "🚚 Picus",
    "igloo":       "🚛 Igloo",
    "lincoln":     "🚌 Lincoln",
}


def render():
    from ui.components import page_banner
    page_banner("🔎", "🔎 Buscador de Rutas — Todas las Empresas", "")
    st.caption("Consulta de referencia para vendedores. No incluye datos de clientes.")

    sb = get_supabase_client()
    if sb is None:
        alert("warn", "⚠️ Supabase no configurado.")
        return

    cr, _ = st.columns([1, 6])
    with cr:
        if st.button("🔄 Recargar", key="vb_reload"):
            _cargar_todas.clear()
            st.rerun()

    df = _cargar_todas()
    if df.empty:
        alert("info", "ℹ️ No se encontraron rutas. Verifica que las tablas tengan datos.")
        return

    # ── Filtros ────────────────────────────────
    with st.expander("🔍 Filtros de búsqueda", expanded=True):
        fc1, fc2, fc3 = st.columns(3)
        f_origen  = fc1.text_input("Origen contiene",  key="vb_orig",  placeholder="ej. HOUSTON")
        f_destino = fc2.text_input("Destino contiene", key="vb_dest",  placeholder="ej. AMOZOC")

        empresas_disp = ["Todas"] + sorted(df["empresa"].dropna().unique().tolist())
        f_empresa = fc3.selectbox("Empresa", empresas_disp, key="vb_emp")

        fc4, fc5 = st.columns(2)
        tipos_disp = ["Todos"] + sorted(df["tipo_servicio"].dropna().unique().tolist())
        f_tipo = fc4.selectbox("Tipo de servicio", tipos_disp, key="vb_tipo")

        ing_min, ing_max = st.slider(
            "Rango ingreso USD",
            min_value=0.0,
            max_value=float(df["ingreso_total_usd"].max() or 10000),
            value=(0.0, float(df["ingreso_total_usd"].max() or 10000)),
            step=100.0,
            key="vb_ing_range",
        )

    # ── Aplicar filtros ────────────────────────
    dff = df.copy()
    if f_origen:
        dff = dff[dff["ruta"].str.contains(f_origen,  case=False, na=False)]
    if f_destino:
        dff = dff[dff["ruta"].str.contains(f_destino, case=False, na=False)]
    if f_empresa != "Todas":
        dff = dff[dff["empresa"] == f_empresa]
    if f_tipo != "Todos":
        dff = dff[dff["tipo_servicio"] == f_tipo]
    dff = dff[
        (dff["ingreso_total_usd"] >= ing_min) &
        (dff["ingreso_total_usd"] <= ing_max)
    ]

    st.markdown(f"**{len(dff)} rutas encontradas**")

    if dff.empty:
        alert("info", "No hay rutas con esos filtros.")
        return

    # ── Tabla de resultados ────────────────────
    dff_show = dff.copy()
    dff_show["empresa"] = dff_show["empresa"].map(EMPRESA_LABELS).fillna(dff_show["empresa"])

    # Formatear moneda
    for col in ["ingreso_total_usd", "costo_directo_usd", "flete", "cruce", "flete_mex", "fuel", "costo_directo", "proveedor_mex"]:
        if col in dff_show.columns:
            dff_show[col] = dff_show[col].apply(
                lambda x: f"${x:,.2f}" if pd.notna(x) and x else "—"
            )

    cols_vista = [c for c in [
        "empresa", "sucursal", "tipo_servicio", "ruta",
        "ingreso_total_usd", "costo_directo_usd",
        "flete", "cruce", "flete_mex", "fuel",
        "id_referencia",
    ] if c in dff_show.columns]

    st.dataframe(
        dff_show[cols_vista].rename(columns={
            "empresa":          "Empresa",
            "sucursal":         "Sucursal",
            "tipo_servicio":    "Tipo",
            "ruta":             "Ruta",
            "ingreso_total_usd":"Ingreso USD",
            "costo_directo_usd":"Costo Dir. USD",
            "flete":            "Flete",
            "cruce":            "Cruce",
            "flete_mex":        "Flete MEX",
            "fuel":             "Fuel",
            "id_referencia":    "ID Ruta",
        }),
        use_container_width=True,
        hide_index=True,
    )

    # ── Descarga ───────────────────────────────
    csv = dff[cols_vista].to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Descargar resultados CSV", csv,
                       file_name="rutas_referencia.csv", mime="text/csv",
                       key="vb_csv")
