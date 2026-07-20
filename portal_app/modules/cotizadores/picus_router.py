from ui.components import page_banner, section_header, alert, divider
import streamlit as st

from services.access import check_access, require_access
from services.supabase_client import current_user
from services.auditoria import registrar_acceso_submodulo

from .picus import (
    captura_rutas,
    consulta_ruta,
    gestion_rutas,
    simulador,
    cotizacion,
)

# Empresa de este router
COMPANY = "picus"

# Definición de tabs: (etiqueta, permission_key, módulo)
TABS = [
    ("🛣️ Captura de Rutas",   "cotizador_picus:captura",      captura_rutas),
    ("🔍 Consulta Ruta",       "cotizador_picus:consulta",     consulta_ruta),
    ("🗂️ Gestión de Rutas",   "cotizador_picus:gestion",      gestion_rutas),
    ("🔁 Simulador VR",        "cotizador_picus:simulador",    simulador),
    ("🗒️ Cotización",          "cotizador_picus:cotizacion",   cotizacion),
]


def render():
    # ── Encabezado ──────────────────────────────────────────────────
    page_banner("🚚", "Cotizador Picus", "Captura, consulta, cotización y programación de viajes")

    # ── Verificar usuario logueado ───────────────────────────────────
    u = current_user() or {}
    user_id = u.get("id") or u.get("sub") or ""

    if not user_id:
        alert("error", "Debes iniciar sesión para acceder al Cotizador Picus.")
        return

    # ── Filtrar tabs según permisos ──────────────────────────────────
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
        alert("error", "No tienes acceso a ningún módulo del Cotizador Picus.")
        return

   # ── Renderizar solo la sección permitida seleccionada ────────────
    etiquetas = [label for label, _ in tabs_visibles]
    modulos   = [modulo for _, modulo in tabs_visibles]

    def _on_cambio_seccion():
        registrar_acceso_submodulo("cot-picus", st.session_state["picus_router_seccion"])

    seccion = st.segmented_control(
        "Sección",
        options=etiquetas,
        default=etiquetas[0],
        key="picus_router_seccion",
        on_change=_on_cambio_seccion,
    )
    seccion = seccion or etiquetas[0]

    idx    = etiquetas.index(seccion)
    modulo = modulos[idx]

    if not require_access(user_id, COMPANY, perms_visibles[idx]):
        return
    modulo.render()
