"""
helpers.py — Funciones centralizadas de cálculo para el cotizador Picus.

Reglas de negocio:
  - Costos fijos (nunca se cobran al cliente): movimiento_local, puntualidad,
    pension, estancia, fianza.
  - Casetas: va en el bloque de ruta junto con los KM (igual que americana).
  - Extras billables (cada uno tiene su propio flag cobrado): pistas_extra,
    stop, falso, gatas, accesorios, guias.
  - Costos indirectos 35%: IMPORTACION y EXPORTACION únicamente. VACIO = 0.
  - Ruta_Tipo "Tramo" fuerza sueldo/bono fijo independientemente del tipo.
  - Modo "Team" agrega bono_team al sueldo (excepto Tramo).
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import streamlit as st

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


# ─────────────────────────────────────────────
# Datos generales (CSV)
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
    "umbral_cd": 50.0,
    "umbral_ub": 50.0,
    "umbral_ci": 35.0,
    "umbral_un": 15.0,
}

TIPOS_RUTA = ["IMPORTACION", "EXPORTACION", "VACIO"]
TIPOS_CON_INDIRECTOS = ["IMPORTACION", "EXPORTACION"]


def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _datos_generales_path() -> str:
    base = os.path.join(_project_root(), ".data")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "datos_generales_picus.csv")


def cargar_datos_generales() -> dict:
    """
    Lee el CSV de datos generales y lo fusiona con DEFAULTS.
    Si Banxico está disponible, sobreescribe el tipo de cambio USD
    con el valor FIX del día (cacheado 24h).
    """
    path = _datos_generales_path()
    if os.path.exists(path):
        try:
            df = pd.read_csv(path)
            if {"Parametro", "Valor"}.issubset(df.columns):
                vals = {}
                for _, row in df.iterrows():
                    p = str(row["Parametro"])
                    v = row["Valor"]
                    try:
                        v = float(v)
                    except Exception:
                        pass
                    vals[p] = v
                resultado = {**DEFAULTS, **vals}
            else:
                resultado = DEFAULTS.copy()
        except Exception:
            resultado = DEFAULTS.copy()
    else:
        resultado = DEFAULTS.copy()

    # Sobrescribir TC con Banxico si está disponible (cache 24h)
    try:
        from services.banxico import get_tipo_cambio_fix
        token = st.secrets.get("TOKEN_BMX", "")
        tc = get_tipo_cambio_fix(token) if token else None
        if tc:
            resultado["Tipo de cambio USD"] = tc
    except Exception:
        pass  # Si falla, conserva el valor del CSV sin romper nada

    return resultado


def guardar_datos_generales(valores: dict) -> None:
    """Guarda el diccionario de datos generales como CSV."""
    df = pd.DataFrame(
        [{"Parametro": k, "Valor": valores[k]} for k in valores],
        columns=["Parametro", "Valor"],
    )
    df.to_csv(_datos_generales_path(), index=False)


# ─────────────────────────────────────────────
# Cálculo de diesel
# ─────────────────────────────────────────────

def calcular_diesel(km: float, valores: dict) -> float:
    """Retorna costo_diesel_camion."""
    rend  = safe_float(valores.get("Rendimiento Camion", 2.5), 2.5)
    costo = safe_float(valores.get("Costo Diesel", 24.0), 24.0)
    return (km / max(rend, 0.0001)) * costo


# ─────────────────────────────────────────────
# Cálculo de sueldo y bono
# ─────────────────────────────────────────────

def calcular_sueldo_bono(
    km: float,
    tipo: str,
    ruta_tipo: str,
    modo_viaje: str,
    valores: dict,
) -> dict:
    """
    Retorna dict con: sueldo, bono, modo_viaje_calc, pago_km.

    Reglas:
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


# ─────────────────────────────────────────────
# Costos fijos (nunca se cobran al cliente)
# ─────────────────────────────────────────────

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


# ─────────────────────────────────────────────
# Extras billables (checkbox individual por concepto)
# ─────────────────────────────────────────────

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


# ─────────────────────────────────────────────
# Costos indirectos
# ─────────────────────────────────────────────

def calcular_costos_indirectos(tipo: str, ingreso_total: float) -> float:
    """
    Aplica 35% solo a IMPORTACION y EXPORTACION.
    VACIO → 0.
    """
    tipo = (tipo or "").strip().upper()
    if tipo in TIPOS_CON_INDIRECTOS:
        return ingreso_total * 0.35
    return 0.0


