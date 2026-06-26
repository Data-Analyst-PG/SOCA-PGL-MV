# portal_app/modules/auditoria/rentabilidad/catalogo_cuentas.py
# ─────────────────────────────────────────────────────────────────────────────
# Tab: Catálogo de Cuentas Contables
# Define qué cuentas existen, a qué tipo(s) de cliente aplican,
# qué driver se usa para prorratear y si son fijas o variables.
# Esta es la base para que el motor de prorrateo sepa cuánto
# asignarle a cada cliente.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import pandas as pd
import streamlit as st

from services.supabase_client import get_authed_client as get_supabase_client
from ui.components import section_header, alert, divider

# ── Constantes ────────────────────────────────────────────────────────────────
TABLE = "rentabilidad_cuentas"

TIPOS_CLIENTE = ["T1", "T2", "T3", "T4", "TODOS"]

DRIVERS = {
    "km":         "Por kilómetro recorrido",
    "viaje":      "Por número de viajes",
    "equitativo": "Reparto equitativo entre tipos que aplican",
    "unidades":   "Por unidades dedicadas asignadas",
    "dias_caja":  "Por días que la caja está en el cliente",
    "cruces":     "Por número de cruces fronterizos",
    "lavados":    "Por número de lavados",
}

TIPOS_COSTO = {
    "fijo":     "Fijo – se asigna como cuota mensual constante",
    "variable": "Variable – depende del uso real del periodo",
}


# ── Helpers ───────────────────────────────────────────────────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def _cargar_cuentas() -> list[dict]:
    sb = get_supabase_client()
    if sb is None:
        return []
    try:
        res = sb.table(TABLE).select("*").order("numero").execute()
        return res.data or []
    except Exception as e:
        st.error(f"Error cargando cuentas: {e}")
        return []


def _guardar_cuenta(data: dict, cuenta_id: str | None = None) -> bool:
    sb = get_supabase_client()
    if sb is None:
        return False
    try:
        if cuenta_id:
            sb.table(TABLE).update(data).eq("id", cuenta_id).execute()
        else:
            sb.table(TABLE).insert(data).execute()
        return True
    except Exception as e:
        st.error(f"Error guardando cuenta: {e}")
        return False


def _eliminar_cuenta(cuenta_id: str) -> bool:
    sb = get_supabase_client()
    if sb is None:
        return False
    try:
        sb.table(TABLE).update({"activa": False}).eq("id", cuenta_id).execute()
        return True
    except Exception as e:
        st.error(f"Error desactivando cuenta: {e}")
        return False


def _build_pct_cols(aplica_a: list[str]) -> dict:
    """Genera pct_t1..t4 equitativos según los tipos que aplican."""
    mapping = {"T1": "pct_t1", "T2": "pct_t2", "T3": "pct_t3", "T4": "pct_t4"}
    base = {v: 0.0 for v in mapping.values()}
    if "TODOS" in aplica_a:
        activos = ["T1", "T2", "T3", "T4"]
    else:
        activos = [t for t in aplica_a if t in mapping]
    if activos:
        pct = round(1.0 / len(activos), 6)
        for t in activos:
            base[mapping[t]] = pct
    return base


