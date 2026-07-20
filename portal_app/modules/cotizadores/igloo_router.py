from ui.components import page_banner, section_header, alert, divider
import streamlit as st

from services.access import check_access, require_access
from services.supabase_client import current_user
from services.auditoria import registrar_acceso_submodulo

from .igloo import (
    captura_rutas,
    consulta_ruta,
    gestion_rutas,
    simulador,
    cotizacion,
)

# Empresa de este router
COMPANY = "igloo"

# Definición de tabs: (etiqueta, permission_key, módulo)
# El orden aquí es el orden que verá el usuario
TABS = [
    ("🛣️ Captura de Rutas",   "cotizador_igloo:captura",      captura_rutas),
    ("🔍 Consulta Ruta",       "cotizador_igloo:consulta",     consulta_ruta),
    ("🗂️ Gestión de Rutas",   "cotizador_igloo:gestion",      gestion_rutas),
    ("🔁 Simulador VR",        "cotizador_igloo:simulador",    simulador),
    ("🗒️ Cotización",          "cotizador_igloo:cotizacion",   cotizacion),
]


def render():
    # ── Encabezado ──────────────────────────────────────────────────
    page_banner("🚛", "Cotizador Igloo", "Captura, consulta, cotización y programación de viajes")

    # ── Verificar usuario logueado ───────────────────────────────────
    u = current_user() or {}
    user_id = u.get("id") or u.get("sub") or ""

    if not user_id:
        alert("error", "Debes iniciar sesión para acceder al Cotizador Igloo.")
        return

    # ── Filtrar tabs según permisos ──────────────────────────────────
    tabs_visibles = [
        (label, modulo)
        for label, perm, modulo in TABS
        if check_access(user_id, COMPANY, perm)
    ]

    # Guardar permisos correspondientes para doble verificación
    perms_visibles = [
        perm
        for _, perm, modulo in TABS
        if check_access(user_id, COMPANY, perm)
    ]

    if not tabs_visibles:
        alert("error", "No tienes acceso a ningún módulo del Cotizador Igloo.")
        return

    # ── Renderizar solo la sección permitida seleccionada ────────────
    etiquetas = [label for label, _ in tabs_visibles]
    modulos   = [modulo for _, modulo in tabs_visibles]

    def _on_cambio_seccion():
        registrar_acceso_submodulo("cot-igloo", st.session_state["igloo_router_seccion"])

    seccion = st.segmented_control(
        "Sección",
        options=etiquetas,
        default=etiquetas[0],
        key="igloo_router_seccion",
        on_change=_on_cambio_seccion,
    )
    seccion = seccion or etiquetas[0]

    idx    = etiquetas.index(seccion)
    modulo = modulos[idx]

    # Doble verificación al momento de renderizar
    if not require_access(user_id, COMPANY, perms_visibles[idx]):
        return
    modulo.render()
