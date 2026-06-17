"""
_shared.py – Set Logis Plus
Helpers, defaults y cálculo central.

Fórmula tarifa americana (Desglosada):
  Flete = Miles_Load × CXM_Flete
  Fuel  = Miles_Load × CXM_Fuel      ← ambos sobre Miles Load
  Total = Flete + Fuel

Pago owner:
  Cargado = Short_Miles × PxM_cargado
  Vacío   = Miles_Empty × PxM_vacio
  (Miles_Load es solo para ingreso Desglosado — no se usa en pago owner)

Fuel Owner (opcional):
  Si fuel_owner=True, el valor de Fuel (Miles_Load × CXM_Fuel) se suma
  como costo adicional al owner — aumenta Costo_Directo y reduce margen.

Extras:
  extras_costo = extras NO cobrados al cliente (costo puro)
  Extras cobrados al cliente ya van sumados en flete_usa al llamar.
"""

from __future__ import annotations

import json
import os
import re
import time
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
TIPOS_RUTA   = ["NB", "SB", "D2DNB", "D2DSB", "Empty"]
TIPOS_CON_MX = {"D2DNB", "D2DSB"}
TIPOS_SUBIDA = {"NB", "D2DNB", "Empty"}
TIPOS_BAJADA = {"SB", "D2DSB"}

# ─────────────────────────────────────────────
# EXTRAS
# ─────────────────────────────────────────────
EXTRAS_USA = [
    "Stop Off",
    "Detention",
    "Lumper Fees",
    "Layover",
    "Fianzas",
    "Additional Insurance",
    "Loadlocks",
    "Accessories",
    "Guias",
    "Maniobras",
    "Mov Extraordinario",
]

