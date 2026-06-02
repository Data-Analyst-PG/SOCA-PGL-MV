"""
captura_rutas.py – Set Logis Plus  (v4)
Flujo paso a paso igual que Lincoln.
Sin HTML inline — todo via ui/components.

Orden visual:
  1. Información General  (tipo, modo, modalidad, indirecto, fecha, cliente)
  2. Ruta Americana       (origen, destino, millas, tarifa desglosada/flat)
  3. Cruce Fronterizo     (aplica?, tipo, carga, monedas, ingreso, costo)
  4. Ruta México          (solo D2D: origen, destino, monedas, ingreso, costo)
  5. Extras / Otros       (igual que Lincoln: monto + checkbox cobrado al cliente)
  6. Costo Indirecto      (método CXM o Porcentaje)
  7. Botón Calcular

Selectores reactivos (tipo_ruta, aplica_cruce, tipo_cruce) están en session_state
y se actualizan con st.rerun() para controlar qué secciones aparecen.
"""

from __future__ import annotations

import re
from datetime import datetime

import streamlit as st

from services.supabase_client import get_supabase_client, current_user
from ui.components import section_header, alert, divider, kpi_row
from ._shared import (
    TABLE_RUTAS,
    TIPOS_RUTA,
    EXTRAS_USA,
    DEFAULTS,
    cargar_datos_generales,
    guardar_datos_generales,
    limpiar_fila_json,
    safe,
    calcular_ruta_setlogis,
    tiene_mx,
    direccion_label,
)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def normalizar(texto: str) -> str:
    if not texto:
        return ""
    texto = str(texto).upper().strip()
    texto = re.sub(r"\s+", " ", texto)
    texto = re.sub(r"\s*,\s*", ", ", texto)
    return texto


def a_usd(monto: float, moneda: str, tc: float) -> float:
    if moneda == "MXP":
        return monto / tc if tc > 0 else 0.0
    return monto


def _get_profile_name(user_id: str) -> str | None:
    sb = get_supabase_client()
    if sb is None or not user_id:
        return None
    try:
        res = sb.table("profiles").select("full_name").eq("id", user_id).maybe_single().execute()
        return (res.data or {}).get("full_name")
    except Exception:
        return None


def _generar_id(supabase) -> str:
    try:
        resp = supabase.table(TABLE_RUTAS).select("ID_Ruta").order("ID_Ruta", desc=True).limit(1).execute()
        if resp.data:
            ultimo = str(resp.data[0].get("ID_Ruta", "SL000000"))
            num = int(re.sub(r"\D", "", ultimo)[-6:]) + 1
        else:
            num = 1
        return f"SL{num:06d}"
    except Exception:
        import time
        return f"SL{int(time.time()) % 1000000:06d}"


