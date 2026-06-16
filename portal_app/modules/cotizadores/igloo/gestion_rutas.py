"""
gestion_rutas.py — Cotizador Igloo
Gestión: Ver tabla / Eliminar / Editar rutas guardadas.
Diseño homologado con Lincoln y Set Logis:
  - Sin st.title()
  - Tabs: Ver Rutas | Eliminar | Editar
  - Form de edición con st.markdown("### emoji Título") por sección
  - Checkboxes individuales de cobro por extra
  - "Sencillo" en lugar de "Operador"
  - Modal @st.dialog para confirmación
"""

import re
from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import streamlit as st

from services.supabase_client import get_supabase_client, get_authed_client, current_user
from ui.components import section_header, alert, divider

from .helpers import (
    DEFAULTS, TIPOS_RUTA,
    cargar_datos_generales,
    safe_number, safe_float,
    calcular_sueldo_y_bono, calcular_diesel,
    calcular_costos_fijos, calcular_extras,
    calcular_utilidades, mostrar_resultados_utilidad,
)


# ─────────────────────────────────────────────
# HELPERS
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
def _load_rutas_igloo_cached(table_name: str) -> pd.DataFrame:
    supabase = get_supabase_client()
    if supabase is None:
        return pd.DataFrame()
    try:
        resp = supabase.table(table_name).select("*").order("Fecha", desc=True).execute()
        if resp.data:
            return pd.DataFrame(resp.data)
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def _to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Rutas Igloo")
    buf.seek(0)
    return buf.getvalue()


def normalizar_texto(texto):
    if not texto:
        return ""
    texto = str(texto).upper().strip()
    texto = re.sub(r'\s+', ' ', texto)
    texto = re.sub(r'\s*,\s*', ', ', texto)
    return texto


def _label(row) -> str:
    return (
        f"{row.get('ID_Ruta', '')} | {row.get('Fecha', '')} | "
        f"{row.get('Tipo', '')} | {row.get('Cliente', '')} | "
        f"{row.get('Origen', '')} → {row.get('Destino', '')}"
    )


