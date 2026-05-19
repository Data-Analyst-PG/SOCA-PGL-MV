from ui.components import section_header, alert, divider
import os
import tempfile
from datetime import datetime

import pandas as pd
import streamlit as st
from fpdf import FPDF

from services.supabase_client import get_supabase_client


# =========================
# Config local (mismo archivo que Captura)
# =========================
DEFAULTS = {
    "Rendimiento Camion": 2.5,
    "Costo Diesel": 24.0,
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
            return pd.read_csv(path).set_index("Parametro").to_dict()["Valor"]
        except Exception:
            return DEFAULTS.copy()
    return DEFAULTS.copy()


def safe_number(x):
    return 0 if (x is None or (isinstance(x, float) and pd.isna(x))) else x


def safe_text(texto):
    return str(texto).encode("latin-1", "replace").decode("latin-1")


def mostrar_resultados(ingreso_total, costo_total, utilidad_bruta, costos_indirectos, utilidad_neta, porcentaje_bruta, porcentaje_neta):
    divider()
    section_header("📊", "Ingresos y Utilidades")

    def colored_bold(label, value, condition):
        color = "green" if condition else "red"
        return f"<strong>{label}:</strong> <span style='color:{color}; font-weight:bold'>{value}</span>"

    st.write(f"**Ingreso Total:** ${ingreso_total:,.2f}")
    st.write(f"**Costo Total:** ${costo_total:,.2f}")
    st.markdown(colored_bold("Utilidad Bruta", f"${utilidad_bruta:,.2f}", utilidad_bruta >= 0), unsafe_allow_html=True)
    st.markdown(colored_bold("% Utilidad Bruta", f"{porcentaje_bruta:.2f}%", porcentaje_bruta >= 50), unsafe_allow_html=True)
    st.write(f"**Costos Indirectos (35%):** ${costos_indirectos:,.2f}")
    st.markdown(colored_bold("Utilidad Neta", f"${utilidad_neta:,.2f}", utilidad_neta >= 0), unsafe_allow_html=True)
    st.markdown(colored_bold("% Utilidad Neta", f"{porcentaje_neta:.2f}%", porcentaje_neta >= 15), unsafe_allow_html=True)


@st.cache_data(show_spinner=False, ttl=120)
def _load_rutas_picus_cached():
    """
    Cachea la tabla por 2 minutos para que no pegue a Supabase en cada rerun.
    """
    supabase = get_supabase_client()
    if supabase is None:
        return pd.DataFrame()

    resp = supabase.table("Rutas_Picus").select("*").execute()
    df = pd.DataFrame(resp.data)
    return df


def render():
    st.title("🔍 Consulta Individual de Ruta (Picus)")

    supabase = get_supabase_client()
    if supabase is None:
        alert("warn", "⚠️ Supabase no configurado. No se pueden consultar rutas guardadas.")
        return

    valores = cargar_datos_generales()

    # Cargar rutas (cacheado)
    df = _load_rutas_picus_cached()

    if df.empty:
        alert("warn", "⚠️ No hay rutas guardadas todavía.")
        return

    # Asegurar formato
    if "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d")
    if "Ingreso Total" in df.columns:
        df["Ingreso Total"] = pd.to_numeric(df["Ingreso Total"], errors="coerce").fillna(0)
    if "Costo_Total_Ruta" in df.columns:
        df["Costo_Total_Ruta"] = pd.to_numeric(df["Costo_Total_Ruta"], errors="coerce").fillna(0)

    section_header("📌", "Selección de Ruta")

    # 1) Ruta Tipo
    if "Ruta_Tipo" not in df.columns:
        alert("error", "La tabla no contiene la columna 'Ruta_Tipo'.")
        return

    tipo_ruta_especifica = st.selectbox("Ruta Larga o Tramo", sorted(df["Ruta_Tipo"].dropna().unique()))
    df_ruta_tipo = df[df["Ruta_Tipo"] == tipo_ruta_especifica]

    # 2) Tipo
    if "Tipo" not in df.columns:
        alert("error", "La tabla no contiene la columna 'Tipo'.")
        return

    tipo_sel = st.selectbox("Tipo (IMPORTACION / EXPORTACION / VACIO)", sorted(df_ruta_tipo["Tipo"].dropna().unique()))
    df_tipo = df_ruta_tipo[df_ruta_tipo["Tipo"] == tipo_sel]

    # 3) Origen/Destino
    if not {"Origen", "Destino"}.issubset(df.columns):
        alert("error", "La tabla debe tener columnas 'Origen' y 'Destino'.")
        return

    rutas_unicas = df_tipo[["Origen", "Destino"]].drop_duplicates()
    opciones_ruta = list(rutas_unicas.itertuples(index=False, name=None))
    ruta_sel = st.selectbox("Ruta (Origen → Destino)", opciones_ruta, format_func=lambda x: f"{x[0]} → {x[1]}")
    origen_sel, destino_sel = ruta_sel

    df_filtrada = df_tipo[(df_tipo["Origen"] == origen_sel) & (df_tipo["Destino"] == destino_sel)]
    if df_filtrada.empty:
        alert("warn", "⚠️ No hay rutas con esa combinación.")
        return

    # 4) Cliente (selección por índice real del DF)
    section_header("📌", "Selecciona Cliente")
    opciones = df_filtrada.index.tolist()
    index_sel = st.selectbox(
        "Cliente",
        opciones,
        format_func=lambda x: f"{df.loc[x, 'Cliente']} ({df.loc[x, 'Origen']} → {df.loc[x, 'Destino']})"
    )

    ruta = df.loc[index_sel]

    # =========================
    # Simulación
    # =========================
    divider()
    section_header("⚙️", "Ajustes para Simulación")

    costo_diesel_input = st.number_input("Costo del Diesel ($/L)", value=float(valores.get("Costo Diesel", 24.0)))
    rendimiento_input = st.number_input("Rendimiento Camión (km/L)", value=float(valores.get("Rendimiento Camion", 2.5)))

    colA, colB = st.columns(2)
    with colA:
        if st.button("🔁 Simular", key="picus_consulta_simular"):
            st.session_state["picus_simular"] = True
    with colB:
        if st.button("🔄 Volver a valores reales", key="picus_consulta_reset"):
            st.session_state["picus_simular"] = False
            st.rerun()

    simular = st.session_state.get("picus_simular", False)

    if simular:
        ingreso_total = safe_number(ruta.get("Ingreso Total"))
        km = safe_number(ruta.get("KM"))
        costo_diesel_camion = (km / rendimiento_input) * costo_diesel_input

        costo_total = (
            costo_diesel_camion +
            safe_number(ruta.get("Sueldo_Operador")) +
            safe_number(ruta.get("Bono")) +
            safe_number(ruta.get("Casetas")) +
            safe_number(ruta.get("Costo Cruce Convertido")) +
            safe_number(ruta.get("Costo_Extras"))
        )

        utilidad_bruta = ingreso_total - costo_total
        costos_indirectos = ingreso_total * 0.35
        utilidad_neta = utilidad_bruta - costos_indirectos
        porcentaje_bruta = (utilidad_bruta / ingreso_total * 100) if ingreso_total > 0 else 0
        porcentaje_neta = (utilidad_neta / ingreso_total * 100) if ingreso_total > 0 else 0

        alert("success", "🔧 Estás viendo una simulación. Se ajustó el diesel y rendimiento.")
        mostrar_resultados(ingreso_total, costo_total, utilidad_bruta, costos_indirectos, utilidad_neta, porcentaje_bruta, porcentaje_neta)

        # Para PDF
        ingreso_total_pdf = ingreso_total
        costo_total_pdf = costo_total
        utilidad_bruta_pdf = utilidad_bruta
        costos_indirectos_pdf = costos_indirectos
        utilidad_neta_pdf = utilidad_neta
        porcentaje_bruta_pdf = porcentaje_bruta
        porcentaje_neta_pdf = porcentaje_neta

    else:
        ingreso_total = safe_number(ruta.get("Ingreso Total"))
        costo_total = safe_number(ruta.get("Costo_Total_Ruta"))
        utilidad_bruta = ingreso_total - costo_total
        costos_indirectos = ingreso_total * 0.35
        utilidad_neta = utilidad_bruta - costos_indirectos
        porcentaje_bruta = (utilidad_bruta / ingreso_total * 100) if ingreso_total > 0 else 0
        porcentaje_neta = (utilidad_neta / ingreso_total * 100) if ingreso_total > 0 else 0

        mostrar_resultados(ingreso_total, costo_total, utilidad_bruta, costos_indirectos, utilidad_neta, porcentaje_bruta, porcentaje_neta)

        # Para PDF
        ingreso_total_pdf = ingreso_total
        costo_total_pdf = costo_total
        utilidad_bruta_pdf = utilidad_bruta
        costos_indirectos_pdf = costos_indirectos
        utilidad_neta_pdf = utilidad_neta
        porcentaje_bruta_pdf = porcentaje_bruta
        porcentaje_neta_pdf = porcentaje_neta

    # =====================
    # Detalles
    # =====================
    divider()
    section_header("📋", "Detalles y Costos de la Ruta")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(f"**Fecha:** {ruta.get('Fecha','')}")
        st.markdown(f"**ID de Ruta:** {ruta.get('ID_Ruta','')}")
        st.markdown(f"**Tipo:** {ruta.get('Tipo','')}")
        st.markdown(f"**Modo:** {ruta.get('Modo de Viaje','')}")
        st.markdown(f"**Cliente:** {ruta.get('Cliente','')}")
        st.markdown(f"**Origen → Destino:** {ruta.get('Origen','')} → {ruta.get('Destino','')}")
        st.markdown(f"**KM:** {safe_number(ruta.get('KM')):,.0f}")
        st.markdown(f"**Rendimiento Camión:** {safe_number(ruta.get('Rendimiento Camion'))} km/L")
        st.markdown(f"**Moneda Flete:** {ruta.get('Moneda','')}")
        st.markdown(f"**Ingreso Flete Original:** ${safe_number(ruta.get('Ingreso_Original')):,.2f}")
        st.markdown(f"**Tipo de cambio:** {safe_number(ruta.get('Tipo de cambio'))}")
        st.markdown(f"**Ingreso Flete Convertido:** ${safe_number(ruta.get('Ingreso Flete')):,.2f}")

    with col2:
        st.markdown(f"**Moneda Cruce:** {ruta.get('Moneda_Cruce','')}")
        st.markdown(f"**Ingreso Cruce Original:** ${safe_number(ruta.get('Cruce_Original')):,.2f}")
        st.markdown(f"**Tipo cambio Cruce:** {safe_number(ruta.get('Tipo cambio Cruce'))}")
        st.markdown(f"**Ingreso Cruce Convertido:** ${safe_number(ruta.get('Ingreso Cruce')):,.2f}")
        st.markdown(f"**Moneda Costo Cruce:** {ruta.get('Moneda Costo Cruce','')}")
        st.markdown(f"**Costo Cruce Original:** ${safe_number(ruta.get('Costo Cruce')):,.2f}")
        st.markdown(f"**Costo Cruce Convertido:** ${safe_number(ruta.get('Costo Cruce Convertido')):,.2f}")
        st.markdown(f"**Casetas:** ${safe_number(ruta.get('Casetas')):,.2f}")
        st.markdown(f"**Diesel Camión:** ${safe_number(ruta.get('Costo_Diesel_Camion')):,.2f}")
        st.markdown(f"**Sueldo Operador:** ${safe_number(ruta.get('Sueldo_Operador')):,.2f}")
        st.markdown(f"**Bono:** ${safe_number(ruta.get('Bono')):,.2f}")
        st.markdown(f"**Ingreso Total:** ${safe_number(ruta.get('Ingreso Total')):,.2f}")
        st.markdown(f"**Costo Total Ruta:** ${safe_number(ruta.get('Costo_Total_Ruta')):,.2f}")

    with col3:
        st.markdown("**🔧 Extras:**")
        st.markdown(f"- Movimiento Local: ${safe_number(ruta.get('Movimiento_Local')):,.2f}")
        st.markdown(f"- Puntualidad: ${safe_number(ruta.get('Puntualidad')):,.2f}")
        st.markdown(f"- Pensión: ${safe_number(ruta.get('Pension')):,.2f}")
        st.markdown(f"- Estancia: ${safe_number(ruta.get('Estancia')):,.2f}")
        st.markdown(f"- Fianza: ${safe_number(ruta.get('Fianza')):,.2f}")
        st.markdown(f"- Pistas Extra: ${safe_number(ruta.get('Pistas_Extra')):,.2f}")
        st.markdown(f"- Stop: ${safe_number(ruta.get('Stop')):,.2f}")
        st.markdown(f"- Falso: ${safe_number(ruta.get('Falso')):,.2f}")
        st.markdown(f"- Gatas: ${safe_number(ruta.get('Gatas')):,.2f}")
        st.markdown(f"- Accesorios: ${safe_number(ruta.get('Accesorios')):,.2f}")
        st.markdown(f"- Guías: ${safe_number(ruta.get('Guias')):,.2f}")

    # =====================
    # PDF
    # =====================
    divider()
    section_header("📥", "Generar PDF de esta Ruta")

    if st.button("📄 Generar PDF", key="picus_generar_pdf"):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)

        # Encabezado
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, "Consulta Individual de Ruta", ln=True)
        pdf.ln(5)

        # Datos principales
        pdf.set_font("Arial", "", 12)
        pdf.cell(0, 10, safe_text(f"ID de Ruta: {ruta.get('ID_Ruta','')}"), ln=True)
        pdf.cell(0, 10, safe_text(f"Fecha: {ruta.get('Fecha','')}"), ln=True)
        pdf.cell(0, 10, safe_text(f"Tipo: {ruta.get('Tipo','')}"), ln=True)
        pdf.cell(0, 10, safe_text(f"Modo: {ruta.get('Modo de Viaje','')}"), ln=True)
        pdf.cell(0, 10, safe_text(f"Cliente: {ruta.get('Cliente','')}"), ln=True)
        pdf.cell(0, 10, safe_text(f"Origen → Destino: {ruta.get('Origen','')} - {ruta.get('Destino','')}"), ln=True)
        pdf.cell(0, 10, safe_text(f"KM: {safe_number(ruta.get('KM')):,.2f}"), ln=True)
        pdf.ln(5)

        # Resultados
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 10, "Resultados de Utilidad:", ln=True)
        pdf.set_font("Arial", "", 12)
        pdf.cell(0, 10, safe_text(f"Ingreso Total: ${ingreso_total_pdf:,.2f}"), ln=True)
        pdf.cell(0, 10, safe_text(f"Costo Total: ${costo_total_pdf:,.2f}"), ln=True)
        pdf.cell(0, 10, safe_text(f"Utilidad Bruta: ${utilidad_bruta_pdf:,.2f}"), ln=True)
        pdf.cell(0, 10, safe_text(f"% Utilidad Bruta: {porcentaje_bruta_pdf:.2f}%"), ln=True)
        pdf.cell(0, 10, safe_text(f"Costos Indirectos (35%): ${costos_indirectos_pdf:,.2f}"), ln=True)
        pdf.cell(0, 10, safe_text(f"Utilidad Neta: ${utilidad_neta_pdf:,.2f}"), ln=True)
        pdf.cell(0, 10, safe_text(f"% Utilidad Neta: {porcentaje_neta_pdf:.2f}%"), ln=True)
        pdf.ln(5)

        # Detalles
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 10, "Detalles de Costos e Ingresos:", ln=True)
        pdf.set_font("Arial", "", 12)

        pdf.cell(0, 10, safe_text(f"Rendimiento Camión: {safe_number(ruta.get('Rendimiento Camion'))} km/L"), ln=True)
        pdf.cell(0, 10, safe_text(f"Moneda Flete: {ruta.get('Moneda','')}"), ln=True)
        pdf.cell(0, 10, safe_text(f"Ingreso Flete Original: ${safe_number(ruta.get('Ingreso_Original')):,.2f}"), ln=True)
        pdf.cell(0, 10, safe_text(f"Tipo de cambio: {safe_number(ruta.get('Tipo de cambio'))}"), ln=True)
        pdf.cell(0, 10, safe_text(f"Ingreso Flete Convertido: ${safe_number(ruta.get('Ingreso Flete')):,.2f}"), ln=True)

        pdf.cell(0, 10, safe_text(f"Moneda Cruce: {ruta.get('Moneda_Cruce','')}"), ln=True)
        pdf.cell(0, 10, safe_text(f"Ingreso Cruce Original: ${safe_number(ruta.get('Cruce_Original')):,.2f}"), ln=True)
        pdf.cell(0, 10, safe_text(f"Tipo cambio Cruce: {safe_number(ruta.get('Tipo cambio Cruce'))}"), ln=True)
        pdf.cell(0, 10, safe_text(f"Ingreso Cruce Convertido: ${safe_number(ruta.get('Ingreso Cruce')):,.2f}"), ln=True)

        pdf.cell(0, 10, safe_text(f"Moneda Costo Cruce: {ruta.get('Moneda Costo Cruce','')}"), ln=True)
        pdf.cell(0, 10, safe_text(f"Costo Cruce Original: ${safe_number(ruta.get('Costo Cruce')):,.2f}"), ln=True)
        pdf.cell(0, 10, safe_text(f"Costo Cruce Convertido: ${safe_number(ruta.get('Costo Cruce Convertido')):,.2f}"), ln=True)

        pdf.cell(0, 10, safe_text(f"Casetas: ${safe_number(ruta.get('Casetas')):,.2f}"), ln=True)
        pdf.cell(0, 10, safe_text(f"Diesel Camión: ${safe_number(ruta.get('Costo_Diesel_Camion')):,.2f}"), ln=True)
        pdf.cell(0, 10, safe_text(f"Sueldo Operador: ${safe_number(ruta.get('Sueldo_Operador')):,.2f}"), ln=True)
        pdf.cell(0, 10, safe_text(f"Bono: ${safe_number(ruta.get('Bono')):,.2f}"), ln=True)
        pdf.cell(0, 10, safe_text(f"Ingreso Total: ${ingreso_total_pdf:,.2f}"), ln=True)
        pdf.cell(0, 10, safe_text(f"Costo Total Ruta: ${costo_total_pdf:,.2f}"), ln=True)

        pdf.ln(5)
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 10, "Extras:", ln=True)
        pdf.set_font("Arial", "", 12)

        extras_map = [
            ("Movimiento_Local", "Movimiento Local"),
            ("Puntualidad", "Puntualidad"),
            ("Pension", "Pensión"),
            ("Estancia", "Estancia"),
            ("Fianza", "Fianza"),
            ("Pistas_Extra", "Pistas Extra"),
            ("Stop", "Stop"),
            ("Falso", "Falso"),
            ("Gatas", "Gatas"),
            ("Accesorios", "Accesorios"),
            ("Guias", "Guías"),
        ]
        for key, label in extras_map:
            pdf.cell(0, 10, safe_text(f"{label}: ${safe_number(ruta.get(key)):,.2f}"), ln=True)

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        pdf.output(temp_file.name)

        with open(temp_file.name, "rb") as f:
            st.download_button(
                label="📄 Descargar PDF",
                data=f,
                file_name=f"Consulta_{ruta.get('Cliente','Cliente')}_{ruta.get('Origen','Origen')}_{ruta.get('Destino','Destino')}.pdf",
                mime="application/pdf",
            )
