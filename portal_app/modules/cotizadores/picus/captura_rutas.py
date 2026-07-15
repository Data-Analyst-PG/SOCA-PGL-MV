"""
captura_rutas.py — Cotizador Picus
Homologado con Igloo / Lincoln:
  - Orden dinámico de secciones según obtener_config_tipo_ruta():
      IMPORTACION → Cruce primero, luego Ruta MX
      EXPORTACION → Ruta MX primero, luego Cruce
      VACIO       → solo Ruta MX (sin Cruce, sin indirectos)
  - Secciones extraídas como funciones: _panel_datos_generales(), _seccion_info_general(),
    _seccion_cruce(), _seccion_ruta_mx(), _seccion_costos_fijos(), _seccion_otros_costos(),
    _mostrar_resultados(), _guardar_ruta()
  - mostrar_resultados_picus() centraliza banner + KPIs + semáforos
  - Botón "Descartar" además de "Guardar Ruta"
  - Sin st.form — usa st.button + pic_form_key para reset
  - Sin HTML inline — todo vía ui/components.py
  - Picus conserva: Ruta_Tipo (Ruta Larga / Tramo), Modo de Viaje (Operador / Team) — NO tocar
"""
from __future__ import annotations

from datetime import datetime

import streamlit as st
from streamlit_searchbox import st_searchbox

from ui.components import section_header, alert, divider
from services.supabase_client import get_supabase_client, current_user
from ._helpers import (
    DEFAULTS, 
    TIPOS_RUTA,
    cargar_datos_generales, 
    guardar_datos_generales,
    safe_float,
    calcular_diesel, 
    calcular_sueldo_bono,
    calcular_costos_fijos, 
    calcular_extras,
    calcular_utilidades,
    generar_id_ruta,  
    get_profile_name, normalizar,
    now_iso, 
    _datos_generales_path,
    cargar_pool_ubicaciones_picus, 
    buscar_ubicacion_picus,
    obtener_config_tipo_ruta, 
    mostrar_resultados_picus,
    _get_last_id_picus_cached,
    log_accion,
)

TABLE_RUTAS = "Rutas_Picus"


# ─────────────────────────────────────────────
# MODAL CONFIRMACIÓN
# ─────────────────────────────────────────────
@st.dialog("✅ Ruta Guardada Exitosamente", width="small")
def _modal_guardado(id_ruta: str) -> None:
    alert("success", "**¡La ruta se guardó correctamente!**")
    st.info(f"### 🆔 ID de la ruta\n`{id_ruta}`")
    st.caption("Puedes consultarla en 'Consulta Ruta' o 'Gestión de Rutas'.")
    if st.button("✅ Aceptar", type="primary", use_container_width=True, key="pic_modal_ok"):
        st.session_state.pop("pic_ruta_guardada_id", None)
        st.session_state.pop("pic_mostrar_modal", None)
        st.session_state.pop("pic_datos_captura", None)
        st.session_state.pop("pic_calc", None)
        st.session_state["pic_revisar_ruta"] = False
        st.session_state["pic_form_key"] = st.session_state.get("pic_form_key", 0) + 1
        st.rerun()


# ─────────────────────────────────────────────
# PANEL PARÁMETROS
# ─────────────────────────────────────────────
def _panel_datos_generales(valores: dict) -> dict:
    with st.expander("⚙️ Configuración de Parámetros", expanded=False):
        tc_banxico = float(valores.get("Tipo de cambio USD", 17.5))
        st.caption(f"💱 Banxico FIX del día: **${tc_banxico:,.4f} MXP/USD** — se actualiza automáticamente cada 24h.")
        claves = list(DEFAULTS.keys())
        c1, c2 = st.columns(2)
        for i, key in enumerate(claves):
            col = c1 if i % 2 == 0 else c2
            valores[key] = col.number_input(
                key,
                value=float(valores.get(key, DEFAULTS[key])),
                step=0.1,
                key=f"pic_param_{key}",
            )
        pc1, pc2 = st.columns([1, 3])
        with pc1:
            if st.button("💾 Guardar parámetros", key="pic_guardar_params"):
                guardar_datos_generales(valores)
                alert("success", "✅ Parámetros guardados correctamente.")
        with pc2:
            st.caption(f"Archivo: `{_datos_generales_path()}`")
    return valores


