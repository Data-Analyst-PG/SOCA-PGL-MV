"""
captura_rutas.py — Cotizador Picus
Diseño homologado con Igloo / Lincoln:
  - Sin st.title(), sin DEFAULTS locales, sin lógica de cálculo inline
  - Toda la lógica centralizada en helpers.py
  - Costos fijos separados (mov. local, puntualidad, pension, estancia, fianza)
  - Casetas en bloque de ruta (junto con KM)
  - Extras billables con checkbox individual por concepto
  - Modo "Team" en lugar de "Operador" / "Team"
  - section_header, kpi_row, semaforos_ruta de components.py
  - Modal @st.dialog para confirmación de guardado
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

import streamlit as st

from services.supabase_client import get_supabase_client, get_authed_client, current_user
from ui.components import section_header, alert, divider

from .helpers import (
    DEFAULTS,
    TIPOS_RUTA,
    cargar_datos_generales,
    guardar_datos_generales,
    safe_number,
    safe_float,
    calcular_diesel,
    calcular_sueldo_bono,
    calcular_costos_fijos,
    calcular_extras,
    calcular_utilidades,
    mostrar_resultados_utilidad,
    _datos_generales_path,
)


# ─────────────────────────────────────────────
# Utilidades internas
# ─────────────────────────────────────────────

def _get_profile_name(user_id: str) -> str:
    if not user_id:
        return ""
    try:
        supabase = get_authed_client()
        res = supabase.table("profiles").select("full_name").eq("user_id", user_id).single().execute()
        return (res.data or {}).get("full_name") or ""
    except Exception:
        return ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@st.cache_data(show_spinner=False, ttl=60)
def _get_last_id_cached() -> str | None:
    supabase = get_supabase_client()
    if supabase is None:
        return None
    resp = supabase.table("Rutas_Picus").select("ID_Ruta").order("ID_Ruta", desc=True).limit(1).execute()
    if resp.data:
        return resp.data[0].get("ID_Ruta")
    return None


def _generar_nuevo_id() -> str:
    ultimo = _get_last_id_cached()
    if ultimo and isinstance(ultimo, str) and len(ultimo) >= 4:
        try:
            numero = int(str(ultimo)[3:]) + 1
        except Exception:
            numero = 1
    else:
        numero = 1
    return f"PIC{numero:06d}"


def _normalizar(texto: str) -> str:
    if not texto:
        return ""
    texto = str(texto).upper().strip()
    texto = re.sub(r'\s+', ' ', texto)
    texto = re.sub(r'\s*,\s*', ', ', texto)
    return texto


# ─────────────────────────────────────────────
# Modal de confirmación
# ─────────────────────────────────────────────

@st.dialog("✅ Ruta Guardada Exitosamente", width="small")
def _modal_guardado(id_ruta: str) -> None:
    alert("success", "**¡La ruta se guardó correctamente!**")
    st.info(f"### 🆔 ID de la ruta\n`{id_ruta}`")
    st.caption("Puedes consultarla en 'Consulta Ruta' o 'Gestión de Rutas'.")
    if st.button("✅ Aceptar", type="primary", use_container_width=True, key="pic_modal_ok"):
        st.session_state.pop("pic_ruta_guardada_id", None)
        st.session_state.pop("pic_mostrar_modal", None)
        st.session_state["pic_form_key"] = st.session_state.get("pic_form_key", 0) + 1
        st.rerun()


# ─────────────────────────────────────────────
# Render principal
# ─────────────────────────────────────────────

def render() -> None:
    supabase = get_supabase_client()
    if supabase is None:
        alert("warn", "⚠️ Supabase no configurado. Podrás revisar cálculos, pero NO guardar rutas en BD.")

    u = current_user() or {}
    user_id       = u.get("id") or u.get("sub") or ""
    nombre_usuario = _get_profile_name(user_id) or u.get("email") or "Desconocido"

    # Modal si viene de un guardado previo
    if st.session_state.get("pic_mostrar_modal"):
        _modal_guardado(st.session_state["pic_ruta_guardada_id"])

    valores = cargar_datos_generales()

    # ── Configuración de Parámetros ──────────────────────────────────
    with st.expander("⚙️ Configuración de Parámetros", expanded=False):
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

    divider()
    section_header("🛣️", "Nueva Ruta")

    form_key = f"pic_captura_{st.session_state.get('pic_form_key', 0)}"

    with st.form(form_key):

        # ── Información General ──────────────────────────────────────
        st.markdown("### 📋 Información General")
        g1, g2, g3, g4 = st.columns(4)
        fecha         = g1.date_input("📅 Fecha", value=datetime.today(), key="pic_fecha")
        tipo          = g2.selectbox("🚛 Tipo de Ruta", TIPOS_RUTA, key="pic_tipo")
        ruta_tipo     = g3.selectbox("📌 Ruta Tipo", ["Ruta Larga", "Tramo"], key="pic_ruta_tipo")
        modo_viaje_ui = g4.selectbox("👥 Modo de Viaje", ["Operador", "Team"], key="pic_modo")

        divider()

        # ── Datos del Cliente ────────────────────────────────────────
        st.markdown("### 🏢 Cliente y Ruta")
        d1, d2, d3 = st.columns(3)
        cliente = d1.text_input("🏢 Nombre Cliente", placeholder="NOMBRE DE LA EMPRESA", key="pic_cliente")
        origen  = d2.text_input("📍 Origen",  placeholder="CIUDAD, ESTADO", key="pic_origen")
        destino = d3.text_input("📍 Destino", placeholder="CIUDAD, ESTADO", key="pic_destino")

        divider()

        # ── Ruta y Kilómetros ────────────────────────────────────────
        st.markdown("### 🛣️ Kilómetros y Casetas")
        r1, r2, r3, r4 = st.columns(4)
        km      = r1.number_input("📏 Kilómetros", min_value=0.0, step=10.0, key="pic_km")
        casetas = r2.number_input("🚧 Casetas (MXP)", min_value=0.0, key="pic_casetas")
        r3.empty()
        r4.empty()

        divider()

        # ── Cruce ───────────────────────────────────────────────────
        st.markdown("### 🛂 Cruce")
        c1, c2, c3, c4 = st.columns(4)
        moneda_ingreso  = c1.selectbox("Moneda Ingreso Flete", ["MXP", "USD"], key="pic_mon_flete")
        ingreso_flete   = c2.number_input("Ingreso Flete", min_value=0.0, key="pic_ing_flete")
        moneda_cruce    = c3.selectbox("Moneda Ingreso Cruce", ["MXP", "USD"], key="pic_mon_cruce")
        ingreso_cruce   = c4.number_input("Ingreso Cruce", min_value=0.0, key="pic_ing_cruce")

        cc1, cc2, cc3, cc4 = st.columns(4)
        moneda_costo_cruce = cc1.selectbox("Moneda Costo Cruce", ["MXP", "USD"], key="pic_mon_costo_cruce")
        costo_cruce        = cc2.number_input("Costo Cruce", min_value=0.0, key="pic_costo_cruce")
        cc3.empty()
        cc4.empty()

        divider()

        # ── Costos Fijos (nunca se cobran) ───────────────────────────
        st.markdown("### 🔒 Costos Fijos Internos")
        st.caption("Estos costos siempre van al costo de la ruta y nunca se cobran al cliente.")
        f1, f2, f3, f4, f5 = st.columns(5)
        movimiento_local = f1.number_input("Movimiento Local (MXP)", min_value=0.0, key="pic_mov_local")
        puntualidad      = f2.number_input("Puntualidad (MXP)",       min_value=0.0, key="pic_puntualidad")
        pension          = f3.number_input("Pensión (MXP)",            min_value=0.0, key="pic_pension")
        estancia         = f4.number_input("Estancia (MXP)",           min_value=0.0, key="pic_estancia")
        fianza           = f5.number_input("Fianza (MXP)",             min_value=0.0, key="pic_fianza")

        divider()

        # ── Costos Extras Billables ──────────────────────────────────
        st.markdown("### 🧾 Costos Extras")
        st.caption("Marca el checkbox si el costo fue cobrado al cliente — se suma al ingreso.")

        e1, e2, e3, e4 = st.columns(4)

        with e1:
            pistas_extra    = st.number_input("Pistas Extra (MXP)", min_value=0.0, key="pic_pistas")
            pistas_cobrado  = st.checkbox("Cobrado al cliente", key="pic_pistas_cob")

        with e2:
            stop            = st.number_input("Stop (MXP)", min_value=0.0, key="pic_stop")
            stop_cobrado    = st.checkbox("Cobrado al cliente", key="pic_stop_cob")

        with e3:
            falso           = st.number_input("Falso (MXP)", min_value=0.0, key="pic_falso")
            falso_cobrado   = st.checkbox("Cobrado al cliente", key="pic_falso_cob")

        with e4:
            gatas           = st.number_input("Gatas (MXP)", min_value=0.0, key="pic_gatas")
            gatas_cobrado   = st.checkbox("Cobrado al cliente", key="pic_gatas_cob")

        e5, e6, e7, e8 = st.columns(4)

        with e5:
            accesorios          = st.number_input("Accesorios (MXP)", min_value=0.0, key="pic_accesorios")
            accesorios_cobrado  = st.checkbox("Cobrado al cliente", key="pic_accesorios_cob")

        with e6:
            guias           = st.number_input("Guías (MXP)", min_value=0.0, key="pic_guias")
            guias_cobrado   = st.checkbox("Cobrado al cliente", key="pic_guias_cob")

        e7.empty()
        e8.empty()

        divider()
        revisar = st.form_submit_button("🔍 Revisar Ruta", use_container_width=True, type="primary")

    # ── Cálculo al presionar Revisar ─────────────────────────────────
    if revisar:
        st.session_state["pic_revisar_ruta"] = True

        tc_usd = safe_float(valores.get("Tipo de cambio USD", 17.5))
        tc_mxp = safe_float(valores.get("Tipo de cambio MXP", 1.0))

        tipo_cambio_flete      = tc_usd if moneda_ingreso    == "USD" else tc_mxp
        tipo_cambio_cruce      = tc_usd if moneda_cruce      == "USD" else tc_mxp
        tipo_cambio_costo_cruce = tc_usd if moneda_costo_cruce == "USD" else tc_mxp

        costo_cruce_convertido      = costo_cruce * tipo_cambio_costo_cruce
        ingreso_flete_convertido    = ingreso_flete * tipo_cambio_flete
        ingreso_cruce_convertido    = ingreso_cruce * tipo_cambio_cruce

        costo_diesel_camion = calcular_diesel(km, valores)

        sb = calcular_sueldo_bono(km, tipo, ruta_tipo, modo_viaje_ui, valores)
        sueldo          = sb["sueldo"]
        bono            = sb["bono"]
        modo_viaje_calc = sb["modo_viaje_calc"]
        pago_km         = sb["pago_km"]

        costos_fijos = calcular_costos_fijos(
            movimiento_local, puntualidad, pension, estancia, fianza,
        )

        extras_result = calcular_extras(
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

        util = calcular_utilidades(ingreso_total, costo_total, tipo)

        st.session_state["pic_datos_captura"] = {
            "fecha":              fecha,
            "tipo":               tipo,
            "ruta_tipo":          ruta_tipo,
            "cliente":            _normalizar(cliente),
            "origen":             _normalizar(origen),
            "destino":            _normalizar(destino),
            "modo_viaje_ui":      modo_viaje_ui,
            "km":                 km,
            "moneda_ingreso":     moneda_ingreso,
            "ingreso_flete":      ingreso_flete,
            "moneda_cruce":       moneda_cruce,
            "ingreso_cruce":      ingreso_cruce,
            "moneda_costo_cruce": moneda_costo_cruce,
            "costo_cruce":        costo_cruce,
            "casetas":            casetas,
            "movimiento_local":   movimiento_local,
            "puntualidad":        puntualidad,
            "pension":            pension,
            "estancia":           estancia,
            "fianza":             fianza,
            "pistas_extra":       pistas_extra,
            "pistas_cobrado":     pistas_cobrado,
            "stop":               stop,
            "stop_cobrado":       stop_cobrado,
            "falso":              falso,
            "falso_cobrado":      falso_cobrado,
            "gatas":              gatas,
            "gatas_cobrado":      gatas_cobrado,
            "accesorios":         accesorios,
            "accesorios_cobrado": accesorios_cobrado,
            "guias":              guias,
            "guias_cobrado":      guias_cobrado,
        }

        st.session_state["pic_calc"] = {
            "modo_viaje_calc":          modo_viaje_calc,
            "pago_km":                  pago_km,
            "sueldo":                   sueldo,
            "bono":                     bono,
            "costo_diesel_camion":      costo_diesel_camion,
            "costos_fijos":             costos_fijos,
            "costo_extras":             costo_extras,
            "ingreso_extras":           ingreso_extras,
            "tipo_cambio_flete":        tipo_cambio_flete,
            "tipo_cambio_cruce":        tipo_cambio_cruce,
            "tipo_cambio_costo_cruce":  tipo_cambio_costo_cruce,
            "ingreso_flete_convertido": ingreso_flete_convertido,
            "ingreso_cruce_convertido": ingreso_cruce_convertido,
            "costo_cruce_convertido":   costo_cruce_convertido,
            "ingreso_total":            ingreso_total,
            "costo_total":              costo_total,
            "utilidad_bruta":           util["utilidad_bruta"],
            "costos_indirectos":        util["costos_indirectos"],
            "utilidad_neta":            util["utilidad_neta"],
            "porcentaje_bruta":         util["porcentaje_bruta"],
            "porcentaje_neta":          util["porcentaje_neta"],
        }

    # ── Mostrar resultados ────────────────────────────────────────────
    if st.session_state.get("pic_revisar_ruta"):
        calc = st.session_state.get("pic_calc", {})
        if not calc:
            return

        d   = st.session_state.get("pic_datos_captura", {})
        tc_usd = safe_float(valores.get("Tipo de cambio USD", 17.5))

        divider()
        section_header("📊", "Resultado de la Ruta")

        mostrar_resultados_utilidad(
            st,
            calc["ingreso_total"],
            calc["costo_total"],
            calc["utilidad_bruta"],
            calc["costos_indirectos"],
            calc["utilidad_neta"],
            calc["porcentaje_bruta"],
            calc["porcentaje_neta"],
            tipo=d.get("tipo", ""),
            tc_usd=tc_usd if d.get("moneda_ingreso") == "USD" else 0.0,
        )

        # ── Guardar Ruta ──────────────────────────────────────────────
        if st.button("💾 Guardar Ruta", key="pic_save_route", type="primary"):
            if supabase is None:
                alert("error", "Supabase no está configurado. No se puede guardar en BD.")
                return

            nuevo_id = _generar_nuevo_id()

            try:
                existe = supabase.table("Rutas_Picus").select("ID_Ruta").eq("ID_Ruta", nuevo_id).execute()
                if existe.data:
                    _get_last_id_cached.clear()
                    alert("error", "⚠️ Conflicto al generar ID. Intenta de nuevo.")
                    return
            except Exception:
                pass

            nueva_ruta = {
                "ID_Ruta":              nuevo_id,
                "Fecha":                str(d["fecha"]),
                "Tipo":                 d["tipo"],
                "Ruta_Tipo":            d["ruta_tipo"],
                "Cliente":              d["cliente"],
                "Origen":               d["origen"],
                "Destino":              d["destino"],
                "Modo de Viaje":        calc["modo_viaje_calc"],
                "KM":                   d["km"],
                "Moneda":               d["moneda_ingreso"],
                "Ingreso_Original":     d["ingreso_flete"],
                "Tipo de cambio":       calc["tipo_cambio_flete"],
                "Ingreso Flete":        calc["ingreso_flete_convertido"],
                "Moneda_Cruce":         d["moneda_cruce"],
                "Cruce_Original":       d["ingreso_cruce"],
                "Tipo cambio Cruce":    calc["tipo_cambio_cruce"],
                "Ingreso Cruce":        calc["ingreso_cruce_convertido"],
                "Moneda Costo Cruce":   d["moneda_costo_cruce"],
                "Costo Cruce":          d["costo_cruce"],
                "Costo Cruce Convertido": calc["costo_cruce_convertido"],
                "Ingreso Total":        calc["ingreso_total"],
                "Pago por KM":          calc["pago_km"],
                "Sueldo_Operador":      calc["sueldo"],
                "Bono":                 calc["bono"],
                "Casetas":              d["casetas"],
                "Movimiento_Local":     d["movimiento_local"],
                "Puntualidad":          d["puntualidad"],
                "Pension":              d["pension"],
                "Estancia":             d["estancia"],
                "Fianza":               d["fianza"],
                "Pistas_Extra":         d["pistas_extra"],
                "Pistas_Cobrado":       d["pistas_cobrado"],
                "Stop":                 d["stop"],
                "Stop_Cobrado":         d["stop_cobrado"],
                "Falso":                d["falso"],
                "Falso_Cobrado":        d["falso_cobrado"],
                "Gatas":                d["gatas"],
                "Gatas_Cobrado":        d["gatas_cobrado"],
                "Accesorios":           d["accesorios"],
                "Accesorios_Cobrado":   d["accesorios_cobrado"],
                "Guias":                d["guias"],
                "Guias_Cobrado":        d["guias_cobrado"],
                "Costo_Diesel_Camion":  calc["costo_diesel_camion"],
                "Costos_Fijos":         calc["costos_fijos"],
                "Costo_Extras":         calc["costo_extras"],
                "Ingresos_Extras":      calc["ingreso_extras"],
                "Costo_Total_Ruta":     calc["costo_total"],
                "Costo Diesel":         safe_float(valores.get("Costo Diesel", 24.0)),
                "Rendimiento Camion":   safe_float(valores.get("Rendimiento Camion", 2.5)),
                # Auditoría
                "created_by":   nombre_usuario,
                "created_at":   _now_iso(),
                "updated_by":   None,
                "updated_at":   None,
                "historial":    [],
            }

            try:
                supabase.table("Rutas_Picus").insert(nueva_ruta).execute()
                _get_last_id_cached.clear()
                st.session_state["pic_ruta_guardada_id"] = nuevo_id
                st.session_state["pic_mostrar_modal"]    = True
                st.session_state.pop("pic_revisar_ruta", None)
                st.session_state.pop("pic_datos_captura", None)
                st.session_state.pop("pic_calc", None)
                st.rerun()
            except Exception as e:
                alert("error", f"❌ Error al guardar: {e}")
