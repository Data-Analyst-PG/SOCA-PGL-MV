"""
gestion_rutas.py — Cotizador Picus
Gestión: Ver tabla / Eliminar / Editar rutas guardadas.
Homologado con captura_rutas.py:
  - Orden dinámico de secciones según obtener_config_tipo_ruta()
      IMPORTACION → Cruce primero, luego Ruta MX
      EXPORTACION → Ruta MX primero, luego Cruce
      VACIO       → solo Ruta MX (sin Cruce)
  - _preview_edicion() centraliza banner + KPIs + semáforos vía mostrar_resultados_picus()
  - Historial de modificaciones guarda el SNAPSHOT COMPLETO de la versión anterior
    (todos los campos de la ruta, no solo un subconjunto) — así se puede auditar
    exactamente por qué cambió cualquier costo o ingreso. SIN CAMBIOS.
  - Tabs: Ver Rutas | Eliminar | Editar
  - Form de edición SIN st.form — usa st.button + searchbox para Origen/Destino
  - Checkboxes individuales de cobro por extra
  - Modal @st.dialog para confirmación
  - Picus conserva: Ruta_Tipo (Ruta Larga / Tramo), Modo de Viaje (Operador / Team) — NO tocar
"""
from __future__ import annotations

from io import BytesIO

import pandas as pd
import streamlit as st
from datetime import datetime
from streamlit_searchbox import st_searchbox

from services.supabase_client import get_supabase_client, current_user
from ui.components import section_header, alert, divider

from ._helpers import (
    DEFAULTS, TIPOS_RUTA,
    cargar_datos_generales,
    safe_number, safe_float,
    calcular_diesel, calcular_sueldo_bono,
    calcular_costos_fijos, calcular_extras,
    calcular_utilidades,
    get_profile_name, normalizar, now_iso,
    load_rutas_picus,
    cargar_pool_ubicaciones_picus, buscar_ubicacion_picus,
    filtrar_rutas_picus, label_ruta_picus,
    obtener_config_tipo_ruta, mostrar_resultados_picus,
)

TABLE_RUTAS = "Rutas_Picus"


# ─────────────────────────────────────────────
# Función auxiliar excel — solo usada en este módulo
# ─────────────────────────────────────────────
def _to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Rutas Picus")
    buf.seek(0)
    return buf.getvalue()


# ─────────────────────────────────────────────
# MODAL CONFIRMACIÓN EDICIÓN
# ─────────────────────────────────────────────
@st.dialog("✅ Ruta Actualizada", width="small")
def _modal_editado(id_ruta: str) -> None:
    alert("success", "**¡Los cambios se guardaron correctamente!**")
    st.info(f"### 🆔 ID de la ruta\n`{id_ruta}`")
    st.caption("Los cambios se han guardado y registrado en el historial.")
    if st.button("✅ Aceptar", type="primary", use_container_width=True, key="pic_gest_modal_ok"):
        st.session_state.pop("pic_gest_editado_id", None)
        st.session_state.pop("pic_gest_mostrar_modal", None)
        st.session_state.pop("pic_datos_edicion", None)
        st.session_state.pop("pic_calc_edicion", None)
        st.session_state["pic_revisar_edicion"] = False
        st.rerun()


# ─────────────────────────────────────────────
# PREVIEW DE EDICIÓN — centraliza banner + KPIs + semáforos
# ─────────────────────────────────────────────
def _preview_edicion(valores: dict) -> None:
    calc = st.session_state.get("pic_calc_edicion", {})
    d    = st.session_state.get("pic_datos_edicion", {})
    if not calc or not d:
        return

    tc_usd = safe_float(valores.get("Tipo de cambio USD", 17.5))

    divider()
    section_header("📊", "Vista Previa de Cambios")

    util = calcular_utilidades(
        calc["ingreso_total"],
        calc["costo_total"],
        d.get("tipo", ""),
    )
    tc_val = tc_usd if d.get("moneda_ingreso") == "USD" else 0.0
    mostrar_resultados_picus(util, tc_usd=tc_val)


