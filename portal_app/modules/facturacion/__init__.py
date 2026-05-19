# portal_app/modules/facturacion/__init__.py
from .estado_cuenta import render as _estado_cuenta
from .cargar_datos  import render as _cargar_datos

def estado_cuenta_page():
    _estado_cuenta()

def cargar_datos_page():
    _cargar_datos()
