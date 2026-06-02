"""
captura_rutas.py – Set Logis Plus  (final)
Base: v2 (estructura y flujo original dentro del form).
Agregados:
  · Modalidad de cobro americana: Desglosada (CXM Flete × Miles Load + CXM Fuel × Short Miles)
                                   o Flat (tarifa total directa)
  · Extras / Otros Conceptos: igual que Lincoln — monto + checkbox "¿Se cobra al cliente?"
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
            step=1.0, format="%.2f", key="sl_cruce_c")
        valores["Cruce Propio Vacio"] = cr2.number_input(
            "Cruce Propio Vacío", value=float(valores.get("Cruce Propio Vacio", 50.00)),
            step=1.0, format="%.2f", key="sl_cruce_v")

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
            ex_.metric("Extras (cliente)", f"${r['Extras_Ingreso']:,.2f}")
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
        alert("error", "⚠️ Supabase no configurado. Verifica tu conexión.")
        return

    u              = current_user() or {}
    user_id        = u.get("id") or u.get("sub") or ""
    nombre_usuario = _get_profile_name(user_id) or u.get("email") or "Desconocido"

    st.session_state.setdefault("sl_resultado", None)
    st.session_state.setdefault("sl_datos", {})

    valores = cargar_datos_generales()
    valores = _panel_datos_generales(valores)
    tc      = safe(valores.get("Tipo de Cambio USD/MXP", 18.50))

    divider()
    section_header("🛣️", "Nueva Ruta")

    with st.form("sl_captura_ruta", clear_on_submit=False):

        # ── 1. INFORMACIÓN GENERAL ────────────────────────────────────────────
        st.markdown("### 📋 Información General")
        g1, g2, g3, g4 = st.columns(4)
        fecha     = g1.date_input("📅 Fecha",  value=datetime.today(), key="sl_fecha")
        tipo_ruta = g2.selectbox("🗺️ Tipo",   TIPOS_RUTA,             key="sl_tipo")
        modo      = g3.selectbox("🚛 Modo",   ["Sencillo", "Team"],   key="sl_modo")
        cliente   = g4.text_input("👤 Cliente", key="sl_cliente",
                                   placeholder="NOMBRE DEL CLIENTE",
                                   disabled=(tipo_ruta == "Empty"))

        es_empty  = tipo_ruta == "Empty"
        aplica_mx = tiene_mx(tipo_ruta)

        st.caption(
            f"📌 Dirección: **{direccion_label(tipo_ruta)}**  ·  "
            f"Tramo MX: **{'Sí' if aplica_mx else 'No'}**"
        )

        # ── 2. RUTA AMERICANA ─────────────────────────────────────────────────
        divider()
        st.markdown("### 🇺🇸 Ruta Americana")

        ru1, ru2 = st.columns(2)
        origen_usa  = ru1.text_input("📍 Origen",  key="sl_ori",  placeholder="CIUDAD, ESTADO")
        destino_usa = ru2.text_input("📍 Destino", key="sl_dest", placeholder="CIUDAD, ESTADO")

        m1, m2, m3 = st.columns(3)
        miles_load  = m1.number_input("🛣️ Miles Load",  min_value=0.0, step=10.0, key="sl_ml")
        short_miles = m2.number_input("🔀 Short Miles",  min_value=0.0, step=1.0,  key="sl_sm")
        miles_empty = m3.number_input("⚪ Miles Empty",  min_value=0.0, step=10.0, key="sl_me")

        # Modalidad de cobro
        divider()
        st.markdown("**💵 Tarifa Americana**")
        mod1, mod2 = st.columns([1, 3])
        modalidad = mod1.radio("Modalidad", ["Desglosada", "Flat"],
                                horizontal=False, key="sl_modalidad",
                                disabled=es_empty)

        if modalidad == "Desglosada":
            td1, td2, td3 = mod2.columns(3)
            moneda_flete  = td1.selectbox("💱 Moneda", ["USD", "MXP"],
                                           key="sl_mon_flete", disabled=es_empty)
            cxm_flete_cap = td2.number_input("CXM Flete ($/mi)", min_value=0.0,
                                              step=0.001, format="%.4f",
                                              key="sl_cxm_flete", disabled=es_empty)
            cxm_fuel_cap  = td3.number_input("CXM Fuel ($/mi)", min_value=0.0,
                                              step=0.001, format="%.4f",
                                              key="sl_cxm_fuel", disabled=es_empty)
            flete_flat_cap = 0.0
            if not es_empty:
                preview = (safe(cxm_flete_cap) * safe(miles_load) +
                           safe(cxm_fuel_cap)  * safe(short_miles))
                mod2.caption(
                    f"Vista previa: CXM Flete ${safe(cxm_flete_cap):.4f} × {miles_load:.0f} mi"
                    f" + CXM Fuel ${safe(cxm_fuel_cap):.4f} × {short_miles:.0f} mi"
                    f" = **${preview:,.2f}**"
                )
        else:
            tf1, tf2 = mod2.columns(2)
            moneda_flete   = tf1.selectbox("💱 Moneda", ["USD", "MXP"],
                                            key="sl_mon_flete", disabled=es_empty)
            flete_flat_cap = tf2.number_input("Tarifa Total (Flat)", min_value=0.0,
                                               step=50.0, key="sl_flete_flat",
                                               disabled=es_empty)
            cxm_flete_cap = cxm_fuel_cap = 0.0

        # ── 3. CRUCE FRONTERIZO ───────────────────────────────────────────────
        divider()
        st.markdown("### 🛂 Cruce Fronterizo")

        incluye_cruce = st.checkbox("¿Incluye cruce?", key="sl_incl_cruce",
                                     value=not es_empty, disabled=es_empty)

        if incluye_cruce and not es_empty:
            crx1, crx2, crx3 = st.columns(3)
            tipo_cruce   = crx1.selectbox("Tipo de Cruce", ["Propio", "Externo"],
                                           key="sl_tcruce")
            tipo_carga_c = crx2.selectbox("Carga del cruce", ["Cargado", "Vacío"],
                                           key="sl_tcarga_c")
            mon_ing_cruce = crx3.selectbox("💱 Moneda Ingreso", ["USD", "MXP"],
                                            key="sl_mon_ing_cruce")

            ci1, ci2 = st.columns(2)
            ingreso_cruce_raw = ci1.number_input("💵 Ingreso Cruce", min_value=0.0,
                                                  step=10.0, key="sl_ing_cruce")

            if tipo_cruce == "Externo":
                mon_costo_cruce = ci2.selectbox("💱 Moneda Costo", ["USD", "MXP"],
                                                 key="sl_mon_costo_cruce")
                costo_cruce_raw = st.number_input("💸 Costo Cruce Externo", min_value=0.0,
                                                   step=10.0, key="sl_costo_cruce")
            else:
                mon_costo_cruce = "USD"
                costo_cruce_raw = 0.0
                key_cfg  = "Cruce Propio Cargado" if tipo_carga_c == "Cargado" else "Cruce Propio Vacio"
                costo_cfg = safe(valores.get(key_cfg, 80.0))
                st.caption(f"ℹ️ Costo cruce propio configurado: **${costo_cfg:,.2f} USD**")

            if mon_ing_cruce == "MXP":
                st.caption(f"ℹ️ Ingreso cruce en USD: **${ingreso_cruce_raw / tc:,.2f}**")
        else:
            tipo_cruce        = "Sin cruce"
            tipo_carga_c      = "Cargado"
            mon_ing_cruce     = "USD"
            ingreso_cruce_raw = 0.0
            mon_costo_cruce   = "USD"
            costo_cruce_raw   = 0.0

        # ── 4. RUTA MX (solo D2D) ─────────────────────────────────────────────
        if aplica_mx:
            divider()
            st.markdown("### 🇲🇽 Ruta México (Externo)")

            mx_r1, mx_r2 = st.columns(2)
            origen_mx  = mx_r1.text_input("📍 Origen MX",  key="sl_ori_mx",
                                            placeholder="CIUDAD, ESTADO")
            destino_mx = mx_r2.text_input("📍 Destino MX", key="sl_dest_mx",
                                            placeholder="CIUDAD, ESTADO")

            mx1, mx2, mx3, mx4 = st.columns(4)
            mon_ing_mx     = mx1.selectbox("💱 Moneda Ingreso", ["USD", "MXP"],
                                            key="sl_mon_ing_mx")
            ingreso_mx_raw = mx2.number_input("💵 Ingreso MX", min_value=0.0,
                                               step=50.0, key="sl_ing_mx")
            mon_costo_mx   = mx3.selectbox("💱 Moneda Costo",  ["USD", "MXP"],
                                            key="sl_mon_costo_mx")
            costo_mx_raw   = mx4.number_input("💸 Costo MX", min_value=0.0,
                                               step=50.0, key="sl_costo_mx")

            if mon_ing_mx == "MXP" or mon_costo_mx == "MXP":
                st.caption(
                    f"ℹ️ Equivalente USD — "
                    f"Ingreso: **${ingreso_mx_raw / tc if mon_ing_mx == 'MXP' else ingreso_mx_raw:,.2f}**  ·  "
                    f"Costo: **${costo_mx_raw / tc if mon_costo_mx == 'MXP' else costo_mx_raw:,.2f}**"
                )
        else:
            origen_mx = destino_mx = ""
            mon_ing_mx = mon_costo_mx = "USD"
            ingreso_mx_raw = costo_mx_raw = 0.0

        # ── 5. EXTRAS / OTROS CONCEPTOS ───────────────────────────────────────
        divider()
        st.markdown("### ➕ Extras / Otros Conceptos")
        st.caption("Captura el monto y marca ✓ si se cobra al cliente (suma a ingreso). Sin monto = ignorado.")

        otros_cargos: dict[str, float] = {}
        otros_pagados: dict[str, bool] = {}

        for i in range(0, len(EXTRAS_USA), 2):
            col_a, col_b = st.columns(2)
            for col, idx in [(col_a, i), (col_b, i + 1)]:
                if idx >= len(EXTRAS_USA):
                    break
                extra = EXTRAS_USA[idx]
                with col:
                    ex1, ex2 = st.columns([3, 1])
                    monto  = ex1.number_input(extra, min_value=0.0, step=10.0,
                                              key=f"sl_ex_m_{idx}")
                    cobrado = ex2.checkbox("cobra", key=f"sl_ex_p_{idx}",
                                           value=True,
                                           help="¿Se cobra al cliente?")
                    if monto > 0:
                        otros_cargos[extra]  = monto
                        otros_pagados[extra] = cobrado

        # ── 6. COSTO INDIRECTO ────────────────────────────────────────────────
        divider()
        st.markdown("### 📉 Costo Indirecto")
        ci_col, _ = st.columns([1, 2])
        modo_ci = ci_col.radio("Método", ["CXM", "Porcentaje"],
                                horizontal=True, key="sl_modo_ci")
        st.caption(
            f"CXM configurado: **${safe(valores.get('CXM Indirecto', 0.10)):.3f}/mi**  ·  "
            f"% configurado: **{safe(valores.get('% Costo Indirecto', 0.09)) * 100:.1f}%**"
        )

        # ── CALCULAR ──────────────────────────────────────────────────────────
        divider()
        calcular = st.form_submit_button(
            "🧮 Calcular Ruta", type="primary", use_container_width=True
        )

    # ── Lógica post-form ──────────────────────────────────────────────────────
    if calcular:
        errores = []
        ruta_usa = f"{normalizar(origen_usa)} - {normalizar(destino_usa)}"

        if not origen_usa.strip() or not destino_usa.strip():
            errores.append("⚠️ Ingresa origen y destino de la ruta USA.")
        if not es_empty and not cliente.strip():
            errores.append("⚠️ Ingresa el cliente.")
        if not es_empty and miles_load <= 0 and short_miles <= 0:
            errores.append("⚠️ Ingresa al menos Miles Load o Short Miles.")
        if es_empty and miles_empty <= 0:
            errores.append("⚠️ Las rutas Empty requieren Miles Empty.")

        if errores:
            for e in errores:
                st.error(e)
        else:
            # Tarifa americana según modalidad
            if es_empty:
                flete_usd = fuel_usd = 0.0
            elif modalidad == "Desglosada":
                flete_raw = safe(cxm_flete_cap) * safe(miles_load)
                fuel_raw  = safe(cxm_fuel_cap)  * safe(short_miles)
                flete_usd = a_usd(flete_raw, moneda_flete, tc)
                fuel_usd  = a_usd(fuel_raw,  moneda_flete, tc)
            else:  # Flat
                flete_usd = a_usd(safe(flete_flat_cap), moneda_flete, tc)
                fuel_usd  = 0.0

            # Conversión a USD
            ingreso_cruce_u = a_usd(ingreso_cruce_raw, mon_ing_cruce,   tc)
            costo_cruce_u   = a_usd(costo_cruce_raw,   mon_costo_cruce, tc)
            ingreso_mx_u    = a_usd(ingreso_mx_raw,    mon_ing_mx,      tc)
            costo_mx_u      = a_usd(costo_mx_raw,      mon_costo_mx,    tc)

            # Extras
            # Cobrado al cliente → suma a ingreso (se pasa sumado en flete_usd)
            # No cobrado         → costo puro
            extras_ingreso   = sum(v for n, v in otros_cargos.items()
                                   if otros_pagados.get(n, True))
            extras_costo_puro = sum(v for n, v in otros_cargos.items()
                                    if not otros_pagados.get(n, True))

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
                tipo_cruce           = tipo_cruce,
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
                "origen_mx":        normalizar(origen_mx)  if aplica_mx else "",
                "destino_mx":       normalizar(destino_mx) if aplica_mx else "",
                "moneda_flete":     moneda_flete,
                "mon_ing_cruce":    mon_ing_cruce,
                "mon_costo_cruce":  mon_costo_cruce,
                "mon_ing_mx":       mon_ing_mx,
                "mon_costo_mx":     mon_costo_mx,
                "tipo_carga_cruce": tipo_carga_c if incluye_cruce and not es_empty else "",
                "incluye_cruce":    incluye_cruce and not es_empty,
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
                    f"Extra_{n.replace(' ', '_')}": v
                    for n, v in d.get("otros_cargos", {}).items()
                }
                extras_cobrado_db = {
                    f"Extra_{n.replace(' ', '_')}_Cobrado": v
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
                    **extras_cobrado_db,
                }

                fila_limpia = limpiar_fila_json(fila)
                supabase.table(TABLE_RUTAS).insert(fila_limpia).execute()

                alert("success", f"✅ Ruta **{d['id_ruta']}** guardada correctamente.")
                st.session_state["sl_resultado"] = None
                st.session_state["sl_datos"]     = {}

            except Exception as ex:
                alert("error", f"❌ Error al guardar: {ex}")
