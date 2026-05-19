from ui.components import section_header, alert, divider
"""
cotizacion.py  –  Set Logis Plus
Generador de cotización formal PDF para enviar al cliente.
"""

import os
import tempfile
from datetime import date

import pandas as pd
import streamlit as st
from fpdf import FPDF # pyright: ignore[reportMissingModuleSource]

from services.supabase_client import get_supabase_client
from ._shared import TABLE_RUTAS, cargar_datos_generales, safe


def _pdf(text) -> str:
    return str(text).encode("latin1", "replace").decode("latin1")

def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

def _img_dir() -> str:
    return os.path.join(_project_root(), "img")


def _get_template_for_page(pagina_actual: int, total_paginas: int):
    """
    Set Logis Plus template system
    """

    img_dir = _img_dir()

    if total_paginas == 1:
        nombre = "2.0 ADT PGL SLPlus.png"

    elif total_paginas == 2:
        if pagina_actual == 1:
            nombre = "2.0 ADT PGL SLPlus (2).png"
        else:
            nombre = "2.0 ADT PGL SLPlus (4).png"

    else:
        if pagina_actual == 1:
            nombre = "2.0 ADT PGL SLPlus (2).png"
        elif pagina_actual == total_paginas:
            nombre = "2.0 ADT PGL SLPlus (4).png"
        else:
            nombre = "2.0 ADT PGL SLPlus (3).png"

    path = os.path.join(img_dir, nombre)

    if os.path.exists(path):
        return path

    st.warning(f"No se encontró plantilla: {nombre}")
    return None

def calcular_lineas_necesarias(filas):
    lineas_totales = 0

    for fila in filas:
        lineas_totales += 2  # header ruta

        for concepto in fila["conceptos"]:
            if concepto["valor"] != 0:
                lineas_totales += 1

    return lineas_totales


def estimar_paginas_necesarias(lineas_totales):
    if lineas_totales <= 20:
        return 1

    lineas_restantes = lineas_totales - 20
    paginas_adicionales = (lineas_restantes + 29) // 30

    return 1 + paginas_adicionales

@st.cache_data(show_spinner=False, ttl=120)
def _cargar_rutas(table: str) -> pd.DataFrame:
    supabase = get_supabase_client()
    if supabase is None:
        return pd.DataFrame()
    try:
        resp = supabase.table(table).select("*").execute()
    except Exception:
        return pd.DataFrame()
    df = pd.DataFrame(resp.data)
    if not df.empty and "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d")
    return df


# Conceptos visibles al cliente
CONCEPTOS = {
    "Flete USA":  "Flete_USA",
    "Fuel":       "Fuel",
    "Cruce":      "Cruce",
    "Flete MEX":  "Flete_MEX",
}


