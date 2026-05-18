from ui.components import section_header, alert, divider
"""
_shared.py  –  Lincoln Freight (USA/MX)
Helpers, defaults y rutas a archivos compartidos entre módulos.
Versión actualizada con ISR/IMSS y Bono por milla
"""

import os
import json
from datetime import date, datetime

import numpy as np
import pandas as pd

# ─────────────────────────────────────────────
# TABLAS SUPABASE
# ─────────────────────────────────────────────
TABLE_RUTAS     = "Rutas_Lincoln"
TABLE_TRAFICOS  = "Traficos_Lincoln"

# ─────────────────────────────────────────────
# DEFAULTS – parámetros operativos de Lincoln
# Todos en USD porque Lincoln opera en sistema americano
# ─────────────────────────────────────────────
DEFAULTS = {
    # Operador USA (por milla)
    "CXM Operador USA":           0.48,   # $/milla operador solo
    "CXM Operador USA (Empty)":   0.30,   # $/milla vacío
    "CXM Team USA":               0.30,   # $/milla team (x operador)
    "CXM Team USA (Empty)":       0.25,   # $/milla vacío team
    # Rendimiento / diesel USA
    "Truck Performance (mpg)":    7.0,    # millas por galón
    "Diesel Price ($/gal)":       3.60,   # precio diesel USA galones
    # Cruce fronterizo
    "Cruce Propio (Cargado)":   50.0,   # USD
    "Cruce Propio (Vacío)":      30.0,   # USD
    # Tramo México (línea propia)
    "Fuel Surcharge ($/mi)":      0.61,   # CXM Fuel USA
    # Operador MX – pago fijo por viaje
    "CXM Operador MX (Expo)":   963.84,  # MXP por viaje exportación
    "CXM Operador MX (Impo)":   963.84,  # MXP por viaje importación
    # Tipo de cambio
    "Tipo de Cambio USD/MXP":    18.50,
    # ✨ NUEVOS CAMPOS
    "ISR/IMSS":                  462.66,  # Prestaciones de ley USD
    "Bono por milla cargada":      0.01,  # Bono adicional $/milla
}

# ─────────────────────────────────────────────
# TIPOS DE RUTA Lincoln
# ─────────────────────────────────────────────
TIPOS_RUTA = ["NB", "SB", "D2DNB", "D2DSB", "DOM USA", "DOM MEX"]

# Extras aplicables en USA
EXTRAS_USA = [
    "Stop Off", "Detention", "Lumper Fees", "Layover",
    "Fianzas", "Additional Insurance", "Loadlocks",
    "Accessories", "Guias", "Maniobras", "Mov Extraordinario",
]

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
                d = df.set_index("Parametro")["Valor"].to_dict()
                out = DEFAULTS.copy()
                for k, v in d.items():
                    try:
                        out[k] = float(v)
                    except Exception:
                        out[k] = v
                # Asegurar que los nuevos campos existan
                if "ISR/IMSS" not in out:
                    out["ISR/IMSS"] = 462.66
                if "Bono por milla cargada" not in out:
                    out["Bono por milla cargada"] = 0.01
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
def safe(x, default=0.0):
    """Devuelve float seguro; None/NaN → default."""
    try:
        if x is None:
            return default
        f = float(x)
        return default if np.isnan(f) else f
    except Exception:
        return default


def limpiar_fila_json(fila: dict) -> dict:
    """Convierte tipos numpy/pandas a tipos serializables para Supabase."""
    limpio = {}
    for k, v in fila.items():
        if v is None or (isinstance(v, float) and np.isnan(v)):
            limpio[k] = None
        elif isinstance(v, (pd.Timestamp, datetime, date, np.datetime64)):
            limpio[k] = str(v)[:10]
        elif isinstance(v, (np.integer,)):
            limpio[k] = int(v)
        elif isinstance(v, (np.floating,)):
            limpio[k] = float(v)
        else:
            try:
                json.dumps(v)
                limpio[k] = v
            except TypeError:
                limpio[k] = str(v)
    return limpio


