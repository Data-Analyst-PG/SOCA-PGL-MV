from ui.components import page_banner, alert, divider
import streamlit as st

from services.access import check_access
from services.supabase_client import current_user
from . import picus_router, igloo_router, lincoln_router, set_logis_router

# Empresas disponibles — agregar aquí cuando se creen nuevos cotizadores
EMPRESAS = [
    ("picus",   "🚚 Picus",  picus_router, "cotizador_picus:captura"),
    ("igloo",   "🚛 Igloo",  igloo_router, "cotizador_igloo:captura"),
    ("lincoln",     "🚌 Lincoln",        lincoln_router,     "cotizador_lincoln:captura"),
    ("set_logis",   "🏭 Set Logis Plus", set_logis_router,   "cotizador_set_logis:captura"),
    # ("set_freight", "📦 Set Freight",    set_freight_router, "cotizador_set_freight:captura"),

]


def render():
    page_banner("📦", "Cotizadores", "Selecciona la empresa para comenzar")

    # Usuario logueado
    u = current_user() or {}
    user_id = u.get("id") or u.get("sub") or ""

    # Filtrar empresas accesibles
    empresas_visibles = [
        (slug, titulo, router)
        for slug, titulo, router, perm in EMPRESAS
        if check_access(user_id, slug, perm)
    ]

    if not empresas_visibles:
        alert("error", "No tienes acceso a ningún cotizador. Contacta al administrador.")
        return

    # Si solo hay una empresa accesible, entrar directo sin mostrar selector
    empresa_activa = st.session_state.get("_cotizadores_empresa")

    if len(empresas_visibles) == 1 and not empresa_activa:
        st.session_state["_cotizadores_empresa"] = empresas_visibles[0][0]
        st.rerun()

    # Mostrar botones solo para empresas accesibles
    if not empresa_activa:
        alert("info", "Selecciona una empresa para comenzar.")
        cols = st.columns(len(empresas_visibles))
        for i, (slug, titulo, _) in enumerate(empresas_visibles):
            with cols[i]:
                if st.button(titulo, use_container_width=True):
                    st.session_state["_cotizadores_empresa"] = slug
                    st.rerun()
        return

    # Verificar que sigue teniendo acceso a la empresa seleccionada
    slugs_accesibles = [s for s, _, _ in empresas_visibles]
    if empresa_activa not in slugs_accesibles:
        st.session_state.pop("_cotizadores_empresa", None)
        alert("error", "Ya no tienes acceso a ese cotizador.")
        st.rerun()
        return

    # Botón para cambiar de empresa (solo si tiene acceso a más de una)
    if len(empresas_visibles) > 1:
        if st.button("← Cambiar empresa", key="cot_cambiar"):
            st.session_state.pop("_cotizadores_empresa", None)
            st.rerun()

    # Renderizar el router de la empresa seleccionada
    divider()
    router = next(r for s, _, r in empresas_visibles if s == empresa_activa)
    router.render()
