"""
captura_rutas.py – Set Logis Plus
Homologado con Lincoln:
  - Sin st.form — usa st.button + sl_form_key para reset (compatible con st_searchbox)
  - st_searchbox para Origen/Destino USA
  - Panel de parámetros: loop genérico sobre DEFAULTS + caption Banxico FIX
  - mostrar_resultados_setlogis() de _shared — 1 línea reemplaza bloque completo
  - Modal @st.dialog al guardar
  - Prefijos sl_* en todos los keys

Diferencias Set Logis que se preservan:
  - Fuel_Owner checkbox (agrega costo fuel al pago del owner)
  - Modo: "Individual" / "Team" (Lincoln usa "Sencillo")
  - 3 tipos de millas: Miles Load, Short Miles, Miles Empty
  - Modalidad Flat / Desglosada con CXM_Flete y CXM_Fuel
  - modo_costo_indirecto: CXM vs %
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st
from streamlit_searchbox import st_searchbox

from services.supabase_client import get_supabase_client, current_user
from ui.components import section_header, alert, divider
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
    normalizar,
    a_usd,
    get_profile_name,
    generar_id_ruta,
    buscar_ubicacion_setlogis,
    mostrar_resultados_setlogis,
)


# ─────────────────────────────────────────────
# MODAL CONFIRMACIÓN
# ─────────────────────────────────────────────
@st.dialog("✅ Ruta Guardada Exitosamente", width="small")
def _modal_guardado(id_ruta: str) -> None:
    alert("success", "**¡La ruta se guardó correctamente!**")
    st.info(f"### 🆔 ID de la ruta\n`{id_ruta}`")
    st.caption("Puedes consultarla en 'Consulta Ruta' o 'Gestión de Rutas'.")
    if st.button("✅ Aceptar", type="primary", use_container_width=True, key="sl_modal_ok"):
        st.session_state.pop("sl_ruta_guardada_id", None)
        st.session_state.pop("sl_mostrar_modal",    None)
        st.session_state.pop("sl_resultado",        None)
        st.session_state.pop("sl_datos",            None)
        st.session_state["sl_form_key"] = st.session_state.get("sl_form_key", 0) + 1
        st.rerun()


# ─────────────────────────────────────────────
# PANEL PARÁMETROS — loop genérico sobre DEFAULTS
# ─────────────────────────────────────────────
def _panel_datos_generales(valores: dict) -> dict:
    with st.expander("⚙️ Configuración de Parámetros", expanded=False):
        tc_banxico = float(valores.get("Tipo de Cambio USD/MXP", DEFAULTS["Tipo de Cambio USD/MXP"]))
        st.caption(
            f"💱 Banxico FIX del día: **${tc_banxico:,.4f} MXP/USD** "
            "— se actualiza automáticamente cada 24h."
        )
        col1, col2, col3 = st.columns(3)
        claves = list(DEFAULTS.keys())
        for i, key in enumerate(claves):
            col = [col1, col2, col3][i % 3]
            valores[key] = col.number_input(
                key,
                value=float(valores.get(key, DEFAULTS[key])),
                step=0.01,
                format="%.4f",
                key=f"sl_gen_{key}",
            )
        if st.button("💾 Guardar Parámetros", key="sl_save_gen"):
            guardar_datos_generales(valores)
            alert("success", "✅ Parámetros guardados correctamente.")
    return valores


# ─────────────────────────────────────────────
# SECCIÓN INFO GENERAL
# ─────────────────────────────────────────────
def _seccion_info_general(fk: int) -> tuple:
    """Devuelve: fecha, tipo_ruta, cliente, modo"""
    st.markdown("### 📋 Información General")
    g1, g2, g3, g4 = st.columns(4)
    fecha      = g1.date_input("📅 Fecha", value=datetime.today(), key=f"sl_fecha_{fk}")
    tipo_ruta  = g2.selectbox("🚛 Tipo de Ruta", TIPOS_RUTA, key=f"sl_tipo_{fk}")
    cliente    = g3.text_input("🏢 Cliente", placeholder="NOMBRE DEL CLIENTE", key=f"sl_cliente_{fk}")
    modo       = g4.selectbox("👥 Modo", ["Individual", "Team"], key=f"sl_modo_{fk}")
    return fecha, tipo_ruta, cliente, modo


# ─────────────────────────────────────────────
# SECCIÓN RUTA AMERICANA
# ─────────────────────────────────────────────
def _seccion_ruta_americana(es_empty: bool, fk: int) -> tuple:
    """Devuelve: origen_usa, destino_usa, miles_load, short_miles, miles_empty,
                 modalidad, moneda_flete, cxm_flete, cxm_fuel, flete_flat, fuel_owner"""
    st.markdown("### 🇺🇸 Ruta Americana")

    ru1, ru2 = st.columns(2)
    with ru1:
        origen_sel = st_searchbox(
            buscar_ubicacion_setlogis,
            label="📍 Origen USA",
            placeholder="Escribe para buscar o capturar nueva...",
            key=f"sl_ori_usa_{fk}",
            clear_on_submit=False,
        )
    with ru2:
        destino_sel = st_searchbox(
            buscar_ubicacion_setlogis,
            label="📍 Destino USA",
            placeholder="Escribe para buscar o capturar nueva...",
            key=f"sl_dest_usa_{fk}",
            clear_on_submit=False,
        )
    origen_usa  = str(origen_sel  or "").strip()
    destino_usa = str(destino_sel or "").strip()

    # ── Millas ───────────────────────────────────────────────────────────────
    m1, m2, m3 = st.columns(3)
    miles_load  = m1.number_input("Miles Load (facturadas al cliente)", min_value=0.0,
                                   step=1.0, format="%.1f", key=f"sl_miles_load_{fk}")
    short_miles = m2.number_input("Short Miles (operador cargado)",     min_value=0.0,
                                   step=1.0, format="%.1f", key=f"sl_short_miles_{fk}")
    miles_empty = m3.number_input("Miles Empty (vacías)",               min_value=0.0,
                                   step=1.0, format="%.1f", key=f"sl_miles_empty_{fk}")

    # ── Modalidad e ingreso ───────────────────────────────────────────────────
    if not es_empty:
        r1, r2 = st.columns([1, 3])
        modalidad    = r1.selectbox("Modalidad", ["Desglosada", "Flat"], key=f"sl_modalidad_{fk}")
        moneda_flete = r2.selectbox("Moneda Flete", ["USD", "MXP"], key=f"sl_mon_flete_{fk}")

        if modalidad == "Desglosada":
            d1, d2 = st.columns(2)
            cxm_flete  = d1.number_input("CXM Flete (USD/milla)",
                                          min_value=0.0, step=0.001, format="%.4f",
                                          key=f"sl_cxm_flete_{fk}")
            cxm_fuel   = d2.number_input("CXM Fuel  (USD/milla)",
                                          min_value=0.0, step=0.001, format="%.4f",
                                          key=f"sl_cxm_fuel_{fk}")
            flete_flat = 0.0
        else:
            flete_flat = st.number_input("Flete Flat (monto total)",
                                          min_value=0.0, step=1.0, format="%.2f",
                                          key=f"sl_flete_flat_{fk}")
            cxm_flete  = 0.0
            cxm_fuel   = 0.0

        # Fuel Owner — exclusivo de Set Logis
        fuel_owner = st.checkbox(
            "⛽ Fuel Owner — el fuel se paga al owner (suma a Costo Directo)",
            key=f"sl_fuel_owner_{fk}",
        )
    else:
        # Ruta Empty: sin flete ni fuel
        modalidad    = "Flat"
        moneda_flete = "USD"
        cxm_flete    = 0.0
        cxm_fuel     = 0.0
        flete_flat   = 0.0
        fuel_owner   = False

    return (origen_usa, destino_usa, miles_load, short_miles, miles_empty,
            modalidad, moneda_flete, cxm_flete, cxm_fuel, flete_flat, fuel_owner)


# ─────────────────────────────────────────────
# SECCIÓN CRUCE
# ─────────────────────────────────────────────
def _seccion_cruce(fk: int) -> tuple:
    """Devuelve: incluye_cruce, tipo_cruce, tipo_carga_c,
                 mon_ing_cruce, ingreso_cruce_raw,
                 mon_costo_cruce, costo_cruce_raw"""
    st.markdown("### 🛂 Cruce")
    incluye_cruce = st.checkbox("¿Incluye cruce?", key=f"sl_incluye_cruce_{fk}")

    tipo_cruce     = "Propio"
    tipo_carga_c   = "Cargado"
    mon_ing_cruce  = "USD"
    ingreso_cruce  = 0.0
    mon_costo_cruce = "USD"
    costo_cruce_raw = 0.0

    if incluye_cruce:
        cr1, cr2 = st.columns(2)
        tipo_cruce   = cr1.selectbox("Tipo de Cruce", ["Propio", "Tercero"],        key=f"sl_tipo_cruce_{fk}")
        tipo_carga_c = cr2.selectbox("Tipo de Carga", ["Cargado", "Vacío"],         key=f"sl_tipo_carga_c_{fk}")

        ic1, ic2, ic3, ic4 = st.columns(4)
        mon_ing_cruce   = ic1.selectbox("Moneda Ingreso", ["USD", "MXP"],           key=f"sl_mon_ing_cr_{fk}")
        ingreso_cruce   = ic2.number_input("Ingreso Cruce", min_value=0.0,
                                            step=0.01, format="%.2f",               key=f"sl_ing_cruce_{fk}")
        if tipo_cruce == "Tercero":
            mon_costo_cruce = ic3.selectbox("Moneda Costo",  ["USD", "MXP"],        key=f"sl_mon_costo_cr_{fk}")
            costo_cruce_raw = ic4.number_input("Costo Cruce", min_value=0.0,
                                               step=0.01, format="%.2f",            key=f"sl_costo_cruce_{fk}")

    return (incluye_cruce, tipo_cruce, tipo_carga_c,
            mon_ing_cruce, ingreso_cruce,
            mon_costo_cruce, costo_cruce_raw)


# ─────────────────────────────────────────────
# SECCIÓN PARTE MX
# ─────────────────────────────────────────────
def _seccion_mx(fk: int) -> tuple:
    """Devuelve: origen_mx, destino_mx,
                 mon_ing_mx, ingreso_mx_raw,
                 mon_costo_mx, costo_mx_raw"""
    st.markdown("### 🇲🇽 Parte MX")
    mx1, mx2 = st.columns(2)
    origen_mx  = mx1.text_input("Origen MX",  placeholder="CIUDAD, MX", key=f"sl_ori_mx_{fk}")
    destino_mx = mx2.text_input("Destino MX", placeholder="CIUDAD, MX", key=f"sl_dest_mx_{fk}")

    m1, m2, m3, m4 = st.columns(4)
    mon_ing_mx   = m1.selectbox("Moneda Ingreso MX",  ["MXP", "USD"], key=f"sl_mon_ing_mx_{fk}")
    ingreso_mx   = m2.number_input("Ingreso MX", min_value=0.0, step=0.01, format="%.2f",
                                    key=f"sl_ing_mx_{fk}")
    mon_costo_mx = m3.selectbox("Moneda Costo MX",   ["MXP", "USD"], key=f"sl_mon_costo_mx_{fk}")
    costo_mx     = m4.number_input("Costo MX",   min_value=0.0, step=0.01, format="%.2f",
                                    key=f"sl_costo_mx_{fk}")

    return origen_mx, destino_mx, mon_ing_mx, ingreso_mx, mon_costo_mx, costo_mx


# ─────────────────────────────────────────────
# SECCIÓN EXTRAS
# ─────────────────────────────────────────────
def _seccion_extras(fk: int) -> tuple:
    """Devuelve: otros_cargos (dict nombre→monto), otros_pagados (dict nombre→bool cobrado)"""
    st.markdown("### ➕ Extras / Otros Cargos")
    otros_cargos  = {}
    otros_pagados = {}
    cols = st.columns(3)
    for i, nombre in enumerate(EXTRAS_USA):
        col = cols[i % 3]
        monto   = col.number_input(nombre, min_value=0.0, step=0.01, format="%.2f",
                                   key=f"sl_extra_{nombre.replace(' ','_')}_{fk}")
        cobrado = col.checkbox(f"Cobrado al cliente ({nombre})",
                               key=f"sl_extra_cob_{nombre.replace(' ','_')}_{fk}")
        if monto > 0:
            otros_cargos[nombre]  = monto
            otros_pagados[nombre] = cobrado
    return otros_cargos, otros_pagados


# ─────────────────────────────────────────────
# COSTO INDIRECTO (modo)
# ─────────────────────────────────────────────
def _seccion_costo_indirecto(fk: int) -> str:
    st.markdown("### 📊 Costo Indirecto")
    modo_ci = st.radio(
        "Método de cálculo",
        ["CXM", "%"],
        horizontal=True,
        key=f"sl_modo_ci_{fk}",
        help="CXM = costo por milla total · % = porcentaje del ingreso global",
    )
    return modo_ci


# ─────────────────────────────────────────────
# RENDER PRINCIPAL
# ─────────────────────────────────────────────
def render() -> None:
    supabase = get_supabase_client()
    if supabase is None:
        alert("warn", "⚠️ Supabase no configurado. Podrás revisar cálculos, pero NO guardar rutas.")

    u              = current_user() or {}
    user_id        = u.get("id") or u.get("sub") or ""
    nombre_usuario = get_profile_name(user_id) or u.get("email") or "Desconocido"

    st.session_state.setdefault("sl_resultado",    None)
    st.session_state.setdefault("sl_datos",        {})
    st.session_state.setdefault("sl_form_key",     0)

    # ── Modal post-guardado ────────────────────────────────────────────────────
    if st.session_state.get("sl_mostrar_modal") and st.session_state.get("sl_ruta_guardada_id"):
        _modal_guardado(st.session_state["sl_ruta_guardada_id"])

    # ── Parámetros ─────────────────────────────────────────────────────────────
    valores = cargar_datos_generales()
    valores = _panel_datos_generales(valores)
    tc      = safe(valores.get("Tipo de Cambio USD/MXP", DEFAULTS["Tipo de Cambio USD/MXP"]))

    divider()
    section_header("🛣️", "Nueva Ruta")

    _k = st.session_state.get("sl_form_key", 0)

    # ── Leer tipo_ruta anticipado para saber orden de secciones ───────────────
    tipo_ruta_actual = st.session_state.get(f"sl_tipo_{_k}", TIPOS_RUTA[0])
    es_empty         = (tipo_ruta_actual == "Empty")
    aplica_mx        = tiene_mx(tipo_ruta_actual)

    # ── Sección siempre primera: Info General ─────────────────────────────────
    fecha, tipo_ruta, cliente, modo = _seccion_info_general(_k)
    es_empty  = (tipo_ruta == "Empty")
    aplica_mx = tiene_mx(tipo_ruta)

    # ── Orden de secciones según tipo (espeja comportamiento de Lincoln) ───────
    # NB    → americana → cruce → extras
    # SB    → americana → cruce → extras
    # D2DNB → mx → cruce → americana → extras
    # D2DSB → americana → cruce → mx → extras
    # Empty → americana (solo millas) → extras

    origen_usa = destino_usa = ""
    miles_load = short_miles = miles_empty = 0.0
    modalidad = "Desglosada"; moneda_flete = "USD"
    cxm_flete = cxm_fuel = flete_flat = 0.0
    fuel_owner = False
    incluye_cruce = False; tipo_cruce = "Propio"; tipo_carga_c = "Cargado"
    mon_ing_cruce = "USD"; ingreso_cruce_raw = 0.0
    mon_costo_cruce = "USD"; costo_cruce_raw = 0.0
    origen_mx = destino_mx = ""
    mon_ing_mx = "MXP"; ingreso_mx_raw = 0.0
    mon_costo_mx = "MXP"; costo_mx_raw = 0.0

    if tipo_ruta == "D2DNB":
        divider()
        (origen_mx, destino_mx,
         mon_ing_mx, ingreso_mx_raw,
         mon_costo_mx, costo_mx_raw)          = _seccion_mx(_k)
        divider()
        (incluye_cruce, tipo_cruce, tipo_carga_c,
         mon_ing_cruce, ingreso_cruce_raw,
         mon_costo_cruce, costo_cruce_raw)    = _seccion_cruce(_k)
        divider()
        (origen_usa, destino_usa,
         miles_load, short_miles, miles_empty,
         modalidad, moneda_flete,
         cxm_flete, cxm_fuel, flete_flat,
         fuel_owner)                           = _seccion_ruta_americana(es_empty, _k)
    elif tipo_ruta == "D2DSB":
        divider()
        (origen_usa, destino_usa,
         miles_load, short_miles, miles_empty,
         modalidad, moneda_flete,
         cxm_flete, cxm_fuel, flete_flat,
         fuel_owner)                           = _seccion_ruta_americana(es_empty, _k)
        divider()
        (incluye_cruce, tipo_cruce, tipo_carga_c,
         mon_ing_cruce, ingreso_cruce_raw,
         mon_costo_cruce, costo_cruce_raw)    = _seccion_cruce(_k)
        divider()
        (origen_mx, destino_mx,
         mon_ing_mx, ingreso_mx_raw,
         mon_costo_mx, costo_mx_raw)          = _seccion_mx(_k)
    else:
        # NB, SB, Empty
        divider()
        (origen_usa, destino_usa,
         miles_load, short_miles, miles_empty,
         modalidad, moneda_flete,
         cxm_flete, cxm_fuel, flete_flat,
         fuel_owner)                           = _seccion_ruta_americana(es_empty, _k)
        if not es_empty:
            divider()
            (incluye_cruce, tipo_cruce, tipo_carga_c,
             mon_ing_cruce, ingreso_cruce_raw,
             mon_costo_cruce, costo_cruce_raw) = _seccion_cruce(_k)

    # ── Extras ────────────────────────────────────────────────────────────────
    divider()
    otros_cargos, otros_pagados = _seccion_extras(_k)

    # ── Costo indirecto ────────────────────────────────────────────────────────
    divider()
    modo_ci = _seccion_costo_indirecto(_k)

    # ── Botón Calcular ────────────────────────────────────────────────────────
    divider()
    if st.button("🔍 Calcular Ruta", type="primary", use_container_width=True,
                 key=f"sl_calcular_{_k}"):

        errores = []
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
            # Convertir monedas a USD
            if es_empty:
                flete_usd = fuel_usd = 0.0
            elif modalidad == "Desglosada":
                flete_usd = a_usd(safe(cxm_flete) * safe(miles_load), moneda_flete, tc)
                fuel_usd  = a_usd(safe(cxm_fuel)  * safe(miles_load), moneda_flete, tc)
            else:
                flete_usd = a_usd(safe(flete_flat), moneda_flete, tc)
                fuel_usd  = 0.0

            ingreso_cruce_u = a_usd(ingreso_cruce_raw, mon_ing_cruce,   tc)
            costo_cruce_u   = a_usd(costo_cruce_raw,   mon_costo_cruce, tc)
            ingreso_mx_u    = a_usd(ingreso_mx_raw,    mon_ing_mx,      tc)
            costo_mx_u      = a_usd(costo_mx_raw,      mon_costo_mx,    tc)

            extras_ingreso    = sum(v for n, v in otros_cargos.items() if otros_pagados.get(n, False))
            extras_costo_puro = sum(v for n, v in otros_cargos.items() if not otros_pagados.get(n, False))

            ruta_usa = f"{normalizar(origen_usa)} - {normalizar(destino_usa)}"

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
                incluye_cruce        = incluye_cruce and not es_empty,
            )

            # Campos extra para guardado
            resultado["Modalidad"]     = modalidad
            resultado["CXM_Flete_Cap"] = safe(cxm_flete) if modalidad == "Desglosada" else 0.0
            resultado["CXM_Fuel_Cap"]  = safe(cxm_fuel)  if modalidad == "Desglosada" else 0.0
            resultado["Flete_Flat"]    = flete_usd        if modalidad == "Flat"       else 0.0

            id_ruta = generar_id_ruta(supabase) if supabase else "SL000000"

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
                "cxm_flete_cap":    safe(cxm_flete) if modalidad == "Desglosada" else 0.0,
                "cxm_fuel_cap":     safe(cxm_fuel)  if modalidad == "Desglosada" else 0.0,
            }
            alert("success", "✅ Ruta calculada. Revisa el resultado abajo.")

    # ── Mostrar resultado — 1 línea gracias a mostrar_resultados_setlogis() ───
    if st.session_state.get("sl_resultado"):
        r = st.session_state["sl_resultado"]
        divider()
        mostrar_resultados_setlogis(
            r,
            modalidad  = r.get("Modalidad", "Flat"),
            miles_load = safe(r.get("Miles_Load", 0.0)),
            cxm_flete  = r.get("CXM_Flete_Cap", 0.0),
            cxm_fuel   = r.get("CXM_Fuel_Cap",  0.0),
        )

        divider()
        col_g, col_x = st.columns([2, 1])
        with col_g:
            if st.button("💾 Guardar en Base de Datos", type="primary",
                         use_container_width=True, key="sl_guardar_ruta"):
                if supabase is None:
                    alert("error", "❌ Supabase no está configurado.")
                else:
                    _guardar_ruta(r, st.session_state["sl_datos"], supabase)
        with col_x:
            if st.button("🗑️ Descartar", use_container_width=True, key="sl_descartar"):
                st.session_state.pop("sl_resultado", None)
                st.session_state.pop("sl_datos",     None)
                st.rerun()


# ─────────────────────────────────────────────
# GUARDAR EN SUPABASE
# ─────────────────────────────────────────────
def _guardar_ruta(r: dict, d: dict, supabase) -> None:
    try:
        extras_db         = {
            f"Extra_{n.replace(' ','_')}": v
            for n, v in d.get("otros_cargos", {}).items()
        }
        extras_cobrado_db = {
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
            "CXM_Flete":            d["cxm_flete_cap"],
            "CXM_Fuel":             d["cxm_fuel_cap"],
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

        st.session_state["sl_ruta_guardada_id"] = d["id_ruta"]
        st.session_state["sl_mostrar_modal"]    = True
        st.session_state["sl_resultado"]        = None
        st.session_state["sl_datos"]            = {}
        st.rerun()

    except Exception as ex:
        alert("error", f"❌ Error al guardar: {ex}")
