"""
gestion_rutas.py — Cotizador Picus
Diseño homologado con Igloo:
  - Sin st.title(), tabs: Ver Rutas | Eliminar | Editar
  - Formulario de edición con mismo orden que captura_rutas:
      Info General → Cruce → Ruta Mexicana → Conceptos de Costos → Otros Costos
  - Checkbox individual por extra (igual que captura)
  - Recalculo via helpers.py (sin lógica inline)
  - Modal @st.dialog para confirmar guardado
  - Historial de modificaciones
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import streamlit as st

from services.supabase_client import get_supabase_client, get_authed_client, current_user
from ui.components import section_header, alert, divider

from .helpers import (
    DEFAULTS,
    TIPOS_RUTA,
    cargar_datos_generales,
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


@st.cache_data(show_spinner=False, ttl=120)
def _load_rutas_picus_cached() -> pd.DataFrame:
    supabase = get_supabase_client()
    if supabase is None:
        return pd.DataFrame()
    try:
        resp = supabase.table("Rutas_Picus").select("*").order("Fecha", desc=True).execute()
        return pd.DataFrame(resp.data) if resp.data else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def _to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Rutas Picus")
    buf.seek(0)
    return buf.getvalue()


def _label(row) -> str:
    return (
        f"{row.get('ID_Ruta','')} | {str(row.get('Fecha',''))[:10]} | "
        f"{row.get('Tipo','')} | {row.get('Cliente','')} | "
        f"{row.get('Origen','')} → {row.get('Destino','')}"
    )


def _filtrar(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    with st.expander("🔎 Filtros (opcional)", expanded=False):
        fc1, fc2, fc3, fc4, fc5 = st.columns(5)
        tipos    = ["Todos"] + sorted(df["Tipo"].dropna().unique().tolist()) if "Tipo" in df.columns else ["Todos"]
        clientes = ["Todos"] + sorted(df["Cliente"].dropna().astype(str).unique().tolist()) if "Cliente" in df.columns else ["Todos"]
        f_tipo   = fc1.selectbox("Tipo",    tipos,    key=f"{prefix}_ftipo")
        f_cli    = fc2.selectbox("Cliente", clientes, key=f"{prefix}_fcli")
        f_ori    = fc3.text_input("Origen contiene",  key=f"{prefix}_fori")
        f_dest   = fc4.text_input("Destino contiene", key=f"{prefix}_fdest")
        f_id     = fc5.text_input("ID contiene",      key=f"{prefix}_fid")

    r = df.copy()
    if f_tipo    != "Todos": r = r[r["Tipo"].astype(str)    == f_tipo]
    if f_cli     != "Todos": r = r[r["Cliente"].astype(str) == f_cli]
    if f_ori:  r = r[r["Origen"].astype(str).str.upper().str.contains(f_ori.upper(),  na=False)]
    if f_dest: r = r[r["Destino"].astype(str).str.upper().str.contains(f_dest.upper(), na=False)]
    if f_id:   r = r[r["ID_Ruta"].astype(str).str.upper().str.contains(f_id.upper(),  na=False)]
    return r


# ─────────────────────────────────────────────
# Modal confirmación edición
# ─────────────────────────────────────────────

@st.dialog("✅ Ruta Actualizada", width="small")
def _modal_editado(id_ruta: str) -> None:
    alert("success", "**¡Los cambios se guardaron correctamente!**")
    st.info(f"### 🆔 ID de la ruta\n`{id_ruta}`")
    if st.button("✅ Aceptar", type="primary", use_container_width=True, key="pic_gest_modal_ok"):
        st.session_state.pop("pic_gest_editado_id", None)
        st.session_state.pop("pic_gest_mostrar_modal", None)
        st.rerun()


# ─────────────────────────────────────────────
# Render principal
# ─────────────────────────────────────────────

def render() -> None:
    supabase = get_supabase_client()
    if supabase is None:
        alert("warn", "⚠️ Supabase no configurado.")
        return

    u = current_user() or {}
    user_id        = u.get("id") or u.get("sub") or ""
    nombre_usuario = _get_profile_name(user_id) or u.get("email") or "Desconocido"

    # Modal tras edición exitosa
    if st.session_state.get("pic_gest_mostrar_modal"):
        _modal_editado(st.session_state["pic_gest_editado_id"])

    # ── Botón recargar ────────────────────────────────────────────────
    rc1, rc2 = st.columns([1, 4])
    with rc1:
        if st.button("🔄 Recargar rutas", key="pic_gest_reload"):
            _load_rutas_picus_cached.clear()
            st.rerun()
    with rc2:
        st.caption("Carga cacheada 2 min. Usa 'Recargar' si acabas de guardar algo.")

    valores = cargar_datos_generales()
    df      = _load_rutas_picus_cached()

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
        df_filtrado = _filtrar(df, "pic_ver")

        cols_mostrar = [c for c in [
            "ID_Ruta","Fecha","Tipo","Ruta_Tipo","Cliente","Origen","Destino",
            "Modo de Viaje","KM","Ingreso Total","Costo_Total_Ruta",
        ] if c in df_filtrado.columns]

        st.dataframe(df_filtrado[cols_mostrar] if cols_mostrar else df_filtrado,
                     use_container_width=True)
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
        df_del = _filtrar(df, "pic_del")
        ids_disponibles = df_del["ID_Ruta"].dropna().astype(str).tolist()
        ids_eliminar = st.multiselect(
            "Selecciona ID(s) a eliminar", ids_disponibles, key="pic_del_ids"
        )
        if st.button("🗑️ Eliminar seleccionadas", key="pic_del_btn",
                     disabled=not ids_eliminar, type="primary"):
            try:
                for idr in ids_eliminar:
                    supabase.table("Rutas_Picus").delete().eq("ID_Ruta", idr).execute()
                alert("success", f"✅ {len(ids_eliminar)} ruta(s) eliminada(s).")
                _load_rutas_picus_cached.clear()
                st.rerun()
            except Exception as e:
                alert("error", f"❌ Error: {e}")

    # ═══════════════════════════════════════════
    # TAB EDITAR
    # ═══════════════════════════════════════════
    with tab_edit:
        section_header("✏️", "Editar Ruta Existente")

        df_edit = _filtrar(df, "pic_edit")
        if df_edit.empty:
            alert("warn", "No hay rutas con esos filtros.")
            return

        opciones = [_label(row) for _, row in df_edit.iterrows()]
        sel      = st.selectbox("Selecciona ruta a editar", opciones, key="pic_edit_sel")
        id_editar = sel.split(" | ")[0].strip()
        ruta_row  = df[df["ID_Ruta"].astype(str) == id_editar]
        if ruta_row.empty:
            alert("error", "No se encontró la ruta.")
            return
        ruta = ruta_row.iloc[0]

        # Info auditoría
        if ruta.get("created_by"):
            st.caption(f"✏️ Creada por **{ruta.get('created_by')}** el {str(ruta.get('created_at',''))[:10]}")
        if ruta.get("updated_by"):
            st.caption(f"🔄 Última edición por **{ruta.get('updated_by')}** el {str(ruta.get('updated_at',''))[:10]}")

        # Parámetros de la ruta (expander)
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

        # ── Formulario de edición ─────────────────────────────────────
        k = id_editar  # sufijo único por ruta

        with st.form(f"pic_editar_{k}"):

            motivo = st.text_input(
                "✏️ Motivo de modificación (obligatorio)",
                placeholder="Describe el motivo del cambio...",
                key=f"pic_ed_motivo_{k}",
            )

            divider()

            # ── Información General ───────────────────────────────────
            st.markdown("### 📋 Información General")
            tipo_idx = TIPOS_RUTA.index(str(ruta.get("Tipo","IMPORTACION"))) if str(ruta.get("Tipo")) in TIPOS_RUTA else 0
            modo_list = ["Operador", "Team"]
            modo_idx  = modo_list.index(str(ruta.get("Modo de Viaje","Operador"))) if str(ruta.get("Modo de Viaje")) in modo_list else 0
            ruta_tipo_list = ["Ruta Larga", "Tramo"]
            ruta_tipo_idx  = ruta_tipo_list.index(str(ruta.get("Ruta_Tipo","Ruta Larga"))) if str(ruta.get("Ruta_Tipo")) in ruta_tipo_list else 0

            g1, g2, g3, g4, g5 = st.columns(5)
            fecha         = g1.date_input("📅 Fecha", value=pd.to_datetime(ruta.get("Fecha"), errors="coerce").date() if ruta.get("Fecha") else datetime.today().date(), key=f"pic_ed_fecha_{k}")
            tipo          = g2.selectbox("🚛 Tipo de Ruta", TIPOS_RUTA, index=tipo_idx, key=f"pic_ed_tipo_{k}")
            ruta_tipo     = g3.selectbox("📌 Ruta Tipo", ruta_tipo_list, index=ruta_tipo_idx, key=f"pic_ed_rt_{k}")
            cliente       = g4.text_input("🏢 Nombre Cliente", value=str(ruta.get("Cliente","")), key=f"pic_ed_cli_{k}")
            modo_viaje    = g5.selectbox("👥 Modo de Viaje", modo_list, index=modo_idx, key=f"pic_ed_modo_{k}")

            # ── Cruce ─────────────────────────────────────────────────
            st.markdown("### 🛂 Cruce")
            mon_cruce_list = ["MXP", "USD"]
            mc_idx  = mon_cruce_list.index(str(ruta.get("Moneda_Cruce","MXP"))) if str(ruta.get("Moneda_Cruce")) in mon_cruce_list else 0
            mcc_idx = mon_cruce_list.index(str(ruta.get("Moneda Costo Cruce","MXP"))) if str(ruta.get("Moneda Costo Cruce")) in mon_cruce_list else 0

            c1, c2, c3, c4 = st.columns(4)
            moneda_cruce       = c1.selectbox("Moneda Ingreso Cruce", mon_cruce_list, index=mc_idx,  key=f"pic_ed_mc_{k}")
            ingreso_cruce      = c2.number_input("Ingreso Cruce",     min_value=0.0, value=float(safe_number(ruta.get("Cruce_Original"))),    key=f"pic_ed_ic_{k}")
            moneda_costo_cruce = c3.selectbox("Moneda Costo Cruce",   mon_cruce_list, index=mcc_idx, key=f"pic_ed_mcc_{k}")
            costo_cruce        = c4.number_input("Costo Cruce",       min_value=0.0, value=float(safe_number(ruta.get("Costo Cruce"))),        key=f"pic_ed_cc_{k}")

            # ── Ruta Mexicana ──────────────────────────────────────────
            st.markdown("### 🇲🇽 Ruta Mexicana")
            r1, r2 = st.columns(2)
            origen  = r1.text_input("📍 Origen",  value=str(ruta.get("Origen","")),  placeholder="CIUDAD, ESTADO", key=f"pic_ed_ori_{k}")
            destino = r2.text_input("📍 Destino", value=str(ruta.get("Destino","")), placeholder="CIUDAD, ESTADO", key=f"pic_ed_dest_{k}")

            mon_flete_list = ["MXP", "USD"]
            mf_idx = mon_flete_list.index(str(ruta.get("Moneda","MXP"))) if str(ruta.get("Moneda")) in mon_flete_list else 0
            r3, r4, r5, r6 = st.columns(4)
            moneda_ingreso = r3.selectbox("Moneda Ingreso Flete", mon_flete_list, index=mf_idx, key=f"pic_ed_mf_{k}")
            ingreso_flete  = r4.number_input("Ingreso Flete",  min_value=0.0, value=float(safe_number(ruta.get("Ingreso_Original"))), key=f"pic_ed_if_{k}")
            km             = r5.number_input("📏 Kilómetros",  min_value=0.0, value=float(safe_number(ruta.get("KM"))),               key=f"pic_ed_km_{k}")
            casetas        = r6.number_input("🛣️ Casetas (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Casetas"))),        key=f"pic_ed_cas_{k}")

            # ── Conceptos de Costos ────────────────────────────────────
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

            # ── Otros Costos ───────────────────────────────────────────
            st.markdown("### 🧾 Otros Costos")
            st.caption("Captura el monto. Marca **'cobro'** si también se le cobra al cliente (suma al ingreso).")

            o1, o2, o3 = st.columns(3)
            with o1:
                pistas_extra   = st.number_input("Pistas Extra (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Pistas_Extra"))), key=f"pic_ed_pist_{k}")
                pistas_cobrado = st.checkbox("cobro", value=bool(ruta.get("Pistas_Cobrado", False)), key=f"pic_ed_pist_cob_{k}")
            with o2:
                stop         = st.number_input("Stop (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Stop"))), key=f"pic_ed_stop_{k}")
                stop_cobrado = st.checkbox("cobro", value=bool(ruta.get("Stop_Cobrado", False)), key=f"pic_ed_stop_cob_{k}")
            with o3:
                falso         = st.number_input("Falso (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Falso"))), key=f"pic_ed_falso_{k}")
                falso_cobrado = st.checkbox("cobro", value=bool(ruta.get("Falso_Cobrado", False)), key=f"pic_ed_falso_cob_{k}")

            o4, o5, o6 = st.columns(3)
            with o4:
                gatas         = st.number_input("Gatas (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Gatas"))), key=f"pic_ed_gatas_{k}")
                gatas_cobrado = st.checkbox("cobro", value=bool(ruta.get("Gatas_Cobrado", False)), key=f"pic_ed_gatas_cob_{k}")
            with o5:
                accesorios         = st.number_input("Accesorios (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Accesorios"))), key=f"pic_ed_acc_{k}")
                accesorios_cobrado = st.checkbox("cobro", value=bool(ruta.get("Accesorios_Cobrado", False)), key=f"pic_ed_acc_cob_{k}")
            with o6:
                guias         = st.number_input("Guías (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Guias"))), key=f"pic_ed_guias_{k}")
                guias_cobrado = st.checkbox("cobro", value=bool(ruta.get("Guias_Cobrado", False)), key=f"pic_ed_guias_cob_{k}")

            divider()
            revisar_ed = st.form_submit_button("🔍 Revisar Cambios", use_container_width=True, type="primary")

        # ── Recálculo tras Revisar Cambios ────────────────────────────
        if revisar_ed:
            if not motivo.strip():
                alert("error", "⚠️ Debes indicar el motivo de la modificación.")
            else:
                st.session_state["pic_revisar_edicion"] = True

                tc_usd = safe_float(valores.get("Tipo de cambio USD", 17.5))
                tc_mxp = safe_float(valores.get("Tipo de cambio MXP", 1.0))

                tipo_cambio_flete       = tc_usd if moneda_ingreso    == "USD" else tc_mxp
                tipo_cambio_cruce       = tc_usd if moneda_cruce      == "USD" else tc_mxp
                tipo_cambio_costo_cruce = tc_usd if moneda_costo_cruce == "USD" else tc_mxp

                costo_cruce_convertido   = costo_cruce   * tipo_cambio_costo_cruce
                ingreso_flete_convertido = ingreso_flete * tipo_cambio_flete
                ingreso_cruce_convertido = ingreso_cruce * tipo_cambio_cruce

                costo_diesel_camion = calcular_diesel(km, valores)

                sb = calcular_sueldo_bono(km, tipo, ruta_tipo, modo_viaje, valores)
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
                    costo_diesel_camion + sueldo + bono
                    + casetas + costos_fijos + costo_extras + costo_cruce_convertido
                )

                util = calcular_utilidades(ingreso_total, costo_total, tipo)

                st.session_state["pic_datos_edicion"] = {
                    "id_editar":           id_editar,
                    "motivo":              motivo,
                    "fecha":               fecha,
                    "tipo":                tipo,
                    "ruta_tipo":           ruta_tipo,
                    "cliente":             cliente,
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

        # ── Mostrar resultado y botón Guardar Cambios ─────────────────
        if st.session_state.get("pic_revisar_edicion") and st.session_state.get("pic_datos_edicion", {}).get("id_editar") == id_editar:
            calc = st.session_state.get("pic_calc_edicion", {})
            d    = st.session_state.get("pic_datos_edicion", {})

            if calc:
                tc_usd = safe_float(valores.get("Tipo de cambio USD", 17.5))
                divider()
                section_header("📊", "Resultado con los Cambios")
                mostrar_resultados_utilidad(
                    st,
                    calc["ingreso_total"], calc["costo_total"],
                    calc["utilidad_bruta"], calc["costos_indirectos"],
                    calc["utilidad_neta"], calc["porcentaje_bruta"], calc["porcentaje_neta"],
                    tipo=d.get("tipo",""),
                    tc_usd=tc_usd if d.get("moneda_ingreso") == "USD" else 0.0,
                )

                if st.button("💾 Guardar Cambios", key=f"pic_confirm_edit_{k}", type="primary"):
                    historial_actual = ruta.get("historial") or []
                    if not isinstance(historial_actual, list):
                        historial_actual = []

                    # Campos anteriores para auditoría
                    campos_auditados = [
                        "Tipo","Ruta_Tipo","Cliente","Origen","Destino","Modo de Viaje",
                        "KM","Moneda","Ingreso_Original","Moneda_Cruce","Cruce_Original",
                        "Costo Cruce","Casetas","Movimiento_Local","Puntualidad",
                        "Pension","Estancia","Fianza","Pistas_Extra","Stop","Falso",
                        "Gatas","Accesorios","Guias","Ingreso Total","Costo_Total_Ruta",
                    ]
                    datos_anteriores = {c: ruta.get(c) for c in campos_auditados if c in ruta.index}

                    historial_actual.append({
                        "at":               _now_iso(),
                        "by":               nombre_usuario,
                        "motivo":           d["motivo"],
                        "datos_anteriores": datos_anteriores,
                    })

                    ruta_actualizada = {
                        "Fecha":                 str(d["fecha"]),
                        "Tipo":                  d["tipo"],
                        "Ruta_Tipo":             d["ruta_tipo"],
                        "Cliente":               d["cliente"],
                        "Origen":                d["origen"],
                        "Destino":               d["destino"],
                        "Modo de Viaje":         calc["modo_viaje_calc"],
                        "KM":                    d["km"],
                        "Moneda":                d["moneda_ingreso"],
                        "Ingreso_Original":      d["ingreso_flete"],
                        "Tipo de cambio":        calc["tipo_cambio_flete"],
                        "Ingreso Flete":         calc["ingreso_flete_convertido"],
                        "Moneda_Cruce":          d["moneda_cruce"],
                        "Cruce_Original":        d["ingreso_cruce"],
                        "Tipo cambio Cruce":     calc["tipo_cambio_cruce"],
                        "Ingreso Cruce":         calc["ingreso_cruce_convertido"],
                        "Moneda Costo Cruce":    d["moneda_costo_cruce"],
                        "Costo Cruce":           d["costo_cruce"],
                        "Costo Cruce Convertido": calc["costo_cruce_convertido"],
                        "Ingreso Total":         calc["ingreso_total"],
                        "Pago por KM":           calc["pago_km"],
                        "Sueldo_Operador":       calc["sueldo"],
                        "Bono":                  calc["bono"],
                        "Casetas":               d["casetas"],
                        "Movimiento_Local":      d["movimiento_local"],
                        "Puntualidad":           d["puntualidad"],
                        "Pension":               d["pension"],
                        "Estancia":              d["estancia"],
                        "Fianza":                d["fianza"],
                        "Pistas_Extra":          d["pistas_extra"],
                        "Pistas_Cobrado":        d["pistas_cobrado"],
                        "Stop":                  d["stop"],
                        "Stop_Cobrado":          d["stop_cobrado"],
                        "Falso":                 d["falso"],
                        "Falso_Cobrado":         d["falso_cobrado"],
                        "Gatas":                 d["gatas"],
                        "Gatas_Cobrado":         d["gatas_cobrado"],
                        "Accesorios":            d["accesorios"],
                        "Accesorios_Cobrado":    d["accesorios_cobrado"],
                        "Guias":                 d["guias"],
                        "Guias_Cobrado":         d["guias_cobrado"],
                        "Costo_Diesel_Camion":   calc["costo_diesel_camion"],
                        "Costos_Fijos":          calc["costos_fijos"],
                        "Costo_Extras":          calc["costo_extras"],
                        "Ingresos_Extras":       calc["ingreso_extras"],
                        "Costo_Total_Ruta":      calc["costo_total"],
                        "Costo Diesel":          safe_float(valores.get("Costo Diesel", 24.0)),
                        "Rendimiento Camion":    safe_float(valores.get("Rendimiento Camion", 2.5)),
                        "updated_by":            nombre_usuario,
                        "updated_at":            _now_iso(),
                        "historial":             historial_actual,
                    }

                    try:
                        supabase.table("Rutas_Picus").update(ruta_actualizada).eq("ID_Ruta", id_editar).execute()
                        _load_rutas_picus_cached.clear()
                        st.session_state["pic_gest_editado_id"]    = id_editar
                        st.session_state["pic_gest_mostrar_modal"] = True
                        st.session_state.pop("pic_revisar_edicion", None)
                        st.session_state.pop("pic_datos_edicion", None)
                        st.session_state.pop("pic_calc_edicion", None)
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
