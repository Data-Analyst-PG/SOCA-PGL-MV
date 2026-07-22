# portal_app/modules/auditoria/__init__.py
from . import (
    reporte_auxiliares,
    rutas_frecuentes,
    rentabilidad_clientes,
    prorrateador,
    seguimiento_sac_ventas,
    cartera_proveedores,
    reporte_balanza_mensual,
    auditorias,          # ← nuevo router de auditorías por empresa
)


def reporteauxiliares_page():      reporte_auxiliares.render()
def rutasfrecuentes_page():        rutas_frecuentes.render()
def rentabilidadclientes_page():   rentabilidad_clientes.render()
def prorrateador_page():           prorrateador.render()
def auditorias_page():             auditorias.render()       # ← reemplaza lincolnauditoria_page
def seguimientosacventas_page():   seguimiento_sac_ventas.render()
def carteraproveedores_page():     cartera_proveedores.render()
def reportebalanzamensual_page():  reporte_balanza_mensual.render()
