from ui.components import section_header, alert, divider
import os
from datetime import datetime, timezone
import pandas as pd
import streamlit as st

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
# Config local (archivo)
# =========================
DEFAULTS = {
    "Rendimiento Camion": 2.5,
    "Costo Diesel": 24.0,
    "Pago x KM (General)": 1.63,
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
    # Guarda en portal_app/.data para que sea consistente con tu repo
    base = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".data")
    base = os.path.abspath(base)
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "datos_generales_picus.csv")


def cargar_datos_generales() -> dict:
    path = _datos_generales_path()
    if os.path.exists(path):
        try:
            return pd.read_csv(path).set_index("Parametro").to_dict()["Valor"]
        except Exception:
            return DEFAULTS.copy()
    return DEFAULTS.copy()


def guardar_datos_generales(valores: dict) -> None:
    path = _datos_generales_path()
    df = pd.DataFrame(valores.items(), columns=["Parametro", "Valor"])
    df.to_csv(path, index=False)


def safe_number(x):
    return 0 if (x is None or (isinstance(x, float) and pd.isna(x))) else x


def render():
    st.title("🚛 Captura de Rutas + Datos Generales (Picus)")

    # Supabase opcional (no tronar si no hay secrets/env)
    supabase = get_supabase_client()
    if supabase is None:
        alert("warn", "⚠️ Supabase no configurado. Podrás revisar cálculos, pero NO guardar rutas en BD.")

    # Detectar usuario logueado
    u = current_user() or {}
    user_id = u.get("id") or u.get("sub") or ""
    nombre_usuario = _get_profile_name(user_id) or u.get("email") or "Desconocido"

    # Estado
    if "picus_revisar_ruta" not in st.session_state:
        st.session_state.picus_revisar_ruta = False

    valores = cargar_datos_generales()

    # =========================
    # Configurar Datos Generales
    # =========================
    with st.expander("⚙️ Configurar Datos Generales", expanded=False):
        col1, col2 = st.columns(2)
        claves = list(DEFAULTS.keys())

        for i, key in enumerate(claves):
            col = col1 if i % 2 == 0 else col2
            valores[key] = col.number_input(
                key,
                value=float(valores.get(key, DEFAULTS[key])),
                step=0.1,
            )

        c1, c2 = st.columns([1, 2])
        with c1:
            if st.button("Guardar Datos Generales", key="picus_guardar_datos_generales"):
                guardar_datos_generales(valores)
                alert("success", "✅ Datos Generales guardados correctamente.")

        with c2:
            st.caption(f"Archivo: `{_datos_generales_path()}`")

    divider()
