# portal_app/modules/administracion/auditoria_uso.py
# ─────────────────────────────────────────────────────────────────────────────
# Dashboard de Auditoría de Uso — lee las 3 tablas de auditoría del sistema:
#   auditoria_sesiones        (login por sesión)
#   auditoria_accesos_modulo  (navegación por módulo)
#   auditoria_acciones        (acciones completadas: crear_ruta, generar_pdf, etc.)
#
# Esquema real de las tablas (verificado en Supabase, proyecto uouxmagxrlfepcckrnbm):
#   auditoria_sesiones:       id, full_name, company_id, created_at
#   auditoria_accesos_modulo: id, full_name, modulo, empresa, created_at
#   auditoria_acciones:       id, full_name, modulo, accion, detalle, created_at
# ─────────────────────────────────────────────────────────────────────────────
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from services.supabase_client import get_authed_client
from ui.components import section_header, alert, divider, kpi_row

TZ_LOCAL = ZoneInfo("America/Matamoros")


def _a_hora_local(iso_str) -> str:
    """Convierte un timestamp ISO (UTC) al horario local de Matamoros."""
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(TZ_LOCAL).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(iso_str)


@st.cache_data(ttl=60, show_spinner=False)
def _cargar_tabla(nombre_tabla: str, desde_iso: str, limite: int = 3000) -> list:
    sb = get_authed_client()
    res = (
        sb.table(nombre_tabla)
        .select("*")
        .gte("created_at", desde_iso)
        .order("created_at", desc=True)
        .limit(limite)
        .execute()
    )
    return res.data or []


def render():
    section_header("📊", "Auditoría de Uso", "Logins, navegación y acciones registradas en SOCA")

    dias = st.selectbox(
        "Periodo",
        [1, 7, 15, 30, 90],
        index=1,
        format_func=lambda d: f"Últimos {d} días",
        key="admin_au_periodo",
    )
    desde = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()

    try:
        sesiones = _cargar_tabla("auditoria_sesiones", desde)
        accesos  = _cargar_tabla("auditoria_accesos_modulo", desde)
        acciones = _cargar_tabla("auditoria_acciones", desde)
    except Exception as e:
        alert("error", f"No se pudo cargar la auditoría: {e}")
        return

    df_sesiones = pd.DataFrame(sesiones)
    df_accesos  = pd.DataFrame(accesos)
    df_acciones = pd.DataFrame(acciones)

    usuarios_activos = set()
    for df in (df_sesiones, df_accesos, df_acciones):
        if not df.empty and "full_name" in df.columns:
            usuarios_activos.update(df["full_name"].dropna().unique().tolist())

    kpi_row([
        dict(icono="🔑", label="Logins",           valor=len(df_sesiones), sub=f"últimos {dias} días", color="#1B2266"),
        dict(icono="🧭", label="Accesos a módulos", valor=len(df_accesos),  sub=f"últimos {dias} días", color="#0077B6"),
        dict(icono="⚡", label="Acciones",          valor=len(df_acciones), sub=f"últimos {dias} días", color="#059669"),
        dict(icono="👥", label="Usuarios activos",  valor=len(usuarios_activos), sub="con actividad", color="#CC1E1E"),
    ])

    divider()

    filtro_usuario = "Todos"
    if usuarios_activos:
        filtro_usuario = st.selectbox(
            "Filtrar por usuario",
            ["Todos"] + sorted(usuarios_activos),
            key="admin_au_usuario",
        )

    def _filtrar(df):
        if df.empty or filtro_usuario == "Todos" or "full_name" not in df.columns:
            return df
        return df[df["full_name"] == filtro_usuario]

    df_accesos_f  = _filtrar(df_accesos)
    df_acciones_f = _filtrar(df_acciones)
    df_sesiones_f = _filtrar(df_sesiones)

    tab1, tab2, tab3 = st.tabs(["🧭 Accesos a Módulos", "⚡ Acciones", "🔑 Logins"])

    with tab1:
        if df_accesos_f.empty:
            alert("info", "Sin accesos registrados en el periodo.")
        else:
            vista = df_accesos_f.copy()
            vista["Fecha/Hora"] = vista["created_at"].apply(_a_hora_local)
            cols = [c for c in ["Fecha/Hora", "full_name", "modulo", "empresa"] if c in vista.columns]
            st.dataframe(
                vista[cols].rename(columns={"full_name": "Usuario", "modulo": "Módulo", "empresa": "Sección/Empresa"}),
                use_container_width=True, height=400,
            )
            st.caption("Accesos por módulo")
            st.bar_chart(df_accesos_f["modulo"].value_counts())

    with tab2:
        if df_acciones_f.empty:
            alert("info", "Sin acciones registradas en el periodo.")
        else:
            vista = df_acciones_f.copy()
            vista["Fecha/Hora"] = vista["created_at"].apply(_a_hora_local)
            cols = [c for c in ["Fecha/Hora", "full_name", "modulo", "accion", "detalle"] if c in vista.columns]
            st.dataframe(
                vista[cols].rename(columns={"full_name": "Usuario", "modulo": "Módulo", "accion": "Acción", "detalle": "Detalle"}),
                use_container_width=True, height=400,
            )
            st.caption("Acciones por tipo")
            st.bar_chart(df_acciones_f["accion"].value_counts())

    with tab3:
        if df_sesiones_f.empty:
            alert("info", "Sin logins registrados en el periodo.")
        else:
            vista = df_sesiones_f.copy()
            vista["Fecha/Hora"] = vista["created_at"].apply(_a_hora_local)
            cols = [c for c in ["Fecha/Hora", "full_name", "company_id"] if c in vista.columns]
            st.dataframe(
                vista[cols].rename(columns={"full_name": "Usuario", "company_id": "Empresa"}),
                use_container_width=True, height=400,
            )
