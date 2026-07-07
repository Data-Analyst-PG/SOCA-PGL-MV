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
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import streamlit as st

from services.supabase_client import get_supabase_client, get_authed_client

# ─────────────────────────────────────────────
# TABLAS SUPABASE
# ─────────────────────────────────────────────
TABLE_RUTAS    = "Rutas_Lincoln"
TABLE_TRAFICOS = "Traficos_Lincoln"

# ─────────────────────────────────────────────
# UMBRALES SEMÁFORO
# ─────────────────────────────────────────────
UMBRAL_CD = 50.0   # % máximo de costo directo aceptable
UMBRAL_UB = 50.0   # % mínimo de utilidad bruta aceptable
UMBRAL_CI = 35.0   # % máximo de costo indirecto aceptable
UMBRAL_UN = 15.0   # % mínimo de utilidad neta aceptable

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
    "% Costo Indirecto":           0.35,
    # Umbrales semáforo Lincoln
    # Umbrales semáforo Lincoln — usan las constantes para consistencia
    "umbral_cd": UMBRAL_CD,
    "umbral_ub": UMBRAL_UB,
    "umbral_ci": UMBRAL_CI,
    "umbral_un": UMBRAL_UN,
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
        token = st.secrets.get("TOKEN_BMX", "")
        tc = get_tipo_cambio_fix(token) if token else None
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
def a_usd(mxp: float, tc: float) -> float:
    """Convierte MXP a USD. Si tc es 0 devuelve 0."""
    return mxp / tc if tc else 0.0


def normalizar(texto: str) -> str:
    if not texto:
        return ""
    texto = str(texto).upper().strip()
    texto = re.sub(r'\s+', ' ', texto)
    texto = re.sub(r'\s*,\s*', ', ', texto)
    return texto


def now_iso() -> str:
    """Timestamp UTC en ISO 8601 — compartido por captura y gestión."""
    return datetime.now(timezone.utc).isoformat()


def mostrar_resultados_lincoln(
    r:          dict,
    modalidad:  str   = "Flat",
    miles_load: float = 0.0,
    cxm_flete:  float = 0.0,
    cxm_fuel:   float = 0.0,
    modo_viaje: str   = "Sencillo",
    es_simulacion: bool = False,
) -> None:
    """
    Muestra banner + KPIs + desglose por tramo para Lincoln.
    Centraliza lo que antes se repetía en captura, consulta, gestión y simulador.

    Parámetros:
        r            : dict resultado de calcular_ruta_lincoln()
        modalidad    : "Flat" | "Desglosada" — afecta banner y desglose
        miles_load   : millas de carga para calcular $/mi en banner Desglosada
        cxm_flete    : CXM flete capturado — para desglose ingreso americano
        cxm_fuel     : CXM fuel capturado  — para desglose ingreso americano
        modo_viaje   : "Sencillo" | "Team" — para filas de costo
        es_simulacion: True → muestra aviso de simulación
    """
    from ui.components import (
        banner_tarifa_sugerida, mostrar_resultados_ruta,
        desglose_ruta, divider, alert,
    )

    if es_simulacion:
        alert("info", "🔧 Estás viendo una simulación con parámetros ajustados.")

    # ── Banner + KPIs ─────────────────────────────────────────────
    tc_usd      = r.get("tc", 18.50)
    _umbral     = r["umbral_cd"]
    _tarifa_sug = r["costo_directo"] / (_umbral / 100)
    _tarifa_mxp = _tarifa_sug * tc_usd
    divider()
    banner_tarifa_sugerida(
        r["costo_directo"], r["ingreso_total"],
        _umbral, "USD", _tarifa_mxp,
        modalidad=modalidad,
        miles_load=miles_load,
        fuel_capturado=r.get("ingreso_fuel_usa", 0.0),
    )
    mostrar_resultados_ruta(r)

    # ── Desglose por tramo ────────────────────────────────────────
    tipo_ruta   = str(r.get("tipo_ruta_key", "NB"))   # llave interna del dict
    es_empty    = (tipo_ruta == "Empty")
    short_miles = safe(r.get("short_miles", 0.0))
    miles_empty = safe(r.get("miles_empty", 0.0))
    factor      = 2 if modo_viaje == "Team" else 1

    if es_empty:
        filas = [
            (f"Operador Vacío ({miles_empty:.0f} mi × ${r['cxm_vacio']:.4f})",
             r["sueldo_base"]),
            (f"Diesel ({miles_empty:.0f} mi vacías)", r["diesel_usa"]),
        ]
    else:
        filas = [
            (f"Sueldo Cargado ({short_miles:.0f} Short Mi × ${r['cxm_cargado']:.4f})",
             short_miles * r["cxm_cargado"] * factor),
            (f"Sueldo Vacío ({miles_empty:.0f} Mi Vacías × ${r['cxm_vacio']:.4f})",
             miles_empty * r["cxm_vacio"] * factor),
            (f"Bono ({short_miles:.0f} Short Mi × ${r['bono_por_milla']:.3f})",
             r["bono_millas"]),
            (f"Diesel ({short_miles:.0f} SM + {miles_empty:.0f} ME)", r["diesel_usa"]),
            ("ISR/IMSS", r["isr_imss"]),
        ]
        if safe(r.get("otros_cargos_costo", 0)) > 0:
            filas.append(("Otros Conceptos (Lincoln pagó)", r["otros_cargos_costo"]))

    desglose_ruta(
        r,
        filas_costo_americana=filas,
        modalidad=modalidad,
        cxm_flete=cxm_flete,
        cxm_fuel=cxm_fuel,
        umbral_cd=_umbral,
        fuel_capturado=r.get("ingreso_fuel_usa", 0.0),
        miles_load_banner=miles_load,
    )


