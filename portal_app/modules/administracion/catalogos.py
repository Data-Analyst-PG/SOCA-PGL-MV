# portal_app/modules/administracion/catalogos.py
# ─────────────────────────────────────────────────────────────────────────────
# Catálogos — alta/edición de Empresas (companies) y Áreas (areas).
# Fuente de verdad para los selectbox de "Empresa" y "Área" en Crear Usuario,
# y (más adelante) para Tickets/Complementarias.
#
# Tablas:
#   companies (id, name, slug, created_at)
#   areas     (id, slug, name, description, is_active, created_at)
# ─────────────────────────────────────────────────────────────────────────────
import re

import pandas as pd
import streamlit as st

from services.supabase_client import get_service_client, get_authed_client
from services.auditoria import registrar_accion
from ui.components import section_header, alert, divider


def _slugify(texto: str) -> str:
    s = texto.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


@st.cache_data(ttl=60, show_spinner=False)
def _cargar_companies() -> pd.DataFrame:
    sb = get_authed_client()
    res = sb.table("companies").select("id, name, slug, created_at").order("name").execute()
    return pd.DataFrame(res.data or [])


@st.cache_data(ttl=60, show_spinner=False)
def _cargar_areas() -> pd.DataFrame:
    sb = get_authed_client()
    res = (
        sb.table("areas")
        .select("id, slug, name, description, is_active, created_at")
        .order("name")
        .execute()
    )
    return pd.DataFrame(res.data or [])


@st.cache_data(ttl=60, show_spinner=False)
def _cargar_sucursales() -> pd.DataFrame:
    sb = get_authed_client()
    res = (
        sb.table("sucursales")
        .select("id, company_id, name, slug, is_active, created_at, companies(name)")
        .order("name")
        .execute()
    )
    df = pd.DataFrame(res.data or [])
    if not df.empty:
        df["empresa"] = df["companies"].apply(lambda c: (c or {}).get("name", ""))
    return df


def _limpiar_cache():
    _cargar_companies.clear()
    _cargar_areas.clear()
    _cargar_sucursales.clear()


# ═══════════════════════════════════════════════════════════════════════════
# EMPRESAS
# ═══════════════════════════════════════════════════════════════════════════
def _tab_empresas(supabase):
    section_header("🏢", "Empresas", "Catálogo usado en Crear Usuario y cotizadores")

    with st.expander("➕ Agregar empresa nueva", expanded=False):
        with st.form("form_nueva_empresa", clear_on_submit=True):
            nombre = st.text_input("Nombre de la empresa*", placeholder="Ej. Set Logis Plus")
            crear = st.form_submit_button("Agregar", type="primary")

        if crear:
            nombre = nombre.strip()
            if not nombre:
                alert("warn", "El nombre es obligatorio.")
            else:
                slug = _slugify(nombre)
                try:
                    supabase.table("companies").insert({"name": nombre, "slug": slug}).execute()
                    registrar_accion("administracion", "crear_empresa_catalogo", {"empresa": nombre})
                    st.success(f"Empresa '{nombre}' agregada.")
                    _limpiar_cache()
                    st.rerun()
                except Exception as e:
                    alert("error", f"No se pudo agregar (¿ya existe ese nombre?): {e}")

    divider()

    companies = _cargar_companies()
    if companies.empty:
        alert("info", "No hay empresas registradas todavía.")
        return

    for fila in companies.itertuples():
        col_txt, col_edit = st.columns([4, 1])
        col_txt.write(f"**{fila.name}**  ·  `{fila.slug}`")
        if col_edit.button("✏️ Renombrar", key=f"emp_edit_{fila.id}"):
            st.session_state[f"_editando_emp_{fila.id}"] = True

        if st.session_state.get(f"_editando_emp_{fila.id}"):
            with st.form(f"form_editar_emp_{fila.id}"):
                nuevo_nombre = st.text_input("Nuevo nombre", value=fila.name, key=f"emp_nombre_{fila.id}")
                c1, c2 = st.columns(2)
                guardar = c1.form_submit_button("💾 Guardar", type="primary")
                cancelar = c2.form_submit_button("Cancelar")

            if guardar:
                nuevo_nombre = nuevo_nombre.strip()
                if nuevo_nombre and nuevo_nombre != fila.name:
                    supabase.table("companies").update(
                        {"name": nuevo_nombre, "slug": _slugify(nuevo_nombre)}
                    ).eq("id", fila.id).execute()
                    registrar_accion("administracion", "editar_empresa_catalogo", {
                        "empresa_anterior": fila.name, "empresa_nueva": nuevo_nombre,
                    })
                    st.success("Empresa actualizada.")
                st.session_state.pop(f"_editando_emp_{fila.id}", None)
                _limpiar_cache()
                st.rerun()
            if cancelar:
                st.session_state.pop(f"_editando_emp_{fila.id}", None)
                st.rerun()

    st.caption("Renombrar una empresa no afecta a los usuarios ya asignados (se guarda por ID).")


