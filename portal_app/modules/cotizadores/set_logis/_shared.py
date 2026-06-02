"""
_shared.py – Set Logis Plus  (v2)
Helpers, defaults y cálculo central.

Lógica de dirección (derivada del tipo de ruta):
  NB  / D2DNB  → Subida
  SB  / D2DSB  → Bajada
  Empty        → sin ingreso, solo pago millas vacías

Lógica de millas y pago owner:
  Pago = (miles_load + short_miles) × PxM_cargado
        + miles_empty × PxM_vacio

Modo Team → usa tarifas Team de config.
Cruce:
  "Sin cruce" → ingreso=0, costo=0
  "Propio"    → costo fijo de config (Cargado o Vacío según tipo_carga)
  "Externo"   → costo capturado en formulario
Ruta MX (D2D): siempre externo, ingreso y costo en USD.

Semáforos Set Logis:
  Directos ≤ 85% verde | Indirectos ≤ 9% verde | Ut.Neta ≥ 6% verde
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime

import numpy as np
import pandas as pd

# ─────────────────────────────────────────────
# TABLAS SUPABASE
# ─────────────────────────────────────────────
TABLE_RUTAS    = "Rutas_SetLogis"
TABLE_TRAFICOS = "Traficos_SetLogis"

# ─────────────────────────────────────────────
# TIPOS DE RUTA
# ─────────────────────────────────────────────
TIPOS_RUTA    = ["NB", "SB", "D2DNB", "D2DSB", "Empty"]
TIPOS_CON_MX  = {"D2DNB", "D2DSB"}
TIPOS_SUBIDA  = {"NB", "D2DNB", "Empty"}
TIPOS_BAJADA  = {"SB", "D2DSB"}

# ─────────────────────────────────────────────
# DEFAULTS
# ─────────────────────────────────────────────
DEFAULTS: dict[str, float] = {
    # Owner individual (USD/milla)
    "PxM Owner Subidas":       1.60,
    "PxM Owner Bajadas":       1.40,
    "PxM Owner Vacio":         0.80,
    # Owner Team (USD/milla)
    "PxM Owner Subidas Team":  1.80,
    "PxM Owner Bajadas Team":  1.60,
    "PxM Owner Vacio Team":    0.90,
    # Cruce propio (USD)
    "Cruce Propio Cargado":   80.00,
    "Cruce Propio Vacio":     50.00,
    # Tipo de cambio
    "Tipo de Cambio USD/MXP": 18.50,
    # Costos indirectos
    "CXM Indirecto":           0.10,
    "% Costo Indirecto":       0.09,
}

# ─────────────────────────────────────────────
# RUTAS DE ARCHIVOS
# ─────────────────────────────────────────────
def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _datos_generales_path() -> str:
    base = os.path.join(_project_root(), ".data")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "datos_generales_setlogis.csv")


# ─────────────────────────────────────────────
# CARGA / GUARDA DATOS GENERALES
# ─────────────────────────────────────────────
def cargar_datos_generales() -> dict:
    path = _datos_generales_path()
    if os.path.exists(path):
        try:
            df = pd.read_csv(path)
            if {"Parametro", "Valor"}.issubset(df.columns):
                d   = df.set_index("Parametro")["Valor"].to_dict()
                out = DEFAULTS.copy()
                for k, v in d.items():
                    try:
                        out[k] = float(v)
                    except Exception:
                        out[k] = v
                return out
        except Exception:
            pass
    return DEFAULTS.copy()


def guardar_datos_generales(valores: dict) -> None:
    df = pd.DataFrame(list(valores.items()), columns=["Parametro", "Valor"])
    df.to_csv(_datos_generales_path(), index=False)


# ─────────────────────────────────────────────
# HELPERS NUMÉRICOS
# ─────────────────────────────────────────────
def safe(x, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        f = float(x)
        return default if (isinstance(f, float) and np.isnan(f)) else f
    except Exception:
        return default


def limpiar_fila_json(fila: dict) -> dict:
    limpio: dict = {}
    for k, v in fila.items():
        if v is None or (isinstance(v, float) and np.isnan(v)):
            limpio[k] = None
        elif isinstance(v, (pd.Timestamp, datetime, date, np.datetime64)):
            limpio[k] = str(v)[:10]
        elif isinstance(v, np.integer):
            limpio[k] = int(v)
        elif isinstance(v, np.floating):
            limpio[k] = float(v)
        else:
            try:
                json.dumps(v)
                limpio[k] = v
            except TypeError:
                limpio[k] = str(v)
    return limpio


# ─────────────────────────────────────────────
# HELPERS DE NEGOCIO
# ─────────────────────────────────────────────
def es_subida(tipo_ruta: str) -> bool:
    return tipo_ruta in TIPOS_SUBIDA


def es_bajada(tipo_ruta: str) -> bool:
    return tipo_ruta in TIPOS_BAJADA


def tiene_mx(tipo_ruta: str) -> bool:
    return tipo_ruta in TIPOS_CON_MX


def direccion_label(tipo_ruta: str) -> str:
    return "Bajada" if es_bajada(tipo_ruta) else "Subida"


def _pxm_cargado(tipo_ruta: str, modo: str, v: dict) -> float:
    team = modo == "Team"
    if es_bajada(tipo_ruta):
        return safe(v.get("PxM Owner Bajadas Team" if team else "PxM Owner Bajadas", 1.40))
    return safe(v.get("PxM Owner Subidas Team" if team else "PxM Owner Subidas", 1.60))


def _pxm_vacio(modo: str, v: dict) -> float:
    team = modo == "Team"
    return safe(v.get("PxM Owner Vacio Team" if team else "PxM Owner Vacio", 0.80))


# ─────────────────────────────────────────────
# CÁLCULO CENTRAL
# ─────────────────────────────────────────────
def calcular_ruta_setlogis(
    *,
    tipo_ruta: str,
    modo: str,                    # "Sencillo" | "Team"
    ruta_usa: str,
    cliente: str,
    miles_load: float,
    miles_empty: float,
    short_miles: float,
    # Ingresos USA (ya en USD)
    flete_usa: float,
    fuel: float,
    # Cruce (ya en USD)
    tipo_cruce: str,              # "Sin cruce" | "Propio" | "Externo"
    ingreso_cruce: float,
    costo_cruce_externo: float,
    # Ruta MX (ya en USD, solo D2D)
    ingreso_mx: float,
    costo_mx: float,
    # Costo indirecto
    modo_costo_indirecto: str,    # "CXM" | "Porcentaje"
    valores: dict,
) -> dict:

    v = valores

    # Tarifas
    pxm_cargado    = _pxm_cargado(tipo_ruta, modo, v)
    pxm_vacio_v    = _pxm_vacio(modo, v)
    tc             = safe(v.get("Tipo de Cambio USD/MXP", 18.50))

    # Millas
    miles_load  = safe(miles_load)
    miles_empty = safe(miles_empty)
    short_miles = safe(short_miles)
    millas_totales = miles_load + miles_empty + short_miles

    # ── INGRESOS ─────────────────────────────────────────────────────────────
    is_empty = tipo_ruta == "Empty"

    if is_empty:
        flete_usa = fuel = flete_fuel = ingreso_usa = 0.0
        ingreso_cruce = ingreso_mx = 0.0
    else:
        flete_usa  = safe(flete_usa)
        fuel       = safe(fuel)
        flete_fuel = flete_usa + fuel
        ingreso_usa = flete_fuel

    ingreso_cruce = safe(ingreso_cruce) if not is_empty else 0.0
    ingreso_mx    = safe(ingreso_mx) if (tiene_mx(tipo_ruta) and not is_empty) else 0.0
    ingreso_global = ingreso_usa + ingreso_cruce + ingreso_mx

    # ── COSTO CRUCE ──────────────────────────────────────────────────────────
    if is_empty or tipo_cruce == "Sin cruce":
        costo_cruce = 0.0
    elif tipo_cruce == "Propio":
        # La key correcta según tipo_carga se pasa desde el formulario vía valores
        # Por simplicidad usamos Cargado como default; el formulario ya controla esto
        costo_cruce = safe(v.get("Cruce Propio Cargado", 80.0))
    else:  # Externo
        costo_cruce = safe(costo_cruce_externo)

    # ── COSTO MX ─────────────────────────────────────────────────────────────
    costo_mx_calc = safe(costo_mx) if tiene_mx(tipo_ruta) else 0.0

    # ── PAGO OWNER ───────────────────────────────────────────────────────────
    pago_owner_cargado = (miles_load + short_miles) * pxm_cargado
    pago_owner_vacio   = miles_empty * pxm_vacio_v
    pago_owner_total   = pago_owner_cargado + pago_owner_vacio

    # ── COSTOS DIRECTOS ───────────────────────────────────────────────────────
    costo_directo_total = pago_owner_total + costo_cruce + costo_mx_calc

    # ── COSTOS INDIRECTOS ─────────────────────────────────────────────────────
    if modo_costo_indirecto == "CXM":
        cxm_ind         = safe(v.get("CXM Indirecto", 0.10))
        costo_indirecto = millas_totales * cxm_ind
        cxm_aplicado    = cxm_ind
        pct_aplicado    = (costo_indirecto / ingreso_global) if ingreso_global > 0 else 0.0
    else:
        pct_ind         = safe(v.get("% Costo Indirecto", 0.09))
        costo_indirecto = ingreso_global * pct_ind
        pct_aplicado    = pct_ind
        cxm_aplicado    = (costo_indirecto / millas_totales) if millas_totales > 0 else 0.0

    # ── UTILIDADES ────────────────────────────────────────────────────────────
    costo_total    = costo_directo_total + costo_indirecto
    utilidad_bruta = ingreso_global - costo_directo_total
    utilidad_neta  = ingreso_global - costo_total

    def _pct(num: float, den: float) -> float:
        return (num / den * 100) if den > 0 else 0.0

    pct_dir  = _pct(costo_directo_total, ingreso_global)
    pct_ind  = _pct(costo_indirecto,     ingreso_global)
    pct_ut_b = _pct(utilidad_bruta,      ingreso_global)
    pct_ut_n = _pct(utilidad_neta,       ingreso_global)

    # ── SEMÁFOROS ────────────────────────────────────────────────────────────
    color_dir  = "#16a34a" if pct_dir  <= 85.0 else "#dc2626"
    color_ind  = "#16a34a" if pct_ind  <=  9.0 else "#dc2626"
    color_ut_n = "#16a34a" if pct_ut_n >=  6.0 else "#dc2626"

    return {
        # Identificación
        "Tipo_Viaje":          tipo_ruta,
        "Modo":                modo,
        "Direccion":           direccion_label(tipo_ruta),
        "Ruta_USA":            ruta_usa,
        "Cliente":             cliente,
        # Millas
        "Miles_Load":          miles_load,
        "Miles_Empty":         miles_empty,
        "Short_Miles":         short_miles,
        "Millas_Totales":      millas_totales,
        # Tarifas aplicadas
        "PxM_Cargado":         pxm_cargado,
        "PxM_Vacio":           pxm_vacio_v,
        # Ingresos
        "Flete_USA":           flete_usa,
        "Fuel":                fuel,
        "Flete_Fuel":          flete_fuel if not is_empty else 0.0,
        "Ingreso_Cruce":       ingreso_cruce,
        "Ingreso_MX":          ingreso_mx,
        "Ingreso_Global":      ingreso_global,
        # Cruce
        "Tipo_Cruce":          tipo_cruce,
        "Costo_Cruce":         costo_cruce,
        # MX
        "Costo_MX":            costo_mx_calc,
        # Costos owner
        "Pago_Owner_Cargado":  pago_owner_cargado,
        "Pago_Owner_Vacio":    pago_owner_vacio,
        "Pago_Owner_Total":    pago_owner_total,
        # Costos agrupados
        "Costo_Directo":       costo_directo_total,
        "Costo_Indirecto":     costo_indirecto,
        "Costo_Total":         costo_total,
        # Utilidades
        "Utilidad_Bruta":      utilidad_bruta,
        "Utilidad_Neta":       utilidad_neta,
        # Porcentajes
        "Pct_Costo_Directo":   pct_dir,
        "Pct_Costo_Indirecto": pct_ind,
        "Pct_Ut_Bruta":        pct_ut_b,
        "Pct_Ut_Neta":         pct_ut_n,
        # Semáforos
        "Color_Directo":       color_dir,
        "Color_Indirecto":     color_ind,
        "Color_Ut_Neta":       color_ut_n,
        # Auxiliares
        "CXM_Indirecto":       cxm_aplicado,
        "Pct_Indirecto":       pct_aplicado,
        "TC":                  tc,
    }
