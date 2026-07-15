"""
gestion_rutas.py – Set Logis Plus
Formulario de edición con estructura visual idéntica a captura_rutas.py:
  - Mismos section headers, mismos layouts de columnas
  - obtener_config_tipo_ruta() para orden de secciones
  - st.radio para Modalidad
  - Preview caption tarifa Desglosada
  - help= en millas
  - st_searchbox en Origen/Destino USA y MX
  - 3 cols (tipo/carga/moneda) en Cruce
  - Caption en extras
  - Caption dirección + MX en Info General

Diferencias Set Logis que se preservan:
  - Fuel_Owner checkbox
  - Modo: "Individual" / "Team"
  - 3 millas: Miles Load, Short Miles, Miles Empty
  - modo_costo_indirecto: CXM vs %
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO

import pandas as pd
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
    limpiar_fila_json,
    safe,
    calcular_ruta_setlogis,
    obtener_config_tipo_ruta,
    tiene_mx,
    normalizar,
    a_usd,
    get_profile_name,
    now_iso,
    load_rutas_setlogis,
    filtrar_rutas_setlogis,
    label_ruta_setlogis,
    buscar_ubicacion_setlogis,
    cargar_pool_ubicaciones_setlogis,
    mostrar_resultados_setlogis,
    log_accion,
)


# ─────────────────────────────────────────────
# Función auxiliar excel — solo usada en este módulo
# ─────────────────────────────────────────────
def _to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Rutas SetLogis")
    buf.seek(0)
    return buf.getvalue()


# ─────────────────────────────────────────────
# MODAL CONFIRMACIÓN EDICIÓN
# ─────────────────────────────────────────────
@st.dialog("✅ Ruta Actualizada Exitosamente", width="small")
def _modal_edicion(id_ruta: str) -> None:
    alert("success", "**¡La ruta se actualizó correctamente!**")
    st.info(f"### 🆔 ID de la ruta\n`{id_ruta}`")
    st.caption("Los cambios se han guardado y registrado en el historial.")
    if st.button("✅ Aceptar", type="primary", use_container_width=True, key="sl_modal_ed_ok"):
        st.session_state.pop("sl_ed_ruta_id",     None)
        st.session_state.pop("sl_ed_modal",       None)
        st.session_state.pop("sl_edit_resultado", None)
        st.session_state.pop("sl_edit_datos",     None)
        st.session_state.pop("sl_edit_id_rev",    None)
        st.rerun()


# ─────────────────────────────────────────────
# PREVIEW EDICIÓN
# ─────────────────────────────────────────────
def _preview_edicion(r: dict, fd: dict) -> None:
    # Función auxiliar — solo usada en este módulo
    mostrar_resultados_setlogis(
        r,
        modalidad  = fd.get("modalidad", "Flat"),
        miles_load = safe(r.get("Miles_Load", 0.0)),
        cxm_flete  = fd.get("cxm_flete_cap", 0.0),
        cxm_fuel   = fd.get("cxm_fuel_cap",  0.0),
    )


# ─────────────────────────────────────────────
# GUARDAR EDICIÓN EN SUPABASE
# ─────────────────────────────────────────────
def _guardar_edicion(supabase, idx_sel, ruta, r_prev, d_prev, nombre_usuario, historial_ant):
    try:
        entrada_historial = {
            "timestamp": now_iso(),
            "usuario":   nombre_usuario,
            "motivo":    d_prev["motivo"],
            "valores_anteriores": {
                "Ingreso_Global":      ruta.get("Ingreso_Global"),
                "Flete_USA":           ruta.get("Flete_USA"),
                "Fuel":                ruta.get("Fuel"),
                "Ingreso_Cruce":       ruta.get("Ingreso_Cruce"),
                "Ingreso_MX":          ruta.get("Ingreso_MX"),
                "Extras_Ingreso":      ruta.get("Extras_Ingreso"),
                "Costo_Directo":       ruta.get("Costo_Directo"),
                "Pago_Owner_Cargado":  ruta.get("Pago_Owner_Cargado"),
                "Pago_Owner_Vacio":    ruta.get("Pago_Owner_Vacio"),
                "Fuel_Owner":          ruta.get("Fuel_Owner"),
                "Pago_Fuel_Owner":     ruta.get("Pago_Fuel_Owner"),
                "Costo_Cruce":         ruta.get("Costo_Cruce"),
                "Costo_MX":            ruta.get("Costo_MX"),
                "Costo_Indirecto":     ruta.get("Costo_Indirecto"),
                "Costo_Total":         ruta.get("Costo_Total"),
                "Utilidad_Bruta":      ruta.get("Utilidad_Bruta"),
                "Utilidad_Neta":       ruta.get("Utilidad_Neta"),
                "Pct_Costo_Directo":   ruta.get("Pct_Costo_Directo"),
                "Pct_Costo_Indirecto": ruta.get("Pct_Costo_Indirecto"),
                "Pct_Ut_Bruta":        ruta.get("Pct_Ut_Bruta"),
                "Pct_Ut_Neta":         ruta.get("Pct_Ut_Neta"),
                "Miles_Load":          ruta.get("Miles_Load"),
                "Short_Miles":         ruta.get("Short_Miles"),
                "Miles_Empty":         ruta.get("Miles_Empty"),
                "Modalidad":           ruta.get("Modalidad"),
                "CXM_Flete":           ruta.get("CXM_Flete"),
                "CXM_Fuel":            ruta.get("CXM_Fuel"),
                "Modo_Costo_Indirecto":ruta.get("Modo_Costo_Indirecto"),
                "Tipo_Viaje":          ruta.get("Tipo_Viaje"),
                "Modo":                ruta.get("Modo"),
                "Fecha":               ruta.get("Fecha"),
                "TC_USD_MXP":          ruta.get("TC_USD_MXP"),
            },
        }
        historial_nuevo = list(historial_ant) + [entrada_historial]

        extras_db         = {f"Extra_{n.replace(' ','_')}": v
                             for n, v in d_prev.get("otros_cargos", {}).items()}
        extras_cobrado_db = {f"Extra_{n.replace(' ','_')}_Cobrado": v
                             for n, v in d_prev.get("otros_pagados", {}).items()}

        fila = {
            "Tipo_Viaje":            r_prev["Tipo_Viaje"],
            "Modo":                  r_prev["Modo"],
            "Direccion":             r_prev["Direccion"],
            "Modalidad":             d_prev["modalidad"],
            "Modo_Costo_Indirecto":  d_prev["modo_ci"],
            "Cliente":               r_prev["Cliente"],
            "Origen":                r_prev["Origen"],
            "Destino":               r_prev["Destino"],
            "Origen_MX":             d_prev["origen_mx"],
            "Destino_MX":            d_prev["destino_mx"],
            "Moneda_Flete":          d_prev["mon_flete"],
            "Moneda_Ingreso_Cruce":  d_prev["mon_ing_cruce"],
            "Moneda_Costo_Cruce":    d_prev["mon_costo_cruce"],
            "Moneda_Ingreso_MX":     d_prev["mon_ing_mx"],
            "Moneda_Costo_MX":       d_prev["mon_costo_mx"],
            "Tipo_Carga_Cruce":      d_prev["tipo_carga_cruce"],
            "Incluye_Cruce":         d_prev["incluye_cruce"],
            "Miles_Load":            r_prev["Miles_Load"],
            "Miles_Empty":           r_prev["Miles_Empty"],
            "Short_Miles":           r_prev["Short_Miles"],
            "Millas_Totales":        r_prev["Millas_Totales"],
            "CXM_Flete":             d_prev["cxm_flete_cap"],
            "CXM_Fuel":              d_prev["cxm_fuel_cap"],
            "Flete_Flat":            r_prev.get("Flete_Flat", d_prev["flete_flat_cap"]),
            "Flete_USA":             r_prev["Flete_USA"],
            "Fuel":                  r_prev["Fuel"],
            "Flete_Fuel":            r_prev["Flete_Fuel"],
            "Ingreso_Cruce":         r_prev["Ingreso_Cruce"],
            "Tipo_Cruce":            r_prev["Tipo_Cruce"],
            "Ingreso_MX":            d_prev.get("ingreso_mx", 0.0),
            "Flete_MEX":             r_prev["Ingreso_MX"],
            "Extras_Ingreso":        r_prev["Extras_Ingreso"],
            "Extras_Costo":          r_prev["Extras_Costo"],
            "Ingreso_Global":        r_prev["Ingreso_Global"],
            "PxM_Cargado":           r_prev["PxM_Cargado"],
            "PxM_Vacio":             r_prev["PxM_Vacio"],
            "Pago_Owner_Cargado":    r_prev["Pago_Owner_Cargado"],
            "Pago_Owner_Vacio":      r_prev["Pago_Owner_Vacio"],
            "Pago_Owner_Total":      r_prev["Pago_Owner_Total"],
            "Fuel_Owner":            r_prev.get("Fuel_Owner", False),
            "Pago_Fuel_Owner":       r_prev.get("Pago_Fuel_Owner", 0.0),
            "Costo_Cruce":           r_prev["Costo_Cruce"],
            "Costo_MX":              d_prev.get("costo_mx", 0.0),
            "Costo_MEX":             r_prev["Costo_MX"],
            "Costo_Directo":         r_prev["Costo_Directo"],
            "Costo_Indirecto":       r_prev["Costo_Indirecto"],
            "Costo_Total":           r_prev["Costo_Total"],
            "Utilidad_Bruta":        r_prev["Utilidad_Bruta"],
            "Utilidad_Neta":         r_prev["Utilidad_Neta"],
            "Pct_Costo_Directo":     r_prev["Pct_Costo_Directo"],
            "Pct_Costo_Indirecto":   r_prev["Pct_Costo_Indirecto"],
            "Pct_Ut_Bruta":          r_prev["Pct_Ut_Bruta"],
            "Pct_Ut_Neta":           r_prev["Pct_Ut_Neta"],
            "TC_USD_MXP":            r_prev["TC"],
            "updated_by":            nombre_usuario,
            "updated_at":            now_iso(),
            "historial":             historial_nuevo,
            **extras_db,
            **extras_cobrado_db,
        }

        fila_limpia = limpiar_fila_json(fila)
        supabase.table(TABLE_RUTAS).update(fila_limpia).eq("ID_Ruta", idx_sel).execute()
        log_accion("editar_ruta", {"id_ruta": idx_sel})

        load_rutas_setlogis.clear()
        cargar_pool_ubicaciones_setlogis.clear()

        st.session_state["sl_ed_ruta_id"] = idx_sel
        st.session_state["sl_ed_modal"]   = True
        st.session_state.pop("sl_edit_resultado", None)
        st.session_state.pop("sl_edit_datos",     None)
        st.session_state.pop("sl_edit_id_rev",    None)
        st.rerun()

    except Exception as ex:
        alert("error", f"❌ Error al guardar cambios: {ex}")


# ─────────────────────────────────────────────
# RENDER PRINCIPAL
# ─────────────────────────────────────────────
def render() -> None:
    supabase = get_supabase_client()
    if supabase is None:
        alert("error", "⚠️ Supabase no configurado.")
        return

    u              = current_user() or {}
    user_id        = u.get("id") or u.get("sub") or ""
    nombre_usuario = get_profile_name(user_id) or u.get("email") or "Desconocido"

    # Modal post-edición
    if st.session_state.get("sl_ed_modal") and st.session_state.get("sl_ed_ruta_id"):
        _modal_edicion(st.session_state["sl_ed_ruta_id"])

    # Recargar
    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("🔄 Recargar", key="sl_gest_reload"):
            load_rutas_setlogis.clear()
            cargar_pool_ubicaciones_setlogis.clear()
            st.rerun()
    with c2:
        st.caption("Carga cacheada 2 min. Usa 'Recargar' si acabas de guardar algo.")

    df = load_rutas_setlogis(TABLE_RUTAS)
    if df.empty:
        alert("info", "ℹ️ No hay rutas guardadas aún.")
        return

    if "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.date

    valores = cargar_datos_generales()
    tc      = safe(valores.get("Tipo de Cambio USD/MXP", DEFAULTS["Tipo de Cambio USD/MXP"]))

    tab_ver, tab_del, tab_edit = st.tabs(["📋 Ver Rutas", "🗑️ Eliminar", "✏️ Editar"])

    # ══════════════════════════════════════════════════════════════
    # TAB VER
    # ══════════════════════════════════════════════════════════════
    with tab_ver:
        section_header("📋", "Rutas Registradas")
        df_tabla  = filtrar_rutas_setlogis(df, "sl_ver")
        COLS      = [
            "ID_Ruta", "Fecha", "Tipo_Viaje", "Modo", "Cliente", "Origen", "Destino",
            "Miles_Load", "Short_Miles", "Miles_Empty",
            "Ingreso_Global", "Costo_Directo", "Utilidad_Bruta",
            "Pct_Ut_Bruta", "Costo_Indirecto", "Utilidad_Neta",
            "Pct_Ut_Neta", "Fuel_Owner", "Usuario",
        ]
        cols_disp = [c for c in COLS if c in df_tabla.columns]
        st.dataframe(
            df_tabla[cols_disp] if cols_disp else df_tabla,
            use_container_width=True, hide_index=True,
        )
        st.caption(f"Mostrando **{len(df_tabla)}** de **{len(df)}** rutas")
        divider()
        descargado_excel = st.download_button(
            "📥 Descargar Excel",
            data=_to_excel_bytes(df_tabla[cols_disp] if cols_disp else df_tabla),
            file_name=f"rutas_setlogis_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="sl_dl_excel",
        )
        if descargado_excel:
            log_accion("exportar_excel", {"filas": len(df_tabla)})

    # ══════════════════════════════════════════════════════════════
    # TAB ELIMINAR
    # ══════════════════════════════════════════════════════════════
    with tab_del:
        section_header("🗑️", "Eliminar Rutas")
        df_del = filtrar_rutas_setlogis(df, "sl_del")
        if df_del.empty:
            alert("info", "No hay rutas con los filtros aplicados.")
        else:
            ids_eliminar = st.multiselect(
                "Selecciona ID(s) a eliminar",
                df_del["ID_Ruta"].dropna().astype(str).tolist(),
                key="sl_del_ids",
            )
            if st.button("🗑️ Eliminar seleccionadas", key="sl_del_btn",
                         disabled=not ids_eliminar, type="primary"):
                try:
                    for idr in ids_eliminar:
                        supabase.table(TABLE_RUTAS).delete().eq("ID_Ruta", idr).execute()
                    log_accion("eliminar_ruta", {"ids_ruta": ids_eliminar})
                    load_rutas_setlogis.clear()
                    cargar_pool_ubicaciones_setlogis.clear()
                    alert("success", f"✅ {len(ids_eliminar)} ruta(s) eliminada(s).")
                    st.rerun()
                except Exception as ex:
                    alert("error", f"❌ Error al eliminar: {ex}")

    # ══════════════════════════════════════════════════════════════
    # TAB EDITAR
    # ══════════════════════════════════════════════════════════════
    with tab_edit:
        section_header("✏️", "Editar Ruta")

        df_ed = filtrar_rutas_setlogis(df, "sl_ed")
        if df_ed.empty:
            alert("info", "No hay rutas con los filtros aplicados.")
            return
        if "ID_Ruta" not in df_ed.columns:
            return

        opciones = df_ed["ID_Ruta"].dropna().astype(str).tolist()
        st.caption(f"Rutas disponibles: **{len(opciones)}**")
        idx_sel = st.selectbox(
            "Selecciona ruta a editar",
            options=[""] + opciones,
            format_func=lambda i: "— Elige una ruta —" if i == "" else label_ruta_setlogis(
                df_ed[df_ed["ID_Ruta"] == i].iloc[0].to_dict()
            ),
            key="sl_ed_select",
        )
        if not idx_sel:
            alert("info", "Selecciona una ruta para editarla.")
            return

        ruta = df_ed[df_ed["ID_Ruta"] == idx_sel].iloc[0].to_dict()
        k    = str(idx_sel)

        # ── Auditoría ──────────────────────────────────────────────────────────
        if ruta.get("Usuario"):
            st.caption(
                f"👤 Capturada por: **{ruta.get('Usuario')}** "
                f"· Fecha: **{ruta.get('Fecha', '—')}**"
            )

        # ── Historial ──────────────────────────────────────────────────────────
        import json as _json
        historial = ruta.get("historial") or []
        if isinstance(historial, str):
            try:
                historial = _json.loads(historial)
            except Exception:
                historial = []

        if historial:
            with st.expander(f"📜 Historial de modificaciones ({len(historial)})", expanded=False):
                for entrada in reversed(historial):
                    ts  = str(entrada.get("timestamp", ""))[:16].replace("T", " ")
                    usr = entrada.get("usuario", "—")
                    mot = entrada.get("motivo",  "—")
                    st.caption(f"**{ts}** · {usr} · _{mot}_")
                    prev = entrada.get("valores_anteriores", {})
                    if prev:
                        c1, c2, c3 = st.columns(3)
                        c1.caption(f"Ingreso: **${safe(prev.get('Ingreso_Global')):,.2f}**")
                        c1.caption(f"C. Directo: **${safe(prev.get('Costo_Directo')):,.2f}**")
                        c1.caption(f"C. Indirecto: **${safe(prev.get('Costo_Indirecto')):,.2f}**")
                        c2.caption(f"Ut. Bruta: **${safe(prev.get('Utilidad_Bruta')):,.2f}** ({safe(prev.get('Pct_Ut_Bruta')):.1f}%)")
                        c2.caption(f"Ut. Neta: **${safe(prev.get('Utilidad_Neta')):,.2f}** ({safe(prev.get('Pct_Ut_Neta')):.1f}%)")
                        c3.caption(f"Miles Load: **{safe(prev.get('Miles_Load')):.0f}**")
                        c3.caption(f"Short Miles: **{safe(prev.get('Short_Miles')):.0f}**")
                        c3.caption(f"Miles Empty: **{safe(prev.get('Miles_Empty')):.0f}**")
                    st.divider()
        else:
            st.caption("📜 Sin modificaciones previas.")

        divider()

        # ── Leer config de tipo para ordenar secciones ────────────────────────
        tipo_ruta_val = str(ruta.get("Tipo_Viaje", TIPOS_RUTA[0]))
        config        = obtener_config_tipo_ruta(tipo_ruta_val)
        orden         = config.get("orden", ["americana"])
        es_empty      = (tipo_ruta_val == "Empty")
        aplica_mx     = config.get("parte_mx", False)
        modalidad_val = str(ruta.get("Modalidad", "Flat"))

        # ── Motivo (obligatorio) ───────────────────────────────────────────────
        st.markdown("### ⚙️ Motivo de modificación")
        motivo = st.text_input(
            "Motivo (obligatorio)",
            placeholder="Ej: Corrección de millas",
            key=f"sl_ed_motivo_{k}",
        )

        # ── INFO GENERAL — idéntico a _seccion_info_general() de captura ──────
        divider()
        st.markdown("### 📋 Información General")
        eg1, eg2, eg3, eg4 = st.columns(4)

        try:
            from datetime import date as _date
            fecha_dt = _date.fromisoformat(str(ruta.get("Fecha", ""))[:10])
        except Exception:
            fecha_dt = datetime.today().date()

        fecha  = eg1.date_input("📅 Fecha", value=fecha_dt, key=f"sl_ed_fecha_{k}")
        tipo_ruta = eg2.selectbox(
            "🚛 Tipo de Ruta", TIPOS_RUTA,
            index=TIPOS_RUTA.index(tipo_ruta_val) if tipo_ruta_val in TIPOS_RUTA else 0,
            key=f"sl_ed_tipo_{k}", disabled=True,
        )
        cliente_actual = str(ruta.get("Cliente", ""))
        cliente = eg3.text_input("🏢 Cliente", value=cliente_actual, key=f"sl_ed_cliente_{k}")
        modo    = eg4.selectbox(
            "👥 Modo", ["Individual", "Team"],
            index=0 if ruta.get("Modo", "Individual") == "Individual" else 1,
            key=f"sl_ed_modo_{k}",
        )

        # Caption dirección + MX — igual que captura
        dir_label = "Bajada" if tipo_ruta_val in {"SB", "D2DSB"} else "Subida"
        mx_label  = "Sí" if aplica_mx else "No"
        st.caption(f"📌 Dirección: **{dir_label}** · Tramo MX: **{mx_label}**")

        # ── Valores por defecto de secciones opcionales ────────────────────────
        origen_actual  = str(ruta.get("Origen",  ""))
        destino_actual = str(ruta.get("Destino", ""))
        miles_load    = safe(ruta.get("Miles_Load"))
        short_miles   = safe(ruta.get("Short_Miles"))
        miles_empty   = safe(ruta.get("Miles_Empty"))
        modalidad     = modalidad_val
        moneda_flete  = str(ruta.get("Moneda_Flete", "USD"))
        cxm_flete_cap = safe(ruta.get("CXM_Flete"))
        cxm_fuel_cap  = safe(ruta.get("CXM_Fuel"))
        flete_flat_cap= safe(ruta.get("Flete_Flat"))
        fuel_owner_ed = bool(ruta.get("Fuel_Owner", False))
        incluye_cruce = bool(ruta.get("Incluye_Cruce", False))
        tipo_cruce    = str(ruta.get("Tipo_Cruce",        "Propio"))
        tipo_carga_c  = str(ruta.get("Tipo_Carga_Cruce",  "Cargado"))
        mon_ing_cruce = str(ruta.get("Moneda_Ingreso_Cruce", "USD"))
        ingreso_cruce_raw = safe(ruta.get("Ingreso_Cruce"))
        mon_costo_cruce   = str(ruta.get("Moneda_Costo_Cruce", "USD"))
        costo_cruce_raw   = safe(ruta.get("Costo_Cruce"))
        origen_mx_val  = str(ruta.get("Origen_MX",  ""))
        destino_mx_val = str(ruta.get("Destino_MX", ""))
        mon_ing_mx  = str(ruta.get("Moneda_Ingreso_MX", "USD"))
        ingreso_mx_raw = safe(ruta.get("Ingreso_MX"))
        mon_costo_mx   = str(ruta.get("Moneda_Costo_MX", "USD"))
        costo_mx_raw   = safe(ruta.get("Costo_MX"))

        # ── SECCIONES EN ORDEN según tipo — idéntico a captura ────────────────
        for seccion in orden:
            divider()

            # ── RUTA AMERICANA ─────────────────────────────────────────────────
            if seccion == "americana":
                st.markdown("### 🇺🇸 Ruta Americana")
                ru1, ru2 = st.columns(2)
                with ru1:
                    origen_sel = st_searchbox(
                        buscar_ubicacion_setlogis,
                        label="📍 Origen USA",
                        placeholder="Buscar o nueva ubicación...",
                        key=f"sl_ed_ori_{k}",
                        clear_on_submit=False,
                    )
                    st.caption(f"Actual: **{origen_actual}**")
                with ru2:
                    destino_sel = st_searchbox(
                        buscar_ubicacion_setlogis,
                        label="📍 Destino USA",
                        placeholder="Buscar o nueva ubicación...",
                        key=f"sl_ed_dest_{k}",
                        clear_on_submit=False,
                    )
                    st.caption(f"Actual: **{destino_actual}**")

                origen_usa  = str(origen_sel  or "").strip() or origen_actual
                destino_usa = str(destino_sel or "").strip() or destino_actual

                m1, m2, m3 = st.columns(3)
                miles_load  = m1.number_input(
                    "🛣️ Miles Load", value=safe(ruta.get("Miles_Load")),
                    min_value=0.0, step=10.0, key=f"sl_ed_ml_{k}",
                    help="Millas que se cotizan al cliente (base del ingreso Desglosado)",
                    disabled=es_empty,
                )
                short_miles = m2.number_input(
                    "🔀 Short Miles", value=safe(ruta.get("Short_Miles")),
                    min_value=0.0, step=1.0, key=f"sl_ed_sm_{k}",
                    help="Millas reales recorridas cargado (base del pago al owner)",
                    disabled=es_empty,
                )
                miles_empty = m3.number_input(
                    "⚪ Miles Empty", value=safe(ruta.get("Miles_Empty")),
                    min_value=0.0, step=10.0, key=f"sl_ed_me_{k}",
                    help="Millas en vacío (pago owner vacío)",
                )

                if not es_empty:
                    divider()
                    st.markdown("**💵 Tarifa Americana**")
                    mod1, mod2 = st.columns([1, 3])
                    mod_idx  = 0 if modalidad_val == "Desglosada" else 1
                    modalidad = mod1.radio(
                        "Modalidad", ["Desglosada", "Flat"],
                        index=mod_idx, horizontal=False, key=f"sl_ed_mod_{k}",
                    )
                    if modalidad == "Desglosada":
                        td1, td2, td3 = mod2.columns(3)
                        moneda_flete  = td1.selectbox(
                            "💱 Moneda", ["USD", "MXP"],
                            index=0 if moneda_flete == "USD" else 1,
                            key=f"sl_ed_mon_flete_{k}",
                        )
                        cxm_flete_cap = td2.number_input(
                            "CXM Flete ($/mi)", value=safe(ruta.get("CXM_Flete")),
                            min_value=0.0, step=0.001, format="%.4f",
                            key=f"sl_ed_cxmf_{k}",
                        )
                        cxm_fuel_cap  = td3.number_input(
                            "CXM Fuel  ($/mi)", value=safe(ruta.get("CXM_Fuel")),
                            min_value=0.0, step=0.001, format="%.4f",
                            key=f"sl_ed_cxmu_{k}",
                        )
                        if miles_load > 0:
                            preview = (safe(cxm_flete_cap) + safe(cxm_fuel_cap)) * safe(miles_load)
                            mod2.caption(
                                f"Vista previa: (CXM Flete ${safe(cxm_flete_cap):.4f}"
                                f" + Fuel ${safe(cxm_fuel_cap):.4f})"
                                f" × {miles_load:.0f} ML"
                                f" = **${preview:,.2f} USD**"
                            )
                        flete_flat_cap = 0.0
                    else:
                        tf1, tf2 = mod2.columns(2)
                        moneda_flete   = tf1.selectbox(
                            "💱 Moneda", ["USD", "MXP"],
                            index=0 if moneda_flete == "USD" else 1,
                            key=f"sl_ed_mon_flete_flat_{k}",
                        )
                        flete_flat_cap = tf2.number_input(
                            "Tarifa Total (Flat)", value=safe(ruta.get("Flete_Flat")),
                            min_value=0.0, step=50.0, key=f"sl_ed_flat_{k}",
                        )
                        cxm_flete_cap = 0.0
                        cxm_fuel_cap  = 0.0

                    # Fuel Owner — exclusivo de Set Logis
                    fuel_owner_ed = st.checkbox(
                        "⛽ Fuel Owner — el fuel se paga al owner (suma a Costo Directo)",
                        value=bool(ruta.get("Fuel_Owner", False)),
                        key=f"sl_ed_fo_{k}",
                    )
                else:
                    modalidad     = "Flat"
                    moneda_flete  = "USD"
                    cxm_flete_cap = 0.0
                    cxm_fuel_cap  = 0.0
                    flete_flat_cap= 0.0
                    fuel_owner_ed = False
                    origen_usa    = origen_actual
                    destino_usa   = destino_actual

            # ── CRUCE — 3 cols (tipo/carga/moneda) idéntico a captura ──────────
            elif seccion == "cruce":
                if not es_empty and config.get("cruce") in ("opcional", True):
                    st.markdown("### 🛂 Cruce Fronterizo")
                    incluye_cruce = st.checkbox(
                        "¿Incluye cruce?",
                        value=bool(ruta.get("Incluye_Cruce", False)),
                        key=f"sl_ed_inc_cr_{k}",
                    )
                    if incluye_cruce:
                        cx1, cx2, cx3 = st.columns(3)
                        tipo_cruce   = cx1.selectbox(
                            "Tipo de Cruce", ["Propio", "Tercero"],
                            index=0 if tipo_cruce == "Propio" else 1,
                            key=f"sl_ed_tipo_cr_{k}",
                        )
                        tipo_carga_c = cx2.selectbox(
                            "Carga del cruce", ["Cargado", "Vacío"],
                            index=0 if tipo_carga_c == "Cargado" else 1,
                            key=f"sl_ed_tipo_cg_{k}",
                        )
                        mon_ing_cruce = cx3.selectbox(
                            "💱 Moneda Ingreso", ["USD", "MXP"],
                            index=0 if mon_ing_cruce == "USD" else 1,
                            key=f"sl_ed_mon_ic_{k}",
                        )
                        ing_col, costo_col = st.columns(2)
                        ingreso_cruce_raw = ing_col.number_input(
                            "Ingreso Cruce", value=safe(ruta.get("Ingreso_Cruce")),
                            min_value=0.0, step=5.0, format="%.2f",
                            key=f"sl_ed_ing_cr_{k}",
                        )
                        if tipo_cruce == "Tercero":
                            costo_cruce_raw = costo_col.number_input(
                                "Costo Cruce Tercero", value=safe(ruta.get("Costo_Cruce")),
                                min_value=0.0, step=5.0, format="%.2f",
                                key=f"sl_ed_costo_cr_{k}",
                            )

            # ── PARTE MX — searchbox igual que _seccion_tramo_mx() de captura ─
            elif seccion == "mx":
                if aplica_mx and not es_empty:
                    st.markdown("### 🇲🇽 Parte Mexicana")
                    mx1, mx2 = st.columns(2)
                    with mx1:
                        origen_mx_sel = st_searchbox(
                            buscar_ubicacion_setlogis,
                            label="📍 Origen MX",
                            placeholder="Buscar o nueva ubicación...",
                            key=f"sl_ed_ori_mx_{k}",
                            clear_on_submit=False,
                        )
                        st.caption(f"Actual: **{origen_mx_val}**")
                        destino_mx_sel = st_searchbox(
                            buscar_ubicacion_setlogis,
                            label="📍 Destino MX",
                            placeholder="Buscar o nueva ubicación...",
                            key=f"sl_ed_dest_mx_{k}",
                            clear_on_submit=False,
                        )
                        st.caption(f"Actual: **{destino_mx_val}**")

                    origen_mx_val  = str(origen_mx_sel  or "").strip() or origen_mx_val
                    destino_mx_val = str(destino_mx_sel or "").strip() or destino_mx_val

                    mon_ing_mx  = mx2.selectbox(
                        "💱 Moneda Ingreso MX", ["USD", "MXP"],
                        index=0 if mon_ing_mx == "USD" else 1,
                        key=f"sl_ed_mon_ing_mx_{k}",
                    )
                    ingreso_mx_raw = mx2.number_input(
                        "Ingreso Flete MX", value=safe(ruta.get("Ingreso_MX")),
                        min_value=0.0, step=100.0, format="%.2f",
                        key=f"sl_ed_ing_mx_{k}",
                    )
                    mon_costo_mx = mx2.selectbox(
                        "💱 Moneda Costo MX", ["USD", "MXP"],
                        index=0 if mon_costo_mx == "USD" else 1,
                        key=f"sl_ed_mon_costo_mx_{k}",
                    )
                    costo_mx_raw = mx2.number_input(
                        "Costo Flete MX", value=safe(ruta.get("Costo_MX")),
                        min_value=0.0, step=100.0, format="%.2f",
                        key=f"sl_ed_costo_mx_{k}",
                    )

        # ── EXTRAS — caption idéntico a captura ───────────────────────────────
        divider()
        st.markdown("### ➕ Extras / Otros Conceptos")
        st.caption(
            "Captura el monto si Set Logis lo pagó (suma al costo). "
            "Marca **'cobrado'** si también se le cobró al cliente (suma al ingreso)."
        )
        otros_cargos  = {}
        otros_pagados = {}
        cols_ext = st.columns(3)
        for i, nombre in enumerate(EXTRAS_USA):
            col   = cols_ext[i % 3]
            key_e = nombre.replace(" ", "_")
            monto   = col.number_input(
                nombre, value=safe(ruta.get(f"Extra_{key_e}", 0.0)),
                min_value=0.0, step=0.01, format="%.2f",
                key=f"sl_ed_ex_{key_e}_{k}",
            )
            cobrado = col.checkbox(
                f"Cobrado al cliente ({nombre})",
                value=bool(ruta.get(f"Extra_{key_e}_Cobrado", False)),
                key=f"sl_ed_cob_{key_e}_{k}",
            )
            if monto > 0:
                otros_cargos[nombre]  = monto
                otros_pagados[nombre] = cobrado

        # ── COSTO INDIRECTO — exclusivo de Set Logis ──────────────────────────
        divider()
        st.markdown("### 📊 Costo Indirecto")
        modo_ci_actual = str(ruta.get("Modo_Costo_Indirecto", "CXM"))
        modo_ci = st.radio(
            "Método de cálculo",
            ["CXM", "%"],
            index=0 if modo_ci_actual == "CXM" else 1,
            horizontal=True, key=f"sl_ed_ci_{k}",
            help="CXM = costo por milla total · % = porcentaje del ingreso global",
        )

        # ── BOTÓN REVISAR ─────────────────────────────────────────────────────
        divider()
        if st.button("🔍 Revisar Cambios", type="primary",
                     use_container_width=True, key=f"sl_ed_revisar_{k}"):
            if not motivo.strip():
                alert("warn", "⚠️ El motivo de modificación es obligatorio.")
                st.stop()

            # Convertir monedas a USD
            if es_empty:
                flete_usd = fuel_usd = 0.0
            elif modalidad == "Desglosada":
                flete_usd = a_usd(safe(cxm_flete_cap) * safe(miles_load), moneda_flete, tc)
                fuel_usd  = a_usd(safe(cxm_fuel_cap)  * safe(miles_load), moneda_flete, tc)
            else:
                flete_usd = a_usd(safe(flete_flat_cap), moneda_flete, tc)
                fuel_usd  = 0.0

            ing_cruce_usd   = 0.0
            costo_cruce_usd = 0.0
            if incluye_cruce and not es_empty:
                ing_cruce_usd   = ingreso_cruce_raw if mon_ing_cruce == "USD" else a_usd(ingreso_cruce_raw, mon_ing_cruce, tc)
                costo_cruce_usd = costo_cruce_raw if tipo_cruce == "Tercero" else 0.0

            ing_mx_usd   = a_usd(ingreso_mx_raw, mon_ing_mx,  tc)
            costo_mx_usd = a_usd(costo_mx_raw,   mon_costo_mx, tc)

            extras_ingreso    = sum(v for n, v in otros_cargos.items() if otros_pagados.get(n, False))
            extras_costo_puro = sum(v for n, v in otros_cargos.items() if not otros_pagados.get(n, False))

            r_calc = calcular_ruta_setlogis(
                tipo_ruta            = tipo_ruta_val,
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
                tipo_carga_cruce     = tipo_carga_c,
                ingreso_cruce        = ing_cruce_usd,
                costo_cruce_externo  = costo_cruce_usd,
                ingreso_mx           = ing_mx_usd,
                costo_mx             = costo_mx_usd,
                extras_ingreso       = extras_ingreso,
                extras_costo         = extras_costo_puro,
                modo_costo_indirecto = modo_ci,
                valores              = valores,
                fuel_owner           = fuel_owner_ed,
                incluye_cruce        = incluye_cruce and not es_empty,
            )

            st.session_state["sl_edit_resultado"] = r_calc
            st.session_state["sl_edit_id_rev"]    = idx_sel
            st.session_state["sl_edit_datos"]      = {
                "motivo":           motivo,
                "modalidad":        modalidad,
                "modo_ci":          modo_ci,
                "cxm_flete_cap":    safe(cxm_flete_cap) if modalidad == "Desglosada" else 0.0,
                "cxm_fuel_cap":     safe(cxm_fuel_cap)  if modalidad == "Desglosada" else 0.0,
                "flete_flat_cap":   flete_flat_cap if modalidad == "Flat" else 0.0,
                "mon_flete":        moneda_flete if not es_empty else "USD",
                "mon_ing_cruce":    mon_ing_cruce,
                "mon_costo_cruce":  mon_costo_cruce,
                "mon_ing_mx":       mon_ing_mx,
                "mon_costo_mx":     mon_costo_mx,
                "ingreso_mx":       ingreso_mx_raw if aplica_mx else 0.0,
                "costo_mx":         costo_mx_raw   if aplica_mx else 0.0,
                "origen_mx":        normalizar(origen_mx_val)  if aplica_mx else "",
                "destino_mx":       normalizar(destino_mx_val) if aplica_mx else "",
                "tipo_carga_cruce": tipo_carga_c if incluye_cruce and not es_empty else "",
                "incluye_cruce":    incluye_cruce and not es_empty,
                "otros_cargos":     otros_cargos,
                "otros_pagados":    otros_pagados,
                "fuel_owner":       fuel_owner_ed,
            }

        # ── VISTA PREVIA ──────────────────────────────────────────────────────
        r_prev = st.session_state.get("sl_edit_resultado")
        d_prev = st.session_state.get("sl_edit_datos", {})
        id_rev = st.session_state.get("sl_edit_id_rev")

        if r_prev and d_prev and id_rev == idx_sel:
            divider()
            _preview_edicion(r_prev, d_prev)
            divider()
            if st.button("💾 Guardar Cambios en Base de Datos", key=f"sl_guardar_ed_{k}",
                         type="primary", use_container_width=True):
                _guardar_edicion(
                    supabase       = supabase,
                    idx_sel        = idx_sel,
                    ruta           = ruta,
                    r_prev         = r_prev,
                    d_prev         = d_prev,
                    nombre_usuario = nombre_usuario,
                    historial_ant  = historial,
                )
