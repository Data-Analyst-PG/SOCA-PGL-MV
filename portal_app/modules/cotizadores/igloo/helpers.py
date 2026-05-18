from ui.components import section_header, alert, divider
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
import pandas as pd
import numpy as np


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
    """Lee el CSV de datos generales y lo fusiona con DEFAULTS."""
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
                return {**DEFAULTS, **vals}
        except Exception:
            pass
    return DEFAULTS.copy()


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
TIPOS_CON_INDIRECTOS = ["IMPORTACION", "EXPORTACION", "DOM MEX", "VACIO"]


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
    tipo = (tipo or "").strip().upper()
    modo = (modo or "Operador")
    factor = 2 if modo == "Team" else 1

    if tipo == "IMPORTACION":
        pago_km = safe_float(valores.get("Pago x km IMPORTACION", 2.10))
        sueldo = km * pago_km * factor
        bono = safe_float(valores.get("Bono ISR IMSS", 462.66)) * factor

    elif tipo == "EXPORTACION":
        pago_km = safe_float(valores.get("Pago x km EXPORTACION", 2.50))
        sueldo = km * pago_km * factor
        bono = safe_float(valores.get("Bono ISR IMSS", 462.66)) * factor

    elif tipo == "DOM MEX":
        if modo_pago_dom == "fijo":
            pago_km = 0.0
            sueldo = safe_float(valores.get("Pago fijo DOM MEX", 200.0)) * factor
        else:  # por km
            pago_km = safe_float(valores.get("Pago x km DOM MEX", 2.10))
            sueldo = km * pago_km * factor
        bono = safe_float(valores.get("Bono ISR IMSS", 462.66)) * factor

    elif tipo == "VACIO":
        pago_km = 0.0
        sueldo = safe_float(valores.get("Pago fijo VACIO", 200.0)) * factor
        bono = 0.0

    else:
        pago_km = 0.0
        sueldo = 0.0
        bono = 0.0

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
    rend_camion = safe_float(valores.get("Rendimiento Camion", 2.5), 2.5)
    rend_termo = safe_float(valores.get("Rendimiento Termo", 3.0), 3.0)
    costo_diesel = safe_float(valores.get("Costo Diesel", 24.0), 24.0)

    diesel_camion = (km / max(rend_camion, 0.0001)) * costo_diesel
    diesel_termo = horas_termo * rend_termo * costo_diesel
    return diesel_camion, diesel_termo


def calcular_extras(lavado_termo, movimiento_local, puntualidad_val,
                    pension, estancia, fianza_termo, renta_termo,
                    pistas_extra, stop, falso, gatas, accesorios, guias):
    """Suma todos los costos extras."""
    return sum(map(safe_number, [
        lavado_termo, movimiento_local, puntualidad_val, pension, estancia,
        fianza_termo, renta_termo, pistas_extra, stop, falso,
        gatas, accesorios, guias,
    ]))


def calcular_utilidades(ingreso_total: float, costo_total: float, tipo: str):
    """
    Retorna dict con:
      utilidad_bruta, costos_indirectos, utilidad_neta,
      porcentaje_bruta, porcentaje_neta
    """
    utilidad_bruta = ingreso_total - costo_total
    costos_ind = calcular_costos_indirectos(tipo, ingreso_total)
    utilidad_neta = utilidad_bruta - costos_ind
    pct_bruta = (utilidad_bruta / ingreso_total * 100) if ingreso_total else 0
    pct_neta = (utilidad_neta / ingreso_total * 100) if ingreso_total else 0

    return {
        "utilidad_bruta": utilidad_bruta,
        "costos_indirectos": costos_ind,
        "utilidad_neta": utilidad_neta,
        "porcentaje_bruta": pct_bruta,
        "porcentaje_neta": pct_neta,
    }