# ─────────────────────────────────────────────
# CARGA DE RUTAS — compartida por consulta, gestión y simulador
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=120)
def load_rutas_lincoln(table: str) -> pd.DataFrame:
    """
    Carga todas las rutas ordenadas por Fecha desc.
    Compartida por consulta_ruta, gestion_rutas y simulador.
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
def cargar_pool_ubicaciones_lincoln() -> list[str]:
    """
    Une y deduplica ubicaciones USA (Origen + Destino) y MX
    (Origen_MX + Destino_MX) de la tabla Rutas_Lincoln.
    Compartido por captura_rutas y gestion_rutas.
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


def buscar_ubicacion_lincoln(termino: str) -> list[str]:
    """
    Filtra el pool por lo que escribe el usuario.
    Si no hay coincidencias, devuelve el término como opción
    para permitir ubicaciones nuevas sin que el campo se limpie.
    """
    if not termino or len(termino) < 2:
        return []
    termino_upper = termino.upper()
    pool = cargar_pool_ubicaciones_lincoln()
    coincidencias = [u for u in pool if termino_upper in u]
    if not coincidencias:
        return [termino_upper]
    return coincidencias


# ─────────────────────────────────────────────
# LABEL Y FILTROS — compartidos por consulta, gestión y simulador
# ─────────────────────────────────────────────
def label_ruta_lincoln(row) -> str:
    """Etiqueta de selectbox para una ruta Lincoln."""
    pct = safe(row.get("Pct_Utilidad_Bruta", 0))
    return (
        f"{row.get('ID_Ruta', '')} | {row.get('Fecha', '')} | "
        f"{row.get('Tipo', '')} | {row.get('Cliente', '—')} | "
        f"{row.get('Origen', '')} → {row.get('Destino', '')} | "
        f"{pct:.1f}% Ut.B"
    )


