"""
set_logis_router.py  –  Set Logis Plus
Router principal con st.tabs() — igual que Picus e Igloo.
"""

import streamlit as st

from services.access import check_access, require_access
from services.supabase_client import current_user
from ui.components import page_banner, alert
from services.auditoria import registrar_acceso_submodulo

from .set_logis import (
    captura_rutas,
    consulta_ruta,
    gestion_rutas,
    simulador,
    cotizacion,
)

COMPANY = "set_logis"

TABS = [
    ("🛣️ Captura de Rutas",  "cotizador_set_logis:captura",    captura_rutas),
    ("🔍 Consulta Ruta",      "cotizador_set_logis:consulta",   consulta_ruta),
    ("🗂️ Gestión de Rutas",  "cotizador_set_logis:gestion",    gestion_rutas),
    ("🔁 Simulador VR",       "cotizador_set_logis:simulador",  simulador),
    ("🗒️ Cotización",         "cotizador_set_logis:cotizacion", cotizacion),
]


def render():
    page_banner("🚚", "Set Logis Plus", "Cotizador Owner-Operator · Subidas & Bajadas USA/MX")

    u = current_user() or {}
    user_id = u.get("id") or u.get("sub") or ""

    if not user_id:
        alert("error", "Debes iniciar sesión para acceder al Cotizador Set Logis.")
        return

    tabs_visibles = [
        (label, modulo)
        for label, perm, modulo in TABS
        if check_access(user_id, COMPANY, perm)
    ]
    perms_visibles = [
        perm
        for _, perm, modulo in TABS
        if check_access(user_id, COMPANY, perm)
    ]

    if not tabs_visibles:
        alert("error", "No tienes acceso a ningún módulo del Cotizador Set Logis.")
        return

   etiquetas = [label for label, _ in tabs_visibles]
    modulos   = [modulo for _, modulo in tabs_visibles]

    def _on_cambio_seccion():
        registrar_acceso_submodulo("cot-set-logis", st.session_state["sl_router_seccion"])

    seccion = st.segmented_control(
        "Sección",
        options=etiquetas,
        default=etiquetas[0],
        key="sl_router_seccion",
        on_change=_on_cambio_seccion,
    )
    seccion = seccion or etiquetas[0]

    idx    = etiquetas.index(seccion)
    modulo = modulos[idx]

    if not require_access(user_id, COMPANY, perms_visibles[idx]):
        return
    modulo.render()
