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
# FILTROS REUTILIZABLES
# ─────────────────────────────────────────────
def _filtrar(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    f1, f2, f3 = st.columns(3)
    txt_id     = f1.text_input("Buscar ID",      key=f"{prefix}_fid").strip().upper()
    txt_cli    = f2.text_input("Buscar Cliente", key=f"{prefix}_fcli").strip().upper()
    txt_ruta   = f3.text_input("Buscar Ruta",    key=f"{prefix}_fruta").strip().upper()
    out = df.copy()
    if txt_id:
        out = out[out["ID_Ruta"].astype(str).str.upper().str.contains(txt_id, na=False)]
    if txt_cli:
        out = out[out["Cliente"].astype(str).str.upper().str.contains(txt_cli, na=False)]
    if txt_ruta:
        out = out[out["Ruta_USA"].astype(str).str.upper().str.contains(txt_ruta, na=False)]
    return out


# ─────────────────────────────────────────────
# TABLA GENERAL
# ─────────────────────────────────────────────
def _tabla_general(df: pd.DataFrame) -> None:
    section_header("📋", "Tabla General de Rutas")
    cols_show = [c for c in [
        "ID_Ruta","Fecha","Tipo_Viaje","Modo","Cliente","Ruta_USA",
        "Modalidad","Miles_Load","Short_Miles","Miles_Empty",
        "Ingreso_Global","Costo_Directo","Costo_Indirecto",
        "Utilidad_Bruta","Utilidad_Neta",
        "Pct_Ut_Bruta","Pct_Ut_Neta","Usuario",
    ] if c in df.columns]
    df_show = df[cols_show].copy()
    for col in ["Ingreso_Global","Costo_Directo","Costo_Indirecto",
                "Utilidad_Bruta","Utilidad_Neta"]:
        if col in df_show.columns:
            df_show[col] = df_show[col].apply(lambda x: f"${x:,.2f}" if pd.notna(x) else "")
    for col in ["Pct_Ut_Bruta","Pct_Ut_Neta"]:
        if col in df_show.columns:
            df_show[col] = df_show[col].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "")
    st.dataframe(df_show, use_container_width=True, hide_index=True)

    try:
        from io import BytesIO
        import openpyxl
        buf = BytesIO()
        df[cols_show].to_excel(buf, index=False, engine="openpyxl")
        buf.seek(0)
        st.download_button(
            "⬇️ Descargar Excel",
            data=buf,
            file_name="rutas_set_logis.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="sl_dl_excel",
        )
    except Exception:
        pass


# ─────────────────────────────────────────────
# ELIMINAR
# ─────────────────────────────────────────────
def _eliminar(df: pd.DataFrame, supabase) -> None:
    section_header("🗑️", "Eliminar Ruta")
    df_fil = _filtrar(df, "sl_elim")
    if df_fil.empty:
        alert("info", "No hay rutas con esos filtros.")
        return
    if "ID_Ruta" not in df_fil.columns:
        return
    df_fil = df_fil.set_index("ID_Ruta", drop=False)
    idx_sel = st.selectbox(
        f"Selecciona ruta a eliminar ({len(df_fil)} encontrada/s)",
        options=[""] + df_fil.index.tolist(),
        format_func=lambda i: "— Elige una ruta —" if i == "" else _label(df_fil.loc[i]),
        key="sl_elim_select",
    )
    if not idx_sel:
        return
    ruta = df_fil.loc[idx_sel]
    st.warning(
        f"⚠️ ¿Confirmas eliminar la ruta **{idx_sel}**?  \n"
        f"Cliente: {ruta.get('Cliente','—')} · Ruta: {ruta.get('Ruta_USA','—')} · Fecha: {ruta.get('Fecha','—')}"
    )
    if st.button("🗑️ Sí, eliminar definitivamente", key="sl_elim_confirm", type="primary"):
        try:
            supabase.table(TABLE_RUTAS).delete().eq("ID_Ruta", idx_sel).execute()
            alert("success", f"✅ Ruta **{idx_sel}** eliminada correctamente.")
            _cargar_rutas.clear()
            st.rerun()
        except Exception as ex:
            alert("error", f"❌ Error al eliminar: {ex}")


