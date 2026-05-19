from ui.components import section_header, alert, divider
"""
captura_rutas.py  –  Set Freight LLC
Formulario de captura de ruta nueva con ingresos y costos por concepto.
"""

import streamlit as st
from datetime import datetime

from services.supabase_client import get_supabase_client, current_user
from ._shared import (
    TABLE_RUTAS, TIPOS_SERVICIO, DEFAULTS,
    CONCEPTOS_INGRESO, CONCEPTOS_COSTO,
    calcular_ruta, generar_id_ruta, limpiar_fila, safe,
)


def _get_sucursal_id() -> str | None:
    """Obtiene la sucursal_id del usuario logueado desde sf_usuarios."""
    u = current_user() or {}
    uid = u.get("id") or u.get("sub")
    if not uid:
        return None
    sb = get_supabase_client()
    if sb is None:
        return None
    try:
        res = sb.table("sf_usuarios").select("sucursal_id").eq("user_id", uid).maybe_single().execute()
        return (res.data or {}).get("sucursal_id")
    except Exception:
        return None


def render():
    st.title("🛣️ Captura de Ruta — Set Freight LLC")

    sb = get_supabase_client()
    if sb is None:
        alert("warn", "⚠️ Supabase no configurado.")
        return

    sucursal_id = _get_sucursal_id()
    if not sucursal_id:
        alert("error", "❌ Tu usuario no está asignado a una sucursal de Set Freight. Contacta al administrador.")
        return

    u = current_user() or {}
    uid = u.get("id") or u.get("sub")

    # ── Datos generales ───────────────────────
    with st.expander("⚙️ Parámetros globales", expanded=False):
        c1, c2 = st.columns(2)
        tc  = c1.number_input("Tipo de Cambio USD/MXP", value=DEFAULTS["Tipo de Cambio USD/MXP"], step=0.01, key="sf_tc")
        pct = c2.number_input("% Costo Indirecto", value=DEFAULTS["% Costo Indirecto"],
                              min_value=0.0, max_value=1.0, step=0.005, format="%.3f", key="sf_pct_ci")

    # ── Identificación de ruta ─────────────────
    section_header("▸", "Datos de la ruta")
    c1, c2, c3 = st.columns(3)
    tipo    = c1.selectbox("Tipo de servicio", TIPOS_SERVICIO, key="sf_tipo")
    origen  = c2.text_input("Origen",  placeholder="ej. HOUSTON, TX",     key="sf_origen")
    destino = c3.text_input("Destino", placeholder="ej. AMOZOC, PUE",     key="sf_destino")

    c4, c5, c6 = st.columns(3)
    millas_carg = c4.number_input("Millas cargado", min_value=0.0, step=1.0, key="sf_mi_c")
    millas_vac  = c5.number_input("Millas vacío",   min_value=0.0, step=1.0, key="sf_mi_v")
    viajes_mes  = c6.number_input("Viajes/mes",     min_value=1,   step=1,   key="sf_viajes", value=1)

    # ── Ingresos ──────────────────────────────
    section_header("▸", "Ingresos (USD)")
    ing_vals = {}
    cols_ing = st.columns(len(CONCEPTOS_INGRESO))
    for i, (label, campo) in enumerate(CONCEPTOS_INGRESO.items()):
        ing_vals[campo] = cols_ing[i].number_input(label, min_value=0.0, step=0.01,
                                                    format="%.2f", key=f"sf_ing_{campo}")

    # ── Costos directos ───────────────────────
    section_header("▸", "Costos directos (USD)")
    cst_vals = {}
    cols_c = st.columns(4)
    for i, (label, campo) in enumerate(CONCEPTOS_COSTO.items()):
        cst_vals[campo] = cols_c[i % 4].number_input(label, min_value=0.0, step=0.01,
                                                      format="%.2f", key=f"sf_cst_{campo}")

    # ── Resultado en tiempo real ───────────────
    row_preview = {**ing_vals, **cst_vals}
    r = calcular_ruta(row_preview, pct_indirecto=pct)

    divider()
    section_header("📊", "Resultado")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Ingreso total",    f"${r['ingreso_total']:,.2f}")
    m1.metric("Costo directo",    f"${r['costo_directo']:,.2f}")
    m2.metric("Costo indirecto",  f"${r['costo_indirecto']:,.2f}")
    color_b = "normal" if r["ut_bruta"] >= 0 else "inverse"
    m2.metric("Utilidad bruta",   f"${r['ut_bruta']:,.2f}", delta_color=color_b)
    color_n = "normal" if r["ut_neta"] >= 0 else "inverse"
    m3.metric("Utilidad neta",    f"${r['ut_neta']:,.2f}",  delta_color=color_n)
    m3.metric("% Ut. neta",       f"{r['pct_ut_neta']:.2%}")
    m4.metric("% Ut. bruta",      f"{r['pct_ut_bruta']:.2%}")
    m4.metric("% Costo directo",  f"{r['pct_cd']:.2%}")

    notas = st.text_area("Notas internas", key="sf_notas", height=80)

    # ── Guardar ───────────────────────────────
    if st.button("💾 Guardar ruta", type="primary", key="sf_guardar"):
        if not origen.strip() or not destino.strip():
            alert("error", "❌ Ingresa origen y destino.")
            return

        fila = limpiar_fila({
            "id_ruta":        generar_id_ruta(),
            "sucursal_id":    sucursal_id,
            "creado_por":     uid,
            "tipo_servicio":  tipo,
            "ruta_origen":    origen.strip().upper(),
            "ruta_destino":   destino.strip().upper(),
            "millas_cargado": millas_carg,
            "millas_vacio":   millas_vac,
            "tipo_cambio":    tc,
            "pct_indirecto":  pct,
            "viajes_mes":     viajes_mes,
            "notas":          notas.strip() or None,
            **ing_vals,
            **cst_vals,
        })

        try:
            sb.table(TABLE_RUTAS).insert(fila).execute()
            st.success(f"✅ Ruta guardada — {fila['id_ruta']}")
            st.cache_data.clear()
        except Exception as e:
            st.error(f"❌ Error al guardar: {e}")