# ─────────────────────────────────────────────
# Utilidades
# ─────────────────────────────────────────────

def calcular_utilidades(ingreso_total: float, costo_total: float, tipo: str) -> dict:
    """
    Retorna dict con utilidades calculadas + campos para semaforos_ruta() y kpi_row().

    Campos originales (compatibles con módulos existentes):
        utilidad_bruta, costos_indirectos, utilidad_neta,
        porcentaje_bruta, porcentaje_neta

    Campos para componentes visuales:
        Pct_Costo_Directo, Pct_Ut_Bruta, Pct_Costo_Indirecto, Pct_Ut_Neta
        Color_Directo, Color_Indirecto, Color_Ut_Neta

    Umbrales Picus (igual que Igloo):
        C. Directos  ≤ 50% → verde
        Ut. Bruta    ≥ 50% → verde
        C. Indirecto ≤ 35% → verde
        Ut. Neta     ≥ 15% → verde
    """
    utilidad_bruta = ingreso_total - costo_total
    costos_ind     = calcular_costos_indirectos(tipo, ingreso_total)
    utilidad_neta  = utilidad_bruta - costos_ind

    pct_bruta = (utilidad_bruta / ingreso_total * 100) if ingreso_total else 0.0
    pct_neta  = (utilidad_neta  / ingreso_total * 100) if ingreso_total else 0.0
    pct_cd    = (costo_total    / ingreso_total * 100) if ingreso_total else 0.0
    pct_ind   = (costos_ind     / ingreso_total * 100) if ingreso_total else 0.0

    return {
        # Campos canónicos
        "ingreso_total":     ingreso_total,
        "costo_directo":     costo_total,    # alias canónico
        # Originales — compatibilidad
        "utilidad_bruta":    utilidad_bruta,
        "costos_indirectos": costos_ind,
        "utilidad_neta":     utilidad_neta,
        "porcentaje_bruta":  pct_bruta,
        "porcentaje_neta":   pct_neta,
        # Para semaforos_ruta() de components.py
        "Pct_Costo_Directo":   pct_cd,
        "Pct_Ut_Bruta":        pct_bruta,
        "Pct_Costo_Indirecto": pct_ind,
        "Pct_Ut_Neta":         pct_neta,
        # Colores para kpi_row()
        "Color_Directo":   "#DC2626" if pct_cd   > 50.0 else "#059669",
        "Color_Indirecto": "#D97706" if pct_ind  > 35.0 else "#059669",
        "Color_Ut_Neta":   "#DC2626" if pct_neta < 15.0 else "#059669",
        # Umbrales Picus — viajan con el resultado
        "umbral_cd": 50.0,
        "umbral_ub": 50.0,
        "umbral_ci": 35.0,
        "umbral_un": 15.0,
    }


# ─────────────────────────────────────────────
# Mostrar resultados — compatible con módulos actuales
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
    """
    LEGACY — mantener firma intacta mientras los módulos migran a mostrar_resultados_ruta().
    Sin HTML inline — delega todo el rendering a ui/components.py.
    tc_usd: tipo de cambio activo; si > 0 muestra equivalente USD en la tarifa sugerida.
    """
    from ui.components import (
        banner_tarifa_sugerida, divider, kpi_row, mostrar_resultados_ruta, semaforos_ruta,
    )

    util = calcular_utilidades(ingreso_total, costo_total, tipo)

    # ── Tarifa sugerida ──
    tarifa_base  = costo_total * 2.0
    valor_sec    = (tarifa_base / tc_usd) if tc_usd > 0 else 0.0
    banner_tarifa_sugerida(tarifa_base, ingreso_total, "MXP", valor_sec)

    divider()

    # ── KPIs principales ──
    kpi_row([
        {"icono": "💰", "label": "Ingreso Total",      "valor": f"${ingreso_total:,.2f}",    "sub": "MXP",                                    "color": "#1B2266"},
        {"icono": "🔧", "label": "Costo Directo",      "valor": f"${costo_total:,.2f}",      "sub": f"{util['Pct_Costo_Directo']:.1f}% del ingreso", "color": util["Color_Directo"]},
        {"icono": "📊", "label": "Utilidad Bruta",     "valor": f"${utilidad_bruta:,.2f}",   "sub": f"{pct_bruta:.1f}%",                      "color": "#059669" if pct_bruta >= 50 else "#DC2626"},
        {"icono": "🏢", "label": "Costos Indirectos",  "valor": f"${costos_indirectos:,.2f}","sub": f"{util['Pct_Costo_Indirecto']:.1f}% del ingreso","color": util["Color_Indirecto"]},
        {"icono": "✅", "label": "Utilidad Neta",      "valor": f"${utilidad_neta:,.2f}",    "sub": f"{pct_neta:.1f}%",                       "color": util["Color_Ut_Neta"]},
    ])

    # ── Semáforos — firma canónica, umbrales viajan en util ──
    semaforos_ruta(util)

