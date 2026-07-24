"""
_helpers.py — Cotizador Picus
Funciones centralizadas de cálculo, datos generales, ubicaciones y resultados.

Reglas de negocio (sin cambios respecto a _helpers.py):
  - Costos fijos (nunca se cobran al cliente): movimiento_local, puntualidad,
    pension, estancia, fianza.
  - Casetas: va en el bloque de ruta junto con los KM (igual que americana).
  - Extras billables (cada uno tiene su propio flag cobrado): pistas_extra,
    stop, falso, gatas, accesorios, guias.
  - Costos indirectos 35%: IMPORTACION y EXPORTACION únicamente. VACIO = 0.
  - Ruta_Tipo "Tramo" fuerza sueldo/bono fijo independientemente del tipo.
  - Modo "Team" agrega bono_team al sueldo (excepto Tramo).

Homologado con Igloo / Lincoln:
  - obtener_config_tipo_ruta() → orden dinámico de secciones en captura/edición
  - mostrar_resultados_picus() → centraliza banner + KPIs + semáforos
  - limpiar_fila_json() → sanitiza payload antes de insert/update en Supabase
  - normalizar() / generar_id_ruta() (antes normalizar_texto / generar_nuevo_id)
"""

from __future__ import annotations

import os
import re as _re
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import streamlit as st
from services.auditoria import registrar_accion

# ─────────────────────────────────────────────
# Constantes de umbral — viajan también dentro de DEFAULTS y de cada
# resultado de calcular_utilidades(), pero se dejan aquí como referencia
# única para quien lea el módulo.
# ─────────────────────────────────────────────
UMBRAL_CD = 50.0
UMBRAL_UB = 50.0
UMBRAL_CI = 35.0
UMBRAL_UN = 15.0

# ─────────────────────────────────────────────
# Datos generales — defaults
# ─────────────────────────────────────────────
DEFAULTS: dict = {
    "Rendimiento Camion":   2.5,
    "Costo Diesel":        24.0,
    "Pago x KM (General)":  1.63,
    "Bono ISR IMSS RL":   462.66,
    "Bono ISR IMSS Tramo": 185.06,
    "Pago Vacio":          100.0,
    "Pago Tramo":          300.0,
    "Bono Rendimiento":    250.0,
    "Bono Modo Team":      650.0,
    "Tipo de cambio USD":   17.5,
    "Tipo de cambio MXP":    1.0,
    "umbral_cd": UMBRAL_CD,
    "umbral_ub": UMBRAL_UB,
    "umbral_ci": UMBRAL_CI,
    "umbral_un": UMBRAL_UN,
}

# ─────────────────────────────────────────────
# Tipos de ruta válidos — Picus NO tiene DOM MEX
# ─────────────────────────────────────────────
TIPOS_RUTA = ["IMPORTACION", "EXPORTACION", "VACIO"]
TIPOS_CON_INDIRECTOS = ["IMPORTACION", "EXPORTACION"]


# ─────────────────────────────────────────────
# CONFIG POR TIPO DE RUTA
# Orden visual de secciones en captura_rutas.py / gestion_rutas.py:
#   IMPORTACION → Cruce primero, luego Ruta MX
#   EXPORTACION → Ruta MX primero, luego Cruce
#   VACIO       → solo Ruta MX (sin cruce, sin indirectos)
# ─────────────────────────────────────────────
def obtener_config_tipo_ruta(tipo_ruta: str) -> dict:
    configs = {
        "IMPORTACION": {"cruce": True,  "ruta_mx": True,
                         "orden": ["cruce", "ruta_mx"]},
        "EXPORTACION": {"cruce": True,  "ruta_mx": True,
                         "orden": ["ruta_mx", "cruce"]},
        "VACIO":       {"cruce": False, "ruta_mx": True,
                         "orden": ["ruta_mx"]},
    }
    return configs.get(tipo_ruta, {"cruce": True, "ruta_mx": True, "orden": ["ruta_mx"]})


def tiene_cruce(tipo_ruta: str) -> bool:
    """Atajo sobre obtener_config_tipo_ruta() para checks rápidos en UI."""
    return obtener_config_tipo_ruta(tipo_ruta).get("cruce", False)


