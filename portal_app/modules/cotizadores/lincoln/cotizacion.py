from ui.components import section_header, alert, divider
"""
cotizacion.py  –  Lincoln Freight (USA/MX)
Generador de cotización formal en PDF para enviar al cliente.
Selecciona rutas guardadas, define conceptos visibles y genera el PDF.
"""

import os
import tempfile
from datetime import date

import pandas as pd
import streamlit as st
from fpdf import FPDF

from services.supabase_client import get_supabase_client
from ._shared import TABLE_RUTAS, cargar_datos_generales, safe


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _safe_pdf(text) -> str:
    return str(text).encode("latin1", "replace").decode("latin1")


def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _find_logo() -> str | None:
    img_dir = os.path.join(_project_root(), "img")
    candidatos = [
        "Lincoln Original.png", "Lincoln White.png", "LicolnF Original.png",
        "LicolnF White.png", "ADT PGL GRAL NO TXT.png",
    ]
    for name in candidatos:
        path = os.path.join(img_dir, name)
        if os.path.exists(path):
            return path
    return None


@st.cache_data(show_spinner=False, ttl=120)
def _cargar_rutas(table: str) -> pd.DataFrame:
    supabase = get_supabase_client()
    if supabase is None:
        return pd.DataFrame()
    resp = supabase.table(table).select("*").execute()
    df = pd.DataFrame(resp.data)
    if not df.empty and "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d")
    return df


# Conceptos que se pueden mostrar al cliente
CONCEPTOS = {
    "Flete USA":       ("Ingreso_Flete_USA", True),
    "Fuel Surcharge":  ("Ingreso_Fuel_USA",  True),
    "Cruce":           ("Ingreso_Cruce",     True),
    "Flete MX":        ("Ingreso_Flete_MX",  False),
    "Otros":           ("Otros",             False),
}


# ─────────────────────────────────────────────
# GENERADOR PDF
# ─────────────────────────────────────────────
def _generar_pdf(
    *,
    fecha_cot: date,
    cliente_nombre: str, cliente_direccion: str, cliente_mail: str,
    empresa_nombre: str, empresa_mail: str, empresa_tel: str,
    moneda: str, tc: float,
    filas: list[dict],   # [{ruta_label, conceptos: [{nombre, valor_usd}]}]
    notas: str,
    logo_path: str | None,
) -> bytes:

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # ── Logo ──
    if logo_path and os.path.exists(logo_path):
        try:
            pdf.image(logo_path, x=10, y=8, w=50)
        except Exception:
            pass

    # ── Encabezado ──
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, _safe_pdf(empresa_nombre), ln=True, align="R")
    pdf.set_font("Arial", size=9)
    pdf.cell(0, 5, _safe_pdf(empresa_mail), ln=True, align="R")
    pdf.cell(0, 5, _safe_pdf(empresa_tel), ln=True, align="R")
    pdf.ln(4)

    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "COTIZACIÓN", ln=True, align="C")
    pdf.set_font("Arial", size=10)
    pdf.cell(0, 6, _safe_pdf(f"Fecha: {fecha_cot}"), ln=True, align="C")
    pdf.ln(4)

    # ── Datos cliente ──
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 7, "DATOS DEL CLIENTE", ln=True)
    pdf.set_font("Arial", size=10)
    pdf.cell(0, 6, _safe_pdf(f"Nombre: {cliente_nombre}"), ln=True)
    pdf.cell(0, 6, _safe_pdf(f"Dirección: {cliente_direccion}"), ln=True)
    pdf.cell(0, 6, _safe_pdf(f"Email: {cliente_mail}"), ln=True)
    pdf.ln(4)

    # ── Tabla de rutas ──
    pdf.set_font("Arial", "B", 10)
    pdf.set_fill_color(30, 30, 100)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(90, 8, "RUTA / CONCEPTO", border=1, fill=True)
    pdf.cell(50, 8, f"TARIFA ({moneda})", border=1, fill=True, align="R")
    pdf.ln()
    pdf.set_text_color(0, 0, 0)

    total_general = 0.0
    fill = False
    for fila in filas:
        pdf.set_font("Arial", "B", 9)
        pdf.set_fill_color(220, 228, 240)
        pdf.cell(90, 7, _safe_pdf(fila["ruta_label"]), border=1, fill=True)
        subtotal = sum(c["valor_usd"] for c in fila["conceptos"])
        if moneda == "MXP":
            subtotal_show = subtotal * tc
        else:
            subtotal_show = subtotal
        pdf.cell(50, 7, f"${subtotal_show:,.2f}", border=1, fill=True, align="R")
        pdf.ln()

        pdf.set_font("Arial", size=9)
        for concepto in fila["conceptos"]:
            v = concepto["valor_usd"] * tc if moneda == "MXP" else concepto["valor_usd"]
            pdf.set_fill_color(245, 245, 255) if fill else pdf.set_fill_color(255, 255, 255)
            pdf.cell(90, 6, _safe_pdf(f"  · {concepto['nombre']}"), border=1, fill=True)
            pdf.cell(50, 6, f"${v:,.2f}", border=1, fill=True, align="R")
            pdf.ln()
            fill = not fill

        total_general += subtotal

    # ── Totales ──
    pdf.set_font("Arial", "B", 10)
    pdf.set_fill_color(30, 30, 100)
    pdf.set_text_color(255, 255, 255)
    total_show = total_general * tc if moneda == "MXP" else total_general
    pdf.cell(90, 8, "TOTAL GENERAL", border=1, fill=True)
    pdf.cell(50, 8, f"${total_show:,.2f} {moneda}", border=1, fill=True, align="R")
    pdf.ln()
    pdf.set_text_color(0, 0, 0)

    # ── Notas ──
    if notas:
        pdf.ln(5)
        pdf.set_font("Arial", "B", 9)
        pdf.cell(0, 6, "Notas:", ln=True)
        pdf.set_font("Arial", size=9)
        pdf.multi_cell(0, 5, _safe_pdf(notas))

    pdf.ln(6)
    pdf.set_font("Arial", "I", 8)
    pdf.cell(0, 5, _safe_pdf(f"Cotización generada por {empresa_nombre} – {fecha_cot}"), ln=True, align="C")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf.output(tmp.name)
    with open(tmp.name, "rb") as f:
        return f.read()


