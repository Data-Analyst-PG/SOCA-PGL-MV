from __future__ import annotations

import pandas as pd
import streamlit as st

from services.supabase_client import current_user

# CHANGE THIS IMPORT TO WHATEVER FUNCTION YOU CREATED
# FOR THE MTN DATABASE
from services.supabase_client import get_mtn_client

from ui.components import (
    section_header,
    kpi_row,
    alert,
    solicitudes_table,
)

# --------------------------------------------------
# LOAD DATA
# --------------------------------------------------

@st.cache_data(ttl=30)
def cargar_solicitudes(nombre_usuario):

    sb = get_mtn_client()

    result = (
        sb.table("solicitud_viaje")
        .select("*")
        .eq(
            "nombre_empleado_solicita",
            nombre_usuario
        )
        .order(
            "created_at",
            desc=True
        )
        .execute()
    )

    return result.data or []


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def render():

    user = current_user()

    if not user:

        alert(
            "error",
            "Debes iniciar sesión."
        )

        st.stop()

    nombre_usuario = (
        user.get("name")
        or user.get("email")
        or ""
    )

    solicitudes = cargar_solicitudes(
        nombre_usuario
    )

    section_header(
        "💳",
        "Mis Viáticos",
        "Consulta tus solicitudes y comprobaciones"
    )

    # --------------------------------------------------
    # KPIs
    # --------------------------------------------------

    total = len(solicitudes)

    pendientes = sum(
        1
        for x in solicitudes
        if str(
            x.get("estatus", "")
        ).lower() == "pendiente"
    )

    autorizadas = sum(
        1
        for x in solicitudes
        if str(
            x.get("estatus", "")
        ).lower() in [
            "autorizada",
            "aprobado",
            "aprobada"
        ]
    )

    rechazadas = sum(
        1
        for x in solicitudes
        if str(
            x.get("estatus", "")
        ).lower() == "rechazada"
    )

    kpi_row([
        {
            "icono": "📄",
            "label": "Total",
            "valor": total,
            "color": "#2563EB",
        },
        {
            "icono": "⏳",
            "label": "Pendientes",
            "valor": pendientes,
            "color": "#D97706",
        },
        {
            "icono": "✅",
            "label": "Autorizadas",
            "valor": autorizadas,
            "color": "#059669",
        },
        {
            "icono": "❌",
            "label": "Rechazadas",
            "valor": rechazadas,
            "color": "#DC2626",
        },
    ])

    st.divider()

    # --------------------------------------------------
    # TABLE
    # --------------------------------------------------

    if not solicitudes:

        alert(
            "info",
            "No existen solicitudes registradas."
        )

        return

    df = pd.DataFrame(
        solicitudes
    )

    columnas = [
        "folio_solicitud",
        "empresa_brinda_servicio",
        "motivo_viaje",
        "fecha_solicitud",
        "fecha_inicio",
        "fecha_fin",
        "total_estimado",
        "estatus"
    ]

    columnas_existentes = [
        c
        for c in columnas
        if c in df.columns
    ]

    df = df[columnas_existentes]

    solicitudes_table(df)

    st.download_button(
        "⬇️ Descargar Excel",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="mis_viaticos.csv",
        mime="text/csv",
    )