def filtrar_rutas_lincoln(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """
    Filtros de búsqueda reutilizables para consulta, gestión y simulador.
    Compartida por los 3 módulos — usa prefix para evitar DuplicateElementKey.
    """
    with st.expander("🔎 Filtros de búsqueda (opcional)", expanded=False):
        fc1, fc2, fc3, fc4, fc5 = st.columns(5)
        tipos    = ["Todos"] + sorted(df["Tipo"].dropna().unique().tolist()) if "Tipo" in df.columns else ["Todos"]
        clientes = ["Todos"] + sorted(df["Cliente"].dropna().astype(str).unique().tolist()) if "Cliente" in df.columns else ["Todos"]
        f_tipo = fc1.selectbox("Tipo",            tipos,    key=f"{prefix}_ftipo")
        f_cli  = fc2.selectbox("Cliente",          clientes, key=f"{prefix}_fcli")
        f_id   = fc3.text_input("ID Ruta",         key=f"{prefix}_fid",  placeholder="LN000001").strip().upper()
        f_orig = fc4.text_input("Origen contiene",  key=f"{prefix}_forig").strip().upper()
        f_dest = fc5.text_input("Destino contiene", key=f"{prefix}_fdest").strip().upper()

    out = df.copy()
    if f_tipo != "Todos":
        out = out[out["Tipo"] == f_tipo]
    if f_cli != "Todos":
        out = out[out["Cliente"].astype(str) == f_cli]
    if f_id:
        out = out[out["ID_Ruta"].astype(str).str.upper().str.contains(f_id, na=False)]
    if f_orig:
        out = out[out["Origen"].astype(str).str.upper().str.contains(f_orig, na=False)]
    if f_dest:
        out = out[out["Destino"].astype(str).str.upper().str.contains(f_dest, na=False)]
    return out

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
    # isr_imss_cfg está en MXP — se convierte a USD con el TC
    # Team = 2 operadores → ISR/IMSS × 2; Empty = 0
    isr_imss = 0.0 if es_empty else a_usd(isr_imss_cfg, tc) * factor

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

    costo_directo        = sueldo_usa + diesel_usa + costo_cruce + costo_mx_usd + otros_cargos_costo + isr_imss
    costo_directo_total  = costo_directo  # alias — se mantiene por compatibilidad con filas guardadas

    # Costo directo SOLO de la parte americana — para el banner de tarifa sugerida
    # en rutas D2D (no debe incluir cruce ni tramo MX, que ya tienen su propio
    # ingreso/costo fijo y no necesitan sugerencia de tarifa)
    costo_directo_americana = sueldo_usa + diesel_usa + isr_imss + otros_cargos_costo

    utilidad_bruta = ingreso_total - costo_directo
    pct_bruta      = (utilidad_bruta / ingreso_total * 100) if ingreso_total > 0 else 0.0

    costos_ind    = ingreso_total * pct_ind
    utilidad_neta = utilidad_bruta - costos_ind
    pct_neta      = (utilidad_neta / ingreso_total * 100) if ingreso_total > 0 else 0.0
    pct_cd        = (costo_directo / ingreso_total * 100) if ingreso_total > 0 else 0.0
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
        "costo_directo_americana": costo_directo_americana,
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
        # Viaje
        "tipo_ruta_key":    tipo_ruta,
        "modo_viaje_key":   modo_viaje,
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
        # ── Alias canónico (mostrar_resultados_ruta lo espera) ──────────────
        "costos_indirectos":   costos_ind,
        "moneda_display":      "USD",
        # ── Colores para kpi_row() — umbrales Lincoln ───────────────────────
        "Color_Directo":   "#DC2626" if pct_cd       > safe(valores.get("umbral_cd", UMBRAL_CD)) else "#059669",
        "Color_Indirecto": "#D97706" if pct_ind_real > safe(valores.get("umbral_ci", UMBRAL_CI)) else "#059669",
        "Color_Ut_Neta":   "#DC2626" if pct_neta     < safe(valores.get("umbral_un", UMBRAL_UN)) else "#059669",
        # ── Umbrales Lincoln — viajan con el resultado ───────────────────────
        "umbral_cd": safe(valores.get("umbral_cd", UMBRAL_CD)),
        "umbral_ub": safe(valores.get("umbral_ub", UMBRAL_UB)),
        "umbral_ci": safe(valores.get("umbral_ci", UMBRAL_CI)),
        "umbral_un": safe(valores.get("umbral_un", UMBRAL_UN)),
    }