# ─────────────────────────────────────────────
# INFORMACIÓN GENERAL
# ─────────────────────────────────────────────
def _seccion_info_general(fk: int) -> dict:
    st.markdown("### 📋 Información General")
    g1, g2, g3, g4, g5 = st.columns(5)
    fecha         = g1.date_input("📅 Fecha",          value=datetime.today(),              key=f"pic_fecha_{fk}")
    tipo          = g2.selectbox("🚛 Tipo de Ruta",    TIPOS_RUTA,                          key=f"pic_tipo_{fk}")
    ruta_tipo     = g3.selectbox("📌 Ruta Tipo",       ["Ruta Larga", "Tramo"],             key=f"pic_ruta_tipo_{fk}")
    cliente       = g4.text_input("🏢 Nombre Cliente", placeholder="NOMBRE DE LA EMPRESA",  key=f"pic_cliente_{fk}")
    modo_viaje_ui = g5.selectbox("👥 Modo de Viaje",   ["Operador", "Team"],                key=f"pic_modo_{fk}")
    return {
        "fecha": fecha, "tipo": tipo, "ruta_tipo": ruta_tipo,
        "cliente": cliente, "modo_viaje_ui": modo_viaje_ui,
    }


# ─────────────────────────────────────────────
# CRUCE
# ─────────────────────────────────────────────
def _seccion_cruce(fk: int) -> dict:
    st.markdown("### 🛂 Cruce")
    c1, c2, c3, c4 = st.columns(4)
    moneda_cruce       = c1.selectbox("Moneda Ingreso Cruce", ["MXP", "USD"], key=f"pic_mon_cruce_{fk}")
    ingreso_cruce      = c2.number_input("Ingreso Cruce",     min_value=0.0,  key=f"pic_ing_cruce_{fk}")
    moneda_costo_cruce = c3.selectbox("Moneda Costo Cruce",   ["MXP", "USD"], key=f"pic_mon_cc_{fk}")
    costo_cruce        = c4.number_input("Costo Cruce",       min_value=0.0,  key=f"pic_costo_cruce_{fk}")
    return {
        "moneda_cruce": moneda_cruce, "ingreso_cruce": ingreso_cruce,
        "moneda_costo_cruce": moneda_costo_cruce, "costo_cruce": costo_cruce,
    }


# ─────────────────────────────────────────────
# RUTA MEXICANA — Origen y Destino con autocomplete
# ─────────────────────────────────────────────
def _seccion_ruta_mx(fk: int) -> dict:
    st.markdown("### 🇲🇽 Ruta Mexicana")

    c1, c2 = st.columns(2)
    with c1:
        origen_sel = st_searchbox(
            buscar_ubicacion_picus,
            label="📍 Origen",
            placeholder="Escribe para buscar o capturar nueva...",
            key=f"pic_origen_{fk}",
            clear_on_submit=False,
        )
    with c2:
        destino_sel = st_searchbox(
            buscar_ubicacion_picus,
            label="📍 Destino",
            placeholder="Escribe para buscar o capturar nueva...",
            key=f"pic_destino_{fk}",
            clear_on_submit=False,
        )

    origen  = str(origen_sel  or "").strip()
    destino = str(destino_sel or "").strip()

    c1, c2, c3, c4 = st.columns(4)
    moneda_ingreso = c1.selectbox("Moneda Ingreso Flete", ["MXP", "USD"], key=f"pic_mon_flete_{fk}")
    ingreso_flete  = c2.number_input("Ingreso Flete",     min_value=0.0,  key=f"pic_ing_flete_{fk}")
    km             = c3.number_input("📏 Kilómetros",     min_value=0.0, step=10.0, key=f"pic_km_{fk}")
    casetas        = c4.number_input("🛣️ Casetas (MXP)",  min_value=0.0,  key=f"pic_casetas_{fk}")

    return {
        "origen": origen, "destino": destino,
        "moneda_ingreso": moneda_ingreso, "ingreso_flete": ingreso_flete,
        "km": km, "casetas": casetas,
    }