# ── Formulario de cuenta nueva / edición ─────────────────────────────────────
def _form_cuenta(key_prefix: str, defaults: dict | None = None) -> dict | None:
    """Renderiza el formulario y devuelve el dict con los datos si se guarda, o None."""
    d = defaults or {}

    col1, col2 = st.columns(2)
    with col1:
        numero = st.text_input(
            "Número de cuenta",
            value=d.get("numero", ""),
            placeholder="Ej: 343",
            key=f"{key_prefix}_numero",
        )
    with col2:
        descripcion = st.text_input(
            "Descripción",
            value=d.get("descripcion", ""),
            placeholder="Ej: Equipo de seguridad",
            key=f"{key_prefix}_desc",
        )

    col3, col4 = st.columns(2)
    with col3:
        aplica_sel = st.multiselect(
            "Aplica a",
            options=TIPOS_CLIENTE,
            default=d.get("aplica_a", ["TODOS"]),
            key=f"{key_prefix}_aplica",
            help="Selecciona los tipos de cliente que absorben este costo. "
                 "'TODOS' lo reparte entre T1, T2, T3 y T4.",
        )
    with col4:
        driver_lbl = st.selectbox(
            "Driver de asignación",
            options=list(DRIVERS.keys()),
            format_func=lambda k: f"{k} – {DRIVERS[k].split('–')[0].strip()}",
            index=list(DRIVERS.keys()).index(d.get("driver", "km")),
            key=f"{key_prefix}_driver",
        )

    col5, col6 = st.columns(2)
    with col5:
        tipo_costo = st.radio(
            "Tipo de costo",
            options=["fijo", "variable"],
            format_func=lambda t: TIPOS_COSTO[t],
            index=0 if d.get("tipo", "fijo") == "fijo" else 1,
            key=f"{key_prefix}_tipo",
            horizontal=True,
        )
    with col6:
        activa = st.checkbox(
            "Cuenta activa",
            value=d.get("activa", True),
            key=f"{key_prefix}_activa",
        )

    # Mostrar distribución porcentual calculada
    if aplica_sel:
        pcts = _build_pct_cols(aplica_sel)
        labels = {"pct_t1": "T1", "pct_t2": "T2", "pct_t3": "T3", "pct_t4": "T4"}
        dist_str = "  ·  ".join(
            f"{lbl}: {pcts[k]*100:.1f}%"
            for k, lbl in labels.items()
            if pcts[k] > 0
        )
        st.caption(f"Distribución calculada: {dist_str}")

    col_btn, _ = st.columns([1, 3])
    with col_btn:
        guardado = st.button("💾 Guardar cuenta", key=f"{key_prefix}_btn")

    if guardado:
        if not numero.strip() or not descripcion.strip():
            alert("warn", "El número y la descripción son obligatorios.")
            return None
        if not aplica_sel:
            alert("warn", "Selecciona al menos un tipo de cliente.")
            return None

        pcts = _build_pct_cols(aplica_sel)
        return {
            "numero":      numero.strip(),
            "descripcion": descripcion.strip(),
            "aplica_a":    aplica_sel,
            "driver":      driver_lbl,
            "tipo":        tipo_costo,
            "activa":      activa,
            **pcts,
        }
    return None