# ─────────────────────────────────────────────
# CÁLCULO CENTRAL ACTUALIZADO
# ✨ Con Bono por milla e ISR/IMSS
# ✨ Costos indirectos al 42%
# ─────────────────────────────────────────────
def calcular_ruta(
    *,
    millas_usa: float,
    millas_vacias: float,
    ingreso_x_milla: float,          # CXM Flete (tarifa al cliente)
    fuel_surcharge: float,            # CXM Fuel
    cruce_ingreso: float,             # lo que cobra Lincoln por el cruce
    otros: float,                     # cargos extra en tarifa
    modo_viaje: str,                  # "Operador" | "Team"
    tipo_cruce: str,                  # "Propio" | "Tercero"
    tipo_carga_cruce: str,            # "Cargado" | "Vacío"
    costo_cruce_tercero: float,       # si cruce=Tercero, cuánto le cobran
    linea_mx: str,                    # "Propia" | "Tercero"
    ingreso_flete_mx: float,          # MXP
    costo_flete_mx: float,            # MXP
    extras: dict,                     # {nombre: valor USD}
    valores: dict,                    # datos generales
) -> dict:
    """
    Calcula todos los ingresos, costos y utilidades de una ruta Lincoln.
    Versión actualizada con bono por milla e ISR/IMSS.
    Retorna dict con resultados desagregados.
    """
    tc      = safe(valores.get("Tipo de Cambio USD/MXP", 18.0))
    mpg     = safe(valores.get("Truck Performance (mpg)", 7.0))
    diesel  = safe(valores.get("Diesel Price ($/gal)", 3.60))
    fs_rate = safe(valores.get("Fuel Surcharge ($/mi)", fuel_surcharge))
    isr_imss = safe(valores.get("ISR/IMSS", 462.66))
    bono_por_milla = safe(valores.get("Bono por milla cargada", 0.01))

    # ── INGRESOS USA ──
    ingreso_flete_usa  = ingreso_x_milla * millas_usa      # $ Flete US
    ingreso_fuel_usa   = fs_rate * millas_usa               # $ Fuel
    ingreso_cruce_usa  = cruce_ingreso
    ingreso_otros      = otros
    ingreso_total_usa  = ingreso_flete_usa + ingreso_fuel_usa + ingreso_cruce_usa + ingreso_otros

    # ── EXTRAS ──
    extras_total = sum(safe(v) for v in extras.values())

    # ── COSTO OPERADOR USA CON BONO ✨ ──
    if modo_viaje == "Team":
        cxm_cargado = safe(valores.get("CXM Team USA", 0.30))
        cxm_vacio   = safe(valores.get("CXM Team USA (Empty)", 0.25))
        factor_team = 2
    else:
        cxm_cargado = safe(valores.get("CXM Operador USA", 0.48))
        cxm_vacio   = safe(valores.get("CXM Operador USA (Empty)", 0.30))
        factor_team = 1

    # Sueldo base
    sueldo_base = (millas_usa * cxm_cargado + millas_vacias * cxm_vacio) * factor_team
    
    # Bono por millas cargadas ✨
    bono_millas = (millas_usa * bono_por_milla) * factor_team
    
    # Sueldo total
    sueldo_usa = sueldo_base + bono_millas
    
    diesel_usa = ((millas_usa + millas_vacias) / mpg) * diesel if mpg else 0.0

    # ── COSTO CRUCE ──
    if tipo_cruce == "Propio":
        if tipo_carga_cruce == "Cargado":
            costo_cruce = safe(valores.get("Cruce Propio (Cargado)", 150.0))
        else:
            costo_cruce = safe(valores.get("Cruce Propio (Vacío)", 30.0))
    else:
        costo_cruce = safe(costo_cruce_tercero)

    # ── COSTO TRAMO MX ──
    if linea_mx == "Propia":
        costo_mx_usd = safe(costo_flete_mx) / tc if tc else 0.0
    else:
        costo_mx_usd = safe(costo_flete_mx) / tc if tc else 0.0  # tercero, igual lo paga

    ingreso_mx_usd = safe(ingreso_flete_mx) / tc if tc else 0.0

    # ── TOTALES ──
    ingreso_total = ingreso_total_usa + ingreso_mx_usd
    
    # Costo directo sin ISR/IMSS
    costo_directo = sueldo_usa + diesel_usa + costo_cruce + costo_mx_usd + extras_total
    
    # Agregar ISR/IMSS ✨
    costo_directo_total = costo_directo + isr_imss
    
    # Utilidad bruta (sobre costo directo total que incluye ISR/IMSS)
    utilidad_bruta = ingreso_total - costo_directo_total
    pct_bruta = utilidad_bruta / ingreso_total * 100 if ingreso_total else 0.0
    
    # Costos indirectos al 42% ✨ (antes era 35%)
    costos_ind = ingreso_total * 0.42
    
    # Utilidad neta
    utilidad_neta = utilidad_bruta - costos_ind
    pct_neta = utilidad_neta / ingreso_total * 100 if ingreso_total else 0.0
    pct_cd = costo_directo_total / ingreso_total * 100 if ingreso_total else 0.0

    return {
        # ingresos
        "ingreso_flete_usa":  ingreso_flete_usa,
        "ingreso_fuel_usa":   ingreso_fuel_usa,
        "ingreso_cruce":      ingreso_cruce_usa,
        "ingreso_otros":      ingreso_otros,
        "ingreso_total_usa":  ingreso_total_usa,
        "ingreso_mx_usd":     ingreso_mx_usd,
        "ingreso_total":      ingreso_total,
        # costos
        "sueldo_base":        sueldo_base,         # ✨ NUEVO
        "bono_millas":        bono_millas,         # ✨ NUEVO
        "sueldo_usa":         sueldo_usa,          # Total (base + bono)
        "diesel_usa":         diesel_usa,
        "costo_cruce":        costo_cruce,
        "costo_mx_usd":       costo_mx_usd,
        "extras_total":       extras_total,
        "isr_imss":           isr_imss,            # ✨ NUEVO
        "costo_directo":      costo_directo,       # Sin ISR/IMSS
        "costo_directo_total": costo_directo_total, # ✨ Con ISR/IMSS
        # utilidades
        "utilidad_bruta":     utilidad_bruta,
        "pct_bruta":          pct_bruta,
        "costos_ind":         costos_ind,          # ✨ Ahora al 42%
        "utilidad_neta":      utilidad_neta,
        "pct_neta":           pct_neta,
        "pct_cd":             pct_cd,
        # parámetros usados
        "tc":                 tc,
        "mpg":                mpg,
        "diesel":             diesel,
        "cxm_cargado":        cxm_cargado,
        "cxm_vacio":          cxm_vacio,
        "bono_por_milla":     bono_por_milla,     # ✨ NUEVO
    }