# ─────────────────────────────────────────────
# COSTOS FIJOS INTERNOS
# ─────────────────────────────────────────────
def _seccion_costos_fijos(fk: int) -> dict:
    st.markdown("### 🔒 Conceptos de Costos")
    st.caption("Estos costos siempre van al costo de la ruta y nunca se cobran al cliente.")
    f1, f2, f3, f4 = st.columns(4)
    movimiento_local = f1.number_input("🔄 Movimiento Local (MXP)", min_value=0.0, key=f"pic_mov_local_{fk}")
    puntualidad      = f2.number_input("⏰ Puntualidad (MXP)",      min_value=0.0, key=f"pic_puntualidad_{fk}")
    pension          = f3.number_input("🏨 Pensión (MXP)",           min_value=0.0, key=f"pic_pension_{fk}")
    estancia         = f4.number_input("🛌 Estancia (MXP)",          min_value=0.0, key=f"pic_estancia_{fk}")

    f1, f2, f3, f4 = st.columns(4)
    fianza = f1.number_input("🔒 Fianza (MXP)", min_value=0.0, key=f"pic_fianza_{fk}")
    f2.empty()
    f3.empty()
    f4.empty()

    return {
        "movimiento_local": movimiento_local, "puntualidad": puntualidad,
        "pension": pension, "estancia": estancia, "fianza": fianza,
    }


# ─────────────────────────────────────────────
# OTROS COSTOS — extras billables con checkbox de cobro
# ─────────────────────────────────────────────
def _seccion_otros_costos(fk: int) -> dict:
    st.markdown("### 🧾 Otros Costos")
    st.caption("Captura el monto. Marca **'cobro'** si también se le cobra al cliente (suma al ingreso).")

    o1, o2, o3 = st.columns(3)
    with o1:
        pistas_extra   = st.number_input("Pistas Extra (MXP)", min_value=0.0, key=f"pic_pistas_{fk}")
        pistas_cobrado = st.checkbox("cobro", key=f"pic_pistas_cob_{fk}")
    with o2:
        stop         = st.number_input("Stop (MXP)",   min_value=0.0, key=f"pic_stop_{fk}")
        stop_cobrado = st.checkbox("cobro",            key=f"pic_stop_cob_{fk}")
    with o3:
        falso         = st.number_input("Falso (MXP)", min_value=0.0, key=f"pic_falso_{fk}")
        falso_cobrado = st.checkbox("cobro",           key=f"pic_falso_cob_{fk}")

    o1, o2, o3 = st.columns(3)
    with o1:
        gatas         = st.number_input("Gatas (MXP)",      min_value=0.0, key=f"pic_gatas_{fk}")
        gatas_cobrado = st.checkbox("cobro",                key=f"pic_gatas_cob_{fk}")
    with o2:
        accesorios         = st.number_input("Accesorios (MXP)", min_value=0.0, key=f"pic_accesorios_{fk}")
        accesorios_cobrado = st.checkbox("cobro",                key=f"pic_accesorios_cob_{fk}")
    with o3:
        guias         = st.number_input("Guías (MXP)", min_value=0.0, key=f"pic_guias_{fk}")
        guias_cobrado = st.checkbox("cobro",           key=f"pic_guias_cob_{fk}")

    return {
        "pistas_extra": pistas_extra, "pistas_cobrado": pistas_cobrado,
        "stop": stop, "stop_cobrado": stop_cobrado,
        "falso": falso, "falso_cobrado": falso_cobrado,
        "gatas": gatas, "gatas_cobrado": gatas_cobrado,
        "accesorios": accesorios, "accesorios_cobrado": accesorios_cobrado,
        "guias": guias, "guias_cobrado": guias_cobrado,
    }


# ─────────────────────────────────────────────
# MOSTRAR RESULTADOS — centraliza banner + KPIs + semáforos
# ─────────────────────────────────────────────
def _mostrar_resultados(valores: dict) -> None:
    calc = st.session_state.get("pic_calc", {})
    d    = st.session_state.get("pic_datos_captura", {})
    if not calc or not d:
        return

    tc_usd = safe_float(valores.get("Tipo de cambio USD", 17.5))

    divider()

    util = calcular_utilidades(
        calc["ingreso_total"],
        calc["costo_total"],
        d.get("tipo", ""),
    )
    tc_val = tc_usd if d.get("moneda_ingreso") == "USD" else 0.0
    mostrar_resultados_picus(util, tc_usd=tc_val)