# ─────────────────────────────────────────────
# Carga / guarda datos generales — persistidos en Supabase
# (tabla datos_generales_cotizadores). Tipo de cambio USD se
# sobrescribe con Banxico FIX (cacheado 24h) cuando está disponible.
# ─────────────────────────────────────────────
from services.datos_generales import (
    cargar_datos_generales as _cargar_dg,
    guardar_datos_generales as _guardar_dg,
)


def cargar_datos_generales() -> dict:
    return _cargar_dg("picus", DEFAULTS, tc_key="Tipo de cambio USD")


def guardar_datos_generales(valores: dict) -> None:
    _guardar_dg("picus", valores)


# ─────────────────────────────────────────────
# Utilidades numéricas
# ─────────────────────────────────────────────
def safe_number(x) -> float:
    """Convierte a float seguro; None / NaN → 0.0."""
    if x is None:
        return 0.0
    try:
        if isinstance(x, float) and np.isnan(x):
            return 0.0
    except Exception:
        pass
    try:
        return float(x)
    except (ValueError, TypeError):
        return 0.0


def safe_float(x, default: float = 0.0) -> float:
    """Alias de safe_number con default configurable."""
    try:
        if x is None or (isinstance(x, float) and np.isnan(x)):
            return float(default)
        return float(x)
    except Exception:
        return float(default)


def limpiar_fila_json(fila: dict) -> dict:
    """Sanitiza un payload antes de insert/update en Supabase (igual que Igloo/Lincoln)."""
    import json
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
# Texto y timestamp
# ─────────────────────────────────────────────
def normalizar(texto: str) -> str:
    """Normaliza texto a mayúsculas, sin espacios dobles ni comas mal formateadas.
    (antes: normalizar_texto)"""
    if not texto:
        return ""
    texto = str(texto).upper().strip()
    texto = _re.sub(r'\s+', ' ', texto)
    texto = _re.sub(r'\s*,\s*', ', ', texto)
    return texto


def now_iso() -> str:
    """Timestamp UTC actual en formato ISO. Compartido por captura y gestión."""
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────
# Mostrar resultados — centraliza banner + KPIs + semáforos
# Reemplaza a mostrar_resultados_utilidad() (legacy, firma de 10 parámetros).
# Se deja mostrar_resultados_utilidad() abajo, SIN eliminar, hasta que
# TODOS los módulos de Picus migren a esta función (regla del proyecto).
# ─────────────────────────────────────────────
def mostrar_resultados_picus(util: dict, tc_usd: float = 0.0) -> None:
    """
    Muestra banner de tarifa sugerida + KPIs + semáforos para una ruta o
    grupo de rutas de Picus, a partir del dict canónico de
    calcular_utilidades() / calcular_utilidades_vuelta_redonda().

    util debe incluir: ingreso_total, costo_directo, utilidad_bruta,
    costos_indirectos, utilidad_neta, Pct_*, Color_*, umbral_cd/ub/ci/un.
    """
    from ui.components import banner_tarifa_sugerida, divider, kpi_row, semaforos_ruta

    ingreso_total = util["ingreso_total"]
    costo_directo = util["costo_directo"]

    umbral_cd   = util["umbral_cd"]
    tarifa_base = costo_directo / (umbral_cd / 100) if umbral_cd else 0.0
    valor_sec   = (tarifa_base / tc_usd) if tc_usd > 0 else 0.0
    banner_tarifa_sugerida(costo_directo, ingreso_total, umbral_cd, "MXP", valor_sec)

    divider()

    kpi_row([
        {"icono": "💰", "label": "Ingreso Total",      "valor": f"${ingreso_total:,.2f}",           "sub": "MXP",                                              "color": "#1B2266"},
        {"icono": "🔧", "label": "Costo Directo",      "valor": f"${costo_directo:,.2f}",           "sub": f"{util['Pct_Costo_Directo']:.1f}% del ingreso",    "color": util["Color_Directo"]},
        {"icono": "📊", "label": "Utilidad Bruta",     "valor": f"${util['utilidad_bruta']:,.2f}",  "sub": f"{util['Pct_Ut_Bruta']:.1f}%",                     "color": "#059669" if util["Pct_Ut_Bruta"] >= UMBRAL_UB else "#DC2626"},
        {"icono": "🏢", "label": "Costos Indirectos",  "valor": f"${util['costos_indirectos']:,.2f}","sub": f"{util['Pct_Costo_Indirecto']:.1f}% del ingreso", "color": util["Color_Indirecto"]},
        {"icono": "✅", "label": "Utilidad Neta",      "valor": f"${util['utilidad_neta']:,.2f}",   "sub": f"{util['Pct_Ut_Neta']:.1f}%",                      "color": util["Color_Ut_Neta"]},
    ])

    semaforos_ruta(util)


