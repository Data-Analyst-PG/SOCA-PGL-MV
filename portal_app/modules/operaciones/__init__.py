# portal_app/modules/operaciones/__init__.py
# ─────────────────────────────────────────────────────────────────────────────
# Módulo de Operaciones — herramientas de automatización interna
# Para agregar una nueva herramienta:
#   1. Crear modules/operaciones/nueva_herramienta.py con render()
#   2. Agregarla al TABS de operaciones.py
#   3. Agregar su permiso en Supabase: "operaciones:nueva_herramienta"
# ─────────────────────────────────────────────────────────────────────────────
from . import operaciones


def operaciones_page():
    operaciones.render()
