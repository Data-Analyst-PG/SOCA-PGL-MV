# portal_app/modules/operaciones/operaciones.py
# ─────────────────────────────────────────────────────────────────────────────
# Router principal del módulo Operaciones.
# Cada herramienta es una tab; se agrega aquí sin tocar otros archivos.
# ─────────────────────────────────────────────────────────────────────────────
from ui.components import page_banner, alert
import streamlit as st

from services.access import check_access
from services.supabase_client import current_user
from . import bono_rendimiento

# ── Catálogo de herramientas ──────────────────────────────────────────────────
# Para agregar una nueva: importar el módulo y agregar entrada aquí.
HERRAMIENTAS = [
    {
        "label":   "⛽ Bono Rendimiento",
        "permiso": "operaciones:bono_rendimiento",
        "modulo":  bono_rendimiento,
    },
    # Ejemplo para futuras herramientas:
    # {
    #     "label":   "📦 Otra Herramienta",
    #     "permiso": "operaciones:otra_herramienta",
    #     "modulo":  otra_herramienta,
    # },
]


def render():
    page_banner("⚙️", "Operaciones", "Herramientas de automatización y cálculo interno")

    u = current_user() or {}
    user_id = u.get("id") or u.get("sub") or ""

    if not user_id:
        alert("error", "Debes iniciar sesión para acceder a Operaciones.")
        return

    # Filtrar herramientas según permisos
    visibles = [
        h for h in HERRAMIENTAS
        if check_access(user_id, None, h["permiso"])
    ]

    if not visibles:
        alert("error", "No tienes acceso a ninguna herramienta de Operaciones. Contacta al administrador.")
        return

    # Si solo hay una herramienta accesible, no mostrar tabs
    if len(visibles) == 1:
        visibles[0]["modulo"].render()
        return

    etiquetas = [h["label"] for h in visibles]
    tabs = st.tabs(etiquetas)

    for tab, herramienta in zip(tabs, visibles):
        with tab:
            herramienta["modulo"].render()