# ─────────────────────────────────────────────
# LEGACY — mantener firma intacta mientras los módulos migran a
# mostrar_resultados_picus(). No eliminar hasta que TODOS los módulos
# usen la versión centralizada.
# ─────────────────────────────────────────────
def mostrar_resultados_utilidad(
    st_module,
    ingreso_total:    float,
    costo_total:      float,
    utilidad_bruta:   float,
    costos_indirectos: float,
    utilidad_neta:    float,
    pct_bruta:        float,
    pct_neta:         float,
    tipo:             str = "",
    tc_usd:           float = 0.0,
) -> None:
    """LEGACY — usar mostrar_resultados_picus() en módulos nuevos."""
    util = calcular_utilidades(ingreso_total, costo_total, tipo)
    mostrar_resultados_picus(util, tc_usd=tc_usd)


# ─────────────────────────────────────────────
# Perfil de usuario
# ─────────────────────────────────────────────
def get_profile_name(user_id: str) -> str:
    """Obtiene el full_name del perfil dado su user_id."""
    if not user_id:
        return ""
    try:
        from services.supabase_client import get_authed_client
        supabase = get_authed_client()
        res = supabase.table("profiles").select("full_name").eq("user_id", user_id).single().execute()
        return (res.data or {}).get("full_name") or ""
    except Exception:
        return ""


# ─────────────────────────────────────────────
# Carga de rutas — compartida por consulta, gestión y simulador
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=120)
def load_rutas_picus() -> pd.DataFrame:
    """Carga todas las rutas de Rutas_Picus, ordenadas por Fecha desc."""
    from services.supabase_client import get_supabase_client
    supabase = get_supabase_client()
    if supabase is None:
        return pd.DataFrame()
    try:
        resp = supabase.table("Rutas_Picus").select("*").order("Fecha", desc=True).execute()
        return pd.DataFrame(resp.data) if resp.data else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


# ─────────────────────────────────────────────
# Pool de ubicaciones — compartido por captura y gestión
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=120)
def cargar_pool_ubicaciones_picus() -> list[str]:
    """Une y deduplica Origen + Destino de Rutas_Picus."""
    from services.supabase_client import get_supabase_client
    sb = get_supabase_client()
    if sb is None:
        return []
    try:
        resp = sb.table("Rutas_Picus").select("Origen, Destino").execute()
        ubicaciones: set[str] = set()
        for row in (resp.data or []):
            o = (row.get("Origen") or "").strip().upper()
            d = (row.get("Destino") or "").strip().upper()
            if o:
                ubicaciones.add(o)
            if d:
                ubicaciones.add(d)
        return sorted(ubicaciones)
    except Exception:
        return []


def buscar_ubicacion_picus(termino: str) -> list[str]:
    """
    Filtra el pool por lo que el usuario escribe.
    Si no hay coincidencias, devuelve el término como opción
    para permitir ubicaciones nuevas sin que el campo se limpie.
    """
    if not termino or len(termino) < 2:
        return []
    termino_upper = termino.upper()
    pool = cargar_pool_ubicaciones_picus()
    coincidencias = [u for u in pool if termino_upper in u]
    if not coincidencias:
        return [termino_upper]
    return coincidencias


# ─────────────────────────────────────────────
# Filtros y label — compartidos por consulta_ruta, gestion_rutas y simulador
# ─────────────────────────────────────────────
def label_ruta_picus(row) -> str:
    """Ejemplo: 'PIC000001 | IMPORTACION | CLIENTE | MTY → CDM'"""
    return (
        f"{row.get('ID_Ruta','?')} | "
        f"{row.get('Tipo','?')} | "
        f"{row.get('Cliente','?')} | "
        f"{row.get('Origen','?')} → {row.get('Destino','?')}"
    )


