from ui.components import section_header, alert, divider
import pandas as pd
import streamlit as st
from fpdf import FPDF
import tempfile

from services.supabase_client import get_supabase_client


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
    # Estado default
    defaults = {
        "rutas_seleccionadas": [],
        "ingreso_total": 0.0,
        "costo_total_general": 0.0,
        "utilidad_bruta": 0.0,
        "costos_indirectos": 0.0,
        "utilidad_neta": 0.0,
        "pct_bruta": 0.0,
        "pct_neta": 0.0,
        "simulacion_realizada": False,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

    st.title("🔁 Simulador de Vuelta Redonda (Picus)")

    supabase = get_supabase_client()
    if supabase is None:
        alert("warn", "⚠️ Supabase no configurado. No se pueden cargar rutas guardadas.")
        return

    c1, c2 = st.columns([1, 3])
    with c1:
        if st.button("🔄 Recargar rutas", key="picus_sim_reload"):
            _load_rutas_picus_cached.clear()
            st.rerun()
    with c2:
        st.caption("Carga cacheada 2 min para que sea rápido.")

    # Cargar rutas
    df = _load_rutas_picus_cached()
    if df.empty:
        alert("warn", "⚠️ No hay rutas guardadas en Supabase.")
        return

    # Normalizar
    for col in ["Origen", "Destino", "Cliente"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.upper()

    if "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d")

    df["Utilidad"] = pd.to_numeric(df.get("Ingreso Total", 0), errors="coerce").fillna(0) - pd.to_numeric(df.get("Costo_Total_Ruta", 0), errors="coerce").fillna(0)
    df["% Utilidad"] = (df["Utilidad"] / pd.to_numeric(df.get("Ingreso Total", 0), errors="coerce").fillna(0).replace(0, pd.NA) * 100).fillna(0).round(2)

    # -------------------------
    # Paso 1: Ruta principal
    # -------------------------
section_header("📌", "Ruta Principal")

    if "Ruta_Tipo" not in df.columns or "Tipo" not in df.columns:
        alert("error", "La tabla debe contener columnas Ruta_Tipo y Tipo.")
        return

    ruta_tipo_sel = st.selectbox(
        "Ruta Larga o Tramo",
        sorted(df["Ruta_Tipo"].dropna().unique()),
        key="picus_sim_ruta_tipo"
    )

    df_filtro = df[df["Ruta_Tipo"] == ruta_tipo_sel].copy()

    tipos_disponibles = sorted(df_filtro["Tipo"].dropna().unique().tolist())
    tipo_ruta_1 = st.selectbox("Selecciona tipo de ruta principal", tipos_disponibles)

    rutas_tipo_1 = df_filtro[df_filtro["Tipo"] == tipo_ruta_1].copy()
    opciones_1 = rutas_tipo_1[["Origen", "Destino"]].drop_duplicates().sort_values(by=["Origen", "Destino"])

    if opciones_1.empty:
        alert("error", "⚠️ No hay rutas disponibles para este tipo.")
        return

    ruta_seleccionada_1 = st.selectbox(
        "Selecciona ruta",
        list(opciones_1.itertuples(index=False, name=None)),
        format_func=lambda x: f"{x[0]} → {x[1]}",
    )
    origen1, destino1 = ruta_seleccionada_1

    candidatas_1 = rutas_tipo_1[(rutas_tipo_1["Origen"] == origen1) & (rutas_tipo_1["Destino"] == destino1)] \
        .sort_values(by="% Utilidad", ascending=False).reset_index(drop=True)

    if tipo_ruta_1 in ["IMPORTACION", "EXPORTACION"]:
        if candidatas_1["Cliente"].dropna().empty:
            alert("error", "⚠️ No hay clientes disponibles para esta ruta.")
            return
        candidatas_1["opcion"] = candidatas_1.apply(lambda row: f"{row['Fecha']} — {row['Cliente']}", axis=1)
        opcion_seleccionada = st.selectbox("Cliente / Fecha", candidatas_1["opcion"].tolist())
        ruta_1 = candidatas_1[candidatas_1["opcion"] == opcion_seleccionada].iloc[0].to_dict()

    elif tipo_ruta_1 == "VACIO":
        if candidatas_1.empty:
            alert("error", "⚠️ No hay rutas VACÍO disponibles para ese origen/destino.")
            return
        ruta_1 = candidatas_1.iloc[0].to_dict()

    else:
        alert("error", "⚠️ Tipo de ruta no reconocido.")
        return

    # -------------------------
    # Paso 2: sugerencias regreso
    # -------------------------
    divider()
section_header("🔁", "Rutas sugeridas (combinaciones con o sin vacío)")

    tipo_principal = str(ruta_1.get("Tipo", "")).strip().upper()
    destino_origen = str(ruta_1.get("Destino", "")).strip().upper()

    if tipo_principal in ["IMPORTACION", "EXPORTACION"]:
        tipo_regreso = "EXPORTACION" if tipo_principal == "IMPORTACION" else "IMPORTACION"
    else:
        tipo_regreso = None  # si principal es VACIO

    sugerencias = []

    # 1) Regreso directo (sin vacío)
    if tipo_regreso:
        directas = df_filtro[(df_filtro["Tipo"] == tipo_regreso) & (df_filtro["Origen"] == destino_origen)].copy()
        for _, row in directas.iterrows():
            ingreso_total = safe_number(ruta_1.get("Ingreso Total")) + safe_number(row.get("Ingreso Total"))
            costo_total = safe_number(ruta_1.get("Costo_Total_Ruta")) + safe_number(row.get("Costo_Total_Ruta"))
            utilidad = ingreso_total - costo_total
            pct = (utilidad / ingreso_total * 100) if ingreso_total else 0
            sugerencias.append({
                "descripcion": f"{row.get('Fecha')} — {row.get('Cliente')} → {row.get('Origen')} → {row.get('Destino')} ({pct:.2f}%)",
                "tramos": [row.to_dict()],
                "utilidad": utilidad,
                "pct": pct
            })

        # 2) Regreso con VACIO + cliente
        vacios = df_filtro[(df_filtro["Tipo"] == "VACIO") & (df_filtro["Origen"] == destino_origen)].copy()
        for _, vacio in vacios.iterrows():
            origen_post = str(vacio.get("Destino", "")).strip().upper()
            candidatos = df_filtro[(df_filtro["Tipo"] == tipo_regreso) & (df_filtro["Origen"] == origen_post)].copy()
            for _, final in candidatos.iterrows():
                ingreso_total = safe_number(ruta_1.get("Ingreso Total")) + safe_number(final.get("Ingreso Total"))
                costo_total = (
                    safe_number(ruta_1.get("Costo_Total_Ruta")) +
                    safe_number(vacio.get("Costo_Total_Ruta")) +
                    safe_number(final.get("Costo_Total_Ruta"))
                )
                utilidad = ingreso_total - costo_total
                pct = (utilidad / ingreso_total * 100) if ingreso_total else 0
                descripcion = f"{final.get('Fecha')} — {final.get('Cliente')} (Vacío {vacio.get('Origen')}→{vacio.get('Destino')}) → {final.get('Destino')} ({pct:.2f}%)"
                sugerencias.append({
                    "descripcion": descripcion,
                    "tramos": [vacio.to_dict(), final.to_dict()],
                    "utilidad": utilidad,
                    "pct": pct
                })

    # 3) Si principal es VACIO: buscar import/export desde su destino
    if tipo_principal == "VACIO":
        origen_vacio = str(ruta_1.get("Destino", "")).strip().upper()
        candidatos = df_filtro[(df_filtro["Tipo"].isin(["IMPORTACION", "EXPORTACION"])) & (df_filtro["Origen"] == origen_vacio)].copy()
        for _, final in candidatos.iterrows():
            ingreso_total = safe_number(ruta_1.get("Ingreso Total")) + safe_number(final.get("Ingreso Total"))
            costo_total = safe_number(ruta_1.get("Costo_Total_Ruta")) + safe_number(final.get("Costo_Total_Ruta"))
            utilidad = ingreso_total - costo_total
            pct = (utilidad / ingreso_total * 100) if ingreso_total else 0
            descripcion = f"{final.get('Fecha')} — {final.get('Cliente')} {final.get('Origen')} → {final.get('Destino')} ({pct:.2f}%)"
            sugerencias.append({
                "descripcion": descripcion,
                "tramos": [final.to_dict()],
                "utilidad": utilidad,
                "pct": pct
            })

    # Ordenar por % utilidad (desc) y utilidad como desempate
    sugerencias = sorted(sugerencias, key=lambda x: (x.get("pct", 0), x.get("utilidad", 0)), reverse=True)

    # Selección
    if sugerencias:
        opciones_sugeridas = {s["descripcion"]: s for s in sugerencias}
        descripcion_sel = st.selectbox("Selecciona una opción de regreso sugerida", list(opciones_sugeridas.keys()), key="picus_sim_regreso_sel")
        seleccion = opciones_sugeridas[descripcion_sel]
        rutas_seleccionadas = [ruta_1] + seleccion.get("tramos", [])
    else:
        alert("warn", "⚠️ No hay rutas de regreso disponibles.")
        rutas_seleccionadas = [ruta_1]

    # -------------------------
    # Simulación
    # -------------------------
    divider()
    if st.button("🚛 Simular Vuelta Redonda", key="picus_sim_run"):
        ingreso_total = sum(safe_number(r.get("Ingreso Total", 0)) for r in rutas_seleccionadas)
        costo_total_general = sum(safe_number(r.get("Costo_Total_Ruta", 0)) for r in rutas_seleccionadas)
        utilidad_bruta = ingreso_total - costo_total_general
        costos_indirectos = ingreso_total * 0.35
        utilidad_neta = utilidad_bruta - costos_indirectos
        pct_bruta = (utilidad_bruta / ingreso_total * 100) if ingreso_total > 0 else 0
        pct_neta = (utilidad_neta / ingreso_total * 100) if ingreso_total > 0 else 0

        st.markdown("## 📄 Detalle de Rutas")
        for r in rutas_seleccionadas:
            st.markdown(f"**{r.get('Tipo','N/A')} — {r.get('Cliente', 'N/A')}**")
            st.markdown(f"**ID Ruta:** {r.get('ID_Ruta', 'N/A')}")
            st.markdown(f"- Fecha: {r.get('Fecha', 'N/A')}")
            st.markdown(f"- {r.get('Origen', 'N/A')} → {r.get('Destino', 'N/A')}")
            st.markdown(f"- Ingreso Total: ${safe_number(r.get('Ingreso Total')):,.2f}")
            st.markdown(f"- Costo Total Ruta: ${safe_number(r.get('Costo_Total_Ruta')):,.2f}")

        divider()
    section_header("📊", "Resultado General")

        def colored_bold(label, value, ok, thr_ok=True):
            color = "green" if ok else "red"
            return f"<strong>{label}:</strong> <span style='color:{color}; font-weight:bold'>{value}</span>"

        st.markdown(f"**Ingreso Total:** ${ingreso_total:,.2f}")
        st.markdown(f"**Costo Total:** ${costo_total_general:,.2f}")
        st.markdown(colored_bold("Utilidad Bruta", f"${utilidad_bruta:,.2f}", utilidad_bruta >= 0), unsafe_allow_html=True)
        st.markdown(colored_bold("% Utilidad Bruta", f"{pct_bruta:.2f}%", pct_bruta >= 50), unsafe_allow_html=True)
        st.markdown(f"**Costos Indirectos (35%):** ${costos_indirectos:,.2f}")
        st.markdown(colored_bold("Utilidad Neta", f"${utilidad_neta:,.2f}", utilidad_neta >= 0), unsafe_allow_html=True)
        st.markdown(colored_bold("% Utilidad Neta", f"{pct_neta:.2f}%", pct_neta >= 15), unsafe_allow_html=True)

        st.session_state.ingreso_total = ingreso_total
        st.session_state.costo_total_general = costo_total_general
        st.session_state.utilidad_bruta = utilidad_bruta
        st.session_state.costos_indirectos = costos_indirectos
        st.session_state.utilidad_neta = utilidad_neta
        st.session_state.pct_bruta = pct_bruta
        st.session_state.pct_neta = pct_neta
        st.session_state.rutas_seleccionadas = rutas_seleccionadas
        st.session_state.simulacion_realizada = True

    # -------------------------
    # PDF
    # -------------------------
section_header("📥", "Generar PDF de la Simulación")

    if not st.session_state.simulacion_realizada:
        alert("info", "ℹ️ Ejecuta primero la simulación para poder generar el PDF.")
        return

    if st.button("📄 Generar PDF", key="picus_sim_pdf"):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)

        pdf.cell(0, 10, "Detalle de Rutas - Vuelta Redonda", ln=True, align="C")
        pdf.ln(10)

        for r in st.session_state.rutas_seleccionadas:
            pdf.set_font("Arial", style="B", size=12)
            pdf.cell(0, 10, f"{r.get('Tipo','N/A')} - {r.get('Cliente','N/A')}", ln=True)
            pdf.set_font("Arial", size=10)
            pdf.cell(0, 10, f"ID Ruta: {r.get('ID_Ruta','N/A')}", ln=True)
            pdf.cell(0, 10, f"Fecha: {r.get('Fecha','N/A')}", ln=True)
            pdf.cell(0, 10, f"{r.get('Origen','N/A')} -> {r.get('Destino','N/A')}", ln=True)
            pdf.cell(0, 10, f"Ingreso Total: ${safe_number(r.get('Ingreso Total')):,.2f}", ln=True)
            pdf.cell(0, 10, f"Costo Total Ruta: ${safe_number(r.get('Costo_Total_Ruta')):,.2f}", ln=True)
            pdf.cell(0, 10, "-----------------------------", ln=True)

        pdf.ln(5)
        pdf.set_font("Arial", style="B", size=12)
        pdf.cell(0, 10, "Resumen General", ln=True)
        pdf.set_font("Arial", size=10)

        pdf.cell(0, 10, f"Ingreso Total: ${st.session_state.ingreso_total:,.2f}", ln=True)
        pdf.cell(0, 10, f"Costo Total: ${st.session_state.costo_total_general:,.2f}", ln=True)
        pdf.cell(0, 10, f"Utilidad Bruta: ${st.session_state.utilidad_bruta:,.2f}", ln=True)
        pdf.cell(0, 10, f"% Utilidad Bruta: {st.session_state.pct_bruta:.2f}%", ln=True)
        pdf.cell(0, 10, f"Costos Indirectos (35%): ${st.session_state.costos_indirectos:,.2f}", ln=True)
        pdf.cell(0, 10, f"Utilidad Neta: ${st.session_state.utilidad_neta:,.2f}", ln=True)
        pdf.cell(0, 10, f"% Utilidad Neta: {st.session_state.pct_neta:.2f}%", ln=True)

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        pdf.output(temp_file.name)

        ruta_base = st.session_state.rutas_seleccionadas[0] if st.session_state.rutas_seleccionadas else {}
        file_name = f"Simulacion_{ruta_base.get('Tipo','NA')}_{ruta_base.get('ID_Ruta','SinID')}.pdf"

        with open(temp_file.name, "rb") as file:
            st.download_button(
                label="Descargar PDF",
                data=file,
                file_name=file_name,
                mime="application/pdf",
            )
