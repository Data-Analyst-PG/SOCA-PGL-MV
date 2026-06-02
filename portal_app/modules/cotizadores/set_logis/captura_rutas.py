"""
captura_rutas.py – Set Logis Plus
Captura de rutas. Sin HTML inline — todo visual via ui/components.

Reglas de negocio:
  · Dirección (Subida/Bajada) se deriva del tipo de ruta, no se captura
  · NB/D2DNB → Subida | SB/D2DSB → Bajada | Empty → solo millas vacías
  · D2DNB/D2DSB incluyen tramo MX (siempre externo)
  · Short Miles se pagan a la misma tasa que millas cargadas
  · Pago owner = (miles_load + short_miles)×PxM_cargado + miles_empty×PxM_vacio
  · Cruce: Propio (costo fijo config) o Externo (costo capturado)
  · Modo Team usa tarifas propias de config
"""

from __future__ import annotations

import re
from datetime import datetime

import streamlit as st

from services.supabase_client import get_supabase_client, current_user
from ui.components import section_header, alert, divider, kpi_row
from ._shared import (
    TABLE_RUTAS,
    TIPOS_RUTA,
    TIPOS_CON_MX,
    DEFAULTS,
    cargar_datos_generales,
    guardar_datos_generales,
    limpiar_fila_json,
    safe,
    calcular_ruta_setlogis,
    tiene_mx,
    direccion_label,
)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def normalizar(texto: str) -> str:
    if not texto:
        return ""
    texto = str(texto).upper().strip()
    texto = re.sub(r"\s+", " ", texto)
    texto = re.sub(r"\s*,\s*", ", ", texto)
    return texto


def _get_profile_name(user_id: str) -> str | None:
    sb = get_supabase_client()
    if sb is None or not user_id:
        return None
    try:
        res = sb.table("profiles").select("full_name").eq("id", user_id).maybe_single().execute()
        return (res.data or {}).get("full_name")
    except Exception:
        return None


def _generar_id(supabase) -> str:
    try:
        resp = supabase.table(TABLE_RUTAS).select("ID_Ruta").order("ID_Ruta", desc=True).limit(1).execute()
        if resp.data:
            ultimo = str(resp.data[0].get("ID_Ruta", "SL000000"))
            num = int(re.sub(r"\D", "", ultimo)[-6:]) + 1
        else:
            num = 1
        return f"SL{num:06d}"
    except Exception:
        import time
        return f"SL{int(time.time()) % 1000000:06d}"


# ─────────────────────────────────────────────
# PANEL DATOS GENERALES
# ─────────────────────────────────────────────
def _panel_datos_generales(valores: dict) -> dict:
    with st.expander("⚙️ Configuración de Parámetros", expanded=False):

        section_header("🚗", "Tarifas Owner Individual (USD/milla)")
        c1, c2, c3 = st.columns(3)
        valores["PxM Owner Subidas"] = c1.number_input(
            "PxM Subidas", value=float(valores.get("PxM Owner Subidas", 1.60)),
            step=0.01, format="%.2f", key="sl_pxm_sub"
        )
        valores["PxM Owner Bajadas"] = c2.number_input(
            "PxM Bajadas", value=float(valores.get("PxM Owner Bajadas", 1.40)),
            step=0.01, format="%.2f", key="sl_pxm_baj"
        )
        valores["PxM Owner Vacio"] = c3.number_input(
            "PxM Vacío", value=float(valores.get("PxM Owner Vacio", 0.80)),
            step=0.01, format="%.2f", key="sl_pxm_vac"
        )

        section_header("👥", "Tarifas Owner Team (USD/milla)")
        t1, t2, t3 = st.columns(3)
        valores["PxM Owner Subidas Team"] = t1.number_input(
            "PxM Subidas Team", value=float(valores.get("PxM Owner Subidas Team", 1.80)),
            step=0.01, format="%.2f", key="sl_pxm_sub_team"
        )
        valores["PxM Owner Bajadas Team"] = t2.number_input(
            "PxM Bajadas Team", value=float(valores.get("PxM Owner Bajadas Team", 1.60)),
            step=0.01, format="%.2f", key="sl_pxm_baj_team"
        )
        valores["PxM Owner Vacio Team"] = t3.number_input(
            "PxM Vacío Team", value=float(valores.get("PxM Owner Vacio Team", 0.90)),
            step=0.01, format="%.2f", key="sl_pxm_vac_team"
        )

        section_header("🛂", "Cruce Propio (USD)")
        cr1, cr2 = st.columns(2)
        valores["Cruce Propio Cargado"] = cr1.number_input(
            "Cruce Propio Cargado", value=float(valores.get("Cruce Propio Cargado", 80.00)),
            step=1.0, format="%.2f", key="sl_cruce_c"
        )
        valores["Cruce Propio Vacio"] = cr2.number_input(
            "Cruce Propio Vacío", value=float(valores.get("Cruce Propio Vacio", 50.00)),
            step=1.0, format="%.2f", key="sl_cruce_v"
        )

        section_header("💹", "Tipo de Cambio y Costos Indirectos")
        x1, x2, x3 = st.columns(3)
        valores["Tipo de Cambio USD/MXP"] = x1.number_input(
            "TC USD/MXP", value=float(valores.get("Tipo de Cambio USD/MXP", 18.50)),
            step=0.05, format="%.2f", key="sl_tc"
        )
        valores["CXM Indirecto"] = x2.number_input(
            "CXM Indirecto ($/mi)", value=float(valores.get("CXM Indirecto", 0.10)),
            step=0.01, format="%.3f", key="sl_cxm_ind"
        )
        valores["% Costo Indirecto"] = x3.number_input(
            "% Costo Indirecto", value=float(valores.get("% Costo Indirecto", 0.09)),
            min_value=0.0, max_value=1.0, step=0.005, format="%.3f", key="sl_pct_ind"
        )

        if st.button("💾 Guardar Parámetros", key="sl_save_params"):
            guardar_datos_generales(valores)
            alert("success", "✅ Parámetros guardados correctamente.")

    return valores


