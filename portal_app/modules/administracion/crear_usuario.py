# portal_app/modules/administracion/crear_usuario.py
# ─────────────────────────────────────────────────────────────────────────────
# Crear Usuario — da de alta la cuenta en Auth (autoconfirmada), completa su
# fila en profiles (el trigger on_auth_user_created ya crea la base), le
# asigna permisos iniciales del catálogo, y le manda un correo de bienvenida
# con link para establecer su contraseña.
# ─────────────────────────────────────────────────────────────────────────────
import pandas as pd
import streamlit as st

from services.supabase_client import get_service_client, get_authed_client
from services.auth_admin import crear_usuario_auth, enviar_link_password
from services.auditoria import registrar_accion
from ui.components import section_header, alert, divider

@st.cache_data(ttl=300, show_spinner=False)
def _cargar_companies() -> pd.DataFrame:
    sb = get_authed_client()
    res = sb.table("companies").select("id, name").order("name").execute()
    return pd.DataFrame(res.data or [])


@st.cache_data(ttl=300, show_spinner=False)
def _cargar_areas() -> pd.DataFrame:
    sb = get_authed_client()
    res = (
        sb.table("areas")
        .select("id, name")
        .eq("is_active", True)
        .order("name")
        .execute()
    )
    return pd.DataFrame(res.data or [])


@st.cache_data(ttl=300, show_spinner=False)
def _cargar_sucursales() -> pd.DataFrame:
    sb = get_authed_client()
    res = (
        sb.table("sucursales")
        .select("id, name, is_active, companies(name)")
        .eq("is_active", True)
        .execute()
    )
    df = pd.DataFrame(res.data or [])
    if not df.empty:
        df["empresa"] = df["companies"].apply(lambda c: (c or {}).get("name", ""))
        df["etiqueta"] = df["empresa"] + " — " + df["name"]
        df = df.sort_values("etiqueta")
    return df

ROLES = ["user", "data_analyst", "admin"]


@st.cache_data(ttl=120, show_spinner=False)
def _cargar_catalogo() -> pd.DataFrame:
    sb = get_authed_client()
    res = (
        sb.table("catalogo_permisos")
        .select("permiso, categoria, etiqueta")
        .eq("activo", True)
        .order("categoria")
        .order("etiqueta")
        .execute()
    )
    return pd.DataFrame(res.data or [])


def render():
    section_header("➕", "Crear Usuario", "Alta de cuenta nueva con permisos iniciales")

    catalogo = _cargar_catalogo()
    companies = _cargar_companies()
    areas = _cargar_areas()
    sucursales = _cargar_sucursales()
    opciones_empresa = ["Sin asignar"] + (companies["name"].tolist() if not companies.empty else [])
    opciones_area = ["Sin asignar"] + (areas["name"].tolist() if not areas.empty else [])
    opciones_sucursal = ["Sin asignar"] + (sucursales["etiqueta"].tolist() if not sucursales.empty else [])

    with st.form("form_crear_usuario", clear_on_submit=False):
        col1, col2 = st.columns(2)
        full_name = col1.text_input("Nombre completo*")
        email     = col2.text_input("Correo*", placeholder="usuario@palosgarza.com")

        col3, col4 = st.columns(2)
        area_sel = col3.selectbox("Área", opciones_area)
        job_title = col4.text_input("Puesto", placeholder="ej. Auditor, Gestor")

        col5, col6 = st.columns(2)
        empresa = col5.selectbox("Empresa (opcional)", opciones_empresa)
        role    = col6.selectbox("Rol del sistema", ROLES, index=0,
                                 help="'admin' salta todos los checks de permiso — asignar con cuidado.")

        sucursal_sel = st.selectbox("Sucursal (opcional)", opciones_sucursal,
                                    help="Lista completa de todas las empresas — verifica que coincida con la Empresa elegida arriba.")

        st.markdown("**Permisos iniciales**")
        marcados = {}
        if not catalogo.empty:
            for categoria, grupo in catalogo.groupby("categoria", sort=False):
                with st.expander(categoria, expanded=False):
                    cols = st.columns(2)
                    for i, fila in enumerate(grupo.itertuples()):
                        col = cols[i % 2]
                        marcados[fila.permiso] = col.checkbox(fila.etiqueta, key=f"nuevo_perm_{fila.permiso}")

        crear = st.form_submit_button("Crear usuario y enviar bienvenida", type="primary", use_container_width=True)

    if not crear:
        return

    full_name = full_name.strip()
    email     = email.strip().lower()

    if not full_name or not email or "@" not in email:
        alert("warn", "Nombre y correo válido son obligatorios.")
        return

    supabase = get_service_client()

    # No hay chequeo previo de duplicados aquí — auth.admin.create_user()
    # ya falla solo si el correo está registrado, y ese error se captura abajo.

    with st.spinner("Creando usuario..."):
        try:
            user_id = crear_usuario_auth(email)
        except Exception as e:
            alert("error", f"No se pudo crear el usuario (¿correo ya registrado?): {e}")
            return

        if not user_id:
            alert("error", "Supabase no devolvió el ID del usuario nuevo.")
            return

        access = {p: True for p, marcado in marcados.items() if marcado}

        company_id = None
        if empresa != "Sin asignar" and not companies.empty:
            match = companies[companies["name"] == empresa]
            if not match.empty:
                company_id = match.iloc[0]["id"]

        area_id = None
        if area_sel != "Sin asignar" and not areas.empty:
            match_area = areas[areas["name"] == area_sel]
            if not match_area.empty:
                area_id = match_area.iloc[0]["id"]

        sucursal_id = None
        if sucursal_sel != "Sin asignar" and not sucursales.empty:
            match_suc = sucursales[sucursales["etiqueta"] == sucursal_sel]
            if not match_suc.empty:
                sucursal_id = match_suc.iloc[0]["id"]

        try:
            supabase.table("profiles").update({
                "full_name": full_name,
                "area_id": area_id,
                "area_name": area_sel if area_sel != "Sin asignar" else None,
                "sucursal_id": sucursal_id,
                "job_title": job_title or None,
                "role": role,
                "is_active": True,
                "access": access,
                "company_id": company_id,
            }).eq("user_id", user_id).execute()
        except Exception as e:
            alert("error", f"Usuario creado en Auth, pero falló al completar su perfil: {e}")
            return

        resultado_correo = enviar_link_password(email, full_name, es_bienvenida=True)

    registrar_accion("administracion", "crear_usuario", {
        "usuario_creado": full_name,
        "correo": email,
        "permisos_iniciales": list(access.keys()),
    })

    if resultado_correo.get("ok"):
        st.success(f"✅ Usuario **{full_name}** creado y correo de bienvenida enviado a {email}.")
    else:
        alert("warn", f"Usuario **{full_name}** creado, pero el correo de bienvenida falló: {resultado_correo.get('error')}. "
                       f"Puedes reenviarlo luego desde Gestión de Accesos (próximamente) o pedirle que use 'Olvidé mi contraseña'.")

    st.cache_data.clear()
