from . import cotizadores as home
from . import picus_router, igloo_router, lincoln_router, set_logis_router, set_freight_router

def cotizadores_page():
    home.render()

def picus_page():
    picus_router.render()

def igloo_page():
    igloo_router.render()

def lincoln_page():
    lincoln_router.render()

def set_logis_page(): 
    set_logis_router.render()
    
def set_freight_page():
    set_freight_router.render()
