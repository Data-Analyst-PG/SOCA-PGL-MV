# portal_app/modules/administracion/admin_router.py
# ─────────────────────────────────────────────────────────────────────────────
# Router principal del módulo Administración
# Estructura: segmented_control, cada sección controlada por su propio permiso
# (mismo patrón que modules/cotizadores/picus_router.py y
#  modules/auditoria/auditorias/__init__.py)
#
# Para agregar una sección nueva:
#   1. Crear modules/administracion/nueva_seccion.py con render()
#   2. Agregar entrada en SECCIONES abajo
#   3. Agregar permiso en Supabase: "administracion:nueva_seccion"
# ─────────────────────────────────────────────────────────────────────────────
import streamlit as st

from services.access import check_access
from services.supabase_client import current_user
from services.auditoria import registrar_acceso_submodulo
from ui.components import page_banner, alert

from . import gestion_accesos
from . import auditoria_uso

SECCIONES = [
    {
        "slug":    "accesos",
        "titulo":  "Gestión de Accesos",
        "icono":   "🔐",
        "permiso": "auditoria:admin_manager",
        "modulo":  gestion_accesos,
    },
    {
        "slug":    "auditoria_uso",
        "titulo":  "Auditoría de Uso",
        "icono":   "📊",
        "permiso": "administracion:auditoria_uso",
        "modulo":  auditoria_uso,
    },
]


def render():
    page_banner("🛠️", "Administración", "Gestión de accesos y auditoría de uso del sistema")

    u = current_user() or {}
    user_id = u.get("id") or u.get("sub") or ""

    if not user_id:
        alert("error", "Debes iniciar sesión para acceder a Administración.")
        return

    # Filtrar secciones visibles según permisos
    visibles = [
        s for s in SECCIONES
        if check_access(user_id, None, s["permiso"])
    ]

    if not visibles:
        alert("error", "No tienes acceso a ninguna sección de Administración. Contacta al administrador.")
        return

    # Si solo hay una sección accesible, no mostrar el selector
    if len(visibles) == 1:
        visibles[0]["modulo"].render()
        return

    etiquetas = [f"{s['icono']} {s['titulo']}" for s in visibles]
    etiqueta_a_seccion = {f"{s['icono']} {s['titulo']}": s for s in visibles}

    def _on_cambio_seccion():
        seleccion = st.session_state["admin_router_seccion"]
        seccion_sel = etiqueta_a_seccion.get(seleccion)
        if seccion_sel:
            registrar_acceso_submodulo("administracion", seccion_sel["slug"])

    seleccion = st.segmented_control(
        "Sección",
        options=etiquetas,
        default=etiquetas[0],
        key="admin_router_seccion",
        on_change=_on_cambio_seccion,
    )

    seccion = etiqueta_a_seccion.get(seleccion) or visibles[0]
    seccion["modulo"].render()
