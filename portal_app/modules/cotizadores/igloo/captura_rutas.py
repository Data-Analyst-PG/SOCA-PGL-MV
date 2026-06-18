"""
captura_rutas.py — Cotizador Igloo
Layout homologado con Lincoln:
  - st.markdown("### emoji Título") para secciones dentro del form
  - Cruce: Moneda Ing | Ingreso | Moneda Costo | Costo
  - Ruta MX fila 1: Origen | Destino con st_searchbox (autocomplete + texto libre)
  - Ruta MX fila 2: Moneda Flete | Ingreso Flete | Kilómetros | Casetas
  - Otros Costos: 3 cols con concepto + checkbox cobro
  - Checkboxes individuales por extra
  - "Sencillo" en lugar de "Operador"
  - Sin st.title()
  - Sin st.form — usa st.button + igloo_form_key para reset
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone

import streamlit as st
from streamlit_searchbox import st_searchbox

from services.supabase_client import get_supabase_client, get_authed_client, current_user
from .helpers import (
    DEFAULTS, TIPOS_RUTA,
    cargar_datos_generales, guardar_datos_generales,
    safe_number, safe_float,
    calcular_sueldo_y_bono, calcular_diesel,
    calcular_costos_fijos, calcular_extras,
    calcular_utilidades,
    generar_nuevo_id, get_profile_name, normalizar_texto,
    _datos_generales_path,
    cargar_pool_ubicaciones_igloo,
    buscar_ubicacion_igloo,
)
from ui.components import section_header, alert, divider, mostrar_resultados_ruta


# ─────────────────────────────────────────────
# Fecha Automatica
# ─────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────
# MODAL CONFIRMACIÓN
# ─────────────────────────────────────────────
@st.dialog("✅ Ruta Guardada Exitosamente", width="small")
def _modal_guardado(id_ruta: str) -> None:
    alert("success", "**¡La ruta se guardó correctamente!**")
    st.info(f"### 🆔 ID de la ruta\n`{id_ruta}`")
    st.caption("Puedes consultar esta ruta en 'Gestión de Rutas' o 'Consulta Individual'.")
    if st.button("✅ Aceptar", type="primary", use_container_width=True, key="igloo_modal_ok"):
        st.session_state.pop("igloo_ruta_guardada_id", None)
        st.session_state.pop("igloo_mostrar_modal", None)
        st.session_state.pop("igloo_datos_captura", None)
        st.session_state.pop("igloo_calc", None)
        st.session_state.igloo_revisar_ruta = False
        st.session_state["igloo_form_key"] = st.session_state.get("igloo_form_key", 0) + 1
        st.rerun()


# ─────────────────────────────────────────────
# RENDER PRINCIPAL
# ─────────────────────────────────────────────
def render():
    supabase = get_supabase_client()
    if supabase is None:
        alert("warn", "⚠️ Supabase no configurado. No se pueden guardar rutas.")
        return

    u = current_user() or {}
    user_id        = u.get("id") or u.get("sub") or ""
    nombre_usuario = get_profile_name(user_id) or u.get("email") or "Desconocido"

    TABLE_RUTAS = "Rutas"

    st.session_state.setdefault("igloo_revisar_ruta", False)
    st.session_state.setdefault("igloo_form_key", 0)

    if st.session_state.get("igloo_mostrar_modal") and st.session_state.get("igloo_ruta_guardada_id"):
        _modal_guardado(st.session_state["igloo_ruta_guardada_id"])

    valores = cargar_datos_generales()

    # ── Parámetros ────────────────────────────────────────────────
    with st.expander("⚙️ Configuración de Parámetros", expanded=False):
        tc_banxico = float(valores.get("Tipo de cambio USD", 19.5))
        st.caption(f"💱 Banxico FIX del día: **${tc_banxico:,.4f} MXP/USD** — se actualiza automáticamente cada 24h.")
        col1, col2, col3 = st.columns(3)
        claves = list(DEFAULTS.keys())
        for i, key in enumerate(claves):
            col = [col1, col2, col3][i % 3]
            valores[key] = col.number_input(
                key,
                value=float(valores.get(key, DEFAULTS[key])),
                step=0.1,
                key=f"igloo_gen_{key}",
            )
        if st.button("💾 Guardar Parámetros", key="igloo_save_gen"):
            guardar_datos_generales(valores)
            alert("success", "✅ Parámetros guardados correctamente.")
        st.caption(f"Archivo: `{_datos_generales_path()}`")

    divider()
    section_header("🛣️", "Nueva Ruta")

    # form_key para resetear widgets después de guardar
    fk = st.session_state.get("igloo_form_key", 0)

    # ══════════════════════════════════════════════════════════════
    # INFORMACIÓN GENERAL
    # ══════════════════════════════════════════════════════════════
    st.markdown("### 📋 Información General")
    c1, c2, c3, c4 = st.columns(4)
    fecha      = c1.date_input("📅 Fecha",          value=datetime.today(),       key=f"igloo_fecha_{fk}")
    tipo       = c2.selectbox("🚛 Tipo de Ruta",    TIPOS_RUTA,                   key=f"igloo_tipo_{fk}")
    cliente    = c3.text_input("🏢 Nombre Cliente", placeholder="NOMBRE DE LA EMPRESA", key=f"igloo_cliente_{fk}")
    modo_viaje = c4.selectbox("👥 Modo de Viaje",   ["Sencillo", "Team"],         key=f"igloo_modo_{fk}")

    # ══════════════════════════════════════════════════════════════
    # CRUCE
    # ══════════════════════════════════════════════════════════════
    st.markdown("### 🛂 Cruce")
    c1, c2, c3, c4 = st.columns(4)
    moneda_cruce       = c1.selectbox("Moneda Ingreso Cruce", ["MXP", "USD"], key=f"igloo_mon_cruce_{fk}")
    ingreso_cruce      = c2.number_input("Ingreso Cruce",     min_value=0.0,  key=f"igloo_ing_cruce_{fk}")
    moneda_costo_cruce = c3.selectbox("Moneda Costo Cruce",   ["MXP", "USD"], key=f"igloo_mon_cc_{fk}")
    costo_cruce        = c4.number_input("Costo Cruce",       min_value=0.0,  key=f"igloo_cc_{fk}")

    # ══════════════════════════════════════════════════════════════
    # RUTA MEXICANA — Origen y Destino con autocomplete
    # ══════════════════════════════════════════════════════════════
    st.markdown("### 🇲🇽 Ruta Mexicana")

    c1, c2 = st.columns(2)
    with c1:
        origen_sel = st_searchbox(
            _buscar_ubicacion_igloo,
            label="📍 Origen",
            placeholder="Escribe para buscar o capturar nueva...",
            key=f"igloo_origen_{fk}",
            clear_on_submit=False,
        )
    with c2:
        destino_sel = st_searchbox(
            _buscar_ubicacion_igloo,
            label="📍 Destino",
            placeholder="Escribe para buscar o capturar nueva...",
            key=f"igloo_destino_{fk}",
            clear_on_submit=False,
        )

    origen  = str(origen_sel  or "").strip()
    destino = str(destino_sel or "").strip()

    c1, c2, c3, c4 = st.columns(4)
    moneda_ingreso = c1.selectbox("Moneda Ingreso Flete", ["MXP", "USD"], key=f"igloo_mon_ing_{fk}")
    ingreso_flete  = c2.number_input("Ingreso Flete",     min_value=0.0,  key=f"igloo_ing_flete_{fk}")
    km             = c3.number_input("📏 Kilómetros",     min_value=0.0,  key=f"igloo_km_{fk}")
    casetas        = c4.number_input("🛣️ Casetas (MXP)",  min_value=0.0,  key=f"igloo_casetas_{fk}")

    if tipo == "DOM MEX":
        c1, _, _, _ = st.columns(4)
        modo_pago_dom = c1.selectbox(
            "Modo pago operador",
            ["km", "fijo"],
            format_func=lambda x: "Por kilómetro" if x == "km" else "Pago fijo",
            key=f"igloo_modo_pago_dom_{fk}",
        )
    else:
        modo_pago_dom = "km"

    # ══════════════════════════════════════════════════════════════
    # TERMO Y COSTOS FIJOS
    # ══════════════════════════════════════════════════════════════
    st.markdown("### 🌡️ Termo y Conceptos de Costos")
    c1, c2, c3, c4 = st.columns(4)
    horas_termo      = c1.number_input("⏱️ Horas Termo",            min_value=0.0, key=f"igloo_horas_{fk}")
    lavado_termo     = c2.number_input("🧼 Lavado Termo (MXP)",     min_value=0.0, key=f"igloo_lav_{fk}")
    movimiento_local = c3.number_input("🔄 Movimiento Local (MXP)", min_value=0.0, key=f"igloo_mov_{fk}")
    puntualidad      = c4.number_input("⏰ Puntualidad (MXP)",      min_value=0.0, key=f"igloo_punt_{fk}")

    c1, c2, c3, c4 = st.columns(4)
    pension      = c1.number_input("🏨 Pensión (MXP)",      min_value=0.0, key=f"igloo_pens_{fk}")
    estancia     = c2.number_input("🛌 Estancia (MXP)",     min_value=0.0, key=f"igloo_est_{fk}")
    fianza_termo = c3.number_input("🔒 Fianza Termo (MXP)", min_value=0.0, key=f"igloo_fianza_{fk}")
    renta_termo  = c4.number_input("📦 Renta Termo (MXP)",  min_value=0.0, key=f"igloo_renta_{fk}")

    # ══════════════════════════════════════════════════════════════
    # OTROS COSTOS
    # ══════════════════════════════════════════════════════════════
    st.markdown("### 🧾 Otros Costos")
    st.caption("Captura el monto. Marca **'cobro'** si también se le cobra al cliente (suma al ingreso).")

    c1, c2, c3 = st.columns(3)
    with c1:
        pistas_extra = st.number_input("Pistas Extra (MXP)", min_value=0.0, key=f"igloo_pistas_{fk}")
        cobra_pistas = st.checkbox("cobro", key=f"igloo_cobra_pistas_{fk}")
    with c2:
        stop         = st.number_input("Stop (MXP)",         min_value=0.0, key=f"igloo_stop_{fk}")
        cobra_stop   = st.checkbox("cobro", key=f"igloo_cobra_stop_{fk}")
    with c3:
        falso        = st.number_input("Falso (MXP)",        min_value=0.0, key=f"igloo_falso_{fk}")
        cobra_falso  = st.checkbox("cobro", key=f"igloo_cobra_falso_{fk}")

    c1, c2, c3 = st.columns(3)
    with c1:
        gatas        = st.number_input("Gatas (MXP)",        min_value=0.0, key=f"igloo_gatas_{fk}")
        cobra_gatas  = st.checkbox("cobro", key=f"igloo_cobra_gatas_{fk}")
    with c2:
        accesorios   = st.number_input("Accesorios (MXP)",   min_value=0.0, key=f"igloo_acc_{fk}")
        cobra_acc    = st.checkbox("cobro", key=f"igloo_cobra_acc_{fk}")
    with c3:
        guias        = st.number_input("Guías (MXP)",        min_value=0.0, key=f"igloo_guias_{fk}")
        cobra_guias  = st.checkbox("cobro", key=f"igloo_cobra_guias_{fk}")

    st.write("")

    # ══════════════════════════════════════════════════════════════
    # BOTÓN REVISAR (reemplaza form_submit_button)
    # ══════════════════════════════════════════════════════════════
    if st.button("🔍 Revisar Ruta", type="primary", use_container_width=True, key=f"igloo_revisar_{fk}"):
        if not origen:
            alert("error", "⚠️ El campo Origen es obligatorio.")
            st.stop()
        if not destino:
            alert("error", "⚠️ El campo Destino es obligatorio.")
            st.stop()

        cliente_norm = normalizar_texto(cliente)
        origen_norm  = normalizar_texto(origen)
        destino_norm = normalizar_texto(destino)

        st.session_state.igloo_revisar_ruta  = True
        st.session_state.igloo_datos_captura = {
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
    if st.session_state.get("igloo_revisar_ruta", False):
        d      = st.session_state.igloo_datos_captura
        tc_usd = safe_float(valores.get("Tipo de cambio USD", 19.5), 19.5)

        costo_cruce_convertido = d["costo_cruce"] * (tc_usd if d["moneda_costo_cruce"] == "USD" else 1)

        pago_km, sueldo, bono = calcular_sueldo_y_bono(
            d["tipo"], d["km"], d["modo_viaje"], valores,
            modo_pago_dom=d.get("modo_pago_dom", "km"),
        )

        factor          = 2 if d["modo_viaje"] == "Team" else 1
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

        st.session_state.igloo_calc = {
            "ingreso_flete_convertido":  ingreso_flete_conv,
            "tipo_cambio_flete":         tc_usd,
            "tipo_cambio_cruce":         tc_usd,
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

        mostrar_resultados_ruta(util)

    # ══════════════════════════════════════════════════════════════
    # GUARDAR
    # ══════════════════════════════════════════════════════════════
    if st.session_state.get("igloo_revisar_ruta", False):
        if st.button("💾 Guardar Ruta", key="igloo_save_route"):
            d    = st.session_state.get("igloo_datos_captura", {})
            calc = st.session_state.get("igloo_calc", {})
            if not d:
                alert("error", "No hay datos de captura.")
                return

            nuevo_id = generar_nuevo_id(TABLE_RUTAS)
            existe   = supabase.table(TABLE_RUTAS).select("ID_Ruta").eq("ID_Ruta", nuevo_id).execute()
            if existe.data:
                _get_last_id_igloo_cached.clear()
                alert("error", "⚠️ Conflicto al generar ID. Intenta de nuevo.")
                return

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
                "Ingreso_Original":       d["ingreso_flete"],
                "Tipo de cambio":         calc.get("tipo_cambio_flete"),
                "Ingreso Flete":          calc.get("ingreso_flete_convertido"),
                "Moneda_Cruce":           d["moneda_cruce"],
                "Cruce_Original":         d["ingreso_cruce"],
                "Tipo cambio Cruce":      calc.get("tipo_cambio_cruce"),
                "Ingreso Cruce":          calc.get("ingreso_cruce_convertido"),
                "Moneda Costo Cruce":     d["moneda_costo_cruce"],
                "Costo Cruce":            d["costo_cruce"],
                "Costo Cruce Convertido": calc.get("costo_cruce_convertido"),
                "Ingreso Total":          calc.get("ingreso_total"),
                "Pago por KM":            calc.get("pago_km"),
                "Sueldo_Operador":        calc.get("sueldo"),
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
                # Cobros individuales
                "Cobra_Pistas":           d.get("cobra_pistas",  False),
                "Cobra_Stop":             d.get("cobra_stop",    False),
                "Cobra_Falso":            d.get("cobra_falso",   False),
                "Cobra_Gatas":            d.get("cobra_gatas",   False),
                "Cobra_Accesorios":       d.get("cobra_acc",     False),
                "Cobra_Guias":            d.get("cobra_guias",   False),
                # Legacy conservada
                "Extras_Cobrados":        False,
                # Parámetros guardados con la ruta
                "Costo Diesel":           float(valores.get("Costo Diesel", 24.0)),
                "Rendimiento Camion":     float(valores.get("Rendimiento Camion", 2.5)),
                "Rendimiento Termo":      float(valores.get("Rendimiento Termo", 3.0)),
                "created_by":             nombre_usuario,
                "created_at":             _now_iso(),
                "updated_by":             None,
                "updated_at":             None,
                "historial":              [],
            }

            try:
                supabase.table(TABLE_RUTAS).insert(nueva_ruta).execute()
                _get_last_id_igloo_cached.clear()
                # Refrescar pool para incluir las nuevas ubicaciones
                _cargar_pool_ubicaciones.clear()
                st.session_state.igloo_ruta_guardada_id = nuevo_id
                st.session_state.igloo_mostrar_modal    = True
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error al guardar ruta: {e}")
                st.exception(e)