# ─────────────────────────────────────────────
# GUARDAR RUTA
# ─────────────────────────────────────────────
def _guardar_ruta(supabase, nombre_usuario: str) -> None:
    d    = st.session_state.get("pic_datos_captura", {})
    calc = st.session_state.get("pic_calc", {})
    if not d or not calc:
        alert("error", "No hay datos de captura.")
        return

    valores  = st.session_state.get("pic_valores_actuales", {})
    nuevo_id = generar_id_ruta()

    try:
        existe = supabase.table(TABLE_RUTAS).select("ID_Ruta").eq("ID_Ruta", nuevo_id).execute()
        if existe.data:
            _get_last_id_picus_cached.clear()
            alert("error", "⚠️ Conflicto al generar ID. Intenta de nuevo.")
            return
    except Exception as e:
        alert("error", f"❌ Error verificando ID: {e}")
        return

    nueva_ruta = {
        "ID_Ruta":                nuevo_id,
        "Fecha":                  str(d["fecha"]),
        "Tipo":                   d["tipo"],
        "Ruta_Tipo":              d["ruta_tipo"],
        "Cliente":                d["cliente"],
        "Origen":                 d["origen"],
        "Destino":                d["destino"],
        "Modo de Viaje":          calc["modo_viaje_calc"],
        "KM":                     d["km"],
        "Moneda":                 d["moneda_ingreso"],
        "Ingreso_Original":       d["ingreso_flete"],
        "Tipo de cambio":         calc["tipo_cambio_flete"],
        "Ingreso Flete":          calc["ingreso_flete_convertido"],
        "Moneda_Cruce":           d["moneda_cruce"],
        "Cruce_Original":         d["ingreso_cruce"],
        "Tipo cambio Cruce":      calc["tipo_cambio_cruce"],
        "Ingreso Cruce":          calc["ingreso_cruce_convertido"],
        "Moneda Costo Cruce":     d["moneda_costo_cruce"],
        "Costo Cruce":            d["costo_cruce"],
        "Costo Cruce Convertido": calc["costo_cruce_convertido"],
        "Ingreso Total":          calc["ingreso_total"],
        "Pago por KM":            calc["pago_km"],
        "Sueldo_Operador":        calc["sueldo"],
        "Bono":                   calc["bono"],
        "Casetas":                d["casetas"],
        "Movimiento_Local":       d["movimiento_local"],
        "Puntualidad":            d["puntualidad"],
        "Pension":                d["pension"],
        "Estancia":               d["estancia"],
        "Fianza":                 d["fianza"],
        "Pistas_Extra":           d["pistas_extra"],
        "Pistas_Cobrado":         d["pistas_cobrado"],
        "Stop":                   d["stop"],
        "Stop_Cobrado":           d["stop_cobrado"],
        "Falso":                  d["falso"],
        "Falso_Cobrado":          d["falso_cobrado"],
        "Gatas":                  d["gatas"],
        "Gatas_Cobrado":          d["gatas_cobrado"],
        "Accesorios":             d["accesorios"],
        "Accesorios_Cobrado":     d["accesorios_cobrado"],
        "Guias":                  d["guias"],
        "Guias_Cobrado":          d["guias_cobrado"],
        "Costo_Diesel_Camion":    calc["costo_diesel_camion"],
        "Costos_Fijos":           calc["costos_fijos"],
        "Costo_Extras":           calc["costo_extras"],
        "Ingresos_Extras":        calc["ingreso_extras"],
        "Costo_Total_Ruta":       calc["costo_total"],
        "Costo Diesel":           safe_float(valores.get("Costo Diesel", 24.0)),
        "Rendimiento Camion":     safe_float(valores.get("Rendimiento Camion", 2.5)),
        "created_by":             nombre_usuario,
        "created_at":             now_iso(),
        "updated_by":             None,
        "updated_at":             None,
        "historial":              [],
    }

    try:
        supabase.table(TABLE_RUTAS).insert(nueva_ruta).execute()
        _get_last_id_picus_cached.clear()
        cargar_pool_ubicaciones_picus.clear()  # refrescar pool con nuevas ubicaciones
        log_accion("crear_ruta", {"id_ruta": nuevo_id})
        st.session_state["pic_ruta_guardada_id"] = nuevo_id
        st.session_state["pic_mostrar_modal"]    = True
        st.rerun()
    except Exception as e:
        alert("error", f"❌ Error al guardar: {e}")


