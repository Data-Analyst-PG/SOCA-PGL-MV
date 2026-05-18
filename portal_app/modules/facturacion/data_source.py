"""
portal_app/modules/facturacion/data_source.py

⭐ ESTE ES EL ÚNICO ARCHIVO QUE CAMBIA CUANDO PASEN DE JSON A SUPABASE ⭐

La app (facturacion.py) SIEMPRE llama estas funciones:
  - get_clientes()
  - get_facturas_cliente(cliente_id)

Hoy leen del JSON.
Mañana leerán de Supabase.
El resto de la app no se toca.
"""

import json
import os
from datetime import date
from typing import Optional

# ─── Configuración: cambiar aquí cuando se migre ─────────────────────────────
MODO = "json"          # ← cambiar a "supabase" cuando estén las tablas listas
# ─────────────────────────────────────────────────────────────────────────────

_JSON_PATH = os.path.join(os.path.dirname(__file__), "datos_facturacion.json")


# ══════════════════════════════════════════════════════════════════════════════
# MODO JSON  (datos de prueba)
# ══════════════════════════════════════════════════════════════════════════════

def _leer_json():
    with open(_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _clientes_json() -> list:
    return _leer_json()["clientes"]


def _facturas_cliente_json(cliente_id: str) -> list:
    data = _leer_json()
    facturas = [f for f in data["facturas"] if f["cliente_id"] == cliente_id]

    # Convertir fechas string → date y recalcular dias_vencido
    hoy = date.today()
    for f in facturas:
        f["fecha_emision"]     = date.fromisoformat(f["fecha_emision"])
        f["fecha_vencimiento"] = date.fromisoformat(f["fecha_vencimiento"])
        if f["estatus"] in ("pendiente", "vencida") and f["fecha_pago"] is None:
            delta = (hoy - f["fecha_vencimiento"]).days
            f["dias_vencido"] = max(delta, 0)
            f["estatus"] = "vencida" if delta > 0 else "pendiente"

    return facturas


# ══════════════════════════════════════════════════════════════════════════════
# MODO SUPABASE  (producción — descomentar cuando esté listo)
# ══════════════════════════════════════════════════════════════════════════════

def _clientes_supabase() -> list:
    """
    FUTURO: leer de tabla 'clientes' en Supabase.
    Descomentar y ajustar cuando las tablas estén creadas.
    """
    # from services.supabase_client import get_authed_client
    # sb = get_authed_client()
    # res = sb.table("clientes").select("*").eq("activo", True).execute()
    # return res.data or []
    raise NotImplementedError("Aún no configurado. Cambiar MODO='supabase' cuando las tablas estén listas.")


def _facturas_cliente_supabase(cliente_id: str) -> list:
    """
    FUTURO: leer de tabla 'facturas' en Supabase.
    """
    # from services.supabase_client import get_authed_client
    # from datetime import date
    # sb = get_authed_client()
    # res = (sb.table("facturas")
    #          .select("*")
    #          .eq("cliente_id", cliente_id)
    #          .neq("estatus", "cancelada")
    #          .execute())
    # facturas = res.data or []
    # hoy = date.today()
    # for f in facturas:
    #     f["fecha_emision"]     = date.fromisoformat(f["fecha_emision"])
    #     f["fecha_vencimiento"] = date.fromisoformat(f["fecha_vencimiento"])
    #     if f["estatus"] in ("pendiente", "vencida"):
    #         delta = (hoy - f["fecha_vencimiento"]).days
    #         f["dias_vencido"] = max(delta, 0)
    # return facturas
    raise NotImplementedError("Aún no configurado.")


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIONES PÚBLICAS — estas llama facturacion.py, nunca cambian
# ══════════════════════════════════════════════════════════════════════════════

def get_clientes() -> list:
    """Devuelve lista de clientes activos."""
    if MODO == "json":
        return _clientes_json()
    elif MODO == "supabase":
        return _clientes_supabase()
    else:
        raise ValueError(f"MODO desconocido: {MODO}")


def get_facturas_cliente(cliente_id: str) -> list:
    """Devuelve facturas activas de un cliente."""
    if MODO == "json":
        return _facturas_cliente_json(cliente_id)
    elif MODO == "supabase":
        return _facturas_cliente_supabase(cliente_id)
    else:
        raise ValueError(f"MODO desconocido: {MODO}")


def get_cliente_by_id(cliente_id: str) -> Optional[dict]:
    """Busca un cliente por su ID."""
    clientes = get_clientes()
    return next((c for c in clientes if c["id"] == cliente_id), None)