def _generar_pdf(
    *,
    fecha_cot,
    cli_nombre,
    cli_dir,
    cli_mail,
    cli_tel,
    cli_ext,

    emp_nombre,
    emp_dir,
    emp_mail,
    emp_tel,
    emp_ext,

    moneda,
    tc,
    filas,
    notas,
) -> bytes:

    lineas_totales = calcular_lineas_necesarias(filas)
    total_pages = estimar_paginas_necesarias(lineas_totales)

    class PDF(FPDF):
        def __init__(self, fecha_str="", total_pages=1):
            super().__init__(orientation="P", unit="in", format="Letter")
            self.set_compression(False)
            self.fecha_str = fecha_str
            self.total_pages = total_pages

        def header(self):
            pagina_actual = self.page_no()
            plantilla = _get_template_for_page(
                pagina_actual,
                self.total_pages
            )

            if plantilla and os.path.exists(plantilla):
                self.image(
                    plantilla,
                    x=0,
                    y=0,
                    w=8.5,
                    h=11
                )

            self.set_font("Helvetica", size=8)
            self.set_text_color(80, 80, 80)

            # fecha
            self.set_xy(0.90, 1.10)
            self.cell(
                1.2,
                0.12,
                str(self.fecha_str),
                align="L"
            )

            # pagination
            self.set_xy(1.21, 10.14)
            self.cell(0.20, 0.12, str(pagina_actual), align="C")

            self.set_xy(1.51, 10.14)
            self.cell(0.20, 0.12, str(self.total_pages), align="C")

    pdf = PDF(
        fecha_str=fecha_cot.strftime("%d/%m/%Y"),
        total_pages=total_pages
    )

    pdf.set_auto_page_break(auto=False)
    pdf.add_page()

    # -------------------
    # CLIENTE / EMPRESA
    # -------------------

    pdf.set_font("Helvetica", size=10)

    # Cliente
    pdf.set_xy(0.85, 2.05)
    pdf.multi_cell(2.89, 0.24, _pdf(cli_nombre), align="L")

    pdf.set_xy(0.85, 2.66)
    pdf.multi_cell(2.89, 0.18, _pdf(cli_dir), align="L")

    pdf.set_xy(0.85, 3.20)
    pdf.multi_cell(2.89, 0.31, _pdf(cli_mail), align="L")

    pdf.set_xy(0.85, 3.60)
    pdf.cell(1.35, 0.31, _pdf(cli_tel), align="L")

    pdf.set_xy(2.39, 3.60)
    pdf.cell(0.76, 0.31, _pdf(cli_ext), align="C")


    # Empresa
    pdf.set_xy(4.76, 2.05)
    pdf.multi_cell(2.89, 0.24, _pdf(emp_nombre), align="R")

    pdf.set_xy(4.76, 2.66)
    pdf.multi_cell(2.89, 0.18, _pdf(emp_dir), align="R")

    pdf.set_xy(4.76, 3.20)
    pdf.multi_cell(2.89, 0.31, _pdf(emp_mail), align="R")

    pdf.set_xy(5.23, 3.60)
    pdf.cell(1.35, 0.31, _pdf(emp_tel), align="R")

    pdf.set_xy(7.03, 3.60)
    pdf.cell(0.76, 0.31, _pdf(emp_ext), align="C")

    # -------------------
    # CONCEPTOS
    # -------------------

    y = 4.50
    y_max_page_1 = 8.20
    y_max_other_pages = 8.80

    total_global = 0
    pagina_actual = 1

    for fila in filas:

        kms_fila = fila.get("kms", "")

        y_max = y_max_page_1 if pagina_actual == 1 else y_max_other_pages

        if y + 0.35 > y_max:
            pdf.add_page()
            pagina_actual += 1
            y = 2.00

        pdf.set_font("Helvetica", "B", 7)

        tipo_ruta = fila["ruta_label"]["tipo"]
        ruta_texto = fila["ruta_label"]["ruta"]
        cliente_texto = fila["ruta_label"]["cliente"]

        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(128, 128, 128)

        pdf.set_xy(0.85, y)
        pdf.multi_cell(
            7,
            0.15,
            _pdf(tipo_ruta),
            align="L"
        )

        y = pdf.get_y()

        segunda_linea = f"{ruta_texto} - {cliente_texto}"

        pdf.set_xy(0.85, y)
        pdf.multi_cell(
            7,
            0.15,
            _pdf(segunda_linea),
            align="L"
        )

        y = pdf.get_y() + 0.05

        pdf.set_text_color(0, 0, 0)

        for c in fila["conceptos"]:
            y_max = y_max_page_1 if pagina_actual == 1 else y_max_other_pages

            if y > y_max:
                pdf.add_page()
                pagina_actual += 1
                y = 1.40

            valor = float(c["valor"])

            if moneda == "MXP":
                valor_show = valor * tc
            else:
                valor_show = valor

            pdf.set_font("Helvetica", size=7)

            # -------------------
            # CONCEPTO
            # -------------------

            pdf.set_xy(0.85, y)
            pdf.cell(
                3.20,
                0.15,
                _pdf(c["nombre"]),
                border=0,
                align="L"
            )

            # -------------------
            # KMS
            # -------------------

            kms_texto = str(kms_fila) if kms_fila else ""

            pdf.set_xy(4.00, y)
            pdf.cell(
                0.70,
                0.15,
                kms_texto,
                border=0,
                align="C"
            )

            # -------------------
            # CANTIDAD
            # -------------------

            cantidad_texto = "1"

            pdf.set_xy(5.10, y)
            pdf.cell(
                0.55,
                0.15,
                cantidad_texto,
                border=0,
                align="C"
            )

            # -------------------
            # MONEDA
            # -------------------

            pdf.set_xy(5.85, y)
            pdf.cell(
                0.65,
                0.15,
                moneda,
                border=0,
                align="C"
            )

            # -------------------
            # PRECIO
            # -------------------

            pdf.set_xy(6.55, y)
            pdf.cell(
                1.05,
                0.15,
                f"${valor_show:,.2f}",
                border=0,
                align="R"
            )

            total_global += valor_show
            y += 0.16

    while pdf.page_no() < total_pages:
        pdf.add_page()

    # -------------------
    # TOTAL
    # -------------------

    pdf.set_font("Helvetica", "B", 8)

    pdf.set_xy(5.85, 9.13)
    pdf.cell(0.70, 0.15, moneda, align="C")

    pdf.set_xy(6.55, 9.13)
    pdf.cell(
        1.00,
        0.15,
        f"${total_global:,.2f}",
        align="R"
    )

    # notas
    pdf.set_font("Helvetica", size=6.5)
    pdf.set_xy(0.90, 9.60)
    pdf.multi_cell(
        4.20,
        0.11,
        _pdf(notas)
    )

    pdf_bytes = pdf.output(dest="S").encode("latin-1")
    return pdf_bytes