# ─────────────────────────────────────────────
# RESUMEN DE RESULTADOS
# ─────────────────────────────────────────────
def _mostrar_resumen(r: dict) -> None:
    divider()
    section_header("📊", "Resultado de la Ruta")

    # KPIs principales
    kpi_row([
        {
            "icono": "💵",
            "label": "Ingreso Global",
            "valor": f"${r['Ingreso_Global']:,.2f}",
            "sub":   "USD total",
            "color": "#1B2266",
        },
        {
            "icono": "🚛",
            "label": "Pago Owner",
            "valor": f"${r['Pago_Owner_Total']:,.2f}",
            "sub":   f"${r['PxM_Cargado']:.2f}/mi cargado · ${r['PxM_Vacio']:.2f}/mi vacío",
            "color": "#0369a1",
        },
        {
            "icono": "📈",
            "label": "Utilidad Bruta",
            "valor": f"${r['Utilidad_Bruta']:,.2f}",
            "sub":   f"{r['Pct_Ut_Bruta']:.1f}% del ingreso",
            "color": "#16a34a" if r["Utilidad_Bruta"] >= 0 else "#dc2626",
        },
        {
            "icono": "🏆",
            "label": "Utilidad Neta",
            "valor": f"${r['Utilidad_Neta']:,.2f}",
            "sub":   f"{r['Pct_Ut_Neta']:.1f}% del ingreso",
            "color": r["Color_Ut_Neta"],
        },
    ])

    # Detalle por secciones
    with st.expander("📋 Detalle completo del cálculo", expanded=True):

        # Ingresos
        section_header("💰", "Ingresos")
        ia, ib, ic, id_ = st.columns(4)
        ia.metric("Flete USA",    f"${r['Flete_USA']:,.2f}")
        ib.metric("Fuel",         f"${r['Fuel']:,.2f}")
        ic.metric("Flete + Fuel", f"${r['Flete_Fuel']:,.2f}")
        id_.metric("Cruce",       f"${r['Ingreso_Cruce']:,.2f}")

        if r["Ingreso_MX"] > 0:
            _, _, _, mx_ = st.columns(4)
            mx_.metric("Ingreso MX", f"${r['Ingreso_MX']:,.2f}")

        divider()

        # Millas
        section_header("🛣️", "Millas")
        ma, mb, mc, md = st.columns(4)
        ma.metric("Miles Load",    f"{r['Miles_Load']:,.0f}")
        mb.metric("Short Miles",   f"{r['Short_Miles']:,.0f}")
        mc.metric("Miles Empty",   f"{r['Miles_Empty']:,.0f}")
        md.metric("Total Millas",  f"{r['Millas_Totales']:,.0f}")

        divider()

        # Costos
        section_header("📉", "Costos Directos")
        ca, cb, cc, cd = st.columns(4)
        ca.metric("Owner Cargado",  f"${r['Pago_Owner_Cargado']:,.2f}")
        cb.metric("Owner Vacío",    f"${r['Pago_Owner_Vacio']:,.2f}")
        cc.metric("Cruce",          f"${r['Costo_Cruce']:,.2f}")
        if r["Costo_MX"] > 0:
            cd.metric("Ruta MX",    f"${r['Costo_MX']:,.2f}")

        # Semáforo directos
        pct_dir_txt = f"{r['Pct_Costo_Directo']:.1f}% del ingreso (límite 85%)"
        if r["Color_Directo"] == "#16a34a":
            st.success(f"✅ Costos Directos: {pct_dir_txt}")
        else:
            st.error(f"🔴 Costos Directos: {pct_dir_txt} — EXCEDE EL LÍMITE")

        divider()
        section_header("📉", "Costos Indirectos")
        ci_a, ci_b = st.columns(2)
        ci_a.metric("Costo Indirecto", f"${r['Costo_Indirecto']:,.2f}")
        ci_b.metric("CXM aplicado",    f"${r['CXM_Indirecto']:.3f}/mi")

        pct_ind_txt = f"{r['Pct_Costo_Indirecto']:.1f}% del ingreso (límite 9%)"
        if r["Color_Indirecto"] == "#16a34a":
            st.success(f"✅ Costos Indirectos: {pct_ind_txt}")
        else:
            st.error(f"🔴 Costos Indirectos: {pct_ind_txt} — EXCEDE EL LÍMITE")

        divider()
        section_header("🏁", "Resumen Final")
        rf_a, rf_b, rf_c = st.columns(3)
        rf_a.metric("Costo Total",     f"${r['Costo_Total']:,.2f}")
        rf_b.metric("Utilidad Bruta",  f"${r['Utilidad_Bruta']:,.2f}",
                    delta=f"{r['Pct_Ut_Bruta']:.1f}%")
        rf_c.metric("Utilidad Neta",   f"${r['Utilidad_Neta']:,.2f}",
                    delta=f"{r['Pct_Ut_Neta']:.1f}%",
                    delta_color="normal" if r["Utilidad_Neta"] >= 0 else "inverse")

        pct_n_txt = f"{r['Pct_Ut_Neta']:.1f}% del ingreso (mínimo 6%)"
        if r["Color_Ut_Neta"] == "#16a34a":
            st.success(f"✅ Utilidad Neta: {pct_n_txt}")
        else:
            st.error(f"🔴 Utilidad Neta: {pct_n_txt} — POR DEBAJO DEL MÍNIMO")


