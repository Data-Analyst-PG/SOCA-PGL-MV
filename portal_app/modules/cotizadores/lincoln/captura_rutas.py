"""
captura_rutas.py – Lincoln Freight (USA/MX)
Estructura de formulario idéntica a Set Logis Plus.
Diferencias exclusivas de Lincoln:
  - Parámetros: CXM operador, diesel, MPG, ISR/IMSS, bono (en lugar de PxM owner)
  - Empty: sección americana visible pero sin tarifa al cliente
  - Cálculo: llama calcular_ruta_lincoln del _shared.py
"""

from __future__ import annotations

from datetime import datetime, timezone

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
    guardar_datos_generales,
    limpiar_fila_json,
    safe,
    calcular_ruta_lincoln,
    obtener_config_tipo_ruta,
    tiene_mx,
    normalizar,
    a_usd,
    get_profile_name,
    generar_id_ruta,
)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────
# PANEL DATOS GENERALES  (Lincoln-specific)
# ─────────────────────────────────────────────
def _panel_datos_generales(valores: dict) -> dict:
    with st.expander("⚙️ Configuración de Parámetros", expanded=False):

        st.markdown("**Operador Sencillo (USD/milla)**")
        c1, c2 = st.columns(2)
        valores["CXM Operador USA"] = c1.number_input(
            "Cargado", value=float(valores.get("CXM Operador USA", 0.48)),
            step=0.01, format="%.2f", key="ln_cxm_carg")
        valores["CXM Operador USA (Empty)"] = c2.number_input(
            "Vacío", value=float(valores.get("CXM Operador USA (Empty)", 0.30)),
            step=0.01, format="%.2f", key="ln_cxm_vac")

        st.markdown("**Operador Team (USD/milla × operador)**")
        t1, t2 = st.columns(2)
        valores["CXM Team USA"] = t1.number_input(
            "Team Cargado", value=float(valores.get("CXM Team USA", 0.30)),
            step=0.01, format="%.2f", key="ln_cxm_team_carg")
        valores["CXM Team USA (Empty)"] = t2.number_input(
            "Team Vacío", value=float(valores.get("CXM Team USA (Empty)", 0.25)),
            step=0.01, format="%.2f", key="ln_cxm_team_vac")

        st.markdown("**Diesel**")
        d1, d2 = st.columns(2)
        valores["Truck Performance (mpg)"] = d1.number_input(
            "Rendimiento (mpg)", value=float(valores.get("Truck Performance (mpg)", 7.0)),
            step=0.1, format="%.1f", key="ln_mpg")
        valores["Diesel Price ($/gal)"] = d2.number_input(
            "Diesel ($/gal)", value=float(valores.get("Diesel Price ($/gal)", 3.60)),
            step=0.01, format="%.2f", key="ln_diesel")

        st.markdown("**Cruce Propio (USD)**")
        cr1, cr2 = st.columns(2)
        valores["Cruce Propio (Cargado)"] = cr1.number_input(
            "Cargado", value=float(valores.get("Cruce Propio (Cargado)", 50.0)),
            step=1.0, format="%.2f", key="ln_cruce_carg")
        valores["Cruce Propio (Vacío)"] = cr2.number_input(
            "Vacío", value=float(valores.get("Cruce Propio (Vacío)", 30.0)),
            step=1.0, format="%.2f", key="ln_cruce_vac")

        st.markdown("**Prestaciones y Bonos**")
        p1, p2 = st.columns(2)
        valores["ISR/IMSS"] = p1.number_input(
            "ISR/IMSS (USD/viaje)", value=float(valores.get("ISR/IMSS", 462.66)),
            step=1.0, format="%.2f", key="ln_isr")
        valores["Bono por milla cargada"] = p2.number_input(
            "Bono/milla cargada (USD)", value=float(valores.get("Bono por milla cargada", 0.01)),
            step=0.001, format="%.3f", key="ln_bono")

        st.markdown("**Costo Indirecto y Tipo de Cambio**")
        i1, i2 = st.columns(2)
        pct_raw = float(valores.get("% Costo Indirecto", 0.42))
        pct_display = pct_raw if pct_raw <= 1.0 else pct_raw / 100
        valores["% Costo Indirecto"] = i1.number_input(
            "% Costo Indirecto (ej. 0.42)", value=pct_display,
            step=0.01, format="%.2f", key="ln_pct_ind")
        valores["Tipo de Cambio USD/MXP"] = i2.number_input(
            "Tipo de Cambio USD/MXP", value=float(valores.get("Tipo de Cambio USD/MXP", 18.50)),
            step=0.1, format="%.2f", key="ln_tc")

        if st.button("💾 Guardar parámetros", key="ln_guardar_params"):
            guardar_datos_generales(valores)
            st.success("Parámetros guardados.")

    return valores


