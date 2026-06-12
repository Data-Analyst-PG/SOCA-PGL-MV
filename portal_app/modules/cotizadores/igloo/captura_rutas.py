"""
captura_rutas.py — Cotizador Igloo
Layout limpio homologado con Lincoln y Set Logis:
  - Un solo section_header fuera del form
  - Secciones internas con st.caption() como separador ligero
  - Checkboxes individuales por extra
  - "Sencillo" en lugar de "Operador"
  - Sin st.title()
"""

import os
import re
from datetime import datetime, timezone

import streamlit as st

from services.supabase_client import get_supabase_client, get_authed_client, current_user
from ui.components import section_header, alert, divider

from .helpers import (
    DEFAULTS, TIPOS_RUTA,
    cargar_datos_generales, guardar_datos_generales,
    safe_number, safe_float,
    calcular_sueldo_y_bono, calcular_diesel,
    calcular_costos_fijos, calcular_extras,
    calcular_utilidades, mostrar_resultados_utilidad,
    _datos_generales_path,
)


# ─────────────────────────────────────────────
# HELPERS
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
def _get_last_id_cached(table_name: str):
    supabase = get_supabase_client()
    if supabase is None:
        return None
    resp = supabase.table(table_name).select("ID_Ruta").order("ID_Ruta", desc=True).limit(1).execute()
    if resp.data:
        return resp.data[0].get("ID_Ruta")
    return None


def generar_nuevo_id(table_name: str) -> str:
    ultimo = _get_last_id_cached(table_name)
    if ultimo and isinstance(ultimo, str) and len(ultimo) >= 3:
        try:
            numero = int(ultimo[2:]) + 1
        except Exception:
            numero = 1
    else:
        numero = 1
    return f"IG{numero:06d}"


