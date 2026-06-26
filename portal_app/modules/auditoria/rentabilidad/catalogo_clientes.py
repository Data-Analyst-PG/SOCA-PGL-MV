# portal_app/modules/auditoria/rentabilidad/catalogo_clientes.py
# ─────────────────────────────────────────────────────────────────────────────
# Tab: Catálogo de Clientes
# Permite asignar y mantener el tipo (T1-T4) de cada cliente.
# Los clientes se leen de la tabla rentabilidad_clientes en Supabase.
# Cuando se carga data operativa nueva, los clientes sin tipo aparecen aquí
# marcados como "Sin clasificar" para que el usuario los asigne.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import pandas as pd
import streamlit as st

from services.supabase_client import get_authed_client as get_supabase_client
from ui.components import section_header, alert, divider

# ── Constantes ────────────────────────────────────────────────────────────────
TABLE = "rentabilidad_clientes"

TIPOS = {
    "T1": "T1 – Retail / CEDIS",
    "T2": "T2 – Exportación / Importación",
    "T3": "T3 – Dedicado",
    "T4": "T4 – Alimenticio / Farmacéutico",
}
TIPOS_OPCIONES = ["Sin clasificar"] + list(TIPOS.values())
TIPO_LABEL_A_CODIGO = {v: k for k, v in TIPOS.items()}
TIPO_LABEL_A_CODIGO["Sin clasificar"] = None


# ── Helpers ───────────────────────────────────────────────────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def _cargar_clientes() -> list[dict]:
    sb = get_supabase_client()
    if sb is None:
        return []
    try:
        res = sb.table(TABLE).select("*").order("nombre").execute()
        return res.data or []
    except Exception as e:
        st.error(f"Error cargando clientes: {e}")
        return []


def _guardar_tipo(cliente_id: str, tipo_codigo: str | None) -> bool:
    sb = get_supabase_client()
    if sb is None:
        return False
    try:
        sb.table(TABLE).update({
            "tipo": tipo_codigo,
            "updated_at": "now()",
        }).eq("id", cliente_id).execute()
        return True
    except Exception as e:
        st.error(f"Error guardando tipo: {e}")
        return False


def _crear_cliente(nombre: str, tipo_codigo: str | None) -> bool:
    sb = get_supabase_client()
    if sb is None:
        return False
    try:
        sb.table(TABLE).insert({
            "nombre": nombre.strip(),
            "tipo": tipo_codigo,
            "activo": True,
        }).execute()
        return True
    except Exception as e:
        st.error(f"Error creando cliente: {e}")
        return False


def _toggle_activo(cliente_id: str, activo: bool) -> bool:
    sb = get_supabase_client()
    if sb is None:
        return False
    try:
        sb.table(TABLE).update({"activo": activo}).eq("id", cliente_id).execute()
        return True
    except Exception as e:
        st.error(f"Error actualizando estado: {e}")
        return False


