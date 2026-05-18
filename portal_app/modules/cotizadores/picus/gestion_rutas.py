from ui.components import section_header, alert, divider
import os
import pandas as pd
import streamlit as st
from datetime import datetime, timezone

from services.supabase_client import get_supabase_client, get_authed_client, current_user


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


# =========================
# Config local (mismo archivo que Captura/Consulta)
# =========================
DEFAULTS = {
    "Rendimiento Camion": 2.5,
    "Costo Diesel": 24.0,
    "Pago x KM (General)": 1.50,
    "Bono ISR IMSS RL": 462.66,
    "Bono ISR IMSS Tramo": 185.06,
    "Pago Vacio": 100.0,
    "Pago Tramo": 300.0,
    "Bono Rendimiento": 250.0,
    "Bono Modo Team": 650.0,
    "Tipo de cambio USD": 17.5,
    "Tipo de cambio MXP": 1.0,
}


def _datos_generales_path() -> str:
    base = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".data")
    base = os.path.abspath(base)
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "datos_generales_picus.csv")


def cargar_datos_generales() -> dict:
    path = _datos_generales_path()
    if os.path.exists(path):
        try:
            data = pd.read_csv(path).set_index("Parametro").to_dict()["Valor"]
            return {**DEFAULTS, **data}
        except Exception:
            return DEFAULTS.copy()
    return DEFAULTS.copy()


def guardar_datos_generales(valores: dict) -> None:
    path = _datos_generales_path()
    df = pd.DataFrame(valores.items(), columns=["Parametro", "Valor"])
    df.to_csv(path, index=False)


def safe_number(x):
    return 0 if (x is None or (isinstance(x, float) and pd.isna(x))) else x


@st.cache_data(show_spinner=False, ttl=120)
def _load_rutas_picus_cached():
    supabase = get_supabase_client()
    if supabase is None:
        return pd.DataFrame()
    resp = supabase.table("Rutas_Picus").select("*").execute()
    return pd.DataFrame(resp.data)


def render():
    st.title("🗂️ Gestión de Rutas Guardadas (Picus)")

    supabase = get_supabase_client()
    if supabase is None:
        alert("warn", "⚠️ Supabase no configurado. No se pueden cargar/editar/eliminar rutas.")
        return

    # Detectar usuario logueado
    u = current_user() or {}
    user_id = u.get("id") or u.get("sub") or ""
    nombre_usuario = _get_profile_name(user_id) or u.get("email") or "Desconocido"

    # ---- control recarga cache ----
    c1, c2 = st.columns([1, 3])
    with c1:
        if st.button("🔄 Recargar rutas", key="picus_gestion_reload"):
            _load_rutas_picus_cached.clear()
            st.rerun()
    with c2:
        st.caption("Carga cacheada 2 min para evitar lentitud. Usa 'Recargar' si acabas de guardar algo.")

    valores = cargar_datos_generales()
    df = _load_rutas_picus_cached()

    if df.empty:
        alert("warn", "⚠️ No hay rutas guardadas todavía.")
        return

    if "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.date

    # =========================
    # Tabla general
    # =========================
section_header("📋", "Rutas Registradas")
    st.dataframe(df, use_container_width=True)
    st.markdown(f"**Total de rutas registradas:** {len(df)}")

    ids_disponibles = df["ID_Ruta"].dropna().astype(str).tolist()

    divider()

    # =========================
    # Eliminar
    # =========================
section_header("🗑️", "Eliminar rutas")
    ids_a_eliminar = st.multiselect("Selecciona los ID de ruta a eliminar", ids_disponibles, key="picus_del_ids")

    if st.button("Eliminar rutas seleccionadas", key="picus_del_btn", disabled=(len(ids_a_eliminar) == 0)):
        try:
            for idr in ids_a_eliminar:
                supabase.table("Rutas_Picus").delete().eq("ID_Ruta", idr).execute()
            alert("success", "✅ Rutas eliminadas correctamente.")
            _load_rutas_picus_cached.clear()
            st.rerun()
        except Exception as e:
            st.error(f"❌ Error eliminando rutas: {e}")
            st.exception(e)

    divider()

    # =========================
    # Editar
    # =========================
