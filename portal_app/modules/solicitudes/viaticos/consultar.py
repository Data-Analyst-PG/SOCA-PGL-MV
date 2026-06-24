from __future__ import annotations

import streamlit as st
import pandas as pd

from supabase import create_client

from services.supabase_client import current_user

from ui.components import (
    section_header,
    kpi_row,
    alert,
    solicitudes_table,
)


def render():

    # =====================================================
    # USER
    # =====================================================

    user = current_user()

    if not user:
        alert(
            "error",
            "Debes iniciar sesión."
        )
        return

    nombre_usuario = (
        user.get("name")
        or user.get("email")
        or ""
    )

    # =====================================================
    # MTN SUPABASE
    # =====================================================

    sb = create_client(
        st.secrets["MTN_SUPABASE_URL"],
        st.secrets["MTN_SUPABASE_SERVICE_KEY"]
    )

    # =====================================================
    # PAGE HEADER
    # =====================================================

    section_header(
        "📊",
        "Consulta de Viáticos",
        "Historial de solicitudes y comprobaciones"
    )

    # =====================================================
    # SOLICITUDES
    # =====================================================

    try:

        solicitudes_resp = (
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

        solicitudes = (
            solicitudes_resp.data
            if solicitudes_resp.data
            else []
        )

        # Excluir solicitudes generadas automáticamente
        solicitudes = [

            s

            for s in solicitudes

            if s.get("motivo_viaje")
            != "Operacion/Solicitud sin Folio"
        ]

        # =================================
        # EXTRAER MONEDA DESDE CONCEPTOS
        # =================================

        for s in solicitudes:

            conceptos = s.get("conceptos", []) or []

            monedas = sorted(
                list(
                    {
                        item.get("Tipo Cambio", "MXP")
                        for item in conceptos
                    }
                )
            )

            s["tipo_cambio"] = ", ".join(monedas)

    except Exception as e:

        alert(
            "error",
            f"Error cargando solicitudes: {e}"
        )

        solicitudes = []

    # =====================================================
    # KPIS SOLICITUDES
    # =====================================================

    pendientes = len([
        x for x in solicitudes
        if x.get("estatus") == "Pendiente"
    ])

    aprobadas = len([
        x for x in solicitudes
        if x.get("estatus") == "Aprobado"
    ])

    rechazadas = len([
        x for x in solicitudes
        if x.get("estatus") == "Rechazado"
    ])

    verificando = len([
        x for x in solicitudes
        if x.get("estatus") == "Verificar"
    ])

    kpi_row([
        {
            "icono": "📄",
            "label": "Solicitudes",
            "valor": len(solicitudes),
            "color": "#1D4ED8"
        },
        {
            "icono": "⏳",
            "label": "Pendientes",
            "valor": pendientes,
            "color": "#D97706"
        },
        {
            "icono": "✅",
            "label": "Aprobadas",
            "valor": aprobadas,
            "color": "#059669"
        },
        {
            "icono": "❌",
            "label": "Rechazadas",
            "valor": rechazadas,
            "color": "#DC2626"
        }
    ])

    st.divider()

    st.subheader("📋 Solicitudes de Viaje")

    if solicitudes:

        df_solicitudes = pd.DataFrame(solicitudes)

        df_solicitudes = df_solicitudes.rename(
            columns={
                "tipo_cambio": "Moneda",
                "total_estimado": "Total a Aprobar"
            }
        )

        columnas_existentes = [
            c for c in [
                "folio_solicitud",
                "empresa_brinda_servicio",
                "motivo_viaje",
                "Moneda",
                "fecha_inicio",
                "fecha_fin",
                "Total a Aprobar",
                "estatus"
            ]
            if c in df_solicitudes.columns
        ]

        solicitudes_table(
            df_solicitudes[columnas_existentes]
        )

    else:

        st.info(
            "No existen solicitudes registradas."
        )

    st.divider()

    # =====================================================
    # COMPROBACIONES
    # =====================================================

    try:

        comprobaciones_resp = (
            sb.table("comprobacion_viaje")
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

        comprobaciones = (
            comprobaciones_resp.data
            if comprobaciones_resp.data
            else []
        )

    except Exception as e:

        alert(
            "error",
            f"Error cargando comprobaciones: {e}"
        )

        comprobaciones = []

    # =====================================================
    # KPI COMPROBACIONES
    # =====================================================

    mxp_comprobado = 0
    usd_comprobado = 0

    mxp_anticipos = 0
    usd_anticipos = 0

    mxp_diferencia = 0
    usd_diferencia = 0

    for comp in comprobaciones:

        conceptos = comp.get(
            "conceptos",
            []
        ) or []

        moneda_principal = "MXP"

        if conceptos:

            moneda_principal = conceptos[0].get(
                "Moneda",
                "MXP"
            )

        total_comprobado = float(
            comp.get(
                "total_comprobado",
                0
            ) or 0
        )

        anticipo = float(
            comp.get(
                "anticipo_viaje",
                0
            ) or 0
        )

        diferencia = float(
            comp.get(
                "diferencia_cargo_favor",
                0
            ) or 0
        )

        if moneda_principal == "USD":

            usd_comprobado += total_comprobado
            usd_anticipos += anticipo
            usd_diferencia += diferencia

        else:

            mxp_comprobado += total_comprobado
            mxp_anticipos += anticipo
            mxp_diferencia += diferencia

    kpi_row([
        {
            "icono": "🧾",
            "label": "Comprobaciones",
            "valor": len(comprobaciones),
            "color": "#7C3AED"
        },
        {
            "icono": "💰",
            "label": "Comprobado MXP",
            "valor": f"${mxp_comprobado:,.0f}",
            "color": "#059669"
        },
        {
            "icono": "💵",
            "label": "Comprobado USD",
            "valor": f"${usd_comprobado:,.0f}",
            "color": "#2563EB"
        },
        {
            "icono": "📊",
            "label": "Dif. MXP / USD",
            "valor": (
                f"${mxp_diferencia:,.0f}"
                f" | "
                f"${usd_diferencia:,.0f}"
            ),
            "color": "#D97706"
        }
    ])

    st.divider()

    st.subheader("🧾 Comprobaciones")

    if comprobaciones:

        df_comp = pd.DataFrame(comprobaciones)

        columnas = [
            "folio_comprobacion",
            "folio_solicitud",
            "total_comprobado",
            "anticipo_viaje",
            "diferencia_cargo_favor",
            "estatus"
        ]

        columnas_existentes = [
            c for c in columnas
            if c in df_comp.columns
        ]

        solicitudes_table(
            df_comp[columnas_existentes]
        )

    else:

        st.info(
            "No existen comprobaciones registradas."
        )