def calcular_utilidades_vuelta_redonda(rutas_seleccionadas: list):
    """
    Calcula utilidades para una vuelta redonda (simulador / programación).
    Aplica 35 % solo a las rutas que NO son VACÍO.
    """
    ingreso_total = sum(safe_number(r.get("Ingreso Total", 0)) for r in rutas_seleccionadas)
    costo_total = sum(safe_number(r.get("Costo_Total_Ruta", 0)) for r in rutas_seleccionadas)
    utilidad_bruta = ingreso_total - costo_total

    # Costos indirectos: solo de los tramos que califican
    costos_ind = 0.0
    for r in rutas_seleccionadas:
        tipo = str(r.get("Tipo", "")).strip().upper()
        ing = safe_number(r.get("Ingreso Total", 0))
        costos_ind += calcular_costos_indirectos(tipo, ing)

    utilidad_neta = utilidad_bruta - costos_ind
    pct_bruta = (utilidad_bruta / ingreso_total * 100) if ingreso_total else 0
    pct_neta = (utilidad_neta / ingreso_total * 100) if ingreso_total else 0

    return {
        "ingreso_total": ingreso_total,
        "costo_total": costo_total,
        "utilidad_bruta": utilidad_bruta,
        "costos_indirectos": costos_ind,
        "utilidad_neta": utilidad_neta,
        "porcentaje_bruta": pct_bruta,
        "porcentaje_neta": pct_neta,
    }


# ─────────────────────────────────────────────
# Mostrar resultados (reutilizable en st)
# ─────────────────────────────────────────────
def mostrar_resultados_utilidad(st_module, ingreso_total, costo_total,
                                 utilidad_bruta, costos_indirectos,
                                 utilidad_neta, pct_bruta, pct_neta,
                                 tipo: str = ""):
    """Muestra las métricas de utilidad con formato visual mejorado."""
    import streamlit as _st  # import local para que el helper no dependa de st a nivel módulo

    _st.markdown("---")

    # ── Encabezado con métricas modernas ──
    _st.markdown("""
    <div style="background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                padding: 1rem 1.25rem; border-radius: 10px; margin-bottom: 1rem;
                border-left: 4px solid #1B2266;">
        <h4 style="margin:0; color:#1B2266;">📊 Resumen de Utilidades</h4>
    </div>
    """, unsafe_allow_html=True)

    # Calcular porcentaje de costo directo
    pct_costo = (costo_total / ingreso_total * 100) if ingreso_total else 0
    
    # ✅ REGLA: Costo Directo VERDE si ≤50%, ROJO si >50%
    delta_color_costo = "normal" if pct_costo <= 50 else "inverse"
    
    # ✅ REGLA: Utilidad Bruta VERDE si ≥50%, ROJO si <50%
    delta_color_bruta = "normal" if pct_bruta >= 50 else "inverse"
    
    # ✅ REGLA: Utilidad Neta VERDE si ≥25%, ROJO si <25%
    color_neta = "#28a745" if pct_neta >= 15 else "#dc3545"
    color_bg = "#d4edda" if pct_neta >= 15 else "#f8d7da"

    col1, col2 = _st.columns(2)
    with col1:
        _st.metric("💰 Ingreso Total", f"${ingreso_total:,.2f}")
        _st.metric("📦 Costo Directo", f"${costo_total:,.2f}",
                   delta=f"{pct_costo:.1f}%",
                   delta_color=delta_color_costo)
    with col2:
        delta_bruta = f"{pct_bruta:.1f}%"
        delta_neta = f"{pct_neta:.1f}%"
        _st.metric("📈 Utilidad Bruta", f"${utilidad_bruta:,.2f}",
                    delta=delta_bruta,
                    delta_color=delta_color_bruta)
        label_ind = "Costos Indirectos (35%)" if costos_indirectos > 0 else "Costos Indirectos (0% — VACÍO)"
        _st.metric(f"🏢 {label_ind}", f"${costos_indirectos:,.2f}")

    # Tarjeta de utilidad neta destacada
    _st.markdown(f"""
    <div style="background:{color_bg}; border-left:5px solid {color_neta};
                padding:1rem 1.25rem; border-radius:8px; margin-top:0.5rem;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div>
                <span style="font-size:0.85rem; color:#555;">Utilidad Neta</span><br>
                <span style="font-size:1.5rem; font-weight:700; color:{color_neta};">
                    ${utilidad_neta:,.2f}
                </span>
            </div>
            <div style="text-align:right;">
                <span style="font-size:0.85rem; color:#555;">% Utilidad Neta</span><br>
                <span style="font-size:1.3rem; font-weight:700; color:{color_neta};">
                    {pct_neta:.2f}%
                </span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