# ─────────────────────────────────────────────
# RENDER PRINCIPAL
# ─────────────────────────────────────────────
def render() -> None:
    supabase = get_supabase_client()
    if supabase is None:
        alert("warn", "⚠️ Supabase no configurado.")
        return

    u = current_user() or {}
    user_id        = u.get("id") or u.get("sub") or ""
    nombre_usuario = get_profile_name(user_id) or u.get("email") or "Desconocido"

    st.session_state.setdefault("pic_revisar_edicion", False)

    # Modal tras edición exitosa
    if st.session_state.get("pic_gest_mostrar_modal"):
        _modal_editado(st.session_state["pic_gest_editado_id"])

    # ── Botón recargar ────────────────────────────────────────────────
    rc1, rc2 = st.columns([1, 4])
    with rc1:
        if st.button("🔄 Recargar rutas", key="pic_gest_reload"):
            load_rutas_picus.clear()
            st.rerun()
    with rc2:
        st.caption("Carga cacheada 2 min. Usa 'Recargar' si acabas de guardar algo.")

    valores = cargar_datos_generales()
    df      = load_rutas_picus()

    if df.empty:
        alert("warn", "⚠️ No hay rutas guardadas todavía.")
        return

    if "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.date

    # ── Tabs ──────────────────────────────────────────────────────────
    tab_ver, tab_del, tab_edit = st.tabs(["📋 Ver Rutas", "🗑️ Eliminar", "✏️ Editar"])

    # ═══════════════════════════════════════════
    # TAB VER
    # ═══════════════════════════════════════════
    with tab_ver:
        section_header("📋", "Rutas Registradas")
        df_filtrado = filtrar_rutas_picus(df, "pic_ver")

        cols_excluir = {"historial", "created_at", "updated_at"}
        cols_mostrar = [c for c in df_filtrado.columns if c not in cols_excluir]

        st.dataframe(
            df_filtrado[cols_mostrar],
            use_container_width=True,
            hide_index=True,
        )
        st.caption(f"**{len(df_filtrado)}** rutas mostradas de **{len(df)}** totales.")

        divider()
        excel_bytes = _to_excel_bytes(df_filtrado)
        st.download_button(
            "📥 Descargar Excel",
            data=excel_bytes,
            file_name="rutas_picus.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="pic_dl_excel",
        )

    # ═══════════════════════════════════════════
    # TAB ELIMINAR
    # ═══════════════════════════════════════════
    with tab_del:
        section_header("🗑️", "Eliminar Rutas")
        df_del = filtrar_rutas_picus(df, "pic_del")
        ids_disponibles = df_del["ID_Ruta"].dropna().astype(str).tolist()
        ids_eliminar = st.multiselect(
            "Selecciona ID(s) a eliminar", ids_disponibles, key="pic_del_ids"
        )
        if st.button("🗑️ Eliminar seleccionadas", key="pic_del_btn",
                     disabled=not ids_eliminar, type="primary"):
            try:
                for idr in ids_eliminar:
                    supabase.table(TABLE_RUTAS).delete().eq("ID_Ruta", idr).execute()
                alert("success", f"✅ {len(ids_eliminar)} ruta(s) eliminada(s).")
                load_rutas_picus.clear()
                st.rerun()
            except Exception as e:
                alert("error", f"❌ Error: {e}")

    # ═══════════════════════════════════════════
    # TAB EDITAR
    # ═══════════════════════════════════════════
    with tab_edit:
        section_header("✏️", "Editar Ruta Existente")

        df_edit = filtrar_rutas_picus(df, "pic_ed")
        if df_edit.empty:
            alert("warn", "No hay rutas con esos filtros.")
            return

        opciones  = [label_ruta_picus(row) for _, row in df_edit.iterrows()]
        sel       = st.selectbox("Selecciona ruta a editar", opciones, key="pic_edit_sel")
        id_editar = sel.split(" | ")[0].strip()
        ruta_row  = df[df["ID_Ruta"].astype(str) == id_editar]
        if ruta_row.empty:
            alert("error", "No se encontró la ruta.")
            return
        ruta = ruta_row.iloc[0]
        k    = id_editar  # sufijo único por ruta

        # Info auditoría
        if ruta.get("created_by"):
            st.caption(f"✏️ Creada por **{ruta.get('created_by')}** el {str(ruta.get('created_at',''))[:10]}")
        if ruta.get("updated_by"):
            st.caption(f"🔄 Última edición por **{ruta.get('updated_by')}** el {str(ruta.get('updated_at',''))[:10]}")

        # Parámetros de la ruta
        with st.expander("⚙️ Configuración de Parámetros", expanded=False):
            st.caption("Valores guardados originalmente con esta ruta.")
            claves = list(DEFAULTS.keys())
            ep1, ep2 = st.columns(2)
            for i, key in enumerate(claves):
                col = ep1 if i % 2 == 0 else ep2
                valores[key] = col.number_input(
                    key,
                    value=float(ruta.get(key, valores.get(key, DEFAULTS[key]))),
                    step=0.1,
                    key=f"pic_ed_gen_{key}",
                )

        # ── Formulario de edición — SIN st.form ──────────────────────
        motivo = st.text_input(
            "✏️ Motivo de modificación (obligatorio)",
            placeholder="Describe el motivo del cambio...",
            key=f"pic_ed_motivo_{k}",
        )

        divider()

        # ── Información General ───────────────────────────────────────
        st.markdown("### 📋 Información General")
        tipo_idx       = TIPOS_RUTA.index(str(ruta.get("Tipo", "IMPORTACION"))) if str(ruta.get("Tipo")) in TIPOS_RUTA else 0
        modo_list      = ["Operador", "Team"]
        modo_idx       = modo_list.index(str(ruta.get("Modo de Viaje", "Operador"))) if str(ruta.get("Modo de Viaje")) in modo_list else 0
        ruta_tipo_list = ["Ruta Larga", "Tramo"]
        ruta_tipo_idx  = ruta_tipo_list.index(str(ruta.get("Ruta_Tipo", "Ruta Larga"))) if str(ruta.get("Ruta_Tipo")) in ruta_tipo_list else 0

        g1, g2, g3, g4, g5 = st.columns(5)
        fecha      = g1.date_input(
            "📅 Fecha",
            value=pd.to_datetime(ruta.get("Fecha"), errors="coerce").date() if ruta.get("Fecha") else datetime.today().date(),
            key=f"pic_ed_fecha_{k}",
        )
        tipo       = g2.selectbox("🚛 Tipo de Ruta",    TIPOS_RUTA,      index=tipo_idx,      key=f"pic_ed_tipo_{k}")
        ruta_tipo  = g3.selectbox("📌 Ruta Tipo",       ruta_tipo_list,  index=ruta_tipo_idx, key=f"pic_ed_rt_{k}")
        cliente    = g4.text_input("🏢 Nombre Cliente", value=str(ruta.get("Cliente", "")),   key=f"pic_ed_cli_{k}")
        modo_viaje = g5.selectbox("👥 Modo de Viaje",   modo_list,       index=modo_idx,      key=f"pic_ed_modo_{k}")

        # ── Orden dinámico Cruce / Ruta MX según tipo (igual que captura) ──
        config = obtener_config_tipo_ruta(tipo)
        orden  = config.get("orden", ["ruta_mx"])

        moneda_cruce = ingreso_cruce = moneda_costo_cruce = costo_cruce = None
        origen = destino = moneda_ingreso = None
        km = casetas = ingreso_flete = None

        for seccion in orden:
            divider()
            if seccion == "cruce":
                st.markdown("### 🛂 Cruce")
                mon_cruce_list = ["MXP", "USD"]
                mc_idx  = mon_cruce_list.index(str(ruta.get("Moneda_Cruce", "MXP")))       if str(ruta.get("Moneda_Cruce"))       in mon_cruce_list else 0
                mcc_idx = mon_cruce_list.index(str(ruta.get("Moneda Costo Cruce", "MXP"))) if str(ruta.get("Moneda Costo Cruce")) in mon_cruce_list else 0

                c1, c2, c3, c4 = st.columns(4)
                moneda_cruce       = c1.selectbox("Moneda Ingreso Cruce", mon_cruce_list, index=mc_idx,  key=f"pic_ed_mc_{k}")
                ingreso_cruce      = c2.number_input("Ingreso Cruce",     min_value=0.0,  value=float(safe_number(ruta.get("Cruce_Original"))), key=f"pic_ed_ic_{k}")
                moneda_costo_cruce = c3.selectbox("Moneda Costo Cruce",   mon_cruce_list, index=mcc_idx, key=f"pic_ed_mcc_{k}")
                costo_cruce        = c4.number_input("Costo Cruce",       min_value=0.0,  value=float(safe_number(ruta.get("Costo Cruce"))),     key=f"pic_ed_cc_{k}")

            elif seccion == "ruta_mx":
                st.markdown("### 🇲🇽 Ruta Mexicana")
                origen_actual  = str(ruta.get("Origen",  "") or "").strip()
                destino_actual = str(ruta.get("Destino", "") or "").strip()
                st.caption(f"📍 Valores actuales — Origen: **{origen_actual}** · Destino: **{destino_actual}**")

                c1, c2 = st.columns(2)
                with c1:
                    origen_sel = st_searchbox(
                        buscar_ubicacion_picus,
                        label="📍 Origen",
                        placeholder=f"Actual: {origen_actual} — escribe para cambiar...",
                        key=f"pic_ed_origen_{k}",
                        clear_on_submit=False,
                    )
                with c2:
                    destino_sel = st_searchbox(
                        buscar_ubicacion_picus,
                        label="📍 Destino",
                        placeholder=f"Actual: {destino_actual} — escribe para cambiar...",
                        key=f"pic_ed_destino_{k}",
                        clear_on_submit=False,
                    )

                # Si el searchbox no devuelve nada, conservar el valor actual
                origen  = normalizar(str(origen_sel  or "").strip() or origen_actual)
                destino = normalizar(str(destino_sel or "").strip() or destino_actual)

                mon_flete_list = ["MXP", "USD"]
                mf_idx = mon_flete_list.index(str(ruta.get("Moneda", "MXP"))) if str(ruta.get("Moneda")) in mon_flete_list else 0
                r3, r4, r5, r6 = st.columns(4)
                moneda_ingreso = r3.selectbox("Moneda Ingreso Flete", mon_flete_list, index=mf_idx, key=f"pic_ed_mf_{k}")
                ingreso_flete  = r4.number_input("Ingreso Flete",   min_value=0.0, value=float(safe_number(ruta.get("Ingreso_Original"))), key=f"pic_ed_if_{k}")
                km             = r5.number_input("📏 Kilómetros",   min_value=0.0, value=float(safe_number(ruta.get("KM"))),               key=f"pic_ed_km_{k}")
                casetas        = r6.number_input("🛣️ Casetas (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Casetas"))),        key=f"pic_ed_cas_{k}")

        # Sin sección Cruce (tipo VACIO) → valores neutros
        if moneda_cruce is None:
            moneda_cruce, ingreso_cruce = "MXP", 0.0
            moneda_costo_cruce, costo_cruce = "MXP", 0.0

        # ── Conceptos de Costos ────────────────────────────────────────
        divider()
        st.markdown("### 🔒 Conceptos de Costos")
        st.caption("Estos costos siempre van al costo de la ruta y nunca se cobran al cliente.")
        f1, f2, f3, f4 = st.columns(4)
        movimiento_local = f1.number_input("🔄 Movimiento Local (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Movimiento_Local"))), key=f"pic_ed_ml_{k}")
        puntualidad      = f2.number_input("⏰ Puntualidad (MXP)",      min_value=0.0, value=float(safe_number(ruta.get("Puntualidad"))),       key=f"pic_ed_punt_{k}")
        pension          = f3.number_input("🏨 Pensión (MXP)",           min_value=0.0, value=float(safe_number(ruta.get("Pension"))),           key=f"pic_ed_pens_{k}")
        estancia         = f4.number_input("🛌 Estancia (MXP)",          min_value=0.0, value=float(safe_number(ruta.get("Estancia"))),          key=f"pic_ed_est_{k}")

        f1b, f2b, f3b, f4b = st.columns(4)
        fianza = f1b.number_input("🔒 Fianza (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Fianza"))), key=f"pic_ed_fianza_{k}")
        f2b.empty(); f3b.empty(); f4b.empty()

        # ── Otros Costos ───────────────────────────────────────────────
        divider()
        st.markdown("### 🧾 Otros Costos")
        st.caption("Captura el monto. Marca **'cobro'** si también se le cobra al cliente (suma al ingreso).")

        o1, o2, o3 = st.columns(3)
        with o1:
            pistas_extra   = st.number_input("Pistas Extra (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Pistas_Extra"))), key=f"pic_ed_pist_{k}")
            pistas_cobrado = st.checkbox("cobro", value=bool(ruta.get("Pistas_Cobrado", False)), key=f"pic_ed_pist_cob_{k}")
        with o2:
            stop         = st.number_input("Stop (MXP)",   min_value=0.0, value=float(safe_number(ruta.get("Stop"))),  key=f"pic_ed_stop_{k}")
            stop_cobrado = st.checkbox("cobro", value=bool(ruta.get("Stop_Cobrado",  False)), key=f"pic_ed_stop_cob_{k}")
        with o3:
            falso         = st.number_input("Falso (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Falso"))), key=f"pic_ed_falso_{k}")
            falso_cobrado = st.checkbox("cobro", value=bool(ruta.get("Falso_Cobrado", False)), key=f"pic_ed_falso_cob_{k}")

        o4, o5, o6 = st.columns(3)
        with o4:
            gatas         = st.number_input("Gatas (MXP)",      min_value=0.0, value=float(safe_number(ruta.get("Gatas"))),      key=f"pic_ed_gatas_{k}")
            gatas_cobrado = st.checkbox("cobro", value=bool(ruta.get("Gatas_Cobrado", False)), key=f"pic_ed_gatas_cob_{k}")
        with o5:
            accesorios         = st.number_input("Accesorios (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Accesorios"))),  key=f"pic_ed_acc_{k}")
            accesorios_cobrado = st.checkbox("cobro", value=bool(ruta.get("Accesorios_Cobrado", False)), key=f"pic_ed_acc_cob_{k}")
        with o6:
            guias         = st.number_input("Guías (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Guias"))), key=f"pic_ed_guias_{k}")
            guias_cobrado = st.checkbox("cobro", value=bool(ruta.get("Guias_Cobrado", False)), key=f"pic_ed_guias_cob_{k}")

        # ── Botón Revisar Cambios ──────────────────────────────────────
        divider()
        if st.button("🔍 Revisar Cambios", use_container_width=True, type="primary", key=f"pic_ed_revisar_{k}"):
            if not motivo.strip():
                alert("error", "⚠️ Debes indicar el motivo de la modificación.")
                st.stop()
            if not origen:
                alert("error", "⚠️ El campo Origen es obligatorio.")
                st.stop()
            if not destino:
                alert("error", "⚠️ El campo Destino es obligatorio.")
                st.stop()

            tc_usd = safe_float(valores.get("Tipo de cambio USD", 17.5))
            tc_mxp = safe_float(valores.get("Tipo de cambio MXP", 1.0))

            tipo_cambio_flete       = tc_usd if moneda_ingreso     == "USD" else tc_mxp
            tipo_cambio_cruce       = tc_usd if moneda_cruce       == "USD" else tc_mxp
            tipo_cambio_costo_cruce = tc_usd if moneda_costo_cruce == "USD" else tc_mxp

            ingreso_flete_convertido = ingreso_flete * tipo_cambio_flete
            ingreso_cruce_convertido = ingreso_cruce * tipo_cambio_cruce
            costo_cruce_convertido   = costo_cruce   * tipo_cambio_costo_cruce

            costo_diesel_camion = calcular_diesel(km, valores)

            sb              = calcular_sueldo_bono(km, tipo, ruta_tipo, modo_viaje, valores)
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
                costo_diesel_camion + sueldo + bono
                + casetas + costos_fijos + costo_extras + costo_cruce_convertido
            )

            st.session_state["pic_revisar_edicion"] = True
            st.session_state["pic_datos_edicion"]   = {
                "id_editar":           id_editar,
                "motivo":              motivo,
                "fecha":               fecha,
                "tipo":                tipo,
                "ruta_tipo":           ruta_tipo,
                "cliente":             normalizar(cliente),
                "origen":              origen,
                "destino":             destino,
                "modo_viaje_ui":       modo_viaje,
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
            st.session_state["pic_calc_edicion"] = {
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

        # ── Mostrar resultado y botón Guardar Cambios ─────────────────
        if (
            st.session_state.get("pic_revisar_edicion")
            and st.session_state.get("pic_datos_edicion", {}).get("id_editar") == id_editar
        ):
            _preview_edicion(valores)

            calc = st.session_state.get("pic_calc_edicion", {})
            d    = st.session_state.get("pic_datos_edicion", {})

            if st.button("💾 Guardar Cambios", key=f"pic_confirm_edit_{k}", type="primary"):
                historial_actual = ruta.get("historial") or []
                if not isinstance(historial_actual, list):
                    historial_actual = []

                # Snapshot completo de los campos auditables antes del cambio
                campos_auditados = [
                    "Fecha", "Tipo", "Ruta_Tipo", "Cliente", "Origen", "Destino", "Modo de Viaje",
                    "KM", "Moneda", "Ingreso_Original", "Moneda_Cruce", "Cruce_Original",
                    "Moneda Costo Cruce", "Costo Cruce",
                    "Tipo de cambio", "Tipo cambio Cruce",
                    "Ingreso Flete", "Ingreso Cruce", "Ingreso Total",
                    "Costo Cruce Convertido",
                    "Costo_Diesel_Camion", "Sueldo_Operador", "Bono",
                    "Casetas", "Costos_Fijos", "Costo_Extras", "Ingresos_Extras",
                    "Costo_Total_Ruta", "Pago por KM",
                    "Movimiento_Local", "Puntualidad", "Pension", "Estancia", "Fianza",
                    "Pistas_Extra", "Pistas_Cobrado",
                    "Stop", "Stop_Cobrado",
                    "Falso", "Falso_Cobrado",
                    "Gatas", "Gatas_Cobrado",
                    "Accesorios", "Accesorios_Cobrado",
                    "Guias", "Guias_Cobrado",
                    "Rendimiento Camion", "Costo Diesel",
                ]

                def _to_native(v):
                    if v is None:
                        return None
                    try:
                        import math
                        if isinstance(v, float) and math.isnan(v):
                            return None
                    except Exception:
                        pass
                    if hasattr(v, "item"):
                        return v.item()
                    if hasattr(v, "isoformat"):
                        return str(v)
                    return v

                datos_anteriores = {
                    c: _to_native(ruta.get(c))
                    for c in campos_auditados
                    if c in ruta.index
                }

                historial_actual.append({
                    "at":               now_iso(),
                    "by":               nombre_usuario,
                    "motivo":           d["motivo"],
                    "datos_anteriores": datos_anteriores,
                })

                ruta_actualizada = {
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
                    "updated_by":             nombre_usuario,
                    "updated_at":             now_iso(),
                    "historial":              historial_actual,
                }

                try:
                    supabase.table(TABLE_RUTAS).update(ruta_actualizada).eq("ID_Ruta", id_editar).execute()
                    load_rutas_picus.clear()
                    cargar_pool_ubicaciones_picus.clear()
                    st.session_state["pic_gest_editado_id"]    = id_editar
                    st.session_state["pic_gest_mostrar_modal"] = True
                    st.session_state.pop("pic_revisar_edicion", None)
                    st.session_state.pop("pic_datos_edicion",   None)
                    st.session_state.pop("pic_calc_edicion",    None)
                    st.rerun()
                except Exception as e:
                    alert("error", f"❌ Error al guardar: {e}")

        # ── Historial ─────────────────────────────────────────────────
        divider()
        st.markdown("### 🧠 Historial de modificaciones")
        historial = ruta.get("historial") or []
        if not isinstance(historial, list):
            historial = []
        if not historial:
            alert("info", "Esta ruta no tiene modificaciones registradas aún.")
        else:
            for h in reversed(historial):
                if not isinstance(h, dict):
                    continue
                with st.expander(f"🕐 {str(h.get('at',''))[:19].replace('T',' ')} — {h.get('by','')} — {h.get('motivo','')}"):
                    datos_ant = h.get("datos_anteriores", {})
                    if datos_ant:
                        st.markdown("**Valores anteriores a la modificación:**")
                        cols = st.columns(3)
                        for i, (kk, v) in enumerate(datos_ant.items()):
                            with cols[i % 3]:
                                st.write(f"**{kk}:** {v}")
