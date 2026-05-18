from ui.components import page_banner, section_header, alert, divider
# portal_app/modules/gestion_solicitudes/gestion_router.py
# ─────────────────────────────────────────────────────────────────────────────
# Router estilo "cotizadores" para el módulo de Seguimiento.
# Muestra tarjetas para elegir entre gestionar Complementarias o Tickets,
# y dentro de cada uno muestra la pantalla de gestión correspondiente.
# ─────────────────────────────────────────────────────────────────────────────
import streamlit as st

from services.access import check_access
from services.supabase_client import current_user

# ── Importar los sub-módulos de gestión ──────────────────────────────────────
from . import complementarias as gestion_comp
from . import tickets as gestion_tickets
from . import viaticos as gestion_viaticos

# ═══════════════════════════════════════════════════════════════════════════════
# CATÁLOGO DE TIPOS DE SEGUIMIENTO
# ═══════════════════════════════════════════════════════════════════════════════
# Cada entrada define un tipo con su permiso y módulo de gestión.
# Para agregar un nuevo tipo (ej. Reembolsos) solo agrega otra entrada.
# ═══════════════════════════════════════════════════════════════════════════════

TIPOS_SEGUIMIENTO = [
    {
        "slug": "complementarias",
        "titulo": "Complementarias",
        "icono": "🛡️",
        "color": "#6C3FC5",
        "descripcion": "Gestión y auditoría de solicitudes complementarias",
        "permiso": "complementarias:manage",
        "modulo": gestion_comp,
    },
    {
        "slug": "tickets",
        "titulo": "Tickets",
        "icono": "⚙️",
        "color": "#0E7C61",
        "descripcion": "Gestión de tickets de soporte y desarrollo",
        "permiso": "tickets:manage",
        "modulo": gestion_tickets,
    },
    {
        "slug": "viaticos",
        "titulo": "Viáticos",
        "icono": "💰",
        "color": "#B45309",
        "descripcion": "Gestión de solicitudes de viáticos",
        "permiso": "viaticos:manage",
        "modulo": gestion_viaticos,
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# TARJETA VISUAL
# ═══════════════════════════════════════════════════════════════════════════════

def _render_card(titulo: str, icono: str, color: str, descripcion: str):
    """Dibuja una tarjeta visual con gradiente."""
    page_banner("📋", "Módulo", "")


# ═══════════════════════════════════════════════════════════════════════════════
# ENCABEZADO
# ═══════════════════════════════════════════════════════════════════════════════

def _render_header():
    page_banner("📋", "Seguimiento", "Gestión y seguimiento de solicitudes, tickets y auditorías")


# ═══════════════════════════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL render()
# ═══════════════════════════════════════════════════════════════════════════════

def render():
    _render_header()

    # ── Obtener usuario logueado ─────────────────────────────────────────────
    u = current_user() or {}
    user_id = u.get("id") or u.get("sub") or ""

    if not user_id:
        alert("error", "⚠️ Debes iniciar sesión para acceder a Seguimiento.")
        return

    # ── Filtrar tipos según permisos ─────────────────────────────────────────
    tipos_visibles = [
        t for t in TIPOS_SEGUIMIENTO
        if check_access(user_id, None, t["permiso"])
    ]

    if not tipos_visibles:
        alert("error", "🚫 No tienes acceso a ningún módulo de seguimiento.")
        st.caption("Contacta al administrador para solicitar acceso.")
        return

    # ── Si solo hay un tipo, entrar directo ──────────────────────────────────
    tipo_activo = st.session_state.get("_seguimiento_tipo")

    if len(tipos_visibles) == 1 and not tipo_activo:
        st.session_state["_seguimiento_tipo"] = tipos_visibles[0]["slug"]
        st.rerun()

    # ── Mostrar tarjetas si no hay tipo activo ───────────────────────────────
    if not tipo_activo:
        st.markdown(
            "<p style='text-align:center; color:#888; margin-bottom:1rem;'>"
            "Selecciona el tipo de seguimiento que deseas gestionar</p>",
            unsafe_allow_html=True,
        )

        cols = st.columns(len(tipos_visibles))
        for i, tipo in enumerate(tipos_visibles):
            with cols[i]:
                _render_card(
                    tipo["titulo"],
                    tipo["icono"],
                    tipo["color"],
                    tipo["descripcion"],
                )
                if st.button(
                    f"Abrir {tipo['titulo']}",
                    key=f"seg_btn_{tipo['slug']}",
                    use_container_width=True,
                    type="primary",
                ):
                    st.session_state["_seguimiento_tipo"] = tipo["slug"]
                    st.rerun()
        return

    # ── Verificar acceso ─────────────────────────────────────────────────────
    slugs_accesibles = [t["slug"] for t in tipos_visibles]
    if tipo_activo not in slugs_accesibles:
        st.session_state.pop("_seguimiento_tipo", None)
        alert("error", "🚫 Ya no tienes acceso a ese módulo.")
        st.rerun()
        return

    # ── Botón para regresar ──────────────────────────────────────────────────
    if len(tipos_visibles) > 1:
        if st.button("← Cambiar tipo de seguimiento", key="seg_cambiar"):
            st.session_state.pop("_seguimiento_tipo", None)
            st.rerun()

    # ── Renderizar el módulo de gestión correspondiente ──────────────────────
    tipo_obj = next(t for t in tipos_visibles if t["slug"] == tipo_activo)

    divider()
    tipo_obj["modulo"].render()