# ─────────────────────────────────────────────
# MOSTRAR RESULTADOS
# ─────────────────────────────────────────────
def _mostrar_resultados(r: dict, fd: dict) -> None:
    divider()
    section_header("📊", "Resultado del Cálculo")

    kpi_row([
        ("💰 Ingreso Total",     f"${r['ingreso_total']:,.2f}",      None),
        ("💸 Costo Directo",     f"${r['costo_directo_total']:,.2f}", None),
        ("📈 Utilidad Bruta",    f"${r['utilidad_bruta']:,.2f}",     f"{r['pct_bruta']:.1f}%"),
        ("📉 Costos Indirectos", f"${r['costos_ind']:,.2f}",          None),
        ("✅ Utilidad Neta",     f"${r['utilidad_neta']:,.2f}",       f"{r['pct_neta']:.1f}%"),
    ])

    semaforos_ruta(r)

    tipo_ruta  = fd.get("tipo_ruta", "NB")
    es_empty   = (tipo_ruta == "Empty")
    millas_usa = fd.get("millas_usa", 0.0)
    millas_vac = fd.get("millas_vacias", 0.0)

    if es_empty:
        filas_costo = [
            (f"Operador Vacío ({millas_vac:.0f} mi × ${r['cxm_vacio']:.4f})", r["sueldo_base"]),
            ("Diesel (millas vacías)", r["diesel_usa"]),
        ]
    else:
        filas_costo = [
            (f"Sueldo Base ({millas_usa:.0f} mi carg + {millas_vac:.0f} mi vac)", r["sueldo_base"]),
            ("Bono por millas cargadas",  r["bono_millas"]),
            ("Diesel (cargado + vacío)",  r["diesel_usa"]),
            ("ISR/IMSS",                  r["isr_imss"]),
        ]
        if r.get("otros_cargos_costo", 0) > 0:
            filas_costo.append(("Otros Cargos (pagados por Lincoln)", r["otros_cargos_costo"]))

    modalidad = fd.get("modalidad", "Flat")
    cxm_flete = fd.get("cxm_flete", 0.0)
    cxm_fuel  = fd.get("cxm_fuel",  0.0)

    desglose_ruta(
        r,
        filas_costo_americana=filas_costo,
        modalidad=modalidad,
        cxm_flete=cxm_flete,
        cxm_fuel=cxm_fuel,
    )


