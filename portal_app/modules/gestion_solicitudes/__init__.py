from ui.components import page_banner, section_header, alert, divider
from .gestion_router import render as page

def render():
    """Alias para que pg_gestion_solicitudes.py pueda llamar el módulo."""
    from .gestion_router import render as _render
    _render()