# ── Render principal ──────────────────────────────────────────────────────────
def render():
    section_header(
        "🧾", "Catálogo de Cuentas Contables",
        "Define el driver y tipo de cada cuenta para el prorrateo automático",
    )

    sb = get_supabase_client()
    if sb is None:
        alert("warn", "Supabase no configurado. Los cambios no se guardarán.")

    # ── Agregar cuenta nueva ──────────────────────────────────────────────────
    with st.expander("➕ Agregar cuenta nueva", expanded=False):
        datos = _form_cuenta("nueva")
        if datos:
            if _guardar_cuenta(datos):
                alert("success", f"Cuenta {datos['numero']} – {datos['descripcion']} guardada.")
                st.cache_data.clear()
                st.rerun()

    divider()

    # ── Filtros ───────────────────────────────────────────────────────────────
    cuentas = _cargar_cuentas()
    if not cuentas:
        alert("info", "No hay cuentas registradas. Agrega la primera arriba.")
        return

    df = pd.DataFrame(cuentas)

    col_f1, col_f2, col_f3, col_f4 = st.columns([2, 2, 2, 1])
    with col_f1:
        buscar = st.text_input("🔍 Buscar", placeholder="Número o descripción...", key="cc_buscar")
    with col_f2:
        filtro_driver = st.multiselect("Driver", options=list(DRIVERS.keys()), key="cc_driver")
    with col_f3:
        filtro_tipo = st.multiselect("Tipo", options=["fijo", "variable"], key="cc_tipo")
    with col_f4:
        solo_activas = st.checkbox("Solo activas", value=True, key="cc_activas")

    if buscar:
        mask = (
            df["numero"].str.contains(buscar, case=False, na=False) |
            df["descripcion"].str.contains(buscar, case=False, na=False)
        )
        df = df[mask]
    if filtro_driver:
        df = df[df["driver"].isin(filtro_driver)]
    if filtro_tipo:
        df = df[df["tipo"].isin(filtro_tipo)]
    if solo_activas:
        df = df[df["activa"] == True]

    # ── KPIs ─────────────────────────────────────────────────────────────────
    col_k1, col_k2, col_k3, col_k4 = st.columns(4)
    col_k1.metric("Total cuentas", len(df))
    col_k2.metric("Fijas", int((df["tipo"] == "fijo").sum()))
    col_k3.metric("Variables", int((df["tipo"] == "variable").sum()))
    col_k4.metric("Inactivas", int((df["activa"] == False).sum()) if "activa" in df.columns else 0)

    divider()

    # ── Vista de tabla compacta ───────────────────────────────────────────────
    section_header("📋", "Cuentas registradas", f"{len(df)} registros")

    DRIVER_ICON = {
        "km": "📍", "viaje": "🚚", "equitativo": "⚖️",
        "unidades": "🚛", "dias_caja": "📦", "cruces": "🛂", "lavados": "🧼",
    }
    TIPO_COLOR = {"fijo": "#0077B6", "variable": "#E65100"}

    for _, row in df.iterrows():
        cid = row["id"]
        driver_icon = DRIVER_ICON.get(row.get("driver", ""), "❓")
        tipo_color  = TIPO_COLOR.get(row.get("tipo", "fijo"), "#6B7280")
        aplica      = ", ".join(row.get("aplica_a") or [])

        col_num, col_desc, col_ap, col_drv, col_tip, col_edit = st.columns(
            [1.2, 3, 2, 1.8, 1.5, 0.8]
        )

        with col_num:
            st.markdown(
                f'<div style="font-weight:700;color:#1B2266;padding:0.4rem 0;">'
                f'{row["numero"]}</div>',
                unsafe_allow_html=True,
            )
        with col_desc:
            st.markdown(
                f'<div style="padding:0.4rem 0;color:#374151;">{row["descripcion"]}</div>',
                unsafe_allow_html=True,
            )
        with col_ap:
            st.markdown(
                f'<div style="padding:0.4rem 0;font-size:0.8rem;color:#6B7280;">'
                f'{aplica}</div>',
                unsafe_allow_html=True,
            )
        with col_drv:
            st.markdown(
                f'<div style="padding:0.4rem 0;font-size:0.85rem;">'
                f'{driver_icon} {row.get("driver","")}</div>',
                unsafe_allow_html=True,
            )
        with col_tip:
            st.markdown(
                f'<span style="background:{tipo_color}18;color:{tipo_color};'
                f'font-size:0.75rem;font-weight:700;padding:2px 10px;'
                f'border-radius:12px;">{row.get("tipo","").upper()}</span>',
                unsafe_allow_html=True,
            )
        with col_edit:
            if st.button("✏️", key=f"cc_edit_{cid}", help="Editar esta cuenta"):
                st.session_state[f"cc_editando_{cid}"] = True

        # Panel de edición inline
        if st.session_state.get(f"cc_editando_{cid}"):
            with st.container():
                st.markdown("---")
                datos_edit = _form_cuenta(f"edit_{cid}", defaults=row.to_dict())
                if datos_edit:
                    if _guardar_cuenta(datos_edit, cuenta_id=cid):
                        alert("success", "Cuenta actualizada.")
                        st.session_state.pop(f"cc_editando_{cid}", None)
                        st.cache_data.clear()
                        st.rerun()
                col_cancel, col_del, _ = st.columns([1, 1, 3])
                with col_cancel:
                    if st.button("Cancelar", key=f"cc_cancel_{cid}"):
                        st.session_state.pop(f"cc_editando_{cid}", None)
                        st.rerun()
                with col_del:
                    if st.button("🗑️ Desactivar", key=f"cc_del_{cid}",
                                 help="Desactiva la cuenta sin borrarla"):
                        if _eliminar_cuenta(cid):
                            alert("success", "Cuenta desactivada.")
                            st.session_state.pop(f"cc_editando_{cid}", None)
                            st.cache_data.clear()
                            st.rerun()

        st.divider()

    # ── Descarga ──────────────────────────────────────────────────────────────
    if not df.empty:
        cols_export = ["numero", "descripcion", "aplica_a", "driver", "tipo",
                       "pct_t1", "pct_t2", "pct_t3", "pct_t4", "activa"]
        cols_export = [c for c in cols_export if c in df.columns]
        csv = df[cols_export].to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Descargar catálogo (.csv)",
            data=csv,
            file_name="catalogo_cuentas_rentabilidad.csv",
            mime="text/csv",
            key="cc_download",
        )
