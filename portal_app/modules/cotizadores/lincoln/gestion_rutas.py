"""
gestion_rutas.py – Lincoln Freight (USA/MX)
Tipos de ruta: NB, SB, D2DNB, D2DSB, Empty.
Flujo edición: form → Revisar Cambios → preview → Guardar (fuera del form).
Patrón alineado con Set Logis Plus.
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

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
    calcular_ruta_lincoln,
    obtener_config_tipo_ruta,
    normalizar,
    a_usd,
    get_profile_name,
)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _label(row) -> str:
    return (
        f"{row.get('ID_Ruta', '')} | "
        f"{row.get('Fecha', '')} | "
        f"{row.get('Tipo', '')} | "
        f"{row.get('Cliente', '')} | "
        f"{row.get('Origen', '')} → {row.get('Destino', '')}"
    )


def _to_excel(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Rutas Lincoln")
    buf.seek(0)
    return buf.getvalue()


# ─────────────────────────────────────────────
# FILTROS
# ─────────────────────────────────────────────
def _filtrar(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    with st.expander("🔎 Filtros (opcional)", expanded=False):
        fc1, fc2, fc3, fc4, fc5 = st.columns(5)

        tipos    = ["Todos"] + sorted(df["Tipo"].dropna().unique().tolist()) if "Tipo" in df.columns else ["Todos"]
        clientes = ["Todos"] + sorted(df["Cliente"].dropna().astype(str).unique().tolist()) if "Cliente" in df.columns else ["Todos"]

        f_tipo = fc1.selectbox("Tipo",           tipos,    key=f"{prefix}_ftipo")
        f_cli  = fc2.selectbox("Cliente",         clientes, key=f"{prefix}_fcli")
        f_id   = fc3.text_input("ID Ruta",                  key=f"{prefix}_fid",   placeholder="LN000001").strip().upper()
        f_orig = fc4.text_input("Origen contiene",           key=f"{prefix}_forig").strip().upper()
        f_dest = fc5.text_input("Destino contiene",          key=f"{prefix}_fdest").strip().upper()

    out = df.copy()
    if f_tipo != "Todos":
        out = out[out["Tipo"] == f_tipo]
    if f_cli != "Todos":
        out = out[out["Cliente"].astype(str) == f_cli]
    if f_id:
        out = out[out["ID_Ruta"].astype(str).str.upper().str.contains(f_id, na=False)]
    if f_orig:
        out = out[out["Origen"].astype(str).str.upper().str.contains(f_orig, na=False)]
    if f_dest:
        out = out[out["Destino"].astype(str).str.upper().str.contains(f_dest, na=False)]
    return out


# ─────────────────────────────────────────────
# PREVIEW DE EDICIÓN
# ─────────────────────────────────────────────
def _preview_edicion(r: dict, tipo_ruta: str, millas_usa: float, millas_vac: float) -> None:
    kpi_row([
        dict(icono="💰", label="Ingreso Total",     valor=f"${r['ingreso_total']:,.2f}",      color="#1B2266"),
        dict(icono="💸", label="Costo Directo",     valor=f"${r['costo_directo_total']:,.2f}", color="#DC2626"),
        dict(icono="📈", label="Utilidad Bruta",    valor=f"${r['utilidad_bruta']:,.2f}",     sub=f"{r['pct_bruta']:.1f}%",  color="#059669"),
        dict(icono="📉", label="Costos Indirectos", valor=f"${r['costos_ind']:,.2f}",          color="#D97706"),
        dict(icono="✅", label="Utilidad Neta",     valor=f"${r['utilidad_neta']:,.2f}",       sub=f"{r['pct_neta']:.1f}%",  color="#059669" if r['utilidad_neta'] >= 0 else "#DC2626"),
    ])
    semaforos_ruta(r)

    es_empty = (tipo_ruta == "Empty")
    if es_empty:
        filas = [
            (f"Operador Vacío ({millas_vac:.0f} mi × ${r['cxm_vacio']:.4f})", r["sueldo_base"]),
            ("Diesel (millas vacías)", r["diesel_usa"]),
        ]
    else:
        filas = [
            (f"Sueldo Base ({millas_usa:.0f} mi carg + {millas_vac:.0f} mi vac)", r["sueldo_base"]),
            ("Bono por millas cargadas", r["bono_millas"]),
            ("Diesel (cargado + vacío)",  r["diesel_usa"]),
            ("ISR/IMSS",                  r["isr_imss"]),
        ]
        if r.get("otros_cargos_costo", 0) > 0:
            filas.append(("Otros Cargos (pagados)", r["otros_cargos_costo"]))

    desglose_ruta(r, filas_costo_americana=filas)


# ─────────────────────────────────────────────
# RENDER
# ─────────────────────────────────────────────
def render() -> None:
    sb = get_supabase_client()
    if sb is None:
        alert("error", "Supabase no configurado.")
        return

    u              = current_user() or {}
    user_id        = u.get("id") or u.get("sub") or ""
    nombre_usuario = get_profile_name(user_id) or u.get("email") or "Desconocido"

    c_reload, c_tip = st.columns([1, 4])
    with c_reload:
        if st.button("🔄 Recargar rutas", key="ln_gest_reload"):
            _cargar_rutas.clear()
            st.rerun()
    c_tip.caption("Caché 2 min. Usa 'Recargar' si acabas de guardar algo.")

    valores = cargar_datos_generales()
    df      = _cargar_rutas(TABLE_RUTAS)

    if df.empty:
        alert("info", "No hay rutas guardadas aún.")
        return

    # ══════════════════════════════════════════════════════════════
    # TABLA DE RUTAS
    # ══════════════════════════════════════════════════════════════
    section_header("📋", "Rutas Registradas")
    df_tabla = _filtrar(df, "ln_tab")

    COLS = [
        "ID_Ruta", "Fecha", "Tipo", "Cliente", "Modo_Viaje",
        "Origen", "Destino", "Millas_USA", "Millas_Vacias",
        "Ingreso_Total", "Costo_Directo_Total", "Utilidad_Bruta",
        "Pct_Utilidad_Bruta", "Costos_Indirectos", "Utilidad_Neta",
        "Pct_Utilidad_Neta", "Capturado_Por", "Fecha",
    ]
    cols_disp = [c for c in COLS if c in df_tabla.columns]
    st.dataframe(df_tabla[cols_disp] if cols_disp else df_tabla,
                 use_container_width=True, hide_index=True)
    st.caption(f"Mostrando {len(df_tabla)} de {len(df)} rutas")

    st.download_button(
        "📥 Descargar Excel",
        data=_to_excel(df_tabla[cols_disp] if cols_disp else df_tabla),
        file_name=f"rutas_lincoln_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="ln_dl_excel",
    )

    # ══════════════════════════════════════════════════════════════
    # EDITAR RUTA
    # ══════════════════════════════════════════════════════════════
    divider()
    section_header("✏️", "Editar Ruta")

    df_ed = _filtrar(df, "ln_ed")
    if df_ed.empty:
        alert("info", "No hay rutas con los filtros aplicados.")
        return

    if "ID_Ruta" not in df_ed.columns:
        return
    df_ed = df_ed.set_index("ID_Ruta", drop=False)

    idx_sel = st.selectbox(
        f"Selecciona ruta a editar ({len(df_ed)} encontrada/s)",
        options=[""] + df_ed.index.tolist(),
        format_func=lambda i: "— Elige una ruta —" if i == "" else _label(df_ed.loc[i]),
        key="ln_ed_select",
    )
    if not idx_sel:
        alert("info", "Selecciona una ruta para editarla.")
        return

    ruta = df_ed.loc[idx_sel].to_dict()
    k    = str(idx_sel)   # se usa en las keys del form para evitar DuplicateElementKey

    # ── Auditoría e historial (solo lectura) ──────────────────────
    if ruta.get("Capturado_Por"):
        st.caption(f"👤 Capturada por: **{ruta.get('Capturado_Por')}** · Fecha: **{ruta.get('Fecha', '—')}**")

    historial = ruta.get("historial") or []
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

    # ── Formulario de edición ─────────────────────────────────────
    tipo_actual = ruta.get("Tipo", "NB")
    es_empty_actual = (tipo_actual == "Empty")

    with st.form(f"ln_edit_form_{k}", clear_on_submit=False):

        # Motivo (obligatorio)
        motivo = st.text_input(
            "✏️ Motivo de modificación (obligatorio)",
            placeholder="Describe el motivo del cambio...",
            key=f"ln_ed_motivo_{k}",
        )

        divider()
        st.markdown("**Información General**")
        g1, g2, g3, g4 = st.columns(4)

        fecha_val = pd.to_datetime(ruta.get("Fecha"), errors="coerce")
        fecha_val = datetime.today() if pd.isna(fecha_val) else fecha_val

        fecha      = g1.date_input("Fecha", value=fecha_val.date(), key=f"ln_ed_fecha_{k}")
        tipo_idx   = TIPOS_RUTA.index(tipo_actual) if tipo_actual in TIPOS_RUTA else 0
        tipo       = g2.selectbox("Tipo de Ruta", TIPOS_RUTA, index=tipo_idx, key=f"ln_ed_tipo_{k}")
        cliente    = g3.text_input("Cliente", value=str(ruta.get("Cliente", "")), key=f"ln_ed_cli_{k}")
        modo_list  = ["Sencillo", "Team"]
        modo_idx   = modo_list.index(ruta.get("Modo_Viaje", "Sencillo")) if ruta.get("Modo_Viaje") in modo_list else 0
        modo_viaje = g4.selectbox("Modo", modo_list, index=modo_idx, key=f"ln_ed_modo_{k}")

        config   = obtener_config_tipo_ruta(tipo)
        es_empty = (tipo == "Empty")

        # ── Ruta Americana ────────────────────────────────────────
        divider()
        st.markdown("**Ruta Americana**")
        ru1, ru2 = st.columns(2)

        with ru1:
            origen_usa  = st.text_input("Origen USA",  value=str(ruta.get("Origen", "")),  key=f"ln_ed_ori_{k}")
            destino_usa = st.text_input("Destino USA",  value=str(ruta.get("Destino", "")), key=f"ln_ed_dest_{k}")
            if es_empty:
                millas_usa    = 0.0
                millas_vacias = st.number_input("Millas Vacías",
                                                 value=float(safe(ruta.get("Millas_Vacias", 0))),
                                                 step=10.0, key=f"ln_ed_mi_vac_{k}")
            else:
                millas_usa    = st.number_input("Millas Cargadas",
                                                 value=float(safe(ruta.get("Millas_USA", 0))),
                                                 step=10.0, key=f"ln_ed_mi_usa_{k}")
                millas_vacias = st.number_input("Millas Vacías",
                                                 value=float(safe(ruta.get("Millas_Vacias", 0))),
                                                 step=10.0, key=f"ln_ed_mi_vac_{k}")

        with ru2:
            if es_empty:
                moneda_usa  = "USD"
                modalidad   = "Flat"
                cxm_flete   = 0.0
                cxm_fuel    = 0.0
                tarifa_flat = 0.0
                st.info("ℹ️ Empty: sin tarifa al cliente.")
            else:
                mon_list   = ["USD", "MXP"]
                mon_idx    = mon_list.index(ruta.get("Moneda_USA", "USD")) if ruta.get("Moneda_USA") in mon_list else 0
                moneda_usa = st.selectbox("Moneda", mon_list, index=mon_idx, key=f"ln_ed_moneda_{k}")
                mod_list   = ["Desglosada", "Flat"]
                mod_idx    = mod_list.index(ruta.get("Modalidad", "Desglosada")) if ruta.get("Modalidad") in mod_list else 0
                modalidad  = st.selectbox("Modalidad", mod_list, index=mod_idx, key=f"ln_ed_modal_{k}")
                if modalidad == "Desglosada":
                    cxm_flete   = st.number_input("CXM Flete ($/mi)",
                                                   value=float(safe(ruta.get("CXM_Flete", 0))),
                                                   step=0.01, format="%.4f", key=f"ln_ed_cxmf_{k}")
                    cxm_fuel    = st.number_input("CXM Fuel ($/mi)",
                                                   value=float(safe(ruta.get("CXM_Fuel", 0))),
                                                   step=0.01, format="%.4f", key=f"ln_ed_cxmfuel_{k}")
                    tarifa_flat = 0.0
                else:
                    tarifa_flat = st.number_input("Tarifa Flat (USD)",
                                                   value=float(safe(ruta.get("Tarifa_Flat", 0))),
                                                   step=50.0, key=f"ln_ed_flat_{k}")
                    cxm_flete   = 0.0
                    cxm_fuel    = 0.0

        # ── Cruce ─────────────────────────────────────────────────
        aplica_cruce     = False
        tipo_cruce       = ""
        tipo_carga       = ""
        moneda_cruce     = "USD"
        ingreso_cruce    = 0.0
        costo_cruce_terc = 0.0

        if not es_empty and config.get("cruce") in ("opcional", True):
            divider()
            st.markdown("**Cruce Fronterizo**")
            aplica_cruce = st.checkbox("¿Aplica cruce?",
                                        value=bool(ruta.get("Aplica_Cruce", False)),
                                        key=f"ln_ed_aplcr_{k}")
            if aplica_cruce:
                cx1, cx2 = st.columns(2)
                tc_list  = ["Propio", "Tercero"]
                tc_idx   = tc_list.index(ruta.get("Tipo_Cruce", "Propio")) if ruta.get("Tipo_Cruce") in tc_list else 0
                tipo_cruce    = cx1.selectbox("Tipo de Cruce", tc_list, index=tc_idx, key=f"ln_ed_tcruce_{k}")
                tca_list = ["Cargado", "Vacío"]
                tca_idx  = tca_list.index(ruta.get("Tipo_Carga_Cruce", "Cargado")) if ruta.get("Tipo_Carga_Cruce") in tca_list else 0
                tipo_carga    = cx1.selectbox("Carga", tca_list, index=tca_idx, key=f"ln_ed_tcarga_{k}")
                mon_cr_list   = ["USD", "MXP"]
                mon_cr_idx    = mon_cr_list.index(ruta.get("Moneda_Cruce", "USD")) if ruta.get("Moneda_Cruce") in mon_cr_list else 0
                moneda_cruce  = cx2.selectbox("Moneda Cruce", mon_cr_list, index=mon_cr_idx, key=f"ln_ed_moncruce_{k}")
                ingreso_cruce = cx2.number_input("Ingreso Cruce",
                                                  value=float(safe(ruta.get("Ingreso_Cruce", 0))),
                                                  step=5.0, key=f"ln_ed_ingcruce_{k}")
                if tipo_cruce == "Tercero":
                    costo_cruce_terc = cx2.number_input("Costo Cruce Tercero",
                                                         value=float(safe(ruta.get("Costo_Cruce", 0))),
                                                         step=5.0, key=f"ln_ed_costocruce_{k}")

        # ── Tramo México ──────────────────────────────────────────
        linea_mx   = ""
        origen_mx  = ""
        destino_mx = ""
        moneda_mx  = "MXP"
        ingreso_mx = 0.0
        costo_mx   = 0.0

        if config.get("parte_mx") and not es_empty:
            divider()
            st.markdown("**Tramo México**")
            mx1, mx2 = st.columns(2)
            lmx_list = ["Propia", "Tercero"]
            lmx_idx  = lmx_list.index(ruta.get("Linea_MX", "Propia")) if ruta.get("Linea_MX") in lmx_list else 0
            linea_mx   = mx1.selectbox("Línea MX", lmx_list, index=lmx_idx, key=f"ln_ed_linmx_{k}")
            origen_mx  = mx1.text_input("Origen MX",  value=str(ruta.get("Origen_MX", "")),  key=f"ln_ed_orimx_{k}")
            destino_mx = mx1.text_input("Destino MX", value=str(ruta.get("Destino_MX", "")), key=f"ln_ed_destmx_{k}")
            monmx_list = ["MXP", "USD"]
            monmx_idx  = monmx_list.index(ruta.get("Moneda_MX", "MXP")) if ruta.get("Moneda_MX") in monmx_list else 0
            moneda_mx  = mx2.selectbox("Moneda MX", monmx_list, index=monmx_idx, key=f"ln_ed_monmx_{k}")
            ingreso_mx = mx2.number_input("Ingreso Flete MX",
                                           value=float(safe(ruta.get("Ingreso_MX_MXP", 0))),
                                           step=100.0, key=f"ln_ed_ingmx_{k}")
            if linea_mx == "Tercero":
                costo_mx = mx2.number_input("Costo Flete MX",
                                             value=float(safe(ruta.get("Costo_MX_MXP", 0))),
                                             step=100.0, key=f"ln_ed_costomx_{k}")

        # ── Otros Cargos ──────────────────────────────────────────
        otros_cargos         = {}
        otros_cargos_pagados = {}

        if not es_empty:
            divider()
            st.markdown("**Otros Cargos (USD)**")
            cols3 = st.columns(3)
            for i, extra in enumerate(EXTRAS_USA):
                with cols3[i % 3]:
                    monto  = st.number_input(extra, min_value=0.0, step=10.0, format="%.2f",
                                             key=f"ln_ed_ext_{extra}_{k}")
                    pagado = st.checkbox("Lincoln pagó", key=f"ln_ed_pag_{extra}_{k}")
                    if monto > 0:
                        otros_cargos[extra]         = monto
                        otros_cargos_pagados[extra] = pagado

        divider()
        revisar = st.form_submit_button("🔍 Revisar Cambios", type="primary",
                                        use_container_width=True)

    # ── Post-form: calcular y guardar en session_state ─────────────────────
    if revisar:
        if not motivo.strip():
            alert("error", "⚠️ El motivo de modificación es obligatorio.")
            st.stop()

        tc = float(valores.get("Tipo de Cambio USD/MXP", 18.5))

        if not es_empty:
            if modalidad == "Desglosada":
                ing_x_milla = cxm_flete if moneda_usa == "USD" else a_usd(cxm_flete, tc)
                fuel_sc     = cxm_fuel  if moneda_usa == "USD" else a_usd(cxm_fuel, tc)
            else:
                ing_x_milla = (tarifa_flat if moneda_usa == "USD" else a_usd(tarifa_flat, tc)) / millas_usa if millas_usa else 0.0
                fuel_sc     = 0.0

            ing_cruce_usd = ingreso_cruce if moneda_cruce == "USD" else a_usd(ingreso_cruce, tc)
        else:
            ing_x_milla   = 0.0
            fuel_sc       = 0.0
            ing_cruce_usd = 0.0

        if config.get("parte_mx") and not es_empty:
            ing_mx_mxp   = ingreso_mx * tc if moneda_mx == "USD" else ingreso_mx
            costo_mx_mxp = costo_mx * tc   if moneda_mx == "USD" else costo_mx
            if linea_mx != "Tercero":
                costo_mx_mxp = 0.0
        else:
            ing_mx_mxp   = 0.0
            costo_mx_mxp = 0.0

        r = calcular_ruta_lincoln(
            tipo_ruta            = tipo,
            millas_usa           = millas_usa,
            millas_vacias        = millas_vacias,
            ingreso_x_milla_usd  = ing_x_milla,
            fuel_surcharge_usd   = fuel_sc,
            ingreso_cruce_usd    = ing_cruce_usd,
            aplica_cruce         = aplica_cruce,
            modo_viaje           = modo_viaje,
            tipo_cruce           = tipo_cruce,
            tipo_carga_cruce     = tipo_carga,
            costo_cruce_tercero_usd = costo_cruce_terc,
            ingreso_flete_mx_mxp = ing_mx_mxp,
            costo_flete_mx_mxp   = costo_mx_mxp,
            linea_mx             = linea_mx,
            otros_cargos         = otros_cargos,
            otros_cargos_pagados = otros_cargos_pagados,
            valores              = valores,
        )

        st.session_state["ln_ed_resultado"] = r
        st.session_state["ln_ed_datos"]     = {
            "id_ruta":            idx_sel,
            "motivo":             motivo.strip(),
            "fecha":              str(fecha),
            "tipo":               tipo,
            "cliente":            normalizar(cliente),
            "modo_viaje":         modo_viaje,
            "origen_usa":         normalizar(origen_usa),
            "destino_usa":        normalizar(destino_usa),
            "millas_usa":         millas_usa,
            "millas_vacias":      millas_vacias,
            "moneda_usa":         moneda_usa,
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
            "costo_mx":           costo_mx,
            "ing_mx_mxp":         ing_mx_mxp,
            "costo_mx_mxp":       costo_mx_mxp,
            "otros_cargos":       otros_cargos,
            "otros_cargos_pagados": otros_cargos_pagados,
        }

    # ── Mostrar resultado y botón guardar (fuera del form) ─────────────────
    r_prev = st.session_state.get("ln_ed_resultado")
    d_prev = st.session_state.get("ln_ed_datos", {})

    if r_prev and d_prev.get("id_ruta") == idx_sel:
        divider()
        section_header("📊", "Vista Previa de Cambios")
        _preview_edicion(r_prev, d_prev["tipo"], d_prev["millas_usa"], d_prev["millas_vacias"])

        divider()
        col_g, col_x = st.columns([2, 1])
        with col_g:
            if st.button("💾 Guardar Cambios", type="primary",
                         use_container_width=True, key="ln_ed_guardar"):

                # Construir historial
                historial_ant = list(ruta.get("historial") or [])
                historial_ant.append({
                    "timestamp": _now_iso(),
                    "usuario":   nombre_usuario,
                    "motivo":    d_prev["motivo"],
                    "valores_anteriores": {
                        "Ingreso_Total":        safe(ruta.get("Ingreso_Total")),
                        "Costo_Directo_Total":  safe(ruta.get("Costo_Directo_Total")),
                        "Utilidad_Bruta":       safe(ruta.get("Utilidad_Bruta")),
                        "Pct_Utilidad_Bruta":   safe(ruta.get("Pct_Utilidad_Bruta")),
                        "Utilidad_Neta":        safe(ruta.get("Utilidad_Neta")),
                        "Pct_Utilidad_Neta":    safe(ruta.get("Pct_Utilidad_Neta")),
                    },
                })

                payload = {
                    "Fecha":              d_prev["fecha"],
                    "Tipo":               d_prev["tipo"],
                    "Cliente":            d_prev["cliente"],
                    "Modo_Viaje":         d_prev["modo_viaje"],
                    "Origen":             d_prev["origen_usa"],
                    "Destino":            d_prev["destino_usa"],
                    "Millas_USA":         d_prev["millas_usa"],
                    "Millas_Vacias":      d_prev["millas_vacias"],
                    "Moneda_USA":         d_prev["moneda_usa"],
                    "Modalidad":          d_prev["modalidad"],
                    "CXM_Flete":          d_prev["cxm_flete"],
                    "CXM_Fuel":           d_prev["cxm_fuel"],
                    "Tarifa_Flat":        d_prev["tarifa_flat"],
                    "Aplica_Cruce":       d_prev["aplica_cruce"],
                    "Tipo_Cruce":         d_prev["tipo_cruce"],
                    "Tipo_Carga_Cruce":   d_prev["tipo_carga"],
                    "Moneda_Cruce":       d_prev["moneda_cruce"],
                    "Ingreso_Cruce":      d_prev["ingreso_cruce"],
                    "Costo_Cruce":        safe(r_prev.get("costo_cruce")),
                    "Linea_MX":           d_prev["linea_mx"],
                    "Origen_MX":          d_prev["origen_mx"],
                    "Destino_MX":         d_prev["destino_mx"],
                    "Moneda_MX":          d_prev["moneda_mx"],
                    "Ingreso_MX_MXP":     d_prev["ing_mx_mxp"],
                    "Costo_MX_MXP":       d_prev["costo_mx_mxp"],
                    "Ingreso_MX_USD":     r_prev["ingreso_mx_usd"],
                    "Costo_MX_USD":       r_prev["costo_mx_usd"],
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
                    "updated_at":         _now_iso(),
                    "historial":          historial_ant,
                }

                try:
                    sb.table(TABLE_RUTAS).update(
                        limpiar_fila_json(payload)
                    ).eq("ID_Ruta", idx_sel).execute()

                    st.success(f"✅ Ruta **{idx_sel}** actualizada correctamente.")
                    st.session_state.pop("ln_ed_resultado", None)
                    st.session_state.pop("ln_ed_datos", None)
                    _cargar_rutas.clear()
                    st.rerun()
                except Exception as e:
                    alert("error", f"Error al guardar: {e}")

        with col_x:
            if st.button("🗑️ Cancelar edición", use_container_width=True, key="ln_ed_cancel"):
                st.session_state.pop("ln_ed_resultado", None)
                st.session_state.pop("ln_ed_datos", None)
                st.rerun()

    # ══════════════════════════════════════════════════════════════
    # ELIMINAR RUTA
    # ══════════════════════════════════════════════════════════════
    divider()
    section_header("🗑️", "Eliminar Ruta")

    with st.expander("⚠️ Zona de Peligro — Eliminar Ruta", expanded=False):
        alert("warn", "⚠️ Esta acción es **permanente** e irreversible.")

        d1, d2 = st.columns(2)
        id_del = d1.text_input("ID de ruta a eliminar (escribe exacto)",
                                placeholder="LN000001", key="ln_del_id").strip()
        if id_del and id_del in df["ID_Ruta"].astype(str).values:
            rd = df[df["ID_Ruta"].astype(str) == id_del].iloc[0]
            d2.info(
                f"**Encontrada:** {rd.get('Cliente', '')} | "
                f"{rd.get('Tipo', '')} | {rd.get('Fecha', '')} | "
                f"Ut. Neta ${safe(rd.get('Utilidad_Neta', 0)):,.2f}"
            )
        elif id_del:
            d2.error("ID no encontrado.")

        motivo_del = st.text_area("Motivo de eliminación (obligatorio)",
                                   placeholder="Ej: duplicada, creada por error…",
                                   key="ln_del_motivo")
        confirmar  = st.checkbox("Confirmo que quiero eliminar esta ruta permanentemente",
                                  key="ln_del_confirmar")

        if st.button("🗑️ ELIMINAR", type="primary", key="ln_del_btn"):
            if not id_del:
                alert("error", "Escribe el ID de la ruta.")
            elif id_del not in df["ID_Ruta"].astype(str).values:
                alert("error", "ID no encontrado.")
            elif not motivo_del.strip():
                alert("error", "El motivo es obligatorio.")
            elif not confirmar:
                alert("warn", "Activa la casilla de confirmación.")
            else:
                try:
                    sb.table(TABLE_RUTAS).delete().eq("ID_Ruta", id_del).execute()
                    st.success(f"✅ Ruta **{id_del}** eliminada.")
                    _cargar_rutas.clear()
                    st.rerun()
                except Exception as e:
                    alert("error", f"Error al eliminar: {e}")