# ─────────────────────────────────────────────
# DEFAULTS
# ─────────────────────────────────────────────
DEFAULTS: dict[str, float] = {
    "PxM Owner Subidas":       1.60,
    "PxM Owner Bajadas":       1.40,
    "PxM Owner Vacio":         0.80,
    "PxM Owner Subidas Team":  1.80,
    "PxM Owner Bajadas Team":  1.60,
    "PxM Owner Vacio Team":    0.90,
    "Cruce Propio Cargado":   80.00,
    "Cruce Propio Vacio":     50.00,
    "Tipo de Cambio USD/MXP": 18.50,
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
                for k, v in DEFAULTS.items():
                    if k not in out:
                        out[k] = v
            else:
                out = DEFAULTS.copy()
        except Exception:
            out = DEFAULTS.copy()
    else:
        out = DEFAULTS.copy()

    # TC FIX de Banxico (cache 24h)
    try:
        from services.banxico import get_tipo_cambio_fix
        tc = get_tipo_cambio_fix()
        if tc:
            out["Tipo de Cambio USD/MXP"] = tc
    except Exception:
        pass

    return out


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
# HELPERS DE TEXTO Y CONVERSIÓN
# (movidos desde captura_rutas — usados en captura, gestion, consulta)
# ─────────────────────────────────────────────
def normalizar(texto: str) -> str:
    """Convierte texto a mayúsculas, elimina espacios extra y normaliza comas."""
    if not texto:
        return ""
    texto = str(texto).upper().strip()
    texto = re.sub(r"\s+", " ", texto)
    texto = re.sub(r"\s*,\s*", ", ", texto)
    return texto


def a_usd(monto: float, moneda: str, tc: float) -> float:
    """Convierte un monto a USD si está en MXP usando el tipo de cambio dado."""
    if moneda == "MXP":
        return monto / tc if tc > 0 else 0.0
    return monto


def get_profile_name(user_id: str) -> str | None:
    """Obtiene el nombre completo del usuario desde la tabla profiles de Supabase."""
    from services.supabase_client import get_supabase_client
    sb = get_supabase_client()
    if sb is None or not user_id:
        return None
    try:
        res = sb.table("profiles").select("full_name").eq("id", user_id).maybe_single().execute()
        return (res.data or {}).get("full_name")
    except Exception:
        return None


def generar_id_ruta(supabase) -> str:
    """
    Genera el siguiente ID correlativo para Rutas_SetLogis.
    Formato: SL000001, SL000002, ...
    Fallback con timestamp si falla la consulta.
    """
    try:
        resp = supabase.table(TABLE_RUTAS).select("ID_Ruta").order("ID_Ruta", desc=True).limit(1).execute()
        if resp.data:
            ultimo = str(resp.data[0].get("ID_Ruta", "SL000000"))
            num = int(re.sub(r"\D", "", ultimo)[-6:]) + 1
        else:
            num = 1
        return f"SL{num:06d}"
    except Exception:
        return f"SL{int(time.time()) % 1000000:06d}"


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
    modo: str,
    ruta_usa: str,
    cliente: str,
    miles_load: float,
    miles_empty: float,
    short_miles: float,
    flete_usa: float,
    fuel: float,
    tipo_cruce: str,
    tipo_carga_cruce: str,
    ingreso_cruce: float,
    costo_cruce_externo: float,
    ingreso_mx: float,
    costo_mx: float,
    extras_ingreso: float,
    extras_costo: float,
    modo_costo_indirecto: str,
    valores: dict,
    fuel_owner: bool = False,
    incluye_cruce: bool = False,
) -> dict:

    v = valores

    # ── MILLAS ───────────────────────────────────────────────────────────────
    # Miles_Load: solo para ingreso desglosado (flete/fuel con cliente)
    # Short_Miles: millas reales recorridas cargado → pago al owner
    # Miles_Empty: millas vacías → pago al owner vacío
    millas_short    = safe(short_miles)
    millas_vacias   = safe(miles_empty)
    millas_totales  = millas_short + millas_vacias   # base para costo indirecto CXM

    # ── PAGO OWNER ───────────────────────────────────────────────────────────
    pxm_cargado        = _pxm_cargado(tipo_ruta, modo, v)
    pxm_vacio_v        = _pxm_vacio(modo, v)
    pago_owner_cargado = millas_short  * pxm_cargado
    pago_owner_vacio   = millas_vacias * pxm_vacio_v
    pago_owner_total   = pago_owner_cargado + pago_owner_vacio

    # ── FUEL OWNER ────────────────────────────────────────────────────────────
    # Si fuel_owner está activo, el fuel (Miles_Load × CXM_Fuel) se paga al owner
    # El monto ya viene calculado en el parámetro `fuel` (Flete_USA lo excluye)
    pago_fuel_owner = safe(fuel) if fuel_owner else 0.0

    # ── FLETE / FUEL ─────────────────────────────────────────────────────────
    flete_fuel = safe(flete_usa) + safe(fuel)

    # ── CRUCE ────────────────────────────────────────────────────────────────
    if not incluye_cruce:
        costo_cruce = 0.0
    elif tipo_cruce == "Propio":
        key_cruce   = "Cruce Propio Cargado" if tipo_carga_cruce == "Cargado" else "Cruce Propio Vacio"
        costo_cruce = safe(v.get(key_cruce, 80.0))
    else:
        costo_cruce = safe(costo_cruce_externo)

    # ── INGRESO GLOBAL ───────────────────────────────────────────────────────
    ingreso_global = (
        safe(flete_usa)
        + safe(fuel)
        + safe(ingreso_cruce)
        + safe(ingreso_mx)
        + safe(extras_ingreso)
    )

    # ── COSTO DIRECTO ────────────────────────────────────────────────────────
    costo_mx_calc       = safe(costo_mx)
    extras_costo_total  = safe(extras_costo)
    costo_directo_total = (
        pago_owner_total
        + pago_fuel_owner
        + costo_cruce
        + costo_mx_calc
        + extras_costo_total
    )

    # ── COSTO INDIRECTO ───────────────────────────────────────────────────────
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
    pct_ind_ = _pct(costo_indirecto,     ingreso_global)
    pct_ut_b = _pct(utilidad_bruta,      ingreso_global)
    pct_ut_n = _pct(utilidad_neta,       ingreso_global)

    # ── SEMÁFOROS Set Logis ───────────────────────────────────────────────────
    color_dir  = "#16a34a" if pct_dir  <= 85.0 else "#dc2626"
    color_ind  = "#16a34a" if pct_ind_ <=  9.0 else "#dc2626"
    color_ut_n = "#16a34a" if pct_ut_n >=  6.0 else "#dc2626"

    return {
        "Tipo_Viaje":          tipo_ruta,
        "Modo":                modo,
        "Direccion":           direccion_label(tipo_ruta),
        "Ruta_USA":            ruta_usa,
        "Cliente":             cliente,
        "Miles_Load":          miles_load,
        "Miles_Empty":         miles_empty,
        "Short_Miles":         short_miles,
        "Millas_Totales":      millas_totales,
        "PxM_Cargado":         pxm_cargado,
        "PxM_Vacio":           pxm_vacio_v,
        "Flete_USA":           flete_usa,
        "Fuel":                fuel,
        "Flete_Fuel":          flete_fuel,
        "Ingreso_Cruce":       ingreso_cruce,
        "Ingreso_MX":          ingreso_mx,
        "Extras_Ingreso":      extras_ingreso,
        "Ingreso_Global":      ingreso_global,
        "Tipo_Cruce":          tipo_cruce,
        "Costo_Cruce":         costo_cruce,
        "Costo_MX":            costo_mx_calc,
        "Pago_Owner_Cargado":  pago_owner_cargado,
        "Pago_Owner_Vacio":    pago_owner_vacio,
        "Pago_Owner_Total":    pago_owner_total,
        "Fuel_Owner":          fuel_owner,
        "Pago_Fuel_Owner":     pago_fuel_owner,
        "Extras_Costo":        extras_costo,
        "Extras_Costo_Total":  extras_costo_total,
        "Costo_Directo":       costo_directo_total,
        "Costo_Indirecto":     costo_indirecto,
        "Costo_Total":         costo_total,
        "Utilidad_Bruta":      utilidad_bruta,
        "Utilidad_Neta":       utilidad_neta,
        "Pct_Costo_Directo":   pct_dir,
        "Pct_Costo_Indirecto": pct_ind_,
        "Pct_Ut_Bruta":        pct_ut_b,
        "Pct_Ut_Neta":         pct_ut_n,
        "Color_Directo":       color_dir,
        "Color_Indirecto":     color_ind,
        "Color_Ut_Neta":       color_ut_n,
        "CXM_Indirecto":       cxm_aplicado,
        "Pct_Indirecto":       pct_aplicado,
        "TC":                  safe(v.get("Tipo de Cambio USD/MXP", 18.50)),
    }