def normalizar_texto(texto):
    if not texto:
        return ""
    texto = str(texto).upper().strip()
    texto = re.sub(r'\s+', ' ', texto)
    texto = re.sub(r'\s*,\s*', ', ', texto)
    return texto


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
    nombre_usuario = _get_profile_name(user_id) or u.get("email") or "Desconocido"

    TABLE_RUTAS = "Rutas"

    st.session_state.setdefault("igloo_revisar_ruta", False)

    if st.session_state.get("igloo_mostrar_modal") and st.session_state.get("igloo_ruta_guardada_id"):
        _modal_guardado(st.session_state["igloo_ruta_guardada_id"])

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
                key=f"igloo_gen_{key}",
            )
        if st.button("💾 Guardar Parámetros", key="igloo_save_gen"):
            guardar_datos_generales(valores)
            alert("success", "✅ Parámetros guardados correctamente.")
            st.caption(f"Archivo: `{_datos_generales_path()}`")

    divider()
    section_header("🛣️", "Nueva Ruta")

    # ══════════════════════════════════════════════════════════════
    # FORMULARIO
    # ══════════════════════════════════════════════════════════════
    with st.form("igloo_captura_ruta"):

        # ── Información General ───────────────────────────────────
        st.caption("**INFORMACIÓN GENERAL**")
        c1, c2, c3, c4 = st.columns(4)
        fecha      = c1.date_input("Fecha", value=datetime.today(), key="igloo_fecha")
        tipo       = c2.selectbox("Tipo de Ruta", TIPOS_RUTA, key="igloo_tipo")
        cliente    = c3.text_input("Nombre Cliente", key="igloo_cliente", placeholder="NOMBRE DE LA EMPRESA")
        modo_viaje = c4.selectbox("Modo de Viaje", ["Sencillo", "Team"], key="igloo_modo")

        st.write("")

        # ── Cruce ─────────────────────────────────────────────────
        st.caption("**CRUCE**")
        c1, c2, c3, c4 = st.columns(4)
        moneda_cruce       = c1.selectbox("Moneda Ingreso Cruce", ["MXP", "USD"], key="igloo_mon_cruce")
        moneda_costo_cruce = c2.selectbox("Moneda Costo Cruce",   ["MXP", "USD"], key="igloo_mon_cc")
        ingreso_cruce      = c3.number_input("Ingreso Cruce",  min_value=0.0, key="igloo_ing_cruce")
        costo_cruce        = c4.number_input("Costo Cruce",    min_value=0.0, key="igloo_cc")

        st.write("")

        # ── Ruta Mexicana ─────────────────────────────────────────
        st.caption("**RUTA MEXICANA**")
        c1, c2, c3, c4 = st.columns(4)
        origen  = c1.text_input("Origen",  key="igloo_origen",  placeholder="CIUDAD, ESTADO")
        destino = c2.text_input("Destino", key="igloo_destino", placeholder="CIUDAD, ESTADO")
        km      = c3.number_input("Kilómetros",    min_value=0.0, key="igloo_km")
        casetas = c4.number_input("Casetas (MXP)", min_value=0.0, key="igloo_casetas")

        c1, c2, c3, c4 = st.columns(4)
        moneda_ingreso = c1.selectbox("Moneda Ingreso Flete", ["MXP", "USD"], key="igloo_mon_ing")
        ingreso_flete  = c2.number_input("Ingreso Flete", min_value=0.0, key="igloo_ing_flete")

        if tipo == "DOM MEX":
            modo_pago_dom = c3.selectbox(
                "Modo pago operador",
                ["km", "fijo"],
                format_func=lambda x: "Por kilómetro" if x == "km" else "Pago fijo",
                key="igloo_modo_pago_dom",
            )
        else:
            modo_pago_dom = "km"

        st.write("")

        # ── Termo y Costos Fijos ──────────────────────────────────
        st.caption("**TERMO Y COSTOS FIJOS**")
        c1, c2, c3, c4 = st.columns(4)
        horas_termo      = c1.number_input("Horas Termo",            min_value=0.0, key="igloo_horas")
        lavado_termo     = c2.number_input("Lavado Termo (MXP)",     min_value=0.0, key="igloo_lav")
        movimiento_local = c3.number_input("Movimiento Local (MXP)", min_value=0.0, key="igloo_mov")
        puntualidad      = c4.number_input("Puntualidad (MXP)",      min_value=0.0, key="igloo_punt")

        c1, c2, c3, c4 = st.columns(4)
        pension      = c1.number_input("Pensión (MXP)",     min_value=0.0, key="igloo_pens")
        estancia     = c2.number_input("Estancia (MXP)",    min_value=0.0, key="igloo_est")
        fianza_termo = c3.number_input("Fianza Termo (MXP)", min_value=0.0, key="igloo_fianza")
        renta_termo  = c4.number_input("Renta Termo (MXP)",  min_value=0.0, key="igloo_renta")

        st.write("")

        # ── Otros Costos ──────────────────────────────────────────
        st.caption("**OTROS COSTOS** — Marca 'Cobro' si el concepto se le cobra al cliente (suma al ingreso).")
        c1, c2, c3, c4, c5, c6 = st.columns(6)

        with c1:
            pistas_extra = st.number_input("Pistas Extra (MXP)", min_value=0.0, key="igloo_pistas")
            cobra_pistas = st.checkbox("Cobro", key="igloo_cobra_pistas")
        with c2:
            stop         = st.number_input("Stop (MXP)",         min_value=0.0, key="igloo_stop")
            cobra_stop   = st.checkbox("Cobro", key="igloo_cobra_stop")
        with c3:
            falso        = st.number_input("Falso (MXP)",        min_value=0.0, key="igloo_falso")
            cobra_falso  = st.checkbox("Cobro", key="igloo_cobra_falso")
        with c4:
            gatas        = st.number_input("Gatas (MXP)",        min_value=0.0, key="igloo_gatas")
            cobra_gatas  = st.checkbox("Cobro", key="igloo_cobra_gatas")
        with c5:
            accesorios   = st.number_input("Accesorios (MXP)",   min_value=0.0, key="igloo_acc")
            cobra_acc    = st.checkbox("Cobro", key="igloo_cobra_acc")
        with c6:
            guias        = st.number_input("Guías (MXP)",        min_value=0.0, key="igloo_guias")
            cobra_guias  = st.checkbox("Cobro", key="igloo_cobra_guias")

        st.write("")
        revisar = st.form_submit_button("🔍 Revisar Ruta", use_container_width=True)

    # ══════════════════════════════════════════════════════════════
    # CÁLCULOS AL REVISAR
    # ══════════════════════════════════════════════════════════════
    if revisar:
        cliente_norm = normalizar_texto(cliente)
        origen_norm  = normalizar_texto(origen)
        destino_norm = normalizar_texto(destino)

        st.session_state.igloo_revisar_ruta  = True
        st.session_state.igloo_datos_captura = {
            "fecha":             fecha,
            "tipo":              tipo,
            "cliente":           cliente_norm,
            "origen":            origen_norm,
            "destino":           destino_norm,
            "modo_viaje":        modo_viaje,
            "km":                km,
            "moneda_ingreso":    moneda_ingreso,
            "ingreso_flete":     ingreso_flete,
            "moneda_cruce":      moneda_cruce,
            "ingreso_cruce":     ingreso_cruce,
            "moneda_costo_cruce": moneda_costo_cruce,
            "costo_cruce":       costo_cruce,
            "horas_termo":       horas_termo,
            "lavado_termo":      lavado_termo,
            "movimiento_local":  movimiento_local,
            "puntualidad":       puntualidad,
            "pension":           pension,
            "estancia":          estancia,
            "fianza_termo":      fianza_termo,
            "renta_termo":       renta_termo,
            "casetas":           casetas,
            "pistas_extra":      pistas_extra,
            "cobra_pistas":      cobra_pistas,
            "stop":              stop,
            "cobra_stop":        cobra_stop,
            "falso":             falso,
            "cobra_falso":       cobra_falso,
            "gatas":             gatas,
            "cobra_gatas":       cobra_gatas,
            "accesorios":        accesorios,
            "cobra_acc":         cobra_acc,
            "guias":             guias,
            "cobra_guias":       cobra_guias,
            "modo_pago_dom":     modo_pago_dom,
        }

        # Extras: siempre al costo; al ingreso solo si cobrado
        extras = calcular_extras(pistas_extra, stop, falso, gatas, accesorios, guias)
        ingreso_extras_cobrados = (
            (pistas_extra if cobra_pistas else 0.0) +
            (stop         if cobra_stop   else 0.0) +
            (falso        if cobra_falso  else 0.0) +
            (gatas        if cobra_gatas  else 0.0) +
            (accesorios   if cobra_acc    else 0.0) +
            (guias        if cobra_guias  else 0.0)
        )

        factor          = 2 if modo_viaje == "Team" else 1
        puntualidad_val = puntualidad * factor

        costos_fijos = calcular_costos_fijos(
            lavado_termo, movimiento_local, puntualidad_val, pension, estancia,
            fianza_termo, renta_termo, casetas,
        )

        tc_usd        = float(valores.get("Tipo de cambio USD", 19.5))
        ingreso_total = ingreso_flete * (tc_usd if moneda_ingreso == "USD" else 1)
        ingreso_total += ingreso_cruce * (tc_usd if moneda_cruce  == "USD" else 1)
        ingreso_total += ingreso_extras_cobrados

        costo_cruce_convertido      = costo_cruce * (tc_usd if moneda_costo_cruce == "USD" else 1)
        diesel_camion, diesel_termo = calcular_diesel(km, horas_termo, valores)
        pago_km, sueldo, bono       = calcular_sueldo_y_bono(tipo, km, modo_viaje, valores, modo_pago_dom)

        costo_total = diesel_camion + diesel_termo + sueldo + bono + costos_fijos + extras + costo_cruce_convertido

        util = calcular_utilidades(ingreso_total, costo_total, tipo)

        st.session_state.igloo_calc = {
            "tipo_cambio_flete":        tc_usd if moneda_ingreso     == "USD" else float(valores.get("Tipo de cambio MXP", 1.0)),
            "tipo_cambio_cruce":        tc_usd if moneda_cruce       == "USD" else float(valores.get("Tipo de cambio MXP", 1.0)),
            "tipo_cambio_costo_cruce":  tc_usd if moneda_costo_cruce == "USD" else float(valores.get("Tipo de cambio MXP", 1.0)),
            "ingreso_flete_convertido": ingreso_flete * (tc_usd if moneda_ingreso == "USD" else 1),
            "ingreso_cruce_convertido": ingreso_cruce * (tc_usd if moneda_cruce   == "USD" else 1),
            "costo_cruce_convertido":   costo_cruce_convertido,
            "ingreso_extras_cobrados":  ingreso_extras_cobrados,
            "ingreso_total":            ingreso_total,
            "costo_diesel_camion":      diesel_camion,
            "costo_diesel_termo":       diesel_termo,
            "pago_km":                  pago_km,
            "sueldo":                   sueldo,
            "bono":                     bono,
            "puntualidad_val":          puntualidad_val,
            "costos_fijos":             costos_fijos,
            "extras":                   extras,
            "costo_total":              costo_total,
            "costos_indirectos":        util["costos_indirectos"],
            "utilidad_bruta":           util["utilidad_bruta"],
            "utilidad_neta":            util["utilidad_neta"],
            "porcentaje_bruta":         util["porcentaje_bruta"],
            "porcentaje_neta":          util["porcentaje_neta"],
        }

        mostrar_resultados_utilidad(
            st, ingreso_total, costo_total,
            util["utilidad_bruta"], util["costos_indirectos"],
            util["utilidad_neta"], util["porcentaje_bruta"], util["porcentaje_neta"],
            tipo=tipo,
            tc_usd=tc_usd,
        )

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
                _get_last_id_cached.clear()
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
                # Cobros individuales — columnas nuevas
                "Cobra_Pistas":           d.get("cobra_pistas",  False),
                "Cobra_Stop":             d.get("cobra_stop",    False),
                "Cobra_Falso":            d.get("cobra_falso",   False),
                "Cobra_Gatas":            d.get("cobra_gatas",   False),
                "Cobra_Accesorios":       d.get("cobra_acc",     False),
                "Cobra_Guias":            d.get("cobra_guias",   False),
                # Legacy conservada
                "Extras_Cobrados":        False,
                # Parámetros
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
                _get_last_id_cached.clear()
                st.session_state.igloo_ruta_guardada_id = nuevo_id
                st.session_state.igloo_mostrar_modal    = True
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error al guardar ruta: {e}")
                st.exception(e)
