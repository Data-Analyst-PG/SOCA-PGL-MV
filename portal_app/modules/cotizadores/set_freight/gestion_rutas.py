from ui.components import section_header, alert, divider
"""
gestion_rutas.py  –  Set Freight LLC
Vista tabular con filtros, edición inline y eliminación.
Solo ve las rutas de la sucursal del usuario (RLS en Supabase lo garantiza).
"""

import streamlit as st
import pandas as pd

from services.supabase_client import get_supabase_client
from ._shared import TABLE_RUTAS, CONCEPTOS_INGRESO, CONCEPTOS_COSTO, calcular_ruta, limpiar_fila, safe


COLS_TABLA = [
    "id_ruta", "tipo_servicio", "ruta_origen", "ruta_destino",
    "flete_usa", "flete_mex", "cruce", "proveedor_usa", "proveedor_mex",
    "viajes_mes", "estado", "created_at",
]


@st.cache_data(show_spinner=False, ttl=60)
def _cargar(table: str) -> pd.DataFrame:
    sb = get_supabase_client()
    if sb is None:
        return pd.DataFrame()
    try:
        resp = sb.table(table).select("*").execute()
    except Exception:
        return pd.DataFrame()
    df = pd.DataFrame(resp.data or [])
    if not df.empty and "created_at" in df.columns:
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce").dt.strftime("%Y-%m-%d")
    return df


def render():
    st.title("🗂️ Gestión de Rutas — Set Freight LLC")

    sb = get_supabase_client()
    if sb is None:
        alert("warn", "⚠️ Supabase no configurado.")
        return

    cr, _ = st.columns([1, 5])
    with cr:
        if st.button("🔄 Recargar", key="sf_gest_reload"):
            _cargar.clear()
            st.rerun()

    df = _cargar(TABLE_RUTAS)
    if df.empty:
        alert("info", "ℹ️ No hay rutas registradas. Captura la primera en el tab de Captura.")
        return

    # ── Filtros ───────────────────────────────
    with st.expander("🔍 Filtros", expanded=True):
        fc1, fc2, fc3 = st.columns(3)
        tipos = ["Todos"] + sorted(df["tipo_servicio"].dropna().unique().tolist())
        f_tipo   = fc1.selectbox("Tipo", tipos, key="sf_g_tipo")
        f_origen = fc2.text_input("Origen contiene", key="sf_g_orig")
        f_estado = fc3.selectbox("Estado", ["Todos", "activa", "borrador", "archivada"], key="sf_g_est")

    dff = df.copy()
    if f_tipo != "Todos":
        dff = dff[dff["tipo_servicio"] == f_tipo]
    if f_origen:
        mask = dff["ruta_origen"].str.contains(f_origen, case=False, na=False)
        dff = dff[mask]
    if f_estado != "Todos":
        dff = dff[dff["estado"] == f_estado]

    # ── Calcular utilidades para mostrar en tabla ─
    if not dff.empty:
        kpis = dff.apply(
            lambda row: pd.Series(calcular_ruta(row.to_dict(), safe(row.get("pct_indirecto"), 0.10))),
            axis=1
        )
        dff["Ingreso"] = kpis["ingreso_total"].map("${:,.2f}".format)
        dff["Ut. Neta"] = kpis["ut_neta"].map("${:,.2f}".format)
        dff["% Neta"]  = kpis["pct_ut_neta"].map("{:.1%}".format)

    cols_show = [c for c in ["id_ruta","tipo_servicio","ruta_origen","ruta_destino",
                              "Ingreso","Ut. Neta","% Neta","viajes_mes","estado","created_at"]
                 if c in dff.columns]
    st.dataframe(dff[cols_show], use_container_width=True, hide_index=True)
    st.caption(f"{len(dff)} rutas mostradas de {len(df)} en tu sucursal")

    # ── Editar / Archivar ─────────────────────
    divider()
section_header("✏️", "Editar ruta")
    if "id_ruta" not in dff.columns or dff.empty:
        return

    ids = dff["id_ruta"].dropna().tolist()
    sel_id = st.selectbox("Selecciona ID a editar", ids, key="sf_g_edit_sel")
    if not sel_id:
        return

    row = df[df["id_ruta"] == sel_id].iloc[0].to_dict()
    rec_id = row.get("id")  # uuid de la fila

    with st.form(key="sf_edit_form"):
        ec1, ec2 = st.columns(2)
        nuevo_origen  = ec1.text_input("Origen",  value=row.get("ruta_origen",""),  key="sf_e_orig")
        nuevo_destino = ec2.text_input("Destino", value=row.get("ruta_destino",""), key="sf_e_dest")

        st.markdown("**Ingresos (USD)**")
        ing_cols = st.columns(len(CONCEPTOS_INGRESO))
        ing_vals = {}
        for i, (lbl, campo) in enumerate(CONCEPTOS_INGRESO.items()):
            ing_vals[campo] = ing_cols[i].number_input(lbl, value=safe(row.get(campo)),
                                                        step=0.01, format="%.2f",
                                                        key=f"sf_e_ing_{campo}")

        st.markdown("**Costos (USD)**")
        cst_cols = st.columns(4)
        cst_vals = {}
        for i, (lbl, campo) in enumerate(CONCEPTOS_COSTO.items()):
            cst_vals[campo] = cst_cols[i % 4].number_input(lbl, value=safe(row.get(campo)),
                                                             step=0.01, format="%.2f",
                                                             key=f"sf_e_cst_{campo}")

        nuevo_estado = st.selectbox("Estado", ["activa","borrador","archivada"],
                                    index=["activa","borrador","archivada"].index(row.get("estado","activa")),
                                    key="sf_e_estado")
        nuevo_notas  = st.text_area("Notas", value=row.get("notas","") or "", key="sf_e_notas")

        guardado = st.form_submit_button("💾 Guardar cambios", type="primary")

    if guardado:
        update = limpiar_fila({
            "ruta_origen":  nuevo_origen.strip().upper(),
            "ruta_destino": nuevo_destino.strip().upper(),
            "estado":       nuevo_estado,
            "notas":        nuevo_notas.strip() or None,
            **ing_vals,
            **cst_vals,
        })
        try:
            sb.table(TABLE_RUTAS).update(update).eq("id", rec_id).execute()
            alert("success", "✅ Ruta actualizada.")
            _cargar.clear()
            st.rerun()
        except Exception as e:
            st.error(f"❌ {e}")