# ─────────────────────────────────────────────
# RENDER
# ─────────────────────────────────────────────
def render():
    st.title("🗒️ Cotización – Lincoln Freight")

    supabase = get_supabase_client()
    if supabase is None:
        alert("warn", "⚠️ Supabase no configurado.")
        return

    c_r, _ = st.columns([1, 4])
    with c_r:
        if st.button("🔄 Recargar rutas", key="ln_cot_reload"):
            _cargar_rutas.clear()
            st.rerun()

    df = _cargar_rutas(TABLE_RUTAS)
    if df.empty:
        alert("warn", "⚠️ No hay rutas guardadas.")
        return

    valores = cargar_datos_generales()

    # ── Datos del cliente y empresa ──
    section_header("👤", "Cliente & Empresa")
    cc1, cc2 = st.columns(2)
    with cc1:
        st.markdown("**Cliente**")
        cli_nombre     = st.text_input("Nombre Cliente",    key="ln_cot_cli_nom")
        cli_dir        = st.text_input("Dirección Cliente", key="ln_cot_cli_dir")
        cli_mail       = st.text_input("Email Cliente",     key="ln_cot_cli_mail")
    with cc2:
        st.markdown("**Empresa (Lincoln)**")
        emp_nombre     = st.text_input("Nombre Empresa",    value="LINCOLN FREIGHT CARRIERS", key="ln_cot_emp_nom")
        emp_mail       = st.text_input("Email Empresa",     key="ln_cot_emp_mail")
        emp_tel        = st.text_input("Teléfono Empresa",  key="ln_cot_emp_tel")

    divider()

    # ── Moneda ──
    section_header("💵", "Moneda")
    mc1, mc2 = st.columns(2)
    moneda_cot = mc1.selectbox("Moneda de Cotización", ["USD", "MXP"], key="ln_cot_moneda")
    tc_cot     = mc2.number_input("Tipo de Cambio USD/MXP", value=float(valores.get("Tipo de Cambio USD/MXP", 18.0)),
                                   step=0.1, key="ln_cot_tc")

    divider()

    # ── Selección de rutas ──
    section_header("🛣️", "Rutas a cotizar")

    opciones_df = (
        df["ID_Ruta"].astype(str) + " | " +
        df.get("Tipo", pd.Series([""] * len(df))).astype(str) + " | " +
        df.get("Origen", pd.Series([""] * len(df))).astype(str) + " → " +
        df.get("Destino", pd.Series([""] * len(df))).astype(str) + " | " +
        df.get("Cliente", pd.Series([""] * len(df))).astype(str)
    )

    seleccionadas = st.multiselect(
        "Selecciona rutas para incluir en la cotización:",
        options=opciones_df.tolist(),
        key="ln_cot_rutas_sel"
    )

    # ── Config de conceptos por ruta ──
    filas_pdf = []

    for ruta_str in seleccionadas:
        id_ruta = ruta_str.split(" | ")[0].strip()
        row_df = df[df["ID_Ruta"] == id_ruta]
        if row_df.empty:
            continue
        row = row_df.iloc[0]

        st.markdown(f"**{ruta_str}**")
        col_s, col_v = st.columns(2)
        with col_s:
            st.caption("Incluir en tarifa:")
            conceptos_seleccionados = []
            for nombre, (col_db, default_on) in CONCEPTOS.items():
                val = safe(row.get(col_db, 0))
                if val == 0:
                    continue
                checked = st.checkbox(f"{nombre} (${val:,.2f})", value=default_on, key=f"ln_cot_{id_ruta}_{nombre}")
                if checked:
                    conceptos_seleccionados.append({"nombre": nombre, "valor_usd": val})
        with col_v:
            st.caption("Extras a incluir:")
            for campo in [
                "Extra_Stop_Off", "Extra_Detention", "Extra_Lumper_Fees",
                "Extra_Layover", "Extra_Mov_Extraordinario",
            ]:
                v_extra = safe(row.get(campo, 0))
                if v_extra > 0:
                    label_e = campo.replace("Extra_", "").replace("_", " ")
                    ch = st.checkbox(f"{label_e} (${v_extra:,.2f})", value=True, key=f"ln_cot_{id_ruta}_{campo}")
                    if ch:
                        conceptos_seleccionados.append({"nombre": label_e, "valor_usd": v_extra})

        ruta_label = f"{row.get('Tipo','')} | {row.get('Origen','')} → {row.get('Destino','')} | {row.get('Cliente','')}"
        filas_pdf.append({"ruta_label": ruta_label, "conceptos": conceptos_seleccionados})

    # ── Notas ──
    divider()
    notas = st.text_area("📝 Notas / Términos (opcional)", height=80, key="ln_cot_notas")

    # ── Generar PDF ──
    divider()
    fecha_cot = st.date_input("Fecha de cotización", value=date.today(), key="ln_cot_fecha")

    if st.button("📄 Generar PDF de Cotización", key="ln_cot_gen"):
        if not seleccionadas:
            alert("warn", "Selecciona al menos una ruta.")
        elif not cli_nombre:
            alert("warn", "Ingresa el nombre del cliente.")
        else:
            logo = _find_logo()
            pdf_bytes = _generar_pdf(
                fecha_cot=fecha_cot,
                cliente_nombre=cli_nombre,
                cliente_direccion=cli_dir,
                cliente_mail=cli_mail,
                empresa_nombre=emp_nombre,
                empresa_mail=emp_mail,
                empresa_tel=emp_tel,
                moneda=moneda_cot,
                tc=tc_cot,
                filas=filas_pdf,
                notas=notas,
                logo_path=logo,
            )
            fname = f"Cotizacion_Lincoln_{cli_nombre}_{fecha_cot}.pdf".replace(" ", "_")
            st.download_button(
                "📥 Descargar Cotización",
                data=pdf_bytes,
                file_name=fname,
                mime="application/pdf",
                key="ln_cot_dl",
            )
            alert("success", "✅ PDF generado exitosamente.")
