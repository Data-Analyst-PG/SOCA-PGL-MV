"""
_shared.py – Set Logis Plus
Helpers, defaults y cálculo central.

Fórmula tarifa americana (Desglosada):
  Flete = Miles_Load × CXM_Flete
  Fuel  = Miles_Load × CXM_Fuel      ← ambos sobre Miles Load
  Total = Flete + Fuel
ruta
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
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import streamlit as st

from services.supabase_client import get_supabase_client
from services.auditoria import registrar_accion

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
# UMBRALES SET LOGIS — viajan en el dict de resultado
# Se definen aquí para que sean editables sin tocar components.py
# ─────────────────────────────────────────────
UMBRAL_CD = 85.0   # % máximo de costo directo aceptable
UMBRAL_UB = 15.0   # % mínimo de utilidad bruta aceptable
UMBRAL_CI =  9.0   # % máximo de costo indirecto aceptable
UMBRAL_UN =  6.0   # % mínimo de utilidad neta aceptable


# ─────────────────────────────────────────────
# CONFIG POR TIPO DE RUTA
# Orden visual de secciones en el formulario:
#   NB    → cruce, americana          (cruce primero — igual que Lincoln)
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
    return configs.get(tipo_ruta, {"parte_usa": True, "cruce": "opcional",
                                    "parte_mx": False, "orden": ["americana"]})


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
                return out
        except Exception:
            pass
    return DEFAULTS.copy()


def guardar_datos_generales(valores: dict) -> None:
    path = _datos_generales_path()
    rows = [{"Parametro": k, "Valor": v} for k, v in valores.items()]
    pd.DataFrame(rows).to_csv(path, index=False)


# ─────────────────────────────────────────────
# UTILIDADES GENERALES
# ─────────────────────────────────────────────
def safe(val, default: float = 0.0) -> float:
    try:
        return float(val) if val not in (None, "", "nan") else default
    except Exception:
        return default


def normalizar(texto: str) -> str:
    return str(texto or "").strip().upper()


def a_usd(valor: float, moneda: str, tc: float) -> float:
    """Convierte MXP → USD si moneda es 'MXP'; si ya es USD lo devuelve igual."""
    if moneda == "MXP" and tc > 0:
        return valor / tc
    return valor


def now_iso() -> str:
    """Timestamp ISO UTC — usar en todos los módulos en vez de _now_iso() local."""
    return datetime.now(timezone.utc).isoformat()


def limpiar_fila_json(fila: dict) -> dict:
    """Convierte tipos no serializables (numpy, date, datetime) para Supabase."""
    resultado = {}
    for k, v in fila.items():
        if isinstance(v, (np.integer,)):
            resultado[k] = int(v)
        elif isinstance(v, (np.floating,)):
            resultado[k] = float(v)
        elif isinstance(v, (np.bool_,)):
            resultado[k] = bool(v)
        elif isinstance(v, (date, datetime)):
            resultado[k] = v.isoformat()
        elif isinstance(v, dict):
            resultado[k] = json.dumps(v)
        elif isinstance(v, list):
            resultado[k] = json.dumps(v)
        else:
            resultado[k] = v
    return resultado


# ─────────────────────────────────────────────
# PERFIL DE USUARIO
# ─────────────────────────────────────────────
def get_profile_name(user_id: str) -> str | None:
    sb = get_supabase_client()
    if sb is None or not user_id:
        return None
    try:
        res = sb.table("profiles").select("full_name").eq("id", user_id).maybe_single().execute()
        return (res.data or {}).get("full_name")
    except Exception:
        return None


# ─────────────────────────────────────────────
# GENERADOR DE ID
# ─────────────────────────────────────────────
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
    origen: str,
    destino: str,
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

    # ── COLORES — calculados con umbrales reales de Set Logis ────────────────
    color_dir  = "#059669" if pct_dir  <= UMBRAL_CD else "#DC2626"
    color_ind  = "#059669" if pct_ind_ <= UMBRAL_CI else "#D97706"
    color_ut_n = "#059669" if pct_ut_n >= UMBRAL_UN else "#DC2626"

    return {
        # ── Campos de negocio Set Logis (PascalCase — guardados en Supabase) ──
        "Tipo_Viaje":          tipo_ruta,
        "Modo":                modo,
        "Direccion":           direccion_label(tipo_ruta),
        "Origen":              origen,
        "Destino":             destino,
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

        # ── Alias canónicos (snake_case) — requeridos por components.py ──────
        # mostrar_resultados_ruta(), semaforos_ruta(), banner_tarifa_sugerida()
        # esperan estos nombres exactos — NO renombrar
        "ingreso_total":       ingreso_global,
        "costo_directo":       costo_directo_total,
        "utilidad_bruta":      utilidad_bruta,
        "costos_indirectos":   costo_indirecto,
        "utilidad_neta":       utilidad_neta,
        "moneda_display":      "USD",

        # ── Umbrales Set Logis — viajan con el resultado para semaforos_ruta() ─
        "umbral_cd":           UMBRAL_CD,
        "umbral_ub":           UMBRAL_UB,
        "umbral_ci":           UMBRAL_CI,
        "umbral_un":           UMBRAL_UN,
    }


# ─────────────────────────────────────────────
# MOSTRAR RESULTADOS — centraliza banner + KPIs + desglose
# Todos los módulos llaman esta función en lugar de construir el bloque manualmente
# ─────────────────────────────────────────────
def mostrar_resultados_setlogis(
    r:               dict,
    modalidad:       str   = "Flat",
    miles_load:      float = 0.0,
    cxm_flete:       float = 0.0,
    cxm_fuel:        float = 0.0,
    es_simulacion:   bool  = False,
    mostrar_desglose: bool = True,
) -> None:
    """
    Muestra banner tarifa sugerida + 5 cards KPI + desglose por tramo.
    Centraliza lo que antes se repetía en captura, consulta, gestión y simulador.

    Parámetros:
        r             : dict resultado de calcular_ruta_setlogis()
        modalidad     : "Flat" | "Desglosada" — afecta banner y desglose
        miles_load    : millas de carga para calcular $/mi en banner Desglosada
        cxm_flete     : CXM flete capturado — para desglose ingreso americano
        cxm_fuel      : CXM fuel capturado  — para desglose ingreso americano
        es_simulacion : True → muestra aviso de simulación
    """
    from ui.components import (
        banner_tarifa_sugerida, mostrar_resultados_ruta,
        desglose_ruta, divider, alert,
    )

    if es_simulacion:
        alert("info", "🔧 Estás viendo una simulación con parámetros ajustados.")

    # ── Fuel Owner — aviso visual ─────────────────────────────────────────────
    if r.get("Fuel_Owner"):
        st.info(f"⛽ **Fuel pagado al Owner:** ${r.get('Pago_Fuel_Owner', 0):,.2f} USD — incluido en Costo Directo")

    # ── Banner tarifa sugerida ────────────────────────────────────────────────
    tc_usd      = r.get("TC", safe(DEFAULTS.get("Tipo de Cambio USD/MXP", 18.50)))
    _umbral     = r["umbral_cd"]
    _tarifa_sug = r["costo_directo"] / (_umbral / 100)
    _tarifa_mxp = _tarifa_sug * tc_usd

    divider()
    banner_tarifa_sugerida(
        r["costo_directo"], r["ingreso_total"],
        _umbral, "USD", _tarifa_mxp,
        modalidad=modalidad,
        miles_load=miles_load,
        fuel_capturado=r.get("Fuel", 0.0),
    )

    # ── 5 cards KPI canónicas ─────────────────────────────────────────────────
    mostrar_resultados_ruta(r)

    # ── Desglose por tramo ────────────────────────────────────────────────────
    if mostrar_desglose:
        tipo_ruta   = str(r.get("Tipo_Viaje", "NB"))
        es_empty    = (tipo_ruta == "Empty")
        short_m     = safe(r.get("Short_Miles", 0.0))
        miles_emp   = safe(r.get("Miles_Empty", 0.0))
        pxm_c       = safe(r.get("PxM_Cargado", 0.0))
        pxm_v       = safe(r.get("PxM_Vacio",   0.0))

        if es_empty:
            filas_costo = [
                (f"Owner Vacío ({miles_emp:.0f} mi × ${pxm_v:.4f})", r.get("Pago_Owner_Vacio", 0.0)),
            ]
        else:
            filas_costo = [
                (f"Owner Cargado ({short_m:.0f} Short Mi × ${pxm_c:.4f})", r.get("Pago_Owner_Cargado", 0.0)),
                (f"Owner Vacío ({miles_emp:.0f} Mi Vacías × ${pxm_v:.4f})",  r.get("Pago_Owner_Vacio", 0.0)),
            ]
            if r.get("Fuel_Owner"):
                filas_costo.append(("Fuel pagado al Owner", r.get("Pago_Fuel_Owner", 0.0)))
            if safe(r.get("Extras_Costo_Total", 0)) > 0:
                filas_costo.append(("Extras (Set Logis pagó)", r.get("Extras_Costo_Total", 0.0)))

        desglose_ruta(
            r,
            filas_costo_americana=filas_costo,
            modalidad=modalidad,
            cxm_flete=cxm_flete,
            cxm_fuel=cxm_fuel,
            umbral_cd=_umbral,
        )


# ─────────────────────────────────────────────
# CARGA DE RUTAS — compartida por consulta, gestión y simulador
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=120)
def load_rutas_setlogis(table: str) -> pd.DataFrame:
    """
    Carga todas las rutas ordenadas por Fecha desc.
    Compartida por consulta_ruta, gestion_rutas y simulador.
    Reemplaza los _cargar_rutas() locales de cada módulo.
    """
    sb = get_supabase_client()
    if sb is None:
        return pd.DataFrame()
    try:
        resp = sb.table(table).select("*").order("Fecha", desc=True).execute()
        df = pd.DataFrame(resp.data or [])
        if not df.empty and "Fecha" in df.columns:
            df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d")
        return df
    except Exception:
        return pd.DataFrame()


# ─────────────────────────────────────────────
# POOL DE UBICACIONES — compartido por captura y gestión
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=120)
def cargar_pool_ubicaciones_setlogis() -> list[str]:
    """
    Une y deduplica ubicaciones USA (Origen + Destino) y MX
    (Origen_MX + Destino_MX) de la tabla Rutas_SetLogis.
    Compartida por captura_rutas y gestion_rutas.
    """
    sb = get_supabase_client()
    if sb is None:
        return []
    try:
        resp = sb.table(TABLE_RUTAS).select(
            "Origen, Destino, Origen_MX, Destino_MX"
        ).execute()
        ubicaciones: set[str] = set()
        for row in (resp.data or []):
            for col in ("Origen", "Destino", "Origen_MX", "Destino_MX"):
                v = (row.get(col) or "").strip().upper()
                if v:
                    ubicaciones.add(v)
        return sorted(ubicaciones)
    except Exception:
        return []


def buscar_ubicacion_setlogis(termino: str) -> list[str]:
    """
    Filtra el pool por lo que escribe el usuario.
    Si no hay coincidencias devuelve el término como opción libre
    para permitir ubicaciones nuevas sin que el campo se limpie.
    """
    if not termino or len(termino) < 2:
        return []
    termino_upper = termino.upper()
    pool = cargar_pool_ubicaciones_setlogis()
    coincidencias = [u for u in pool if termino_upper in u]
    if not coincidencias:
        return [termino_upper]
    return coincidencias


# ─────────────────────────────────────────────
# LABEL Y FILTROS — compartidos por consulta, gestión y simulador
# ─────────────────────────────────────────────
def label_ruta_setlogis(row) -> str:
    """Etiqueta de selectbox para una ruta Set Logis."""
    fo  = " ⛽" if row.get("Fuel_Owner") else ""
    pct = safe(row.get("Pct_Ut_Bruta", 0))
    return (
        f"{row.get('ID_Ruta', '')} | {row.get('Fecha', '')} | "
        f"{row.get('Tipo_Viaje', '')} | {row.get('Cliente', '—')} | "
        f"{row.get('Origen', '')} → {row.get('Destino', '')}{fo} | "
        f"{pct:.1f}% Ut.B"
    )


def filtrar_rutas_setlogis(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """
    Filtros de búsqueda reutilizables para consulta, gestión y simulador.
    Compartida por los 3 módulos — usa prefix para evitar DuplicateElementKey.
    """
    if df.empty:
        return df

    f1, f2, f3, f4 = st.columns(4)

    tipos_disp = ["Todos"] + sorted(df["Tipo_Viaje"].dropna().unique().tolist())
    tipo_fil = f1.selectbox("Tipo Viaje", tipos_disp, key=f"{prefix}_fil_tipo")

    modos_disp = ["Todos"] + sorted(df["Modo"].dropna().unique().tolist()) if "Modo" in df.columns else ["Todos"]
    modo_fil = f2.selectbox("Modo", modos_disp, key=f"{prefix}_fil_modo")

    clientes_disp = ["Todos"] + sorted(df["Cliente"].dropna().unique().tolist()) if "Cliente" in df.columns else ["Todos"]
    cliente_fil = f3.selectbox("Cliente", clientes_disp, key=f"{prefix}_fil_cliente")

    texto_fil = f4.text_input("Buscar ruta / ID", key=f"{prefix}_fil_texto").strip().upper()

    resultado = df.copy()
    if tipo_fil    != "Todos":
        resultado = resultado[resultado["Tipo_Viaje"] == tipo_fil]
    if modo_fil    != "Todos" and "Modo" in resultado.columns:
        resultado = resultado[resultado["Modo"] == modo_fil]
    if cliente_fil != "Todos" and "Cliente" in resultado.columns:
        resultado = resultado[resultado["Cliente"] == cliente_fil]
    if texto_fil:
        mask = (
            resultado.get("ID_Ruta",  pd.Series(dtype=str)).astype(str).str.upper().str.contains(texto_fil, na=False)
            | resultado.get("Origen",  pd.Series(dtype=str)).astype(str).str.upper().str.contains(texto_fil, na=False)
            | resultado.get("Destino", pd.Series(dtype=str)).astype(str).str.upper().str.contains(texto_fil, na=False)
        )
        resultado = resultado[mask]

    return resultado


# ─────────────────────────────────────────────
# AUDITORÍA
# ─────────────────────────────────────────────
def log_accion(accion: str, detalle: dict | None = None) -> None:
    """Wrapper de auditoría — centraliza el nombre del módulo 'cot-set-logis'."""
    registrar_accion("cot-set-logis", accion, detalle)
