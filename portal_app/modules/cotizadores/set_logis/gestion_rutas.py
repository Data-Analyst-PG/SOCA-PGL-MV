"""
gestion_rutas.py – Set Logis Plus
Homologado con Lincoln:
  - Sin st.form en edición — usa st.button + st_searchbox para Origen/Destino
  - Funciones de cache, label y filtros vienen de _shared.py
  - mostrar_resultados_setlogis() de _shared — 1 línea reemplaza bloque manual
  - Modal @st.dialog para confirmar guardado de edición
  - Historial de modificaciones (ya existía, mejorado)
  - Tabs: Ver Rutas | Eliminar | Editar
  - Prefijos sl_ed_*, sl_ver_*, sl_del_* en keys

Diferencias Set Logis que se preservan:
  - Fuel_Owner checkbox en edición
  - Modo: "Individual" / "Team"
  - 3 tipos de millas: Miles Load, Short Miles, Miles Empty
  - Modalidad Flat / Desglosada con CXM_Flete / CXM_Fuel
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
from ._shared import (
    TABLE_RUTAS,
    TIPOS_RUTA,
    EXTRAS_USA,
    DEFAULTS,
    cargar_datos_generales,
    limpiar_fila_json,
    safe,
    calcular_ruta_setlogis,
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
        st.session_state.pop("sl_ed_ruta_id",    None)
        st.session_state.pop("sl_ed_modal",      None)
        st.session_state.pop("sl_edit_resultado", None)
        st.session_state.pop("sl_edit_datos",     None)
        st.session_state.pop("sl_edit_id_rev",    None)
        st.rerun()


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

    # ── Tabs ──────────────────────────────────────────────────────
    tab_ver, tab_del, tab_edit = st.tabs(["📋 Ver Rutas", "🗑️ Eliminar", "✏️ Editar"])

    # ══════════════════════════════════════════════════════════════
    # TAB VER
    # ══════════════════════════════════════════════════════════════
    with tab_ver:
        section_header("📋", "Rutas Registradas")

        df_tabla = filtrar_rutas_setlogis(df, "sl_ver")

        COLS = [
            "ID_Ruta", "Fecha", "Tipo_Viaje", "Modo", "Cliente", "Ruta_USA",
            "Miles_Load", "Short_Miles", "Miles_Empty",
            "Ingreso_Global", "Costo_Directo", "Utilidad_Bruta",
            "Pct_Ut_Bruta", "Costo_Indirecto", "Utilidad_Neta",
            "Pct_Ut_Neta", "Fuel_Owner", "Usuario",
        ]
        cols_disp = [c for c in COLS if c in df_tabla.columns]
        st.dataframe(
            df_tabla[cols_disp] if cols_disp else df_tabla,
            use_container_width=True,
            hide_index=True,
        )
        st.caption(f"Mostrando **{len(df_tabla)}** de **{len(df)}** rutas")

        divider()
        st.download_button(
            "📥 Descargar Excel",
            data=_to_excel_bytes(df_tabla[cols_disp] if cols_disp else df_tabla),
            file_name=f"rutas_setlogis_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="sl_dl_excel",
        )

    # ══════════════════════════════════════════════════════════════
    # TAB ELIMINAR
    # ══════════════════════════════════════════════════════════════
    with tab_del:
        section_header("🗑️", "Eliminar Rutas")

        df_del = filtrar_rutas_setlogis(df, "sl_del")
        if df_del.empty:
            alert("info", "No hay rutas con los filtros aplicados.")
        else:
            ids_disponibles = df_del["ID_Ruta"].dropna().astype(str).tolist()
            ids_eliminar = st.multiselect(
                "Selecciona ID(s) a eliminar", ids_disponibles, key="sl_del_ids"
            )
            if st.button("🗑️ Eliminar seleccionadas", key="sl_del_btn",
                         disabled=not ids_eliminar, type="primary"):
                try:
                    for idr in ids_eliminar:
                        supabase.table(TABLE_RUTAS).delete().eq("ID_Ruta", idr).execute()
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
        idx_sel = st.selectbox(
            f"Selecciona ruta a editar ({len(opciones)} encontrada/s)",
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

        # ── FORMULARIO DE EDICIÓN — SIN st.form ───────────────────────────────
        tipo_ruta_val = str(ruta.get("Tipo_Viaje", TIPOS_RUTA[0]))
        es_empty      = (tipo_ruta_val == "Empty")
        aplica_mx     = tiene_mx(tipo_ruta_val)
        modalidad_val = str(ruta.get("Modalidad", "Flat"))

        # Motivo (obligatorio)
        st.markdown("### ⚙️ Motivo de modificación")
        motivo = st.text_input(
            "Motivo (obligatorio)",
            placeholder="Ej: Corrección de millas",
            key=f"sl_ed_motivo_{k}",
        )

        divider()

        # ── Info General ───────────────────────────────────────────────────────
        st.markdown("### 📋 Información General")
        eg1, eg2, eg3 = st.columns(3)

        try:
            from datetime import date as _date
            fecha_dt = _date.fromisoformat(str(ruta.get("Fecha", ""))[:10])
        except Exception:
            fecha_dt = datetime.today().date()

        fecha     = eg1.date_input("Fecha", value=fecha_dt, key=f"sl_ed_fecha_{k}")
        tipo_ruta = eg2.selectbox(
            "Tipo de Ruta", TIPOS_RUTA,
            index=TIPOS_RUTA.index(tipo_ruta_val) if tipo_ruta_val in TIPOS_RUTA else 0,
            key=f"sl_ed_tipo_{k}", disabled=True,
        )
        modo = eg3.selectbox(
            "Modo", ["Individual", "Team"],
            index=0 if ruta.get("Modo", "Individual") == "Individual" else 1,
            key=f"sl_ed_modo_{k}",
        )

        # Separar origen / destino de Ruta_USA
        ruta_usa_val = str(ruta.get("Ruta_USA", ""))
        if " - " in ruta_usa_val:
            origen_actual, destino_actual = ruta_usa_val.split(" - ", 1)
        else:
            origen_actual, destino_actual = ruta_usa_val, ""

        cliente_actual = str(ruta.get("Cliente", ""))

        eg4, eg5, eg6 = st.columns(3)
        cliente = eg4.text_input("Cliente", value=cliente_actual, key=f"sl_ed_cliente_{k}")

        with eg5:
            origen_sel = st_searchbox(
                buscar_ubicacion_setlogis,
                label="Origen USA",
                placeholder="Buscar o nueva ubicación...",
                key=f"sl_ed_ori_{k}",
                clear_on_submit=False,
            )
            st.caption(f"Actual: **{origen_actual}**")

        with eg6:
            destino_sel = st_searchbox(
                buscar_ubicacion_setlogis,
                label="Destino USA",
                placeholder="Buscar o nueva ubicación...",
                key=f"sl_ed_dest_{k}",
                clear_on_submit=False,
            )
            st.caption(f"Actual: **{destino_actual}**")

        # Preservar valor actual si el usuario no interactúa con searchbox
        origen_usa  = str(origen_sel  or "").strip() or origen_actual
        destino_usa = str(destino_sel or "").strip() or destino_actual

        divider()

        # ── Ruta Americana ─────────────────────────────────────────────────────
        st.markdown("### 🇺🇸 Ruta Americana")
        m1, m2, m3 = st.columns(3)
        miles_load  = m1.number_input("Miles Load",  value=safe(ruta.get("Miles_Load")),
                                       min_value=0.0, step=1.0, format="%.1f", key=f"sl_ed_ml_{k}")
        short_miles = m2.number_input("Short Miles", value=safe(ruta.get("Short_Miles")),
                                       min_value=0.0, step=1.0, format="%.1f", key=f"sl_ed_sm_{k}")
        miles_empty = m3.number_input("Miles Empty", value=safe(ruta.get("Miles_Empty")),
                                       min_value=0.0, step=1.0, format="%.1f", key=f"sl_ed_me_{k}")

        if not es_empty:
            r1, r2 = st.columns([1, 3])
            mod_idx = 0 if modalidad_val == "Desglosada" else 1
            modalidad    = r1.selectbox("Modalidad", ["Desglosada", "Flat"],
                                         index=mod_idx, key=f"sl_ed_mod_{k}")
            moneda_flete = r2.selectbox("Moneda Flete", ["USD", "MXP"],
                                         index=0 if ruta.get("Moneda_Flete","USD") == "USD" else 1,
                                         key=f"sl_ed_mon_flete_{k}")

            if modalidad == "Desglosada":
                d1, d2 = st.columns(2)
                cxm_flete_cap = d1.number_input(
                    "CXM Flete (USD/mi)",
                    value=safe(ruta.get("CXM_Flete")),
                    min_value=0.0, step=0.001, format="%.4f", key=f"sl_ed_cxmf_{k}",
                )
                cxm_fuel_cap  = d2.number_input(
                    "CXM Fuel  (USD/mi)",
                    value=safe(ruta.get("CXM_Fuel")),
                    min_value=0.0, step=0.001, format="%.4f", key=f"sl_ed_cxmu_{k}",
                )
                flete_flat_cap = 0.0
            else:
                flete_flat_cap = st.number_input(
                    "Flete Flat (monto total)",
                    value=safe(ruta.get("Flete_Flat")),
                    min_value=0.0, step=1.0, format="%.2f", key=f"sl_ed_flat_{k}",
                )
                cxm_flete_cap = 0.0
                cxm_fuel_cap  = 0.0

            fuel_owner_ed = st.checkbox(
                "⛽ Fuel Owner — el fuel se paga al owner",
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

        divider()

        # ── Cruce ──────────────────────────────────────────────────────────────
        if not es_empty:
            st.markdown("### 🛂 Cruce")
            incluye_cruce = st.checkbox(
                "¿Incluye cruce?",
                value=bool(ruta.get("Incluye_Cruce", False)),
                key=f"sl_ed_inc_cr_{k}",
            )
            tipo_cruce    = str(ruta.get("Tipo_Cruce",       "Propio"))
            tipo_carga_c  = str(ruta.get("Tipo_Carga_Cruce", "Cargado"))
            mon_ing_cruce   = str(ruta.get("Moneda_Ingreso_Cruce", "USD"))
            ingreso_cruce_raw = safe(ruta.get("Ingreso_Cruce"))
            mon_costo_cruce   = str(ruta.get("Moneda_Costo_Cruce", "USD"))
            costo_cruce_raw   = safe(ruta.get("Costo_Cruce"))

            if incluye_cruce:
                cr1, cr2 = st.columns(2)
                tipo_cruce   = cr1.selectbox("Tipo Cruce", ["Propio", "Tercero"],
                                              index=0 if tipo_cruce == "Propio" else 1,
                                              key=f"sl_ed_tipo_cr_{k}")
                tipo_carga_c = cr2.selectbox("Tipo Carga", ["Cargado", "Vacío"],
                                              index=0 if tipo_carga_c == "Cargado" else 1,
                                              key=f"sl_ed_tipo_cg_{k}")
                ic1, ic2, ic3, ic4 = st.columns(4)
                mon_ing_cruce     = ic1.selectbox("Mon. Ingreso", ["USD", "MXP"],
                                                   index=0 if mon_ing_cruce == "USD" else 1,
                                                   key=f"sl_ed_mon_ic_{k}")
                ingreso_cruce_raw = ic2.number_input("Ingreso Cruce", value=ingreso_cruce_raw,
                                                      min_value=0.0, step=0.01, format="%.2f",
                                                      key=f"sl_ed_ing_cr_{k}")
                if tipo_cruce == "Tercero":
                    mon_costo_cruce = ic3.selectbox("Mon. Costo", ["USD", "MXP"],
                                                     index=0 if mon_costo_cruce == "USD" else 1,
                                                     key=f"sl_ed_mon_cc_{k}")
                    costo_cruce_raw = ic4.number_input("Costo Cruce", value=costo_cruce_raw,
                                                        min_value=0.0, step=0.01, format="%.2f",
                                                        key=f"sl_ed_costo_cr_{k}")
        else:
            incluye_cruce     = False
            tipo_cruce        = "Propio"
            tipo_carga_c      = "Cargado"
            mon_ing_cruce     = "USD"
            ingreso_cruce_raw = 0.0
            mon_costo_cruce   = "USD"
            costo_cruce_raw   = 0.0

        divider()

        # ── Parte MX ───────────────────────────────────────────────────────────
        if aplica_mx:
            st.markdown("### 🇲🇽 Parte MX")
            mx1, mx2 = st.columns(2)
            origen_mx  = mx1.text_input("Origen MX",  value=str(ruta.get("Origen_MX",  "")),
                                         key=f"sl_ed_ori_mx_{k}")
            destino_mx = mx2.text_input("Destino MX", value=str(ruta.get("Destino_MX", "")),
                                         key=f"sl_ed_dest_mx_{k}")
            m1, m2, m3, m4 = st.columns(4)
            mon_ing_mx   = m1.selectbox("Mon. Ingreso MX", ["MXP", "USD"],
                                         index=0 if ruta.get("Moneda_Ingreso_MX","MXP") == "MXP" else 1,
                                         key=f"sl_ed_mon_im_{k}")
            ingreso_mx_raw = m2.number_input("Ingreso MX", value=safe(ruta.get("Ingreso_MX")),
                                              min_value=0.0, step=0.01, format="%.2f",
                                              key=f"sl_ed_ing_mx_{k}")
            mon_costo_mx = m3.selectbox("Mon. Costo MX", ["MXP", "USD"],
                                         index=0 if ruta.get("Moneda_Costo_MX","MXP") == "MXP" else 1,
                                         key=f"sl_ed_mon_cm_{k}")
            costo_mx_raw = m4.number_input("Costo MX", value=safe(ruta.get("Costo_MX")),
                                            min_value=0.0, step=0.01, format="%.2f",
                                            key=f"sl_ed_costo_mx_{k}")
            divider()
        else:
            origen_mx = destino_mx = ""
            mon_ing_mx = "MXP"; ingreso_mx_raw = 0.0
            mon_costo_mx = "MXP"; costo_mx_raw  = 0.0

        # ── Extras ─────────────────────────────────────────────────────────────
        st.markdown("### ➕ Extras / Otros Cargos")
        otros_cargos  = {}
        otros_pagados = {}
        cols_ext = st.columns(3)
        for i, nombre in enumerate(EXTRAS_USA):
            col = cols_ext[i % 3]
            key_e = nombre.replace(" ", "_")
            val_guardado   = safe(ruta.get(f"Extra_{key_e}", 0.0))
            cob_guardado   = bool(ruta.get(f"Extra_{key_e}_Cobrado", False))
            monto   = col.number_input(nombre, value=val_guardado,
                                        min_value=0.0, step=0.01, format="%.2f",
                                        key=f"sl_ed_ex_{key_e}_{k}")
            cobrado = col.checkbox(f"Cobrado ({nombre})", value=cob_guardado,
                                   key=f"sl_ed_cob_{key_e}_{k}")
            if monto > 0:
                otros_cargos[nombre]  = monto
                otros_pagados[nombre] = cobrado

        divider()

        # ── Costo Indirecto ────────────────────────────────────────────────────
        st.markdown("### 📊 Costo Indirecto")
        modo_ci = st.radio(
            "Método de cálculo",
            ["CXM", "%"], horizontal=True, key=f"sl_ed_ci_{k}",
        )

        divider()

        # ── Botón Revisar Cambios ──────────────────────────────────────────────
        if st.button("🔍 Revisar Cambios", type="primary",
                     use_container_width=True, key=f"sl_ed_revisar_{k}"):
            if not motivo.strip():
                alert("warn", "⚠️ El motivo de modificación es obligatorio.")
                st.stop()

            # Convertir monedas
            if es_empty:
                flete_usd = fuel_usd = 0.0
            elif modalidad == "Desglosada":
                flete_usd = a_usd(safe(cxm_flete_cap) * safe(miles_load), moneda_flete, tc)
                fuel_usd  = a_usd(safe(cxm_fuel_cap)  * safe(miles_load), moneda_flete, tc)
            else:
                flete_usd = a_usd(safe(flete_flat_cap), moneda_flete, tc)
                fuel_usd  = 0.0

            ingreso_cruce_u = a_usd(ingreso_cruce_raw, mon_ing_cruce,   tc)
            costo_cruce_u   = a_usd(costo_cruce_raw,   mon_costo_cruce, tc)
            ingreso_mx_u    = a_usd(ingreso_mx_raw,    mon_ing_mx,      tc)
            costo_mx_u      = a_usd(costo_mx_raw,      mon_costo_mx,    tc)

            extras_ingreso    = sum(v for n, v in otros_cargos.items() if otros_pagados.get(n, False))
            extras_costo_puro = sum(v for n, v in otros_cargos.items() if not otros_pagados.get(n, False))

            ruta_usa = f"{normalizar(origen_usa)} - {normalizar(destino_usa)}"

            r_prev = calcular_ruta_setlogis(
                tipo_ruta            = tipo_ruta,
                modo                 = modo,
                ruta_usa             = ruta_usa,
                cliente              = normalizar(cliente),
                miles_load           = miles_load,
                miles_empty          = miles_empty,
                short_miles          = short_miles,
                flete_usa            = flete_usd,
                fuel                 = fuel_usd,
                tipo_cruce           = tipo_cruce,
                tipo_carga_cruce     = tipo_carga_c,
                ingreso_cruce        = ingreso_cruce_u,
                costo_cruce_externo  = costo_cruce_u,
                ingreso_mx           = ingreso_mx_u,
                costo_mx             = costo_mx_u,
                extras_ingreso       = extras_ingreso,
                extras_costo         = extras_costo_puro,
                modo_costo_indirecto = modo_ci,
                valores              = valores,
                fuel_owner           = fuel_owner_ed,
                incluye_cruce        = incluye_cruce and not es_empty,
            )

            st.session_state["sl_edit_resultado"]  = r_prev
            st.session_state["sl_edit_id_rev"]     = idx_sel
            st.session_state["sl_edit_datos"] = {
                "motivo":          motivo,
                "modalidad":       modalidad,
                "cxm_flete_cap":   safe(cxm_flete_cap) if modalidad == "Desglosada" else 0.0,
                "cxm_fuel_cap":    safe(cxm_fuel_cap)  if modalidad == "Desglosada" else 0.0,
                "flete_flat_cap":  flete_flat_cap if modalidad == "Flat" else 0.0,
                "mon_flete":       moneda_flete if not es_empty else "USD",
                "mon_ing_cruce":   mon_ing_cruce,
                "mon_costo_cruce": mon_costo_cruce,
                "mon_ing_mx":      mon_ing_mx,
                "mon_costo_mx":    mon_costo_mx,
                "origen_mx":       normalizar(origen_mx)  if aplica_mx else "",
                "destino_mx":      normalizar(destino_mx) if aplica_mx else "",
                "tipo_carga_cruce": tipo_carga_c if incluye_cruce and not es_empty else "",
                "incluye_cruce":   incluye_cruce and not es_empty,
                "otros_cargos":    otros_cargos,
                "otros_pagados":   otros_pagados,
                "fuel_owner":      fuel_owner_ed,
            }

        # ── Vista Previa ───────────────────────────────────────────────────────
        r_prev = st.session_state.get("sl_edit_resultado")
        d_prev = st.session_state.get("sl_edit_datos", {})
        id_rev = st.session_state.get("sl_edit_id_rev")

        if r_prev and d_prev and id_rev == idx_sel:
            divider()
            mostrar_resultados_setlogis(
                r_prev,
                modalidad  = d_prev.get("modalidad", "Flat"),
                miles_load = safe(r_prev.get("Miles_Load", 0.0)),
                cxm_flete  = d_prev.get("cxm_flete_cap", 0.0),
                cxm_fuel   = d_prev.get("cxm_fuel_cap",  0.0),
            )

            divider()
            if st.button("💾 Guardar Cambios en Base de Datos", key=f"sl_guardar_ed_{k}",
                         type="primary", use_container_width=True):
                _guardar_edicion(
                    supabase      = supabase,
                    idx_sel       = idx_sel,
                    ruta          = ruta,
                    r_prev        = r_prev,
                    d_prev        = d_prev,
                    nombre_usuario= nombre_usuario,
                    historial_ant = historial,
                )


# ─────────────────────────────────────────────
# GUARDAR EDICIÓN EN SUPABASE
# ─────────────────────────────────────────────
def _guardar_edicion(
    supabase,
    idx_sel:        str,
    ruta:           dict,
    r_prev:         dict,
    d_prev:         dict,
    nombre_usuario: str,
    historial_ant:  list,
) -> None:
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
                "Tipo_Viaje":          ruta.get("Tipo_Viaje"),
                "Modo":                ruta.get("Modo"),
                "Fecha":               ruta.get("Fecha"),
                "TC_USD_MXP":          ruta.get("TC_USD_MXP"),
            },
        }
        historial_nuevo = list(historial_ant) + [entrada_historial]

        extras_db         = {
            f"Extra_{n.replace(' ','_')}": v
            for n, v in d_prev.get("otros_cargos", {}).items()
        }
        extras_cobrado_db = {
            f"Extra_{n.replace(' ','_')}_Cobrado": v
            for n, v in d_prev.get("otros_pagados", {}).items()
        }

        fila = {
            "Tipo_Viaje":           r_prev["Tipo_Viaje"],
            "Modo":                 r_prev["Modo"],
            "Direccion":            r_prev["Direccion"],
            "Modalidad":            d_prev["modalidad"],
            "Cliente":              r_prev["Cliente"],
            "Ruta_USA":             r_prev["Ruta_USA"],
            "Origen_MX":            d_prev["origen_mx"],
            "Destino_MX":           d_prev["destino_mx"],
            "Moneda_Flete":         d_prev["mon_flete"],
            "Moneda_Ingreso_Cruce": d_prev["mon_ing_cruce"],
            "Moneda_Costo_Cruce":   d_prev["mon_costo_cruce"],
            "Moneda_Ingreso_MX":    d_prev["mon_ing_mx"],
            "Moneda_Costo_MX":      d_prev["mon_costo_mx"],
            "Tipo_Carga_Cruce":     d_prev["tipo_carga_cruce"],
            "Incluye_Cruce":        d_prev["incluye_cruce"],
            "Miles_Load":           r_prev["Miles_Load"],
            "Miles_Empty":          r_prev["Miles_Empty"],
            "Short_Miles":          r_prev["Short_Miles"],
            "Millas_Totales":       r_prev["Millas_Totales"],
            "CXM_Flete":            d_prev["cxm_flete_cap"],
            "CXM_Fuel":             d_prev["cxm_fuel_cap"],
            "Flete_Flat":           r_prev.get("Flete_Flat", d_prev["flete_flat_cap"]),
            "Flete_USA":            r_prev["Flete_USA"],
            "Fuel":                 r_prev["Fuel"],
            "Flete_Fuel":           r_prev["Flete_Fuel"],
            "Ingreso_Cruce":        r_prev["Ingreso_Cruce"],
            "Tipo_Cruce":           r_prev["Tipo_Cruce"],
            "Ingreso_MX":           r_prev["Ingreso_MX"],
            "Extras_Ingreso":       r_prev["Extras_Ingreso"],
            "Extras_Costo":         r_prev["Extras_Costo"],
            "Ingreso_Global":       r_prev["Ingreso_Global"],
            "PxM_Cargado":          r_prev["PxM_Cargado"],
            "PxM_Vacio":            r_prev["PxM_Vacio"],
            "Pago_Owner_Cargado":   r_prev["Pago_Owner_Cargado"],
            "Pago_Owner_Vacio":     r_prev["Pago_Owner_Vacio"],
            "Pago_Owner_Total":     r_prev["Pago_Owner_Total"],
            "Fuel_Owner":           r_prev.get("Fuel_Owner", False),
            "Pago_Fuel_Owner":      r_prev.get("Pago_Fuel_Owner", 0.0),
            "Costo_Cruce":          r_prev["Costo_Cruce"],
            "Costo_MX":             r_prev["Costo_MX"],
            "Costo_Directo":        r_prev["Costo_Directo"],
            "Costo_Indirecto":      r_prev["Costo_Indirecto"],
            "Costo_Total":          r_prev["Costo_Total"],
            "Utilidad_Bruta":       r_prev["Utilidad_Bruta"],
            "Utilidad_Neta":        r_prev["Utilidad_Neta"],
            "Pct_Costo_Directo":    r_prev["Pct_Costo_Directo"],
            "Pct_Costo_Indirecto":  r_prev["Pct_Costo_Indirecto"],
            "Pct_Ut_Bruta":         r_prev["Pct_Ut_Bruta"],
            "Pct_Ut_Neta":          r_prev["Pct_Ut_Neta"],
            "TC_USD_MXP":           r_prev["TC"],
            "updated_by":           nombre_usuario,
            "updated_at":           now_iso(),
            "historial":            historial_nuevo,
            **extras_db,
            **extras_cobrado_db,
        }

        fila_limpia = limpiar_fila_json(fila)
        supabase.table(TABLE_RUTAS).update(fila_limpia).eq("ID_Ruta", idx_sel).execute()

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
