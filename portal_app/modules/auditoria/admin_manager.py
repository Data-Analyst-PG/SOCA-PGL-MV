import os
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from services.supabase_client import get_supabase_client, get_authed_client, current_user

st.write("DEBUG VERSION 2")

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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

# =================================
# ADMIN PAGE
# =================================
def render():
    from ui.components import section_header, alert, divider
    st.title("Administración de Permisos")

    try:
        supabase = get_supabase_client()  # MUST be service-role internally

        # =================================
        # LOAD ALL USERS
        # =================================
        res = supabase.table("profiles").select(
            "user_id, role, company_id, is_active, created_at, full_name, job_title, area_name, access"
        ).execute()

        data = res.data or []

        if not data:
            alert("warn", "No hay usuarios en profiles.")
            return

        df = pd.DataFrame(data)

        # =================================
        # ENSURE NO DROPDOWN COLLAPSE
        # =================================
        df["full_name"] = df["full_name"].fillna("Sin Nombre")

        # IMPORTANT: do NOT use .unique()
        selected_user_id = st.selectbox(
            "Seleccionar Usuario",
            options=df["user_id"],
            format_func=lambda uid: df.loc[df["user_id"] == uid, "full_name"].values[0]
        )

        selected_row = df[df["user_id"] == selected_user_id].iloc[0]

        # =================================
        # USER INFO
        # =================================
        section_header("▸", "Información del Usuario")

        # --- TOGGLE BUTTON ---
        current_status = bool(selected_row["is_active"])

        button_label = "Deactivate User" if current_status else "Activate User"

        if st.button(button_label):
            new_status = not current_status

            supabase.table("profiles").update({
                "is_active": new_status
            }).eq("user_id", selected_user_id).execute()

            st.success(f"Usuario {'activado' if new_status else 'desactivado'} correctamente")

            st.rerun()

        # --- USER DETAILS ---
        st.write(f"**Nombre:** {selected_row['full_name']}")
        st.write(f"**Role:** {selected_row['role']}")
        st.write(f"**Área:** {selected_row['area_name']}")
        st.write(f"**Activo:** {selected_row['is_active']}")

        # =================================
        # ACCESS MANAGEMENT
        # =================================

        ALL_ROLES = [
            "tickets:read","tickets:create","tickets:manage","ventas:buscador","ventas:subastas",
            "complementarias:read","auditoria:prorrateador","auditoria:rentabilidad",
            "complementarias:create","complementarias:manage","auditoria:admin_manager",
            "cotizador_igloo:captura","cotizador_igloo:gestion","cotizador_picus:captura",
            "cotizador_picus:gestion","cotizador_igloo:consulta","cotizador_picus:consulta",
            "cotizador_igloo:simulador","cotizador_lincoln:captura","cotizador_lincoln:gestion",
            "cotizador_picus:simulador","facturacion:estado_cuenta","auditoria:rutas_frecuentes",
            "cotizador_igloo:concluidos","cotizador_igloo:cotizacion","cotizador_lincoln:consulta",
            "cotizador_picus:concluidos","cotizador_picus:cotizacion","cotizador_lincoln:simulador",
            "cotizador_set_logis:captura","cotizador_set_logis:gestion","auditoria:reporte_auxiliares",
            "cotizador_igloo:programacion","cotizador_lincoln:concluidos","cotizador_lincoln:cotizacion",
            "cotizador_picus:programacion","cotizador_set_logis:consulta","cotizador_set_freight:captura",
            "cotizador_set_freight:gestion","cotizador_set_logis:simulador","cotizador_lincoln:programacion",
            "cotizador_set_freight:consulta","cotizador_set_logis:concluidos","cotizador_set_logis:cotizacion",
            "cotizador_set_freight:simulador","cotizador_set_freight:concluidos","cotizador_set_freight:cotizacion",
            "cotizador_set_logis:programacion","cotizador_set_freight:programacion"
        ]

        # normalize current access
        current_access = selected_row.get("access") or {}
        if isinstance(current_access, list):
            current_access = {k: True for k in current_access}

        # Dropdown
        selected_role = st.selectbox("Seleccionar Acceso", ALL_ROLES)

        # Buttons BELOW
        col_btn1, col_btn2 = st.columns(2)

        with col_btn1:
            if st.button("Permitir Acceso"):
                if selected_role not in current_access:
                    current_access[selected_role] = True

                    supabase.table("profiles").update({
                        "access": current_access
                    }).eq("user_id", selected_user_id).execute()

                    st.success(f"Acceso agregado: {selected_role}")
                    st.rerun()
                else:
                    alert("warn", "El usuario ya tiene este acceso")

        with col_btn2:
            if st.button("Revocar Acceso"):
                if selected_role in current_access:
                    current_access.pop(selected_role)

                    supabase.table("profiles").update({
                        "access": current_access
                    }).eq("user_id", selected_user_id).execute()

                    st.success(f"Acceso removido: {selected_role}")
                    st.rerun()
                else:
                    alert("warn", "El usuario no tiene este acceso")

        # =================================
        # ACCESS JSON
        # =================================
        section_header("▸", "Permisos (Access JSON)")

        if selected_row["access"]:
            st.json(selected_row["access"])
        else:
            alert("info", "Este usuario no tiene permisos definidos.")

    except Exception as e:
        st.error(f"Error: {e}")
