# portal_app/modules/solicitudes/solicitudes_router.py
# ─────────────────────────────────────────────────────────────────────────────
# Router de Solicitudes — usa sistema de componentes UI
# ─────────────────────────────────────────────────────────────────────────────
import streamlit as st

from services.access import check_access
from services.supabase_client import current_user
from ui.components import page_banner, module_card, alert

from .complementarias import captura as comp_captura
from .complementarias import consulta as comp_consulta
from .tickets import crear as ticket_crear
from .tickets import consultar as ticket_consultar


TIPOS_SOLICITUD = [
    {
        "slug": "complementarias",
        "titulo": "Complementarias",
        "icono": "📋",
        "color": "#6C3FC5",
        "descripcion": "Solicitudes de cargos complementarios para tráficos",
        "tabs": [
            ("➕ Nueva Solicitud",   "complementarias:create", comp_captura),
            ("🔍 Consultar Estatus", "complementarias:read",   comp_consulta),
        ],
    },
    {
        "slug": "tickets",
        "titulo": "Tickets",
        "icono": "🎫",
        "color": "#0E7C61",
        "descripcion": "Tickets de soporte para el equipo de Análisis de Datos",
        "tabs": [
            ("➕ Crear Ticket",      "tickets:create", ticket_crear),
            ("🔍 Consultar Estatus", "tickets:read",   ticket_consultar),
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

    # ── Filtrar tipos según permisos ──────────────────────────────────────────
    tipos_visibles = [
        t for t in TIPOS_SOLICITUD
        if any(check_access(user_id, None, perm) for _, perm, _ in t["tabs"])
    ]

    if not tipos_visibles:
        alert("error", "No tienes acceso a ningún tipo de solicitud. Contacta al administrador.")
        return

    tipo_activo = st.session_state.get("_solicitudes_tipo")

    # Entrada directa si solo hay un tipo
    if len(tipos_visibles) == 1 and not tipo_activo:
        st.session_state["_solicitudes_tipo"] = tipos_visibles[0]["slug"]
        st.rerun()

    # ── Pantalla de selección ─────────────────────────────────────────────────
    if not tipo_activo:
        st.markdown(
            "<p style='color:#6B7280; margin-bottom:1rem;'>"
            "Selecciona el tipo de solicitud que deseas realizar</p>",
            unsafe_allow_html=True,
        )
        cols = st.columns(len(tipos_visibles))
        for i, tipo in enumerate(tipos_visibles):
            with cols[i]:
                module_card(
                    icono=tipo["icono"],
                    titulo=tipo["titulo"],
                    descripcion=tipo["descripcion"],
                    color_acento=tipo["color"],
                )
                if st.button(
                    f"Abrir {tipo['titulo']}",
                    key=f"sol_btn_{tipo['slug']}",
                    use_container_width=True,
                    type="primary",
                ):
                    st.session_state["_solicitudes_tipo"] = tipo["slug"]
                    st.rerun()
        return

    # ── Verificar acceso al tipo activo ──────────────────────────────────────
    if tipo_activo not in [t["slug"] for t in tipos_visibles]:
        st.session_state.pop("_solicitudes_tipo", None)
        alert("error", "Ya no tienes acceso a ese tipo de solicitud.")
        st.rerun()
        return

    # ── Botón volver ──────────────────────────────────────────────────────────
    if len(tipos_visibles) > 1:
        if st.button("← Cambiar tipo de solicitud", key="sol_cambiar"):
            st.session_state.pop("_solicitudes_tipo", None)
            st.rerun()

    tipo_obj = next(t for t in tipos_visibles if t["slug"] == tipo_activo)

    st.divider()

    # ── Tabs del tipo seleccionado ────────────────────────────────────────────
    tabs_visibles = [
        (label, modulo)
        for label, perm, modulo in tipo_obj["tabs"]
        if check_access(user_id, None, perm)
    ]

    if not tabs_visibles:
        alert("error", "No tienes acceso a ninguna opción de este tipo.")
        return

    tab_widgets = st.tabs([label for label, _ in tabs_visibles])
    for tab, (_, modulo) in zip(tab_widgets, tabs_visibles):
        with tab:
            modulo.render()