# ─────────────────────────────────────────────
# GUARDAR EN SUPABASE
# ─────────────────────────────────────────────
def _guardar_ruta(r: dict, fd: dict, id_ruta: str, user_id: str, nombre_usuario: str) -> None:
    supabase = get_supabase_client()
    if supabase is None:
        alert("error", "No se pudo conectar a Supabase.")
        return

    tc  = r.get("tc", 18.5)
    now = _now_iso()

    fila = {
        "ID_Ruta":              id_ruta,
        "Fecha":                fd["fecha"],
        "Tipo":                 fd["tipo_ruta"],
        "Cliente":              fd["cliente"],
        "Modo_Viaje":           fd["modo_viaje"],
        "Origen":               fd["origen_usa"],
        "Destino":              fd["destino_usa"],
        "Millas_USA":           fd["millas_usa"],
        "Millas_Vacias":        fd["millas_vacias"],
        "Moneda_USA":           fd.get("moneda_usa", "USD"),
        "Modalidad":            fd.get("modalidad", "Flat"),
        "CXM_Flete":            fd.get("cxm_flete", 0.0),
        "CXM_Fuel":             fd.get("cxm_fuel", 0.0),
        "Tarifa_Flat":          fd.get("tarifa_flat", 0.0),
        "Ingreso_Flete_USA":    r["ingreso_flete_usa"],
        "Ingreso_Fuel_USA":     r["ingreso_fuel_usa"],
        "Aplica_Cruce":         fd.get("aplica_cruce", False),
        "Tipo_Cruce":           fd.get("tipo_cruce", ""),
        "Tipo_Carga_Cruce":     fd.get("tipo_carga", ""),
        "Moneda_Cruce":         fd.get("moneda_cruce", "USD"),
        "Ingreso_Cruce":        r["ingreso_cruce"],
        "Costo_Cruce":          r["costo_cruce"],
        "Linea_MX":             fd.get("linea_mx", ""),
        "Origen_MX":            fd.get("origen_mx", ""),
        "Destino_MX":           fd.get("destino_mx", ""),
        "Moneda_MX":            fd.get("moneda_mx", "MXP"),
        "Ingreso_MX_MXP":       fd.get("ingreso_mx_mxp", 0.0),
        "Costo_MX_MXP":         fd.get("costo_mx_mxp", 0.0),
        "Ingreso_MX_USD":       r["ingreso_mx_usd"],
        "Costo_MX_USD":         r["costo_mx_usd"],
        "Otros_Cargos_JSON":    str(fd.get("otros_cargos", {})),
        "Otros_Cargos_Ingreso": r["otros_cargos_ingreso"],
        "Otros_Cargos_Costo":   r["otros_cargos_costo"],
        "Sueldo_Base":          r["sueldo_base"],
        "Bono_Millas":          r["bono_millas"],
        "Sueldo_Operador":      r["sueldo_usa"],
        "Diesel_USA":           r["diesel_usa"],
        "ISR_IMSS":             r["isr_imss"],
        "Costo_Directo":        r["costo_directo"],
        "Costo_Directo_Total":  r["costo_directo_total"],
        "Ingreso_Total":        r["ingreso_total"],
        "Utilidad_Bruta":       r["utilidad_bruta"],
        "Pct_Utilidad_Bruta":   r["pct_bruta"],
        "Costos_Indirectos":    r["costos_ind"],
        "Utilidad_Neta":        r["utilidad_neta"],
        "Pct_Utilidad_Neta":    r["pct_neta"],
        "Tipo_Cambio":          tc,
        "Capturado_Por":        nombre_usuario,
        "User_ID":              user_id,
        "created_at":           now,
        "updated_at":           now,
    }

    try:
        supabase.table(TABLE_RUTAS).insert(limpiar_fila_json(fila)).execute()
        st.success(f"✅ Ruta **{id_ruta}** guardada correctamente.")
        st.session_state.pop("ln_resultado", None)
        st.session_state.pop("ln_form_data", None)
    except Exception as e:
        alert("error", f"Error al guardar: {e}")