def _filtrar(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    with st.expander("🔎 Filtros (opcional)", expanded=False):
        fc1, fc2, fc3, fc4, fc5 = st.columns(5)
        tipos    = ["Todos"] + sorted(df["Tipo"].dropna().unique().tolist()) if "Tipo" in df.columns else ["Todos"]
        clientes = ["Todos"] + sorted(df["Cliente"].dropna().astype(str).unique().tolist()) if "Cliente" in df.columns else ["Todos"]
        f_tipo = fc1.selectbox("Tipo",            tipos,    key=f"{prefix}_ftipo")
        f_cli  = fc2.selectbox("Cliente",          clientes, key=f"{prefix}_fcli")
        f_id   = fc3.text_input("ID Ruta",         key=f"{prefix}_fid",   placeholder="IG000001").strip().upper()
        f_orig = fc4.text_input("Origen contiene", key=f"{prefix}_forig").strip().upper()
        f_dest = fc5.text_input("Destino contiene",key=f"{prefix}_fdest").strip().upper()

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
# MODAL CONFIRMACIÓN EDICIÓN
# ─────────────────────────────────────────────
@st.dialog("✅ Ruta Actualizada Exitosamente", width="small")
def _modal_edicion(id_ruta: str) -> None:
    alert("success", "**¡La ruta se actualizó correctamente!**")
    st.info(f"### 🆔 ID de la ruta\n`{id_ruta}`")
    st.caption("Los cambios se han guardado y registrado en el historial.")
    if st.button("✅ Aceptar", type="primary", use_container_width=True, key="igloo_modal_ed_ok"):
        st.session_state.pop("igloo_ruta_editada_id", None)
        st.session_state.pop("igloo_mostrar_modal_edicion", None)
        st.session_state.pop("igloo_datos_edicion", None)
        st.session_state.pop("igloo_calc_edicion", None)
        st.session_state.igloo_revisar_edicion = False
        st.rerun()


# ─────────────────────────────────────────────
# RENDER PRINCIPAL
# ─────────────────────────────────────────────
def render():
    supabase = get_supabase_client()
    if supabase is None:
        alert("warn", "⚠️ Supabase no configurado.")
        return

    u = current_user() or {}
    user_id        = u.get("id") or u.get("sub") or ""
    nombre_usuario = _get_profile_name(user_id) or u.get("email") or "Desconocido"

    TABLE_RUTAS = "Rutas"

    # Modal de edición si aplica
    if st.session_state.get("igloo_mostrar_modal_edicion") and st.session_state.get("igloo_ruta_editada_id"):
        _modal_edicion(st.session_state["igloo_ruta_editada_id"])

    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("🔄 Recargar", key="igloo_gestion_reload"):
            _load_rutas_igloo_cached.clear()
            st.rerun()
    with c2:
        st.caption("Carga cacheada 2 min. Usa 'Recargar' si acabas de guardar/editar algo.")

    valores = cargar_datos_generales()
    df      = _load_rutas_igloo_cached(TABLE_RUTAS)

    if df.empty:
        alert("info", "No hay rutas guardadas aún.")
        return

    st.session_state.setdefault("igloo_revisar_edicion", False)

    # ══════════════════════════════════════════════════════════════
    # TABS
    # ══════════════════════════════════════════════════════════════
    tab_ver, tab_del, tab_edit = st.tabs(["📋 Ver Rutas", "🗑️ Eliminar", "✏️ Editar"])

    # ── TAB VER ───────────────────────────────────────────────────
    with tab_ver:
        section_header("📋", "Rutas Registradas")
        df_tabla = _filtrar(df, "ig_ver")

        COLS = [
            "ID_Ruta", "Fecha", "Tipo", "Cliente", "Modo de Viaje",
            "Origen", "Destino", "KM",
            "Ingreso Total", "Costo_Total_Ruta", "Utilidad_Bruta",
            "Porcentaje_Utilidad_Bruta", "Costos_Indirectos", "Utilidad_Neta",
            "Porcentaje_Utilidad_Neta", "created_by",
        ]
        cols_disp = [c for c in COLS if c in df_tabla.columns]
        st.dataframe(
            df_tabla[cols_disp] if cols_disp else df_tabla,
            use_container_width=True,
            hide_index=True,
        )
        st.caption(f"Mostrando {len(df_tabla)} de {len(df)} rutas")
        st.download_button(
            "📥 Descargar Excel",
            data=_to_excel_bytes(df_tabla[cols_disp] if cols_disp else df_tabla),
            file_name=f"rutas_igloo_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="ig_dl_excel",
        )

    # ── TAB ELIMINAR ──────────────────────────────────────────────
    with tab_del:
        section_header("🗑️", "Eliminar Ruta")

        df_del = df.copy()
        if "ID_Ruta" not in df_del.columns:
            alert("warn", "No se puede identificar rutas.")
            return
        df_del = df_del.set_index("ID_Ruta", drop=False)

        df_del_f = _filtrar(df_del.reset_index(drop=True), "ig_del")

        if df_del_f.empty:
            alert("info", "No hay rutas con los filtros aplicados.")
        else:
            df_del_f = df_del_f.set_index("ID_Ruta", drop=False)
            idx_del = st.selectbox(
                "Selecciona ruta a eliminar",
                options=[""] + df_del_f.index.tolist(),
                format_func=lambda i: "— Elige una ruta —" if i == "" else _label(df_del_f.loc[i]),
                key="ig_del_select",
            )
            if idx_del:
                st.warning(f"⚠️ ¿Eliminar la ruta **{idx_del}**? Esta acción no se puede deshacer.")
                if st.button("🗑️ Confirmar Eliminación", key="ig_del_confirm", type="primary"):
                    try:
                        supabase.table(TABLE_RUTAS).delete().eq("ID_Ruta", idx_del).execute()
                        alert("success", f"✅ Ruta **{idx_del}** eliminada.")
                        _load_rutas_igloo_cached.clear()
                        st.rerun()
                    except Exception as ex:
                        alert("error", f"❌ Error al eliminar: {ex}")

    # ── TAB EDITAR ────────────────────────────────────────────────
    with tab_edit:
        section_header("✏️", "Editar Ruta")

        df_ed = df.copy()
        if "ID_Ruta" not in df_ed.columns:
            return
        df_ed = df_ed.set_index("ID_Ruta", drop=False)

        df_ed_f = _filtrar(df_ed.reset_index(drop=True), "ig_ed")
        if df_ed_f.empty:
            alert("info", "No hay rutas con los filtros aplicados.")
            return

        df_ed_f = df_ed_f.set_index("ID_Ruta", drop=False)
        idx_sel = st.selectbox(
            f"Selecciona ruta a editar ({len(df_ed_f)} encontrada/s)",
            options=[""] + df_ed_f.index.tolist(),
            format_func=lambda i: "— Elige una ruta —" if i == "" else _label(df_ed_f.loc[i]),
            key="ig_ed_select",
        )
        if not idx_sel:
            alert("info", "Selecciona una ruta para editarla.")
            return

        ruta = df_ed_f.loc[idx_sel].to_dict()
        st.caption(f"🖊️ Creada por: **{ruta.get('created_by', 'N/A')}** el {str(ruta.get('created_at', ''))[:10]}")

        # Historial (solo lectura, fuera del form)
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
                    key=f"igloo_edit_gen_{key}",
                )

        # ══════════════════════════════════════════════════════════
        # FORMULARIO DE EDICIÓN
        # ══════════════════════════════════════════════════════════
        with st.form("igloo_editar_ruta_form"):

            # Motivo obligatorio
            motivo = st.text_input(
                "✏️ Motivo de modificación (obligatorio)",
                placeholder="Describe el motivo del cambio...",
                key="igloo_motivo_edicion",
            )

            divider()

            # ── Información General ───────────────────────────────
            st.markdown("### 📋 Información General")
            c1, c2, c3, c4 = st.columns(4)
            fecha      = c1.date_input("📅 Fecha", value=pd.to_datetime(ruta.get("Fecha"), errors="coerce").date() if ruta.get("Fecha") else datetime.today().date())
            tipo       = c2.selectbox("🚛 Tipo de Ruta", TIPOS_RUTA, index=tipo_index)
            cliente    = c3.text_input("🏢 Nombre Cliente", value=str(ruta.get("Cliente", "")), placeholder="NOMBRE DE LA EMPRESA")
            modo_viaje = c4.selectbox("👥 Modo de Viaje", modo_list, index=modo_index)

            # ── Cruce ─────────────────────────────────────────────
            st.markdown("### 🛂 Cruce")
            c1, c2, c3, c4 = st.columns(4)
            moneda_cruce       = c1.selectbox("Moneda Ingreso Cruce", ["MXP", "USD"],
                                               index=["MXP","USD"].index(str(ruta.get("Moneda_Cruce","MXP"))))
            ingreso_cruce      = c2.number_input("Ingreso Cruce", min_value=0.0,
                                                  value=float(safe_number(ruta.get("Cruce_Original", 0))))
            moneda_costo_cruce = c3.selectbox("Moneda Costo Cruce", ["MXP", "USD"],
                                               index=["MXP","USD"].index(str(ruta.get("Moneda Costo Cruce","MXP"))))
            costo_cruce        = c4.number_input("Costo Cruce", min_value=0.0,
                                                  value=float(safe_number(ruta.get("Costo Cruce", 0))))

            # ── Ruta Mexicana ─────────────────────────────────────
            st.markdown("### 🇲🇽 Ruta Mexicana")
            c1, c2 = st.columns(2)
            origen  = c1.text_input("📍 Origen",  value=str(ruta.get("Origen", "")),  placeholder="CIUDAD, ESTADO")
            destino = c2.text_input("📍 Destino", value=str(ruta.get("Destino", "")), placeholder="CIUDAD, ESTADO")

            c1, c2, c3, c4 = st.columns(4)
            moneda_ingreso = c1.selectbox("Moneda Ingreso Flete", ["MXP", "USD"],
                                           index=["MXP","USD"].index(str(ruta.get("Moneda","MXP"))))
            ingreso_flete  = c2.number_input("Ingreso Flete", min_value=0.0,
                                              value=float(safe_number(ruta.get("Ingreso_Original", 0))))
            km             = c3.number_input("📏 Kilómetros",    min_value=0.0,
                                              value=float(safe_number(ruta.get("KM", 0))))
            casetas        = c4.number_input("🛣️ Casetas (MXP)", min_value=0.0,
                                              value=float(safe_number(ruta.get("Casetas", 0))))

            if tipo == "DOM MEX":
                c1, _, _, _ = st.columns(4)
                modo_pago_actual = ruta.get("Modo_Pago_Dom", "km")
                modo_pago_dom = c1.selectbox(
                    "Modo pago operador",
                    ["km", "fijo"],
                    format_func=lambda x: "Por kilómetro" if x == "km" else "Pago fijo",
                    index=["km", "fijo"].index(modo_pago_actual) if modo_pago_actual in ["km","fijo"] else 0,
                )
            else:
                modo_pago_dom = "km"

            # ── Termo y Costos Fijos ──────────────────────────────
            st.markdown("### 🌡️ Termo y Conceptos de Costos")
            c1, c2, c3, c4 = st.columns(4)
            horas_termo      = c1.number_input("⏱️ Horas Termo",            min_value=0.0, value=float(safe_number(ruta.get("Horas_Termo", 0))))
            lavado_termo     = c2.number_input("🧼 Lavado Termo (MXP)",     min_value=0.0, value=float(safe_number(ruta.get("Lavado_Termo", 0))))
            movimiento_local = c3.number_input("🔄 Movimiento Local (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Movimiento_Local", 0))))
            # Puntualidad: deshacer el factor Team para mostrar valor base
            punt_guardada    = safe_number(ruta.get("Puntualidad", 0))
            factor_guardado  = 2 if ruta.get("Modo de Viaje") == "Team" else 1
            puntualidad      = c4.number_input("⏰ Puntualidad (MXP)",      min_value=0.0, value=float(punt_guardada / factor_guardado))

            c1, c2, c3, c4 = st.columns(4)
            pension      = c1.number_input("🏨 Pensión (MXP)",      min_value=0.0, value=float(safe_number(ruta.get("Pension", 0))))
            estancia     = c2.number_input("🛌 Estancia (MXP)",     min_value=0.0, value=float(safe_number(ruta.get("Estancia", 0))))
            fianza_termo = c3.number_input("🔒 Fianza Termo (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Fianza_Termo", 0))))
            renta_termo  = c4.number_input("📦 Renta Termo (MXP)",  min_value=0.0, value=float(safe_number(ruta.get("Renta_Termo", 0))))

            # ── Otros Costos ──────────────────────────────────────
            st.markdown("### 🧾 Otros Costos")
            st.caption("Captura el monto. Marca **'cobro'** si también se le cobra al cliente (suma al ingreso).")

            c1, c2, c3 = st.columns(3)
            with c1:
                pistas_extra = st.number_input("Pistas Extra (MXP)", min_value=0.0, value=float(safe_number(ruta.get("Pistas_Extra", 0))), key="ig_ed_pistas")
                cobra_pistas = st.checkbox("cobro", value=bool(ruta.get("Cobra_Pistas", False)), key="ig_ed_cobra_pistas")
            with c2:
                stop         = st.number_input("Stop (MXP)",         min_value=0.0, value=float(safe_number(ruta.get("Stop", 0))),         key="ig_ed_stop")
                cobra_stop   = st.checkbox("cobro", value=bool(ruta.get("Cobra_Stop", False)),   key="ig_ed_cobra_stop")
            with c3:
                falso        = st.number_input("Falso (MXP)",        min_value=0.0, value=float(safe_number(ruta.get("Falso", 0))),        key="ig_ed_falso")
                cobra_falso  = st.checkbox("cobro", value=bool(ruta.get("Cobra_Falso", False)),  key="ig_ed_cobra_falso")

            c1, c2, c3 = st.columns(3)
            with c1:
                gatas        = st.number_input("Gatas (MXP)",        min_value=0.0, value=float(safe_number(ruta.get("Gatas", 0))),        key="ig_ed_gatas")
                cobra_gatas  = st.checkbox("cobro", value=bool(ruta.get("Cobra_Gatas", False)),  key="ig_ed_cobra_gatas")
            with c2:
                accesorios   = st.number_input("Accesorios (MXP)",   min_value=0.0, value=float(safe_number(ruta.get("Accesorios", 0))),   key="ig_ed_acc")
                cobra_acc    = st.checkbox("cobro", value=bool(ruta.get("Cobra_Accesorios", False)), key="ig_ed_cobra_acc")
            with c3:
                guias        = st.number_input("Guías (MXP)",        min_value=0.0, value=float(safe_number(ruta.get("Guias", 0))),        key="ig_ed_guias")
                cobra_guias  = st.checkbox("cobro", value=bool(ruta.get("Cobra_Guias", False)),  key="ig_ed_cobra_guias")

            divider()
            revisar = st.form_submit_button("🔍 Revisar Cambios", use_container_width=True)

        # ══════════════════════════════════════════════════════════
        # CÁLCULOS AL REVISAR
        # ══════════════════════════════════════════════════════════
        if revisar:
            if not motivo or not motivo.strip():
                alert("error", "⚠️ Debes especificar un motivo para la modificación.")
                return

            cliente_norm = normalizar_texto(cliente)
            origen_norm  = normalizar_texto(origen)
            destino_norm = normalizar_texto(destino)

            st.session_state.igloo_revisar_edicion = True
            st.session_state.igloo_datos_edicion   = {
                "id_ruta":            idx_sel,
                "motivo":             motivo.strip(),
                "fecha":              fecha,
                "tipo":               tipo,
                "cliente":            cliente_norm,
                "origen":             origen_norm,
                "destino":            destino_norm,
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

            # ── Cálculo ───────────────────────────────────────────
            factor          = 2 if modo_viaje == "Team" else 1
            puntualidad_val = puntualidad * factor

            extras = calcular_extras(pistas_extra, stop, falso, gatas, accesorios, guias)
            ingreso_extras_cobrados = (
                (pistas_extra if cobra_pistas else 0.0) +
                (stop         if cobra_stop   else 0.0) +
                (falso        if cobra_falso  else 0.0) +
                (gatas        if cobra_gatas  else 0.0) +
                (accesorios   if cobra_acc    else 0.0) +
                (guias        if cobra_guias  else 0.0)
            )

            costos_fijos = calcular_costos_fijos(
                lavado_termo, movimiento_local, puntualidad_val, pension, estancia,
                fianza_termo, renta_termo, casetas,
            )

            tc_usd        = float(valores.get("Tipo de cambio USD", 19.5))
            ingreso_total = ingreso_flete * (tc_usd if moneda_ingreso == "USD" else 1)
            ingreso_total += ingreso_cruce * (tc_usd if moneda_cruce  == "USD" else 1)
            ingreso_total += ingreso_extras_cobrados

            costo_cruce_convertido      = costo_cruce * (tc_usd if moneda_costo_cruce == "USD" else 1)
            diesel_camion, diesel_termo = calcular_diesel(km, horas_termo, valores)
            pago_km, sueldo, bono       = calcular_sueldo_y_bono(tipo, km, modo_viaje, valores, modo_pago_dom)

            costo_total = diesel_camion + diesel_termo + sueldo + bono + costos_fijos + extras + costo_cruce_convertido

            util = calcular_utilidades(ingreso_total, costo_total, tipo)

            st.session_state.igloo_calc_edicion = {
                "tipo_cambio_flete":        tc_usd if moneda_ingreso     == "USD" else 1.0,
                "tipo_cambio_cruce":        tc_usd if moneda_cruce       == "USD" else 1.0,
                "tipo_cambio_costo_cruce":  tc_usd if moneda_costo_cruce == "USD" else 1.0,
                "ingreso_flete_convertido": ingreso_flete * (tc_usd if moneda_ingreso == "USD" else 1),
                "ingreso_cruce_convertido": ingreso_cruce * (tc_usd if moneda_cruce   == "USD" else 1),
                "costo_cruce_convertido":   costo_cruce_convertido,
                "ingreso_extras_cobrados":  ingreso_extras_cobrados,
                "ingreso_total":            ingreso_total,
                "costo_diesel_camion":      diesel_camion,
                "costo_diesel_termo":       diesel_termo,
                "pago_km":                  pago_km,
                "sueldo":                   sueldo,
                "bono":                     bono,
                "puntualidad_val":          puntualidad_val,
                "costos_fijos":             costos_fijos,
                "extras":                   extras,
                "costo_total":              costo_total,
                "costos_indirectos":        util["costos_indirectos"],
                "utilidad_bruta":           util["utilidad_bruta"],
                "utilidad_neta":            util["utilidad_neta"],
                "porcentaje_bruta":         util["porcentaje_bruta"],
                "porcentaje_neta":          util["porcentaje_neta"],
            }

            mostrar_resultados_utilidad(
                st, ingreso_total, costo_total,
                util["utilidad_bruta"], util["costos_indirectos"],
                util["utilidad_neta"], util["porcentaje_bruta"], util["porcentaje_neta"],
                tipo=tipo,
                tc_usd=tc_usd,
            )

        # ── Guardar Cambios ───────────────────────────────────────
        if st.session_state.get("igloo_revisar_edicion", False):
            if st.button("💾 Guardar Cambios", key="igloo_confirmar_edicion", type="primary"):
                d    = st.session_state.get("igloo_datos_edicion", {})
                calc = st.session_state.get("igloo_calc_edicion", {})

                if not d:
                    alert("error", "No hay datos de edición.")
                    return

                # Historial
                historial_anterior = ruta.get("historial") or []
                if not isinstance(historial_anterior, list):
                    historial_anterior = []

                nueva_entrada = {
                    "timestamp": _now_iso(),
                    "usuario":   nombre_usuario,
                    "motivo":    d["motivo"],
                    "cambios_anteriores": {
                        "Cliente":        ruta.get("Cliente"),
                        "Origen":         ruta.get("Origen"),
                        "Destino":        ruta.get("Destino"),
                        "KM":             ruta.get("KM"),
                        "Ingreso_Original": ruta.get("Ingreso_Original"),
                        "Cruce_Original": ruta.get("Cruce_Original"),
                        "Costo_Total_Ruta": ruta.get("Costo_Total_Ruta"),
                        "Utilidad_Neta":  ruta.get("Utilidad_Neta"),
                    },
                }
                historial_actualizado = historial_anterior + [nueva_entrada]

                ruta_actualizada = {
                    "Fecha":              str(d["fecha"]),
                    "Tipo":               d["tipo"],
                    "Cliente":            d["cliente"],
                    "Origen":             d["origen"],
                    "Destino":            d["destino"],
                    "Modo de Viaje":      d["modo_viaje"],
                    "KM":                 d["km"],
                    "Moneda":             d["moneda_ingreso"],
                    "Ingreso_Original":   d["ingreso_flete"],
                    "Tipo de cambio":     calc.get("tipo_cambio_flete"),
                    "Ingreso Flete":      calc.get("ingreso_flete_convertido"),
                    "Moneda_Cruce":       d["moneda_cruce"],
                    "Cruce_Original":     d["ingreso_cruce"],
                    "Tipo cambio Cruce":  calc.get("tipo_cambio_cruce"),
                    "Ingreso Cruce":      calc.get("ingreso_cruce_convertido"),
                    "Moneda Costo Cruce": d["moneda_costo_cruce"],
                    "Costo Cruce":        d["costo_cruce"],
                    "Costo Cruce Convertido": calc.get("costo_cruce_convertido"),
                    "Ingreso Total":      calc.get("ingreso_total"),
                    "Pago por KM":        calc.get("pago_km"),
                    "Sueldo_Operador":    calc.get("sueldo"),
                    "Bono":               calc.get("bono"),
                    "Casetas":            d["casetas"],
                    "Horas_Termo":        d["horas_termo"],
                    "Lavado_Termo":       d["lavado_termo"],
                    "Movimiento_Local":   d["movimiento_local"],
                    "Puntualidad":        calc.get("puntualidad_val"),
                    "Pension":            d["pension"],
                    "Estancia":           d["estancia"],
                    "Fianza_Termo":       d["fianza_termo"],
                    "Renta_Termo":        d["renta_termo"],
                    "Pistas_Extra":       d["pistas_extra"],
                    "Stop":               d["stop"],
                    "Falso":              d["falso"],
                    "Gatas":              d["gatas"],
                    "Accesorios":         d["accesorios"],
                    "Guias":              d["guias"],
                    "Costo_Diesel_Camion": calc.get("costo_diesel_camion"),
                    "Costo_Diesel_Termo":  calc.get("costo_diesel_termo"),
                    "Costo_Extras":        calc.get("extras"),
                    "Costo_Total_Ruta":    calc.get("costo_total"),
                    "Costos_Indirectos":   calc.get("costos_indirectos"),
                    "Utilidad_Bruta":      calc.get("utilidad_bruta"),
                    "Utilidad_Neta":       calc.get("utilidad_neta"),
                    "Porcentaje_Utilidad_Bruta": calc.get("porcentaje_bruta"),
                    "Porcentaje_Utilidad_Neta":  calc.get("porcentaje_neta"),
                    "Modo_Pago_Dom":       d.get("modo_pago_dom", "km"),
                    # Cobros individuales
                    "Cobra_Pistas":        d.get("cobra_pistas",  False),
                    "Cobra_Stop":          d.get("cobra_stop",    False),
                    "Cobra_Falso":         d.get("cobra_falso",   False),
                    "Cobra_Gatas":         d.get("cobra_gatas",   False),
                    "Cobra_Accesorios":    d.get("cobra_acc",     False),
                    "Cobra_Guias":         d.get("cobra_guias",   False),
                    # Legacy
                    "Extras_Cobrados":     False,
                    # Parámetros
                    "Costo Diesel":        float(valores.get("Costo Diesel", 24.0)),
                    "Rendimiento Camion":  float(valores.get("Rendimiento Camion", 2.5)),
                    "Rendimiento Termo":   float(valores.get("Rendimiento Termo", 3.0)),
                    "updated_by":          nombre_usuario,
                    "updated_at":          _now_iso(),
                    "historial":           historial_actualizado,
                }

                try:
                    supabase.table(TABLE_RUTAS).update(ruta_actualizada).eq("ID_Ruta", d["id_ruta"]).execute()
                    st.session_state.igloo_ruta_editada_id       = d["id_ruta"]
                    st.session_state.igloo_mostrar_modal_edicion = True
                    _load_rutas_igloo_cached.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error al actualizar la ruta: {e}")
                    st.exception(e)
