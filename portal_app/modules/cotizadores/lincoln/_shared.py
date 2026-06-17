"""
_shared.py – Lincoln Freight (USA/MX)
Helpers, defaults y lógica de cálculo central.
Tipos de ruta: NB, SB, D2DNB, D2DSB, Empty

Millas:
  Miles Load  → ingreso al cliente (CXM Flete × Miles Load + Fuel × Miles Load)
  Short Miles → pago operador cargado + bono
  Miles Empty → pago operador vacío
  Diesel      → (Short Miles + Miles Empty) / MPG × precio_galón

Cruce Team: costo no se duplica (solo paga 1 operador al cruzar)
Empty: sin bono, sin ISR/IMSS, sin ingreso cliente
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
    "CXM Operador USA":           0.48,   # $/short mile cargado sencillo
    "CXM Operador USA (Empty)":   0.30,   # $/mile vacío sencillo
    "CXM Team USA":               0.30,   # $/short mile cargado team (× operador)
    "CXM Team USA (Empty)":       0.25,   # $/mile vacío team
    # Rendimiento / diesel USA
    "Truck Performance (mpg)":    7.0,
    "Diesel Price ($/gal)":       3.60,
    # Fuel surcharge al cliente
    "Fuel Surcharge ($/mi)":      0.61,
    # Cruce fronterizo
    "Cruce Propio (Cargado)":    50.0,
    "Cruce Propio (Vacío)":      30.0,
    # Operador MX
    "CXM Operador MX (Expo)":   963.84,
    "CXM Operador MX (Impo)":   963.84,
    # Tipo de cambio
    "Tipo de Cambio USD/MXP":    18.50,
    # Prestaciones / bonos
    "ISR/IMSS":                  462.66,
    "Bono por milla cargada":      0.01,   # sobre Short Miles
    # Costo indirecto (solo %)
    "% Costo Indirecto":           0.42,
}

# ─────────────────────────────────────────────
# CONFIG POR TIPO DE RUTA
# Orden visual de secciones en el formulario:
#   NB    → cruce, americana
#   SB    → americana, cruce
#   D2DNB → mx, cruce, americana
#   D2DSB → americana, cruce, mx
#   Empty → americana (sin cruce ni mx)
# ─────────────────────────────────────────────
def obtener_config_tipo_ruta(tipo_ruta: str) -> dict:
    configs = {
        "NB":    {"parte_usa": True,  "cruce": "opcional", "parte_mx": False,
                  "orden": ["cruce", "americana"]},
        "SB":    {"parte_usa": True,  "cruce": "opcional", "parte_mx": False,
                  "orden": ["americana", "cruce"]},
        "D2DNB": {"parte_usa": True,  "cruce": True,       "parte_mx": True,
                  "orden": ["mx", "cruce", "americana"]},
        "D2DSB": {"parte_usa": True,  "cruce": True,       "parte_mx": True,
                  "orden": ["americana", "cruce", "mx"]},
        "Empty": {"parte_usa": True,  "cruce": False,      "parte_mx": False,
                  "orden": ["americana"]},
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
#
# Millas:
#   miles_load  → ingreso cliente (flete + fuel)
#   short_miles → pago operador cargado + bono
#   miles_empty → pago operador vacío
#   Diesel      → (short_miles + miles_empty) / mpg × diesel_precio
#
# Empty:  solo diesel(short+empty) + pago vacío — sin bono, sin ISR/IMSS
# Team:   cruce no se duplica (1 operador cruza)
# ─────────────────────────────────────────────
def calcular_ruta_lincoln(
    tipo_ruta: str,
    miles_load: float,
    short_miles: float,
    miles_empty: float,
    ingreso_x_milla_usd: float,    # CXM flete × miles_load  (o 0 si Flat)
    tarifa_flat_usd: float,        # monto fijo (solo Flat, 0 si Desglosada)
    fuel_surcharge_usd: float,     # fuel surcharge × miles_load
    ingreso_cruce_usd: float,
    aplica_cruce: bool,
    modo_viaje: str,               # "Sencillo" | "Team"
    tipo_cruce: str,               # "Propio" | "Tercero"
    tipo_carga_cruce: str,         # "Cargado" | "Vacío"
    costo_cruce_tercero_usd: float,
    ingreso_flete_mx_mxp: float,
    costo_flete_mx_mxp: float,
    linea_mx: str,
    otros_cargos: dict,            # {nombre: monto_usd}
    otros_cargos_cobrados: dict,   # {nombre: bool} → True = se cobró al cliente
    valores: dict,
) -> dict:
    tc            = safe(valores.get("Tipo de Cambio USD/MXP", 18.50))
    mpg           = safe(valores.get("Truck Performance (mpg)", 7.0))
    diesel_precio = safe(valores.get("Diesel Price ($/gal)", 3.60))
    isr_imss_cfg  = safe(valores.get("ISR/IMSS", 462.66))
    bono_cfg      = safe(valores.get("Bono por milla cargada", 0.01))
    pct_ind       = safe(valores.get("% Costo Indirecto", 0.42))

    es_empty = (tipo_ruta == "Empty")
    es_team  = (modo_viaje == "Team")

    # ── CXM por modo ─────────────────────────────────────────────
    if es_team:
        cxm_cargado = safe(valores.get("CXM Team USA", 0.30))
        cxm_vacio   = safe(valores.get("CXM Team USA (Empty)", 0.25))
    else:
        cxm_cargado = safe(valores.get("CXM Operador USA", 0.48))
        cxm_vacio   = safe(valores.get("CXM Operador USA (Empty)", 0.30))

    # ── Ingreso USA ───────────────────────────────────────────────
    if es_empty:
        ingreso_flete_usa = 0.0
        ingreso_fuel_usa  = 0.0
    else:
        if tarifa_flat_usd > 0:
            ingreso_flete_usa = tarifa_flat_usd
            ingreso_fuel_usa  = 0.0
        else:
            ingreso_flete_usa = ingreso_x_milla_usd * miles_load
            ingreso_fuel_usa  = fuel_surcharge_usd  * miles_load

    ingreso_total_usa = ingreso_flete_usa + ingreso_fuel_usa

    # ── Otros cargos ─────────────────────────────────────────────
    # Todo monto capturado = Lincoln lo pagó (costo)
    # Si se marcó "cobrado al cliente" = suma también al ingreso
    otros_cargos_costo    = sum(safe(v) for v in otros_cargos.values())
    otros_cargos_ingreso  = sum(
        safe(monto) for nombre, monto in otros_cargos.items()
        if otros_cargos_cobrados.get(nombre, False)
    )

    # ── Factor operadores ─────────────────────────────────────────
    # Team = 2 operadores: sueldo, bono e ISR/IMSS se pagan × 2
    factor = 2 if es_team else 1

    # ── Sueldo operador ───────────────────────────────────────────
    if es_empty:
        sueldo_base = miles_empty * cxm_vacio * factor
        bono_millas = 0.0
    else:
        sueldo_base = (short_miles * cxm_cargado + miles_empty * cxm_vacio) * factor
        bono_millas = short_miles * bono_cfg * factor

    sueldo_usa = sueldo_base + bono_millas

    # ── Diesel ────────────────────────────────────────────────────
    # (Short Miles + Miles Empty) / MPG × precio_galón (no se duplica)
    diesel_usa = ((short_miles + miles_empty) / mpg) * diesel_precio if mpg else 0.0

    # ── ISR / IMSS ────────────────────────────────────────────────
    # Team = 2 operadores → ISR/IMSS × 2; Empty = 0
    isr_imss = 0.0 if es_empty else isr_imss_cfg * factor

    # ── Cruce ─────────────────────────────────────────────────────
    if aplica_cruce and not es_empty:
        if tipo_cruce == "Propio":
            clave = "Cruce Propio (Cargado)" if tipo_carga_cruce == "Cargado" else "Cruce Propio (Vacío)"
            costo_cruce = safe(valores.get(clave, 50.0))
        else:
            costo_cruce = costo_cruce_tercero_usd
        # Team: costo de cruce NO se duplica (solo cruza 1 operador)
    else:
        costo_cruce       = 0.0
        ingreso_cruce_usd = 0.0

    # ── Tramo MX ──────────────────────────────────────────────────
    ingreso_mx_usd = a_usd(ingreso_flete_mx_mxp, tc)
    costo_mx_usd   = a_usd(costo_flete_mx_mxp,   tc)

    # ── Totales ───────────────────────────────────────────────────
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
        # Utilidades
        "utilidad_bruta":       utilidad_bruta,
        "pct_bruta":            pct_bruta,
        "costos_ind":           costos_ind,
        "utilidad_neta":        utilidad_neta,
        "pct_neta":             pct_neta,
        # Para semaforos_ruta() en components.py
        "Pct_Costo_Directo":    pct_cd,
        "Pct_Ut_Bruta":         pct_bruta,
        "Pct_Costo_Indirecto":  pct_ind_real,
        "Pct_Ut_Neta":          pct_neta,
        # Parámetros usados (para simulador, PDF y desglose)
        "tc":               tc,
        "mpg":              mpg,
        "diesel":           diesel_precio,
        "cxm_cargado":      cxm_cargado,
        "cxm_vacio":        cxm_vacio,
        "bono_por_milla":   bono_cfg,
        "pct_ind":          pct_ind,
        # Millas (para desglose visual)
        "miles_load":       miles_load,
        "short_miles":      short_miles,
        "miles_empty":      miles_empty,
        # ── Alias para desglose_ruta en components.py (espera claves Set Logis) ──
        # Ingresos americanos
        "Flete_USA":        ingreso_flete_usa,
        "Fuel":             ingreso_fuel_usa,
        "Extras_Ingreso":   otros_cargos_ingreso,
        # Cruce
        "Ingreso_Cruce":    ingreso_cruce_usd,
        "Costo_Cruce":      costo_cruce,
        "Tipo_Cruce":       tipo_cruce,
        # MX
        "Ingreso_MX":       ingreso_mx_usd,
        "Costo_MX":         costo_mx_usd,
        # Millas (nombres Set Logis para que el componente calcule preview)
        "Miles_Load":       miles_load,
        "Short_Miles":      short_miles,
        "Miles_Empty":      miles_empty,
    }
