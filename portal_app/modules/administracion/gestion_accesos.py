# portal_app/modules/administracion/gestion_accesos.py
# ─────────────────────────────────────────────────────────────────────────────
# Gestión de Accesos — activar/desactivar usuarios y otorgar/revocar permisos.
# Migrado desde modules/auditoria/admin_manager.py (se elimina ese archivo
# una vez confirmado que este funciona correctamente).
#
# Cambios respecto al original:
#   - Se quitó el st.write("DEBUG VERSION 2") que quedó de una prueba
#   - Se agregaron keys explícitas a los widgets
#   - Cada cambio de acceso/estatus ahora se registra en auditoria_acciones
#     (antes no quedaba rastro de quién otorgó/revocó qué)
# ─────────────────────────────────────────────────────────────────────────────
import pandas as pd
import streamlit as st

from services.supabase_client import get_supabase_client, get_authed_client
from services.auditoria import registrar_accion
from ui.components import section_header, alert, divider


def _get_profile_name(user_id: str) -> str:
    """Obtiene el full_name del usuario logueado desde profiles."""
    if not user_id:
        return ""
    try:
        supabase = get_authed_client()
        res = supabase.table("profiles").select("full_name").eq("user_id", user_id).single().execute()
        return (res.data or {}).get("full_name") or ""
    except Exception:
        return ""


# Catálogo de permisos disponibles en el sistema.
# Agregar aquí cualquier permiso nuevo que se cree en otros módulos.
ALL_ROLES = [
    "tickets:read", "tickets:create", "tickets:manage", "ventas:buscador", "ventas:subastas",
    "complementarias:read", "auditoria:prorrateador", "auditoria:rentabilidad",
    "complementarias:create", "complementarias:manage", "auditoria:admin_manager",
    "administracion:auditoria_uso", "operaciones:bono_rendimiento",
    "cotizador_igloo:captura", "cotizador_igloo:gestion", "cotizador_picus:captura",
    "cotizador_picus:gestion", "cotizador_igloo:consulta", "cotizador_picus:consulta",
    "cotizador_igloo:simulador", "cotizador_lincoln:captura", "cotizador_lincoln:gestion",
    "cotizador_picus:simulador", "facturacion:estado_cuenta", "auditoria:rutas_frecuentes",
    "cotizador_igloo:concluidos", "cotizador_igloo:cotizacion", "cotizador_lincoln:consulta",
    "cotizador_picus:concluidos", "cotizador_picus:cotizacion", "cotizador_lincoln:simulador",
    "cotizador_set_logis:captura", "cotizador_set_logis:gestion", "auditoria:reporte_auxiliares",
    "cotizador_igloo:programacion", "cotizador_lincoln:concluidos", "cotizador_lincoln:cotizacion",
    "cotizador_picus:programacion", "cotizador_set_logis:consulta", "cotizador_set_freight:captura",
    "cotizador_set_freight:gestion", "cotizador_set_logis:simulador", "cotizador_lincoln:programacion",
    "cotizador_set_freight:consulta", "cotizador_set_logis:concluidos", "cotizador_set_logis:cotizacion",
    "cotizador_set_freight:simulador", "cotizador_set_freight:concluidos", "cotizador_set_freight:cotizacion",
    "cotizador_set_logis:programacion", "cotizador_set_freight:programacion",
]


def render():
    section_header("🔐", "Gestión de Accesos", "Activar/desactivar usuarios y otorgar/revocar permisos")

    try:
        supabase = get_supabase_client()  # MUST be service-role internally

        res = supabase.table("profiles").select(
            "user_id, role, company_id, is_active, created_at, full_name, job_title, area_name, access"
        ).execute()

        data = res.data or []

        if not data:
            alert("warn", "No hay usuarios en profiles.")
            return

        df = pd.DataFrame(data)
        df["full_name"] = df["full_name"].fillna("Sin Nombre")

        # IMPORTANT: no usar .unique()
        selected_user_id = st.selectbox(
            "Seleccionar Usuario",
            options=df["user_id"],
            format_func=lambda uid: df.loc[df["user_id"] == uid, "full_name"].values[0],
            key="admin_ga_user_sel",
        )

        selected_row = df[df["user_id"] == selected_user_id].iloc[0]

        # =================================
        # INFO DEL USUARIO
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

        st.write(f"**Nombre:** {selected_row['full_name']}")
        st.write(f"**Role:** {selected_row['role']}")
        st.write(f"**Área:** {selected_row['area_name']}")
        st.write(f"**Activo:** {selected_row['is_active']}")

        divider()

        # =================================
        # GESTIÓN DE PERMISOS
        # =================================
        section_header("▸", "Gestión de Permisos")

        current_access = selected_row.get("access") or {}
        if isinstance(current_access, list):
            current_access = {k: True for k in current_access}

        selected_role = st.selectbox("Seleccionar Acceso", ALL_ROLES, key="admin_ga_perm_sel")

        col_btn1, col_btn2 = st.columns(2)

        with col_btn1:
            if st.button("Permitir Acceso", key="admin_ga_permitir"):
                if selected_role not in current_access:
                    current_access[selected_role] = True
                    supabase.table("profiles").update({"access": current_access}).eq("user_id", selected_user_id).execute()
                    try:
                        registrar_accion("administracion", "editar_acceso_usuario", {
                            "usuario_afectado": selected_row["full_name"],
                            "permiso": selected_role,
                            "cambio": "otorgado",
                        })
                    except Exception:
                        pass
                    st.success(f"Acceso agregado: {selected_role}")
                    st.rerun()
                else:
                    alert("warn", "El usuario ya tiene este acceso")

        with col_btn2:
            if st.button("Revocar Acceso", key="admin_ga_revocar"):
                if selected_role in current_access:
                    current_access.pop(selected_role)
                    supabase.table("profiles").update({"access": current_access}).eq("user_id", selected_user_id).execute()
                    try:
                        registrar_accion("administracion", "editar_acceso_usuario", {
                            "usuario_afectado": selected_row["full_name"],
                            "permiso": selected_role,
                            "cambio": "revocado",
                        })
                    except Exception:
                        pass
                    st.success(f"Acceso removido: {selected_role}")
                    st.rerun()
                else:
                    alert("warn", "El usuario no tiene este acceso")

        divider()
        section_header("▸", "Permisos (Access JSON)")

        if selected_row["access"]:
            st.json(selected_row["access"])
        else:
            alert("info", "Este usuario no tiene permisos definidos.")

    except Exception as e:
        st.error(f"Error: {e}")