# ─────────────────────────────────────────────
# PANEL DATOS GENERALES
# ─────────────────────────────────────────────
def _panel_datos_generales(valores: dict) -> dict:
    with st.expander("⚙️ Configuración de Parámetros", expanded=False):

        st.markdown("**Tarifas Owner Individual (USD/milla)**")
        c1, c2, c3 = st.columns(3)
        valores["PxM Owner Subidas"] = c1.number_input(
            "PxM Subidas", value=float(valores.get("PxM Owner Subidas", 1.60)),
            step=0.01, format="%.2f", key="sl_pxm_sub")
        valores["PxM Owner Bajadas"] = c2.number_input(
            "PxM Bajadas", value=float(valores.get("PxM Owner Bajadas", 1.40)),
            step=0.01, format="%.2f", key="sl_pxm_baj")
        valores["PxM Owner Vacio"] = c3.number_input(
            "PxM Vacío", value=float(valores.get("PxM Owner Vacio", 0.80)),
            step=0.01, format="%.2f", key="sl_pxm_vac")

        st.markdown("**Tarifas Owner Team (USD/milla)**")
        t1, t2, t3 = st.columns(3)
        valores["PxM Owner Subidas Team"] = t1.number_input(
            "PxM Subidas Team", value=float(valores.get("PxM Owner Subidas Team", 1.80)),
            step=0.01, format="%.2f", key="sl_pxm_sub_team")
        valores["PxM Owner Bajadas Team"] = t2.number_input(
            "PxM Bajadas Team", value=float(valores.get("PxM Owner Bajadas Team", 1.60)),
            step=0.01, format="%.2f", key="sl_pxm_baj_team")
        valores["PxM Owner Vacio Team"] = t3.number_input(
            "PxM Vacío Team", value=float(valores.get("PxM Owner Vacio Team", 0.90)),
            step=0.01, format="%.2f", key="sl_pxm_vac_team")

        st.markdown("**Cruce Propio (USD)**")
        cr1, cr2 = st.columns(2)
        valores["Cruce Propio Cargado"] = cr1.number_input(
            "Cruce Propio Cargado", value=float(valores.get("Cruce Propio Cargado", 80.00)),
            step=1.0, format="%.2f", key="sl_cruce_cfg_c")
        valores["Cruce Propio Vacio"] = cr2.number_input(
            "Cruce Propio Vacío", value=float(valores.get("Cruce Propio Vacio", 50.00)),
            step=1.0, format="%.2f", key="sl_cruce_cfg_v")

        st.markdown("**Tipo de Cambio y Costos Indirectos**")
        x1, x2, x3 = st.columns(3)
        valores["Tipo de Cambio USD/MXP"] = x1.number_input(
            "TC USD/MXP", value=float(valores.get("Tipo de Cambio USD/MXP", 18.50)),
            step=0.05, format="%.2f", key="sl_tc")
        valores["CXM Indirecto"] = x2.number_input(
            "CXM Indirecto ($/mi)", value=float(valores.get("CXM Indirecto", 0.10)),
            step=0.01, format="%.3f", key="sl_cxm_ind")
        valores["% Costo Indirecto"] = x3.number_input(
            "% Costo Indirecto", value=float(valores.get("% Costo Indirecto", 0.09)),
            min_value=0.0, max_value=1.0, step=0.005, format="%.3f", key="sl_pct_ind")

        if st.button("💾 Guardar Parámetros", key="sl_save_params"):
            guardar_datos_generales(valores)
            alert("success", "✅ Parámetros guardados correctamente.")

    return valores