# ─────────────────────────────────────────────
# RENDER PRINCIPAL
# ─────────────────────────────────────────────
def render() -> None:
    supabase = get_supabase_client()
    if supabase is None:
        alert("error", "⚠️ Supabase no configurado. Verifica tu conexión.")
        return

    u            = current_user() or {}
    user_id      = u.get("id") or u.get("sub") or ""
    nombre_usuario = _get_profile_name(user_id) or u.get("email") or "Desconocido"

    st.session_state.setdefault("sl_resultado", None)

    # Parámetros
    valores = cargar_datos_generales()
    valores = _panel_datos_generales(valores)

    divider()
    section_header("🛣️", "Nueva Ruta")

    with st.form("sl_captura_ruta", clear_on_submit=False):

        # ── Información General ───────────────────────────────────────────────
        st.markdown("### 📋 Información General")
        g1, g2, g3, g4 = st.columns(4)
        with g1:
            fecha = st.date_input("📅 Fecha", value=datetime.today(), key="sl_fecha")
        with g2:
            tipo_ruta = st.selectbox("🗺️ Tipo", TIPOS_RUTA, key="sl_tipo")
        with g3:
            modo = st.selectbox("🚛 Modo", ["Sencillo", "Team"], key="sl_modo")
        with g4:
            cliente = st.text_input(
                "👤 Cliente",
                key="sl_cliente",
                placeholder="NOMBRE DEL CLIENTE",
                disabled=(tipo_ruta == "Empty"),
            )

        # Info derivada (solo lectura)
        st.caption(
            f"📌 Dirección derivada: **{direccion_label(tipo_ruta)}**  ·  "
            f"Tramo MX: **{'Sí' if tiene_mx(tipo_ruta) else 'No'}**"
        )

        # ── Ruta Americana ────────────────────────────────────────────────────
        divider()
        st.markdown("### 🇺🇸 Ruta Americana")

        usa1, usa2 = st.columns(2)
        with usa1:
            origen_usa  = st.text_input("📍 Origen",  key="sl_ori",  placeholder="CIUDAD, ESTADO")
            destino_usa = st.text_input("📍 Destino", key="sl_dest", placeholder="CIUDAD, ESTADO")
            miles_load  = st.number_input("🛣️ Miles Load (cargadas)",  min_value=0.0, step=10.0, key="sl_ml")
            short_miles = st.number_input("🔀 Short Miles",            min_value=0.0, step=1.0,  key="sl_sm")
            miles_empty = st.number_input("⚪ Miles Empty (vacías)",   min_value=0.0, step=10.0, key="sl_me")

        with usa2:
            es_empty = tipo_ruta == "Empty"
            flete_usa = st.number_input(
                "💵 Flete USA (USD)", min_value=0.0, step=50.0, key="sl_flete",
                disabled=es_empty,
            )
            fuel = st.number_input(
                "⛽ Fuel Surcharge (USD)", min_value=0.0, step=10.0, key="sl_fuel",
                disabled=es_empty,
            )

        # ── Cruce ─────────────────────────────────────────────────────────────
        divider()
        st.markdown("### 🛂 Cruce Fronterizo")

        cr1, cr2, cr3 = st.columns(3)
        with cr1:
            tipo_cruce = st.selectbox(
                "Tipo de Cruce", ["Propio", "Externo"], key="sl_tcruce",
                disabled=es_empty,
            )
        with cr2:
            ingreso_cruce = st.number_input(
                "💵 Ingreso Cruce (USD)", min_value=0.0, step=10.0, key="sl_ing_cruce",
                disabled=es_empty,
            )
        with cr3:
            costo_cruce_ext = st.number_input(
                "💸 Costo Cruce Externo (USD)",
                min_value=0.0, step=10.0, key="sl_costo_cruce",
                disabled=(tipo_cruce == "Propio" or es_empty),
                help="Solo aplica si el cruce es Externo. Si es Propio se toma de la configuración.",
            )

        if tipo_cruce == "Propio" and not es_empty:
            costo_cruce_cfg = safe(valores.get("Cruce Propio Cargado", 80.0))
            st.caption(f"ℹ️ Costo cruce propio configurado: **${costo_cruce_cfg:,.2f} USD**")

        # ── Ruta MX (solo D2D) ────────────────────────────────────────────────
        aplica_mx = tiene_mx(tipo_ruta)
        if aplica_mx:
            divider()
            st.markdown("### 🇲🇽 Ruta México (Externo)")
            mx1, mx2 = st.columns(2)
            with mx1:
                ingreso_mx = st.number_input(
                    "💵 Ingreso Ruta MX (USD)", min_value=0.0, step=50.0, key="sl_ing_mx"
                )
            with mx2:
                costo_mx = st.number_input(
                    "💸 Costo Ruta MX (USD)", min_value=0.0, step=50.0, key="sl_costo_mx"
                )
        else:
            ingreso_mx = 0.0
            costo_mx   = 0.0

        # ── Costo Indirecto ───────────────────────────────────────────────────
        divider()
        st.markdown("### 📉 Costo Indirecto")
        ci1, _ = st.columns([1, 2])
        with ci1:
            modo_ci = st.radio(
                "Método", ["CXM", "Porcentaje"],
                horizontal=True, key="sl_modo_ci",
            )
        st.caption(
            f"CXM configurado: **${safe(valores.get('CXM Indirecto', 0.10)):.3f}/mi**  ·  "
            f"% configurado: **{safe(valores.get('% Costo Indirecto', 0.09))*100:.1f}%**"
        )

        # ── Botón calcular ────────────────────────────────────────────────────
        divider()
        calcular = st.form_submit_button(
            "🧮 Calcular Ruta", type="primary", use_container_width=True
        )

    # ── Lógica post-form ──────────────────────────────────────────────────────
    if calcular:
        errores = []

        ruta_usa = f"{normalizar(origen_usa)} - {normalizar(destino_usa)}"
        if not origen_usa.strip() or not destino_usa.strip():
            errores.append("⚠️ Ingresa origen y destino de la ruta USA.")
        if tipo_ruta != "Empty" and not cliente.strip():
            errores.append("⚠️ Ingresa el cliente.")
        if tipo_ruta != "Empty" and miles_load <= 0 and short_miles <= 0:
            errores.append("⚠️ Ingresa al menos Miles Load o Short Miles.")
        if tipo_ruta == "Empty" and miles_empty <= 0:
            errores.append("⚠️ Las rutas Empty requieren Miles Empty.")

        if errores:
            for e in errores:
                st.error(e)
        else:
            resultado = calcular_ruta_setlogis(
                tipo_ruta            = tipo_ruta,
                modo                 = modo,
                ruta_usa             = ruta_usa,
                cliente              = normalizar(cliente),
                miles_load           = miles_load,
                miles_empty          = miles_empty,
                short_miles          = short_miles,
                flete_usa            = flete_usa,
                fuel                 = fuel,
                tipo_cruce           = tipo_cruce,
                ingreso_cruce        = ingreso_cruce,
                costo_cruce_externo  = costo_cruce_ext,
                ingreso_mx           = ingreso_mx,
                costo_mx             = costo_mx,
                modo_costo_indirecto = modo_ci,
                valores              = valores,
            )

            id_ruta = _generar_id(supabase)

            st.session_state["sl_resultado"] = resultado
            st.session_state["sl_datos"] = {
                "id_ruta":  id_ruta,
                "fecha":    str(fecha),
                "usuario":  nombre_usuario,
            }
            alert("success", "✅ Ruta calculada correctamente.")

    # ── Mostrar resultado ─────────────────────────────────────────────────────
    if st.session_state.get("sl_resultado"):
        _mostrar_resumen(st.session_state["sl_resultado"])

        divider()
        if st.button("💾 Guardar en Base de Datos", key="sl_guardar", type="primary", use_container_width=True):
            try:
                r    = st.session_state["sl_resultado"]
                d    = st.session_state["sl_datos"]

                fila = {
                    "ID_Ruta":             d["id_ruta"],
                    "Fecha":               d["fecha"],
                    "Usuario":             d["usuario"],
                    "Tipo_Viaje":          r["Tipo_Viaje"],
                    "Modo":                r["Modo"],
                    "Direccion":           r["Direccion"],
                    "Cliente":             r["Cliente"],
                    "Ruta_USA":            r["Ruta_USA"],
                    # Millas
                    "Miles_Load":          r["Miles_Load"],
                    "Miles_Empty":         r["Miles_Empty"],
                    "Short_Miles":         r["Short_Miles"],
                    "Millas_Totales":      r["Millas_Totales"],
                    # Ingresos
                    "Flete_USA":           r["Flete_USA"],
                    "Fuel":                r["Fuel"],
                    "Flete_Fuel":          r["Flete_Fuel"],
                    "Ingreso_Cruce":       r["Ingreso_Cruce"],
                    "Tipo_Cruce":          r["Tipo_Cruce"],
                    "Ingreso_MX":          r["Ingreso_MX"],
                    "Ingreso_Global":      r["Ingreso_Global"],
                    # Tarifas
                    "PxM_Cargado":         r["PxM_Cargado"],
                    "PxM_Vacio":           r["PxM_Vacio"],
                    # Costos owner
                    "Pago_Owner_Cargado":  r["Pago_Owner_Cargado"],
                    "Pago_Owner_Vacio":    r["Pago_Owner_Vacio"],
                    "Pago_Owner_Total":    r["Pago_Owner_Total"],
                    # Cruce y MX
                    "Costo_Cruce":         r["Costo_Cruce"],
                    "Costo_MX":            r["Costo_MX"],
                    # Costos agrupados
                    "Costo_Directo":       r["Costo_Directo"],
                    "Costo_Indirecto":     r["Costo_Indirecto"],
                    "Costo_Total":         r["Costo_Total"],
                    # Utilidades
                    "Utilidad_Bruta":      r["Utilidad_Bruta"],
                    "Utilidad_Neta":       r["Utilidad_Neta"],
                    # Porcentajes
                    "Pct_Costo_Directo":   r["Pct_Costo_Directo"],
                    "Pct_Costo_Indirecto": r["Pct_Costo_Indirecto"],
                    "Pct_Ut_Bruta":        r["Pct_Ut_Bruta"],
                    "Pct_Ut_Neta":         r["Pct_Ut_Neta"],
                }

                fila_limpia = limpiar_fila_json(fila)
                supabase.table(TABLE_RUTAS).insert(fila_limpia).execute()

                alert("success", f"✅ Ruta **{d['id_ruta']}** guardada correctamente.")
                st.session_state["sl_resultado"] = None
                st.session_state["sl_datos"]     = {}

            except Exception as ex:
                alert("error", f"❌ Error al guardar: {ex}")
