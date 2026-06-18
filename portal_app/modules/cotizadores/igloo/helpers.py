"""
helpers.py — Funciones centralizadas de cálculo para el cotizador Igloo.

Este archivo existe para que TODOS los módulos (captura, consulta, gestión,
simulador, programación, viajes concluidos) calculen utilidades exactamente
igual, evitando inconsistencias.

Regla de negocio:
  - El 35 % de costos indirectos se aplica a IMPORTACION, EXPORTACION y DOM MEX.
  - VACIO NO lleva costos indirectos.
"""

import os
import re as _re
import numpy as np
import pandas as pd
import streamlit as st

from ui.components import section_header, kpi_row, semaforos_ruta, divider
# ─────────────────────────────────────────────
# Funciones de seguridad numérica
# ─────────────────────────────────────────────
def safe_number(x):
    """Convierte a float seguro; None / NaN → 0.0."""
    if x is None:
        return 0.0
    if isinstance(x, float) and (pd.isna(x) or np.isnan(x)):
        return 0.0
    try:
        return float(x)
    except (ValueError, TypeError):
        return 0.0


def safe_float(x, default=0.0):
    """Alias más explícito de safe_number con default configurable."""
    try:
        if x is None or (isinstance(x, float) and np.isnan(x)):
            return float(default)
        return float(x)
    except Exception:
        return float(default)


# ─────────────────────────────────────────────
# Datos generales (CSV)
# ─────────────────────────────────────────────
DEFAULTS = {
    "Rendimiento Camion": 2.5,
    "Costo Diesel": 24.0,
    "Rendimiento Termo": 3.0,
    "Bono ISR IMSS": 462.66,
    "Pago x km IMPORTACION": 2.10,
    "Pago x km EXPORTACION": 2.50,
    "Pago fijo VACIO": 200.00,
    "Pago x km DOM MEX": 2.10,
    "Pago fijo DOM MEX": 200.00,
    "Tipo de cambio USD": 19.5,
    "Tipo de cambio MXP": 1.0,
}