# ─────────────────────────────────────────────
# RENDER PRINCIPAL
# ─────────────────────────────────────────────
def render() -> None:
    supabase = get_supabase_client()
    if supabase is None:
        alert("error", "Supabase no configurado.")
        return

    u              = current_user() or {}
    user_id        = u.get("id") or u.get("sub") or ""
    nombre_usuario = get_profile_name(user_id) or u.get("email") or "Desconocido"

    st.session_state.setdefault("ln_resultado", None)
    st.session_state.setdefault("ln_form_data", {})

    valores = cargar_datos_generales()
    valores = _panel_datos_generales(valores)

    divider()
    section_header("🛣️", "Nueva Ruta")

    with st.form("ln_captura_ruta", clear_on_submit=False):

        # ── 1. Información general ────────────────────────────────────────────
        st.markdown("**Información General**")
        g1, g2, g3, g4 = st.columns(4)
        fecha      = g1.date_input("Fecha", value=datetime.today(), key="ln_fecha")
        tipo_ruta  = g2.selectbox("Tipo de Ruta", TIPOS_RUTA, key="ln_tipo")
        cliente    = g3.text_input("Cliente", key="ln_cliente")
        modo_viaje = g4.selectbox("Modo", ["Sencillo", "Team"], key="ln_modo")

        config   = obtener_config_tipo_ruta(tipo_ruta)
        es_empty = (tipo_ruta == "Empty")

        # ── 2. Ruta Americana ─────────────────────────────────────────────────
        divider()
        st.markdown("**Ruta Americana**")
        ru1, ru2 = st.columns(2)

        with ru1:
            origen_usa    = st.text_input("Origen USA",  key="ln_ori_usa")
            destino_usa   = st.text_input("Destino USA", key="ln_dest_usa")
            millas_usa    = st.number_input(
                "Millas Cargadas",
                min_value=0.0, step=10.0, key="ln_mi_usa",
                help="En rutas Empty este campo se ignora en el cálculo." if es_empty else None,
            )
            millas_vacias = st.number_input("Millas Vacías", min_value=0.0, step=10.0, key="ln_mi_vac")

        with ru2:
            moneda_usa = st.selectbox("Moneda", ["USD", "MXP"], key="ln_moneda_usa")
            modalidad  = st.selectbox("Modalidad", ["Desglosada", "Flat"], key="ln_modalidad")

            if es_empty:
                # En Empty no hay tarifa al cliente — se muestra aviso, campos en 0
                st.info("ℹ️ **Empty:** sin tarifa al cliente. Solo costos de reposicionamiento.")
                cxm_flete   = 0.0
                cxm_fuel    = 0.0
                tarifa_flat = 0.0
            elif modalidad == "Desglosada":
                cxm_flete   = st.number_input(
                    "CXM Flete ($/mi)",
                    value=float(valores.get("CXM Operador USA", 0.48)),
                    step=0.01, format="%.4f", key="ln_cxm_flete",
                )
                cxm_fuel    = st.number_input(
                    "Fuel Surcharge ($/mi)",
                    value=float(valores.get("Fuel Surcharge ($/mi)", 0.61)),
                    step=0.01, format="%.4f", key="ln_cxm_fuel",
                )
                tarifa_flat = 0.0
            else:
                tarifa_flat = st.number_input(
                    "Tarifa Flat (USD)", min_value=0.0, step=50.0, key="ln_tarifa_flat"
                )
                cxm_flete   = 0.0
                cxm_fuel    = 0.0

        # ── 3. Cruce Fronterizo ───────────────────────────────────────────────
        aplica_cruce     = False
        tipo_cruce       = ""
        tipo_carga       = ""
        moneda_cruce     = "USD"
        ingreso_cruce    = 0.0
        costo_cruce_terc = 0.0

        if not es_empty and config.get("cruce") in ("opcional", True):
            divider()
            st.markdown("**Cruce Fronterizo**")
            aplica_cruce = st.checkbox(
                "¿Aplica cruce?",
                value=(config["cruce"] is True),
                key="ln_aplica_cruce",
            )
            if aplica_cruce:
                cx1, cx2 = st.columns(2)
                tipo_cruce    = cx1.selectbox("Tipo de Cruce", ["Propio", "Tercero"], key="ln_tipo_cruce")
                tipo_carga    = cx1.selectbox("Carga", ["Cargado", "Vacío"], key="ln_tipo_carga")
                moneda_cruce  = cx2.selectbox("Moneda Cruce", ["USD", "MXP"], key="ln_moneda_cruce")
                ingreso_cruce = cx2.number_input("Ingreso Cruce", min_value=0.0, step=5.0, key="ln_ing_cruce")
                if tipo_cruce == "Tercero":
                    costo_cruce_terc = cx2.number_input(
                        "Costo Cruce Tercero", min_value=0.0, step=5.0, key="ln_costo_cruce_terc"
                    )

        # ── 4. Tramo México ───────────────────────────────────────────────────
        linea_mx     = ""
        origen_mx    = ""
        destino_mx   = ""
        moneda_mx    = "MXP"
        ingreso_mx   = 0.0
        costo_mx     = 0.0

        if config.get("parte_mx") and not es_empty:
            divider()
            st.markdown("**Tramo México**")
            mx1, mx2 = st.columns(2)
            linea_mx   = mx1.selectbox("Línea MX", ["Propia", "Tercero"], key="ln_linea_mx")
            origen_mx  = mx1.text_input("Origen MX",  key="ln_ori_mx")
            destino_mx = mx1.text_input("Destino MX", key="ln_dest_mx")
            moneda_mx  = mx2.selectbox("Moneda MX", ["MXP", "USD"], key="ln_moneda_mx")
            ingreso_mx = mx2.number_input("Ingreso Flete MX", min_value=0.0, step=100.0, key="ln_ing_mx")
            if linea_mx == "Tercero":
                costo_mx = mx2.number_input("Costo Flete MX", min_value=0.0, step=100.0, key="ln_costo_mx")

        # ── 5. Otros Cargos ───────────────────────────────────────────────────
        otros_cargos         = {}
        otros_cargos_pagados = {}

        if not es_empty:
            divider()
            st.markdown("**Otros Cargos (USD)**")
            st.caption("Captura el monto y marca si Lincoln lo pagó (se suma al costo directo).")
            cols3 = st.columns(3)
            for i, extra in enumerate(EXTRAS_USA):
                with cols3[i % 3]:
                    monto  = st.number_input(
                        extra, min_value=0.0, step=10.0, format="%.2f", key=f"ln_extra_{extra}"
                    )
                    pagado = st.checkbox("Lincoln pagó", key=f"ln_pagado_{extra}")
                    if monto > 0:
                        otros_cargos[extra]         = monto
                        otros_cargos_pagados[extra] = pagado

        # ── Submit ────────────────────────────────────────────────────────────
        divider()
        submitted = st.form_submit_button(
            "🔍 Calcular Ruta", type="primary", use_container_width=True
        )

    # ── Post-form: calcular ───────────────────────────────────────────────────
    if submitted:
        tc = float(valores.get("Tipo de Cambio USD/MXP", 18.5))

        # Ingreso por milla en USD
        if es_empty:
            ing_x_milla_usd = 0.0
            fuel_sc_usd     = 0.0
            ing_cruce_usd   = 0.0
        else:
            if modalidad == "Desglosada":
                ing_x_milla_usd = cxm_flete if moneda_usa == "USD" else a_usd(cxm_flete, tc)
                fuel_sc_usd     = cxm_fuel  if moneda_usa == "USD" else a_usd(cxm_fuel,  tc)
            else:
                # Flat: derivar CXM equivalente a partir del total y las millas cargadas
                flat_usd        = tarifa_flat if moneda_usa == "USD" else a_usd(tarifa_flat, tc)
                ing_x_milla_usd = flat_usd / millas_usa if millas_usa else 0.0
                fuel_sc_usd     = 0.0
            ing_cruce_usd = ingreso_cruce if moneda_cruce == "USD" else a_usd(ingreso_cruce, tc)

        # Tramo MX → siempre en MXP para el cálculo
        if config.get("parte_mx") and not es_empty:
            ing_mx_mxp   = ingreso_mx * tc if moneda_mx == "USD" else ingreso_mx
            costo_mx_mxp = costo_mx   * tc if moneda_mx == "USD" else costo_mx
            if linea_mx != "Tercero":
                costo_mx_mxp = 0.0
        else:
            ing_mx_mxp   = 0.0
            costo_mx_mxp = 0.0

        r = calcular_ruta_lincoln(
            tipo_ruta               = tipo_ruta,
            millas_usa              = millas_usa,
            millas_vacias           = millas_vacias,
            ingreso_x_milla_usd     = ing_x_milla_usd,
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
            otros_cargos_pagados    = otros_cargos_pagados,
            valores                 = valores,
        )

        st.session_state["ln_resultado"] = r
        st.session_state["ln_form_data"] = {
            "fecha":            str(fecha),
            "tipo_ruta":        tipo_ruta,
            "cliente":          normalizar(cliente),
            "modo_viaje":       modo_viaje,
            "origen_usa":       normalizar(origen_usa),
            "destino_usa":      normalizar(destino_usa),
            "millas_usa":       millas_usa,
            "millas_vacias":    millas_vacias,
            "moneda_usa":       moneda_usa,
            "modalidad":        modalidad,
            "cxm_flete":        cxm_flete,
            "cxm_fuel":         cxm_fuel,
            "tarifa_flat":      tarifa_flat,
            "aplica_cruce":     aplica_cruce,
            "tipo_cruce":       tipo_cruce,
            "tipo_carga":       tipo_carga,
            "moneda_cruce":     moneda_cruce,
            "ingreso_cruce":    ingreso_cruce,
            "costo_cruce_terc": costo_cruce_terc,
            "linea_mx":         linea_mx,
            "origen_mx":        normalizar(origen_mx),
            "destino_mx":       normalizar(destino_mx),
            "moneda_mx":        moneda_mx,
            "ingreso_mx":       ingreso_mx,
            "ingreso_mx_mxp":   ing_mx_mxp,
            "costo_mx":         costo_mx,
            "costo_mx_mxp":     costo_mx_mxp,
            "otros_cargos":          otros_cargos,
            "otros_cargos_pagados":  otros_cargos_pagados,
        }

    # ── Mostrar resultado + botón guardar (fuera del form) ────────────────────
    r  = st.session_state.get("ln_resultado")
    fd = st.session_state.get("ln_form_data", {})

    if r and fd:
        _mostrar_resultados(r, fd)

        divider()
        col_g, col_x = st.columns([2, 1])
        with col_g:
            if st.button(
                "💾 Guardar Ruta", type="primary",
                use_container_width=True, key="ln_guardar_ruta"
            ):
                id_ruta = generar_id_ruta()
                _guardar_ruta(r, fd, id_ruta, user_id, nombre_usuario)
        with col_x:
            if st.button("🗑️ Descartar", use_container_width=True, key="ln_descartar"):
                st.session_state.pop("ln_resultado", None)
                st.session_state.pop("ln_form_data", None)
                st.rerun()
