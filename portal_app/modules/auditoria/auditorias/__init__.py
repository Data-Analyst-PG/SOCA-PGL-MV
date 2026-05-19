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
        "disponible": False,
    },
    {
        "slug":       "set_freight",
        "titulo":     "Set Freight",
        "icono":      "📦",
        "permiso":    "auditoria:set_freight_auditoria",
        "modulo":     set_freight,
        "disponible": False,
    },
    {
        "slug":       "set_logis",
        "titulo":     "Set Logis",
        "icono":      "🚚",
        "permiso":    "auditoria:set_logis_auditoria",
        "modulo":     set_logis,
        "disponible": False,
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

    # Construir tabs solo con las empresas accesibles
    etiquetas = [f"{e['icono']} {e['titulo']}" for e in empresas_visibles]
    tabs = st.tabs(etiquetas)

    for tab, empresa in zip(tabs, empresas_visibles):
        with tab:
            if not empresa["disponible"]:
                alert("info",
                      f"La auditoría de {empresa['titulo']} está en desarrollo. "
                      "Estará disponible próximamente.")
            else:
                empresa["modulo"].render()