def _project_root() -> str:
    """Sube 3 niveles desde igloo/ hasta portal_app/."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _datos_generales_path() -> str:
    base = os.path.join(_project_root(), ".data")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "datos_generales_igloo.csv")


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
# Tipos de ruta válidos
# ─────────────────────────────────────────────
TIPOS_RUTA = ["IMPORTACION", "EXPORTACION", "VACIO", "DOM MEX"]
TIPOS_CON_INDIRECTOS = ["IMPORTACION", "EXPORTACION", "DOM MEX"]


# ─────────────────────────────────────────────
# Cálculos centralizados
# ─────────────────────────────────────────────
def convertir_a_mxp(valor: float, moneda: str, tc_usd: float) -> float:
    """Convierte un valor a MXP según la moneda."""
    moneda = (moneda or "MXP").strip().upper()
    if moneda == "USD":
        return float(valor) * tc_usd
    return float(valor)


def calcular_sueldo_y_bono(tipo: str, km: float, modo: str, valores: dict,
                            modo_pago_dom: str = "km"):
    """
    Retorna (pago_km, sueldo, bono) según el tipo de ruta.

    modo_pago_dom: solo relevante para DOM MEX.  Puede ser "km" o "fijo".
    """
    tipo  = (tipo or "").strip().upper()
    modo  = (modo or "Operador")
    factor = 2 if modo == "Team" else 1

    if tipo == "IMPORTACION":
        pago_km = safe_float(valores.get("Pago x km IMPORTACION", 2.10))
        sueldo  = km * pago_km * factor
        bono    = safe_float(valores.get("Bono ISR IMSS", 462.66)) * factor

    elif tipo == "EXPORTACION":
        pago_km = safe_float(valores.get("Pago x km EXPORTACION", 2.50))
        sueldo  = km * pago_km * factor
        bono    = safe_float(valores.get("Bono ISR IMSS", 462.66)) * factor

    elif tipo == "DOM MEX":
        if modo_pago_dom == "fijo":
            pago_km = 0.0
            sueldo  = safe_float(valores.get("Pago fijo DOM MEX", 200.0)) * factor
        else:  # por km
            pago_km = safe_float(valores.get("Pago x km DOM MEX", 2.10))
            sueldo  = km * pago_km * factor
        bono = safe_float(valores.get("Bono ISR IMSS", 462.66)) * factor

    elif tipo == "VACIO":
        pago_km = 0.0
        sueldo  = safe_float(valores.get("Pago fijo VACIO", 200.0)) * factor
        bono    = 0.0

    else:
        pago_km = 0.0
        sueldo  = 0.0
        bono    = 0.0

    return pago_km, sueldo, bono


def calcular_costos_indirectos(tipo: str, ingreso_total: float) -> float:
    """
    Aplica 35 % de costos indirectos SOLO si el tipo de ruta lo requiere.
    VACIO → 0.
    IMPORTACION / EXPORTACION / DOM MEX → ingreso_total × 0.35
    """
    tipo = (tipo or "").strip().upper()
    if tipo in TIPOS_CON_INDIRECTOS:
        return ingreso_total * 0.35
    return 0.0


def calcular_diesel(km: float, horas_termo: float, valores: dict):
    """Retorna (costo_diesel_camion, costo_diesel_termo)."""
    rend_camion  = safe_float(valores.get("Rendimiento Camion", 2.5), 2.5)
    rend_termo   = safe_float(valores.get("Rendimiento Termo",  3.0), 3.0)
    costo_diesel = safe_float(valores.get("Costo Diesel",      24.0), 24.0)

    diesel_camion = (km / max(rend_camion, 0.0001)) * costo_diesel
    diesel_termo  = horas_termo * rend_termo * costo_diesel
    return diesel_camion, diesel_termo


def calcular_costos_fijos(lavado_termo, movimiento_local, puntualidad_val,
                          pension, estancia, fianza_termo, renta_termo, casetas):
    """
    Costos internos de operación — siempre van al costo, NUNCA al ingreso.
    Incluye: lavado_termo, movimiento_local, puntualidad, pension,
             estancia, fianza_termo, renta_termo, casetas.
    """
    return sum(map(safe_number, [
        lavado_termo, movimiento_local, puntualidad_val,
        pension, estancia, fianza_termo, renta_termo, casetas,
    ]))


def calcular_extras(pistas_extra, stop, falso, gatas, accesorios, guias):
    """
    Costos extras COBRABLES al cliente (pistas, stop, falso, gatas,
    accesorios, guias). Siempre se suman al costo; también al ingreso
    si costos_extras_cobrados=True.
    """
    return sum(map(safe_number, [
        pistas_extra, stop, falso, gatas, accesorios, guias,
    ]))


def calcular_utilidades(ingreso_total: float, costo_total: float, tipo: str):
    """
    Retorna dict con utilidades calculadas + campos para semaforos_ruta() y kpi_row().

    Campos originales (sin cambio, compatibles con todos los módulos existentes):
        utilidad_bruta, costos_indirectos, utilidad_neta,
        porcentaje_bruta, porcentaje_neta

    Campos nuevos para componentes visuales:
        Pct_Costo_Directo, Pct_Ut_Bruta, Pct_Costo_Indirecto, Pct_Ut_Neta
        Color_Directo, Color_Indirecto, Color_Ut_Neta

    Umbrales Igloo:
        C. Directos  ≤ 50%  → verde
        Ut. Bruta    ≥ 50%  → verde
        C. Indirecto ≤ 35%  → verde  (el 35% es el valor fijo calculado)
        Ut. Neta     ≥ 15%  → verde
    """
    # ── Cálculos (sin modificar) ─────────────────────────────────────────────
    utilidad_bruta = ingreso_total - costo_total
    costos_ind     = calcular_costos_indirectos(tipo, ingreso_total)
    utilidad_neta  = utilidad_bruta - costos_ind

    pct_bruta = (utilidad_bruta / ingreso_total * 100) if ingreso_total else 0
    pct_neta  = (utilidad_neta  / ingreso_total * 100) if ingreso_total else 0
    pct_cd    = (costo_total    / ingreso_total * 100) if ingreso_total else 0
    pct_ind   = (costos_ind     / ingreso_total * 100) if ingreso_total else 0

    return {
        # ── Campos originales — sin cambio ───────────────────────────────────
        "utilidad_bruta":    utilidad_bruta,
        "costos_indirectos": costos_ind,
        "utilidad_neta":     utilidad_neta,
        "porcentaje_bruta":  pct_bruta,
        "porcentaje_neta":   pct_neta,
        # ── Campos canónicos (alias + totales) ───────────────────────────────
        "ingreso_total":  ingreso_total,
        "costo_directo":  costo_total,   # alias canónico de costo_total
        # ── Campos para semaforos_ruta() de components.py ────────────────────
        "Pct_Costo_Directo":   pct_cd,
        "Pct_Ut_Bruta":        pct_bruta,
        "Pct_Costo_Indirecto": pct_ind,
        "Pct_Ut_Neta":         pct_neta,
        # ── Colores para kpi_row() — umbrales Igloo ──────────────────────────
        "Color_Directo":   "#DC2626" if pct_cd    > 50.0 else "#059669",
        "Color_Indirecto": "#D97706" if pct_ind   > 35.0 else "#059669",
        "Color_Ut_Neta":   "#DC2626" if pct_neta  < 15.0 else "#059669",
        # ── Umbrales Igloo — viajan con el resultado ─────────────────────────
        "umbral_cd": 50.0,
        "umbral_ub": 50.0,
        "umbral_ci": 35.0,
        "umbral_un": 15.0,
    }


def calcular_utilidades_vuelta_redonda(rutas_seleccionadas: list):
    """
    Calcula utilidades para una vuelta redonda (simulador / programación).
    Aplica 35 % solo a las rutas que NO son VACÍO.
    """
    ingreso_total  = sum(safe_number(r.get("Ingreso Total", 0)) for r in rutas_seleccionadas)
    costo_total    = sum(safe_number(r.get("Costo_Total_Ruta", 0)) for r in rutas_seleccionadas)
    utilidad_bruta = ingreso_total - costo_total

    # Costos indirectos: solo de los tramos que califican
    costos_ind = 0.0
    for r in rutas_seleccionadas:
        tipo = str(r.get("Tipo", "")).strip().upper()
        ing  = safe_number(r.get("Ingreso Total", 0))
        costos_ind += calcular_costos_indirectos(tipo, ing)

    utilidad_neta = utilidad_bruta - costos_ind
    pct_bruta     = (utilidad_bruta / ingreso_total * 100) if ingreso_total else 0
    pct_neta      = (utilidad_neta  / ingreso_total * 100) if ingreso_total else 0

    return {
        "ingreso_total":     ingreso_total,
        "costo_total":       costo_total,
        "utilidad_bruta":    utilidad_bruta,
        "costos_indirectos": costos_ind,
        "utilidad_neta":     utilidad_neta,
        "porcentaje_bruta":  pct_bruta,
        "porcentaje_neta":   pct_neta,
    }


# ─────────────────────────────────────────────
# Mostrar resultados — función LEGACY mantenida
# para compatibilidad mientras se migran módulos
# ─────────────────────────────────────────────
def mostrar_resultados_utilidad(st_module, ingreso_total, costo_total,
                                 utilidad_bruta, costos_indirectos,
                                 utilidad_neta, pct_bruta, pct_neta,
                                 tipo: str = "", tc_usd: float = 0.0):
    """
    Muestra las métricas de utilidad con formato visual.
    LEGACY: se mantiene para no romper módulos que aún la llamen.
    Los módulos nuevos usan kpi_row() + semaforos_ruta() directamente.

    tc_usd: tipo de cambio activo. Si > 0, la tarifa sugerida también
            se muestra convertida a USD.
    """
    # ── Tarifa sugerida: costo = 50% del ingreso → ingreso = costo × 2 ──
    tarifa_mxp = costo_total * 2.0
    tarifa_usd = (tarifa_mxp / tc_usd) if tc_usd > 0 else 0.0

    usd_extra = (
        f"&nbsp;&nbsp;/&nbsp;&nbsp;USD ${tarifa_usd:,.2f}"
        if tc_usd > 0 else ""
    )

    if tarifa_mxp > 0:
        if ingreso_total == 0:
            st_module.markdown(
                f"""
                <div style='background:#fffbeb; border-left:4px solid #f59e0b;
                            padding:10px 16px; border-radius:8px; margin-bottom:14px;
                            font-size:0.9rem; color:#92400e;'>
                    💡 <b>Tarifa sugerida (50% margen):</b>
                    &nbsp; MXP ${tarifa_mxp:,.2f}{usd_extra}<br>
                    <span style='font-size:0.78rem; opacity:0.8;'>
                        El costo directo debe representar el 50% del ingreso total.
                        TC utilizado: ${tc_usd:,.2f} MXP/USD
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            diff     = ingreso_total - tarifa_mxp
            diff_pct = (diff / tarifa_mxp * 100) if tarifa_mxp else 0
            color_diff = "#059669" if diff >= 0 else "#dc2626"
            signo    = "+" if diff >= 0 else ""
            icon     = "✅" if diff >= 0 else "⚠️"
            st_module.markdown(
                f"""
                <div style='background:#eff6ff; border-left:4px solid #3b82f6;
                            padding:10px 16px; border-radius:8px; margin-bottom:14px;
                            font-size:0.9rem; color:#1e40af;'>
                    📊 <b>Tarifa sugerida (50% margen):</b>
                    &nbsp; MXP ${tarifa_mxp:,.2f}{usd_extra}
                    &nbsp;|&nbsp;
                    {icon} Tu tarifa está
                    <span style='color:{color_diff}; font-weight:700;'>
                        {signo}{diff_pct:.1f}% ({signo}${diff:,.2f} MXP)
                    </span>
                    vs la sugerida
                </div>
                """,
                unsafe_allow_html=True,
            )

    pct_cd  = (costo_total       / ingreso_total * 100) if ingreso_total else 0
    pct_ind = (costos_indirectos / ingreso_total * 100) if ingreso_total else 0

    kpi_row([
        {
            "icono": "💰",
            "label": "Ingreso Global",
            "valor": f"${ingreso_total:,.2f}",
            "sub":   "MXP",
            "color": "#1B2266",
        },
        {
            "icono": "📉",
            "label": "Costo Directo",
            "valor": f"${costo_total:,.2f}",
            "sub":   f"{pct_cd:.1f}%",
            "color": "#DC2626" if pct_cd > 50.0 else "#059669",
        },
        {
            "icono": "📈",
            "label": "Costo Indirecto",
            "valor": f"${costos_indirectos:,.2f}",
            "sub":   f"{pct_ind:.1f}%",
            "color": "#D97706" if pct_ind > 35.0 else "#059669",
        },
        {
            "icono": "✅",
            "label": "Utilidad Neta",
            "valor": f"${utilidad_neta:,.2f}",
            "sub":   f"{pct_neta:.1f}%",
            "color": "#DC2626" if pct_neta < 15.0 else "#059669",
        },
    ])

    divider()

    semaforos_ruta({
        "Pct_Costo_Directo":   pct_cd,
        "Pct_Ut_Bruta":        pct_bruta,
        "Pct_Costo_Indirecto": pct_ind,
        "Pct_Ut_Neta":         pct_neta,
        "umbral_cd": 50.0,
        "umbral_ub": 50.0,
        "umbral_ci": 35.0,
        "umbral_un": 15.0,
    })


