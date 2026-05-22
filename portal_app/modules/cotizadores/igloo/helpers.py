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
                                 tipo: str = "", tc_usd: float = 0.0):
    """
    Muestra las métricas de utilidad con formato visual mejorado.

    tc_usd: tipo de cambio activo. Si > 0, la tarifa sugerida también
            se muestra convertida a USD.
    """

    # ── Tarifa sugerida: costo = 50% del ingreso → ingreso = costo × 2 ──
    tarifa_mxp = costo_total * 2.0
    tarifa_usd = (tarifa_mxp / tc_usd) if tc_usd > 0 else 0.0

    # Texto auxiliar con equivalente en USD (solo si hay TC)
    usd_extra = (
        f"&nbsp;&nbsp;/&nbsp;&nbsp;USD ${tarifa_usd:,.2f}"
        if tc_usd > 0 else ""
    )

    # ── Banner de tarifa sugerida (HTML puro para evitar render literal) ──
    if tarifa_mxp > 0:
        if ingreso_total == 0:
            # Sin ingreso: banner amarillo prominente
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
            # Con ingreso: banner azul comparativo
            diff = ingreso_total - tarifa_mxp
            diff_pct = (diff / tarifa_mxp * 100) if tarifa_mxp else 0
            color_diff = "#059669" if diff >= 0 else "#dc2626"
            signo = "+" if diff >= 0 else ""
            icon = "✅" if diff >= 0 else "⚠️"
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

    section_header("📊", "Resumen de Utilidades")

    col1, col2 = st_module.columns(2)

    # ── Ingreso Total ─────────────────────────────────────────────────────
    with col1:
        nota_sin_ingreso = (
            f"<div style='font-size:0.75rem; color:#f59e0b; margin-top:4px;'>"
            f"⚠️ Sin ingreso — sugerida: MXP ${tarifa_mxp:,.2f}{usd_extra}"
            f"</div>"
            if ingreso_total == 0 and tarifa_mxp > 0
            else ""
        )
        st_module.markdown(
            f"""
            <div style='border-left:4px solid #059669; padding:12px 16px;
                        border-radius:8px; background:#f0fdf4; margin-bottom:12px;'>
                <div style='font-size:0.8rem; color:#6b7280;'>💰 Ingreso Total</div>
                <div style='font-size:2rem; font-weight:700; color:#1e3a5f;'>
                    ${ingreso_total:,.2f}
                </div>
                {nota_sin_ingreso}
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ── Costo Directo ─────────────────────────────────────────────────
        delta_costo = (costo_total / ingreso_total * 100) if ingreso_total else 0
        st_module.markdown(
            f"""
            <div style='border-left:4px solid #dc2626; padding:12px 16px;
                        border-radius:8px; background:#fef2f2; margin-bottom:12px;'>
                <div style='font-size:0.8rem; color:#6b7280;'>🧾 Costo Directo</div>
                <div style='font-size:2rem; font-weight:700; color:#1e3a5f;'>
                    ${costo_total:,.2f}
                </div>
                <div style='font-size:0.75rem; color:#dc2626; margin-top:4px;'>
                    ↑ {delta_costo:.1f}%
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        # ── Utilidad Bruta ────────────────────────────────────────────────
        color_bruta = "#059669" if utilidad_bruta >= 0 else "#dc2626"
        bg_bruta = "#f0fdf4" if utilidad_bruta >= 0 else "#fef2f2"
        signo_bruta = "↑" if utilidad_bruta >= 0 else "↓"
        st_module.markdown(
            f"""
            <div style='border-left:4px solid {color_bruta}; padding:12px 16px;
                        border-radius:8px; background:{bg_bruta}; margin-bottom:12px;'>
                <div style='font-size:0.8rem; color:#6b7280;'>📝 Utilidad Bruta</div>
                <div style='font-size:2rem; font-weight:700; color:#1e3a5f;'>
                    ${utilidad_bruta:,.2f}
                </div>
                <div style='font-size:0.75rem; color:{color_bruta}; margin-top:4px;'>
                    {signo_bruta} {pct_bruta:.1f}%
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ── Costos Indirectos ─────────────────────────────────────────────
        tipo_upper = (tipo or "").strip().upper()
        aplica_ind = tipo_upper in ("IMPORTACION", "EXPORTACION", "DOM MEX")
        label_ind = (
            "Costos Indirectos (35%)"
            if aplica_ind
            else "Costos Indirectos (N/A - Vacío)"
        )
        st_module.markdown(
            f"""
            <div style='border-left:4px solid #7c3aed; padding:12px 16px;
                        border-radius:8px; background:#faf5ff; margin-bottom:12px;'>
                <div style='font-size:0.8rem; color:#6b7280;'>🗂️ {label_ind}</div>
                <div style='font-size:2rem; font-weight:700; color:#1e3a5f;'>
                    ${costos_indirectos:,.2f}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ── Utilidad Neta (barra completa) ────────────────────────────────────
    color_neta = "#059669" if utilidad_neta >= 0 else "#dc2626"
    bg_neta = "#f0fdf4" if utilidad_neta >= 0 else "#fef2f2"
    st_module.markdown(
        f"""
        <div style='border:2px solid {color_neta}; padding:14px 20px;
                    border-radius:10px; background:{bg_neta};
                    display:flex; justify-content:space-between;
                    align-items:center; margin-top:4px;'>
            <div>
                <div style='font-size:0.8rem; color:#6b7280;'>Utilidad Neta</div>
                <div style='font-size:1.6rem; font-weight:800; color:{color_neta};'>
                    ${utilidad_neta:,.2f}
                </div>
            </div>
            <div style='text-align:right;'>
                <div style='font-size:0.8rem; color:#6b7280;'>% Utilidad Neta</div>
                <div style='font-size:1.4rem; font-weight:800; color:{color_neta};'>
                    {pct_neta:.2f}%
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
