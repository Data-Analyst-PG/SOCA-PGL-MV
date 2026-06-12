"""
captura_rutas.py – Set Logis Plus
Helpers de texto/conversión y generación de ID viven en _shared.py.
HTML de resultados delegado a ui/components (semaforos_ruta, desglose_ruta).
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from services.supabase_client import get_supabase_client, current_user
from ui.components import section_header, alert, divider, kpi_row, semaforos_ruta, desglose_ruta
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
    # helpers movidos desde este archivo a _shared:
    normalizar,
    a_usd,
    get_profile_name,
    generar_id_ruta,
)


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
            "Cruce Propio Cargado", value=float(valores.get("Cruce Propio Cargado", 80.0)),
            step=1.0, format="%.2f", key="sl_cruce_carg")
        valores["Cruce Propio Vacio"] = cr2.number_input(
            "Cruce Propio Vacío", value=float(valores.get("Cruce Propio Vacio", 50.0)),
            step=1.0, format="%.2f", key="sl_cruce_vac")

        st.markdown("**Tipo de Cambio y Costo Indirecto**")
        tc1, tc2, tc3 = st.columns(3)
        valores["Tipo de Cambio USD/MXP"] = tc1.number_input(
            "TC USD/MXP", value=float(valores.get("Tipo de Cambio USD/MXP", 18.50)),
            step=0.1, format="%.2f", key="sl_tc")
        valores["CXM Indirecto"] = tc2.number_input(
            "CXM Indirecto ($/mi)", value=float(valores.get("CXM Indirecto", 0.10)),
            step=0.01, format="%.4f", key="sl_cxm_ind")
        pct_display = float(valores.get("% Costo Indirecto", 0.09)) * 100
        pct_val = tc3.number_input(
            "% Costo Indirecto", value=pct_display,
            step=0.1, format="%.1f", key="sl_pct_ind")
        valores["% Costo Indirecto"] = pct_val / 100

        if st.button("💾 Guardar parámetros", key="sl_guardar_params"):
            guardar_datos_generales(valores)
            st.success("Parámetros guardados.")

    return valores


# ─────────────────────────────────────────────
# RESUMEN DE RESULTADOS
# ─────────────────────────────────────────────
def _mostrar_resumen(r: dict, modalidad: str, cxm_flete: float, cxm_fuel: float) -> None:
    section_header("📊", "Resultado del Cálculo")

    kpi_row([
        {"icono": "💰", "label": "Ingreso Global",   "valor": f"${r['Ingreso_Global']:,.2f}",  "sub": "USD", "color": "#1B2266"},
        {"icono": "📉", "label": "Costo Directo",    "valor": f"${r['Costo_Directo']:,.2f}",   "sub": f"{r['Pct_Costo_Directo']:.1f}%", "color": r.get("Color_Directo","#dc2626")},
        {"icono": "📊", "label": "Costo Indirecto",  "valor": f"${r['Costo_Indirecto']:,.2f}", "sub": f"{r['Pct_Costo_Indirecto']:.1f}%", "color": r.get("Color_Indirecto","#dc2626")},
        {"icono": "✅", "label": "Utilidad Neta",    "valor": f"${r['Utilidad_Neta']:,.2f}",   "sub": f"{r['Pct_Ut_Neta']:.1f}%", "color": r.get("Color_Ut_Neta","#dc2626")},
    ])

    if r.get("Fuel_Owner"):
        st.info(f"⛽ **Fuel pagado al Owner:** ${r.get('Pago_Fuel_Owner', 0):,.2f} USD — incluido en Costo Directo")

    divider()
    semaforos_ruta(r)
    divider()
    desglose_ruta(r, modalidad=modalidad, cxm_flete=cxm_flete, cxm_fuel=cxm_fuel)


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
    nombre_usuario = get_profile_name(user_id) or u.get("email") or "Desconocido"

    st.session_state.setdefault("sl_resultado", None)
    st.session_state.setdefault("sl_datos", {})
    st.session_state.setdefault("sl_form_key", 0)

    valores = cargar_datos_generales()
    valores = _panel_datos_generales(valores)
    tc      = safe(valores.get("Tipo de Cambio USD/MXP", 18.50))

    divider()
    section_header("🛣️", "Nueva Ruta")

    tipo_ruta_actual = st.session_state.get("sl_tipo", TIPOS_RUTA[0])
    es_empty_outer   = (tipo_ruta_actual == "Empty")

    _k = st.session_state.get("sl_form_key", 0)
    with st.form(f"sl_captura_ruta_{_k}", clear_on_submit=False):

        # ── 1. INFO GENERAL ───────────────────────────────────────────────────
        st.markdown("### 📋 Información General")
        g1, g2, g3, g4 = st.columns(4)
        fecha      = g1.date_input("📅 Fecha", value=datetime.today(), key="sl_fecha")
        tipo_ruta  = g2.selectbox("🚛 Tipo de Ruta", TIPOS_RUTA,
                                   index=TIPOS_RUTA.index(tipo_ruta_actual), key="sl_tipo")
        cliente    = g3.text_input("🏢 Cliente", placeholder="NOMBRE DEL CLIENTE", key="sl_cliente")
        modo       = g4.selectbox("👥 Modo", ["Individual", "Team"], key="sl_modo")

        es_empty = (tipo_ruta == "Empty")
        aplica_mx = tiene_mx(tipo_ruta)

        dir_label = direccion_label(tipo_ruta)
        mx_label  = "Sí" if aplica_mx else "No"
        st.caption(f"📌 Dirección: **{dir_label}** · Tramo MX: **{mx_label}**")

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
                preview = (safe(cxm_flete_cap) + safe(cxm_fuel_cap)) * safe(miles_load)
                mod2.caption(
                    f"Vista previa: (CXM Flete ${safe(cxm_flete_cap):.4f}"
                    f" + CXM Fuel ${safe(cxm_fuel_cap):.4f})"
                    f" × {miles_load:.0f} ML"
                    f" = **${preview:,.2f} USD**"
                )
        else:
            tf1, tf2 = mod2.columns(2)
            moneda_flete   = tf1.selectbox("💱 Moneda", ["USD", "MXP"],
                                            key="sl_mon_flete", disabled=es_empty)
            flete_flat_cap = tf2.number_input("Tarifa Total (Flat)", min_value=0.0,
                                               step=50.0, key="sl_flete_flat",
                                               disabled=es_empty)
            cxm_flete_cap = cxm_fuel_cap = 0.0

        # ── Fuel Owner ────────────────────────────────────────────────────────
        if not es_empty and modalidad == "Desglosada":
            divider()
            fuel_owner = st.checkbox(
                "⛽ Pagar Fuel al Owner (el monto de Fuel se suma al costo directo)",
                value=False,
                key=f"sl_fuel_owner_{_k}",
                help=(
                    "Actívalo cuando se acordó pagar el fuel al owner. "
                    "El cálculo: Miles Load × CXM Fuel se suma como costo directo. "
                    "El ingreso al cliente no cambia."
                ),
            )
        else:
            fuel_owner = False

        # ── 3. CRUCE ──────────────────────────────────────────────────────────
        divider()
        st.markdown("### 🛂 Cruce Fronterizo")

        incluye_cruce = st.checkbox("¿Incluye cruce?", key="sl_inc_cruce",
                                     disabled=es_empty)
        tipo_cruce    = "Propio"
        tipo_carga_c  = "Cargado"
        ingreso_cruce_raw = 0.0
        costo_cruce_raw   = 0.0
        mon_ing_cruce     = "USD"
        mon_costo_cruce   = "USD"

        if incluye_cruce and not es_empty:
            cx1, cx2 = st.columns(2)
            tipo_cruce   = cx1.selectbox("Tipo de Cruce",  ["Propio", "Tercero"], key="sl_tcruce")
            tipo_carga_c = cx2.selectbox("Tipo de Carga",  ["Cargado", "Vacío"],  key="sl_tcarga")

            ic1, ic2 = st.columns(2)
            mon_ing_cruce     = ic1.selectbox("Moneda Ingreso Cruce",  ["USD", "MXP"], key="sl_mon_ic")
            ingreso_cruce_raw = ic1.number_input("Ingreso Cruce", min_value=0.0, step=10.0, key="sl_ing_cruce")

            if tipo_cruce == "Tercero":
                mon_costo_cruce   = ic2.selectbox("Moneda Costo Cruce",  ["USD", "MXP"], key="sl_mon_cc")
                costo_cruce_raw   = ic2.number_input("Costo Cruce (Tercero)", min_value=0.0, step=10.0, key="sl_cos_cruce")

        # ── 4. TRAMO MX ───────────────────────────────────────────────────────
        origen_mx = destino_mx = ""
        ingreso_mx_raw = costo_mx_raw = 0.0
        mon_ing_mx = mon_costo_mx = "MXP"

        if aplica_mx and not es_empty:
            divider()
            st.markdown("### 🇲🇽 Tramo Mexicano")
            mx1, mx2 = st.columns(2)
            origen_mx  = mx1.text_input("📍 Origen MX",  key="sl_ori_mx",  placeholder="CIUDAD")
            destino_mx = mx2.text_input("📍 Destino MX", key="sl_dest_mx", placeholder="CIUDAD")

            mi1, mi2 = st.columns(2)
            mon_ing_mx     = mi1.selectbox("Moneda Ingreso MX",  ["MXP","USD"], key="sl_mon_imx")
            ingreso_mx_raw = mi1.number_input("Ingreso MX", min_value=0.0, step=100.0, key="sl_ing_mx")
            mon_costo_mx   = mi2.selectbox("Moneda Costo MX",    ["MXP","USD"], key="sl_mon_cmx")
            costo_mx_raw   = mi2.number_input("Costo MX",  min_value=0.0, step=100.0, key="sl_cos_mx")

        # ── 5. EXTRAS ─────────────────────────────────────────────────────────
        divider()
        st.markdown("### ➕ Otros Cargos")
        otros_cargos  = {}
        otros_pagados = {}

        cols_extra = st.columns(3)
        for i, extra in enumerate(EXTRAS_USA):
            col = cols_extra[i % 3]
            monto   = col.number_input(extra, min_value=0.0, step=10.0,
                                        key=f"sl_ext_{extra}", label_visibility="visible")
            cobrado = col.checkbox("Cobrado al cliente", key=f"sl_extc_{extra}")
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
            if es_empty:
                flete_usd = fuel_usd = 0.0
            elif modalidad == "Desglosada":
                # Flete = CXM_Flete × Miles_Load  |  Fuel = CXM_Fuel × Miles_Load
                # Se separan para que fuel_owner pueda identificar cuánto es fuel
                flete_usd = a_usd(safe(cxm_flete_cap) * safe(miles_load), moneda_flete, tc)
                fuel_usd  = a_usd(safe(cxm_fuel_cap)  * safe(miles_load), moneda_flete, tc)
            else:
                flete_usd = a_usd(safe(flete_flat_cap), moneda_flete, tc)
                fuel_usd  = 0.0

            ingreso_cruce_u = a_usd(ingreso_cruce_raw, mon_ing_cruce,   tc)
            costo_cruce_u   = a_usd(costo_cruce_raw,   mon_costo_cruce, tc)
            ingreso_mx_u    = a_usd(ingreso_mx_raw,    mon_ing_mx,      tc)
            costo_mx_u      = a_usd(costo_mx_raw,      mon_costo_mx,    tc)

            extras_ingreso    = sum(v for n, v in otros_cargos.items() if otros_pagados.get(n, False))
            extras_costo_puro = sum(v for n, v in otros_cargos.items() if not otros_pagados.get(n, False))

            resultado = calcular_ruta_setlogis(
                tipo_ruta            = tipo_ruta,
                modo                 = modo,
                ruta_usa             = ruta_usa,
                cliente              = normalizar(cliente),
                miles_load           = miles_load,
                miles_empty          = miles_empty,
                short_miles          = short_miles,
                flete_usa            = flete_usd,
                fuel                 = fuel_usd,
                tipo_cruce           = tipo_cruce,
                tipo_carga_cruce     = tipo_carga_c,
                ingreso_cruce        = ingreso_cruce_u,
                costo_cruce_externo  = costo_cruce_u,
                ingreso_mx           = ingreso_mx_u,
                costo_mx             = costo_mx_u,
                extras_ingreso       = extras_ingreso,
                extras_costo         = extras_costo_puro,
                modo_costo_indirecto = modo_ci,
                valores              = valores,
                fuel_owner           = fuel_owner,
            )

            resultado["Modalidad"]     = modalidad
            resultado["CXM_Flete_Cap"] = safe(cxm_flete_cap) if modalidad == "Desglosada" else 0.0
            resultado["CXM_Fuel_Cap"]  = safe(cxm_fuel_cap)  if modalidad == "Desglosada" else 0.0
            resultado["Flete_Flat"]    = flete_usd            if modalidad == "Flat"        else 0.0

            id_ruta = generar_id_ruta(supabase)

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
                "fuel_owner":       fuel_owner,
            }
            alert("success", "✅ Ruta calculada correctamente.")

    # ── Mostrar resultado ─────────────────────────────────────────────────────
    if st.session_state.get("sl_resultado"):
        r = st.session_state["sl_resultado"]
        _mostrar_resumen(
            r,
            modalidad = r.get("Modalidad", "Flat"),
            cxm_flete = r.get("CXM_Flete_Cap", 0.0),
            cxm_fuel  = r.get("CXM_Fuel_Cap",  0.0),
        )

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
                    "Fuel_Owner":           r.get("Fuel_Owner", False),
                    "Pago_Fuel_Owner":      r.get("Pago_Fuel_Owner", 0.0),
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
                st.session_state["sl_form_key"]  = _k + 1
                st.rerun()

            except Exception as ex:
                alert("error", f"❌ Error al guardar: {ex}")