# ─────────────────────────────────────────────
# Funciones compartidas (antes vivían en los módulos como privadas)
# ─────────────────────────────────────────────

@st.cache_data(show_spinner=False, ttl=60)
def _get_last_id_igloo_cached(table_name: str):
    from services.supabase_client import get_supabase_client
    supabase = get_supabase_client()
    if supabase is None:
        return None
    resp = supabase.table(table_name).select("ID_Ruta").order("ID_Ruta", desc=True).limit(1).execute()
    if resp.data:
        return resp.data[0].get("ID_Ruta")
    return None


def generar_nuevo_id(table_name: str) -> str:
    """Genera el siguiente ID_Ruta (IG000001, IG000002, ...) para la tabla dada."""
    ultimo = _get_last_id_igloo_cached(table_name)
    if ultimo and isinstance(ultimo, str) and len(ultimo) >= 3:
        try:
            numero = int(ultimo[2:]) + 1
        except Exception:
            numero = 1
    else:
        numero = 1
    return f"IG{numero:06d}"


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


# ─────────────────────────────────────────────
# Pool de ubicaciones — compartido por captura y gestión
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=120)
def cargar_pool_ubicaciones_igloo() -> list[str]:
    """
    Une y deduplica Origen + Destino de la tabla Rutas.
    Compartido por captura_rutas y gestion_rutas.
    """
    from services.supabase_client import get_supabase_client
    sb = get_supabase_client()
    if sb is None:
        return []
    try:
        resp = sb.table("Rutas").select("Origen, Destino").execute()
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


