from ui.components import section_header, alert, divider
"""
_shared.py – Set Logis
Helpers, defaults y funciones compartidas entre módulos
Modelo de negocio: Pago a owners por milla (cargada/vacía)
"""

import os
import json
from datetime import date, datetime

import numpy as np
import pandas as pd

# ─────────────────────────────────────────────
# TABLAS SUPABASE
# ─────────────────────────────────────────────
TABLE_RUTAS = "Rutas_SetLogis"
TABLE_TRAFICOS = "Traficos_SetLogis"

# ─────────────────────────────────────────────
# DEFAULTS – Parámetros operativos de Set Logis
# ─────────────────────────────────────────────
DEFAULTS = {
    # Pago a owners (USD por milla)
    "PxM Owner Subidas": 1.60,        # Pago por milla cargada (NB/D2DNB)
    "PxM Owner Bajadas": 1.40,        # Pago por milla cargada (SB/D2DSB)
    "PxM Owner Vacio": 0.80,          # Pago por milla vacía
    
    # Tipo de cambio
    "Tipo de Cambio USD/MXP": 18.50,
    
    # Costos indirectos - dos opciones para pruebas
    "CXM Indirecto": 0.10,            # $/milla (sobre total de millas)
    "% Costo Indirecto": 0.15,        # Porcentaje sobre ingreso total
}

# ─────────────────────────────────────────────
# TIPOS DE RUTA Set Logis
# ─────────────────────────────────────────────
TIPOS_RUTA = ["NB", "SB", "D2DNB", "D2DSB", "Empty"]

# Direcciones de viaje
DIRECCIONES = ["Subida", "Bajada"]

# ─────────────────────────────────────────────
# RUTAS DE ARCHIVOS
# ─────────────────────────────────────────────
def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


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
                d = df.set_index("Parametro")["Valor"].to_dict()
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
# CÁLCULO CENTRAL SET LOGIS
# ─────────────────────────────────────────────
def calcular_ruta_setlogis(
    *,
    tipo_ruta: str,
    direccion: str,
    ruta_usa: str,        # Origen → Destino
    cliente: str,
    miles_load: float,     # Millas cargadas (Miles_Load)
    miles_empty: float,    # Millas vacías (Miles_Empty)
    flete_usa: float,      # Flete USA
    fuel: float,           # Fuel surcharge
    cruce: float,          # Cruce
    reembolso_cruce: float,  # Reembolso cruce
    modo_costo_indirecto: str,     # "CXM" o "Porcentaje"
    valores: dict,
) -> dict:
    """
    Calcula ruta Set Logis según estructura de BD existente.
    
    Campos BD:
    - Miles_Load (millas cargadas)
    - Miles_Empty (millas vacías)
    - Ruta_USA (origen → destino)
    - Flete_USA, Fuel, Cruce
    - Sueldo_Owner_Cargado, Sueldo_Owner_Vacio
    """
    
    # Parámetros (usando nombres originales)
    pxm_subidas = safe(valores.get("PxM Owner Subidas", 1.60))  # Tasa_Owner_Cargado para Subida
    pxm_bajadas = safe(valores.get("PxM Owner Bajadas", 1.40))  # Tasa_Owner_Cargado para Bajada
    pxm_vacio = safe(valores.get("PxM Owner Vacio", 0.80))       # Tasa_Owner_Vacio
    cxm_indirecto = safe(valores.get("CXM Indirecto", 0.10))
    pct_indirecto = safe(valores.get("% Costo Indirecto", 0.15))
    tc = safe(valores.get("Tipo de Cambio USD/MXP", 18.50))
    
    # ── INGRESOS ──
    # Flete_Fuel = combinación de Flete_USA + Fuel
    flete_fuel = flete_usa + fuel
    
    # Ingreso_Global = Flete_Fuel + Cruce
    ingreso_global = flete_fuel + cruce
    
    # Empty trips no tienen ingreso
    if tipo_ruta == "Empty":
        ingreso_global = 0.0
        flete_usa = 0.0
        fuel = 0.0
        cruce = 0.0
        flete_fuel = 0.0
        cliente = ""
    
    # ── COSTOS DIRECTOS ──
    # Tasa según dirección (Subida o Bajada)
    if direccion.upper() == "SUBIDA" or tipo_ruta == "Empty":
        tasa_owner_cargado = pxm_subidas
    else:  # BAJADA
        tasa_owner_cargado = pxm_bajadas
    
    # Sueldo_Owner_Cargado = Miles_Load × Tasa_Owner_Cargado
    sueldo_owner_cargado = miles_load * tasa_owner_cargado
    
    # Sueldo_Owner_Vacio = Miles_Empty × Tasa_Owner_Vacio
    sueldo_owner_vacio = miles_empty * pxm_vacio
    
    # Total_Costos_Directos = Sueldo_Owner_Cargado + Sueldo_Owner_Vacio
    total_costos_directos = sueldo_owner_cargado + sueldo_owner_vacio
    
    # ── COSTOS INDIRECTOS ──
    # Empty trips NO tienen costos indirectos
    if tipo_ruta == "Empty":
        costo_indirecto = 0.0
    else:
        if modo_costo_indirecto == "CXM":
            # CXM_Indirecto × (Miles_Load + Miles_Empty)
            millas_totales = miles_load + miles_empty
            costo_indirecto = millas_totales * cxm_indirecto
        else:  # Porcentaje
            costo_indirecto = ingreso_global * pct_indirecto
    
    # ── UTILIDADES ──
    # Ut_Bruta = Ingreso_Global - Total_Costos_Directos
    ut_bruta = ingreso_global - total_costos_directos
    pct_ut_bruta = (ut_bruta / ingreso_global * 100) if ingreso_global > 0 else 0.0
    
    # Utilidad_Neta = Ut_Bruta - Costo_Indirecto
    utilidad_neta = ut_bruta - costo_indirecto
    pct_ut_neta = (utilidad_neta / ingreso_global * 100) if ingreso_global > 0 else 0.0
    
    # Porcentajes
    pct_cd = (total_costos_directos / ingreso_global * 100) if ingreso_global > 0 else 0.0
    pct_ci = (costo_indirecto / ingreso_global * 100) if ingreso_global > 0 else 0.0
    
    return {
        # Ingresos (estructura BD)
        "Flete_USA": flete_usa,
        "Fuel": fuel,
        "Flete_Fuel": flete_fuel,
        "Cruce": cruce,
        "Reembolso_Cruce": reembolso_cruce,
        "Ingreso_Global": ingreso_global,
        
        # Costos directos (estructura BD)
        "Tasa_Owner_Cargado": tasa_owner_cargado,
        "Tasa_Owner_Vacio": pxm_vacio,
        "Sueldo_Owner_Cargado": sueldo_owner_cargado,
        "Sueldo_Owner_Vacio": sueldo_owner_vacio,
        "Total_Costos_Directos": total_costos_directos,
        
        # Costos indirectos (estructura BD)
        "CXM_Indirecto": cxm_indirecto if modo_costo_indirecto == "CXM" else 0.0,
        "Costo_Indirecto": costo_indirecto,
        
        # Utilidades (estructura BD)
        "Ut_Bruta": ut_bruta,
        "Utilidad_Neta": utilidad_neta,
        "Pct_Ut_Bruta": pct_ut_bruta,
        "Pct_Ut_Neta": pct_ut_neta,
        "Pct_CD": pct_cd,
        "Pct_CI": pct_ci,
        
        # Parámetros usados
        "pxm_subidas": pxm_subidas,
        "pxm_bajadas": pxm_bajadas,
        "pxm_vacio": pxm_vacio,
        "tc": tc,
    }