def filtrar_rutas_picus(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """
    Muestra un expander con filtros opcionales y devuelve el DataFrame filtrado.
    Usar con un prefix único por módulo:
      - consulta_ruta → "pic_cons"
      - gestion ver   → "pic_ver"
      - gestion del   → "pic_del"
      - gestion edit  → "pic_ed"
      - simulador     → "pic_sim"
    """
    with st.expander("🔎 Filtros de búsqueda (opcional)", expanded=False):
        fc1, fc2, fc3, fc4, fc5 = st.columns(5)
        tipos_disp    = ["Todos"] + sorted(df["Tipo"].dropna().unique().tolist()) if "Tipo" in df.columns else ["Todos"]
        clientes_disp = ["Todos"] + sorted(df["Cliente"].dropna().astype(str).unique().tolist()) if "Cliente" in df.columns else ["Todos"]
        filtro_tipo    = fc1.selectbox("Tipo",              tipos_disp,    key=f"{prefix}_ftipo")
        filtro_cliente = fc2.selectbox("Cliente",           clientes_disp, key=f"{prefix}_fcli")
        filtro_origen  = fc3.text_input("Origen contiene",                 key=f"{prefix}_forig")
        filtro_destino = fc4.text_input("Destino contiene",                key=f"{prefix}_fdest")
        filtro_id      = fc5.text_input("ID Ruta", placeholder="PIC000001", key=f"{prefix}_fid")

    out = df.copy()
    if filtro_tipo    != "Todos": out = out[out["Tipo"].astype(str) == filtro_tipo]
    if filtro_cliente != "Todos": out = out[out["Cliente"].astype(str) == filtro_cliente]
    if filtro_origen.strip():     out = out[out["Origen"].astype(str).str.upper().str.contains(filtro_origen.strip().upper(), na=False)]
    if filtro_destino.strip():    out = out[out["Destino"].astype(str).str.upper().str.contains(filtro_destino.strip().upper(), na=False)]
    if filtro_id.strip():         out = out[out["ID_Ruta"].astype(str).str.upper().str.contains(filtro_id.strip().upper(), na=False)]
    return out


# ─────────────────────────────────────────────
# Generador de ID — antes generar_nuevo_id()
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=60)
def _get_last_id_picus_cached() -> str | None:
    from services.supabase_client import get_supabase_client
    supabase = get_supabase_client()
    if supabase is None:
        return None
    resp = supabase.table("Rutas_Picus").select("ID_Ruta").order("ID_Ruta", desc=True).limit(1).execute()
    if resp.data:
        return resp.data[0].get("ID_Ruta")
    return None


def generar_id_ruta() -> str:
    """Genera el siguiente ID_Ruta (PIC000001, PIC000002, ...) para Rutas_Picus.
    (antes: generar_nuevo_id)"""
    ultimo = _get_last_id_picus_cached()
    if ultimo and isinstance(ultimo, str) and len(ultimo) >= 4:
        try:
            numero = int(str(ultimo)[3:]) + 1
        except Exception:
            numero = 1
    else:
        numero = 1
    return f"PIC{numero:06d}"


# ─────────────────────────────────────────────
# CÁLCULOS — SIN CAMBIOS respecto a _helpers.py
# ─────────────────────────────────────────────
def calcular_diesel(km: float, valores: dict) -> float:
    rend  = safe_float(valores.get("Rendimiento Camion", 2.5), 2.5)
    costo = safe_float(valores.get("Costo Diesel", 24.0), 24.0)
    return (km / max(rend, 0.0001)) * costo