# ─────────────────────────────────────────────
# RENDER PRINCIPAL
# ─────────────────────────────────────────────
def render() -> None:
    supabase = get_supabase_client()
    if supabase is None:
        alert("warn", "⚠️ Supabase no configurado. Podrás revisar cálculos, pero NO guardar rutas en BD.")

    u              = current_user() or {}
    user_id        = u.get("id") or u.get("sub") or ""
    nombre_usuario = get_profile_name(user_id) or u.get("email") or "Desconocido"

    st.session_state.setdefault("pic_revisar_ruta", False)
    st.session_state.setdefault("pic_form_key", 0)

    # Modal si viene de un guardado previo
    if st.session_state.get("pic_mostrar_modal") and st.session_state.get("pic_ruta_guardada_id"):
        _modal_guardado(st.session_state["pic_ruta_guardada_id"])

    valores = cargar_datos_generales()
    valores = _panel_datos_generales(valores)
    st.session_state["pic_valores_actuales"] = valores  # usado en _guardar_ruta

    divider()
    section_header("🛣️", "Nueva Ruta")

    fk = st.session_state.get("pic_form_key", 0)

    # ── Info General siempre primera — define tipo → orden dinámico ──
    info      = _seccion_info_general(fk)
    tipo      = info["tipo"]
    ruta_tipo = info["ruta_tipo"]

    config = obtener_config_tipo_ruta(tipo)
    orden  = config.get("orden", ["ruta_mx"])

    datos_cruce = {"moneda_cruce": "MXP", "ingreso_cruce": 0.0, "moneda_costo_cruce": "MXP", "costo_cruce": 0.0}
    datos_mx    = {}

    for seccion in orden:
        divider()
        if seccion == "cruce":
            datos_cruce = _seccion_cruce(fk)
        elif seccion == "ruta_mx":
            datos_mx = _seccion_ruta_mx(fk)

    divider()
    datos_costos_fijos = _seccion_costos_fijos(fk)

    divider()
    datos_otros = _seccion_otros_costos(fk)

    st.write("")

    # ══════════════════════════════════════════════════════════════
    # BOTÓN REVISAR
    # ══════════════════════════════════════════════════════════════
    divider()
    if st.button("🔍 Revisar Ruta", use_container_width=True, type="primary", key=f"pic_revisar_btn_{fk}"):
        origen  = datos_mx.get("origen", "")
        destino = datos_mx.get("destino", "")
        if not origen:
            alert("error", "⚠️ El campo Origen es obligatorio.")
            st.stop()
        if not destino:
            alert("error", "⚠️ El campo Destino es obligatorio.")
            st.stop()

        km             = datos_mx["km"]
        casetas        = datos_mx["casetas"]
        moneda_ingreso = datos_mx["moneda_ingreso"]
        ingreso_flete  = datos_mx["ingreso_flete"]

        moneda_cruce       = datos_cruce["moneda_cruce"]
        ingreso_cruce      = datos_cruce["ingreso_cruce"]
        moneda_costo_cruce = datos_cruce["moneda_costo_cruce"]
        costo_cruce        = datos_cruce["costo_cruce"]

        movimiento_local = datos_costos_fijos["movimiento_local"]
        puntualidad      = datos_costos_fijos["puntualidad"]
        pension          = datos_costos_fijos["pension"]
        estancia         = datos_costos_fijos["estancia"]
        fianza           = datos_costos_fijos["fianza"]

        pistas_extra, pistas_cobrado = datos_otros["pistas_extra"], datos_otros["pistas_cobrado"]
        stop, stop_cobrado           = datos_otros["stop"], datos_otros["stop_cobrado"]
        falso, falso_cobrado         = datos_otros["falso"], datos_otros["falso_cobrado"]
        gatas, gatas_cobrado         = datos_otros["gatas"], datos_otros["gatas_cobrado"]
        accesorios, accesorios_cobrado = datos_otros["accesorios"], datos_otros["accesorios_cobrado"]
        guias, guias_cobrado         = datos_otros["guias"], datos_otros["guias_cobrado"]

        tc_usd = safe_float(valores.get("Tipo de cambio USD", 17.5))
        tc_mxp = safe_float(valores.get("Tipo de cambio MXP", 1.0))

        tipo_cambio_flete       = tc_usd if moneda_ingreso     == "USD" else tc_mxp
        tipo_cambio_cruce       = tc_usd if moneda_cruce       == "USD" else tc_mxp
        tipo_cambio_costo_cruce = tc_usd if moneda_costo_cruce == "USD" else tc_mxp

        ingreso_flete_convertido = ingreso_flete * tipo_cambio_flete
        ingreso_cruce_convertido = ingreso_cruce * tipo_cambio_cruce
        costo_cruce_convertido   = costo_cruce   * tipo_cambio_costo_cruce

        costo_diesel_camion = calcular_diesel(km, valores)

        sb              = calcular_sueldo_bono(km, tipo, ruta_tipo, info["modo_viaje_ui"], valores)
        sueldo          = sb["sueldo"]
        bono            = sb["bono"]
        modo_viaje_calc = sb["modo_viaje_calc"]
        pago_km         = sb["pago_km"]

        costos_fijos = calcular_costos_fijos(
            movimiento_local, puntualidad, pension, estancia, fianza,
        )

        extras_result  = calcular_extras(
            pistas_extra, stop, falso, gatas, accesorios, guias,
            pistas_cobrado, stop_cobrado, falso_cobrado,
            gatas_cobrado, accesorios_cobrado, guias_cobrado,
        )
        costo_extras   = extras_result["costo_extras"]
        ingreso_extras = extras_result["ingreso_extras"]

        ingreso_total = ingreso_flete_convertido + ingreso_cruce_convertido + ingreso_extras
        costo_total   = (
            costo_diesel_camion
            + sueldo
            + bono
            + casetas
            + costos_fijos
            + costo_extras
            + costo_cruce_convertido
        )

        st.session_state["pic_revisar_ruta"]  = True
        st.session_state["pic_datos_captura"] = {
            "fecha":               info["fecha"],
            "tipo":                tipo,
            "ruta_tipo":           ruta_tipo,
            "cliente":             normalizar(info["cliente"]),
            "origen":              normalizar(origen),
            "destino":             normalizar(destino),
            "modo_viaje_ui":       info["modo_viaje_ui"],
            "km":                  km,
            "moneda_ingreso":      moneda_ingreso,
            "ingreso_flete":       ingreso_flete,
            "moneda_cruce":        moneda_cruce,
            "ingreso_cruce":       ingreso_cruce,
            "moneda_costo_cruce":  moneda_costo_cruce,
            "costo_cruce":         costo_cruce,
            "casetas":             casetas,
            "movimiento_local":    movimiento_local,
            "puntualidad":         puntualidad,
            "pension":             pension,
            "estancia":            estancia,
            "fianza":              fianza,
            "pistas_extra":        pistas_extra,
            "pistas_cobrado":      pistas_cobrado,
            "stop":                stop,
            "stop_cobrado":        stop_cobrado,
            "falso":               falso,
            "falso_cobrado":       falso_cobrado,
            "gatas":               gatas,
            "gatas_cobrado":       gatas_cobrado,
            "accesorios":          accesorios,
            "accesorios_cobrado":  accesorios_cobrado,
            "guias":               guias,
            "guias_cobrado":       guias_cobrado,
        }
        st.session_state["pic_calc"] = {
            "modo_viaje_calc":           modo_viaje_calc,
            "pago_km":                   pago_km,
            "sueldo":                    sueldo,
            "bono":                      bono,
            "costo_diesel_camion":       costo_diesel_camion,
            "costos_fijos":              costos_fijos,
            "costo_extras":              costo_extras,
            "ingreso_extras":            ingreso_extras,
            "tipo_cambio_flete":         tipo_cambio_flete,
            "tipo_cambio_cruce":         tipo_cambio_cruce,
            "tipo_cambio_costo_cruce":   tipo_cambio_costo_cruce,
            "ingreso_flete_convertido":  ingreso_flete_convertido,
            "ingreso_cruce_convertido":  ingreso_cruce_convertido,
            "costo_cruce_convertido":    costo_cruce_convertido,
            "ingreso_total":             ingreso_total,
            "costo_total":               costo_total,
        }
        st.rerun()

    # ══════════════════════════════════════════════════════════════
    # RESULTADOS + GUARDAR / DESCARTAR
    # ══════════════════════════════════════════════════════════════
    if st.session_state.get("pic_revisar_ruta"):
        _mostrar_resultados(valores)

        c1, c2 = st.columns(2)
        with c1:
            if st.button("💾 Guardar Ruta", type="primary", use_container_width=True, key="pic_save_route"):
                if supabase is None:
                    alert("error", "Supabase no está configurado. No se puede guardar en BD.")
                else:
                    _guardar_ruta(supabase, nombre_usuario)
        with c2:
            if st.button("🗑️ Descartar", use_container_width=True, key="pic_descartar"):
                st.session_state["pic_revisar_ruta"] = False
                st.session_state.pop("pic_datos_captura", None)
                st.session_state.pop("pic_calc", None)
                st.session_state["pic_form_key"] = st.session_state.get("pic_form_key", 0) + 1
                st.rerun()
