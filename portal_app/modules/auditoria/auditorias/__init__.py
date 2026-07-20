# portal_app/modules/auditoria/auditorias/__init__.py
# ─────────────────────────────────────────────────────────────────────────────
# Router de Auditorías por Empresa
# Estructura: una tab por empresa, controlada por permisos individuales
# Para agregar una empresa nueva:
#   1. Crear modules/auditoria/auditorias/nueva_empresa.py con render()
#   2. Agregar entrada en EMPRESAS abajo
#   3. Agregar permiso en Supabase: "auditoria:nueva_empresa"
# ─────────────────────────────────────────────────────────────────────────────
import streamlit as st

from services.supabase_client import current_user
from services.access import check_access
from services.auditoria import registrar_acceso_submodulo
from ui.components import page_banner, alert

from . import lincoln
from . import igloo
from . import picus
from . import set_freight
from . import set_logis


# Catálogo de empresas — orden, icono, permiso y módulo
EMPRESAS = [
    {
        "slug":       "lincoln",
        "titulo":     "Lincoln Freight",
        "icono":      "🏴",
        "permiso":    "auditoria:lincoln_auditoria",
        "modulo":     lincoln,
        "disponible": True,
    },
    {
        "slug":       "igloo",
        "titulo":     "Igloo",
        "icono":      "🚛",
        "permiso":    "auditoria:igloo_auditoria",
        "modulo":     igloo,
        "disponible": True,   # ← cambiar a True cuando esté desarrollado
    },
    {
        "slug":       "picus",
        "titulo":     "Picus",
        "icono":      "🚚",
        "permiso":    "auditoria:picus_auditoria",
        "modulo":     picus,
        "disponible": True,
    },
    {
        "slug":       "set_freight",
        "titulo":     "Set Freight",
        "icono":      "📦",
        "permiso":    "auditoria:set_freight_auditoria",
        "modulo":     set_freight,
        "disponible": True,
    },
    {
        "slug":       "set_logis",
        "titulo":     "Set Logis",
        "icono":      "🚚",
        "permiso":    "auditoria:set_logis_auditoria",
        "modulo":     set_logis,
        "disponible": True,
    },
]


def render():
    page_banner("🔍", "Auditorías por Empresa",
                "Selecciona la empresa para revisar su reporte mensual")

    u = current_user() or {}
    user_id = u.get("id") or u.get("sub") or ""

    if not user_id:
        alert("error", "Debes iniciar sesión para acceder a Auditorías.")
        return

    # Filtrar empresas visibles según permisos
    empresas_visibles = [
        e for e in EMPRESAS
        if check_access(user_id, None, e["permiso"])
    ]

    if not empresas_visibles:
        alert("error", "No tienes acceso a ninguna auditoría. Contacta al administrador.")
        return

    # Construir segmented_control solo con las empresas accesibles
    etiquetas = [f"{e['icono']} {e['titulo']}" for e in empresas_visibles]
    etiqueta_a_empresa = {f"{e['icono']} {e['titulo']}": e for e in empresas_visibles}

    def _on_cambio_empresa():
        seleccion = st.session_state["aud_auditorias_empresa"]
        empresa_sel = etiqueta_a_empresa.get(seleccion)
        if empresa_sel:
            registrar_acceso_submodulo("aud-auditorias", empresa_sel["slug"])

    seleccion = st.segmented_control(
        "Empresa",
        options=etiquetas,
        default=etiquetas[0],
        key="aud_auditorias_empresa",
        on_change=_on_cambio_empresa,
    )

    # Si el usuario deselecciona el segmento activo (posible con segmented_control,
    # a diferencia de st.tabs que siempre tiene una pestaña activa), cae a la primera empresa
    empresa = etiqueta_a_empresa.get(seleccion) or empresas_visibles[0]

    if not empresa["disponible"]:
        alert("info",
              f"La auditoría de {empresa['titulo']} está en desarrollo. "
              "Estará disponible próximamente.")
    else:
        empresa["modulo"].render()