# ═══════════════════════════════════════════════════════════════════════════
# ÁREAS
# ═══════════════════════════════════════════════════════════════════════════
def _tab_areas(supabase):
    section_header("🗂️", "Áreas", "Catálogo usado en Crear Usuario y Gestión de Accesos")

    with st.expander("➕ Agregar área nueva", expanded=False):
        with st.form("form_nueva_area", clear_on_submit=True):
            nombre = st.text_input("Nombre del área*", placeholder="Ej. Recursos Humanos")
            descripcion = st.text_input("Descripción (opcional)", placeholder="Breve descripción del área")
            crear = st.form_submit_button("Agregar", type="primary")

        if crear:
            nombre = nombre.strip()
            if not nombre:
                alert("warn", "El nombre es obligatorio.")
            else:
                slug = _slugify(nombre)
                try:
                    supabase.table("areas").insert({
                        "name": nombre, "slug": slug, "description": descripcion.strip() or None,
                    }).execute()
                    registrar_accion("administracion", "crear_area_catalogo", {"area": nombre})
                    st.success(f"Área '{nombre}' agregada.")
                    _limpiar_cache()
                    st.rerun()
                except Exception as e:
                    alert("error", f"No se pudo agregar (¿ya existe ese nombre?): {e}")

    divider()

    areas = _cargar_areas()
    if areas.empty:
        alert("info", "No hay áreas registradas todavía.")
        return

    n_activas = int(areas["is_active"].sum())
    st.caption(f"{n_activas}/{len(areas)} áreas activas")

    for fila in areas.itertuples():
        col_txt, col_toggle = st.columns([4, 1])
        desc = f" — {fila.description}" if fila.description else ""
        col_txt.write(f"**{fila.name}**  ·  `{fila.slug}`{desc}")
        nuevo_valor = col_toggle.toggle(
            "Activa", value=bool(fila.is_active),
            key=f"area_toggle_{fila.id}", label_visibility="collapsed",
        )
        if nuevo_valor != bool(fila.is_active):
            supabase.table("areas").update({"is_active": nuevo_valor}).eq("id", fila.id).execute()
            registrar_accion("administracion", "editar_area_catalogo", {
                "area": fila.name, "activa": nuevo_valor,
            })
            _limpiar_cache()
            st.rerun()

    st.caption("Desactivar un área la oculta del selectbox en Crear Usuario — no afecta a quienes ya la tienen asignada.")


# ═══════════════════════════════════════════════════════════════════════════
# SUCURSALES
# ═══════════════════════════════════════════════════════════════════════════
def _tab_sucursales(supabase):
    section_header("📍", "Sucursales", "Catálogo por empresa — usado en Tickets, Complementarias y Viáticos")

    companies = _cargar_companies()
    if companies.empty:
        alert("warn", "Primero da de alta al menos una empresa en la pestaña 'Empresas'.")
        return

    with st.expander("➕ Agregar sucursal nueva", expanded=False):
        with st.form("form_nueva_sucursal", clear_on_submit=True):
            empresa_sel = st.selectbox("Empresa*", companies["name"].tolist())
            nombre = st.text_input("Nombre de la sucursal*", placeholder="Ej. Nuevo Laredo")
            crear = st.form_submit_button("Agregar", type="primary")

        if crear:
            nombre = nombre.strip()
            if not nombre:
                alert("warn", "El nombre es obligatorio.")
            else:
                company_id = companies.loc[companies["name"] == empresa_sel, "id"].iloc[0]
                slug = _slugify(nombre)
                try:
                    supabase.table("sucursales").insert({
                        "company_id": company_id, "name": nombre, "slug": slug,
                    }).execute()
                    registrar_accion("administracion", "crear_sucursal_catalogo", {
                        "empresa": empresa_sel, "sucursal": nombre,
                    })
                    st.success(f"Sucursal '{nombre}' agregada a {empresa_sel}.")
                    _limpiar_cache()
                    st.rerun()
                except Exception as e:
                    alert("error", f"No se pudo agregar (¿ya existe esa sucursal en esta empresa?): {e}")

    divider()

    sucursales = _cargar_sucursales()
    if sucursales.empty:
        alert("info", "No hay sucursales registradas todavía.")
        return

    for empresa_nombre, grupo in sucursales.groupby("empresa", sort=True):
        n_activas = int(grupo["is_active"].sum())
        with st.expander(f"{empresa_nombre} ({n_activas}/{len(grupo)} activas)", expanded=False):
            for fila in grupo.itertuples():
                col_txt, col_toggle = st.columns([4, 1])
                col_txt.write(f"**{fila.name}**  ·  `{fila.slug}`")
                nuevo_valor = col_toggle.toggle(
                    "Activa", value=bool(fila.is_active),
                    key=f"suc_toggle_{fila.id}", label_visibility="collapsed",
                )
                if nuevo_valor != bool(fila.is_active):
                    supabase.table("sucursales").update({"is_active": nuevo_valor}).eq("id", fila.id).execute()
                    registrar_accion("administracion", "editar_sucursal_catalogo", {
                        "empresa": empresa_nombre, "sucursal": fila.name, "activa": nuevo_valor,
                    })
                    _limpiar_cache()
                    st.rerun()

    st.caption("Desactivar una sucursal la oculta de los selectbox de Tickets/Complementarias/Viáticos una vez migrados a este catálogo.")


# ═══════════════════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA
# ═══════════════════════════════════════════════════════════════════════════
def render():
    section_header("📚", "Catálogos", "Empresas, Áreas y Sucursales usadas en todo el sistema")

    supabase = get_service_client()  # bypassa RLS — módulo ya protegido por permiso de admin

    seccion = st.segmented_control(
        "Sección",
        options=["🏢 Empresas", "🗂️ Áreas", "📍 Sucursales"],
        default="🏢 Empresas",
        key="catalogos_seccion",
    )
    seccion = seccion or "🏢 Empresas"

    divider()

    if seccion == "🏢 Empresas":
        _tab_empresas(supabase)
    elif seccion == "🗂️ Áreas":
        _tab_areas(supabase)
    else:
        _tab_sucursales(supabase)
