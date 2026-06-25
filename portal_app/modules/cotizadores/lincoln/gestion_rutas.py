"""
gestion_rutas.py – Lincoln Freight (USA/MX)
Homologado con Igloo y Picus:
  - Sin st.title(), tabs: Ver Rutas | Eliminar | Editar
  - Sin funciones locales duplicadas — todo va en _shared.py
  - Edición SIN st.form — usa st.button + st_searchbox para Origen/Destino
  - mostrar_resultados_ruta() + banner_tarifa_sugerida() de components
  - Historial de modificaciones
  - Modal @st.dialog para confirmar guardado
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO

import pandas as pd
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
    limpiar_fila_json,
    safe,
    calcular_ruta_lincoln,
    obtener_config_tipo_ruta,
    normalizar,
    a_usd,
    get_profile_name,
    now_iso,
    load_rutas_lincoln,
    filtrar_rutas_lincoln,
    label_ruta_lincoln,
    buscar_ubicacion_lincoln,
    cargar_pool_ubicaciones_lincoln,
)


# ─────────────────────────────────────────────
# Función auxiliar excel — solo usada en este módulo
# ─────────────────────────────────────────────
def _to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Rutas Lincoln")
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
    if st.button("✅ Aceptar", type="primary", use_container_width=True, key="ln_gest_modal_ok"):
        st.session_state.pop("ln_gest_editado_id", None)
        st.session_state.pop("ln_gest_mostrar_modal", None)
        st.session_state.pop("ln_ed_resultado", None)
        st.session_state.pop("ln_ed_datos", None)
        st.session_state["ln_revisar_edicion"] = False
        st.rerun()


# ─────────────────────────────────────────────
# PREVIEW EDICIÓN
# ─────────────────────────────────────────────
def _preview_edicion(r: dict, fd: dict) -> None:
    # Función auxiliar — solo usada en este módulo
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

    tipo_ruta   = fd.get("tipo", "NB")
    es_empty    = (tipo_ruta == "Empty")
    short_miles = fd.get("short_miles", 0.0)
    miles_empty = fd.get("miles_empty", 0.0)
    factor      = 2 if fd.get("modo_viaje") == "Team" else 1

    if es_empty:
        filas = [
            (f"Operador Vacío ({miles_empty:.0f} mi × ${r['cxm_vacio']:.4f})", r["sueldo_base"]),
            (f"Diesel ({miles_empty:.0f} mi vacías)", r["diesel_usa"]),
        ]
    else:
        filas = [
            (f"Sueldo Cargado ({short_miles:.0f} Short Mi × ${r['cxm_cargado']:.4f})",
             short_miles * r["cxm_cargado"] * factor),
            (f"Sueldo Vacío ({miles_empty:.0f} Mi Vacías × ${r['cxm_vacio']:.4f})",
             miles_empty * r["cxm_vacio"] * factor),
            (f"Bono ({short_miles:.0f} Short Mi × ${r['bono_por_milla']:.3f})", r["bono_millas"]),
            (f"Diesel ({short_miles:.0f} SM + {miles_empty:.0f} ME)", r["diesel_usa"]),
            ("ISR/IMSS", r["isr_imss"]),
        ]
        if r.get("otros_cargos_costo", 0) > 0:
            filas.append(("Otros Conceptos (Lincoln pagó)", r["otros_cargos_costo"]))

    desglose_ruta(
        r,
        filas_costo_americana=filas,
        modalidad=fd.get("modalidad", "Flat"),
        cxm_flete=fd.get("cxm_flete", 0.0),
        cxm_fuel=fd.get("cxm_fuel", 0.0),
    )


# ─────────────────────────────────────────────
# RENDER PRINCIPAL
# ─────────────────────────────────────────────
def render() -> None:
    sb = get_supabase_client()
    if sb is None:
        alert("error", "Supabase no configurado.")
        return

    u              = current_user() or {}
    user_id        = u.get("id") or u.get("sub") or ""
    nombre_usuario = get_profile_name(user_id) or u.get("email") or "Desconocido"

    st.session_state.setdefault("ln_revisar_edicion", False)

    # Modal tras edición exitosa
    if st.session_state.get("ln_gest_mostrar_modal") and st.session_state.get("ln_gest_editado_id"):
        _modal_edicion(st.session_state["ln_gest_editado_id"])

    # ── Recargar ──────────────────────────────────────────────────
    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("🔄 Recargar", key="ln_gest_reload"):
            load_rutas_lincoln.clear()
            st.rerun()
    with c2:
        st.caption("Carga cacheada 2 min. Usa 'Recargar' si acabas de guardar algo.")

    valores = cargar_datos_generales()
    df      = load_rutas_lincoln(TABLE_RUTAS)

    if df.empty:
        alert("info", "No hay rutas guardadas aún.")
        return

    if "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.date

    # ── Tabs ──────────────────────────────────────────────────────
    tab_ver, tab_del, tab_edit = st.tabs(["📋 Ver Rutas", "🗑️ Eliminar", "✏️ Editar"])

    # ══════════════════════════════════════════════════════════════
    # TAB VER
    # ══════════════════════════════════════════════════════════════
    with tab_ver:
        section_header("📋", "Rutas Registradas")

        df_tabla = filtrar_rutas_lincoln(df, "ln_ver")

        COLS = [
            "ID_Ruta", "Fecha", "Tipo", "Cliente", "Modo_Viaje",
            "Origen", "Destino", "Miles_Load", "Short_Miles", "Miles_Empty",
            "Ingreso_Total", "Costo_Directo_Total", "Utilidad_Bruta",
            "Pct_Utilidad_Bruta", "Costos_Indirectos", "Utilidad_Neta",
            "Pct_Utilidad_Neta", "Capturado_Por",
        ]
        cols_disp = [c for c in COLS if c in df_tabla.columns]
        st.dataframe(
            df_tabla[cols_disp] if cols_disp else df_tabla,
            use_container_width=True, hide_index=True,
        )
        st.caption(f"Mostrando **{len(df_tabla)}** de **{len(df)}** rutas")

        divider()
        st.download_button(
            "📥 Descargar Excel",
            data=_to_excel_bytes(df_tabla[cols_disp] if cols_disp else df_tabla),
            file_name=f"rutas_lincoln_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="ln_dl_excel",
        )

    # ══════════════════════════════════════════════════════════════
    # TAB ELIMINAR
    # ══════════════════════════════════════════════════════════════
    with tab_del:
        section_header("🗑️", "Eliminar Rutas")

        df_del = filtrar_rutas_lincoln(df, "ln_del")
        if df_del.empty:
            alert("info", "No hay rutas con los filtros aplicados.")
        else:
            ids_disponibles = df_del["ID_Ruta"].dropna().astype(str).tolist()
            ids_eliminar = st.multiselect(
                "Selecciona ID(s) a eliminar", ids_disponibles, key="ln_del_ids"
            )
            if st.button("🗑️ Eliminar seleccionadas", key="ln_del_btn",
                         disabled=not ids_eliminar, type="primary"):
                try:
                    for idr in ids_eliminar:
                        sb.table(TABLE_RUTAS).delete().eq("ID_Ruta", idr).execute()
                    load_rutas_lincoln.clear()
                    cargar_pool_ubicaciones_lincoln.clear()
                    alert("success", f"✅ {len(ids_eliminar)} ruta(s) eliminada(s).")
                    st.rerun()
                except Exception as e:
                    alert("error", f"Error al eliminar: {e}")

    # ══════════════════════════════════════════════════════════════
    # TAB EDITAR
    # ══════════════════════════════════════════════════════════════
    with tab_edit:
        section_header("✏️", "Editar Ruta")

        df_ed = filtrar_rutas_lincoln(df, "ln_ed")
        if df_ed.empty:
            alert("info", "No hay rutas con los filtros aplicados.")
            return

        if "ID_Ruta" not in df_ed.columns:
            return

        opciones = df_ed["ID_Ruta"].dropna().astype(str).tolist()
        idx_sel = st.selectbox(
            f"Selecciona ruta a editar ({len(opciones)} encontrada/s)",
            options=[""] + opciones,
            format_func=lambda i: "— Elige una ruta —" if i == "" else label_ruta_lincoln(
                df_ed[df_ed["ID_Ruta"] == i].iloc[0].to_dict()
            ),
            key="ln_ed_select",
        )
        if not idx_sel:
            alert("info", "Selecciona una ruta para editarla.")
            return

        ruta = df_ed[df_ed["ID_Ruta"] == idx_sel].iloc[0].to_dict()
        k    = str(idx_sel)

        # ── Auditoría e historial ──────────────────────────────
        if ruta.get("Capturado_Por"):
            st.caption(
                f"👤 Capturada por: **{ruta.get('Capturado_Por')}** "
                f"· Fecha: **{ruta.get('Fecha', '—')}**"
            )

        historial = ruta.get("historial") or []
        if isinstance(historial, str):
            import json
            try:
                historial = json.loads(historial)
            except Exception:
                historial = []

        if historial:
            with st.expander(f"📜 Historial de modificaciones ({len(historial)})", expanded=False):
                for entrada in reversed(historial):
                    ts  = str(entrada.get("timestamp", ""))[:16].replace("T", " ")
                    usr = entrada.get("usuario", "—")
                    mot = entrada.get("motivo", "—")
                    st.caption(f"**{ts}** · {usr} · _{mot}_")
                    prev = entrada.get("valores_anteriores", {})
                    if prev:
                        c1, c2 = st.columns(2)
                        c1.caption(f"Ingreso: **${safe(prev.get('Ingreso_Total')):,.2f}**")
                        c1.caption(f"Costo Directo: **${safe(prev.get('Costo_Directo_Total')):,.2f}**")
                        c2.caption(f"Ut. Bruta: **${safe(prev.get('Utilidad_Bruta')):,.2f}** ({safe(prev.get('Pct_Utilidad_Bruta')):.1f}%)")
                        c2.caption(f"Ut. Neta: **${safe(prev.get('Utilidad_Neta')):,.2f}** ({safe(prev.get('Pct_Utilidad_Neta')):.1f}%)")
                    st.divider()
        else:
            st.caption("📜 Sin modificaciones previas.")

        divider()

        # ── Motivo obligatorio ─────────────────────────────────
        motivo = st.text_input(
            "✏️ Motivo de modificación (obligatorio)",
            placeholder="Describe el motivo del cambio...",
            key=f"ln_ed_motivo_{k}",
        )

        divider()

        # ── Info General ───────────────────────────────────────
        st.markdown("### 📋 Información General")
        g1, g2, g3, g4 = st.columns(4)

        fecha_val = pd.to_datetime(ruta.get("Fecha"), errors="coerce")
        fecha_val = datetime.today() if pd.isna(fecha_val) else fecha_val
        fecha      = g1.date_input("📅 Fecha", value=fecha_val.date() if hasattr(fecha_val, "date") else datetime.today().date(), key=f"ln_ed_fecha_{k}")
        tipo_idx   = TIPOS_RUTA.index(ruta.get("Tipo", TIPOS_RUTA[0])) if ruta.get("Tipo") in TIPOS_RUTA else 0
        tipo       = g2.selectbox("🚛 Tipo de Ruta", TIPOS_RUTA, index=tipo_idx, key=f"ln_ed_tipo_{k}")
        cliente    = g3.text_input("🏢 Cliente", value=str(ruta.get("Cliente", "")), key=f"ln_ed_cli_{k}")
        modo_list  = ["Sencillo", "Team"]
        modo_idx   = modo_list.index(ruta.get("Modo_Viaje", "Sencillo")) if ruta.get("Modo_Viaje") in modo_list else 0
        modo_viaje = g4.selectbox("👥 Modo", modo_list, index=modo_idx, key=f"ln_ed_modo_{k}")

        config   = obtener_config_tipo_ruta(tipo)
        orden    = config.get("orden", ["americana"])
        es_empty = (tipo == "Empty")

        dir_label = "Subida" if tipo in {"NB", "D2DNB", "Empty"} else "Bajada"
        mx_label  = "Sí" if config["parte_mx"] else "No"
        st.caption(f"📌 Dirección: **{dir_label}** · Tramo MX: **{mx_label}**")

        # Valores por defecto
        origen_usa = destino_usa = ""
        miles_load = short_miles = miles_empty = 0.0
        modalidad    = "Desglosada"
        moneda_flete = "USD"
        cxm_flete = cxm_fuel = tarifa_flat = 0.0
        aplica_cruce = False
        tipo_cruce   = "Propio"
        tipo_carga   = "Cargado"
        moneda_cruce = "USD"
        ingreso_cruce = costo_cruce_terc = 0.0
        linea_mx   = "Propia"
        origen_mx  = destino_mx = ""
        moneda_mx  = "MXP"
        ingreso_mx = costo_mx = 0.0
        otros_cargos          = {}
        otros_cargos_cobrados = {}

        # ── Secciones en orden según tipo ─────────────────────
        for seccion in orden:
            divider()

            if seccion == "americana":
                st.markdown("### 🇺🇸 Ruta Americana")

                origen_actual  = str(ruta.get("Origen",  "") or "").strip()
                destino_actual = str(ruta.get("Destino", "") or "").strip()
                st.caption(f"📍 Valores actuales — Origen: **{origen_actual}** · Destino: **{destino_actual}**")

                ru1, ru2 = st.columns(2)
                with ru1:
                    origen_sel = st_searchbox(
                        buscar_ubicacion_lincoln,
                        label="📍 Origen USA",
                        placeholder=f"Actual: {origen_actual} — escribe para cambiar...",
                        key=f"ln_ed_ori_{k}",
                        clear_on_submit=False,
                    )
                with ru2:
                    destino_sel = st_searchbox(
                        buscar_ubicacion_lincoln,
                        label="📍 Destino USA",
                        placeholder=f"Actual: {destino_actual} — escribe para cambiar...",
                        key=f"ln_ed_dest_{k}",
                        clear_on_submit=False,
                    )
                origen_usa  = str(origen_sel  or "").strip() or origen_actual
                destino_usa = str(destino_sel or "").strip() or destino_actual

                m1, m2, m3 = st.columns(3)
                miles_load  = m1.number_input("🛣️ Miles Load",  value=float(safe(ruta.get("Miles_Load",  0))), min_value=0.0, step=10.0, key=f"ln_ed_ml_{k}", disabled=es_empty)
                short_miles = m2.number_input("🔀 Short Miles", value=float(safe(ruta.get("Short_Miles", 0))), min_value=0.0, step=1.0,  key=f"ln_ed_sm_{k}", disabled=es_empty)
                miles_empty = m3.number_input("⚪ Miles Empty", value=float(safe(ruta.get("Miles_Empty", 0))), min_value=0.0, step=10.0, key=f"ln_ed_me_{k}")

                divider()
                st.markdown("**💵 Tarifa Americana**")
                mod1, mod2 = st.columns([1, 3])
                mod_opts = ["Desglosada", "Flat"]
                mod_idx  = mod_opts.index(ruta.get("Modalidad", "Desglosada")) if ruta.get("Modalidad") in mod_opts else 0
                modalidad = mod1.radio("Modalidad", mod_opts, index=mod_idx, horizontal=False, key=f"ln_ed_modal_{k}", disabled=es_empty)

                if es_empty:
                    mod2.info("ℹ️ **Empty:** sin tarifa al cliente.")
                elif modalidad == "Desglosada":
                    td1, td2, td3 = mod2.columns(3)
                    mon_list  = ["USD", "MXP"]
                    mon_idx   = mon_list.index(ruta.get("Moneda_USA", "USD")) if ruta.get("Moneda_USA") in mon_list else 0
                    moneda_flete = td1.selectbox("💱 Moneda", mon_list, index=mon_idx, key=f"ln_ed_monfl_{k}")
                    cxm_flete    = td2.number_input("CXM Flete ($/mi)", value=float(safe(ruta.get("CXM_Flete", 0))), min_value=0.0, step=0.001, format="%.4f", key=f"ln_ed_cxmfl_{k}")
                    cxm_fuel     = td3.number_input("Fuel Surcharge ($/mi)", value=float(safe(ruta.get("CXM_Fuel", 0))), min_value=0.0, step=0.001, format="%.4f", key=f"ln_ed_fuel_{k}")
                else:
                    tf1, tf2 = mod2.columns(2)
                    mon_list  = ["USD", "MXP"]
                    mon_idx   = mon_list.index(ruta.get("Moneda_USA", "USD")) if ruta.get("Moneda_USA") in mon_list else 0
                    moneda_flete = tf1.selectbox("💱 Moneda", mon_list, index=mon_idx, key=f"ln_ed_monflat_{k}")
                    tarifa_flat  = tf2.number_input("Tarifa Total (Flat)", value=float(safe(ruta.get("Tarifa_Flat", 0))), min_value=0.0, step=50.0, key=f"ln_ed_flat_{k}")

            elif seccion == "cruce":
                if not es_empty and config.get("cruce") in ("opcional", True):
                    st.markdown("### 🛂 Cruce Fronterizo")
                    forzado      = (config.get("cruce") is True)
                    aplica_cruce = st.checkbox("¿Incluye cruce?", value=bool(ruta.get("Aplica_Cruce", forzado)), key=f"ln_ed_aplcruce_{k}")
                    if aplica_cruce:
                        cx1, cx2, cx3 = st.columns(3)
                        tc_list   = ["Propio", "Tercero"]
                        tc_idx    = tc_list.index(ruta.get("Tipo_Cruce", "Propio")) if ruta.get("Tipo_Cruce") in tc_list else 0
                        tca_list  = ["Cargado", "Vacío"]
                        tca_idx   = tca_list.index(ruta.get("Tipo_Carga_Cruce", "Cargado")) if ruta.get("Tipo_Carga_Cruce") in tca_list else 0
                        mc_list   = ["USD", "MXP"]
                        mc_idx    = mc_list.index(ruta.get("Moneda_Cruce", "USD")) if ruta.get("Moneda_Cruce") in mc_list else 0
                        tipo_cruce   = cx1.selectbox("Tipo de Cruce",   tc_list,  index=tc_idx,  key=f"ln_ed_tcruce_{k}")
                        tipo_carga   = cx2.selectbox("Carga del cruce", tca_list, index=tca_idx, key=f"ln_ed_tcarga_{k}")
                        moneda_cruce = cx3.selectbox("💱 Moneda",       mc_list,  index=mc_idx,  key=f"ln_ed_mcruce_{k}")
                        ing_col, costo_col = st.columns(2)
                        ingreso_cruce    = ing_col.number_input("Ingreso Cruce", value=float(safe(ruta.get("Ingreso_Cruce", 0))), min_value=0.0, step=5.0, key=f"ln_ed_icruce_{k}")
                        if tipo_cruce == "Tercero":
                            costo_cruce_terc = costo_col.number_input("Costo Cruce Tercero", value=float(safe(ruta.get("Costo_Cruce", 0))), min_value=0.0, step=5.0, key=f"ln_ed_ccruce_{k}")

            elif seccion == "mx":
                if config.get("parte_mx") and not es_empty:
                    st.markdown("### 🇲🇽 Parte Mexicana")

                    origen_mx_actual  = str(ruta.get("Origen_MX",  "") or "").strip()
                    destino_mx_actual = str(ruta.get("Destino_MX", "") or "").strip()
                    st.caption(f"📍 Valores actuales — Origen MX: **{origen_mx_actual}** · Destino MX: **{destino_mx_actual}**")

                    mx1, mx2 = st.columns(2)
                    lmx_list = ["Propia", "Tercero"]
                    lmx_idx  = lmx_list.index(ruta.get("Linea_MX", "Propia")) if ruta.get("Linea_MX") in lmx_list else 0
                    linea_mx = mx1.selectbox("Línea MX", lmx_list, index=lmx_idx, key=f"ln_ed_linmx_{k}")

                    with mx1:
                        origen_mx_sel = st_searchbox(
                            buscar_ubicacion_lincoln,
                            label="📍 Origen MX",
                            placeholder=f"Actual: {origen_mx_actual} — escribe para cambiar...",
                            key=f"ln_ed_orimx_{k}",
                            clear_on_submit=False,
                        )
                        destino_mx_sel = st_searchbox(
                            buscar_ubicacion_lincoln,
                            label="📍 Destino MX",
                            placeholder=f"Actual: {destino_mx_actual} — escribe para cambiar...",
                            key=f"ln_ed_destmx_{k}",
                            clear_on_submit=False,
                        )
                    origen_mx  = str(origen_mx_sel  or "").strip() or origen_mx_actual
                    destino_mx = str(destino_mx_sel or "").strip() or destino_mx_actual

                    monmx_list = ["MXP", "USD"]
                    monmx_idx  = monmx_list.index(ruta.get("Moneda_MX", "MXP")) if ruta.get("Moneda_MX") in monmx_list else 0
                    moneda_mx  = mx2.selectbox("💱 Moneda MX", monmx_list, index=monmx_idx, key=f"ln_ed_monmx_{k}")
                    ingreso_mx = mx2.number_input("Ingreso Flete MX", value=float(safe(ruta.get("Ingreso_MX_MXP", 0))), min_value=0.0, step=100.0, key=f"ln_ed_ingmx_{k}")
                    if linea_mx == "Tercero":
                        costo_mx = mx2.number_input("Costo Flete MX", value=float(safe(ruta.get("Costo_MX_MXP", 0))), min_value=0.0, step=100.0, key=f"ln_ed_costomx_{k}")

        # ── Extras siempre al final ────────────────────────────
        divider()
        st.markdown("### ➕ Extras / Otros Conceptos")
        st.caption("Monto capturado = Lincoln lo pagó (costo). Marca **'cobra'** si se cobró al cliente (ingreso).")

        cols3 = st.columns(3)
        for i, extra in enumerate(EXTRAS_USA):
            with cols3[i % 3]:
                val_prev = 0.0
                try:
                    import json as _json
                    oc = ruta.get("Otros_Cargos_JSON", "{}")
                    if isinstance(oc, str):
                        oc = _json.loads(oc.replace("'", '"'))
                    val_prev = float(safe(oc.get(extra, 0)))
                except Exception:
                    val_prev = 0.0
                monto   = st.number_input(extra, value=val_prev, min_value=0.0, step=10.0, format="%.2f", key=f"ln_ed_extra_{extra}_{k}")
                cobrado = st.checkbox("cobra", key=f"ln_ed_cobra_{extra}_{k}")
                if monto > 0:
                    otros_cargos[extra]          = monto
                    otros_cargos_cobrados[extra] = cobrado

        # ── Botón Revisar ──────────────────────────────────────
        divider()
        revisar = st.button(
            "🔍 Revisar Cambios", type="primary", use_container_width=True,
            key=f"ln_ed_revisar_{k}",
            disabled=not motivo.strip(),
        )

        if revisar:
            if not motivo.strip():
                alert("warn", "⚠️ El motivo de modificación es obligatorio.")
            else:
                tc = float(valores.get("Tipo de Cambio USD/MXP", 18.5))

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

                if config.get("parte_mx") and not es_empty:
                    ing_mx_mxp   = ingreso_mx * tc if moneda_mx == "USD" else ingreso_mx
                    costo_mx_mxp = costo_mx   * tc if moneda_mx == "USD" else costo_mx
                    if linea_mx != "Tercero":
                        costo_mx_mxp = 0.0
                else:
                    ing_mx_mxp   = 0.0
                    costo_mx_mxp = 0.0

                r_nuevo = calcular_ruta_lincoln(
                    tipo_ruta               = tipo,
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

                st.session_state["ln_ed_resultado"] = r_nuevo
                st.session_state["ln_ed_datos"] = {
                    "id_ruta":            idx_sel,
                    "motivo":             motivo.strip(),
                    "fecha":              str(fecha),
                    "tipo":               tipo,
                    "cliente":            normalizar(cliente),
                    "modo_viaje":         modo_viaje,
                    "origen_usa":         normalizar(origen_usa),
                    "destino_usa":        normalizar(destino_usa),
                    "miles_load":         miles_load,
                    "short_miles":        short_miles,
                    "miles_empty":        miles_empty,
                    "moneda_flete":       moneda_flete,
                    "modalidad":          modalidad,
                    "cxm_flete":          cxm_flete,
                    "cxm_fuel":           cxm_fuel,
                    "tarifa_flat":        tarifa_flat,
                    "aplica_cruce":       aplica_cruce,
                    "tipo_cruce":         tipo_cruce,
                    "tipo_carga":         tipo_carga,
                    "moneda_cruce":       moneda_cruce,
                    "ingreso_cruce":      ing_cruce_usd,
                    "costo_cruce_terc":   costo_cruce_terc,
                    "linea_mx":           linea_mx,
                    "origen_mx":          normalizar(origen_mx),
                    "destino_mx":         normalizar(destino_mx),
                    "moneda_mx":          moneda_mx,
                    "ingreso_mx":         ingreso_mx,
                    "ing_mx_mxp":         ing_mx_mxp,
                    "costo_mx":           costo_mx,
                    "costo_mx_mxp":       costo_mx_mxp,
                    "otros_cargos":          otros_cargos,
                    "otros_cargos_cobrados": otros_cargos_cobrados,
                }
                st.session_state["ln_revisar_edicion"] = True

        # ── Preview + Guardar ──────────────────────────────────
        r_prev = st.session_state.get("ln_ed_resultado")
        d_prev = st.session_state.get("ln_ed_datos", {})

        if r_prev and d_prev.get("id_ruta") == idx_sel and st.session_state.get("ln_revisar_edicion"):
            divider()
            section_header("📊", "Vista Previa de Cambios")
            _preview_edicion(r_prev, d_prev)

            divider()
            col_g, col_x = st.columns([2, 1])
            with col_g:
                if st.button("💾 Guardar Cambios", type="primary",
                             use_container_width=True, key="ln_ed_guardar"):
                    # Construir historial
                    historial_ant = ruta.get("historial") or []
                    if not isinstance(historial_ant, list):
                        historial_ant = []

                    nueva_entrada = {
                        "timestamp": now_iso(),
                        "usuario":   nombre_usuario,
                        "motivo":    d_prev["motivo"],
                        "valores_anteriores": {
                            # Identificación
                            "Fecha":               ruta.get("Fecha"),
                            "Tipo":                ruta.get("Tipo"),
                            "Cliente":             ruta.get("Cliente"),
                            "Modo_Viaje":          ruta.get("Modo_Viaje"),
                            # Ruta USA
                            "Origen":              ruta.get("Origen"),
                            "Destino":             ruta.get("Destino"),
                            "Miles_Load":          ruta.get("Miles_Load"),
                            "Short_Miles":         ruta.get("Short_Miles"),
                            "Miles_Empty":         ruta.get("Miles_Empty"),
                            "Moneda_USA":          ruta.get("Moneda_USA"),
                            "Modalidad":           ruta.get("Modalidad"),
                            "CXM_Flete":           ruta.get("CXM_Flete"),
                            "CXM_Fuel":            ruta.get("CXM_Fuel"),
                            "Tarifa_Flat":         ruta.get("Tarifa_Flat"),
                            "Ingreso_Flete_USA":   ruta.get("Ingreso_Flete_USA"),
                            "Ingreso_Fuel_USA":    ruta.get("Ingreso_Fuel_USA"),
                            # Cruce
                            "Aplica_Cruce":        ruta.get("Aplica_Cruce"),
                            "Tipo_Cruce":          ruta.get("Tipo_Cruce"),
                            "Tipo_Carga_Cruce":    ruta.get("Tipo_Carga_Cruce"),
                            "Moneda_Cruce":        ruta.get("Moneda_Cruce"),
                            "Ingreso_Cruce":       ruta.get("Ingreso_Cruce"),
                            "Costo_Cruce":         ruta.get("Costo_Cruce"),
                            # Tramo MX
                            "Linea_MX":            ruta.get("Linea_MX"),
                            "Origen_MX":           ruta.get("Origen_MX"),
                            "Destino_MX":          ruta.get("Destino_MX"),
                            "Moneda_MX":           ruta.get("Moneda_MX"),
                            "Ingreso_MX_MXP":      ruta.get("Ingreso_MX_MXP"),
                            "Costo_MX_MXP":        ruta.get("Costo_MX_MXP"),
                            "Ingreso_MX_USD":      ruta.get("Ingreso_MX_USD"),
                            "Costo_MX_USD":        ruta.get("Costo_MX_USD"),
                            # Extras
                            "Otros_Cargos_JSON":   ruta.get("Otros_Cargos_JSON"),
                            "Otros_Cargos_Ingreso": ruta.get("Otros_Cargos_Ingreso"),
                            "Otros_Cargos_Costo":  ruta.get("Otros_Cargos_Costo"),
                            # Parámetros del cálculo
                            "Tipo_Cambio":         ruta.get("Tipo_Cambio"),
                            "MPG":                 ruta.get("MPG"),
                            "Precio_Diesel_USD":   ruta.get("Precio_Diesel_USD"),
                            "CXM_Operador":        ruta.get("CXM_Operador"),
                            "CXM_Vacio":           ruta.get("CXM_Vacio"),
                            "Bono_Por_Milla":      ruta.get("Bono_Por_Milla"),
                            # Costos desglosados
                            "Sueldo_Base":         ruta.get("Sueldo_Base"),
                            "Bono_Millas":         ruta.get("Bono_Millas"),
                            "Sueldo_Operador":     ruta.get("Sueldo_Operador"),
                            "Diesel_USA":          ruta.get("Diesel_USA"),
                            "ISR_IMSS":            ruta.get("ISR_IMSS"),
                            "Costo_Directo":       ruta.get("Costo_Directo"),
                            "Costo_Directo_Total": ruta.get("Costo_Directo_Total"),
                            # Resultados
                            "Ingreso_Total":       ruta.get("Ingreso_Total"),
                            "Utilidad_Bruta":      ruta.get("Utilidad_Bruta"),
                            "Pct_Utilidad_Bruta":  ruta.get("Pct_Utilidad_Bruta"),
                            "Costos_Indirectos":   ruta.get("Costos_Indirectos"),
                            "Utilidad_Neta":       ruta.get("Utilidad_Neta"),
                            "Pct_Utilidad_Neta":   ruta.get("Pct_Utilidad_Neta"),
                        },
                    }
                    historial_ant.append(nueva_entrada)

                    payload = {
                        "Fecha":              d_prev["fecha"],
                        "Tipo":               d_prev["tipo"],
                        "Cliente":            d_prev["cliente"],
                        "Modo_Viaje":         d_prev["modo_viaje"],
                        "Origen":             d_prev["origen_usa"],
                        "Destino":            d_prev["destino_usa"],
                        "Miles_Load":         d_prev["miles_load"],
                        "Short_Miles":        d_prev["short_miles"],
                        "Miles_Empty":        d_prev["miles_empty"],
                        "Moneda_USA":         d_prev["moneda_flete"],
                        "Modalidad":          d_prev["modalidad"],
                        "CXM_Flete":          d_prev["cxm_flete"],
                        "CXM_Fuel":           d_prev["cxm_fuel"],
                        "Tarifa_Flat":        d_prev["tarifa_flat"],
                        "Aplica_Cruce":       d_prev["aplica_cruce"],
                        "Tipo_Cruce":         d_prev["tipo_cruce"],
                        "Tipo_Carga_Cruce":   d_prev["tipo_carga"],
                        "Moneda_Cruce":       d_prev["moneda_cruce"],
                        "Ingreso_Cruce":      r_prev["ingreso_cruce"],
                        "Costo_Cruce":        r_prev["costo_cruce"],
                        "Linea_MX":           d_prev["linea_mx"],
                        "Origen_MX":          d_prev["origen_mx"],
                        "Destino_MX":         d_prev["destino_mx"],
                        "Moneda_MX":          d_prev["moneda_mx"],
                        "Ingreso_MX_MXP":     d_prev["ing_mx_mxp"],
                        "Costo_MX_MXP":       d_prev["costo_mx_mxp"],
                        "Ingreso_MX_USD":     r_prev["ingreso_mx_usd"],
                        "Costo_MX_USD":       r_prev["costo_mx_usd"],
                        "Otros_Cargos_JSON":  str(d_prev.get("otros_cargos", {})),
                        "Otros_Cargos_Ingreso": r_prev["otros_cargos_ingreso"],
                        "Otros_Cargos_Costo":   r_prev["otros_cargos_costo"],
                        "Ingreso_Flete_USA":  r_prev["ingreso_flete_usa"],
                        "Ingreso_Fuel_USA":   r_prev["ingreso_fuel_usa"],
                        "Sueldo_Base":        r_prev["sueldo_base"],
                        "Bono_Millas":        r_prev["bono_millas"],
                        "Sueldo_Operador":    r_prev["sueldo_usa"],
                        "Diesel_USA":         r_prev["diesel_usa"],
                        "ISR_IMSS":           r_prev["isr_imss"],
                        "Costo_Directo":      r_prev["costo_directo"],
                        "Costo_Directo_Total": r_prev["costo_directo_total"],
                        "Ingreso_Total":      r_prev["ingreso_total"],
                        "Utilidad_Bruta":     r_prev["utilidad_bruta"],
                        "Pct_Utilidad_Bruta": r_prev["pct_bruta"],
                        "Costos_Indirectos":  r_prev["costos_ind"],
                        "Utilidad_Neta":      r_prev["utilidad_neta"],
                        "Pct_Utilidad_Neta":  r_prev["pct_neta"],
                        "Tipo_Cambio":        r_prev["tc"],
                        "updated_by":         nombre_usuario,
                        "updated_at":         now_iso(),
                        "historial":          historial_ant,
                    }

                    try:
                        sb.table(TABLE_RUTAS).update(
                            limpiar_fila_json(payload)
                        ).eq("ID_Ruta", idx_sel).execute()
                        load_rutas_lincoln.clear()
                        cargar_pool_ubicaciones_lincoln.clear()
                        st.session_state["ln_gest_editado_id"]   = idx_sel
                        st.session_state["ln_gest_mostrar_modal"] = True
                        st.session_state["ln_revisar_edicion"]    = False
                        st.rerun()
                    except Exception as e:
                        alert("error", f"Error al guardar: {e}")

            with col_x:
                if st.button("🗑️ Descartar cambios", use_container_width=True, key="ln_ed_descartar"):
                    st.session_state.pop("ln_ed_resultado", None)
                    st.session_state.pop("ln_ed_datos", None)
                    st.session_state["ln_revisar_edicion"] = False
                    st.rerun()
