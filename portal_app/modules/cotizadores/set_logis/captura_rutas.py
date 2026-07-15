"""
captura_rutas.py – Set Logis Plus
Estructura visual idéntica a Lincoln Freight.
Diferencias Set Logis:
  - Fuel_Owner checkbox en Ruta Americana
  - Modo: "Individual" / "Team" (Lincoln usa "Sencillo")
  - 3 millas: Miles Load (facturadas), Short Miles (operador), Miles Empty
  - Modalidad Flat / Desglosada con CXM_Flete + CXM_Fuel separados
  - modo_costo_indirecto: CXM vs % (sección al final)
  - Sin linea_mx en parte MX, sin forzado en cruce

Orden de secciones según tipo de ruta:
    NB    → Info General → Cruce → Ruta Americana → Extras → Costo Indirecto
    SB    → Info General → Ruta Americana → Cruce → Extras → Costo Indirecto
    D2DNB → Info General → Parte MX → Cruce → Ruta Americana → Extras → Costo Indirecto
    D2DSB → Info General → Ruta Americana → Cruce → Parte MX → Extras → Costo Indirecto
    Empty → Info General → Ruta Americana → Extras → Costo Indirecto

Sin st.form — usa st.button + sl_form_key (compatible con st_searchbox).
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st
from streamlit_searchbox import st_searchbox

from services.supabase_client import get_supabase_client, current_user
from ui.components import section_header, alert, divider
from ._helpers import (
    TABLE_RUTAS,
    TIPOS_RUTA,
    EXTRAS_USA,
    DEFAULTS,
    cargar_datos_generales,
    guardar_datos_generales,
    limpiar_fila_json,
    safe,
    calcular_ruta_setlogis,
    obtener_config_tipo_ruta,
    tiene_mx,
    normalizar,
    a_usd,
    get_profile_name,
    generar_id_ruta,
    buscar_ubicacion_setlogis,
    cargar_pool_ubicaciones_setlogis,
    mostrar_resultados_setlogis,
    log_accion,
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
        st.session_state["sl_form_key"] = st.session_state.get("sl_form_key", 0) + 1
        st.rerun()


# ─────────────────────────────────────────────
# PANEL PARÁMETROS — loop genérico idéntico a Lincoln
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
                key=f"sl_gen_{key}",
            )
        if st.button("💾 Guardar Parámetros", key="sl_save_gen"):
            guardar_datos_generales(valores)
            alert("success", "✅ Parámetros guardados correctamente.")
    return valores


# ─────────────────────────────────────────────
# SECCIONES DEL FORMULARIO
# Firmas idénticas a Lincoln — solo nombres de empresa difieren
# ─────────────────────────────────────────────

def _seccion_info_general(es_empty: bool, tipo_ruta: str, fk: int) -> tuple:
    """Devuelve: fecha, tipo_ruta, cliente, modo"""
    st.markdown("### 📋 Información General")
    g1, g2, g3, g4 = st.columns(4)
    fecha  = g1.date_input("📅 Fecha", value=datetime.today(), key=f"sl_fecha_{fk}")
    tipo   = g2.selectbox("🚛 Tipo de Ruta", TIPOS_RUTA,
                           index=TIPOS_RUTA.index(tipo_ruta), key=f"sl_tipo_{fk}")
    cliente = g3.text_input("🏢 Cliente", placeholder="NOMBRE DEL CLIENTE", key=f"sl_cliente_{fk}")
    modo    = g4.selectbox("👥 Modo", ["Individual", "Team"], key=f"sl_modo_{fk}")

    config    = obtener_config_tipo_ruta(tipo)
    dir_label = "Bajada" if tipo in {"SB", "D2DSB"} else "Subida"
    mx_label  = "Sí" if config["parte_mx"] else "No"
    st.caption(f"📌 Dirección: **{dir_label}** · Tramo MX: **{mx_label}**")
    return fecha, tipo, cliente, modo


def _seccion_ruta_americana(es_empty: bool, valores: dict, fk: int) -> tuple:
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

    m1, m2, m3 = st.columns(3)
    miles_load  = m1.number_input(
        "🛣️ Miles Load", min_value=0.0, step=10.0, key=f"sl_miles_load_{fk}",
        help="Millas que se cotizan al cliente (base del ingreso Desglosado)",
        disabled=es_empty,
    )
    short_miles = m2.number_input(
        "🔀 Short Miles", min_value=0.0, step=1.0, key=f"sl_short_miles_{fk}",
        help="Millas reales recorridas cargado (base del pago al owner)",
        disabled=es_empty,
    )
    miles_empty = m3.number_input(
        "⚪ Miles Empty", min_value=0.0, step=10.0, key=f"sl_miles_empty_{fk}",
        help="Millas en vacío (pago owner vacío)",
    )

    cxm_flete   = 0.0
    cxm_fuel    = 0.0
    flete_flat  = 0.0
    moneda_flete = "USD"

    if es_empty:
        st.info("ℹ️ **Empty:** sin tarifa al cliente. Solo costos de reposicionamiento.")
        return (origen_usa, destino_usa, miles_load, short_miles, miles_empty,
                "Flat", moneda_flete, cxm_flete, cxm_fuel, flete_flat, False)

    divider()
    st.markdown("**💵 Tarifa Americana**")
    mod1, mod2 = st.columns([1, 3])
    modalidad = mod1.radio(
        "Modalidad", ["Desglosada", "Flat"],
        horizontal=False, key=f"sl_modalidad_{fk}",
    )

    if modalidad == "Desglosada":
        td1, td2, td3 = mod2.columns(3)
        moneda_flete = td1.selectbox("💱 Moneda", ["USD", "MXP"], key=f"sl_mon_flete_{fk}")
        cxm_flete    = td2.number_input(
            "CXM Flete ($/mi)", min_value=0.0, step=0.001, format="%.4f", key=f"sl_cxm_flete_{fk}",
        )
        cxm_fuel     = td3.number_input(
            "CXM Fuel  ($/mi)", min_value=0.0, step=0.001, format="%.4f", key=f"sl_cxm_fuel_{fk}",
            value=0.0,
        )
        if miles_load > 0:
            preview = (safe(cxm_flete) + safe(cxm_fuel)) * safe(miles_load)
            mod2.caption(
                f"Vista previa: (CXM Flete ${safe(cxm_flete):.4f}"
                f" + Fuel ${safe(cxm_fuel):.4f})"
                f" × {miles_load:.0f} ML"
                f" = **${preview:,.2f} USD**"
            )
    else:
        tf1, tf2 = mod2.columns(2)
        moneda_flete = tf1.selectbox("💱 Moneda", ["USD", "MXP"], key=f"sl_mon_flete_flat_{fk}")
        flete_flat   = tf2.number_input(
            "Tarifa Total (Flat)", min_value=0.0, step=50.0, key=f"sl_flete_flat_{fk}"
        )

    # ── Fuel Owner — exclusivo de Set Logis ────────────────────────────────
    fuel_owner = st.checkbox(
        "⛽ Fuel Owner — el fuel se paga al owner (suma a Costo Directo)",
        key=f"sl_fuel_owner_{fk}",
    )

    return (origen_usa, destino_usa, miles_load, short_miles, miles_empty,
            modalidad, moneda_flete, cxm_flete, cxm_fuel, flete_flat, fuel_owner)


def _seccion_cruce(tipo_ruta: str, config: dict, fk: int) -> tuple:
    """Devuelve: aplica_cruce, tipo_cruce, tipo_carga, moneda_cruce, ingreso_cruce, costo_cruce_terc"""
    st.markdown("### 🛂 Cruce Fronterizo")

    aplica_cruce     = False
    tipo_cruce       = "Propio"
    tipo_carga       = "Cargado"
    moneda_cruce     = "USD"
    ingreso_cruce    = 0.0
    costo_cruce_terc = 0.0

    forzado = (config.get("cruce") is True)
    aplica_cruce = st.checkbox(
        "¿Incluye cruce?",
        value=forzado,
        key=f"sl_aplica_cruce_{fk}",
    )

    if aplica_cruce:
        cx1, cx2, cx3 = st.columns(3)
        tipo_cruce   = cx1.selectbox("Tipo de Cruce", ["Propio", "Tercero"],   key=f"sl_tipo_cruce_{fk}")
        tipo_carga   = cx2.selectbox("Carga del cruce", ["Cargado", "Vacío"],  key=f"sl_tipo_carga_{fk}")
        moneda_cruce = cx3.selectbox("💱 Moneda Ingreso", ["USD", "MXP"],      key=f"sl_moneda_cruce_{fk}")

        ing_col, costo_col = st.columns(2)
        ingreso_cruce = ing_col.number_input(
            "Ingreso Cruce", min_value=0.0, step=5.0, format="%.2f", key=f"sl_ing_cruce_{fk}"
        )
        if tipo_cruce == "Tercero":
            costo_cruce_terc = costo_col.number_input(
                "Costo Cruce Tercero", min_value=0.0, step=5.0, format="%.2f",
                key=f"sl_costo_cruce_terc_{fk}",
            )

    return aplica_cruce, tipo_cruce, tipo_carga, moneda_cruce, ingreso_cruce, costo_cruce_terc


def _seccion_tramo_mx(fk: int) -> tuple:
    """Devuelve: origen_mx, destino_mx, moneda_mx, ingreso_mx, costo_mx"""
    st.markdown("### 🇲🇽 Parte Mexicana")

    mx1, mx2 = st.columns(2)
    with mx1:
        origen_mx_sel = st_searchbox(
            buscar_ubicacion_setlogis,
            label="📍 Origen MX",
            placeholder="Escribe para buscar o capturar nueva...",
            key=f"sl_ori_mx_{fk}",
            clear_on_submit=False,
        )
        destino_mx_sel = st_searchbox(
            buscar_ubicacion_setlogis,
            label="📍 Destino MX",
            placeholder="Escribe para buscar o capturar nueva...",
            key=f"sl_dest_mx_{fk}",
            clear_on_submit=False,
        )
    origen_mx  = str(origen_mx_sel  or "").strip()
    destino_mx = str(destino_mx_sel or "").strip()

    moneda_mx  = mx2.selectbox("💱 Moneda MX", ["MXP", "USD"], key=f"sl_moneda_mx_{fk}")
    ingreso_mx = mx2.number_input(
        "Ingreso Flete MX", min_value=0.0, step=100.0, format="%.2f", key=f"sl_ing_mx_{fk}"
    )
    costo_mx = mx2.number_input(
        "Costo Flete MX", min_value=0.0, step=100.0, format="%.2f", key=f"sl_costo_mx_{fk}"
    )

    return origen_mx, destino_mx, moneda_mx, ingreso_mx, costo_mx


def _seccion_extras(fk: int) -> tuple:
    """Devuelve: otros_cargos {nombre: monto}, otros_cargos_cobrados {nombre: bool}"""
    st.markdown("### ➕ Extras / Otros Conceptos")
    st.caption(
        "Captura el monto si Set Logis lo pagó (suma al costo). "
        "Marca **'cobrado'** si también se le cobró al cliente (suma al ingreso)."
    )
    otros_cargos          = {}
    otros_cargos_cobrados = {}
    cols = st.columns(3)
    for i, nombre in enumerate(EXTRAS_USA):
        col   = cols[i % 3]
        monto = col.number_input(
            nombre, min_value=0.0, step=0.01, format="%.2f",
            key=f"sl_extra_{nombre.replace(' ','_')}_{fk}",
        )
        cobrado = col.checkbox(
            f"Cobrado al cliente ({nombre})",
            key=f"sl_extra_cob_{nombre.replace(' ','_')}_{fk}",
        )
        if monto > 0:
            otros_cargos[nombre]          = monto
            otros_cargos_cobrados[nombre] = cobrado
    return otros_cargos, otros_cargos_cobrados


def _seccion_costo_indirecto(fk: int) -> str:
    """Set Logis — exclusivo: CXM vs % (Lincoln siempre usa %)"""
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

    st.session_state.setdefault("sl_resultado", None)
    st.session_state.setdefault("sl_form_data", {})
    st.session_state.setdefault("sl_form_key",  0)

    # Modal post-guardado
    if st.session_state.get("sl_mostrar_modal") and st.session_state.get("sl_ruta_guardada_id"):
        _modal_guardado(st.session_state["sl_ruta_guardada_id"])

    valores = cargar_datos_generales()
    valores = _panel_datos_generales(valores)
    tc      = safe(valores.get("Tipo de Cambio USD/MXP", DEFAULTS["Tipo de Cambio USD/MXP"]))
    divider()
    section_header("🛣️", "Nueva Ruta")

    _k = st.session_state.get("sl_form_key", 0)

    # Leer tipo_ruta anticipado para saber orden ANTES de renderizar
    tipo_ruta_actual = st.session_state.get(f"sl_tipo_{_k}", TIPOS_RUTA[0])
    config           = obtener_config_tipo_ruta(tipo_ruta_actual)
    orden            = config.get("orden", ["americana"])
    es_empty         = (tipo_ruta_actual == "Empty")

    # ── Info General — siempre primera ──────────────────────────────────────
    fecha, tipo_ruta, cliente, modo = _seccion_info_general(es_empty, tipo_ruta_actual, _k)
    config   = obtener_config_tipo_ruta(tipo_ruta)
    orden    = config.get("orden", ["americana"])
    es_empty = (tipo_ruta == "Empty")

    # Valores por defecto de secciones opcionales
    origen_usa = destino_usa = ""
    miles_load = short_miles = miles_empty = 0.0
    modalidad    = "Desglosada"
    moneda_flete = "USD"
    cxm_flete = cxm_fuel = flete_flat = 0.0
    fuel_owner   = False
    aplica_cruce = False
    tipo_cruce   = "Propio"
    tipo_carga   = "Cargado"
    moneda_cruce = "USD"
    ingreso_cruce = costo_cruce_terc = 0.0
    origen_mx  = destino_mx = ""
    moneda_mx  = "MXP"
    ingreso_mx = costo_mx = 0.0

    # ── Secciones en orden según tipo — idéntico al patrón de Lincoln ──────
    for seccion in orden:
        divider()

        if seccion == "americana":
            (origen_usa, destino_usa, miles_load, short_miles, miles_empty,
             modalidad, moneda_flete, cxm_flete, cxm_fuel, flete_flat,
             fuel_owner) = _seccion_ruta_americana(es_empty, valores, _k)

        elif seccion == "cruce":
            if not es_empty and config.get("cruce") in ("opcional", True):
                (aplica_cruce, tipo_cruce, tipo_carga,
                 moneda_cruce, ingreso_cruce,
                 costo_cruce_terc) = _seccion_cruce(tipo_ruta, config, _k)

        elif seccion == "mx":
            if config.get("parte_mx") and not es_empty:
                (origen_mx, destino_mx,
                 moneda_mx, ingreso_mx, costo_mx) = _seccion_tramo_mx(_k)

    # ── Extras — siempre al final antes de costo indirecto ──────────────────
    divider()
    otros_cargos, otros_cargos_cobrados = _seccion_extras(_k)

    # ── Costo Indirecto — exclusivo de Set Logis ─────────────────────────────
    divider()
    modo_ci = _seccion_costo_indirecto(_k)

    # ── Botón Calcular ────────────────────────────────────────────────────────
    divider()
    submitted = st.button(
        "🔍 Calcular Ruta", type="primary", use_container_width=True,
        key=f"sl_calcular_{_k}",
    )

    if submitted:
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

            ing_cruce_usd  = 0.0
            costo_cruce_usd = 0.0
            if aplica_cruce and not es_empty:
                ing_cruce_usd   = ingreso_cruce if moneda_cruce == "USD" else a_usd(ingreso_cruce, moneda_cruce, tc)
                costo_cruce_usd = costo_cruce_terc if tipo_cruce == "Tercero" else 0.0

            ing_mx_usd   = a_usd(ingreso_mx, moneda_mx, tc)
            costo_mx_usd = a_usd(costo_mx,   moneda_mx, tc)

            # Extras: cobrado = ingreso; no cobrado = costo puro
            extras_ingreso    = sum(v for n, v in otros_cargos.items() if otros_cargos_cobrados.get(n, False))
            extras_costo_puro = sum(v for n, v in otros_cargos.items() if not otros_cargos_cobrados.get(n, False))

            resultado = calcular_ruta_setlogis(
                tipo_ruta            = tipo_ruta,
                modo                 = modo,
                origen               = normalizar(origen_usa),
                destino              = normalizar(destino_usa),
                cliente              = normalizar(cliente),
                miles_load           = miles_load,
                miles_empty          = miles_empty,
                short_miles          = short_miles,
                flete_usa            = flete_usd,
                fuel                 = fuel_usd,
                tipo_cruce           = tipo_cruce,
                tipo_carga_cruce     = tipo_carga,
                ingreso_cruce        = ing_cruce_usd,
                costo_cruce_externo  = costo_cruce_usd,
                ingreso_mx           = ing_mx_usd,
                costo_mx             = costo_mx_usd,
                extras_ingreso       = extras_ingreso,
                extras_costo         = extras_costo_puro,
                modo_costo_indirecto = modo_ci,
                valores              = valores,
                fuel_owner           = fuel_owner,
                incluye_cruce        = aplica_cruce and not es_empty,
            )

            # Campos extra para guardado y display
            resultado["Modalidad"]      = modalidad
            resultado["CXM_Flete_Cap"]  = safe(cxm_flete) if modalidad == "Desglosada" else 0.0
            resultado["CXM_Fuel_Cap"]   = safe(cxm_fuel)  if modalidad == "Desglosada" else 0.0
            resultado["Flete_Flat"]     = flete_usd        if modalidad == "Flat"       else 0.0

            id_ruta = generar_id_ruta(supabase) if supabase else "SL000000"

            st.session_state["sl_resultado"] = resultado
            st.session_state["sl_form_data"] = {
                "id_ruta":           id_ruta,
                "fecha":             str(fecha),
                "usuario":           nombre_usuario,
                "origen_mx":         normalizar(origen_mx),
                "destino_mx":        normalizar(destino_mx),
                "moneda_flete":      moneda_flete,
                "moneda_cruce":      moneda_cruce,
                "moneda_mx":         moneda_mx,
                "tipo_carga_cruce":  tipo_carga if aplica_cruce and not es_empty else "",
                "incluye_cruce":     aplica_cruce and not es_empty,
                "otros_cargos":      otros_cargos,
                "otros_cobrados":    otros_cargos_cobrados,
                "fuel_owner":        fuel_owner,
                "cxm_flete_cap":     safe(cxm_flete) if modalidad == "Desglosada" else 0.0,
                "cxm_fuel_cap":      safe(cxm_fuel)  if modalidad == "Desglosada" else 0.0,
            }

    # ── Mostrar resultado — idéntico a Lincoln: 1 línea ──────────────────────
    if st.session_state.get("sl_resultado"):
        r  = st.session_state["sl_resultado"]
        fd = st.session_state.get("sl_form_data", {})
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
                    _guardar_ruta(r, fd, supabase)
        with col_x:
            if st.button("🗑️ Descartar", use_container_width=True, key="sl_descartar"):
                st.session_state.pop("sl_resultado", None)
                st.session_state.pop("sl_form_data",  None)
                st.rerun()


# ─────────────────────────────────────────────
# GUARDAR EN SUPABASE
# ─────────────────────────────────────────────
def _guardar_ruta(r: dict, fd: dict, supabase) -> None:
    try:
        extras_db         = {
            f"Extra_{n.replace(' ','_')}": v
            for n, v in fd.get("otros_cargos", {}).items()
        }
        extras_cobrado_db = {
            f"Extra_{n.replace(' ','_')}_Cobrado": v
            for n, v in fd.get("otros_cobrados", {}).items()
        }

        fila = {
            "ID_Ruta":              fd["id_ruta"],
            "Fecha":                fd["fecha"],
            "Usuario":              fd["usuario"],
            "Tipo_Viaje":           r["Tipo_Viaje"],
            "Modo":                 r["Modo"],
            "Direccion":            r["Direccion"],
            "Modalidad":            r["Modalidad"],
            "Cliente":              r["Cliente"],
            "Origen":               r["Origen"],
            "Destino":              r["Destino"],
            "Origen_MX":            fd.get("origen_mx",  ""),
            "Destino_MX":           fd.get("destino_mx", ""),
            "Moneda_Flete":         fd.get("moneda_flete",  "USD"),
            "Moneda_Ingreso_Cruce": fd.get("moneda_cruce",  "USD"),
            "Moneda_MX":            fd.get("moneda_mx",     "MXP"),
            "Tipo_Carga_Cruce":     fd.get("tipo_carga_cruce", ""),
            "Incluye_Cruce":        fd.get("incluye_cruce", False),
            "Miles_Load":           r["Miles_Load"],
            "Miles_Empty":          r["Miles_Empty"],
            "Short_Miles":          r["Short_Miles"],
            "Millas_Totales":       r["Millas_Totales"],
            "CXM_Flete":            fd.get("cxm_flete_cap", 0.0),
            "CXM_Fuel":             fd.get("cxm_fuel_cap",  0.0),
            "Flete_Flat":           r.get("Flete_Flat", 0.0),
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
        log_accion("crear_ruta", {"id_ruta": fd["id_ruta"]})

        # Invalidar cache de ubicaciones para que aparezcan las nuevas
        cargar_pool_ubicaciones_setlogis.clear()

        st.session_state["sl_ruta_guardada_id"] = fd["id_ruta"]
        st.session_state["sl_mostrar_modal"]    = True
        st.session_state["sl_resultado"]        = None
        st.session_state["sl_form_data"]        = {}
        st.rerun()

    except Exception as ex:
        alert("error", f"❌ Error al guardar: {ex}")