def calcular_sueldo_bono(
    km: float,
    tipo: str,
    ruta_tipo: str,
    modo_viaje: str,
    valores: dict,
) -> dict:
    """
    Retorna dict con: sueldo, bono, modo_viaje_calc, pago_km.

    Reglas (NO TOCAR — lógica propia de Picus):
      - Ruta_Tipo == "Tramo"  → sueldo fijo + bono tramo; fuerza modo = "Operador"
      - IMPORTACION/EXPO      → sueldo = km × pago_km + bono RL + bono rendimiento
      - VACIO                 → sueldo fijo si km ≤ 100, else km × pago_km; bono = 0
      - Modo "Team" (no Tramo)→ agrega bono_team al sueldo
    """
    tipo      = (tipo or "").strip().upper()
    ruta_tipo = (ruta_tipo or "").strip()
    pago_km   = safe_float(valores.get("Pago x KM (General)", 1.63))

    if ruta_tipo == "Tramo":
        sueldo          = safe_float(valores.get("Pago Tramo", 300.0))
        bono            = safe_float(valores.get("Bono ISR IMSS Tramo", 185.06))
        modo_viaje_calc = "Operador"

    elif tipo in ("IMPORTACION", "EXPORTACION"):
        sueldo          = km * pago_km
        bono_isr        = safe_float(valores.get("Bono ISR IMSS RL", 462.66))
        bono_rend       = safe_float(valores.get("Bono Rendimiento", 250.0))
        bono            = bono_isr + bono_rend
        modo_viaje_calc = modo_viaje

    else:  # VACIO
        sueldo = (
            safe_float(valores.get("Pago Vacio", 100.0))
            if km <= 100
            else km * pago_km
        )
        bono            = 0.0
        modo_viaje_calc = modo_viaje

    # Bono Team (solo si no es Tramo)
    if ruta_tipo != "Tramo" and modo_viaje_calc == "Team":
        sueldo += safe_float(valores.get("Bono Modo Team", 650.0))

    return {
        "sueldo":           sueldo,
        "bono":             bono,
        "modo_viaje_calc":  modo_viaje_calc,
        "pago_km":          pago_km,
    }


def calcular_costos_fijos(
    movimiento_local: float,
    puntualidad: float,
    pension: float,
    estancia: float,
    fianza: float,
) -> float:
    """
    Costos internos de operación — siempre van al costo, NUNCA al ingreso.
    Incluye: movimiento_local, puntualidad, pension, estancia, fianza.
    Casetas va por separado en el bloque de ruta.
    """
    return sum(map(safe_number, [
        movimiento_local, puntualidad, pension, estancia, fianza,
    ]))


def calcular_extras(
    pistas_extra:      float,
    stop:              float,
    falso:             float,
    gatas:             float,
    accesorios:        float,
    guias:             float,
    pistas_cobrado:    bool = False,
    stop_cobrado:      bool = False,
    falso_cobrado:     bool = False,
    gatas_cobrado:     bool = False,
    accesorios_cobrado: bool = False,
    guias_cobrado:     bool = False,
) -> dict:
    """
    Costos extras cobrables al cliente.
    - costo_extras  : suma total (siempre va al costo)
    - ingreso_extras: suma de los que tienen su flag cobrado = True
    """
    conceptos = [
        (pistas_extra,  pistas_cobrado),
        (stop,          stop_cobrado),
        (falso,         falso_cobrado),
        (gatas,         gatas_cobrado),
        (accesorios,    accesorios_cobrado),
        (guias,         guias_cobrado),
    ]

    costo_extras   = sum(safe_number(v) for v, _ in conceptos)
    ingreso_extras = sum(safe_number(v) for v, cobrado in conceptos if cobrado)

    return {
        "costo_extras":   costo_extras,
        "ingreso_extras": ingreso_extras,
    }


def calcular_costos_indirectos(tipo: str, ingreso_total: float) -> float:
    """Aplica 35% solo a IMPORTACION y EXPORTACION. VACIO → 0."""
    tipo = (tipo or "").strip().upper()
    if tipo in TIPOS_CON_INDIRECTOS:
        return ingreso_total * (UMBRAL_CI / 100)
    return 0.0


