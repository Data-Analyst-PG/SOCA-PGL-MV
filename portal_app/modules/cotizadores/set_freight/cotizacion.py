from ui.components import section_header, alert, divider
"""
cotizacion.py  –  Set Freight LLC
Generador de cotización formal en PDF para enviar al cliente.
Solo incluye los conceptos de INGRESO (no los costos internos).
"""

import os
import tempfile
import streamlit as st
import pandas as pd
from datetime import date
from fpdf import FPDF

from services.supabase_client import get_supabase_client
from ._shared import TABLE_RUTAS, CONCEPTOS_INGRESO, calcular_ruta, safe


def _pdf(t) -> str:
    return str(t).encode("latin1", "replace").decode("latin1")


def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _find_logo() -> str | None:
    img_dir = os.path.join(_project_root(), "img")
    for name in ["Set Freight.png", "SetFreight.png", "ADT PGL GRAL NO TXT.png", "Color PGL MS.png"]:
        p = os.path.join(img_dir, name)
        if os.path.exists(p):
            return p
    return None


@st.cache_data(show_spinner=False, ttl=120)
def _cargar(table: str) -> pd.DataFrame:
    sb = get_supabase_client()
    if sb is None:
        return pd.DataFrame()
    try:
        resp = sb.table(table).select("*").execute()
    except Exception:
        return pd.DataFrame()
    return pd.DataFrame(resp.data or [])


def _generar_pdf(*, fecha_cot, cli_nombre, cli_dir, cli_mail,
                  emp_nombre, emp_mail, emp_tel,
                  moneda, tc, filas, notas, logo_path) -> bytes:
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    if logo_path and os.path.exists(logo_path):
        try:
            pdf.image(logo_path, x=10, y=8, w=50)
        except Exception:
            pass

    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, _pdf(emp_nombre), ln=True, align="R")
    pdf.set_font("Arial", size=9)
    pdf.cell(0, 5, _pdf(emp_mail), ln=True, align="R")
    pdf.cell(0, 5, _pdf(emp_tel),  ln=True, align="R")
    pdf.ln(4)

    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "COTIZACIÓN DE FLETE", ln=True, align="C")
    pdf.set_font("Arial", size=10)
    pdf.cell(0, 6, _pdf(f"Fecha: {fecha_cot}"), ln=True, align="C")
    pdf.ln(4)

    pdf.set_font("Arial", size=10)
    pdf.cell(0, 6, _pdf(f"Cliente: {cli_nombre}"), ln=True)
    if cli_dir:
        pdf.cell(0, 5, _pdf(f"Dirección: {cli_dir}"), ln=True)
    if cli_mail:
        pdf.cell(0, 5, _pdf(f"Email: {cli_mail}"), ln=True)
    pdf.ln(6)

    # Tabla de conceptos
    pdf.set_fill_color(30, 50, 120)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(90, 8, "Concepto / Ruta", border=1, fill=True)
    pdf.cell(40, 8, f"Precio ({moneda})", border=1, fill=True, align="C")
    pdf.cell(50, 8, "Notas", border=1, fill=True, ln=True)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", size=9)

    total = 0.0
    for concepto, ruta, precio_usd, nota_fila in filas:
        precio_display = precio_usd * tc if moneda == "MXP" else precio_usd
        total += precio_usd
        pdf.cell(90, 7, _pdf(f"{concepto} | {ruta}"), border=1)
        pdf.cell(40, 7, f"{moneda} {precio_display:,.2f}", border=1, align="R")
        pdf.cell(50, 7, _pdf(nota_fila or ""), border=1, ln=True)

    total_display = total * tc if moneda == "MXP" else total
    pdf.set_font("Arial", "B", 10)
    pdf.cell(90, 8, "TOTAL", border=1)
    pdf.cell(40, 8, f"{moneda} {total_display:,.2f}", border=1, align="R")
    pdf.cell(50, 8, "", border=1, ln=True)

    if notas:
        pdf.ln(6)
        pdf.set_font("Arial", "I", 9)
        pdf.multi_cell(0, 5, _pdf(f"Notas: {notas}"))

    pdf.ln(10)
    pdf.set_font("Arial", size=9)
    pdf.cell(0, 5, "Esta cotización es válida por 15 días a partir de la fecha de emisión.", ln=True, align="C")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
        pdf.output(f.name)
        f.seek(0)
        data = open(f.name, "rb").read()
    return data