# ─────────────────────────────────────────────
# Utilidades Vuelta Redonda (simulador)
# ─────────────────────────────────────────────

def calcular_utilidades_vuelta_redonda(rutas_seleccionadas: list) -> dict:
    """
    Calcula utilidades agregadas para una vuelta redonda.
    Aplica 35% de indirectos solo a rutas IMPORTACION / EXPORTACION.
    VACIO → indirectos = 0 (igual que Igloo).

    Devuelve los mismos campos que calcular_utilidades() para que
    mostrar_resultados_utilidad() los use directamente.
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
        # Campos canónicos
        "ingreso_total":     ingreso_total,
        "costo_directo":     costo_total,    # alias canónico
        "costo_total":       costo_total,    # compatibilidad legacy
        "utilidad_bruta":    utilidad_bruta,
        "costos_indirectos": costos_ind,
        "utilidad_neta":     utilidad_neta,
        "porcentaje_bruta":  pct_bruta,
        "porcentaje_neta":   pct_neta,
        "Pct_Costo_Directo":   pct_cd,
        "Pct_Ut_Bruta":        pct_bruta,
        "Pct_Costo_Indirecto": pct_ind,
        "Pct_Ut_Neta":         pct_neta,
        "Color_Directo":   "#DC2626" if pct_cd   > 50.0 else "#059669",
        "Color_Indirecto": "#D97706" if pct_ind  > 35.0 else "#059669",
        "Color_Ut_Neta":   "#DC2626" if pct_neta < 15.0 else "#059669",
        # Umbrales Picus — viajan con el resultado
        "umbral_cd": 50.0,
        "umbral_ub": 50.0,
        "umbral_ci": 35.0,
        "umbral_un": 15.0,
    }


# ─────────────────────────────────────────────
# Funciones compartidas — usadas en 2+ módulos
# (antes vivían como privadas en captura/gestión)
# ─────────────────────────────────────────────

import re as _re


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


def normalizar_texto(texto: str) -> str:
    """Normaliza texto a mayúsculas, sin espacios dobles ni comas mal formateadas."""
    if not texto:
        return ""
    texto = str(texto).upper().strip()
    texto = _re.sub(r'\s+', ' ', texto)
    texto = _re.sub(r'\s*,\s*', ', ', texto)
    return texto


def now_iso() -> str:
    """Timestamp UTC actual en formato ISO. Compartido por captura y gestión."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


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


def generar_nuevo_id() -> str:
    """Genera el siguiente ID_Ruta (PIC000001, PIC000002, ...) para Rutas_Picus."""
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
# Pool de ubicaciones — compartido por captura y gestión
# ─────────────────────────────────────────────

@st.cache_data(show_spinner=False, ttl=120)
def cargar_pool_ubicaciones_picus() -> list[str]:
    """
    Une y deduplica Origen + Destino de Rutas_Picus.
    Compartido por captura_rutas y gestion_rutas.
    """
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
# Carga de rutas — compartida por consulta, gestión y simulador
# ─────────────────────────────────────────────

@st.cache_data(show_spinner=False, ttl=120)
def load_rutas_picus() -> pd.DataFrame:
    """
    Carga todas las rutas de Rutas_Picus, ordenadas por Fecha desc.
    Compartida por consulta_ruta, gestion_rutas y simulador.
    """
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
# Filtros y label — compartidos por consulta_ruta,
# gestion_rutas y simulador para evitar keys duplicadas
# ─────────────────────────────────────────────

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


def label_ruta_picus(row) -> str:
    """
    Formatea una fila de ruta para selectboxes.
    Ejemplo: 'PIC000001 | IMPORTACION | CLIENTE | MTY → CDM'
    """
    return (
        f"{row.get('ID_Ruta','?')} | "
        f"{row.get('Tipo','?')} | "
        f"{row.get('Cliente','?')} | "
        f"{row.get('Origen','?')} → {row.get('Destino','?')}"
    )
