"""
pruebas_router.py — Módulo Sandbox
Prueba del flujo de EDICIÓN de rutas Igloo con searchbox en Origen/Destino.
Lee de la misma tabla "Rutas" pero no modifica gestion_rutas.py de Igloo.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from io import BytesIO

import pandas as st_pd
import pandas as pd
import streamlit as st
from streamlit_searchbox import st_searchbox

from services.supabase_client import get_supabase_client, get_authed_client, current_user
from ui.components import page_banner, section_header, alert, divider

from modules.cotizadores.igloo.helpers import (
    DEFAULTS, TIPOS_RUTA,
    cargar_datos_generales,
    safe_number, safe_float,
    calcular_sueldo_y_bono, calcular_diesel,
    calcular_costos_fijos, calcular_extras,
    calcular_utilidades, mostrar_resultados_utilidad,
    filtrar_rutas_igloo, label_ruta_igloo,
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


@st.cache_data(show_spinner=False, ttl=120)
def _load_rutas_cached(table_name: str) -> pd.DataFrame:
    sb = get_supabase_client()
    if sb is None:
        return pd.DataFrame()
    try:
        resp = sb.table(table_name).select("*").order("Fecha", desc=True).execute()
        return pd.DataFrame(resp.data) if resp.data else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def normalizar_texto(texto):
    if not texto:
        return ""
    texto = str(texto).upper().strip()
    texto = re.sub(r'\s+', ' ', texto)
    texto = re.sub(r'\s*,\s*', ', ', texto)
    return texto


# ─────────────────────────────────────────────
# POOL DE UBICACIONES
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=120)
def _cargar_pool_ubicaciones() -> list[str]:
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
    if not termino or len(termino) < 2:
        return []
    termino_upper = termino.upper()
    pool = _cargar_pool_ubicaciones()
    coincidencias = [u for u in pool if termino_upper in u]
    if not coincidencias:
        return [termino_upper]
    return coincidencias


# ─────────────────────────────────────────────
# MODAL CONFIRMACIÓN
# ─────────────────────────────────────────────
@st.dialog("✅ Ruta Actualizada Exitosamente", width="small")
def _modal_edicion(id_ruta: str) -> None:
    alert("success", "**¡La ruta se actualizó correctamente!**")
    st.info(f"### 🆔 ID de la ruta\n`{id_ruta}`")
    st.caption("Los cambios se han guardado y registrado en el historial.")
    if st.button("✅ Aceptar", type="primary", use_container_width=True, key="prb_modal_ed_ok"):
        st.session_state.pop("prb_ruta_editada_id", None)
        st.session_state.pop("prb_mostrar_modal_edicion", None)
        st.session_state.pop("prb_datos_edicion", None)
        st.session_state.pop("prb_calc_edicion", None)
        st.session_state["prb_revisar_edicion"] = False
        st.rerun()


# ─────────────────────────────────────────────
# RENDER PRINCIPAL
# ─────────────────────────────────────────────
def render():
    page_banner("🧪", "Módulo de Pruebas — Gestión de Rutas", "Prueba de edición con autocomplete en Origen/Destino")

    sb = get_supabase_client()
    if sb is None:
        alert("warn", "⚠️ Supabase no configurado.")
        return

    u = current_user() or {}
    user_id        = u.get("id") or u.get("sub") or ""
    nombre_usuario = _get_profile_name(user_id) or u.get("email") or "Desconocido"

    st.session_state.setdefault("prb_revisar_edicion", False)

    if st.session_state.get("prb_mostrar_modal_edicion") and st.session_state.get("prb_ruta_editada_id"):
        _modal_edicion(st.session_state["prb_ruta_editada_id"])

    # ── Recargar ──────────────────────────────────────────────────
    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("🔄 Recargar", key="prb_gest_reload"):
            _load_rutas_cached.clear()
            st.rerun()
    with c2:
        st.caption("Carga cacheada 2 min. Usa 'Recargar' si acabas de guardar algo.")

    df = _load_rutas_cached(TABLE_RUTAS)
    if df.empty:
        alert("warn", "⚠️ No hay rutas registradas.")
        return

    valores = cargar_datos_generales()

    # ── Selector de ruta ──────────────────────────────────────────
    section_header("✏️", "Editar Ruta")

    df_ed = df.copy()
    if "ID_Ruta" not in df_ed.columns:
        alert("error", "La tabla no tiene columna ID_Ruta.")
        return

    df_ed_f = filtrar_rutas_igloo(df_ed, "prb_ed")
    if df_ed_f.empty:
        alert("info", "No hay rutas con los filtros aplicados.")
        return

    df_ed_f = df_ed_f.set_index("ID_Ruta", drop=False)
    idx_sel = st.selectbox(
        f"Selecciona ruta a editar ({len(df_ed_f)} encontrada/s)",
        options=[""] + df_ed_f.index.tolist(),
        format_func=lambda i: "— Elige una ruta —" if i == "" else label_ruta_igloo(df_ed_f.loc[i]),
        key="prb_ed_select",
    )
    if not idx_sel:
        alert("info", "Selecciona una ruta para editarla.")
        return

    ruta = df_ed_f.loc[idx_sel].to_dict()
    st.caption(f"🖊️ Creada por: **{ruta.get('created_by', 'N/A')}** el {str(ruta.get('created_at', ''))[:10]}")

    # Historial (solo lectura)
    historial = ruta.get("historial") or []
    if isinstance(historial, list) and historial:
        with st.expander(f"📜 Historial de modificaciones ({len(historial)})", expanded=False):
            for entrada in reversed(historial):
                ts  = str(entrada.get("timestamp", ""))[:16].replace("T", " ")
                usr = entrada.get("usuario", "—")
                mot = entrada.get("motivo", "—")
                st.caption(f"**{ts}** · {usr} · _{mot}_")
                cambios = entrada.get("cambios_anteriores", {})
                if cambios:
                    c1, c2 = st.columns(2)
                    c1.caption(f"Ingreso: **${safe_number(cambios.get('Ingreso_Original', 0)):,.2f}**")
                    c1.caption(f"Costo: **${safe_number(cambios.get('Costo_Total_Ruta', 0)):,.2f}**")
                    c2.caption(f"Ut. Neta: **${safe_number(cambios.get('Utilidad_Neta', 0)):,.2f}**")
                st.divider()

    tipo_index = TIPOS_RUTA.index(ruta["Tipo"]) if ruta.get("Tipo") in TIPOS_RUTA else 0
    modo_list  = ["Sencillo", "Team"]
    modo_index = modo_list.index(ruta.get("Modo de Viaje", "Sencillo")) if ruta.get("Modo de Viaje") in modo_list else 0

    # ── Parámetros de la ruta ──────────────────────────────────
    with st.expander("⚙️ Configuración de Parámetros", expanded=False):
        st.caption("Valores guardados originalmente con esta ruta.")
        col1, col2, col3 = st.columns(3)
        claves = list(DEFAULTS.keys())
        for i, key in enumerate(claves):
            col = [col1, col2, col3][i % 3]
            valores[key] = col.number_input(
                key,
                value=float(ruta.get(key, valores.get(key, DEFAULTS[key]))),
                step=0.1,
                key=f"prb_edit_gen_{key}",
            )

    # ══════════════════════════════════════════════════════════════
    # FORMULARIO DE EDICIÓN
    # ══════════════════════════════════════════════════════════════

    motivo = st.text_input(
        "✏️ Motivo de modificación (obligatorio)",
        placeholder="Describe el motivo del cambio...",
        key=f"prb_motivo_edicion_{idx_sel}",
    )

    divider()

    # ── Información General ───────────────────────────────────────
    st.markdown("### 📋 Información General")
    c1, c2, c3, c4 = st.columns(4)
    fecha = c1.date_input(
        "📅 Fecha",
        value=pd.to_datetime(ruta.get("Fecha"), errors="coerce").date() if ruta.get("Fecha") else datetime.today().date(),
        key=f"prb_ed_fecha_{idx_sel}",
    )
    tipo       = c2.selectbox("🚛 Tipo de Ruta",  TIPOS_RUTA, index=tipo_index,  key=f"prb_ed_tipo_{idx_sel}")
    cliente    = c3.text_input("🏢 Nombre Cliente", value=str(ruta.get("Cliente", "")), placeholder="NOMBRE DE LA EMPRESA", key=f"prb_ed_cliente_{idx_sel}")
    modo_viaje = c4.selectbox("👥 Modo de Viaje",  modo_list,  index=modo_index, key=f"prb_ed_modo_{idx_sel}")

    # ── Cruce ─────────────────────────────────────────────────────
    st.markdown("### 🛂 Cruce")
    c1, c2, c3, c4 = st.columns(4)
    moneda_cruce       = c1.selectbox("Moneda Ingreso Cruce", ["MXP", "USD"],
                                       index=["MXP","USD"].index(str(ruta.get("Moneda_Cruce","MXP"))),
                                       key=f"prb_ed_mon_cruce_{idx_sel}")
    ingreso_cruce      = c2.number_input("Ingreso Cruce", min_value=0.0,
                                          value=float(safe_number(ruta.get("Cruce_Original", 0))),
                                          key=f"prb_ed_ing_cruce_{idx_sel}")
    moneda_costo_cruce = c3.selectbox("Moneda Costo Cruce", ["MXP", "USD"],
                                       index=["MXP","USD"].index(str(ruta.get("Moneda Costo Cruce","MXP"))),
                                       key=f"prb_ed_mon_cc_{idx_sel}")
    costo_cruce        = c4.number_input("Costo Cruce", min_value=0.0,
                                          value=float(safe_number(ruta.get("Costo Cruce", 0))),
                                          key=f"prb_ed_cc_{idx_sel}")

    # ── Ruta Mexicana — searchbox ─────────────────────────────────
    st.markdown("### 🇲🇽 Ruta Mexicana")

    origen_actual  = str(ruta.get("Origen",  "") or "").strip()
    destino_actual = str(ruta.get("Destino", "") or "").strip()
    st.caption(f"📍 Valores actuales — Origen: **{origen_actual}** · Destino: **{destino_actual}**")

    c1, c2 = st.columns(2)
    with c1:
        origen_sel = st_searchbox(
            _buscar_ubicacion,
            label="📍 Origen",
            placeholder=f"Actual: {origen_actual} — escribe para cambiar...",
            key=f"prb_ed_origen_{idx_sel}",
            clear_on_submit=False,
        )
    with c2:
        destino_sel = st_searchbox(
            _buscar_ubicacion,
            label="📍 Destino",
            placeholder=f"Actual: {destino_actual} — escribe para cambiar...",
            key=f"prb_ed_destino_{idx_sel}",
            clear_on_submit=False,
        )

    # Si no seleccionaron nada nuevo, conservar el valor original
    origen  = str(origen_sel  or "").strip() or origen_actual
    destino = str(destino_sel or "").strip() or destino_actual

    c1, c2, c3, c4 = st.columns(4)
    moneda_ingreso = c1.selectbox("Moneda Ingreso Flete", ["MXP", "USD"],
                                   index=["MXP","USD"].index(str(ruta.get("Moneda","MXP"))),
                                   key=f"prb_ed_mon_ing_{idx_sel}")
    ingreso_flete  = c2.number_input("Ingreso Flete", min_value=0.0,
                                      value=float(safe_number(ruta.get("Ingreso_Original", 0))),
                                      key=f"prb_ed_ing_flete_{idx_sel}")
    km             = c3.number_input("📏 Kilómetros", min_value=0.0,
                                      value=float(safe_number(ruta.get("KM", 0))),
                                      key=f"prb_ed_km_{idx_sel}")
    casetas        = c4.number_input("🛣️ Casetas (MXP)", min_value=0.0,
                                      value=float(safe_number(ruta.get("Casetas", 0))),
                                      key=f"prb_ed_casetas_{idx_sel}")

    if tipo == "DOM MEX":
        c1, _, _, _ = st.columns(4)
        modo_pago_actual = ruta.get("Modo_Pago_Dom", "km")
        modo_pago_dom = c1.selectbox(
            "Modo pago operador",
            ["km", "fijo"],
            format_func=lambda x: "Por kilómetro" if x == "km" else "Pago fijo",
            index=["km", "fijo"].index(modo_pago_actual) if modo_pago_actual in ["km","fijo"] else 0,
            key=f"prb_ed_modo_pago_dom_{idx_sel}",
        )
    else:
        modo_pago_dom = "km"

    # ── Termo y Costos Fijos ──────────────────────────────────────
    st.markdown("### 🌡️ Termo y Costos Fijos")
    c1, c2, c3, c4 = st.columns(4)
    horas_termo      = c1.number_input("⏱️ Horas Termo",            min_value=0.0, value=float(safe_number(ruta.get("Horas_Termo", 0))),      key=f"prb_ed_horas_{idx_sel}")
    lavado_termo     = c2.number_input("🧼 Lavado Termo (MXP)",     min_value=0.0, value=float(safe_number(ruta.get("Lavado_Termo", 0))),     key=f"prb_ed_lav_{idx_sel}")
    movimiento_local = c3.number_input("🔄 Movimiento Local (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Movimiento_Local", 0))), key=f"prb_ed_mov_{idx_sel}")

    punt_guardada   = safe_number(ruta.get("Puntualidad", 0))
    factor_guardado = 2 if ruta.get("Modo de Viaje") == "Team" else 1
    puntualidad     = c4.number_input("⏰ Puntualidad (MXP)", min_value=0.0,
                                       value=float(punt_guardada / factor_guardado),
                                       key=f"prb_ed_punt_{idx_sel}")

    c1, c2, c3, c4 = st.columns(4)
    pension      = c1.number_input("🏨 Pensión (MXP)",      min_value=0.0, value=float(safe_number(ruta.get("Pension", 0))),      key=f"prb_ed_pens_{idx_sel}")
    estancia     = c2.number_input("🛌 Estancia (MXP)",     min_value=0.0, value=float(safe_number(ruta.get("Estancia", 0))),     key=f"prb_ed_est_{idx_sel}")
    fianza_termo = c3.number_input("🔒 Fianza Termo (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Fianza_Termo", 0))), key=f"prb_ed_fianza_{idx_sel}")
    renta_termo  = c4.number_input("📦 Renta Termo (MXP)",  min_value=0.0, value=float(safe_number(ruta.get("Renta_Termo", 0))),  key=f"prb_ed_renta_{idx_sel}")

    # ── Otros Costos ──────────────────────────────────────────────
    st.markdown("### 🧾 Otros Costos")
    st.caption("Captura el monto. Marca **'cobro'** si también se le cobra al cliente (suma al ingreso).")

    c1, c2, c3 = st.columns(3)
    with c1:
        pistas_extra = st.number_input("Pistas Extra (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Pistas_Extra", 0))), key=f"prb_ed_pistas_{idx_sel}")
        cobra_pistas = st.checkbox("cobro", value=bool(ruta.get("Cobra_Pistas", False)), key=f"prb_ed_cobra_pistas_{idx_sel}")
    with c2:
        stop         = st.number_input("Stop (MXP)",         min_value=0.0, value=float(safe_number(ruta.get("Stop", 0))),         key=f"prb_ed_stop_{idx_sel}")
        cobra_stop   = st.checkbox("cobro", value=bool(ruta.get("Cobra_Stop", False)),   key=f"prb_ed_cobra_stop_{idx_sel}")
    with c3:
        falso        = st.number_input("Falso (MXP)",        min_value=0.0, value=float(safe_number(ruta.get("Falso", 0))),        key=f"prb_ed_falso_{idx_sel}")
        cobra_falso  = st.checkbox("cobro", value=bool(ruta.get("Cobra_Falso", False)),  key=f"prb_ed_cobra_falso_{idx_sel}")

    c1, c2, c3 = st.columns(3)
    with c1:
        gatas        = st.number_input("Gatas (MXP)",        min_value=0.0, value=float(safe_number(ruta.get("Gatas", 0))),        key=f"prb_ed_gatas_{idx_sel}")
        cobra_gatas  = st.checkbox("cobro", value=bool(ruta.get("Cobra_Gatas", False)),  key=f"prb_ed_cobra_gatas_{idx_sel}")
    with c2:
        accesorios   = st.number_input("Accesorios (MXP)",   min_value=0.0, value=float(safe_number(ruta.get("Accesorios", 0))),   key=f"prb_ed_acc_{idx_sel}")
        cobra_acc    = st.checkbox("cobro", value=bool(ruta.get("Cobra_Accesorios", False)), key=f"prb_ed_cobra_acc_{idx_sel}")
    with c3:
        guias        = st.number_input("Guías (MXP)",        min_value=0.0, value=float(safe_number(ruta.get("Guias", 0))),        key=f"prb_ed_guias_{idx_sel}")
        cobra_guias  = st.checkbox("cobro", value=bool(ruta.get("Cobra_Guias", False)),  key=f"prb_ed_cobra_guias_{idx_sel}")

    divider()

    # ── Botón Revisar Cambios ─────────────────────────────────────
    if st.button("🔍 Revisar Cambios", type="primary", use_container_width=True, key=f"prb_ed_revisar_{idx_sel}"):
        if not motivo or not motivo.strip():
            alert("error", "⚠️ Debes especificar un motivo para la modificación.")
            st.stop()

        st.session_state["prb_revisar_edicion"] = True
        st.session_state["prb_datos_edicion"]   = {
            "id_ruta":            idx_sel,
            "motivo":             motivo.strip(),
            "fecha":              fecha,
            "tipo":               tipo,
            "cliente":            normalizar_texto(cliente),
            "origen":             normalizar_texto(origen),
            "destino":            normalizar_texto(destino),
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
    if st.session_state.get("prb_revisar_edicion", False):
        d      = st.session_state["prb_datos_edicion"]
        tc_usd = safe_float(valores.get("Tipo de cambio USD", 19.5), 19.5)

        costo_cruce_conv = d["costo_cruce"] * (tc_usd if d["moneda_costo_cruce"] == "USD" else 1)

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
            costos_fijos  + extras       + costo_cruce_conv
        )

        util = calcular_utilidades(ingreso_total, costo_total, d["tipo"])

        st.session_state["prb_calc_edicion"] = {
            "ingreso_flete_convertido":  ingreso_flete_conv,
            "tipo_cambio_flete":         tc_usd,
            "tipo_cambio_cruce":         tc_usd,
            "ingreso_cruce_convertido":  ingreso_cruce_conv,
            "costo_cruce_convertido":    costo_cruce_conv,
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
    # GUARDAR CAMBIOS
    # ══════════════════════════════════════════════════════════════
    if st.session_state.get("prb_revisar_edicion", False):
        if st.button("💾 Guardar Cambios", key="prb_save_edicion"):
            d    = st.session_state.get("prb_datos_edicion", {})
            calc = st.session_state.get("prb_calc_edicion", {})
            if not d:
                alert("error", "No hay datos de edición.")
                return

            historial_anterior = ruta.get("historial") or []
            if not isinstance(historial_anterior, list):
                historial_anterior = []

            nueva_entrada = {
                "timestamp": _now_iso(),
                "usuario":   nombre_usuario,
                "motivo":    d["motivo"],
                "cambios_anteriores": {
                    "Fecha":            ruta.get("Fecha"),
                    "Tipo":             ruta.get("Tipo"),
                    "Cliente":          ruta.get("Cliente"),
                    "Origen":           ruta.get("Origen"),
                    "Destino":          ruta.get("Destino"),
                    "Modo de Viaje":    ruta.get("Modo de Viaje"),
                    "KM":               ruta.get("KM"),
                    "Ingreso_Original": ruta.get("Ingreso_Original"),
                    "Ingreso Total":    ruta.get("Ingreso Total"),
                    "Costo_Total_Ruta": ruta.get("Costo_Total_Ruta"),
                    "Utilidad_Bruta":   ruta.get("Utilidad_Bruta"),
                    "Utilidad_Neta":    ruta.get("Utilidad_Neta"),
                },
            }
            historial_actualizado = historial_anterior + [nueva_entrada]

            ruta_actualizada = {
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
                "Cobra_Pistas":           d.get("cobra_pistas",  False),
                "Cobra_Stop":             d.get("cobra_stop",    False),
                "Cobra_Falso":            d.get("cobra_falso",   False),
                "Cobra_Gatas":            d.get("cobra_gatas",   False),
                "Cobra_Accesorios":       d.get("cobra_acc",     False),
                "Cobra_Guias":            d.get("cobra_guias",   False),
                "Extras_Cobrados":        False,
                "Costo Diesel":           float(valores.get("Costo Diesel", 24.0)),
                "Rendimiento Camion":     float(valores.get("Rendimiento Camion", 2.5)),
                "Rendimiento Termo":      float(valores.get("Rendimiento Termo", 3.0)),
                "updated_by":             nombre_usuario,
                "updated_at":             _now_iso(),
                "historial":              historial_actualizado,
            }

            try:
                sb.table(TABLE_RUTAS).update(ruta_actualizada).eq("ID_Ruta", d["id_ruta"]).execute()
                _load_rutas_cached.clear()
                _cargar_pool_ubicaciones.clear()
                st.session_state["prb_ruta_editada_id"]       = d["id_ruta"]
                st.session_state["prb_mostrar_modal_edicion"] = True
                st.rerun()
            except Exception as e:
                alert("error", f"❌ Error al actualizar: {e}")
                st.exception(e)