def render():
    st.title("🗒️ Generador de Cotización — Set Freight LLC")

    sb = get_supabase_client()
    if sb is None:
        alert("warn", "⚠️ Supabase no configurado.")
        return

    df = _cargar(TABLE_RUTAS)
    if df.empty:
        alert("warn", "⚠️ No hay rutas registradas. Captura rutas primero.")
        return

    df["_label"] = (df.get("id_ruta","").fillna("") + " · " +
                    df.get("ruta_origen","").fillna("") + " — " +
                    df.get("ruta_destino","").fillna(""))

    # ── Selección de rutas a cotizar ──────────
section_header("1.", "Selecciona rutas a incluir")
    rutas_sel = st.multiselect("Rutas", df["_label"].tolist(), key="sf_cot_rutas")
    if not rutas_sel:
        alert("info", "Selecciona al menos una ruta.")
        return

    rows_sel = df[df["_label"].isin(rutas_sel)]

section_header("2.", "Datos del cliente")
    c1, c2 = st.columns(2)
    cli_nombre = c1.text_input("Nombre del cliente",    key="sf_cot_cli")
    cli_mail   = c2.text_input("Email del cliente",     key="sf_cot_mail")
    cli_dir    = c1.text_input("Dirección (opcional)",  key="sf_cot_dir")

section_header("3.", "Datos del emisor y moneda")
    d1, d2, d3 = st.columns(3)
    emp_nombre = d1.text_input("Empresa emisora", value="Set Freight LLC", key="sf_cot_emp")
    emp_mail   = d2.text_input("Email empresa",   key="sf_cot_emp_mail")
    emp_tel    = d3.text_input("Teléfono",        key="sf_cot_tel")

    m1, m2 = st.columns(2)
    moneda  = m1.selectbox("Moneda", ["USD", "MXP"], key="sf_cot_mon")
    tc      = m2.number_input("Tipo de cambio", value=18.0, step=0.01, key="sf_cot_tc")

    fecha_cot = st.date_input("Fecha cotización", value=date.today(), key="sf_cot_fecha")
    notas_pdf = st.text_area("Notas al pie", key="sf_cot_notas", height=60)

    if st.button("📄 Generar PDF", type="primary", key="sf_cot_gen"):
        if not cli_nombre.strip():
            alert("error", "❌ Ingresa el nombre del cliente.")
            return

        filas = []
        for _, row in rows_sel.iterrows():
            r = calcular_ruta(row.to_dict(), safe(row.get("pct_indirecto"), 0.10))
            ruta_str = f"{row.get('ruta_origen','')} — {row.get('ruta_destino','')}"
            for label, campo in CONCEPTOS_INGRESO.items():
                val = safe(row.get(campo))
                if val > 0:
                    filas.append((label, ruta_str, val, ""))

        logo = _find_logo()
        try:
            pdf_bytes = _generar_pdf(
                fecha_cot=fecha_cot, cli_nombre=cli_nombre, cli_dir=cli_dir, cli_mail=cli_mail,
                emp_nombre=emp_nombre, emp_mail=emp_mail, emp_tel=emp_tel,
                moneda=moneda, tc=tc, filas=filas, notas=notas_pdf, logo_path=logo,
            )
            st.download_button(
                label="⬇️ Descargar cotización PDF",
                data=pdf_bytes,
                file_name=f"cotizacion_sf_{fecha_cot}.pdf",
                mime="application/pdf",
            )
        except Exception as e:
            st.error(f"❌ Error generando PDF: {e}")
