# portal_app/modules/administracion/gestion_accesos.py
# ─────────────────────────────────────────────────────────────────────────────
# Gestión de Accesos — v2
# Antes: lista ALL_ROLES hardcodeada en el código + un dropdown con botones
#        "Permitir"/"Revocar" uno a la vez.
# Ahora: el catálogo de permisos vive en Supabase (catalogo_permisos) y se
#        edita desde la tab "🗂️ Catálogo de Permisos" — aquí solo se leen
#        los permisos activos, agrupados por categoría, como checkboxes
#        dentro de un formulario. Un solo "Guardar cambios" aplica todo.
# ─────────────────────────────────────────────────────────────────────────────
import pandas as pd
import streamlit as st

from services.supabase_client import get_service_client, get_authed_client
from services.auditoria import registrar_accion
from ui.components import section_header, alert, divider


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
    section_header("🔐", "Gestión de Accesos", "Activar/desactivar usuarios y otorgar/revocar permisos")

    supabase = get_service_client()  # bypassa RLS — módulo ya protegido por permiso de admin

    # =================================
    # CATÁLOGO DE PERMISOS
    # =================================
    catalogo = _cargar_catalogo()
    if catalogo.empty:
        alert("warn", "El catálogo de permisos está vacío. Ve a la pestaña '🗂️ Catálogo de Permisos' para agregar el primero.")
        return

    # =================================
    # SELECCIÓN DE USUARIO
    # =================================
    try:
        res = supabase.table("profiles").select(
            "user_id, role, company_id, is_active, full_name, job_title, area_name, access"
        ).order("full_name").execute()
        data = res.data or []
    except Exception as e:
        alert("error", f"No se pudo cargar la lista de usuarios: {e}")
        return

    if not data:
        alert("warn", "No hay usuarios en profiles.")
        return

    df_usuarios = pd.DataFrame(data)
    df_usuarios["full_name"] = df_usuarios["full_name"].fillna("Sin Nombre")

    selected_user_id = st.selectbox(
        "Seleccionar Usuario",
        options=df_usuarios["user_id"],
        format_func=lambda uid: df_usuarios.loc[df_usuarios["user_id"] == uid, "full_name"].values[0],
        key="admin_ga_user_sel",
    )
    selected_row = df_usuarios[df_usuarios["user_id"] == selected_user_id].iloc[0]

    # =================================
    # INFO + ACTIVAR/DESACTIVAR
    # =================================
    section_header("▸", "Información del Usuario")

    current_status = bool(selected_row["is_active"])
    button_label = "Desactivar Usuario" if current_status else "Activar Usuario"

    if st.button(button_label, key="admin_ga_toggle_status"):
        new_status = not current_status
        supabase.table("profiles").update({"is_active": new_status}).eq("user_id", selected_user_id).execute()
        try:
            registrar_accion("administracion", "editar_acceso_usuario", {
                "usuario_afectado": selected_row["full_name"],
                "cambio": "activado" if new_status else "desactivado",
            })
        except Exception:
            pass
        st.success(f"Usuario {'activado' if new_status else 'desactivado'} correctamente")
        st.rerun()

    c1, c2, c3 = st.columns(3)
    c1.write(f"**Nombre:** {selected_row['full_name']}")
    c2.write(f"**Role:** {selected_row['role']}")
    c3.write(f"**Área:** {selected_row['area_name']}")

    divider()

    # =================================
    # CHECKLIST DE PERMISOS POR CATEGORÍA
    # =================================
    section_header("▸", "Permisos", "Marca o desmarca los accesos y da clic en Guardar — se aplican todos juntos")

    current_access = selected_row.get("access") or {}
    if isinstance(current_access, list):
        current_access = {k: True for k in current_access}

    with st.form(f"form_permisos_{selected_user_id}"):
        marcados: dict[str, bool] = {}

        for categoria, grupo in catalogo.groupby("categoria", sort=False):
            activos_en_categoria = sum(1 for p in grupo["permiso"] if current_access.get(p))
            with st.expander(f"{categoria} ({activos_en_categoria}/{len(grupo)})", expanded=False):
                cols = st.columns(2)
                for i, fila in enumerate(grupo.itertuples()):
                    col = cols[i % 2]
                    marcados[fila.permiso] = col.checkbox(
                        fila.etiqueta,
                        value=bool(current_access.get(fila.permiso, False)),
                        key=f"perm_{selected_user_id}_{fila.permiso}",
                    )

        guardar = st.form_submit_button("💾 Guardar cambios", type="primary", use_container_width=True)

    if guardar:
        otorgados = [p for p, marcado in marcados.items() if marcado and not current_access.get(p)]
        revocados = [p for p, marcado in marcados.items() if not marcado and current_access.get(p)]

        if not otorgados and not revocados:
            alert("info", "No hubo cambios que guardar.")
            return

        nuevo_access = dict(current_access)
        for p in otorgados:
            nuevo_access[p] = True
        for p in revocados:
            nuevo_access.pop(p, None)

        supabase.table("profiles").update({"access": nuevo_access}).eq("user_id", selected_user_id).execute()
        try:
            registrar_accion("administracion", "editar_acceso_usuario", {
                "usuario_afectado": selected_row["full_name"],
                "otorgados": otorgados,
                "revocados": revocados,
            })
        except Exception:
            pass

        st.success(f"✅ Guardado: {len(otorgados)} otorgado(s), {len(revocados)} revocado(s).")
        st.rerun()

    divider()
    section_header("▸", "Permisos (Access JSON)")
    if current_access:
        st.json(current_access)
    else:
        alert("info", "Este usuario no tiene permisos definidos.")

    divider()

    # =================================
    # ALCANCE POR EMPRESA / SUCURSAL
    # =================================
    section_header("▸", "Alcance", "En qué empresa/sucursal/tipo puede actuar dentro de módulos que lo requieren (Complementarias, Tickets)")
    st.caption(
        "⚠️ Sin ninguna regla, el usuario NO ve nada en estos módulos — es el default seguro. "
        "Para usuarios que dan servicio a TODAS las empresas (ej. Auditoría, Análisis de Datos, "
        "Facturación y Cobranza), asígnales el permiso 'Complementarias — Ver todo' en la sección "
        "de Permisos de arriba, en vez de dejar el Alcance vacío."
    )
    st.caption(
        "Para usuarios con alcance limitado (ej. Liquidaciones → solo Lincoln y Set Logis; "
        "Safety Mexicano → solo Picus e Igloo), agrega una regla por cada empresa que deban ver. "
        "Si además solo deben ver cierto tipo de solicitud (ej. solo Desconclusiones), especifícalo "
        "en 'Tipo' — si lo dejas vacío, ven todos los tipos dentro de esa empresa."
    )

    try:
        res_alc = (
            supabase.table("alcance_usuario")
            .select("id, modulo, empresa, sucursal, tipo, activo")
            .eq("user_id", selected_user_id)
            .order("modulo")
            .execute()
        )
        reglas_actuales = res_alc.data or []
    except Exception as e:
        alert("error", f"No se pudo cargar el alcance: {e}")
        reglas_actuales = []

    if reglas_actuales:
        for regla in reglas_actuales:
            c_mod, c_emp, c_suc, c_tipo, c_del = st.columns([2, 2, 2, 2, 1])
            c_mod.write(f"**{regla['modulo']}**")
            c_emp.write(regla["empresa"] or "_Todas_")
            c_suc.write(regla["sucursal"] or "_Todas_")
            c_tipo.write(regla["tipo"] or "_Todos_")
            if c_del.button("🗑️", key=f"del_alcance_{regla['id']}"):
                supabase.table("alcance_usuario").delete().eq("id", regla["id"]).execute()
                registrar_accion("administracion", "editar_acceso_usuario", {
                    "usuario_afectado": selected_row["full_name"],
                    "alcance_eliminado": regla,
                })
                st.rerun()
    else:
        alert("info", "Sin reglas de alcance — este usuario ve todo en los módulos que tengan alcance.")

    with st.expander("➕ Agregar regla de alcance", expanded=False):
        with st.form(f"form_alcance_{selected_user_id}", clear_on_submit=True):
            col_m, col_e, col_s, col_t = st.columns(4)
            nuevo_modulo = col_m.selectbox("Módulo", ["complementarias", "tickets"], key="alc_modulo")
            nueva_empresa = col_e.text_input("Empresa (vacío = todas)", key="alc_empresa")
            nueva_sucursal = col_s.text_input("Sucursal (vacío = todas)", key="alc_sucursal")
            nuevo_tipo = col_t.text_input("Tipo (vacío = todos, solo Complementarias)", key="alc_tipo")

            agregar_alcance = st.form_submit_button("Agregar regla", type="primary")

        if agregar_alcance:
            supabase.table("alcance_usuario").insert({
                "user_id": selected_user_id,
                "modulo": nuevo_modulo,
                "empresa": nueva_empresa.strip() or None,
                "sucursal": nueva_sucursal.strip() or None,
                "tipo": nuevo_tipo.strip() or None,
            }).execute()
            registrar_accion("administracion", "editar_acceso_usuario", {
                "usuario_afectado": selected_row["full_name"],
                "alcance_agregado": {"modulo": nuevo_modulo, "empresa": nueva_empresa, "sucursal": nueva_sucursal, "tipo": nuevo_tipo},
            })
            st.success("Regla de alcance agregada.")
            st.rerun()