def buscar_ubicacion_igloo(termino: str) -> list[str]:
    """
    Filtra el pool por lo que el usuario escribe.
    Si no hay coincidencias, devuelve el término como opción
    para permitir ubicaciones nuevas sin que el campo se limpie.
    """
    if not termino or len(termino) < 2:
        return []
    termino_upper = termino.upper()
    pool = cargar_pool_ubicaciones_igloo()
    coincidencias = [u for u in pool if termino_upper in u]
    if not coincidencias:
        return [termino_upper]
    return coincidencias


# ─────────────────────────────────────────────
# Filtros y label — compartidos por consulta_ruta,
# gestion_rutas y simulador para evitar keys duplicadas
# ─────────────────────────────────────────────
def filtrar_rutas_igloo(df, prefix: str):
    """
    Muestra un expander con filtros opcionales y devuelve el DataFrame filtrado.
    Usar con un prefix único por módulo:
      - consulta_ruta  → "ig_cons"
      - gestion ver    → "ig_ver"
      - gestion del    → "ig_del"
      - gestion edit   → "ig_ed"
      - simulador      → "ig_sim"
    """
    import streamlit as st

    with st.expander("🔎 Filtros de búsqueda (opcional)", expanded=False):
        fc1, fc2, fc3, fc4, fc5 = st.columns(5)
        tipos_disp    = ["Todos"] + sorted(df["Tipo"].dropna().unique().tolist()) if "Tipo" in df.columns else ["Todos"]
        clientes_disp = ["Todos"] + sorted(df["Cliente"].dropna().astype(str).unique().tolist()) if "Cliente" in df.columns else ["Todos"]
        filtro_tipo    = fc1.selectbox("Tipo",              tipos_disp,    key=f"{prefix}_ftipo")
        filtro_cliente = fc2.selectbox("Cliente",           clientes_disp, key=f"{prefix}_fcli")
        filtro_origen  = fc3.text_input("Origen contiene",                 key=f"{prefix}_forig")
        filtro_destino = fc4.text_input("Destino contiene",                key=f"{prefix}_fdest")
        filtro_id      = fc5.text_input("ID Ruta", placeholder="IG000001", key=f"{prefix}_fid")

    out = df.copy()
    if filtro_tipo    != "Todos": out = out[out["Tipo"].astype(str) == filtro_tipo]
    if filtro_cliente != "Todos": out = out[out["Cliente"].astype(str) == filtro_cliente]
    if filtro_origen.strip():     out = out[out["Origen"].astype(str).str.upper().str.contains(filtro_origen.strip().upper(), na=False)]
    if filtro_destino.strip():    out = out[out["Destino"].astype(str).str.upper().str.contains(filtro_destino.strip().upper(), na=False)]
    if filtro_id.strip():         out = out[out["ID_Ruta"].astype(str).str.upper().str.contains(filtro_id.strip().upper(), na=False)]
    return out


def label_ruta_igloo(row) -> str:
    """
    Formatea una fila de ruta para selectboxes.
    Resultado: "IG000001 | 2026-01-15 | IMPORTACION | CLIENTE | Origen → Destino"
    """
    fecha = str(row.get("Fecha", ""))[:10]
    return (
        f"{row.get('ID_Ruta', '')} | {fecha} | "
        f"{row.get('Tipo', '')} | {row.get('Cliente', '')} | "
        f"{row.get('Origen', '')} → {row.get('Destino', '')}"
    )