section_header("✏️", "Editar Ruta Existente")

    id_editar = st.selectbox("Selecciona el ID de Ruta a editar", ids_disponibles, key="picus_edit_id")
    ruta = df[df["ID_Ruta"].astype(str) == str(id_editar)].iloc[0]

    # Mostrar quién creó / modificó la ruta
    if ruta.get("created_by"):
        st.caption(f"✏️ Creada por: **{ruta.get('created_by')}** el {str(ruta.get('created_at',''))[:10]}")
    if ruta.get("updated_by"):
        st.caption(f"🔄 Última modificación por: **{ruta.get('updated_by')}** el {str(ruta.get('updated_at',''))[:10]}")

    motivo_modificacion = st.text_input(
        "📝 Motivo de la modificación*",
        placeholder="Ej: Corrección de KM, cambio de cliente, ajuste de ingreso...",
        key="picus_motivo_mod",
    )

    # ---- Datos generales (expander) ----
    with st.expander("⚙️ Configurar Datos Generales (Picus)", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            rendimiento_camion = st.number_input("Rendimiento Camion", value=float(valores.get("Rendimiento Camion", 2.5)))
            pago_km = st.number_input("Pago x KM (General)", value=float(valores.get("Pago x KM (General)", 1.50)))
            bono_isr_tramo = st.number_input("Bono ISR IMSS Tramo", value=float(valores.get("Bono ISR IMSS Tramo", 185.06)))
            pago_tramo = st.number_input("Pago Tramo", value=float(valores.get("Pago Tramo", 300.0)))
            bono_team = st.number_input("Bono Modo Team", value=float(valores.get("Bono Modo Team", 650.0)))
            tipo_cambio_mxp = st.number_input("Tipo de cambio MXP", value=float(valores.get("Tipo de cambio MXP", 1.0)))
        with col2:
            costo_diesel = st.number_input("Costo Diesel", value=float(valores.get("Costo Diesel", 24.0)))
            bono_isr_rl = st.number_input("Bono ISR IMSS RL", value=float(valores.get("Bono ISR IMSS RL", 462.66)))
            pago_vacio = st.number_input("Pago Vacio", value=float(valores.get("Pago Vacio", 100.0)))
            bono_rendimiento = st.number_input("Bono Rendimiento", value=float(valores.get("Bono Rendimiento", 250.0)))
            tipo_cambio_usd = st.number_input("Tipo de cambio USD", value=float(valores.get("Tipo de cambio USD", 17.5)))

        if st.button("Guardar Datos Generales", key="picus_save_generales"):
            nuevos = {
                "Rendimiento Camion": rendimiento_camion,
                "Costo Diesel": costo_diesel,
                "Pago x KM (General)": pago_km,
                "Bono ISR IMSS RL": bono_isr_rl,
                "Bono ISR IMSS Tramo": bono_isr_tramo,
                "Pago Vacio": pago_vacio,
                "Pago Tramo": pago_tramo,
                "Bono Rendimiento": bono_rendimiento,
                "Bono Modo Team": bono_team,
                "Tipo de cambio USD": tipo_cambio_usd,
                "Tipo de cambio MXP": tipo_cambio_mxp,
            }
            guardar_datos_generales(nuevos)
            alert("success", "✅ Datos generales guardados correctamente.")
            st.caption(f"Archivo: `{_datos_generales_path()}`")

    divider()

    # ---- Form editar ruta ----
    with st.form("picus_editar_ruta_form"):
        col1, col2 = st.columns(2)

        with col1:
            fecha = st.date_input("Fecha", ruta.get("Fecha"))
            tipo = st.selectbox("Tipo", ["IMPORTACION", "EXPORTACION", "VACIO"],
                                index=["IMPORTACION", "EXPORTACION", "VACIO"].index(str(ruta.get("Tipo"))))
            ruta_tipo = st.selectbox("Ruta Tipo", ["Ruta Larga", "Tramo"],
                                     index=["Ruta Larga", "Tramo"].index(str(ruta.get("Ruta_Tipo"))))
            cliente = st.text_input("Cliente", value=str(ruta.get("Cliente", "")))
            origen = st.text_input("Origen", value=str(ruta.get("Origen", "")))
            destino = st.text_input("Destino", value=str(ruta.get("Destino", "")))
            modo_viaje = st.selectbox("Modo de Viaje", ["Operador", "Team"],
                                      index=["Operador", "Team"].index(str(ruta.get("Modo de Viaje"))))
            km = st.number_input("Kilómetros", min_value=0.0, value=float(safe_number(ruta.get("KM"))))
            moneda_ingreso = st.selectbox("Moneda Flete", ["MXP", "USD"],
                                          index=["MXP", "USD"].index(str(ruta.get("Moneda"))))
            ingreso_original = st.number_input("Ingreso Flete Original", min_value=0.0,
                                               value=float(safe_number(ruta.get("Ingreso_Original"))))

        with col2:
            moneda_cruce = st.selectbox("Moneda Cruce", ["MXP", "USD"],
                                        index=["MXP", "USD"].index(str(ruta.get("Moneda_Cruce"))))
            ingreso_cruce = st.number_input("Ingreso Cruce Original", min_value=0.0,
                                            value=float(safe_number(ruta.get("Cruce_Original"))))
            moneda_costo_cruce = st.selectbox("Moneda Costo Cruce", ["MXP", "USD"],
                                              index=["MXP", "USD"].index(str(ruta.get("Moneda Costo Cruce"))))
            costo_cruce = st.number_input("Costo Cruce", min_value=0.0,
                                          value=float(safe_number(ruta.get("Costo Cruce"))))

            movimiento_local = st.number_input("Movimiento Local (MXP)", min_value=0.0,
                                               value=float(safe_number(ruta.get("Movimiento_Local"))))
            puntualidad = st.number_input("Puntualidad (MXP)", min_value=0.0,
                                          value=float(safe_number(ruta.get("Puntualidad"))))
            pension = st.number_input("Pensión (MXP)", min_value=0.0,
                                      value=float(safe_number(ruta.get("Pension"))))
            estancia = st.number_input("Estancia (MXP)", min_value=0.0,
                                       value=float(safe_number(ruta.get("Estancia"))))
            fianza = st.number_input("Fianza (MXP)", min_value=0.0,
                                     value=float(safe_number(ruta.get("Fianza"))))
            casetas = st.number_input("Casetas (MXP)", min_value=0.0,
                                      value=float(safe_number(ruta.get("Casetas"))))

        divider()
    section_header("🧾", "Costos Extras")
        col3, col4 = st.columns(2)
        with col3:
            pistas_extra = st.number_input("Pistas Extra (MXP)", min_value=0.0,
                                           value=float(safe_number(ruta.get("Pistas_Extra"))))
            stop = st.number_input("Stop (MXP)", min_value=0.0,
                                   value=float(safe_number(ruta.get("Stop"))))
            falso = st.number_input("Falso (MXP)", min_value=0.0,
                                    value=float(safe_number(ruta.get("Falso"))))
            extras_cobrados = st.checkbox("✅ ¿Costos Extras fueron cobrados al cliente?",
                                          value=bool(ruta.get("Extras_Cobrados", False)))
        with col4:
            gatas = st.number_input("Gatas (MXP)", min_value=0.0,
                                    value=float(safe_number(ruta.get("Gatas"))))
            accesorios = st.number_input("Accesorios (MXP)", min_value=0.0,
                                         value=float(safe_number(ruta.get("Accesorios"))))
            guias = st.number_input("Guías (MXP)", min_value=0.0,
                                    value=float(safe_number(ruta.get("Guias"))))

        guardar = st.form_submit_button("💾 Guardar cambios")

    if guardar:
        if not motivo_modificacion.strip():
            alert("error", "⚠️ Debes indicar el motivo de la modificación antes de guardar.")
            st.stop()
        try:
            # Snapshot de datos anteriores para el historial
            campos_auditados = [
                "Tipo", "Ruta_Tipo", "Cliente", "Origen", "Destino", "KM", "Modo de Viaje",
                "Moneda", "Ingreso_Original", "Ingreso Flete", "Ingreso Total",
                "Moneda_Cruce", "Cruce_Original", "Ingreso Cruce",
                "Moneda Costo Cruce", "Costo Cruce", "Costo Cruce Convertido",
                "Pago por KM", "Sueldo_Operador", "Bono", "Casetas",
                "Movimiento_Local", "Puntualidad", "Pension", "Estancia", "Fianza",
                "Pistas_Extra", "Stop", "Falso", "Gatas", "Accesorios", "Guias",
                "Costo_Diesel_Camion", "Costo_Extras", "Costo_Total_Ruta",
                "Extras_Cobrados",
            ]
            datos_anteriores = {
                c: (ruta[c].item() if hasattr(ruta.get(c), "item") else ruta.get(c))
                for c in campos_auditados if c in ruta.index
            }

            historial_actual = ruta.get("historial") or []
            if not isinstance(historial_actual, list):
                historial_actual = []
            historial_actual.append({
                "at": _now_iso(),
                "by": nombre_usuario,
                "motivo": motivo_modificacion.strip(),
                "datos_anteriores": datos_anteriores,
            })

            # refrescar valores por si se editaron
            valores = cargar_datos_generales()

            tc_usd = float(valores.get("Tipo de cambio USD", 17.5))
            tc_mxp = float(valores.get("Tipo de cambio MXP", 1.0))

            tipo_cambio_flete = tc_usd if moneda_ingreso == "USD" else tc_mxp
            tipo_cambio_cruce = tc_usd if moneda_cruce == "USD" else tc_mxp
            tipo_cambio_costo_cruce = tc_usd if moneda_costo_cruce == "USD" else tc_mxp

            costo_diesel = float(valores.get("Costo Diesel", 24.0))
            rendimiento_camion = float(valores.get("Rendimiento Camion", 2.5))

            pago_km = float(valores.get("Pago x KM (General)", 1.63))
            bono_isr_rl = float(valores.get("Bono ISR IMSS RL", 462.66))
            bono_isr_tramo = float(valores.get("Bono ISR IMSS Tramo", 185.06))
            pago_vacio = float(valores.get("Pago Vacio", 100.0))
            pago_tramo = float(valores.get("Pago Tramo", 300.0))
            bono_rendimiento = float(valores.get("Bono Rendimiento", 250.0))
            bono_team = float(valores.get("Bono Modo Team", 650.0))

            costo_diesel_camion = (km / rendimiento_camion) * costo_diesel

            # --- sueldo/bono según ruta ---
            bono = 0.0
            sueldo = 0.0

            if ruta_tipo == "Tramo":
                sueldo = pago_tramo
                bono = bono_isr_tramo
                modo_viaje = "Operador"  # forzar
            elif tipo in ["IMPORTACION", "EXPORTACION"]:
                sueldo = km * pago_km
                bono = bono_isr_rl + bono_rendimiento
            else:  # VACIO
                sueldo = pago_vacio if km <= 100 else km * pago_km
                bono = 0.0

            if ruta_tipo != "Tramo" and modo_viaje == "Team":
                sueldo += bono_team

            extras = sum(map(safe_number, [
                movimiento_local, puntualidad, pension, estancia, fianza,
                pistas_extra, stop, falso, gatas, accesorios, guias
            ]))

            ingreso_flete_convertido = ingreso_original * tipo_cambio_flete
            ingreso_cruce_convertido = ingreso_cruce * tipo_cambio_cruce
            ingresos_extras = extras if extras_cobrados else 0.0
            ingreso_total = ingreso_flete_convertido + ingreso_cruce_convertido + ingresos_extras

            costo_cruce_convertido = costo_cruce * tipo_cambio_costo_cruce
            costo_total = costo_diesel_camion + sueldo + bono + casetas + extras + costo_cruce_convertido

            ruta_actualizada = {
                "Modo de Viaje": modo_viaje,
                "Fecha": fecha.isoformat(),
                "Tipo": tipo,
                "Ruta_Tipo": ruta_tipo,
                "Cliente": cliente,
                "Origen": origen,
                "Destino": destino,
                "KM": km,
                "Moneda": moneda_ingreso,
                "Ingreso_Original": ingreso_original,
                "Tipo de cambio": tipo_cambio_flete,
                "Ingreso Flete": ingreso_flete_convertido,
                "Moneda_Cruce": moneda_cruce,
                "Cruce_Original": ingreso_cruce,
                "Tipo cambio Cruce": tipo_cambio_cruce,
                "Ingreso Cruce": ingreso_cruce_convertido,
                "Ingreso Total": ingreso_total,
                "Moneda Costo Cruce": moneda_costo_cruce,
                "Costo Cruce": costo_cruce,
                "Costo Cruce Convertido": costo_cruce_convertido,
                "Pago por KM": pago_km,
                "Sueldo_Operador": sueldo,
                "Bono": bono,
                "Casetas": casetas,
                "Movimiento_Local": movimiento_local,
                "Puntualidad": puntualidad,
                "Pension": pension,
                "Estancia": estancia,
                "Fianza": fianza,
                "Pistas_Extra": pistas_extra,
                "Stop": stop,
                "Falso": falso,
                "Gatas": gatas,
                "Accesorios": accesorios,
                "Guias": guias,
                "Costo_Diesel_Camion": costo_diesel_camion,
                "Costo_Extras": extras,
                "Costo_Total_Ruta": costo_total,
                "Costo Diesel": costo_diesel,
                "Rendimiento Camion": rendimiento_camion,
                "Ingresos_Extras": ingresos_extras,
                "Extras_Cobrados": extras_cobrados,

                # ── Auditoría ──────────────────────────
                "updated_by": nombre_usuario,
                "updated_at": _now_iso(),
                "historial": historial_actual,
            }

            supabase.table("Rutas_Picus").update(ruta_actualizada).eq("ID_Ruta", id_editar).execute()
            alert("success", "✅ Ruta actualizada exitosamente.")
            _load_rutas_picus_cached.clear()
            st.rerun()

        except Exception as e:
            st.error(f"❌ Error al actualizar ruta: {e}")
            st.exception(e)

    # ── Historial de modificaciones ──────────────────────────────────
    divider()
    st.markdown("### 🧠 Historial de modificaciones de esta ruta")
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
                    for i, (k, v) in enumerate(datos_ant.items()):
                        with cols[i % 3]:
                            st.write(f"**{k}:** {v}")