# ─────────────────────────────────────────────
# RESUMEN DE RESULTADOS
# ─────────────────────────────────────────────
def _mostrar_resumen(r: dict) -> None:
    divider()
    section_header("📊", "Resultado de la Ruta")

    kpi_row([
        {"icono": "💵", "label": "Ingreso Global",
         "valor": f"${r['Ingreso_Global']:,.2f} USD",
         "sub": "Total ingresos", "color": "#1B2266"},
        {"icono": "🚛", "label": "Pago Owner",
         "valor": f"${r['Pago_Owner_Total']:,.2f} USD",
         "sub": f"${r['PxM_Cargado']:.2f}/mi carg · ${r['PxM_Vacio']:.2f}/mi vacío",
         "color": "#0369a1"},
        {"icono": "📈", "label": "Utilidad Bruta",
         "valor": f"${r['Utilidad_Bruta']:,.2f} USD",
         "sub": f"{r['Pct_Ut_Bruta']:.1f}% del ingreso",
         "color": "#16a34a" if r["Utilidad_Bruta"] >= 0 else "#dc2626"},
        {"icono": "🏆", "label": "Utilidad Neta",
         "valor": f"${r['Utilidad_Neta']:,.2f} USD",
         "sub": f"{r['Pct_Ut_Neta']:.1f}% del ingreso",
         "color": r["Color_Ut_Neta"]},
    ])

    with st.expander("📋 Detalle completo del cálculo", expanded=True):

        section_header("💰", "Ingresos")
        ia, ib, ic, id_ = st.columns(4)
        ia.metric("Flete USA",    f"${r['Flete_USA']:,.2f}")
        ib.metric("Fuel",         f"${r['Fuel']:,.2f}")
        ic.metric("Flete + Fuel", f"${r['Flete_Fuel']:,.2f}")
        id_.metric("Cruce",       f"${r['Ingreso_Cruce']:,.2f}")
        if r.get("Extras_Ingreso", 0) > 0:
            _, _, _, ex_ = st.columns(4)
            ex_.metric("Extras cliente", f"${r['Extras_Ingreso']:,.2f}")
        if r["Ingreso_MX"] > 0:
            _, _, _, mx_ = st.columns(4)
            mx_.metric("Ingreso MX", f"${r['Ingreso_MX']:,.2f}")

        divider()
        section_header("🛣️", "Millas")
        ma, mb, mc, md = st.columns(4)
        ma.metric("Miles Load",   f"{r['Miles_Load']:,.0f}")
        mb.metric("Short Miles",  f"{r['Short_Miles']:,.0f}")
        mc.metric("Miles Empty",  f"{r['Miles_Empty']:,.0f}")
        md.metric("Total Millas", f"{r['Millas_Totales']:,.0f}")

        divider()
        section_header("📉", "Costos Directos")
        ca, cb, cc, cd = st.columns(4)
        ca.metric("Owner Cargado", f"${r['Pago_Owner_Cargado']:,.2f}")
        cb.metric("Owner Vacío",   f"${r['Pago_Owner_Vacio']:,.2f}")
        cc.metric("Cruce",         f"${r['Costo_Cruce']:,.2f}")
        cd.metric("Ruta MX",       f"${r['Costo_MX']:,.2f}")
        if r.get("Extras_Costo", 0) > 0:
            _, _, _, exc_ = st.columns(4)
            exc_.metric("Extras (costo)", f"${r['Extras_Costo']:,.2f}")

        pct_dir_txt = f"{r['Pct_Costo_Directo']:.1f}% del ingreso (límite 85%)"
        if r["Color_Directo"] == "#16a34a":
            st.success(f"✅ Costos Directos: {pct_dir_txt}")
        else:
            st.error(f"🔴 Costos Directos: {pct_dir_txt} — EXCEDE EL LÍMITE")

        divider()
        section_header("📉", "Costos Indirectos")
        ci_a, ci_b = st.columns(2)
        ci_a.metric("Costo Indirecto", f"${r['Costo_Indirecto']:,.2f}")
        ci_b.metric("CXM aplicado",    f"${r['CXM_Indirecto']:.3f}/mi")

        pct_ind_txt = f"{r['Pct_Costo_Indirecto']:.1f}% del ingreso (límite 9%)"
        if r["Color_Indirecto"] == "#16a34a":
            st.success(f"✅ Costos Indirectos: {pct_ind_txt}")
        else:
            st.error(f"🔴 Costos Indirectos: {pct_ind_txt} — EXCEDE EL LÍMITE")

        divider()
        section_header("🏁", "Resumen Final")
        rf_a, rf_b, rf_c = st.columns(3)
        rf_a.metric("Costo Total",    f"${r['Costo_Total']:,.2f}")
        rf_b.metric("Utilidad Bruta", f"${r['Utilidad_Bruta']:,.2f}",
                    delta=f"{r['Pct_Ut_Bruta']:.1f}%")
        rf_c.metric("Utilidad Neta",  f"${r['Utilidad_Neta']:,.2f}",
                    delta=f"{r['Pct_Ut_Neta']:.1f}%",
                    delta_color="normal" if r["Utilidad_Neta"] >= 0 else "inverse")

        pct_n_txt = f"{r['Pct_Ut_Neta']:.1f}% del ingreso (mínimo 6%)"
        if r["Color_Ut_Neta"] == "#16a34a":
            st.success(f"✅ Utilidad Neta: {pct_n_txt}")
        else:
            st.error(f"🔴 Utilidad Neta: {pct_n_txt} — POR DEBAJO DEL MÍNIMO")


