"""
pruebas_router.py — Módulo Sandbox
Prueba de captura de rutas Igloo con autocomplete en Origen/Destino.
Usa st_searchbox en lugar de st.form para permitir sugerencias mientras se escribe.
Los prefijos de session_state son "prb_" para no colisionar con el cotizador real.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone

import streamlit as st
from streamlit_searchbox import st_searchbox

from services.supabase_client import get_supabase_client, get_authed_client, current_user
from ui.components import page_banner, section_header, alert, divider

from modules.cotizadores.igloo.helpers import (
    DEFAULTS, TIPOS_RUTA,
    cargar_datos_generales, guardar_datos_generales,
    safe_number, safe_float,
    calcular_sueldo_y_bono, calcular_diesel,
    calcular_costos_fijos, calcular_extras,
    calcular_utilidades, mostrar_resultados_utilidad,
    _datos_generales_path,
)


TABLE_RUTAS = "Rutas"


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _get_profile_name(user_id: str) -> str:
    if not user_id:
        return ""
    try:
        res = get_authed_client().table("profiles").select("full_name").eq("user_id", user_id).single().execute()
        return (res.data or {}).get("full_name") or ""
    except Exception:
        return ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@st.cache_data(show_spinner=False, ttl=60)
def _get_last_id_cached(table_name: str):
    sb = get_supabase_client()
    if sb is None:
        return None
    resp = sb.table(table_name).select("ID_Ruta").order("ID_Ruta", desc=True).limit(1).execute()
    return resp.data[0].get("ID_Ruta") if resp.data else None


def generar_nuevo_id() -> str:
    ultimo = _get_last_id_cached(TABLE_RUTAS)
    if ultimo and isinstance(ultimo, str) and len(ultimo) >= 3:
        try:
            numero = int(ultimo[2:]) + 1
        except Exception:
            numero = 1
    else:
        numero = 1
    return f"IG{numero:06d}"


def normalizar_texto(texto: str) -> str:
    if not texto:
        return ""
    texto = str(texto).upper().strip()
    texto = re.sub(r'\s+', ' ', texto)
    texto = re.sub(r'\s*,\s*', ', ', texto)
    return texto


# ─────────────────────────────────────────────
# POOL DE UBICACIONES (Origen + Destino unidos)
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=120)
def _cargar_pool_ubicaciones() -> list[str]:
    """
    Une y deduplica todos los valores de Origen y Destino de la tabla Rutas.
    Así si "Laredo, TX" solo existe como Origen, también aparece al escribir en Destino.
    """
    sb = get_supabase_client()
    if sb is None:
        return []
    try:
        resp = sb.table(TABLE_RUTAS).select("Origen, Destino").execute()
        ubicaciones: set[str] = set()
        for row in (resp.data or []):
            o = (row.get("Origen") or "").strip().upper()
            d = (row.get("Destino") or "").strip().upper()
            if o:
                ubicaciones.add(o)
            if d:
                ubicaciones.add(d)
        return sorted(ubicaciones)
    except Exception:
        return []


def _buscar_ubicacion(termino: str) -> list[str]:
    """
    Filtra el pool por lo que el usuario está escribiendo.
    Si no hay coincidencias, devuelve el término mismo como opción
    para que el usuario pueda confirmar una ubicación nueva.
    """
    if not termino or len(termino) < 2:
        return []
    termino_upper = termino.upper()
    pool = _cargar_pool_ubicaciones()
    coincidencias = [u for u in pool if termino_upper in u]
    if not coincidencias:
        # Permitir capturar texto libre devolviendo el mismo término como opción
        return [termino_upper]
    return coincidencias


# ─────────────────────────────────────────────
# MODAL CONFIRMACIÓN
# ─────────────────────────────────────────────
@st.dialog("✅ Ruta Guardada Exitosamente", width="small")
def _modal_guardado(id_ruta: str) -> None:
    alert("success", "**¡La ruta se guardó correctamente!**")
    st.info(f"### 🆔 ID de la ruta\n`{id_ruta}`")
    st.caption("Puedes consultar esta ruta en 'Gestión de Rutas' o 'Consulta Individual'.")
    if st.button("✅ Aceptar", type="primary", use_container_width=True, key="prb_modal_ok"):
        for k in ["prb_ruta_guardada_id", "prb_mostrar_modal", "prb_datos_captura", "prb_calc"]:
            st.session_state.pop(k, None)
        st.session_state["prb_revisar_ruta"] = False
        st.session_state["prb_form_key"] = st.session_state.get("prb_form_key", 0) + 1
        st.rerun()


# ─────────────────────────────────────────────
# RENDER PRINCIPAL
# ─────────────────────────────────────────────
def render():
    page_banner("🧪", "Módulo de Pruebas", "Sandbox de desarrollo — solo acceso autorizado")

    supabase = get_supabase_client()
    if supabase is None:
        alert("warn", "⚠️ Supabase no configurado.")
        return

    u = current_user() or {}
    user_id        = u.get("id") or u.get("sub") or ""
    nombre_usuario = _get_profile_name(user_id) or u.get("email") or "Desconocido"

    st.session_state.setdefault("prb_revisar_ruta", False)
    st.session_state.setdefault("prb_form_key", 0)

    if st.session_state.get("prb_mostrar_modal") and st.session_state.get("prb_ruta_guardada_id"):
        _modal_guardado(st.session_state["prb_ruta_guardada_id"])

    valores = cargar_datos_generales()

    # ── Parámetros ────────────────────────────────────────────────
    with st.expander("⚙️ Configuración de Parámetros", expanded=False):
        col1, col2, col3 = st.columns(3)
        claves = list(DEFAULTS.keys())
        for i, key in enumerate(claves):
            col = [col1, col2, col3][i % 3]
            valores[key] = col.number_input(
                key,
                value=float(valores.get(key, DEFAULTS[key])),
                step=0.1,
                key=f"prb_gen_{key}",
            )
        if st.button("💾 Guardar Parámetros", key="prb_save_gen"):
            guardar_datos_generales(valores)
            alert("success", "✅ Parámetros guardados correctamente.")
        st.caption(f"Archivo: `{_datos_generales_path()}`")

    divider()
    section_header("🛣️", "Nueva Ruta — Prueba Autocomplete")
    st.caption("🔍 En Origen y Destino verás sugerencias de ubicaciones ya registradas. Puedes seleccionar una o escribir una nueva.")

    # ── Usamos form_key para poder resetear widgets después de guardar ──
    fk = st.session_state.get("prb_form_key", 0)

    # ══════════════════════════════════════════════════════════════
    # SECCIÓN: INFORMACIÓN GENERAL
    # ══════════════════════════════════════════════════════════════
    st.markdown("### 📋 Información General")
    c1, c2, c3, c4 = st.columns(4)
    fecha      = c1.date_input("📅 Fecha",          value=datetime.today(), key=f"prb_fecha_{fk}")
    tipo       = c2.selectbox("🚛 Tipo de Ruta",    TIPOS_RUTA,             key=f"prb_tipo_{fk}")
    cliente    = c3.text_input("🏢 Nombre Cliente", placeholder="NOMBRE DE LA EMPRESA", key=f"prb_cliente_{fk}")
    modo_viaje = c4.selectbox("👥 Modo de Viaje",   ["Sencillo", "Team"],   key=f"prb_modo_{fk}")

    # ══════════════════════════════════════════════════════════════
    # SECCIÓN: CRUCE
    # ══════════════════════════════════════════════════════════════
    st.markdown("### 🛂 Cruce")
    c1, c2, c3, c4 = st.columns(4)
    moneda_cruce       = c1.selectbox("Moneda Ingreso Cruce", ["MXP", "USD"], key=f"prb_mon_cruce_{fk}")
    ingreso_cruce      = c2.number_input("Ingreso Cruce",     min_value=0.0,  key=f"prb_ing_cruce_{fk}")
    moneda_costo_cruce = c3.selectbox("Moneda Costo Cruce",   ["MXP", "USD"], key=f"prb_mon_cc_{fk}")
    costo_cruce        = c4.number_input("Costo Cruce",       min_value=0.0,  key=f"prb_cc_{fk}")

    # ══════════════════════════════════════════════════════════════
    # SECCIÓN: RUTA MEXICANA — con searchbox en Origen y Destino
    # ══════════════════════════════════════════════════════════════
    st.markdown("### 🇲🇽 Ruta Mexicana")

    c1, c2 = st.columns(2)
    with c1:
        origen_sel = st_searchbox(
            _buscar_ubicacion,
            label="📍 Origen",
            placeholder="Escribe para buscar o capturar nueva...",
            key=f"prb_origen_{fk}",
            clear_on_submit=False,
        )
    with c2:
        destino_sel = st_searchbox(
            _buscar_ubicacion,
            label="📍 Destino",
            placeholder="Escribe para buscar o capturar nueva...",
            key=f"prb_destino_{fk}",
            clear_on_submit=False,
        )

    # st_searchbox devuelve None si no seleccionaron nada del dropdown,
    # pero el texto escrito queda en el widget — lo recuperamos del session_state
    origen  = str(origen_sel  or "").strip()
    destino = str(destino_sel or "").strip()

    c1, c2, c3, c4 = st.columns(4)
    moneda_ingreso = c1.selectbox("Moneda Ingreso Flete", ["MXP", "USD"], key=f"prb_mon_ing_{fk}")
    ingreso_flete  = c2.number_input("Ingreso Flete",     min_value=0.0,  key=f"prb_ing_flete_{fk}")
    km             = c3.number_input("📏 Kilómetros",     min_value=0.0,  key=f"prb_km_{fk}")
    casetas        = c4.number_input("🛣️ Casetas (MXP)",  min_value=0.0,  key=f"prb_casetas_{fk}")

    if tipo == "DOM MEX":
        c1, _, _, _ = st.columns(4)
        modo_pago_dom = c1.selectbox(
            "Modo pago operador",
            ["km", "fijo"],
            format_func=lambda x: "Por kilómetro" if x == "km" else "Pago fijo",
            key=f"prb_modo_pago_dom_{fk}",
        )
    else:
        modo_pago_dom = "km"

    # ══════════════════════════════════════════════════════════════
    # SECCIÓN: TERMO Y COSTOS FIJOS
    # ══════════════════════════════════════════════════════════════
    st.markdown("### 🌡️ Termo y Conceptos de Costos")
    c1, c2, c3, c4 = st.columns(4)
    horas_termo      = c1.number_input("⏱️ Horas Termo",            min_value=0.0, key=f"prb_horas_{fk}")
    lavado_termo     = c2.number_input("🧼 Lavado Termo (MXP)",     min_value=0.0, key=f"prb_lav_{fk}")
    movimiento_local = c3.number_input("🔄 Movimiento Local (MXP)", min_value=0.0, key=f"prb_mov_{fk}")
    puntualidad      = c4.number_input("⏰ Puntualidad (MXP)",      min_value=0.0, key=f"prb_punt_{fk}")

    c1, c2, c3, c4 = st.columns(4)
    pension      = c1.number_input("🏨 Pensión (MXP)",      min_value=0.0, key=f"prb_pens_{fk}")
    estancia     = c2.number_input("🛌 Estancia (MXP)",     min_value=0.0, key=f"prb_est_{fk}")
    fianza_termo = c3.number_input("🔒 Fianza Termo (MXP)", min_value=0.0, key=f"prb_fianza_{fk}")
    renta_termo  = c4.number_input("📦 Renta Termo (MXP)",  min_value=0.0, key=f"prb_renta_{fk}")

    # ══════════════════════════════════════════════════════════════
    # SECCIÓN: OTROS COSTOS
    # ══════════════════════════════════════════════════════════════
    st.markdown("### 🧾 Otros Costos")
    st.caption("Captura el monto. Marca **'cobro'** si también se le cobra al cliente (suma al ingreso).")

    c1, c2, c3 = st.columns(3)
    with c1:
        pistas_extra = st.number_input("Pistas Extra (MXP)", min_value=0.0, key=f"prb_pistas_{fk}")
        cobra_pistas = st.checkbox("cobro", key=f"prb_cobra_pistas_{fk}")
    with c2:
        stop         = st.number_input("Stop (MXP)",         min_value=0.0, key=f"prb_stop_{fk}")
        cobra_stop   = st.checkbox("cobro", key=f"prb_cobra_stop_{fk}")
    with c3:
        falso        = st.number_input("Falso (MXP)",        min_value=0.0, key=f"prb_falso_{fk}")
        cobra_falso  = st.checkbox("cobro", key=f"prb_cobra_falso_{fk}")

    c1, c2, c3 = st.columns(3)
    with c1:
        gatas        = st.number_input("Gatas (MXP)",        min_value=0.0, key=f"prb_gatas_{fk}")
        cobra_gatas  = st.checkbox("cobro", key=f"prb_cobra_gatas_{fk}")
    with c2:
        accesorios   = st.number_input("Accesorios (MXP)",   min_value=0.0, key=f"prb_acc_{fk}")
        cobra_acc    = st.checkbox("cobro", key=f"prb_cobra_acc_{fk}")
    with c3:
        guias        = st.number_input("Guías (MXP)",        min_value=0.0, key=f"prb_guias_{fk}")
        cobra_guias  = st.checkbox("cobro", key=f"prb_cobra_guias_{fk}")

    st.write("")

    # ══════════════════════════════════════════════════════════════
    # BOTÓN REVISAR (reemplaza form_submit_button)
    # ══════════════════════════════════════════════════════════════
    if st.button("🔍 Revisar Ruta", type="primary", use_container_width=True, key=f"prb_revisar_{fk}"):
        if not origen:
            alert("error", "⚠️ El campo Origen es obligatorio.")
            st.stop()
        if not destino:
            alert("error", "⚠️ El campo Destino es obligatorio.")
            st.stop()

        cliente_norm = normalizar_texto(cliente)
        origen_norm  = normalizar_texto(origen)
        destino_norm = normalizar_texto(destino)

        st.session_state["prb_revisar_ruta"]  = True
        st.session_state["prb_datos_captura"] = {
            "fecha":              fecha,
            "tipo":               tipo,
            "cliente":            cliente_norm,
            "origen":             origen_norm,
            "destino":            destino_norm,
            "modo_viaje":         modo_viaje,
            "km":                 km,
            "moneda_ingreso":     moneda_ingreso,
            "ingreso_flete":      ingreso_flete,
            "moneda_cruce":       moneda_cruce,
            "ingreso_cruce":      ingreso_cruce,
            "moneda_costo_cruce": moneda_costo_cruce,
            "costo_cruce":        costo_cruce,
            "horas_termo":        horas_termo,
            "lavado_termo":       lavado_termo,
            "movimiento_local":   movimiento_local,
            "puntualidad":        puntualidad,
            "pension":            pension,
            "estancia":           estancia,
            "fianza_termo":       fianza_termo,
            "renta_termo":        renta_termo,
            "casetas":            casetas,
            "pistas_extra":       pistas_extra,
            "cobra_pistas":       cobra_pistas,
            "stop":               stop,
            "cobra_stop":         cobra_stop,
            "falso":              falso,
            "cobra_falso":        cobra_falso,
            "gatas":              gatas,
            "cobra_gatas":        cobra_gatas,
            "accesorios":         accesorios,
            "cobra_acc":          cobra_acc,
            "guias":              guias,
            "cobra_guias":        cobra_guias,
            "modo_pago_dom":      modo_pago_dom,
        }
        st.rerun()

    # ══════════════════════════════════════════════════════════════
    # CÁLCULOS AL REVISAR
    # ══════════════════════════════════════════════════════════════
    if st.session_state.get("prb_revisar_ruta", False):
        d      = st.session_state["prb_datos_captura"]
        tc_usd = safe_float(valores.get("Tipo de cambio USD", 19.5), 19.5)

        costo_cruce_convertido = d["costo_cruce"] * (tc_usd if d["moneda_costo_cruce"] == "USD" else 1)

        pago_km, sueldo, bono = calcular_sueldo_y_bono(
            d["tipo"], d["km"], d["modo_viaje"], valores,
            modo_pago_dom=d.get("modo_pago_dom", "km"),
        )

        factor         = 2 if d["modo_viaje"] == "Team" else 1
        puntualidad_val = d["puntualidad"] * factor

        diesel_camion, diesel_termo = calcular_diesel(d["km"], d["horas_termo"], valores)

        costos_fijos = calcular_costos_fijos(
            d["lavado_termo"], d["movimiento_local"], puntualidad_val,
            d["pension"], d["estancia"], d["fianza_termo"], d["renta_termo"], d["casetas"],
        )

        extras = calcular_extras(
            d["pistas_extra"], d["stop"], d["falso"],
            d["gatas"], d["accesorios"], d["guias"],
        )

        ingreso_extras_cobrados = (
            (d["pistas_extra"] if d["cobra_pistas"] else 0.0) +
            (d["stop"]         if d["cobra_stop"]   else 0.0) +
            (d["falso"]        if d["cobra_falso"]  else 0.0) +
            (d["gatas"]        if d["cobra_gatas"]  else 0.0) +
            (d["accesorios"]   if d["cobra_acc"]    else 0.0) +
            (d["guias"]        if d["cobra_guias"]  else 0.0)
        )

        ingreso_flete_conv = d["ingreso_flete"] * (tc_usd if d["moneda_ingreso"] == "USD" else 1)
        ingreso_cruce_conv = d["ingreso_cruce"] * (tc_usd if d["moneda_cruce"]   == "USD" else 1)
        ingreso_total      = ingreso_flete_conv + ingreso_cruce_conv + ingreso_extras_cobrados

        costo_total = (
            diesel_camion + diesel_termo + sueldo + bono +
            costos_fijos  + extras       + costo_cruce_convertido
        )

        util = calcular_utilidades(ingreso_total, costo_total, d["tipo"])

        st.session_state["prb_calc"] = {
            "ingreso_cruce_convertido":  ingreso_cruce_conv,
            "costo_cruce_convertido":    costo_cruce_convertido,
            "ingreso_extras_cobrados":   ingreso_extras_cobrados,
            "ingreso_total":             ingreso_total,
            "costo_diesel_camion":       diesel_camion,
            "costo_diesel_termo":        diesel_termo,
            "pago_km":                   pago_km,
            "sueldo":                    sueldo,
            "bono":                      bono,
            "puntualidad_val":           puntualidad_val,
            "costos_fijos":              costos_fijos,
            "extras":                    extras,
            "costo_total":               costo_total,
            "costos_indirectos":         util["costos_indirectos"],
            "utilidad_bruta":            util["utilidad_bruta"],
            "utilidad_neta":             util["utilidad_neta"],
            "porcentaje_bruta":          util["porcentaje_bruta"],
            "porcentaje_neta":           util["porcentaje_neta"],
        }

        divider()
        mostrar_resultados_utilidad(
            st, ingreso_total, costo_total,
            util["utilidad_bruta"], util["costos_indirectos"],
            util["utilidad_neta"], util["porcentaje_bruta"], util["porcentaje_neta"],
            tipo=d["tipo"],
            tc_usd=tc_usd,
        )

    # ══════════════════════════════════════════════════════════════
    # GUARDAR
    # ══════════════════════════════════════════════════════════════
    if st.session_state.get("prb_revisar_ruta", False):
        if st.button("💾 Guardar Ruta", key="prb_save_route"):
            d    = st.session_state.get("prb_datos_captura", {})
            calc = st.session_state.get("prb_calc", {})
            if not d:
                alert("error", "No hay datos de captura.")
                return

            nuevo_id = generar_nuevo_id()
            existe   = supabase.table(TABLE_RUTAS).select("ID_Ruta").eq("ID_Ruta", nuevo_id).execute()
            if existe.data:
                _get_last_id_cached.clear()
                alert("error", "⚠️ Conflicto al generar ID. Intenta de nuevo.")
                return

            tc_usd = safe_float(valores.get("Tipo de cambio USD", 19.5), 19.5)

            nueva_ruta = {
                "ID_Ruta":                nuevo_id,
                "Fecha":                  str(d["fecha"]),
                "Tipo":                   d["tipo"],
                "Cliente":                d["cliente"],
                "Origen":                 d["origen"],
                "Destino":                d["destino"],
                "Modo de Viaje":          d["modo_viaje"],
                "KM":                     d["km"],
                "Moneda":                 d["moneda_ingreso"],
                "Tipo de cambio":         tc_usd,
                "Ingreso_Original":       d["ingreso_flete"],
                "Ingreso Flete":          d["ingreso_flete"] * (tc_usd if d["moneda_ingreso"] == "USD" else 1),
                "Moneda_Cruce":           d["moneda_cruce"],
                "Cruce_Original":         d["ingreso_cruce"],
                "Ingreso Cruce":          calc.get("ingreso_cruce_convertido"),
                "Moneda Costo Cruce":     d["moneda_costo_cruce"],
                "Costo Cruce":            d["costo_cruce"],
                "Costo Cruce Convertido": calc.get("costo_cruce_convertido"),
                "Ingreso Total":          calc.get("ingreso_total"),
                "Sueldo_Operador":        calc.get("sueldo"),
                "Pago por KM":            calc.get("pago_km"),
                "Bono":                   calc.get("bono"),
                "Casetas":                d["casetas"],
                "Horas_Termo":            d["horas_termo"],
                "Lavado_Termo":           d["lavado_termo"],
                "Movimiento_Local":       d["movimiento_local"],
                "Puntualidad":            calc.get("puntualidad_val"),
                "Pension":                d["pension"],
                "Estancia":               d["estancia"],
                "Fianza_Termo":           d["fianza_termo"],
                "Renta_Termo":            d["renta_termo"],
                "Pistas_Extra":           d["pistas_extra"],
                "Stop":                   d["stop"],
                "Falso":                  d["falso"],
                "Gatas":                  d["gatas"],
                "Accesorios":             d["accesorios"],
                "Guias":                  d["guias"],
                "Costo_Diesel_Camion":    calc.get("costo_diesel_camion"),
                "Costo_Diesel_Termo":     calc.get("costo_diesel_termo"),
                "Costo_Extras":           calc.get("extras"),
                "Costo_Total_Ruta":       calc.get("costo_total"),
                "Costos_Indirectos":      calc.get("costos_indirectos"),
                "Utilidad_Bruta":         calc.get("utilidad_bruta"),
                "Utilidad_Neta":          calc.get("utilidad_neta"),
                "Porcentaje_Utilidad_Bruta": calc.get("porcentaje_bruta"),
                "Porcentaje_Utilidad_Neta":  calc.get("porcentaje_neta"),
                "Modo_Pago_Dom":          d.get("modo_pago_dom", "km"),
                "Cobra_Pistas":           d["cobra_pistas"],
                "Cobra_Stop":             d["cobra_stop"],
                "Cobra_Falso":            d["cobra_falso"],
                "Cobra_Gatas":            d["cobra_gatas"],
                "Cobra_Accesorios":       d["cobra_acc"],
                "Cobra_Guias":            d["cobra_guias"],
                "Extras_Cobrados":        False,
                "Rendimiento Camion":     float(valores.get("Rendimiento Camion", 2.5)),
                "Rendimiento Termo":      float(valores.get("Rendimiento Termo", 3.0)),
                "Costo Diesel":           float(valores.get("Costo Diesel", 24.0)),
                "created_by":             nombre_usuario,
                "created_at":             _now_iso(),
                "updated_by":             None,
                "updated_at":             None,
                "historial":              [],
            }

            try:
                supabase.table(TABLE_RUTAS).insert(nueva_ruta).execute()
                _get_last_id_cached.clear()
                # Invalidar el pool de ubicaciones para que incluya las nuevas
                _cargar_pool_ubicaciones.clear()
                st.session_state["prb_ruta_guardada_id"] = nuevo_id
                st.session_state["prb_mostrar_modal"]    = True
                st.rerun()
            except Exception as e:
                alert("error", f"❌ Error al guardar ruta: {e}")
                st.exception(e)
