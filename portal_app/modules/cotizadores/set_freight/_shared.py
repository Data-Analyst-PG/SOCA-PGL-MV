from ui.components import section_header, alert, divider
"""
_shared.py  –  Set Freight LLC
Lógica central: conceptos de ingreso/costo, cálculos y helpers.

Modelo de costos:
  Ingresos:      Flete USA + Flete MEX + Cruce + Fuel Surcharge + Otros
  Costos Dir:    Proveedor USA + Cruce Cargado + Cruce Vacío +
                 Proveedor MEX + Doble Operador + Mov Local + Mov Extra + Estancias
  Costo Indir:   Ingreso Total × pct_indirecto  (default 10%)
  Utilidad Neta: Ingreso - CD - CI
"""

from datetime import date, datetime
import pandas as pd
from services.supabase_client import get_supabase_client

# ─── Tabla Supabase ───────────────────────────
TABLE_RUTAS = "sf_rutas"

# ─── Tipos de viaje ──────────────────────────
TIPOS_SERVICIO = ["NB", "SB", "D2D SB", "D2D NB", "PPNB", "PPSB", "DOMUSA"]

# ─── Defaults globales ───────────────────────
DEFAULTS = {
    "Tipo de Cambio USD/MXP": 18.00,
    "% Costo Indirecto":       0.10,
}

# ─── Conceptos de ingreso visibles al cliente ─
CONCEPTOS_INGRESO = {
    "Flete USA":       "flete_usa",
    "Flete MEX":       "flete_mex",
    "Cruce":           "cruce",
    "Fuel Surcharge":  "fuel_surcharge",
    "Otros Ingresos":  "otros_ingresos",
}

# ─── Conceptos de costo interno ──────────────
CONCEPTOS_COSTO = {
    "Proveedor USA":   "proveedor_usa",
    "Cruce Cargado":   "cruce_cargado",
    "Cruce Vacío":     "cruce_vacio",
    "Proveedor MEX":   "proveedor_mex",
    "Doble Operador":  "doble_operador",
    "Mov. Local":      "mov_local",
    "Mov. Extra":      "mov_extra",
    "Estancias":       "estancias",
}


def safe(val, default=0.0) -> float:
    try:
        return float(val) if val not in (None, "", "nan") else default
    except Exception:
        return default


def calcular_ruta(row: dict, pct_indirecto: float = 0.10) -> dict:
    """Recibe un dict con los campos de sf_rutas, devuelve KPIs calculados."""
    ing = sum(safe(row.get(c)) for c in CONCEPTOS_INGRESO.values())
    cd  = sum(safe(row.get(c)) for c in CONCEPTOS_COSTO.values())
    ci  = ing * pct_indirecto
    ut_bruta = ing - cd
    ut_neta  = ing - cd - ci

    return {
        "ingreso_total":   ing,
        "costo_directo":   cd,
        "costo_indirecto": ci,
        "ut_bruta":        ut_bruta,
        "ut_neta":         ut_neta,
        "pct_ut_bruta":    ut_bruta / ing if ing else 0,
        "pct_ut_neta":     ut_neta  / ing if ing else 0,
        "pct_cd":          cd / ing if ing else 0,
        # individuales para desglose
        **{k: safe(row.get(v)) for k, v in CONCEPTOS_INGRESO.items()},
        **{k: safe(row.get(v)) for k, v in CONCEPTOS_COSTO.items()},
    }


def generar_id_ruta() -> str:
    """Genera el siguiente ID correlativo SF000001, SF000002..."""
    sb = get_supabase_client()
    if sb is None:
        return "SF000001"
    try:
        resp = (sb.table(TABLE_RUTAS)
                  .select("id_ruta")
                  .order("created_at", desc=True)
                  .limit(1)
                  .execute())
        ultimo = (resp.data or [{}])[0].get("id_ruta", "SF000000")
        n = int(ultimo.replace("SF", "") or 0) + 1
        return f"SF{n:06d}"
    except Exception:
        return "SF000001"


def limpiar_fila(row: dict) -> dict:
    """Convierte numpy/NaT a tipos serializables para Supabase."""
    clean = {}
    for k, v in row.items():
        if hasattr(v, "item"):          # numpy scalar
            v = v.item()
        if isinstance(v, float) and v != v:  # NaN
            v = None
        if isinstance(v, (date, datetime)):
            v = v.isoformat()
        clean[k] = v
    return clean