section_header("🛣️", "Nueva Ruta")

    # =========================
    # Helper: generar ID
    # =========================
    def generar_nuevo_id():
        if supabase is None:
            # Si no hay supabase, generamos un ID local por timestamp
            return f"PICLOCAL{datetime.now().strftime('%Y%m%d%H%M%S')}"

        try:
            resp = (
                supabase.table("Rutas_Picus")
                .select("ID_Ruta")
                .order("ID_Ruta", desc=True)
                .limit(1)
                .execute()
            )
            if resp.data and resp.data[0].get("ID_Ruta"):
                ultimo = resp.data[0]["ID_Ruta"]
                numero = int(str(ultimo)[3:]) + 1  # PIC000001
            else:
                numero = 1
        except Exception as e:
            st.warning(f"⚠️ No se pudo generar el ID automáticamente: {e}")
            numero = 1

        return f"PIC{numero:06d}"

    # =========================
    # Formulario principal
    # =========================
    with st.form("picus_captura_ruta"):
        col1, col2 = st.columns(2)

        with col1:
            fecha = st.date_input("Fecha", value=datetime.today())
            tipo = st.selectbox("Tipo de Ruta", ["IMPORTACION", "EXPORTACION", "VACIO"])
            ruta_tipo = st.selectbox("Ruta Tipo", ["Ruta Larga", "Tramo"])
            cliente = st.text_input("Nombre Cliente")
            origen = st.text_input("Origen")
            destino = st.text_input("Destino")
            modo_viaje_ui = st.selectbox("Modo de Viaje", ["Operador", "Team"])
            km = st.number_input("Kilómetros", min_value=0.0)
            moneda_ingreso = st.selectbox("Moneda Ingreso Flete", ["MXP", "USD"])
            ingreso_flete = st.number_input("Ingreso Flete", min_value=0.0)

        with col2:
            moneda_cruce = st.selectbox("Moneda Ingreso Cruce", ["MXP", "USD"])
            ingreso_cruce = st.number_input("Ingreso Cruce", min_value=0.0)
            moneda_costo_cruce = st.selectbox("Moneda Costo Cruce", ["MXP", "USD"])
            costo_cruce = st.number_input("Costo Cruce", min_value=0.0)
            movimiento_local = st.number_input("Movimiento Local (MXP)", min_value=0.0)
            puntualidad = st.number_input("Puntualidad", min_value=0.0)
            pension = st.number_input("Pensión (MXP)", min_value=0.0)
            estancia = st.number_input("Estancia (MXP)", min_value=0.0)
            fianza = st.number_input("Fianza (MXP)", min_value=0.0)
            casetas = st.number_input("Casetas (MXP)", min_value=0.0)

        divider()
    section_header("🧾", "Costos Extras")
        col3, col4 = st.columns(2)
        with col3:
            pistas_extra = st.number_input("Pistas Extra (MXP)", min_value=0.0)
            stop = st.number_input("Stop (MXP)", min_value=0.0)
            falso = st.number_input("Falso (MXP)", min_value=0.0)
            extras_cobrados = st.checkbox("✅ ¿Costos extras fueron cobrados al cliente?")
        with col4:
            gatas = st.number_input("Gatas (MXP)", min_value=0.0)
            accesorios = st.number_input("Accesorios (MXP)", min_value=0.0)
            guias = st.number_input("Guías (MXP)", min_value=0.0)

        revisar = st.form_submit_button("🔍 Revisar Ruta")

        if revisar:
            st.session_state.picus_revisar_ruta = True
            st.session_state.picus_datos_captura = {
                "fecha": fecha,
                "tipo": tipo,
                "ruta_tipo": ruta_tipo,
                "cliente": cliente,
                "origen": origen,
                "destino": destino,
                "modo_viaje_ui": modo_viaje_ui,
                "km": km,
                "moneda_ingreso": moneda_ingreso,
                "ingreso_flete": ingreso_flete,
                "moneda_cruce": moneda_cruce,
                "ingreso_cruce": ingreso_cruce,
                "moneda_costo_cruce": moneda_costo_cruce,
                "costo_cruce": costo_cruce,
                "movimiento_local": movimiento_local,
                "puntualidad": puntualidad,
                "pension": pension,
                "estancia": estancia,
                "fianza": fianza,
                "casetas": casetas,
                "pistas_extra": pistas_extra,
                "stop": stop,
                "falso": falso,
                "extras_cobrados": extras_cobrados,
                "gatas": gatas,
                "accesorios": accesorios,
                "guias": guias,
            }

            # ===========
            # Cálculos
            # ===========
            costo_cruce_convertido = costo_cruce * (valores["Tipo de cambio USD"] if moneda_costo_cruce == "USD" else 1)

            costo_diesel_camion = (km / valores["Rendimiento Camion"]) * valores["Costo Diesel"]

            pago_km = float(valores.get("Pago x KM (General)", 1.63))
            bono = 0.0
            sueldo = 0.0

            # Condicional por tipo de ruta
            if ruta_tipo == "Tramo":
                sueldo = float(valores.get("Pago Tramo", 300.0))
                bono = float(valores.get("Bono ISR IMSS Tramo", 185.06))
                modo_viaje_calc = "Operador"  # Forzar
            elif tipo in ["IMPORTACION", "EXPORTACION"]:
                sueldo = km * pago_km
                bono_isr = float(valores.get("Bono ISR IMSS RL", 0))
                bono_rend = float(valores.get("Bono Rendimiento", 0))
                bono = bono_isr + bono_rend
                modo_viaje_calc = modo_viaje_ui
            else:  # VACIO
                if km <= 100:
                    sueldo = float(valores.get("Pago Vacio", 100.0))
                else:
                    sueldo = km * pago_km
                bono = 0.0
                modo_viaje_calc = modo_viaje_ui

            # Bono Team (si no es tramo)
            if ruta_tipo != "Tramo" and modo_viaje_calc == "Team":
                sueldo += float(valores.get("Bono Modo Team", 650))

            extras = sum(
                map(
                    safe_number,
                    [
                        movimiento_local,
                        puntualidad,
                        pension,
                        estancia,
                        fianza,
                        pistas_extra,
                        stop,
                        falso,
                        gatas,
                        accesorios,
                        guias,
                    ],
                )
            )

            costo_total = costo_diesel_camion + sueldo + bono + casetas + extras + costo_cruce_convertido

            tipo_cambio_flete = valores["Tipo de cambio USD"] if moneda_ingreso == "USD" else valores["Tipo de cambio MXP"]
            tipo_cambio_cruce = valores["Tipo de cambio USD"] if moneda_cruce == "USD" else valores["Tipo de cambio MXP"]

            ingreso_flete_convertido = ingreso_flete * tipo_cambio_flete
            ingreso_cruce_convertido = ingreso_cruce * tipo_cambio_cruce
            ingresos_extras = extras if extras_cobrados else 0
            ingreso_total = ingreso_flete_convertido + ingreso_cruce_convertido + ingresos_extras

            utilidad_bruta = ingreso_total - costo_total
            costos_indirectos = ingreso_total * 0.35
            utilidad_neta = utilidad_bruta - costos_indirectos
            porcentaje_bruta = (utilidad_bruta / ingreso_total * 100) if ingreso_total > 0 else 0
            porcentaje_neta = (utilidad_neta / ingreso_total * 100) if ingreso_total > 0 else 0

            st.session_state.picus_resultados = {
                "modo_viaje_calc": modo_viaje_calc,
                "pago_km": pago_km,
                "bono": bono,
                "costo_diesel_camion": costo_diesel_camion,
                "extras": extras,
                "ingresos_extras": ingresos_extras,
                "tipo_cambio_flete": tipo_cambio_flete,
                "tipo_cambio_cruce": tipo_cambio_cruce,
                "tipo_cambio_costo_cruce": (valores["Tipo de cambio USD"] if moneda_costo_cruce == "USD" else valores["Tipo de cambio MXP"]),
                "ingreso_total": ingreso_total,
                "costo_total": costo_total,
                "utilidad_bruta": utilidad_bruta,
                "costos_indirectos": costos_indirectos,
                "utilidad_neta": utilidad_neta,
                "porcentaje_bruta": porcentaje_bruta,
                "porcentaje_neta": porcentaje_neta,
                "costo_cruce_convertido": costo_cruce_convertido,
                "sueldo": sueldo,
            }

            # ===========
            # Mostrar
            # ===========
            def colored_bold(label, value, condition):
                color = "green" if condition else "red"
                return f"<strong>{label}:</strong> <span style='color:{color}; font-weight:bold'>{value}</span>"

            divider()
        section_header("📊", "Ingresos y Utilidades")

            st.write(f"**Ingreso Total:** ${ingreso_total:,.2f}")
            st.write(f"**Costo Total:** ${costo_total:,.2f}")
            st.markdown(colored_bold("Utilidad Bruta", f"${utilidad_bruta:,.2f}", utilidad_bruta >= 0), unsafe_allow_html=True)
            st.markdown(colored_bold("% Utilidad Bruta", f"{porcentaje_bruta:.2f}%", porcentaje_bruta >= 50), unsafe_allow_html=True)
            st.write(f"**Costos Indirectos (35%):** ${costos_indirectos:,.2f}")
            st.markdown(colored_bold("Utilidad Neta", f"${utilidad_neta:,.2f}", utilidad_neta >= 0), unsafe_allow_html=True)
            st.markdown(colored_bold("% Utilidad Neta", f"{porcentaje_neta:.2f}%", porcentaje_neta >= 15), unsafe_allow_html=True)

    # =========================
    # Guardar Ruta
    # =========================
    if st.session_state.get("picus_revisar_ruta") and st.button("💾 Guardar Ruta", key="picus_guardar_ruta"):
        if supabase is None:
            alert("error", "Supabase no está configurado. No puedo guardar en BD.")
            return

        d = st.session_state.get("picus_datos_captura", {})
        r = st.session_state.get("picus_resultados", {})

        if not d or not r:
            alert("error", "No hay datos para guardar. Primero revisa la ruta.")
            return

        nuevo_id = generar_nuevo_id()

        # Confirmar no conflicto
        try:
            existe = supabase.table("Rutas_Picus").select("ID_Ruta").eq("ID_Ruta", nuevo_id).execute()
            if existe.data:
                alert("error", "⚠️ Conflicto al generar ID. Intenta de nuevo.")
                return
        except Exception:
            # Si falla el check, igual intentamos insert (Supabase dirá si hay conflicto)
            pass

        nueva_ruta = {
            "ID_Ruta": nuevo_id,
            "Fecha": str(d["fecha"]),
            "Tipo": d["tipo"],
            "Ruta_Tipo": d["ruta_tipo"],
            "Cliente": d["cliente"],
            "Origen": d["origen"],
            "Destino": d["destino"],
            "Modo de Viaje": r["modo_viaje_calc"],
            "KM": d["km"],
            "Moneda": d["moneda_ingreso"],
            "Ingreso_Original": d["ingreso_flete"],
            "Tipo de cambio": r["tipo_cambio_flete"],
            "Ingreso Flete": d["ingreso_flete"] * r["tipo_cambio_flete"],
            "Moneda_Cruce": d["moneda_cruce"],
            "Cruce_Original": d["ingreso_cruce"],
            "Tipo cambio Cruce": r["tipo_cambio_cruce"],
            "Ingreso Cruce": d["ingreso_cruce"] * r["tipo_cambio_cruce"],
            "Moneda Costo Cruce": d["moneda_costo_cruce"],
            "Costo Cruce": d["costo_cruce"],
            "Costo Cruce Convertido": r["costo_cruce_convertido"],
            "Ingreso Total": r["ingreso_total"],
            "Pago por KM": r["pago_km"],
            "Sueldo_Operador": r["sueldo"],
            "Bono": r["bono"],
            "Casetas": d["casetas"],
            "Movimiento_Local": d["movimiento_local"],
            "Puntualidad": d["puntualidad"],
            "Pension": d["pension"],
            "Estancia": d["estancia"],
            "Fianza": d["fianza"],
            "Pistas_Extra": d["pistas_extra"],
            "Stop": d["stop"],
            "Falso": d["falso"],
            "Gatas": d["gatas"],
            "Accesorios": d["accesorios"],
            "Guias": d["guias"],
            "Costo_Diesel_Camion": r["costo_diesel_camion"],
            "Costo_Extras": r["extras"],
            "Costo_Total_Ruta": r["costo_total"],
            "Costo Diesel": valores["Costo Diesel"],
            "Rendimiento Camion": valores["Rendimiento Camion"],
            "Ingresos_Extras": r["ingresos_extras"],
            "Extras_Cobrados": d["extras_cobrados"],

            # ── Auditoría ──────────────────────────────
            "created_by": nombre_usuario,
            "created_at": _now_iso(),
            "updated_by": None,
            "updated_at": None,
            "historial": [],
        }

        try:
            supabase.table("Rutas_Picus").insert(nueva_ruta).execute()
            alert("success", "✅ Ruta guardada exitosamente.")
            st.session_state.picus_revisar_ruta = False
            st.session_state.pop("picus_datos_captura", None)
            st.session_state.pop("picus_resultados", None)
            st.rerun()
        except Exception as e:
            st.error(f"❌ Error al guardar ruta: {e}")
            st.json(nueva_ruta)