def render():
    st.title("🗒️ Cotización – Set Logis Plus")

    supabase = get_supabase_client()
    if supabase is None:
        alert("warn", "⚠️ Supabase no configurado.")
        return

    cr, _ = st.columns([1, 4])
    with cr:
        if st.button("🔄 Recargar rutas", key="sl_cot_reload"):
            _cargar_rutas.clear()
            st.rerun()

    df = _cargar_rutas(TABLE_RUTAS)
    if df.empty:
        alert("warn", "⚠️ No hay rutas guardadas.")
        alert("info", "💡 Captura rutas primero para poder generar cotizaciones.")
        return

    valores = cargar_datos_generales()

    section_header("👤", "Cliente y Empresa")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Cliente")

        cli_nombre = st.text_input(
            "Nombre de la Empresa del Cliente",
            key="sl_cot_cn"
        )

        cli_dir = st.text_input(
            "Dirección Fiscal del Cliente",
            key="sl_cot_cdir"
        )

        cli_mail = st.text_input(
            "Email del Cliente",
            key="sl_cot_cmail"
        )

        cli_tel = st.text_input(
            "Teléfono del Cliente",
            key="sl_cot_ctel"
        )

        cli_ext = st.text_input(
            "Ext Cliente",
            key="sl_cot_cext"
        )


    with col2:
        st.markdown("### Empresa")

        emp_nombre = st.text_input(
            "Nombre de tu Empresa",
            value="SET LOGIS PLUS",
            key="sl_cot_en"
        )

        emp_dir = st.text_input(
            "Dirección Fiscal de la Empresa",
            key="sl_cot_edir"
        )

        emp_mail = st.text_input(
            "Email de la Empresa",
            key="sl_cot_eml"
        )

        emp_tel = st.text_input(
            "Teléfono de la Empresa",
            key="sl_cot_tel"
        )

        emp_ext = st.text_input(
            "Ext Empresa",
            key="sl_cot_eext"
        )

    divider()
    mc1, mc2 = st.columns(2)
    moneda = mc1.selectbox("Moneda", ["USD", "MXP"], key="sl_cot_mon")
    tc     = mc2.number_input("TC USD/MXP", value=float(valores.get("Tipo de Cambio USD/MXP", 18.0)), step=0.1, key="sl_cot_tc")

    divider()
    section_header("🛣️", "Rutas a cotizar")

    opciones = (
        df["ID_Ruta"].astype(str) + " | " +
        df.get("Tipo_Viaje", pd.Series([""] * len(df))).astype(str) + " | " +
        df.get("Ruta_USA", pd.Series([""] * len(df))).astype(str) + " | " +
        df.get("Cliente", pd.Series([""] * len(df))).astype(str)
    )
    seleccionadas = st.multiselect("Selecciona rutas:", opciones.tolist(), key="sl_cot_sel")

    filas_pdf = []
    for ruta_str in seleccionadas:
        id_ruta = ruta_str.split(" | ")[0].strip()
        row_df  = df[df["ID_Ruta"] == id_ruta]
        if row_df.empty:
            continue
        row = row_df.iloc[0]

        st.markdown(f"**{ruta_str}**")
        conceptos_sel = []
        cols_c = st.columns(len(CONCEPTOS))
        for i, (nombre, col_db) in enumerate(CONCEPTOS.items()):
            val = safe(row.get(col_db, 0))
            if val == 0:
                continue
            checked = cols_c[i % len(CONCEPTOS)].checkbox(
                f"{nombre} (${val:,.2f})", value=True, key=f"sl_cot_{id_ruta}_{nombre}"
            )
            if checked:
                conceptos_sel.append({"nombre": nombre, "valor": val})

        ruta_label = {
            "tipo": str(row.get("Tipo_Viaje", "")),
            "ruta": str(row.get("Ruta_USA", "")),
            "cliente": str(row.get("Cliente", "")),
        }

        kms_valor = row.get("Miles_Load", "")

        filas_pdf.append({
            "ruta_label": ruta_label,
            "conceptos": conceptos_sel,
            "kms": kms_valor
        })

    divider()
    notas     = st.text_area("📝 Notas / Términos", height=70, key="sl_cot_notas")
    fecha_cot = st.date_input("Fecha de cotización", value=date.today(), key="sl_cot_fecha")

    if st.button("📄 Generar PDF", key="sl_cot_gen"):
        if not seleccionadas:
            alert("warn", "Selecciona al menos una ruta.")
        elif not cli_nombre or not emp_nombre:
            alert("warn", "Completa los datos principales de cliente y empresa.")
        else:
            pdf_bytes = _generar_pdf(
                fecha_cot=fecha_cot,

                cli_nombre=cli_nombre,
                cli_dir=cli_dir,
                cli_mail=cli_mail,
                cli_tel=cli_tel,
                cli_ext=cli_ext,

                emp_nombre=emp_nombre,
                emp_dir=emp_dir,
                emp_mail=emp_mail,
                emp_tel=emp_tel,
                emp_ext=emp_ext,

                moneda=moneda,
                tc=tc,
                filas=filas_pdf,
                notas=notas,
            )
            fname = f"Cotizacion_SetLogis_{cli_nombre}_{fecha_cot}.pdf".replace(" ", "_")
            st.download_button("📥 Descargar", data=pdf_bytes, file_name=fname, mime="application/pdf")
            alert("success", "✅ PDF generado.")
