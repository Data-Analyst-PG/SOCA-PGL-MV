# portal_app/modules/administracion/catalogo_permisos.py
# ─────────────────────────────────────────────────────────────────────────────
# Catálogo de Permisos — alta/baja de permisos disponibles en el sistema.
# Fuente de verdad para el checklist de Gestión de Accesos: cualquier permiso
# nuevo que se cree en código (ej. al agregar un módulo) se agrega aquí una
# sola vez y queda disponible para asignar a usuarios sin tocar más código.
#
# Tabla: catalogo_permisos (permiso, categoria, etiqueta, activo, created_at)
# ─────────────────────────────────────────────────────────────────────────────
import pandas as pd
import streamlit as st

from services.supabase_client import get_supabase_client, get_authed_client
from services.auditoria import registrar_accion
from ui.components import section_header, alert, divider


@st.cache_data(ttl=60, show_spinner=False)
def _cargar_todos() -> pd.DataFrame:
    sb = get_authed_client()
    res = (
        sb.table("catalogo_permisos")
        .select("id, permiso, categoria, etiqueta, activo")
        .order("categoria")
        .order("etiqueta")
        .execute()
    )
    return pd.DataFrame(res.data or [])


def render():
    section_header("🗂️", "Catálogo de Permisos",
                    "Permisos disponibles para asignar en Gestión de Accesos")

    supabase = get_supabase_client()  # service-role interno

    # =================================
    # AGREGAR PERMISO NUEVO
    # =================================
    with st.expander("➕ Agregar permiso nuevo", expanded=False):
        with st.form("form_nuevo_permiso", clear_on_submit=True):
            col1, col2 = st.columns(2)
            nuevo_permiso  = col1.text_input("Clave del permiso", placeholder="ej. modulo:accion")
            nueva_categoria = col2.text_input("Categoría", placeholder="ej. Cotizador Igloo")
            nueva_etiqueta = st.text_input("Etiqueta (lo que ve el admin)", placeholder="ej. Captura de Rutas")

            crear = st.form_submit_button("Agregar al catálogo", type="primary")

        if crear:
            permiso = nuevo_permiso.strip()
            categoria = nueva_categoria.strip()
            etiqueta = nueva_etiqueta.strip()

            if not permiso or ":" not in permiso:
                alert("warn", "La clave del permiso debe tener el formato 'modulo:accion' (ej. cotizador_igloo:captura).")
            elif not categoria or not etiqueta:
                alert("warn", "Categoría y etiqueta son obligatorias.")
            else:
                try:
                    supabase.table("catalogo_permisos").insert({
                        "permiso": permiso,
                        "categoria": categoria,
                        "etiqueta": etiqueta,
                    }).execute()
                    registrar_accion("administracion", "crear_permiso_catalogo", {"permiso": permiso, "categoria": categoria})
                    st.success(f"Permiso '{permiso}' agregado.")
                    _cargar_todos.clear()
                    st.rerun()
                except Exception as e:
                    alert("error", f"No se pudo agregar (¿ya existe esa clave?): {e}")

    divider()

    # =================================
    # LISTADO / ACTIVAR-DESACTIVAR
    # =================================
    df = _cargar_todos()
    if df.empty:
        alert("info", "El catálogo está vacío.")
        return

    for categoria, grupo in df.groupby("categoria", sort=False):
        n_activos = int(grupo["activo"].sum())
        with st.expander(f"{categoria} ({n_activos}/{len(grupo)} activos)", expanded=False):
            for fila in grupo.itertuples():
                col_txt, col_toggle = st.columns([4, 1])
                col_txt.write(f"**{fila.etiqueta}**  ·  `{fila.permiso}`")
                nuevo_valor = col_toggle.toggle(
                    "Activo",
                    value=bool(fila.activo),
                    key=f"cat_perm_toggle_{fila.id}",
                    label_visibility="collapsed",
                )
                if nuevo_valor != bool(fila.activo):
                    supabase.table("catalogo_permisos").update({"activo": nuevo_valor}).eq("id", fila.id).execute()
                    registrar_accion("administracion", "editar_permiso_catalogo", {
                        "permiso": fila.permiso,
                        "activo": nuevo_valor,
                    })
                    _cargar_todos.clear()
                    st.rerun()

    st.caption("Desactivar un permiso lo oculta del checklist de Gestión de Accesos — no borra los accesos ya otorgados a quienes lo tengan.")