# ─────────────────────────────────────────────
# RESUMEN DE RESULTADO (igual que captura)
# ─────────────────────────────────────────────
def _mostrar_resumen_edicion(r: dict, modalidad: str, cxm_flete: float, cxm_fuel: float) -> None:
    divider()
    section_header("📊", "Vista Previa del Resultado")

    pct_ut_b   = r.get("Pct_Ut_Bruta", 0.0)
    color_ut_b = "#16a34a" if pct_ut_b >= 15.0 else "#dc2626"

    kpi_row([
        {
            "icono": "💵",
            "label": "Ingreso Total",
            "valor": f"${r['Ingreso_Global']:,.2f} USD",
            "sub":   "Flete + Cruce + MX + Extras cliente",
            "color": "#1B2266",
        },
        {
            "icono": "📉",
            "label": "Costo Directo",
            "valor": f"${r['Costo_Directo']:,.2f} USD",
            "sub":   f"{r['Pct_Costo_Directo']:.1f}% del ingreso",
            "color": r.get("Color_Directo", "#6B7280"),
        },
        {
            "icono": "📈",
            "label": "Utilidad Bruta",
            "valor": f"${r['Utilidad_Bruta']:,.2f} USD",
            "sub":   f"{pct_ut_b:.1f}% del ingreso",
            "color": color_ut_b,
        },
        {
            "icono": "🔁",
            "label": "Costo Indirecto",
            "valor": f"${r['Costo_Indirecto']:,.2f} USD",
            "sub":   f"{r['Pct_Costo_Indirecto']:.1f}% del ingreso",
            "color": r.get("Color_Indirecto", "#F59E0B"),
        },
        {
            "icono": "🏆",
            "label": "Utilidad Neta",
            "valor": f"${r['Utilidad_Neta']:,.2f} USD",
            "sub":   f"{r['Pct_Ut_Neta']:.1f}% del ingreso",
            "color": r.get("Color_Ut_Neta", "#6B7280"),
        },
    ])

    divider()
    semaforos_ruta(r)
    desglose_ruta(r, modalidad=modalidad, cxm_flete=cxm_flete, cxm_fuel=cxm_fuel)