def calcular_utilidades(ingreso_total: float, costo_total: float, tipo: str) -> dict:
    """
    Retorna dict canónico con utilidades calculadas + campos para
    semaforos_ruta() y kpi_row() (SIN CAMBIOS respecto a _helpers.py).
    """
    utilidad_bruta = ingreso_total - costo_total
    costos_ind     = calcular_costos_indirectos(tipo, ingreso_total)
    utilidad_neta  = utilidad_bruta - costos_ind

    pct_bruta = (utilidad_bruta / ingreso_total * 100) if ingreso_total else 0.0
    pct_neta  = (utilidad_neta  / ingreso_total * 100) if ingreso_total else 0.0
    pct_cd    = (costo_total    / ingreso_total * 100) if ingreso_total else 0.0
    pct_ind   = (costos_ind     / ingreso_total * 100) if ingreso_total else 0.0

    return {
        "ingreso_total":     ingreso_total,
        "costo_directo":     costo_total,
        "utilidad_bruta":    utilidad_bruta,
        "costos_indirectos": costos_ind,
        "utilidad_neta":     utilidad_neta,
        "porcentaje_bruta":  pct_bruta,
        "porcentaje_neta":   pct_neta,
        "Pct_Costo_Directo":   pct_cd,
        "Pct_Ut_Bruta":        pct_bruta,
        "Pct_Costo_Indirecto": pct_ind,
        "Pct_Ut_Neta":         pct_neta,
        "Color_Directo":   "#DC2626" if pct_cd   > UMBRAL_CD else "#059669",
        "Color_Indirecto": "#D97706" if pct_ind  > UMBRAL_CI else "#059669",
        "Color_Ut_Neta":   "#DC2626" if pct_neta < UMBRAL_UN else "#059669",
        "umbral_cd": UMBRAL_CD,
        "umbral_ub": UMBRAL_UB,
        "umbral_ci": UMBRAL_CI,
        "umbral_un": UMBRAL_UN,
    }


def calcular_utilidades_vuelta_redonda(rutas_seleccionadas: list) -> dict:
    """
    Calcula utilidades agregadas para una vuelta redonda.
    Aplica 35% de indirectos solo a rutas IMPORTACION / EXPORTACION.
    VACIO → indirectos = 0 (SIN CAMBIOS respecto a _helpers.py).
    """
    ingreso_total = sum(safe_number(r.get("Ingreso Total", 0)) for r in rutas_seleccionadas)
    costo_total   = sum(safe_number(r.get("Costo_Total_Ruta", 0)) for r in rutas_seleccionadas)

    costos_ind = sum(
        calcular_costos_indirectos(str(r.get("Tipo", "")), safe_number(r.get("Ingreso Total", 0)))
        for r in rutas_seleccionadas
    )

    utilidad_bruta = ingreso_total - costo_total
    utilidad_neta  = utilidad_bruta - costos_ind

    pct_bruta = (utilidad_bruta / ingreso_total * 100) if ingreso_total else 0.0
    pct_neta  = (utilidad_neta  / ingreso_total * 100) if ingreso_total else 0.0
    pct_cd    = (costo_total    / ingreso_total * 100) if ingreso_total else 0.0
    pct_ind   = (costos_ind     / ingreso_total * 100) if ingreso_total else 0.0

    return {
        "ingreso_total":     ingreso_total,
        "costo_directo":     costo_total,
        "costo_total":       costo_total,
        "utilidad_bruta":    utilidad_bruta,
        "costos_indirectos": costos_ind,
        "utilidad_neta":     utilidad_neta,
        "porcentaje_bruta":  pct_bruta,
        "porcentaje_neta":   pct_neta,
        "Pct_Costo_Directo":   pct_cd,
        "Pct_Ut_Bruta":        pct_bruta,
        "Pct_Costo_Indirecto": pct_ind,
        "Pct_Ut_Neta":         pct_neta,
        "Color_Directo":   "#DC2626" if pct_cd   > UMBRAL_CD else "#059669",
        "Color_Indirecto": "#D97706" if pct_ind  > UMBRAL_CI else "#059669",
        "Color_Ut_Neta":   "#DC2626" if pct_neta < UMBRAL_UN else "#059669",
        "umbral_cd": UMBRAL_CD,
        "umbral_ub": UMBRAL_UB,
        "umbral_ci": UMBRAL_CI,
        "umbral_un": UMBRAL_UN,
    }


# ─────────────────────────────────────────────
# AUDITORÍA
# ─────────────────────────────────────────────
def log_accion(accion: str, detalle: dict | None = None) -> None:
    """Wrapper de auditoría — centraliza el nombre del módulo 'cot-picus'."""
    registrar_accion("cot-picus", accion, detalle)
