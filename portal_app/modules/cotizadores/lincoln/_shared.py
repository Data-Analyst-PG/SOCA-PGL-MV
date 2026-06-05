"""
_shared.py  –  Lincoln Freight (USA/MX)
Helpers, defaults y lógica de cálculo central.
Tipos de ruta: NB, SB, D2DNB, D2DSB, Empty  (alineado con Set Logis Plus)
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import date, datetime

import numpy as np
import pandas as pd

from services.supabase_client import get_supabase_client, get_authed_client

# ─────────────────────────────────────────────
# TABLAS SUPABASE
# ─────────────────────────────────────────────
TABLE_RUTAS    = "Rutas_Lincoln"
TABLE_TRAFICOS = "Traficos_Lincoln"

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
    "Stop Off", "Detention", "Lumper Fees", "Layover",
    "Fianzas", "Additional Insurance", "Loadlocks",
    "Accessories", "Guias", "Maniobras", "Mov Extraordinario",
]

# ─────────────────────────────────────────────
# DEFAULTS
# ─────────────────────────────────────────────
DEFAULTS: dict[str, float] = {
    # Operador USA (por milla) — camión propio
    "CXM Operador USA":           0.48,   # $/milla cargado sencillo
    "CXM Operador USA (Empty)":   0.30,   # $/milla vacío sencillo
    "CXM Team USA":               0.30,   # $/milla cargado team (x operador)
    "CXM Team USA (Empty)":       0.25,   # $/milla vacío team
    # Rendimiento / diesel USA
    "Truck Performance (mpg)":    7.0,
    "Diesel Price ($/gal)":       3.60,
    # Cruce fronterizo
    "Cruce Propio (Cargado)":    50.0,
    "Cruce Propio (Vacío)":      30.0,
    # Fuel surcharge al cliente
    "Fuel Surcharge ($/mi)":      0.61,
    # Operador MX
    "CXM Operador MX (Expo)":   963.84,
    "CXM Operador MX (Impo)":   963.84,
    # Tipo de cambio
    "Tipo de Cambio USD/MXP":    18.50,
    # Prestaciones / bonos
    "ISR/IMSS":                  462.66,
    "Bono por milla cargada":      0.01,
    # Costo indirecto (solo %)
    "% Costo Indirecto":           0.42,
}

# ─────────────────────────────────────────────
# CONFIG POR TIPO DE RUTA
# ─────────────────────────────────────────────
def obtener_config_tipo_ruta(tipo_ruta: str) -> dict:
    configs = {
        "NB":    {"parte_usa": True,  "cruce": "opcional", "parte_mx": False},
        "SB":    {"parte_usa": True,  "cruce": "opcional", "parte_mx": False},
        "D2DNB": {"parte_usa": True,  "cruce": True,       "parte_mx": True},
        "D2DSB": {"parte_usa": True,  "cruce": True,       "parte_mx": True},
        "Empty": {"parte_usa": True,  "cruce": False,      "parte_mx": False},
    }
    return configs.get(tipo_ruta, configs["NB"])


def tiene_mx(tipo_ruta: str) -> bool:
    return tipo_ruta in TIPOS_CON_MX


def direccion_label(tipo_ruta: str) -> str:
    if tipo_ruta in TIPOS_SUBIDA:
        return "Subida"
    if tipo_ruta in TIPOS_BAJADA:
        return "Bajada"
    return tipo_ruta


# ─────────────────────────────────────────────
# RUTAS DE ARCHIVOS
# ─────────────────────────────────────────────
def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _datos_generales_path() -> str:
    base = os.path.join(_project_root(), ".data")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "datos_generales_lincoln.csv")


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
                # Garantizar campos nuevos
                for k, v in DEFAULTS.items():
                    if k not in out:
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
# HELPERS DE TEXTO Y CONVERSIÓN
# ─────────────────────────────────────────────
def normalizar(texto: str) -> str:
    if not texto:
        return ""
    texto = str(texto).upper().strip()
    texto = re.sub(r'\s+', ' ', texto)
    texto = re.sub(r'\s*,\s*', ', ', texto)
    return texto


def a_usd(mxp: float, tc: float) -> float:
    return mxp / tc if tc else 0.0


def get_profile_name(user_id: str) -> str:
    if not user_id:
        return ""
    try:
        sb = get_authed_client()
        res = sb.table("profiles").select("full_name").eq("user_id", user_id).single().execute()
        return (res.data or {}).get("full_name") or ""
    except Exception:
        return ""


def generar_id_ruta() -> str:
    sb = get_supabase_client()
    if sb is None:
        return f"LN{int(time.time()) % 1_000_000:06d}"
    try:
        resp = (
            sb.table(TABLE_RUTAS)
            .select("ID_Ruta")
            .order("Fecha", desc=True)
            .limit(100)
            .execute()
        )
        ids = [
            r["ID_Ruta"] for r in (resp.data or [])
            if r.get("ID_Ruta", "").startswith("LN")
        ]
        nums = []
        for i in ids:
            try:
                nums.append(int(i[2:]))
            except Exception:
                pass
        n = max(nums) + 1 if nums else 1
        return f"LN{n:06d}"
    except Exception:
        return f"LN{int(time.time()) % 1_000_000:06d}"


# ─────────────────────────────────────────────
# CÁLCULO CENTRAL
# Reglas Empty:
#   - Solo millas vacías para diesel y pago operador
#   - Sin bono por milla
#   - Sin ISR/IMSS
# ─────────────────────────────────────────────
def calcular_ruta_lincoln(
    tipo_ruta: str,
    millas_usa: float,
    millas_vacias: float,
    ingreso_x_milla_usd: float,
    fuel_surcharge_usd: float,
    ingreso_cruce_usd: float,
    aplica_cruce: bool,
    modo_viaje: str,
    tipo_cruce: str,
    tipo_carga_cruce: str,
    costo_cruce_tercero_usd: float,
    ingreso_flete_mx_mxp: float,
    costo_flete_mx_mxp: float,
    linea_mx: str,
    otros_cargos: dict,
    otros_cargos_pagados: dict,
    valores: dict,
) -> dict:
    """
    Calcula todos los ingresos, costos y utilidades de una ruta Lincoln.

    Empty:  solo diesel (millas_vacias) + pago_operador_vacio — sin bono, sin ISR/IMSS.
    NB/SB/D2D: cálculo completo con bono e ISR/IMSS.
    """
    tc            = safe(valores.get("Tipo de Cambio USD/MXP", 18.50))
    mpg           = safe(valores.get("Truck Performance (mpg)", 7.0))
    diesel_precio = safe(valores.get("Diesel Price ($/gal)", 3.60))
    isr_imss_cfg  = safe(valores.get("ISR/IMSS", 462.66))
    bono_cfg      = safe(valores.get("Bono por milla cargada", 0.01))
    pct_ind       = safe(valores.get("% Costo Indirecto", 0.42))

    es_empty = (tipo_ruta == "Empty")

    # ── Modo de viaje (factor team = 2 operadores) ────────────────────────
    if modo_viaje == "Team":
        cxm_cargado = safe(valores.get("CXM Team USA", 0.30))
        cxm_vacio   = safe(valores.get("CXM Team USA (Empty)", 0.25))
        factor      = 2
    else:
        cxm_cargado = safe(valores.get("CXM Operador USA", 0.48))
        cxm_vacio   = safe(valores.get("CXM Operador USA (Empty)", 0.30))
        factor      = 1

    # ── Ingresos USA ──────────────────────────────────────────────────────
    if es_empty:
        # En Empty no hay flete ni fuel cobrado al cliente
        ingreso_flete_usa = 0.0
        ingreso_fuel_usa  = 0.0
    else:
        ingreso_flete_usa = ingreso_x_milla_usd * millas_usa
        ingreso_fuel_usa  = fuel_surcharge_usd  * millas_usa

    ingreso_total_usa = ingreso_flete_usa + ingreso_fuel_usa

    # ── Otros Cargos ──────────────────────────────────────────────────────
    otros_cargos_ingreso = sum(otros_cargos.values())
    otros_cargos_costo   = sum(
        monto for nombre, monto in otros_cargos.items()
        if otros_cargos_pagados.get(nombre, False) and monto > 0
    )

    # ── Sueldo operador ───────────────────────────────────────────────────
    if es_empty:
        # Solo pago por millas vacías, sin bono
        sueldo_base = millas_vacias * cxm_vacio * factor
        bono_millas = 0.0
    else:
        sueldo_base = (millas_usa * cxm_cargado + millas_vacias * cxm_vacio) * factor
        bono_millas = millas_usa * bono_cfg * factor

    sueldo_usa = sueldo_base + bono_millas

    # ── Diesel ────────────────────────────────────────────────────────────
    if es_empty:
        # Solo millas vacías
        diesel_usa = (millas_vacias / mpg) * diesel_precio if mpg else 0.0
    else:
        diesel_usa = ((millas_usa + millas_vacias) / mpg) * diesel_precio if mpg else 0.0

    # ── ISR / IMSS ────────────────────────────────────────────────────────
    isr_imss = 0.0 if es_empty else isr_imss_cfg

    # ── Cruce ─────────────────────────────────────────────────────────────
    if aplica_cruce and not es_empty:
        if tipo_cruce == "Propio":
            if tipo_carga_cruce == "Cargado":
                costo_cruce = safe(valores.get("Cruce Propio (Cargado)", 50.0))
            else:
                costo_cruce = safe(valores.get("Cruce Propio (Vacío)", 30.0))
        else:
            costo_cruce = costo_cruce_tercero_usd
    else:
        costo_cruce       = 0.0
        ingreso_cruce_usd = 0.0

    # ── Tramo MX ──────────────────────────────────────────────────────────
    ingreso_mx_usd = a_usd(ingreso_flete_mx_mxp, tc)
    costo_mx_usd   = a_usd(costo_flete_mx_mxp, tc)

    # ── Totales ───────────────────────────────────────────────────────────
    ingreso_total = (
        ingreso_total_usa
        + ingreso_cruce_usd
        + ingreso_mx_usd
        + otros_cargos_ingreso
    )

    costo_directo       = sueldo_usa + diesel_usa + costo_cruce + costo_mx_usd + otros_cargos_costo
    costo_directo_total = costo_directo + isr_imss

    utilidad_bruta = ingreso_total - costo_directo_total
    pct_bruta      = (utilidad_bruta / ingreso_total * 100) if ingreso_total > 0 else 0.0

    costos_ind    = ingreso_total * pct_ind
    utilidad_neta = utilidad_bruta - costos_ind
    pct_neta      = (utilidad_neta / ingreso_total * 100) if ingreso_total > 0 else 0.0
    pct_cd        = (costo_directo_total / ingreso_total * 100) if ingreso_total > 0 else 0.0
    pct_ind_real  = (costos_ind / ingreso_total * 100) if ingreso_total > 0 else 0.0

    return {
        # Ingresos
        "ingreso_flete_usa":    ingreso_flete_usa,
        "ingreso_fuel_usa":     ingreso_fuel_usa,
        "ingreso_total_usa":    ingreso_total_usa,
        "ingreso_cruce":        ingreso_cruce_usd,
        "ingreso_mx_usd":       ingreso_mx_usd,
        "otros_cargos_ingreso": otros_cargos_ingreso,
        "ingreso_total":        ingreso_total,
        # Costos
        "sueldo_base":          sueldo_base,
        "bono_millas":          bono_millas,
        "sueldo_usa":           sueldo_usa,
        "diesel_usa":           diesel_usa,
        "costo_cruce":          costo_cruce,
        "costo_mx_usd":         costo_mx_usd,
        "otros_cargos_costo":   otros_cargos_costo,
        "isr_imss":             isr_imss,
        "costo_directo":        costo_directo,
        "costo_directo_total":  costo_directo_total,
        # Utilidades / semáforos
        "utilidad_bruta":       utilidad_bruta,
        "pct_bruta":            pct_bruta,
        "costos_ind":           costos_ind,
        "utilidad_neta":        utilidad_neta,
        "pct_neta":             pct_neta,
        # Porcentajes para semáforos (nombres alineados con components.py)
        "Pct_Costo_Directo":    pct_cd,
        "Pct_Ut_Bruta":         pct_bruta,
        "Pct_Costo_Indirecto":  pct_ind_real,
        "Pct_Ut_Neta":          pct_neta,
        # Parámetros usados (para simulador y PDF)
        "tc":                   tc,
        "mpg":                  mpg,
        "diesel":               diesel_precio,
        "cxm_cargado":          cxm_cargado,
        "cxm_vacio":            cxm_vacio,
        "bono_por_milla":       bono_cfg,
        "pct_ind":              pct_ind,
    }