# ─────────────────────────────────────────────
# EDITAR — flujo: form → revisar → guardar
# ─────────────────────────────────────────────
def _editar(df: pd.DataFrame, supabase, nombre_usuario: str) -> None:
    section_header("✏️", "Editar Ruta")
    df_fil = _filtrar(df, "sl_edit")
    if df_fil.empty:
        alert("info", "No hay rutas con esos filtros.")
        return
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

    valores = cargar_datos_generales()
    tc = safe(valores.get("Tipo de Cambio USD/MXP", 18.50))
    tipo_ruta_actual = str(ruta.get("Tipo_Viaje", "NB"))

    # Clave dinámica para evitar DuplicateElementKey
    k = idx_sel.replace("-", "_")

    # ── Si ya se revisó, limpiar al cambiar de ruta ───────────────────────────
    if st.session_state.get("sl_edit_id_revisado") != idx_sel:
        st.session_state.pop("sl_edit_resultado", None)
        st.session_state.pop("sl_edit_datos", None)
        st.session_state["sl_edit_id_revisado"] = idx_sel

    # ══════════════════════════════════════════════════════════════
    # FORMULARIO DE EDICIÓN
    # ══════════════════════════════════════════════════════════════
    with st.form(f"sl_edit_form_{k}", clear_on_submit=False):

        # Motivo obligatorio — arriba del todo
        motivo = st.text_input(
            "📝 Motivo de la modificación *",
            placeholder="Ej: Corrección de millas, ajuste de ingreso…",
            key=f"sl_edit_motivo_{k}",
        )
        st.divider()

        # ── Info general ──────────────────────────────────────────────────────
        st.markdown("### 📋 Información General")
        g1, g2, g3, g4 = st.columns(4)
        tipo_idx  = TIPOS_RUTA.index(tipo_ruta_actual) if tipo_ruta_actual in TIPOS_RUTA else 0
        tipo_ruta = g1.selectbox("Tipo", TIPOS_RUTA, index=tipo_idx,   key=f"sl_edit_tipo_{k}")
        modo      = g2.selectbox("Modo", ["Sencillo","Team"],
                                  index=0 if ruta.get("Modo","Sencillo")=="Sencillo" else 1,
                                  key=f"sl_edit_modo_{k}")
        cliente   = g3.text_input("Cliente", value=str(ruta.get("Cliente","")), key=f"sl_edit_cli_{k}")
        try:
            fecha_default = datetime.strptime(str(ruta.get("Fecha",""))[:10], "%Y-%m-%d").date()
        except Exception:
            fecha_default = datetime.today().date()
        fecha = g4.date_input("Fecha", value=fecha_default, key=f"sl_edit_fecha_{k}")

        aplica_mx = tiene_mx(tipo_ruta)
        es_empty  = tipo_ruta == "Empty"

        # ── Ruta USA ──────────────────────────────────────────────────────────
        st.divider()
        st.markdown("### 🇺🇸 Ruta Americana")
        u1, u2 = st.columns(2)
        origen_usa  = u1.text_input("Origen USA",  value=str(ruta.get("Ruta_USA","").split(" - ")[0] if " - " in str(ruta.get("Ruta_USA","")) else ruta.get("Ruta_USA","")), key=f"sl_edit_ori_{k}")
        destino_usa = u2.text_input("Destino USA", value=str(ruta.get("Ruta_USA","").split(" - ")[-1] if " - " in str(ruta.get("Ruta_USA","")) else ""), key=f"sl_edit_dest_{k}")

        m1, m2, m3 = st.columns(3)
        miles_load  = m1.number_input("Miles Load (cotizadas cliente)", value=safe(ruta.get("Miles_Load")),
                                       min_value=0.0, step=10.0, key=f"sl_edit_ml_{k}",
                                       disabled=es_empty)
        short_miles = m2.number_input("Short Miles (reales cargado)",   value=safe(ruta.get("Short_Miles")),
                                       min_value=0.0, step=10.0, key=f"sl_edit_sm_{k}",
                                       disabled=es_empty)
        miles_empty = m3.number_input("Miles Empty (vacías)",           value=safe(ruta.get("Miles_Empty")),
                                       min_value=0.0, step=10.0, key=f"sl_edit_me_{k}")

        # ── Modalidad / Tarifa ────────────────────────────────────────────────
        st.divider()
        st.markdown("### 💰 Tarifa")
        mod_opts     = ["Flat","Desglosada"]
        modalidad_val = str(ruta.get("Modalidad","Flat"))
        mod_idx      = mod_opts.index(modalidad_val) if modalidad_val in mod_opts else 0
        modalidad    = st.radio("Modalidad", mod_opts, index=mod_idx,
                                 horizontal=True, key=f"sl_edit_modalidad_{k}",
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

        # ── Cruce ─────────────────────────────────────────────────────────────
        st.divider()
        st.markdown("### 🛂 Cruce Fronterizo")
        incluye_cruce = st.checkbox("¿Incluye cruce?", value=bool(ruta.get("Incluye_Cruce", False)),
                                     key=f"sl_edit_cruce_{k}", disabled=es_empty)
        if incluye_cruce and not es_empty:
            crx1, crx2, crx3 = st.columns(3)
            tc_opts   = ["Propio","Externo"]
            tc_idx_   = tc_opts.index(str(ruta.get("Tipo_Cruce","Propio"))) if str(ruta.get("Tipo_Cruce","Propio")) in tc_opts else 0
            tipo_cruce    = crx1.selectbox("Tipo Cruce", tc_opts, index=tc_idx_, key=f"sl_edit_tcruce_{k}")
            tcc_opts  = ["Cargado","Vacío"]
            tcc_idx_  = tcc_opts.index(str(ruta.get("Tipo_Carga_Cruce","Cargado"))) if str(ruta.get("Tipo_Carga_Cruce","Cargado")) in tcc_opts else 0
            tipo_carga_c  = crx2.selectbox("Carga Cruce", tcc_opts, index=tcc_idx_, key=f"sl_edit_tcarga_{k}")
            mon_opts  = ["USD","MXP"]
            mon_ing_cruce = crx3.selectbox("Moneda Ingreso", mon_opts,
                                            index=0 if str(ruta.get("Moneda_Ingreso_Cruce","USD"))=="USD" else 1,
                                            key=f"sl_edit_mic_{k}")
            ci1, ci2 = st.columns(2)
            ingreso_cruce_raw = ci1.number_input("Ingreso Cruce", value=safe(ruta.get("Ingreso_Cruce")),
                                                  min_value=0.0, step=10.0, key=f"sl_edit_ingc_{k}")
            if tipo_cruce == "Externo":
                mon_costo_cruce = ci2.selectbox("Moneda Costo", mon_opts,
                                                 index=0 if str(ruta.get("Moneda_Costo_Cruce","USD"))=="USD" else 1,
                                                 key=f"sl_edit_mcc_{k}")
                costo_cruce_raw = st.number_input("Costo Cruce Externo", value=safe(ruta.get("Costo_Cruce")),
                                                   min_value=0.0, step=10.0, key=f"sl_edit_costoc_{k}")
            else:
                mon_costo_cruce = "USD"
                costo_cruce_raw = 0.0
        else:
            tipo_cruce = "Sin cruce"; tipo_carga_c = "Cargado"
            mon_ing_cruce = "USD";    ingreso_cruce_raw = 0.0
            mon_costo_cruce = "USD";  costo_cruce_raw   = 0.0

        # ── Ruta MX ───────────────────────────────────────────────────────────
        if aplica_mx:
            st.divider()
            st.markdown("### 🇲🇽 Ruta México")
            mx_r1, mx_r2 = st.columns(2)
            origen_mx  = mx_r1.text_input("Origen MX",  value=str(ruta.get("Origen_MX","")),  key=f"sl_edit_ori_mx_{k}")
            destino_mx = mx_r2.text_input("Destino MX", value=str(ruta.get("Destino_MX","")), key=f"sl_edit_dest_mx_{k}")
            mx1, mx2, mx3, mx4 = st.columns(4)
            mon_ing_mx     = mx1.selectbox("Moneda Ingreso MX", ["USD","MXP"],
                                            index=0 if str(ruta.get("Moneda_Ingreso_MX","USD"))=="USD" else 1,
                                            key=f"sl_edit_mim_{k}")
            ingreso_mx_raw = mx2.number_input("Ingreso MX", value=safe(ruta.get("Ingreso_MX")),
                                               min_value=0.0, step=50.0, key=f"sl_edit_ingm_{k}")
            mon_costo_mx   = mx3.selectbox("Moneda Costo MX", ["USD","MXP"],
                                            index=0 if str(ruta.get("Moneda_Costo_MX","USD"))=="USD" else 1,
                                            key=f"sl_edit_mcm_{k}")
            costo_mx_raw   = mx4.number_input("Costo MX", value=safe(ruta.get("Costo_MX")),
                                               min_value=0.0, step=50.0, key=f"sl_edit_costom_{k}")
        else:
            origen_mx = destino_mx = ""
            mon_ing_mx = mon_costo_mx = "USD"
            ingreso_mx_raw = costo_mx_raw = 0.0

        # ── Extras ────────────────────────────────────────────────────────────
        st.divider()
        st.markdown("### ➕ Extras")
        st.caption("Captura el monto y marca ✓ si se cobra al cliente.")
        otros_cargos:  dict[str, float] = {}
        otros_pagados: dict[str, bool]  = {}
        for i in range(0, len(EXTRAS_USA), 2):
            col_a, col_b = st.columns(2)
            for col, idx in [(col_a, i), (col_b, i+1)]:
                if idx >= len(EXTRAS_USA):
                    break
                extra       = EXTRAS_USA[idx]
                col_monto   = f"Extra_{extra.replace(' ','_')}"
                col_cobrado = f"Extra_{extra.replace(' ','_')}_Cobrado"
                val_monto   = safe(ruta.get(col_monto, 0.0))
                val_cobrado = bool(ruta.get(col_cobrado, False))
                with col:
                    ex1, ex2 = st.columns([3,1])
                    monto   = ex1.number_input(extra, value=val_monto, min_value=0.0,
                                               step=10.0, key=f"sl_edit_exm_{idx}_{k}")
                    cobrado = ex2.checkbox("cobra", value=val_cobrado,
                                           key=f"sl_edit_exp_{idx}_{k}", help="¿Se cobra al cliente?")
                    if monto > 0:
                        otros_cargos[extra]  = monto
                        otros_pagados[extra] = cobrado

        # ── Costo Indirecto ───────────────────────────────────────────────────
        st.divider()
        st.markdown("### 📉 Costo Indirecto")
        ci_col, _ = st.columns([1,2])
        modo_ci = ci_col.radio("Método", ["CXM","Porcentaje"],
                                horizontal=True, key=f"sl_edit_ci_{k}")

        st.divider()
        # Botón que solo calcula y muestra la vista previa
        revisar = st.form_submit_button("🔍 Revisar Cambios", type="primary",
                                         use_container_width=True)

    # ══════════════════════════════════════════════════════════════
    # LÓGICA POST-FORM: calcular y guardar en session_state
    # ══════════════════════════════════════════════════════════════
    if revisar:
        if not motivo.strip():
            alert("error", "⚠️ El motivo de modificación es obligatorio.")
            st.stop()

        # Construir valores de ingreso según modalidad
        if es_empty:
            flete_usd = fuel_usd = 0.0
        elif modalidad == "Desglosada":
            flete_usd = a_usd((safe(cxm_flete_cap) + safe(cxm_fuel_cap)) * safe(miles_load),
                               moneda_flete, tc)
            fuel_usd  = 0.0
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
        )

        r["Modalidad"]     = modalidad
        r["CXM_Flete_Cap"] = safe(cxm_flete_cap) if modalidad == "Desglosada" else 0.0
        r["CXM_Fuel_Cap"]  = safe(cxm_fuel_cap)  if modalidad == "Desglosada" else 0.0
        r["Flete_Flat"]    = flete_usd            if modalidad == "Flat"       else 0.0

        # Guardar todo en session_state para el botón de guardar (fuera del form)
        st.session_state["sl_edit_resultado"] = r
        st.session_state["sl_edit_datos"] = {
            "idx_sel":        idx_sel,
            "fecha":          str(fecha),
            "motivo":         motivo.strip(),
            "origen_mx":      normalizar(origen_mx)  if aplica_mx else "",
            "destino_mx":     normalizar(destino_mx) if aplica_mx else "",
            "moneda_flete":   moneda_flete,
            "mon_ing_cruce":  mon_ing_cruce,
            "mon_costo_cruce": mon_costo_cruce,
            "mon_ing_mx":     mon_ing_mx,
            "mon_costo_mx":   mon_costo_mx,
            "tipo_carga_cruce": tipo_carga_c if incluye_cruce and not es_empty else "",
            "incluye_cruce":  incluye_cruce and not es_empty,
            "otros_cargos":   otros_cargos,
            "otros_pagados":  otros_pagados,
            "miles_load":     miles_load,
            "miles_empty":    miles_empty,
            "short_miles":    short_miles,
            "modalidad":      modalidad,
            "cxm_flete_cap":  safe(cxm_flete_cap),
            "cxm_fuel_cap":   safe(cxm_fuel_cap),
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
                # Historial: guardar TODOS los valores anteriores de la ruta
                historial_anterior = ruta.get("historial") or []
                if not isinstance(historial_anterior, list):
                    historial_anterior = []

                entrada_historial = {
                    "timestamp": _now_iso(),
                    "usuario":   nombre_usuario,
                    "motivo":    d_prev["motivo"],
                    "valores_anteriores": {
                        # Financieros
                        "Ingreso_Global":      ruta.get("Ingreso_Global"),
                        "Flete_USA":           ruta.get("Flete_USA"),
                        "Fuel":                ruta.get("Fuel"),
                        "Ingreso_Cruce":       ruta.get("Ingreso_Cruce"),
                        "Ingreso_MX":          ruta.get("Ingreso_MX"),
                        "Extras_Ingreso":      ruta.get("Extras_Ingreso"),
                        "Costo_Directo":       ruta.get("Costo_Directo"),
                        "Pago_Owner_Cargado":  ruta.get("Pago_Owner_Cargado"),
                        "Pago_Owner_Vacio":    ruta.get("Pago_Owner_Vacio"),
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
                        # Millas
                        "Miles_Load":          ruta.get("Miles_Load"),
                        "Short_Miles":         ruta.get("Short_Miles"),
                        "Miles_Empty":         ruta.get("Miles_Empty"),
                        "Millas_Totales":      ruta.get("Millas_Totales"),
                        # PxM
                        "PxM_Cargado":         ruta.get("PxM_Cargado"),
                        "PxM_Vacio":           ruta.get("PxM_Vacio"),
                        # Tarifas
                        "Modalidad":           ruta.get("Modalidad"),
                        "CXM_Flete":           ruta.get("CXM_Flete"),
                        "CXM_Fuel":            ruta.get("CXM_Fuel"),
                        "Flete_Flat":          ruta.get("Flete_Flat"),
                        # Ruta
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

                # Limpiar estado
                st.session_state.pop("sl_edit_resultado", None)
                st.session_state.pop("sl_edit_datos", None)
                st.session_state.pop("sl_edit_id_revisado", None)

                alert("success", f"✅ Ruta **{idx_sel}** actualizada correctamente.")
                _cargar_rutas.clear()
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

    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("🔄 Recargar", key="sl_gest_reload"):
            _cargar_rutas.clear()
            st.rerun()
    with c2:
        st.caption("Carga cacheada 2 min. Usa 'Recargar' si acabas de guardar algo.")

    df = _cargar_rutas(TABLE_RUTAS)
    if df.empty:
        alert("warn", "No hay rutas guardadas todavía.")
        alert("info", "Captura una ruta primero desde la pestaña Captura de Rutas.")
        return

    t_tabla, t_eliminar, t_editar = st.tabs([
        "📋 Tabla General",
        "🗑️ Eliminar",
        "✏️ Editar",
    ])

    with t_tabla:
        _tabla_general(df)

    with t_eliminar:
        _eliminar(df, supabase)

    with t_editar:
        _editar(df, supabase, nombre_usuario)
