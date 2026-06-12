"""
gestion_rutas.py – Set Logis Plus
Gestión de rutas guardadas: tabla general, eliminar, editar con recalculo.
FIX: keys del form incluyen el ID de ruta para evitar DuplicateElementKey
     cuando Streamlit renderiza todos los tabs simultáneamente.
FLUJO EDITAR: form → Revisar Cambios → muestra resultado → Guardar (fuera del form)
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from services.supabase_client import get_supabase_client, current_user
from ui.components import (
    section_header, alert, divider, kpi_row,
    semaforos_ruta, desglose_ruta,
)
from ._shared import (
    TABLE_RUTAS,
    TIPOS_RUTA,
    EXTRAS_USA,
    cargar_datos_generales,
    limpiar_fila_json,
    safe,
    calcular_ruta_setlogis,
    tiene_mx,
    direccion_label,
    normalizar,
    a_usd,
    get_profile_name,
)


# ─────────────────────────────────────────────
# CACHE
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=120)
def _cargar_rutas(table: str) -> pd.DataFrame:
    sb = get_supabase_client()
    if sb is None:
        return pd.DataFrame()
    try:
        resp = sb.table(table).select("*").order("Fecha", desc=True).execute()
        df = pd.DataFrame(resp.data or [])
        if not df.empty and "Fecha" in df.columns:
            df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d")
        return df
    except Exception:
        return pd.DataFrame()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _label(row) -> str:
    return (
        f"{row.get('ID_Ruta', '')} | "
        f"{row.get('Fecha', '')} | "
        f"{row.get('Tipo_Viaje', '')} | "
        f"{row.get('Cliente', '')} | "
        f"{row.get('Ruta_USA', '')}"
    )


# ─────────────────────────────────────────────
# RESUMEN EDICIÓN
# ─────────────────────────────────────────────
def _mostrar_resumen_edicion(r: dict, modalidad: str, cxm_flete: float, cxm_fuel: float) -> None:
    section_header("📊", "Vista Previa de Cambios")
    kpi_row([
        {"icono": "💰", "label": "Ingreso Global",  "valor": f"${r['Ingreso_Global']:,.2f}",  "sub": "USD", "color": "#1B2266"},
        {"icono": "📉", "label": "Costo Directo",   "valor": f"${r['Costo_Directo']:,.2f}",   "sub": f"{r['Pct_Costo_Directo']:.1f}%", "color": r.get("Color_Directo","#dc2626")},
        {"icono": "📊", "label": "Costo Indirecto", "valor": f"${r['Costo_Indirecto']:,.2f}", "sub": f"{r['Pct_Costo_Indirecto']:.1f}%", "color": r.get("Color_Indirecto","#dc2626")},
        {"icono": "✅", "label": "Utilidad Neta",   "valor": f"${r['Utilidad_Neta']:,.2f}",   "sub": f"{r['Pct_Ut_Neta']:.1f}%", "color": r.get("Color_Ut_Neta","#dc2626")},
    ])

    if r.get("Fuel_Owner"):
        st.info(f"⛽ **Fuel pagado al Owner:** ${r.get('Pago_Fuel_Owner', 0):,.2f} USD — incluido en Costo Directo")

    divider()
    semaforos_ruta(r)
    divider()
    desglose_ruta(r, modalidad=modalidad, cxm_flete=cxm_flete, cxm_fuel=cxm_fuel)


# ─────────────────────────────────────────────
# TABLA GENERAL
# ─────────────────────────────────────────────
def _tabla_rutas(df: pd.DataFrame) -> None:
    cols_show = [c for c in [
        "ID_Ruta", "Fecha", "Tipo_Viaje", "Modo", "Cliente", "Ruta_USA",
        "Ingreso_Global", "Costo_Directo", "Utilidad_Neta",
        "Pct_Ut_Neta", "Fuel_Owner",
    ] if c in df.columns]
    st.dataframe(df[cols_show], use_container_width=True, hide_index=True)


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

    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("🔄 Recargar", key="sl_gest_reload"):
            _cargar_rutas.clear()
            st.rerun()
    with c2:
        st.caption("Carga cacheada 2 min. Usa 'Recargar' si acabas de guardar algo.")

    df = _cargar_rutas(TABLE_RUTAS)
    if df.empty:
        alert("info", "ℹ️ No hay rutas guardadas.")
        return

    valores = cargar_datos_generales()
    tc      = safe(valores.get("Tipo de Cambio USD/MXP", 18.50))

    # ── Tabs: Ver tabla / Eliminar / Editar ──────────────────────────────────
    tab_ver, tab_del, tab_edit = st.tabs(["📋 Ver Rutas", "🗑️ Eliminar", "✏️ Editar"])

    # ══════════════════════════════════════════════════════════════
    # TAB VER
    # ══════════════════════════════════════════════════════════════
    with tab_ver:
        section_header("📋", "Rutas Guardadas")
        _tabla_rutas(df)

    # ══════════════════════════════════════════════════════════════
    # TAB ELIMINAR
    # ══════════════════════════════════════════════════════════════
    with tab_del:
        section_header("🗑️", "Eliminar Ruta")

        df_del = df.copy()
        if "ID_Ruta" not in df_del.columns:
            alert("warn", "No se puede identificar rutas.")
            return
        df_del = df_del.set_index("ID_Ruta", drop=False)

        idx_del = st.selectbox(
            "Selecciona ruta a eliminar",
            options=[""] + df_del.index.tolist(),
            format_func=lambda i: "— Elige una ruta —" if i == "" else _label(df_del.loc[i]),
            key="sl_del_select",
        )
        if idx_del:
            st.warning(f"⚠️ ¿Eliminar la ruta **{idx_del}**? Esta acción no se puede deshacer.")
            if st.button("🗑️ Confirmar Eliminación", key="sl_del_confirm", type="primary"):
                try:
                    supabase.table(TABLE_RUTAS).delete().eq("ID_Ruta", idx_del).execute()
                    alert("success", f"✅ Ruta **{idx_del}** eliminada.")
                    _cargar_rutas.clear()
                    st.rerun()
                except Exception as ex:
                    alert("error", f"❌ Error al eliminar: {ex}")

    # ══════════════════════════════════════════════════════════════
    # TAB EDITAR
    # ══════════════════════════════════════════════════════════════
    with tab_edit:
        section_header("✏️", "Editar Ruta")

        df_fil = df.copy()
        if "ID_Ruta" not in df_fil.columns:
            return
        df_fil = df_fil.set_index("ID_Ruta", drop=False)

        idx_sel = st.selectbox(
            f"Selecciona ruta a editar ({len(df_fil)} encontrada/s)",
            options=[""] + df_fil.index.tolist(),
            format_func=lambda i: "— Elige una ruta —" if i == "" else _label(df_fil.loc[i]),
            key="sl_edit_select",
        )
        if not idx_sel:
            alert("info", "Selecciona una ruta para editarla.")
            return

        ruta = df_fil.loc[idx_sel].to_dict()

        # Auditoría e historial (solo lectura, fuera del form)
        if ruta.get("Usuario"):
            st.caption(f"👤 Capturada por: **{ruta.get('Usuario')}** · Fecha: **{ruta.get('Fecha','—')}**")
        historial = ruta.get("historial") or []
        if historial:
            with st.expander(f"📜 Historial de modificaciones ({len(historial)})", expanded=False):
                for entrada in reversed(historial):
                    ts  = str(entrada.get("timestamp",""))[:16].replace("T"," ")
                    usr = entrada.get("usuario","—")
                    mot = entrada.get("motivo","—")
                    with st.container():
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
                            if prev.get("Flete_USA"):
                                c1.caption(f"Flete USA: **${safe(prev.get('Flete_USA')):,.2f}**")
                            if prev.get("Ingreso_Cruce"):
                                c2.caption(f"Ing. Cruce: **${safe(prev.get('Ingreso_Cruce')):,.2f}**")
                            if prev.get("Ingreso_MX"):
                                c3.caption(f"Ing. MX: **${safe(prev.get('Ingreso_MX')):,.2f}**")
                        st.divider()
        else:
            st.caption("📜 Sin modificaciones previas.")

        # ── FORM DE EDICIÓN ───────────────────────────────────────────────────
        tipo_ruta_val = str(ruta.get("Tipo_Viaje", TIPOS_RUTA[0]))
        es_empty      = (tipo_ruta_val == "Empty")
        aplica_mx     = tiene_mx(tipo_ruta_val)
        modalidad_val = str(ruta.get("Modalidad", "Flat"))

        k = idx_sel  # sufijo único por ruta para evitar DuplicateElementKey

        with st.form(f"sl_edit_form_{k}"):

            st.markdown("### ⚙️ Motivo de modificación")
            motivo = st.text_input("Motivo (obligatorio)", key=f"sl_edit_motivo_{k}",
                                    placeholder="Ej: Corrección de millas")

            st.divider()
            st.markdown("### 📋 Información General")
            eg1, eg2, eg3 = st.columns(3)

            fecha_val = ruta.get("Fecha", "")
            try:
                from datetime import date as _date
                fecha_dt = _date.fromisoformat(str(fecha_val)[:10])
            except Exception:
                fecha_dt = datetime.today().date()

            fecha    = eg1.date_input("Fecha", value=fecha_dt, key=f"sl_edit_fecha_{k}")
            tipo_ruta = eg2.selectbox("Tipo de Ruta", TIPOS_RUTA,
                                       index=TIPOS_RUTA.index(tipo_ruta_val) if tipo_ruta_val in TIPOS_RUTA else 0,
                                       key=f"sl_edit_tipo_{k}", disabled=True)
            modo     = eg3.selectbox("Modo", ["Individual", "Team"],
                                      index=0 if ruta.get("Modo","Individual") == "Individual" else 1,
                                      key=f"sl_edit_modo_{k}")

            cliente_val = str(ruta.get("Cliente", ""))
            origen_val  = str(ruta.get("Ruta_USA", "")).split(" - ")[0] if " - " in str(ruta.get("Ruta_USA","")) else str(ruta.get("Ruta_USA",""))
            destino_val = str(ruta.get("Ruta_USA", "")).split(" - ")[1] if " - " in str(ruta.get("Ruta_USA","")) else ""

            st.divider()
            st.markdown("### 🇺🇸 Ruta Americana")
            ru1, ru2 = st.columns(2)
            origen_usa  = ru1.text_input("Origen",  value=origen_val,  key=f"sl_edit_ori_{k}")
            destino_usa = ru2.text_input("Destino", value=destino_val, key=f"sl_edit_dest_{k}")
            cliente     = st.text_input("Cliente",  value=cliente_val, key=f"sl_edit_cli_{k}")

            m1, m2, m3 = st.columns(3)
            miles_load  = m1.number_input("Miles Load",  value=safe(ruta.get("Miles_Load")),
                                           min_value=0.0, step=10.0, key=f"sl_edit_ml_{k}", disabled=es_empty)
            short_miles = m2.number_input("Short Miles", value=safe(ruta.get("Short_Miles")),
                                           min_value=0.0, step=1.0,  key=f"sl_edit_sm_{k}", disabled=es_empty)
            miles_empty = m3.number_input("Miles Empty", value=safe(ruta.get("Miles_Empty")),
                                           min_value=0.0, step=10.0, key=f"sl_edit_me_{k}")

            st.divider()
            st.markdown("**💵 Tarifa Americana**")
            mod1, mod2 = st.columns([1, 3])
            modalidad  = mod1.radio("Modalidad", ["Desglosada", "Flat"],
                                     index=0 if modalidad_val == "Desglosada" else 1,
                                     horizontal=False, key=f"sl_edit_modalidad_{k}",
                                     disabled=es_empty)

            moneda_flete_val = str(ruta.get("Moneda_Flete","USD"))
            if modalidad == "Desglosada":
                td1, td2, td3 = st.columns(3)
                moneda_flete   = td1.selectbox("Moneda", ["USD","MXP"],
                                                index=0 if moneda_flete_val=="USD" else 1,
                                                key=f"sl_edit_mf_desg_{k}", disabled=es_empty)
                cxm_flete_cap  = td2.number_input("CXM Flete ($/mi)", value=safe(ruta.get("CXM_Flete")),
                                                   min_value=0.0, step=0.001, format="%.4f",
                                                   key=f"sl_edit_cxmf_{k}", disabled=es_empty)
                cxm_fuel_cap   = td3.number_input("CXM Fuel ($/mi)",  value=safe(ruta.get("CXM_Fuel")),
                                                   min_value=0.0, step=0.001, format="%.4f",
                                                   key=f"sl_edit_cxmfu_{k}", disabled=es_empty)
                flete_flat_cap = 0.0
            else:
                tf1, tf2 = st.columns(2)
                moneda_flete   = tf1.selectbox("Moneda", ["USD","MXP"],
                                                index=0 if moneda_flete_val=="USD" else 1,
                                                key=f"sl_edit_mf_flat_{k}", disabled=es_empty)
                flete_flat_cap = tf2.number_input("Tarifa Flat", value=safe(ruta.get("Flete_USA")),
                                                   min_value=0.0, step=50.0,
                                                   key=f"sl_edit_flat_{k}", disabled=es_empty)
                cxm_flete_cap = cxm_fuel_cap = 0.0

            # ── Fuel Owner ────────────────────────────────────────────────────
            if not es_empty and modalidad == "Desglosada":
                st.divider()
                fuel_owner_ed = st.checkbox(
                    "⛽ Pagar Fuel al Owner (el monto de Fuel se suma al costo directo)",
                    value=bool(ruta.get("Fuel_Owner", False)),
                    key=f"sl_edit_fuel_owner_{k}",
                    help="Actívalo cuando se acordó pagar el fuel al owner.",
                )
            else:
                fuel_owner_ed = False

            # ── Cruce ─────────────────────────────────────────────────────────
            st.divider()
            st.markdown("### 🛂 Cruce Fronterizo")
            incluye_cruce = st.checkbox("¿Incluye cruce?",
                                         value=bool(ruta.get("Incluye_Cruce", False)),
                                         key=f"sl_edit_inccruce_{k}", disabled=es_empty)
            tipo_cruce   = "Propio"
            tipo_carga_c = "Cargado"
            ingreso_cruce_raw = 0.0
            costo_cruce_raw   = 0.0
            mon_ing_cruce     = "USD"
            mon_costo_cruce   = "USD"

            if incluye_cruce and not es_empty:
                cx1, cx2 = st.columns(2)
                tipo_cruce   = cx1.selectbox("Tipo Cruce",  ["Propio","Tercero"],
                                              index=0 if str(ruta.get("Tipo_Cruce","Propio"))=="Propio" else 1,
                                              key=f"sl_edit_tcruce_{k}")
                tipo_carga_c = cx2.selectbox("Tipo Carga",  ["Cargado","Vacío"],
                                              index=0 if str(ruta.get("Tipo_Carga_Cruce","Cargado"))=="Cargado" else 1,
                                              key=f"sl_edit_tcarga_{k}")
                ic1, ic2 = st.columns(2)
                mon_ing_cruce     = ic1.selectbox("Moneda Ing. Cruce", ["USD","MXP"],
                                                   index=0 if str(ruta.get("Moneda_Ingreso_Cruce","USD"))=="USD" else 1,
                                                   key=f"sl_edit_mon_ic_{k}")
                ingreso_cruce_raw = ic1.number_input("Ingreso Cruce", value=safe(ruta.get("Ingreso_Cruce")),
                                                      min_value=0.0, step=10.0, key=f"sl_edit_ic_{k}")
                if tipo_cruce == "Tercero":
                    mon_costo_cruce   = ic2.selectbox("Moneda Costo Cruce", ["USD","MXP"],
                                                       index=0 if str(ruta.get("Moneda_Costo_Cruce","USD"))=="USD" else 1,
                                                       key=f"sl_edit_mon_cc_{k}")
                    costo_cruce_raw   = ic2.number_input("Costo Cruce", value=safe(ruta.get("Costo_Cruce")),
                                                          min_value=0.0, step=10.0, key=f"sl_edit_cc_{k}")

            # ── Tramo MX ──────────────────────────────────────────────────────
            origen_mx = destino_mx = ""
            ingreso_mx_raw = costo_mx_raw = 0.0
            mon_ing_mx = "MXP"
            mon_costo_mx = "MXP"

            if aplica_mx and not es_empty:
                st.divider()
                st.markdown("### 🇲🇽 Tramo Mexicano")
                mx1, mx2 = st.columns(2)
                origen_mx  = mx1.text_input("Origen MX",  value=str(ruta.get("Origen_MX","")),
                                             key=f"sl_edit_ori_mx_{k}")
                destino_mx = mx2.text_input("Destino MX", value=str(ruta.get("Destino_MX","")),
                                             key=f"sl_edit_dest_mx_{k}")
                mi1, mi2 = st.columns(2)
                mon_ing_mx     = mi1.selectbox("Moneda Ing. MX", ["MXP","USD"],
                                                index=0 if str(ruta.get("Moneda_Ingreso_MX","MXP"))=="MXP" else 1,
                                                key=f"sl_edit_mon_imx_{k}")
                ingreso_mx_raw = mi1.number_input("Ingreso MX", value=safe(ruta.get("Ingreso_MX")),
                                                   min_value=0.0, step=100.0, key=f"sl_edit_imx_{k}")
                mon_costo_mx   = mi2.selectbox("Moneda Costo MX", ["MXP","USD"],
                                                index=0 if str(ruta.get("Moneda_Costo_MX","MXP"))=="MXP" else 1,
                                                key=f"sl_edit_mon_cmx_{k}")
                costo_mx_raw   = mi2.number_input("Costo MX", value=safe(ruta.get("Costo_MX")),
                                                   min_value=0.0, step=100.0, key=f"sl_edit_cmx_{k}")

            # ── Extras ────────────────────────────────────────────────────────
            st.divider()
            st.markdown("### ➕ Otros Cargos")
            otros_cargos  = {}
            otros_pagados = {}

            cols_extra = st.columns(3)
            for i, extra in enumerate(EXTRAS_USA):
                col = cols_extra[i % 3]
                key_ext  = f"Extra_{extra.replace(' ','_')}"
                key_cob  = f"Extra_{extra.replace(' ','_')}_Cobrado"
                val_prev = safe(ruta.get(key_ext, 0.0))
                cob_prev = bool(ruta.get(key_cob, False))
                monto   = col.number_input(extra, value=val_prev, min_value=0.0, step=10.0,
                                            key=f"sl_edit_ext_{extra}_{k}")
                cobrado = col.checkbox("Cobrado al cliente", value=cob_prev,
                                        key=f"sl_edit_extc_{extra}_{k}")
                if monto > 0:
                    otros_cargos[extra]  = monto
                    otros_pagados[extra] = cobrado

            # ── Costo Indirecto ───────────────────────────────────────────────
            st.divider()
            st.markdown("### 📉 Costo Indirecto")
            ci_col, _ = st.columns([1,2])
            modo_ci = ci_col.radio("Método", ["CXM","Porcentaje"],
                                    horizontal=True, key=f"sl_edit_ci_{k}")

            st.divider()
            revisar = st.form_submit_button("🔍 Revisar Cambios", type="primary",
                                             use_container_width=True)

        # ══════════════════════════════════════════════════════════════
        # LÓGICA POST-FORM
        # ══════════════════════════════════════════════════════════════
        if revisar:
            if not motivo.strip():
                alert("error", "⚠️ El motivo de modificación es obligatorio.")
                st.stop()

            if es_empty:
                flete_usd = fuel_usd = 0.0
            elif modalidad == "Desglosada":
                # Separar flete y fuel igual que en captura
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

            r = calcular_ruta_setlogis(
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

            r["Modalidad"]     = modalidad
            r["CXM_Flete_Cap"] = safe(cxm_flete_cap) if modalidad == "Desglosada" else 0.0
            r["CXM_Fuel_Cap"]  = safe(cxm_fuel_cap)  if modalidad == "Desglosada" else 0.0
            r["Flete_Flat"]    = flete_usd            if modalidad == "Flat"       else 0.0

            st.session_state["sl_edit_resultado"] = r
            st.session_state["sl_edit_datos"] = {
                "idx_sel":         idx_sel,
                "fecha":           str(fecha),
                "motivo":          motivo.strip(),
                "origen_mx":       normalizar(origen_mx)  if aplica_mx else "",
                "destino_mx":      normalizar(destino_mx) if aplica_mx else "",
                "moneda_flete":    moneda_flete,
                "mon_ing_cruce":   mon_ing_cruce,
                "mon_costo_cruce": mon_costo_cruce,
                "mon_ing_mx":      mon_ing_mx,
                "mon_costo_mx":    mon_costo_mx,
                "tipo_carga_cruce": tipo_carga_c if incluye_cruce and not es_empty else "",
                "incluye_cruce":   incluye_cruce and not es_empty,
                "otros_cargos":    otros_cargos,
                "otros_pagados":   otros_pagados,
                "miles_load":      miles_load,
                "miles_empty":     miles_empty,
                "short_miles":     short_miles,
                "modalidad":       modalidad,
                "cxm_flete_cap":   safe(cxm_flete_cap),
                "cxm_fuel_cap":    safe(cxm_fuel_cap),
                "fuel_owner":      fuel_owner_ed,
            }

        # ══════════════════════════════════════════════════════════════
        # MOSTRAR RESULTADO Y BOTÓN GUARDAR (fuera del form)
        # ══════════════════════════════════════════════════════════════
        r_prev = st.session_state.get("sl_edit_resultado")
        d_prev = st.session_state.get("sl_edit_datos", {})

        if r_prev and d_prev.get("idx_sel") == idx_sel:
            mod_prev = d_prev.get("modalidad", "Flat")
            _mostrar_resumen_edicion(
                r_prev,
                modalidad = mod_prev,
                cxm_flete = d_prev.get("cxm_flete_cap", 0.0),
                cxm_fuel  = d_prev.get("cxm_fuel_cap",  0.0),
            )

            divider()
            if st.button("💾 Guardar Cambios en Base de Datos", key=f"sl_guardar_edit_{k}",
                         type="primary", use_container_width=True):
                try:
                    historial_anterior = ruta.get("historial") or []
                    if not isinstance(historial_anterior, list):
                        historial_anterior = []

                    entrada_historial = {
                        "timestamp": _now_iso(),
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
                            "Extras_Costo":        ruta.get("Extras_Costo"),
                            "Costo_Indirecto":     ruta.get("Costo_Indirecto"),
                            "Costo_Total":         ruta.get("Costo_Total"),
                            "Utilidad_Bruta":      ruta.get("Utilidad_Bruta"),
                            "Utilidad_Neta":       ruta.get("Utilidad_Neta"),
                            "Pct_Ut_Bruta":        ruta.get("Pct_Ut_Bruta"),
                            "Pct_Ut_Neta":         ruta.get("Pct_Ut_Neta"),
                            "Pct_Costo_Directo":   ruta.get("Pct_Costo_Directo"),
                            "Pct_Costo_Indirecto": ruta.get("Pct_Costo_Indirecto"),
                            "Miles_Load":          ruta.get("Miles_Load"),
                            "Short_Miles":         ruta.get("Short_Miles"),
                            "Miles_Empty":         ruta.get("Miles_Empty"),
                            "Millas_Totales":      ruta.get("Millas_Totales"),
                            "PxM_Cargado":         ruta.get("PxM_Cargado"),
                            "PxM_Vacio":           ruta.get("PxM_Vacio"),
                            "Modalidad":           ruta.get("Modalidad"),
                            "CXM_Flete":           ruta.get("CXM_Flete"),
                            "CXM_Fuel":            ruta.get("CXM_Fuel"),
                            "Flete_Flat":          ruta.get("Flete_Flat"),
                            "Tipo_Viaje":          ruta.get("Tipo_Viaje"),
                            "Modo":                ruta.get("Modo"),
                            "Cliente":             ruta.get("Cliente"),
                            "Ruta_USA":            ruta.get("Ruta_USA"),
                            "Origen_MX":           ruta.get("Origen_MX"),
                            "Destino_MX":          ruta.get("Destino_MX"),
                            "Tipo_Cruce":          ruta.get("Tipo_Cruce"),
                            "Incluye_Cruce":       ruta.get("Incluye_Cruce"),
                            "Tipo_Carga_Cruce":    ruta.get("Tipo_Carga_Cruce"),
                            "Fecha":               ruta.get("Fecha"),
                            "TC_USD_MXP":          ruta.get("TC_USD_MXP"),
                        },
                    }
                    historial_nuevo = historial_anterior + [entrada_historial]

                    extras_db         = {f"Extra_{n.replace(' ','_')}": v
                                         for n, v in d_prev["otros_cargos"].items()}
                    extras_cobrado_db = {f"Extra_{n.replace(' ','_')}_Cobrado": v
                                         for n, v in d_prev["otros_pagados"].items()}

                    fila = {
                        "Fecha":                d_prev["fecha"],
                        "Tipo_Viaje":           r_prev["Tipo_Viaje"],
                        "Modo":                 r_prev["Modo"],
                        "Direccion":            r_prev["Direccion"],
                        "Modalidad":            mod_prev,
                        "Cliente":              r_prev["Cliente"],
                        "Ruta_USA":             r_prev["Ruta_USA"],
                        "Origen_MX":            d_prev["origen_mx"],
                        "Destino_MX":           d_prev["destino_mx"],
                        "Moneda_Flete":         d_prev["moneda_flete"],
                        "Moneda_Ingreso_Cruce": d_prev["mon_ing_cruce"],
                        "Moneda_Costo_Cruce":   d_prev["mon_costo_cruce"],
                        "Moneda_Ingreso_MX":    d_prev["mon_ing_mx"],
                        "Moneda_Costo_MX":      d_prev["mon_costo_mx"],
                        "Tipo_Carga_Cruce":     d_prev["tipo_carga_cruce"],
                        "Incluye_Cruce":        d_prev["incluye_cruce"],
                        "Miles_Load":           d_prev["miles_load"],
                        "Miles_Empty":          d_prev["miles_empty"],
                        "Short_Miles":          d_prev["short_miles"],
                        "Millas_Totales":       r_prev["Millas_Totales"],
                        "CXM_Flete":            d_prev["cxm_flete_cap"] if mod_prev == "Desglosada" else 0.0,
                        "CXM_Fuel":             d_prev["cxm_fuel_cap"]  if mod_prev == "Desglosada" else 0.0,
                        "Flete_Flat":           r_prev["Flete_Flat"],
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
                        "updated_at":           _now_iso(),
                        "historial":            historial_nuevo,
                        **extras_db,
                        **extras_cobrado_db,
                    }

                    fila_limpia = limpiar_fila_json(fila)
                    supabase.table(TABLE_RUTAS).update(fila_limpia).eq("ID_Ruta", idx_sel).execute()

                    st.session_state.pop("sl_edit_resultado", None)
                    st.session_state.pop("sl_edit_datos", None)
                    st.session_state.pop("sl_edit_id_revisado", None)

                    alert("success", f"✅ Ruta **{idx_sel}** actualizada correctamente.")
                    _cargar_rutas.clear()
                    st.rerun()

                except Exception as ex:
                    alert("error", f"❌ Error al guardar cambios: {ex}")
