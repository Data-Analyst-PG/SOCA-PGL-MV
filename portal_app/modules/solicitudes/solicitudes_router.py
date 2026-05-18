# portal_app/modules/solicitudes/solicitudes_router.py
import streamlit as st

from services.access import check_access
from services.supabase_client import current_user
from ui.components import page_banner, alert, divider

from .complementarias import captura as comp_captura
from .complementarias import consulta as comp_consulta
from .tickets import crear as ticket_crear
from .tickets import consultar as ticket_consultar
from .viaticos import crear as viatico_crear
from .viaticos import consultar as viatico_consultar


# ── Definición de módulos ─────────────────────────────────────────────────────
# Cada módulo tiene: slug, título, ícono, color, y sus tabs internos
# (etiqueta, permiso requerido, módulo a renderizar)
MODULOS = [
    {
        "slug":  "complementarias",
        "titulo": "📋 Complementarias",
        "tabs": [
            ("➕ Nueva Solicitud",   "complementarias:create", comp_captura),
            ("🔍 Consultar Estatus", "complementarias:read",   comp_consulta),
        ],
    },
    {
        "slug":  "tickets",
        "titulo": "🎫 Tickets",
        "tabs": [
            ("➕ Crear Ticket",      "tickets:create", ticket_crear),
            ("🔍 Consultar Estatus", "tickets:read",   ticket_consultar),
        ],
    },
    {
        "slug":  "viaticos",
        "titulo": "💼 Viáticos",
        "tabs": [
            ("➕ Nueva Solicitud",   "viaticos:create", viatico_crear),
            ("🔍 Consultar Estatus", "viaticos:read",   viatico_consultar),
        ],
    },
]


def render():
    page_banner("📋", "Solicitudes",
                "Crea y consulta complementarias, tickets y viáticos")

    u = current_user() or {}
    user_id = u.get("id") or u.get("sub") or ""

    if not user_id:
        alert("error", "Debes iniciar sesión para acceder a Solicitudes.")
        return

    # ── Filtrar módulos según permisos ────────────────────────────────────────
    modulos_visibles = [
        m for m in MODULOS
        if any(check_access(user_id, None, perm) for _, perm, _ in m["tabs"])
    ]

    if not modulos_visibles:
        alert("error", "No tienes acceso a ningún tipo de solicitud. Contacta al administrador.")
        return

    # ── Si solo hay un módulo, entrar directo ─────────────────────────────────
    if len(modulos_visibles) == 1:
        _render_modulo(modulos_visibles[0], user_id)
        return

    # ── Selector de módulo estilo cotizadores ─────────────────────────────────
    modulo_activo = st.session_state.get("_solicitudes_modulo")

    if not modulo_activo:
        # Mostrar tabs de selección
        etiquetas = [m["titulo"] for m in modulos_visibles]
        tabs = st.tabs(etiquetas)
        for tab, modulo in zip(tabs, modulos_visibles):
            with tab:
                _render_modulo(modulo, user_id)
    else:
        # Módulo seleccionado por botón directo (compatibilidad)
        slugs = [m["slug"] for m in modulos_visibles]
        if modulo_activo not in slugs:
            st.session_state.pop("_solicitudes_modulo", None)
            st.rerun()
            return
        modulo_obj = next(m for m in modulos_visibles if m["slug"] == modulo_activo)
        _render_modulo(modulo_obj, user_id)


def _render_modulo(modulo: dict, user_id: str):
    """Renderiza las tabs internas de un módulo (ej: Nueva Solicitud / Consultar)."""
    tabs_visibles = [
        (label, mod)
        for label, perm, mod in modulo["tabs"]
        if check_access(user_id, None, perm)
    ]

    if not tabs_visibles:
        alert("error", "No tienes acceso a ninguna opción de este módulo.")
        return

    if len(tabs_visibles) == 1:
        tabs_visibles[0][1].render()
        return

    tab_widgets = st.tabs([label for label, _ in tabs_visibles])
    for tab, (_, mod) in zip(tab_widgets, tabs_visibles):
        with tab:
            mod.render()
