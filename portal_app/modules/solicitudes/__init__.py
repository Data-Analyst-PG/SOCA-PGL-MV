from .solicitudes_router import render as page

def render():
    """Alias para que pg_solicitudes.py pueda llamar solicitudes.render()"""
    from .solicitudes_router import render as _render
    _render()