# ─────────────────────────────────────────────
# RENDER PRINCIPAL
# ─────────────────────────────────────────────
def render() -> None:
    supabase = get_supabase_client()
    if supabase is None:
        alert("error", "⚠️ Supabase no configurado.")
        return

    u              = current_user() or {}
    user_id        = u.get("id") or u.get("sub") or ""
    nombre_usuario = _get_profile_name(user_id) or u.get("email") or "Desconocido"

    # Session state
    st.session_state.setdefault("sl_resultado", None)
    st.session_state.setdefault("sl_datos", {})
    # Selectores reactivos en session_state
    st.session_state.setdefault("sl_tipo_ruta",     "NB")
    st.session_state.setdefault("sl_aplica_cruce",  True)
    st.session_state.setdefault("sl_tipo_cruce",    "Propio")
    st.session_state.setdefault("sl_tcarga_cruce",  "Cargado")
    st.session_state.setdefault("sl_modalidad",     "Desglosada")

    # Parámetros
    valores = cargar_datos_generales()
    valores = _panel_datos_generales(valores)
    tc      = safe(valores.get("Tipo de Cambio USD/MXP", 18.50))

    divider()
    section_header("🛣️", "Nueva Ruta")

    # ══════════════════════════════════════════════════════════════
    # SECCIÓN 1 — INFORMACIÓN GENERAL
    # ══════════════════════════════════════════════════════════════
    section_header("📋", "Información General")

    ig1, ig2, ig3, ig4 = st.columns(4)

    # Tipo de ruta — reactivo: al cambiar recarga la página
    tipo_ruta_sel = ig1.selectbox(
        "🗺️ Tipo de Ruta", TIPOS_RUTA,
        index=TIPOS_RUTA.index(st.session_state["sl_tipo_ruta"]),
        key="sl_tipo_ruta_sel",
    )
    if tipo_ruta_sel != st.session_state["sl_tipo_ruta"]:
        st.session_state["sl_tipo_ruta"] = tipo_ruta_sel
        # Resetear cruce si pasa a Empty
        if tipo_ruta_sel == "Empty":
            st.session_state["sl_aplica_cruce"] = False
        else:
            st.session_state["sl_aplica_cruce"] = True
        st.rerun()

    tipo_ruta = st.session_state["sl_tipo_ruta"]
    is_empty  = tipo_ruta == "Empty"
    aplica_mx = tiene_mx(tipo_ruta)

    modo      = ig2.selectbox("🚛 Modo", ["Sencillo", "Team"], key="sl_modo")
    modalidad_sel = ig3.selectbox("📐 Modalidad", ["Desglosada", "Flat"], key="sl_modalidad_sel",
                                   index=["Desglosada", "Flat"].index(st.session_state["sl_modalidad"]))
    if modalidad_sel != st.session_state["sl_modalidad"]:
        st.session_state["sl_modalidad"] = modalidad_sel
        st.rerun()
    modalidad = st.session_state["sl_modalidad"]

    modo_ci   = ig4.radio("📉 Indirecto", ["CXM", "Porcentaje"],
                           horizontal=True, key="sl_modo_ci")

    st.caption(
        f"📌 Dirección: **{direccion_label(tipo_ruta)}**  ·  "
        f"Tramo MX: **{'Sí' if aplica_mx else 'No'}**"
    )

    with st.form("sl_captura_ruta", clear_on_submit=False):

        # Fecha y cliente dentro del form
        fd1, fd2 = st.columns(2)
        fecha   = fd1.date_input("📅 Fecha", value=datetime.today(), key="sl_fecha")
        cliente = fd2.text_input("👤 Cliente", key="sl_cliente",
                                  placeholder="NOMBRE DEL CLIENTE",
                                  disabled=is_empty)

        # ── SECCIÓN 2 — RUTA AMERICANA ────────────────────────────────────────
        divider()
        section_header("🇺🇸", "Ruta Americana")

        ru1, ru2 = st.columns(2)
        origen_usa  = ru1.text_input("📍 Origen",  key="sl_ori",  placeholder="CIUDAD, ESTADO")
        destino_usa = ru2.text_input("📍 Destino", key="sl_dest", placeholder="CIUDAD, ESTADO")

        m1, m2, m3 = st.columns(3)
        miles_load  = m1.number_input("🛣️ Miles Load",  min_value=0.0, step=10.0, key="sl_ml")
        short_miles = m2.number_input("🔀 Short Miles",  min_value=0.0, step=1.0,  key="sl_sm")
        miles_empty = m3.number_input("⚪ Miles Empty",  min_value=0.0, step=10.0, key="sl_me")

        # Tarifa según modalidad
        divider()
        if modalidad == "Desglosada":
            section_header("💵", "Tarifa Americana — Desglosada")
            td1, td2, td3 = st.columns(3)
            moneda_flete  = td1.selectbox("💱 Moneda", ["USD", "MXP"], key="sl_mon_flete",
                                           disabled=is_empty)
            cxm_flete_cap = td2.number_input("CXM Flete ($/mi)", min_value=0.0,
                                              step=0.001, format="%.4f", key="sl_cxm_flete",
                                              disabled=is_empty)
            cxm_fuel_cap  = td3.number_input("CXM Fuel ($/mi)", min_value=0.0,
                                              step=0.001, format="%.4f", key="sl_cxm_fuel",
                                              disabled=is_empty)
            flete_flat_cap = 0.0
        else:
            section_header("💵", "Tarifa Americana — Flat")
            tf1, tf2 = st.columns(2)
            moneda_flete   = tf1.selectbox("💱 Moneda", ["USD", "MXP"], key="sl_mon_flete",
                                            disabled=is_empty)
            flete_flat_cap = tf2.number_input("Tarifa Total (Flat)", min_value=0.0,
                                               step=50.0, key="sl_flete_flat",
                                               disabled=is_empty)
            cxm_flete_cap = cxm_fuel_cap = 0.0

        # ── SECCIÓN 3 — CRUCE ─────────────────────────────────────────────────
        divider()
        section_header("🛂", "Cruce Fronterizo")

        # Checkbox aplica cruce — submit_button del form lo detecta correctamente
        # pero el rerun lo manejamos con un botón auxiliar FUERA del form más abajo.
        # Aquí lo mostramos como campo de lectura controlado por session_state.
        cr_a, cr_b, cr_c, cr_d = st.columns(4)
        aplica_cruce_form = cr_a.checkbox(
            "¿Incluye cruce?", key="sl_incl_cruce_form",
            value=st.session_state["sl_aplica_cruce"],
            disabled=is_empty,
        )
        tipo_cruce_form = cr_b.selectbox(
            "Tipo de Cruce", ["Propio", "Externo"], key="sl_tcruce_form",
            index=["Propio", "Externo"].index(st.session_state["sl_tipo_cruce"]),
            disabled=(not st.session_state["sl_aplica_cruce"] or is_empty),
        )
        tipo_carga_form = cr_c.selectbox(
            "Carga del cruce", ["Cargado", "Vacío"], key="sl_tcarga_form",
            index=["Cargado", "Vacío"].index(st.session_state["sl_tcarga_cruce"]),
            disabled=(not st.session_state["sl_aplica_cruce"] or is_empty),
        )
        mon_ing_cruce = cr_d.selectbox(
            "💱 Moneda Ingreso", ["USD", "MXP"], key="sl_mon_ing_cruce",
            disabled=(not st.session_state["sl_aplica_cruce"] or is_empty),
        )

        aplica_cruce_actual = st.session_state["sl_aplica_cruce"]
        tipo_cruce_actual   = st.session_state["sl_tipo_cruce"]

        ingreso_cruce_raw = 0.0
        mon_costo_cruce   = "USD"
        costo_cruce_raw   = 0.0

        if aplica_cruce_actual and not is_empty:
            cr_e, cr_f = st.columns(2)
            ingreso_cruce_raw = cr_e.number_input(
                "💵 Ingreso Cruce", min_value=0.0, step=10.0, key="sl_ing_cruce"
            )
            if tipo_cruce_actual == "Externo":
                cr_f_cols = st.columns(2)
                mon_costo_cruce = cr_f_cols[0].selectbox(
                    "💱 Moneda Costo Cruce", ["USD", "MXP"], key="sl_mon_costo_cruce"
                )
                costo_cruce_raw = cr_f_cols[1].number_input(
                    "💸 Costo Cruce", min_value=0.0, step=10.0, key="sl_costo_cruce"
                )
            else:
                key_cfg   = "Cruce Propio Cargado" if tipo_carga_form == "Cargado" else "Cruce Propio Vacio"
                costo_cfg = safe(valores.get(key_cfg, 80.0))
                st.caption(f"ℹ️ Costo cruce propio configurado: **${costo_cfg:,.2f} USD**")

        # ── SECCIÓN 4 — RUTA MX ───────────────────────────────────────────────
        if aplica_mx:
            divider()
            section_header("🇲🇽", "Ruta México (Externo)")

            mx_r1, mx_r2 = st.columns(2)
            origen_mx  = mx_r1.text_input("📍 Origen MX",  key="sl_ori_mx",
                                            placeholder="CIUDAD, ESTADO")
            destino_mx = mx_r2.text_input("📍 Destino MX", key="sl_dest_mx",
                                            placeholder="CIUDAD, ESTADO")

            mx1, mx2, mx3, mx4 = st.columns(4)
            mon_ing_mx     = mx1.selectbox("💱 Moneda Ingreso", ["USD", "MXP"], key="sl_mon_ing_mx")
            ingreso_mx_raw = mx2.number_input("💵 Ingreso MX", min_value=0.0, step=50.0, key="sl_ing_mx")
            mon_costo_mx   = mx3.selectbox("💱 Moneda Costo",  ["USD", "MXP"], key="sl_mon_costo_mx")
            costo_mx_raw   = mx4.number_input("💸 Costo MX",   min_value=0.0, step=50.0, key="sl_costo_mx")
        else:
            origen_mx = destino_mx = ""
            mon_ing_mx = mon_costo_mx = "USD"
            ingreso_mx_raw = costo_mx_raw = 0.0

        # ── SECCIÓN 5 — EXTRAS ────────────────────────────────────────────────
        divider()
        section_header("➕", "Extras / Otros Conceptos")

        otros_cargos: dict[str, float]  = {}
        otros_pagados: dict[str, bool]  = {}

        for i in range(0, len(EXTRAS_USA), 2):
            col_a, col_b = st.columns(2)
            for col, idx in [(col_a, i), (col_b, i + 1)]:
                if idx >= len(EXTRAS_USA):
                    break
                extra = EXTRAS_USA[idx]
                key_m = f"sl_ex_m_{idx}"
                key_p = f"sl_ex_p_{idx}"
                with col:
                    ex1, ex2 = st.columns([3, 1])
                    monto   = ex1.number_input(extra, min_value=0.0, step=10.0,
                                               key=key_m, label_visibility="visible")
                    pagado  = ex2.checkbox("cobra", key=key_p, value=False,
                                           help="¿Se cobra al cliente?")
                    if monto > 0:
                        otros_cargos[extra]  = monto
                        otros_pagados[extra] = pagado

        # ── SECCIÓN 6 — COSTO INDIRECTO ───────────────────────────────────────
        divider()
        section_header("📉", "Costo Indirecto")
        st.caption(
            f"CXM configurado: **${safe(valores.get('CXM Indirecto', 0.10)):.3f}/mi**  ·  "
            f"% configurado: **{safe(valores.get('% Costo Indirecto', 0.09))*100:.1f}%**"
        )

        # ── BOTÓN CALCULAR ────────────────────────────────────────────────────
        divider()
        calcular = st.form_submit_button(
            "🧮 Calcular Ruta", type="primary", use_container_width=True
        )

    # ── Botones reactivos FUERA del form ──────────────────────────────────────
    # Permiten actualizar session_state y recargar el formulario
    col_r1, col_r2, col_r3 = st.columns(3)
    with col_r1:
        if st.button("🔄 Aplicar cambios de cruce / tipo", key="sl_btn_cruce_reload",
                     help="Presiona aquí después de cambiar Tipo de Cruce o si incluye cruce"):
            st.session_state["sl_aplica_cruce"] = aplica_cruce_form
            st.session_state["sl_tipo_cruce"]   = tipo_cruce_form
            st.session_state["sl_tcarga_cruce"] = tipo_carga_form
            st.rerun()

    # ── Lógica post-form ──────────────────────────────────────────────────────
    if calcular:
        # Sincronizar session_state con lo que está en el form al momento del submit
        st.session_state["sl_aplica_cruce"] = aplica_cruce_form
        st.session_state["sl_tipo_cruce"]   = tipo_cruce_form
        st.session_state["sl_tcarga_cruce"] = tipo_carga_form

        errores = []
        ruta_usa = f"{normalizar(origen_usa)} - {normalizar(destino_usa)}"

        if not origen_usa.strip() or not destino_usa.strip():
            errores.append("⚠️ Ingresa origen y destino de la ruta USA.")
        if not is_empty and not cliente.strip():
            errores.append("⚠️ Ingresa el cliente.")
        if not is_empty and miles_load <= 0 and short_miles <= 0:
            errores.append("⚠️ Ingresa al menos Miles Load o Short Miles.")
        if is_empty and miles_empty <= 0:
            errores.append("⚠️ Las rutas Empty requieren Miles Empty.")

        if errores:
            for e in errores:
                st.error(e)
        else:
            # Calcular tarifa americana
            if is_empty:
                flete_usd = fuel_usd = 0.0
            elif modalidad == "Desglosada":
                flete_raw = safe(cxm_flete_cap) * safe(miles_load)
                fuel_raw  = safe(cxm_fuel_cap)  * safe(short_miles)
                flete_usd = a_usd(flete_raw, moneda_flete, tc)
                fuel_usd  = a_usd(fuel_raw,  moneda_flete, tc)
            else:
                flete_usd = a_usd(safe(flete_flat_cap), moneda_flete, tc)
                fuel_usd  = 0.0

            # Convertir a USD
            ingreso_cruce_u = a_usd(ingreso_cruce_raw, mon_ing_cruce,   tc)
            costo_cruce_u   = a_usd(costo_cruce_raw,   mon_costo_cruce, tc)
            ingreso_mx_u    = a_usd(ingreso_mx_raw,    mon_ing_mx,      tc)
            costo_mx_u      = a_usd(costo_mx_raw,      mon_costo_mx,    tc)

            # Extras: ingreso = todos los que tienen monto
            #         costo   = solo los marcados como "cobrado al cliente" = False (pagado por empresa)
            extras_ingreso = sum(v for n, v in otros_cargos.items() if otros_pagados.get(n, False))
            extras_costo   = sum(v for n, v in otros_cargos.items() if otros_pagados.get(n, False))
            # Nota: en Lincoln "cobrado al cliente" = sí → suma a ingreso;
            # si no se cobra al cliente → es costo puro.
            extras_ingreso = sum(v for n, v in otros_cargos.items() if otros_pagados.get(n, False))
            extras_costo_puro = sum(v for n, v in otros_cargos.items() if not otros_pagados.get(n, False))

            tipo_cruce_calc = (
                "Sin cruce" if (not aplica_cruce_form or is_empty) else tipo_cruce_form
            )

            resultado = calcular_ruta_setlogis(
                tipo_ruta            = tipo_ruta,
                modo                 = modo,
                ruta_usa             = ruta_usa,
                cliente              = normalizar(cliente),
                miles_load           = miles_load,
                miles_empty          = miles_empty,
                short_miles          = short_miles,
                flete_usa            = flete_usd + extras_ingreso,
                fuel                 = fuel_usd,
                tipo_cruce           = tipo_cruce_calc,
                ingreso_cruce        = ingreso_cruce_u,
                costo_cruce_externo  = costo_cruce_u,
                ingreso_mx           = ingreso_mx_u,
                costo_mx             = costo_mx_u,
                extras_costo         = extras_costo_puro,
                modo_costo_indirecto = modo_ci,
                valores              = valores,
            )

            resultado["Modalidad"]      = modalidad
            resultado["CXM_Flete_Cap"]  = safe(cxm_flete_cap) if modalidad == "Desglosada" else 0.0
            resultado["CXM_Fuel_Cap"]   = safe(cxm_fuel_cap)  if modalidad == "Desglosada" else 0.0
            resultado["Flete_Flat"]     = flete_usd            if modalidad == "Flat"        else 0.0
            resultado["Extras_Ingreso"] = extras_ingreso
            resultado["Extras_Costo"]   = extras_costo_puro

            id_ruta = _generar_id(supabase)

            st.session_state["sl_resultado"] = resultado
            st.session_state["sl_datos"] = {
                "id_ruta":          id_ruta,
                "fecha":            str(fecha),
                "usuario":          nombre_usuario,
                "origen_mx":        normalizar(origen_mx) if aplica_mx else "",
                "destino_mx":       normalizar(destino_mx) if aplica_mx else "",
                "moneda_flete":     moneda_flete,
                "mon_ing_cruce":    mon_ing_cruce,
                "mon_costo_cruce":  mon_costo_cruce,
                "mon_ing_mx":       mon_ing_mx,
                "mon_costo_mx":     mon_costo_mx,
                "tipo_carga_cruce": tipo_carga_form if aplica_cruce_form and not is_empty else "",
                "incluye_cruce":    aplica_cruce_form and not is_empty,
                "otros_cargos":     otros_cargos,
                "otros_pagados":    otros_pagados,
            }
            alert("success", "✅ Ruta calculada correctamente.")

    # ── Mostrar resultado ─────────────────────────────────────────────────────
    if st.session_state.get("sl_resultado"):
        _mostrar_resumen(st.session_state["sl_resultado"])

        divider()
        if st.button("💾 Guardar en Base de Datos", key="sl_guardar",
                     type="primary", use_container_width=True):
            try:
                r = st.session_state["sl_resultado"]
                d = st.session_state["sl_datos"]

                extras_db = {
                    f"Extra_{n.replace(' ','_')}": v
                    for n, v in d.get("otros_cargos", {}).items()
                }
                extras_pagados_db = {
                    f"Extra_{n.replace(' ','_')}_Cobrado": v
                    for n, v in d.get("otros_pagados", {}).items()
                }

                fila = {
                    "ID_Ruta":              d["id_ruta"],
                    "Fecha":                d["fecha"],
                    "Usuario":              d["usuario"],
                    "Tipo_Viaje":           r["Tipo_Viaje"],
                    "Modo":                 r["Modo"],
                    "Direccion":            r["Direccion"],
                    "Modalidad":            r["Modalidad"],
                    "Cliente":              r["Cliente"],
                    "Ruta_USA":             r["Ruta_USA"],
                    "Origen_MX":            d["origen_mx"],
                    "Destino_MX":           d["destino_mx"],
                    "Moneda_Flete":         d["moneda_flete"],
                    "Moneda_Ingreso_Cruce": d["mon_ing_cruce"],
                    "Moneda_Costo_Cruce":   d["mon_costo_cruce"],
                    "Moneda_Ingreso_MX":    d["mon_ing_mx"],
                    "Moneda_Costo_MX":      d["mon_costo_mx"],
                    "Tipo_Carga_Cruce":     d["tipo_carga_cruce"],
                    "Incluye_Cruce":        d["incluye_cruce"],
                    "Miles_Load":           r["Miles_Load"],
                    "Miles_Empty":          r["Miles_Empty"],
                    "Short_Miles":          r["Short_Miles"],
                    "Millas_Totales":       r["Millas_Totales"],
                    "CXM_Flete":            r["CXM_Flete_Cap"],
                    "CXM_Fuel":             r["CXM_Fuel_Cap"],
                    "Flete_Flat":           r["Flete_Flat"],
                    "Flete_USA":            r["Flete_USA"],
                    "Fuel":                 r["Fuel"],
                    "Flete_Fuel":           r["Flete_Fuel"],
                    "Ingreso_Cruce":        r["Ingreso_Cruce"],
                    "Tipo_Cruce":           r["Tipo_Cruce"],
                    "Ingreso_MX":           r["Ingreso_MX"],
                    "Extras_Ingreso":       r["Extras_Ingreso"],
                    "Extras_Costo":         r["Extras_Costo"],
                    "Ingreso_Global":       r["Ingreso_Global"],
                    "PxM_Cargado":          r["PxM_Cargado"],
                    "PxM_Vacio":            r["PxM_Vacio"],
                    "Pago_Owner_Cargado":   r["Pago_Owner_Cargado"],
                    "Pago_Owner_Vacio":     r["Pago_Owner_Vacio"],
                    "Pago_Owner_Total":     r["Pago_Owner_Total"],
                    "Costo_Cruce":          r["Costo_Cruce"],
                    "Costo_MX":             r["Costo_MX"],
                    "Costo_Directo":        r["Costo_Directo"],
                    "Costo_Indirecto":      r["Costo_Indirecto"],
                    "Costo_Total":          r["Costo_Total"],
                    "Utilidad_Bruta":       r["Utilidad_Bruta"],
                    "Utilidad_Neta":        r["Utilidad_Neta"],
                    "Pct_Costo_Directo":    r["Pct_Costo_Directo"],
                    "Pct_Costo_Indirecto":  r["Pct_Costo_Indirecto"],
                    "Pct_Ut_Bruta":         r["Pct_Ut_Bruta"],
                    "Pct_Ut_Neta":          r["Pct_Ut_Neta"],
                    "TC_USD_MXP":           r["TC"],
                    **extras_db,
                    **extras_pagados_db,
                }

                fila_limpia = limpiar_fila_json(fila)
                supabase.table(TABLE_RUTAS).insert(fila_limpia).execute()

                alert("success", f"✅ Ruta **{d['id_ruta']}** guardada correctamente.")
                st.session_state["sl_resultado"] = None
                st.session_state["sl_datos"]     = {}

            except Exception as ex:
                alert("error", f"❌ Error al guardar: {ex}")