# ── Render ────────────────────────────────────────────────────────────────────
def render():
    section_header("🏢", "Catálogo de Clientes",
                   "Asigna el tipo de operación a cada cliente para el prorrateo de costos")

    sb = get_supabase_client()
    if sb is None:
        alert("warn", "Supabase no configurado. Los cambios no se guardarán.")

    # ── Agregar cliente manual ────────────────────────────────────────────────
    with st.expander("➕ Agregar cliente manualmente", expanded=False):
        col_n, col_t, col_b = st.columns([3, 2, 1])
        with col_n:
            nuevo_nombre = st.text_input(
                "Nombre del cliente",
                placeholder="Ej: Cliente 72",
                key="rc_nuevo_nombre",
            )
        with col_t:
            nuevo_tipo_lbl = st.selectbox(
                "Tipo", TIPOS_OPCIONES, key="rc_nuevo_tipo"
            )
        with col_b:
            st.write("")
            st.write("")
            if st.button("Guardar", key="rc_btn_agregar"):
                if not nuevo_nombre.strip():
                    alert("warn", "Ingresa un nombre para el cliente.")
                else:
                    codigo = TIPO_LABEL_A_CODIGO.get(nuevo_tipo_lbl)
                    if _crear_cliente(nuevo_nombre, codigo):
                        alert("success", f"Cliente '{nuevo_nombre}' agregado.")
                        st.cache_data.clear()
                        st.rerun()

    divider()

    # ── Carga y filtros ───────────────────────────────────────────────────────
    clientes = _cargar_clientes()
    if not clientes:
        alert("info", "No hay clientes registrados. Agrega el primero arriba o carga data operativa.")
        return

    df = pd.DataFrame(clientes)

    col_f1, col_f2, col_f3 = st.columns([2, 2, 1])
    with col_f1:
        buscar = st.text_input("🔍 Buscar cliente", placeholder="Escribe el nombre...", key="rc_buscar")
    with col_f2:
        filtro_tipo = st.multiselect(
            "Filtrar por tipo",
            options=["Sin clasificar"] + list(TIPOS.values()),
            key="rc_filtro_tipo",
        )
    with col_f3:
        solo_activos = st.checkbox("Solo activos", value=True, key="rc_activos")

    # Aplicar filtros
    if solo_activos:
        df = df[df["activo"] == True]
    if buscar:
        df = df[df["nombre"].str.contains(buscar, case=False, na=False)]
    if filtro_tipo:
        codigos_filtro = {TIPO_LABEL_A_CODIGO.get(t) for t in filtro_tipo}
        df = df[df["tipo"].isin(codigos_filtro)]

    # ── KPIs rápidos ─────────────────────────────────────────────────────────
    total = len(df)
    sin_tipo = int((df["tipo"].isna() | (df["tipo"] == "")).sum())
    clasificados = total - sin_tipo

    col_k1, col_k2, col_k3 = st.columns(3)
    col_k1.metric("Total clientes", total)
    col_k2.metric("Clasificados", clasificados)
    col_k3.metric("Sin clasificar", sin_tipo,
                  delta=f"-{sin_tipo}" if sin_tipo else None,
                  delta_color="inverse")

    if sin_tipo > 0:
        alert("warn", f"{sin_tipo} cliente(s) sin tipo asignado. El prorrateo los ignorará hasta que los clasifiques.")

    divider()

    # ── Tabla editable ────────────────────────────────────────────────────────
    section_header("📋", "Clientes registrados", f"{total} registros")

    for _, row in df.iterrows():
        cid   = row["id"]
        nom   = row["nombre"]
        tipo_actual = row.get("tipo") or ""
        activo = row.get("activo", True)

        # Mapear código → label para el selectbox
        tipo_lbl_actual = TIPOS.get(tipo_actual, "Sin clasificar")

        with st.container():
            col_nom, col_sel, col_act, col_save = st.columns([3, 3, 1, 1])

            with col_nom:
                st.markdown(
                    f'<div style="padding:0.5rem 0;font-weight:600;color:#1B2266;">'
                    f'{nom}</div>',
                    unsafe_allow_html=True,
                )

            with col_sel:
                nuevo_tipo_lbl = st.selectbox(
                    "",
                    options=TIPOS_OPCIONES,
                    index=TIPOS_OPCIONES.index(tipo_lbl_actual)
                          if tipo_lbl_actual in TIPOS_OPCIONES else 0,
                    key=f"rc_tipo_{cid}",
                    label_visibility="collapsed",
                )

            with col_act:
                nuevo_activo = st.checkbox(
                    "Activo",
                    value=bool(activo),
                    key=f"rc_activo_{cid}",
                )

            with col_save:
                if st.button("💾", key=f"rc_save_{cid}", help="Guardar cambios"):
                    codigo_nuevo = TIPO_LABEL_A_CODIGO.get(nuevo_tipo_lbl)
                    ok1 = _guardar_tipo(cid, codigo_nuevo)
                    ok2 = _toggle_activo(cid, nuevo_activo)
                    if ok1 and ok2:
                        st.toast(f"✅ {nom} actualizado")
                        st.cache_data.clear()
                        st.rerun()

            st.divider()

    # ── Descarga ──────────────────────────────────────────────────────────────
    if not df.empty:
        csv = df[["nombre", "tipo", "activo"]].rename(columns={
            "nombre": "Cliente", "tipo": "Tipo", "activo": "Activo"
        }).to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Descargar catálogo (.csv)",
            data=csv,
            file_name="catalogo_clientes_rentabilidad.csv",
            mime="text/csv",
            key="rc_download",
        )
