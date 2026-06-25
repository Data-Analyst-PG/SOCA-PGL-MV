"""
captura_rutas.py – Lincoln Freight (USA/MX)
Estructura visual idéntica a Set Logis Plus.
Diferencias Lincoln:
  - 3 tipos de millas: Miles Load, Short Miles, Miles Empty
  - Parámetros: CXM operador, diesel, MPG, ISR/IMSS, bono
  - Extras: monto capturado = Lincoln pagó (costo). Checkbox = cobrado al cliente (ingreso)
  - Orden de secciones según tipo de ruta:
      NB    → Info General → Cruce → Ruta Americana → Extras
      SB    → Info General → Ruta Americana → Cruce → Extras
      D2DNB → Info General → Parte MX → Cruce → Ruta Americana → Extras
      D2DSB → Info General → Ruta Americana → Cruce → Parte MX → Extras
      Empty → Info General → Ruta Americana → Extras
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st
from streamlit_searchbox import st_searchbox

from services.supabase_client import get_supabase_client, current_user
from ui.components import (
    section_header, alert, divider,
    mostrar_resultados_ruta, banner_tarifa_sugerida, desglose_ruta,
)
from ._shared import (
    TABLE_RUTAS,
    TIPOS_RUTA,
    EXTRAS_USA,
    cargar_datos_generales,
    guardar_datos_generales,
    limpiar_fila_json,
    safe,
    calcular_ruta_lincoln,
    obtener_config_tipo_ruta,
    tiene_mx,
    normalizar,
    a_usd,
    get_profile_name,
    generar_id_ruta,
    now_iso,
    buscar_ubicacion_lincoln,
)


# ─────────────────────────────────────────────
# PANEL PARÁMETROS
# ─────────────────────────────────────────────
def _panel_datos_generales(valores: dict) -> dict:
    with st.expander("⚙️ Configuración de Parámetros", expanded=False):

        st.markdown("**Operador Sencillo (USD/milla)**")
        c1, c2 = st.columns(2)
        valores["CXM Operador USA"] = c1.number_input(
            "Cargado", value=float(valores.get("CXM Operador USA", 0.48)),
            step=0.01, format="%.4f", key="ln_cxm_carg")
        valores["CXM Operador USA (Empty)"] = c2.number_input(
            "Vacío", value=float(valores.get("CXM Operador USA (Empty)", 0.30)),
            step=0.01, format="%.4f", key="ln_cxm_vac")

        st.markdown("**Operador Team (USD/milla × operador)**")
        t1, t2 = st.columns(2)
        valores["CXM Team USA"] = t1.number_input(
            "Team Cargado", value=float(valores.get("CXM Team USA", 0.30)),
            step=0.01, format="%.4f", key="ln_cxm_team_carg")
        valores["CXM Team USA (Empty)"] = t2.number_input(
            "Team Vacío", value=float(valores.get("CXM Team USA (Empty)", 0.25)),
            step=0.01, format="%.4f", key="ln_cxm_team_vac")

        st.markdown("**Diesel**")
        d1, d2 = st.columns(2)
        valores["Truck Performance (mpg)"] = d1.number_input(
            "Rendimiento (mpg)", value=float(valores.get("Truck Performance (mpg)", 7.0)),
            step=0.1, format="%.1f", key="ln_mpg")
        valores["Diesel Price ($/gal)"] = d2.number_input(
            "Diesel ($/gal)", value=float(valores.get("Diesel Price ($/gal)", 3.60)),
            step=0.01, format="%.2f", key="ln_diesel")

        st.markdown("**Cruce Propio (USD)**")
        cr1, cr2 = st.columns(2)
        valores["Cruce Propio (Cargado)"] = cr1.number_input(
            "Cargado", value=float(valores.get("Cruce Propio (Cargado)", 50.0)),
            step=1.0, format="%.2f", key="ln_cruce_carg")
        valores["Cruce Propio (Vacío)"] = cr2.number_input(
            "Vacío", value=float(valores.get("Cruce Propio (Vacío)", 30.0)),
            step=1.0, format="%.2f", key="ln_cruce_vac")

        st.markdown("**Prestaciones y Bonos**")
        p1, p2 = st.columns(2)
        valores["ISR/IMSS"] = p1.number_input(
            "ISR/IMSS (USD/viaje)", value=float(valores.get("ISR/IMSS", 462.66)),
            step=1.0, format="%.2f", key="ln_isr")
        valores["Bono por milla cargada"] = p2.number_input(
            "Bono/Short Mile (USD)", value=float(valores.get("Bono por milla cargada", 0.01)),
            step=0.001, format="%.3f", key="ln_bono")

        st.markdown("**Costo Indirecto y Tipo de Cambio**")
        i1, i2 = st.columns(2)
        pct_raw = float(valores.get("% Costo Indirecto", 0.42))
        pct_display = pct_raw if pct_raw <= 1.0 else pct_raw / 100
        valores["% Costo Indirecto"] = i1.number_input(
            "% Costo Indirecto (ej. 0.42)", value=pct_display,
            step=0.01, format="%.2f", key="ln_pct_ind")
        valores["Tipo de Cambio USD/MXP"] = i2.number_input(
            "Tipo de Cambio USD/MXP", value=float(valores.get("Tipo de Cambio USD/MXP", 18.50)),
            step=0.1, format="%.2f", key="ln_tc")

        if st.button("💾 Guardar parámetros", key="ln_guardar_params"):
            guardar_datos_generales(valores)
            st.success("Parámetros guardados.")

    return valores


# ─────────────────────────────────────────────
# SECCIONES DEL FORMULARIO
# ─────────────────────────────────────────────
def _seccion_info_general(es_empty: bool, tipo_ruta: str) -> tuple:
    """Devuelve: fecha, tipo_ruta, cliente, modo_viaje"""
    st.markdown("### 📋 Información General")
    g1, g2, g3, g4 = st.columns(4)
    fecha      = g1.date_input("📅 Fecha", value=datetime.today(), key="ln_fecha")
    tipo       = g2.selectbox("🚛 Tipo de Ruta", TIPOS_RUTA,
                               index=TIPOS_RUTA.index(tipo_ruta), key="ln_tipo")
    cliente    = g3.text_input("🏢 Cliente", placeholder="NOMBRE DEL CLIENTE", key="ln_cliente")
    modo_viaje = g4.selectbox("👥 Modo", ["Sencillo", "Team"], key="ln_modo")

    config = obtener_config_tipo_ruta(tipo)
    dir_label = "Subida" if tipo in {"NB", "D2DNB", "Empty"} else "Bajada"
    mx_label  = "Sí" if config["parte_mx"] else "No"
    st.caption(f"📌 Dirección: **{dir_label}** · Tramo MX: **{mx_label}**")
    return fecha, tipo, cliente, modo_viaje


def _seccion_ruta_americana(es_empty: bool, valores: dict) -> tuple:
    """Devuelve: origen_usa, destino_usa, miles_load, short_miles, miles_empty,
                 modalidad, moneda_flete, cxm_flete, cxm_fuel, tarifa_flat"""
    st.markdown("### 🇺🇸 Ruta Americana")

    ru1, ru2 = st.columns(2)
    with ru1:
        origen_sel = st_searchbox(
            buscar_ubicacion_lincoln,
            label="📍 Origen USA",
            placeholder="CIUDAD, ESTADO...",
            key=f"ln_ori_usa",
            clear_on_submit=False,
        )
    with ru2:
        destino_sel = st_searchbox(
            buscar_ubicacion_lincoln,
            label="📍 Destino USA",
            placeholder="CIUDAD, ESTADO...",
            key=f"ln_dest_usa",
            clear_on_submit=False,
        )
    origen_usa  = str(origen_sel  or "").strip()
    destino_usa = str(destino_sel or "").strip()

    m1, m2, m3 = st.columns(3)
    miles_load  = m1.number_input(
        "🛣️ Miles Load",
        min_value=0.0, step=10.0, key="ln_ml",
        help="Millas que se cotizan al cliente (base del ingreso)",
        disabled=es_empty,
    )
    short_miles = m2.number_input(
        "🔀 Short Miles",
        min_value=0.0, step=1.0, key="ln_sm",
        help="Millas reales recorridas cargado (base del pago al operador y bono)",
        disabled=es_empty,
    )
    miles_empty = m3.number_input(
        "⚪ Miles Empty",
        min_value=0.0, step=10.0, key="ln_me",
        help="Millas en vacío (pago operador vacío + diesel)",
    )

    divider()
    st.markdown("**💵 Tarifa Americana**")
    mod1, mod2 = st.columns([1, 3])
    modalidad = mod1.radio(
        "Modalidad", ["Desglosada", "Flat"],
        horizontal=False, key="ln_modalidad",
        disabled=es_empty,
    )

    cxm_flete   = 0.0
    cxm_fuel    = 0.0
    tarifa_flat = 0.0
    moneda_flete = "USD"

    if es_empty:
        mod2.info("ℹ️ **Empty:** sin tarifa al cliente. Solo costos de reposicionamiento.")
    elif modalidad == "Desglosada":
        td1, td2, td3 = mod2.columns(3)
        moneda_flete = td1.selectbox("💱 Moneda", ["USD", "MXP"], key="ln_mon_flete")
        cxm_flete    = td2.number_input(
            "CXM Flete ($/mi)", min_value=0.0, step=0.001, format="%.4f", key="ln_cxm_flete",
            value=float(valores.get("CXM Operador USA", 0.48)),
        )
        cxm_fuel     = td3.number_input(
            "Fuel Surcharge ($/mi)", min_value=0.0, step=0.001, format="%.4f", key="ln_cxm_fuel",
            value=float(valores.get("Fuel Surcharge ($/mi)", 0.61)),
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
        moneda_flete = tf1.selectbox("💱 Moneda", ["USD", "MXP"], key="ln_mon_flete_flat")
        tarifa_flat  = tf2.number_input(
            "Tarifa Total (Flat)", min_value=0.0, step=50.0, key="ln_tarifa_flat"
        )

    return (origen_usa, destino_usa, miles_load, short_miles, miles_empty,
            modalidad, moneda_flete, cxm_flete, cxm_fuel, tarifa_flat)


def _seccion_cruce(tipo_ruta: str, config: dict) -> tuple:
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
        key="ln_aplica_cruce",
    )

    if aplica_cruce:
        cx1, cx2, cx3 = st.columns(3)
        tipo_cruce = cx1.selectbox("Tipo de Cruce", ["Propio", "Tercero"], key="ln_tipo_cruce")
        tipo_carga = cx2.selectbox("Carga del cruce", ["Cargado", "Vacío"], key="ln_tipo_carga")
        moneda_cruce = cx3.selectbox("💱 Moneda Ingreso", ["USD", "MXP"], key="ln_moneda_cruce")

        ing_col, costo_col = st.columns(2)
        ingreso_cruce = ing_col.number_input(
            "Ingreso Cruce", min_value=0.0, step=5.0, format="%.2f", key="ln_ing_cruce"
        )
        if tipo_cruce == "Tercero":
            costo_cruce_terc = costo_col.number_input(
                "Costo Cruce Tercero", min_value=0.0, step=5.0, format="%.2f",
                key="ln_costo_cruce_terc"
            )

    return aplica_cruce, tipo_cruce, tipo_carga, moneda_cruce, ingreso_cruce, costo_cruce_terc


def _seccion_tramo_mx() -> tuple:
    """Devuelve: linea_mx, origen_mx, destino_mx, moneda_mx, ingreso_mx, costo_mx"""
    st.markdown("### 🇲🇽 Parte Mexicana")

    mx1, mx2 = st.columns(2)
    linea_mx   = mx1.selectbox("Línea MX", ["Propia", "Tercero"], key="ln_linea_mx")
    origen_mx  = mx1.text_input("📍 Origen MX",  placeholder="CIUDAD, ESTADO", key="ln_ori_mx")
    destino_mx = mx1.text_input("📍 Destino MX", placeholder="CIUDAD, ESTADO", key="ln_dest_mx")
    moneda_mx  = mx2.selectbox("💱 Moneda MX", ["MXP", "USD"], key="ln_moneda_mx")
    ingreso_mx = mx2.number_input(
        "Ingreso Flete MX", min_value=0.0, step=100.0, format="%.2f", key="ln_ing_mx"
    )
    costo_mx = 0.0
    if linea_mx == "Tercero":
        costo_mx = mx2.number_input(
            "Costo Flete MX", min_value=0.0, step=100.0, format="%.2f", key="ln_costo_mx"
        )

    return linea_mx, origen_mx, destino_mx, moneda_mx, ingreso_mx, costo_mx


def _seccion_extras() -> tuple:
    """Devuelve: otros_cargos {nombre: monto}, otros_cargos_cobrados {nombre: bool}"""
    st.markdown("### ➕ Extras / Otros Conceptos")
    st.caption(
        "Captura el monto si Lincoln lo pagó (suma al costo). "
        "Marca **'cobrado'** si también se le cobró al cliente (suma al ingreso)."
    )

    otros_cargos         = {}
    otros_cargos_cobrados = {}

    cols3 = st.columns(3)
    for i, extra in enumerate(EXTRAS_USA):
        with cols3[i % 3]:
            monto   = st.number_input(
                extra, min_value=0.0, step=10.0, format="%.2f", key=f"ln_extra_{extra}"
            )
            cobrado = st.checkbox("cobra", key=f"ln_cobra_{extra}")
            if monto > 0:
                otros_cargos[extra]          = monto
                otros_cargos_cobrados[extra] = cobrado

    return otros_cargos, otros_cargos_cobrados


# ─────────────────────────────────────────────
# MOSTRAR RESULTADOS
# ─────────────────────────────────────────────
def _mostrar_resultados(r: dict, fd: dict) -> None:
    tc_usd      = r.get("tc", 18.50)
    _umbral     = r["umbral_cd"]
    _tarifa_sug = r["costo_directo"] / (_umbral / 100)
    _tarifa_mxp = _tarifa_sug * tc_usd
    divider()
    banner_tarifa_sugerida(
        r["costo_directo"], r["ingreso_total"],
        _umbral, "USD", _tarifa_mxp,
    )
    mostrar_resultados_ruta(r)

    tipo_ruta   = fd.get("tipo_ruta", "NB")
    es_empty    = (tipo_ruta == "Empty")
    short_miles = fd.get("short_miles", 0.0)
    miles_empty = fd.get("miles_empty", 0.0)

    if es_empty:
        filas_costo = [
            (f"Operador Vacío ({miles_empty:.0f} mi × ${r['cxm_vacio']:.4f})", r["sueldo_base"]),
            (f"Diesel ({miles_empty:.0f} mi vacías)", r["diesel_usa"]),
        ]
    else:
        filas_costo = [
            (f"Sueldo Cargado ({short_miles:.0f} Short Mi × ${r['cxm_cargado']:.4f})",
             short_miles * r["cxm_cargado"] * (2 if fd.get("modo_viaje") == "Team" else 1)),
            (f"Sueldo Vacío ({miles_empty:.0f} Mi Vacías × ${r['cxm_vacio']:.4f})",
             miles_empty * r["cxm_vacio"] * (2 if fd.get("modo_viaje") == "Team" else 1)),
            (f"Bono ({short_miles:.0f} Short Mi × ${r['bono_por_milla']:.3f})", r["bono_millas"]),
            (f"Diesel ({short_miles:.0f} SM + {miles_empty:.0f} ME)", r["diesel_usa"]),
            ("ISR/IMSS", r["isr_imss"]),
        ]
        if r.get("otros_cargos_costo", 0) > 0:
            filas_costo.append(("Otros Conceptos (Lincoln pagó)", r["otros_cargos_costo"]))

    desglose_ruta(
        r,
        filas_costo_americana=filas_costo,
        modalidad=fd.get("modalidad", "Flat"),
        cxm_flete=fd.get("cxm_flete", 0.0),
        cxm_fuel=fd.get("cxm_fuel", 0.0),
    )


# ─────────────────────────────────────────────
# GUARDAR EN SUPABASE
# ─────────────────────────────────────────────
def _guardar_ruta(r: dict, fd: dict, id_ruta: str, user_id: str, nombre_usuario: str) -> None:
    supabase = get_supabase_client()
    if supabase is None:
        alert("error", "No se pudo conectar a Supabase.")
        return

    now = now_iso()
    fila = {
        "ID_Ruta":              id_ruta,
        "Fecha":                fd["fecha"],
        "Tipo":                 fd["tipo_ruta"],
        "Cliente":              fd["cliente"],
        "Modo_Viaje":           fd["modo_viaje"],
        "Origen":               fd["origen_usa"],
        "Destino":              fd["destino_usa"],
        # Millas — nombres nuevos (columnas agregadas en migración)
        "Miles_Load":           fd["miles_load"],
        "Short_Miles":          fd["short_miles"],
        "Miles_Empty":          fd["miles_empty"],
        "Moneda_USA":           fd["moneda_flete"],
        "Modalidad":            fd["modalidad"],
        "CXM_Flete":            fd["cxm_flete"],
        "CXM_Fuel":             fd["cxm_fuel"],
        "Tarifa_Flat":          fd["tarifa_flat"],
        "Ingreso_Flete_USA":    r["ingreso_flete_usa"],
        "Ingreso_Fuel_USA":     r["ingreso_fuel_usa"],
        "Aplica_Cruce":         fd["aplica_cruce"],
        "Tipo_Cruce":           fd["tipo_cruce"],
        "Tipo_Carga_Cruce":     fd["tipo_carga"],
        "Moneda_Cruce":         fd["moneda_cruce"],
        "Ingreso_Cruce":        r["ingreso_cruce"],
        "Costo_Cruce":          r["costo_cruce"],
        "Linea_MX":             fd["linea_mx"],
        "Origen_MX":            fd["origen_mx"],
        "Destino_MX":           fd["destino_mx"],
        "Moneda_MX":            fd["moneda_mx"],
        "Ingreso_MX_MXP":       fd["ingreso_mx_mxp"],
        "Costo_MX_MXP":         fd["costo_mx_mxp"],
        "Ingreso_MX_USD":       r["ingreso_mx_usd"],
        "Costo_MX_USD":         r["costo_mx_usd"],
        "Otros_Cargos_JSON":    str(fd.get("otros_cargos", {})),
        "Otros_Cargos_Ingreso": r["otros_cargos_ingreso"],
        "Otros_Cargos_Costo":   r["otros_cargos_costo"],
        "Sueldo_Base":          r["sueldo_base"],
        "Bono_Millas":          r["bono_millas"],
        "Sueldo_Operador":      r["sueldo_usa"],
        "Diesel_USA":           r["diesel_usa"],
        "ISR_IMSS":             r["isr_imss"],
        "Costo_Directo":        r["costo_directo"],
        "Costo_Directo_Total":  r["costo_directo_total"],
        "Ingreso_Total":        r["ingreso_total"],
        "Utilidad_Bruta":       r["utilidad_bruta"],
        "Pct_Utilidad_Bruta":   r["pct_bruta"],
        "Costos_Indirectos":    r["costos_ind"],
        "Utilidad_Neta":        r["utilidad_neta"],
        "Pct_Utilidad_Neta":    r["pct_neta"],
        "Tipo_Cambio":          r["tc"],
        "Capturado_Por":        nombre_usuario,
        "User_ID":              user_id,
        "created_at":           now,
        "updated_at":           now,
    }

    try:
        supabase.table(TABLE_RUTAS).insert(limpiar_fila_json(fila)).execute()
        # Limpiar cache si existe
        try:
            from . import consulta_ruta as _cr
            _cr._cargar_rutas.clear()
        except Exception:
            pass
        # Activar modal de éxito y limpiar estado del formulario
        st.session_state["ln_ruta_guardada_id"]  = id_ruta
        st.session_state["ln_mostrar_modal"]     = True
        st.session_state.pop("ln_resultado", None)
        st.session_state.pop("ln_form_data", None)
        st.rerun()
    except Exception as e:
        alert("error", f"Error al guardar: {e}")


# ─────────────────────────────────────────────
# MODAL CONFIRMACIÓN
# ─────────────────────────────────────────────
@st.dialog("✅ Ruta Guardada Exitosamente", width="small")
def _modal_guardado(id_ruta: str) -> None:
    alert("success", "**¡La ruta se guardó correctamente!**")
    st.info(f"### 🆔 ID de la ruta\n`{id_ruta}`")
    st.caption("Puedes consultarla en 'Consulta Ruta' o 'Gestión de Rutas'.")
    if st.button("✅ Aceptar", type="primary", use_container_width=True, key="ln_modal_ok"):
        st.session_state.pop("ln_ruta_guardada_id", None)
        st.session_state.pop("ln_mostrar_modal", None)
        # Incrementar sufijo de form para forzar que todos los widgets queden vacíos
        st.session_state["ln_form_key"] = st.session_state.get("ln_form_key", 0) + 1
        st.rerun()


# ─────────────────────────────────────────────
# RENDER PRINCIPAL
# ─────────────────────────────────────────────
def render() -> None:
    supabase = get_supabase_client()
    if supabase is None:
        alert("error", "Supabase no configurado.")
        return

    u              = current_user() or {}
    user_id        = u.get("id") or u.get("sub") or ""
    nombre_usuario = get_profile_name(user_id) or u.get("email") or "Desconocido"

    st.session_state.setdefault("ln_resultado", None)
    st.session_state.setdefault("ln_form_data", {})
    # Sufijo de sesión: cambia al limpiar el formulario, forzando recreación de widgets
    st.session_state.setdefault("ln_form_key", 0)

    # Mostrar modal de éxito si acaba de guardar
    if st.session_state.get("ln_mostrar_modal") and st.session_state.get("ln_ruta_guardada_id"):
        _modal_guardado(st.session_state["ln_ruta_guardada_id"])

    valores = cargar_datos_generales()
    valores = _panel_datos_generales(valores)
    divider()
    section_header("🛣️", "Nueva Ruta")

    # Leer tipo_ruta ANTES del form para saber el orden de secciones
    # Usamos session_state para persistir entre reruns del selectbox
    tipo_ruta_actual = st.session_state.get("ln_tipo", TIPOS_RUTA[0])
    config           = obtener_config_tipo_ruta(tipo_ruta_actual)
    orden            = config.get("orden", ["americana"])
    es_empty         = (tipo_ruta_actual == "Empty")

    _k = st.session_state.get("ln_form_key", 0)
    with st.form(f"ln_captura_ruta_{_k}", clear_on_submit=False):

        # ── Info General siempre primera ──────────────────────────────────────
        fecha, tipo_ruta, cliente, modo_viaje = _seccion_info_general(
            es_empty, tipo_ruta_actual
        )
        config   = obtener_config_tipo_ruta(tipo_ruta)
        orden    = config.get("orden", ["americana"])
        es_empty = (tipo_ruta == "Empty")

        # Valores por defecto de secciones opcionales
        origen_usa = destino_usa = ""
        miles_load = short_miles = miles_empty = 0.0
        modalidad = "Desglosada"
        moneda_flete = "USD"
        cxm_flete = cxm_fuel = tarifa_flat = 0.0
        aplica_cruce = False
        tipo_cruce = "Propio"
        tipo_carga = "Cargado"
        moneda_cruce = "USD"
        ingreso_cruce = costo_cruce_terc = 0.0
        linea_mx = "Propia"
        origen_mx = destino_mx = ""
        moneda_mx = "MXP"
        ingreso_mx = costo_mx = 0.0

        # ── Secciones en orden según tipo de ruta ─────────────────────────────
        for seccion in orden:

            divider()

            if seccion == "americana":
                (origen_usa, destino_usa, miles_load, short_miles, miles_empty,
                 modalidad, moneda_flete, cxm_flete, cxm_fuel, tarifa_flat) = \
                    _seccion_ruta_americana(es_empty, valores)

            elif seccion == "cruce":
                if not es_empty and config.get("cruce") in ("opcional", True):
                    (aplica_cruce, tipo_cruce, tipo_carga,
                     moneda_cruce, ingreso_cruce, costo_cruce_terc) = \
                        _seccion_cruce(tipo_ruta, config)

            elif seccion == "mx":
                if config.get("parte_mx") and not es_empty:
                    (linea_mx, origen_mx, destino_mx,
                     moneda_mx, ingreso_mx, costo_mx) = _seccion_tramo_mx()

        # ── Extras siempre al final ───────────────────────────────────────────
        divider()
        otros_cargos, otros_cargos_cobrados = _seccion_extras()

        divider()
        submitted = st.form_submit_button(
            "🔍 Calcular Ruta", type="primary", use_container_width=True
        )

    # ── Post-form: calcular ───────────────────────────────────────────────────
    if submitted:
        tc = float(valores.get("Tipo de Cambio USD/MXP", 18.5))

        # Ingreso por milla en USD
        if es_empty or tarifa_flat > 0:
            ing_x_milla_usd = 0.0
            fuel_sc_usd     = 0.0
            tarifa_flat_usd = 0.0 if es_empty else (
                tarifa_flat if moneda_flete == "USD" else a_usd(tarifa_flat, tc)
            )
        else:
            ing_x_milla_usd = cxm_flete if moneda_flete == "USD" else a_usd(cxm_flete, tc)
            fuel_sc_usd     = cxm_fuel  if moneda_flete == "USD" else a_usd(cxm_fuel,  tc)
            tarifa_flat_usd = 0.0

        ing_cruce_usd = 0.0
        if aplica_cruce and not es_empty:
            ing_cruce_usd = ingreso_cruce if moneda_cruce == "USD" else a_usd(ingreso_cruce, tc)

        # Tramo MX → siempre en MXP para el cálculo
        if config.get("parte_mx") and not es_empty:
            ing_mx_mxp   = ingreso_mx * tc if moneda_mx == "USD" else ingreso_mx
            costo_mx_mxp = costo_mx   * tc if moneda_mx == "USD" else costo_mx
            if linea_mx != "Tercero":
                costo_mx_mxp = 0.0
        else:
            ing_mx_mxp   = 0.0
            costo_mx_mxp = 0.0

        r = calcular_ruta_lincoln(
            tipo_ruta               = tipo_ruta,
            miles_load              = miles_load,
            short_miles             = short_miles,
            miles_empty             = miles_empty,
            ingreso_x_milla_usd     = ing_x_milla_usd,
            tarifa_flat_usd         = tarifa_flat_usd,
            fuel_surcharge_usd      = fuel_sc_usd,
            ingreso_cruce_usd       = ing_cruce_usd,
            aplica_cruce            = aplica_cruce,
            modo_viaje              = modo_viaje,
            tipo_cruce              = tipo_cruce,
            tipo_carga_cruce        = tipo_carga,
            costo_cruce_tercero_usd = costo_cruce_terc,
            ingreso_flete_mx_mxp    = ing_mx_mxp,
            costo_flete_mx_mxp      = costo_mx_mxp,
            linea_mx                = linea_mx,
            otros_cargos            = otros_cargos,
            otros_cargos_cobrados   = otros_cargos_cobrados,
            valores                 = valores,
        )

        st.session_state["ln_resultado"] = r
        st.session_state["ln_form_data"] = {
            "fecha":                 str(fecha),
            "tipo_ruta":             tipo_ruta,
            "cliente":               normalizar(cliente),
            "modo_viaje":            modo_viaje,
            "origen_usa":            normalizar(origen_usa),
            "destino_usa":           normalizar(destino_usa),
            "miles_load":            miles_load,
            "short_miles":           short_miles,
            "miles_empty":           miles_empty,
            "moneda_flete":          moneda_flete,
            "modalidad":             modalidad,
            "cxm_flete":             cxm_flete,
            "cxm_fuel":              cxm_fuel,
            "tarifa_flat":           tarifa_flat,
            "aplica_cruce":          aplica_cruce,
            "tipo_cruce":            tipo_cruce,
            "tipo_carga":            tipo_carga,
            "moneda_cruce":          moneda_cruce,
            "ingreso_cruce":         ingreso_cruce,
            "costo_cruce_terc":      costo_cruce_terc,
            "linea_mx":              linea_mx,
            "origen_mx":             normalizar(origen_mx),
            "destino_mx":            normalizar(destino_mx),
            "moneda_mx":             moneda_mx,
            "ingreso_mx":            ingreso_mx,
            "ingreso_mx_mxp":        ing_mx_mxp,
            "costo_mx":              costo_mx,
            "costo_mx_mxp":          costo_mx_mxp,
            "otros_cargos":          otros_cargos,
            "otros_cargos_cobrados": otros_cargos_cobrados,
        }

    # ── Mostrar resultado + botón guardar (fuera del form) ────────────────────
    r  = st.session_state.get("ln_resultado")
    fd = st.session_state.get("ln_form_data", {})

    if r and fd:
        _mostrar_resultados(r, fd)

        divider()
        col_g, col_x = st.columns([2, 1])
        with col_g:
            if st.button("💾 Guardar Ruta", type="primary",
                         use_container_width=True, key="ln_guardar_ruta"):
                id_ruta = generar_id_ruta()
                _guardar_ruta(r, fd, id_ruta, user_id, nombre_usuario)
        with col_x:
            if st.button("🗑️ Descartar", use_container_width=True, key="ln_descartar"):
                st.session_state.pop("ln_resultado", None)
                st.session_state.pop("ln_form_data", None)
                st.rerun()
