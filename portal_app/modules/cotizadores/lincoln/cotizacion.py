"""
cotizacion.py – Lincoln Freight (USA/MX)
Generador de cotización con plantilla PNG igual que Igloo/Picus/Set Logis.
Plantillas: portal_app/img/2.0 ADT PGL LINCOLN (2/3/4).png
"""

from __future__ import annotations

import os
import re
from datetime import date

import pandas as pd
import streamlit as st
from fpdf import FPDF

from services.supabase_client import get_supabase_client
from ui.components import section_header, alert, divider
from ._shared import TABLE_RUTAS, cargar_datos_generales, safe


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

def _img_dir() -> str:
    return os.path.join(_project_root(), "img")

def _fonts_dir() -> str:
    return os.path.join(_project_root(), "fonts")

def safe_text(text: str) -> str:
    return str(text).encode("latin-1", "replace").decode("latin-1")


# ─────────────────────────────────────────────
# SISTEMA DE PLANTILLAS (idéntico a Igloo)
# ─────────────────────────────────────────────
def _get_template(pagina_actual: int, total_paginas: int) -> str | None:
    img_dir = _img_dir()
    if total_paginas == 1:
        nombre = "2.0 ADT PGL LINCOLN.png"
    elif total_paginas == 2:
        nombre = "2.0 ADT PGL LINCOLN (2).png" if pagina_actual == 1 else "2.0 ADT PGL LINCOLN (4).png"
    else:
        if pagina_actual == 1:
            nombre = "2.0 ADT PGL LINCOLN (2).png"
        elif pagina_actual == total_paginas:
            nombre = "2.0 ADT PGL LINCOLN (4).png"
        else:
            nombre = "2.0 ADT PGL LINCOLN (3).png"

    path = os.path.join(img_dir, nombre)
    return path if os.path.exists(path) else None


def _estimar_paginas(lineas: int) -> int:
    if lineas <= 20:
        return 1
    return 1 + (lineas - 20 + 29) // 30


def _contar_lineas(rutas_config: dict, ids_sel: list, df: pd.DataFrame) -> int:
    total = 0
    for ruta_sel in ids_sel:
        id_ruta = ruta_sel.split(" | ")[0]
        if id_ruta not in df.index:
            continue
        total += 2  # header tipo + origen-destino
        cfg = rutas_config.get(ruta_sel, {"cobrar": [], "mostrar": []})
        for campo in cfg["cobrar"] + cfg["mostrar"]:
            val = df.loc[id_ruta].get(campo, 0)
            if val and not pd.isna(val) and float(val) != 0:
                total += 1
    return total


# ─────────────────────────────────────────────
# CLASE PDF (idéntica a Igloo)
# ─────────────────────────────────────────────
class PDF(FPDF):
    def __init__(self, fecha_str: str = "", total_pages: int = 1, **kwargs):
        super().__init__(**kwargs)
        self.fecha_str   = fecha_str
        self.total_pages = total_pages
        self.has_montserrat = False
        try:
            fonts = _fonts_dir()
            reg  = os.path.join(fonts, "Montserrat-Regular.ttf")
            bold = os.path.join(fonts, "Montserrat-Bold.ttf")
            it   = os.path.join(fonts, "Montserrat-Italic.ttf")
            if os.path.exists(reg):
                self.add_font("Montserrat", "",  reg,  uni=True); self.has_montserrat = True
            if os.path.exists(bold):
                self.add_font("Montserrat", "B", bold, uni=True)
            if os.path.exists(it):
                self.add_font("Montserrat", "I", it,   uni=True)
        except Exception:
            self.has_montserrat = False

    def set_body_font(self, bold: bool = False, italic: bool = False, size: float = 7):
        style = ("B" if bold else "") + ("I" if italic else "")
        if self.has_montserrat:
            try:
                self.set_font("Montserrat", style, size)
            except Exception:
                self.set_font("Montserrat", "", size)
        else:
            self.set_font("Helvetica", style, size)

    def header(self):
        page = self.page_no()
        tpl  = _get_template(page, self.total_pages)
        if tpl:
            self.image(tpl, x=0, y=0, w=8.5, h=11)

    def footer(self):
        pass   # El número de página va en la plantilla


# ─────────────────────────────────────────────
# CACHE DE RUTAS
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=120)
def _cargar_rutas(table: str) -> pd.DataFrame:
    sb = get_supabase_client()
    if sb is None:
        return pd.DataFrame()
    try:
        resp = sb.table(table).select("*").execute()
        df   = pd.DataFrame(resp.data or [])
        if not df.empty and "Fecha" in df.columns:
            df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d")
        return df
    except Exception:
        return pd.DataFrame()


# ─────────────────────────────────────────────
# CONCEPTOS POR RUTA
# Cobrar → suma al total de la cotización
# Mostrar → solo visual, en gris (no suma)
# ─────────────────────────────────────────────
CONCEPTOS_COBRAR = [
    ("Flete USA",      "Ingreso_Flete_USA"),
    ("Fuel Surcharge", "Ingreso_Fuel_USA"),
    ("Cruce",          "Ingreso_Cruce"),
    ("Flete MX",       "Ingreso_MX_USD"),
]
CONCEPTOS_MOSTRAR = [
    ("Otros Cargos", "Otros_Cargos_Ingreso"),
]


# ─────────────────────────────────────────────
# RENDER
# ─────────────────────────────────────────────
def render() -> None:
    sb = get_supabase_client()
    if sb is None:
        alert("error", "Supabase no configurado.")
        return

    c_r, _ = st.columns([1, 5])
    with c_r:
        if st.button("🔄 Recargar rutas", key="ln_cot_reload"):
            _cargar_rutas.clear()
            st.rerun()

    df = _cargar_rutas(TABLE_RUTAS)
    if df.empty:
        alert("warn", "No hay rutas guardadas. Captura rutas primero.")
        return

    if "ID_Ruta" in df.columns:
        df.set_index("ID_Ruta", inplace=True, drop=False)

    valores = cargar_datos_generales()

    # ── Fecha ─────────────────────────────────────────────────────
    fecha = st.date_input("📅 Fecha de cotización", value=date.today(), key="ln_cot_fecha")

    # ── Datos cliente / empresa ───────────────────────────────────
    tab_cli, tab_emp = st.tabs(["👤 Datos del Cliente", "🏢 Datos de la Empresa"])

    with tab_cli:
        c1, c2 = st.columns(2)
        cliente_nombre    = c1.text_input("Nombre del Cliente *",    key="ln_cot_cli_nom")
        cliente_direccion = c1.text_input("Dirección",               key="ln_cot_cli_dir")
        cliente_mail      = c2.text_input("📧 Email",                key="ln_cot_cli_mail")
        cliente_telefono  = c2.text_input("📞 Teléfono",             key="ln_cot_cli_tel")
        cliente_ext       = c2.text_input("Ext.",                    key="ln_cot_cli_ext")

    with tab_emp:
        e1, e2 = st.columns(2)
        empresa_nombre    = e1.text_input("Nombre Empresa",  value="Lincoln Freight LLC",   key="ln_cot_emp_nom")
        empresa_direccion = e1.text_input("Dirección",                                       key="ln_cot_emp_dir")
        empresa_mail      = e2.text_input("📧 Email",                                        key="ln_cot_emp_mail")
        empresa_telefono  = e2.text_input("📞 Teléfono",                                     key="ln_cot_emp_tel")
        empresa_ext       = e2.text_input("Ext.",                                            key="ln_cot_emp_ext")

    divider()

    # ── Selección de rutas ────────────────────────────────────────
    section_header("1.", "Seleccionar rutas a cotizar")

    def _lbl(row) -> str:
        return (
            f"{row.get('ID_Ruta','')} | {row.get('Fecha','')} | "
            f"{row.get('Tipo','')} | {row.get('Cliente','—')} | "
            f"{row.get('Origen','')} → {row.get('Destino','')}"
        )

    df["_label"] = df.apply(_lbl, axis=1)
    ids_sel = st.multiselect("Rutas disponibles", df["_label"].tolist(), key="ln_cot_rutas")

    if not ids_sel:
        alert("info", "Selecciona al menos una ruta para continuar.")
        return

    # ── Configurar conceptos por ruta ─────────────────────────────
    divider()
    section_header("2.", "Configurar conceptos por ruta")
    st.caption("Marca los conceptos que se cobrarán al cliente. Los desmarcados aparecen en gris (solo visual).")

    rutas_config: dict = {}
    moneda_cot = st.selectbox("💱 Moneda de la cotización", ["USD", "MXP"], key="ln_cot_moneda")
    tc = float(valores.get("Tipo de Cambio USD/MXP", 18.5))
    if moneda_cot == "MXP":
        tc_input = st.number_input("Tipo de Cambio USD/MXP", value=tc, step=0.1, key="ln_cot_tc")
        tc = tc_input

    for ruta_lbl in ids_sel:
        id_ruta = ruta_lbl.split(" | ")[0]
        if id_ruta not in df.index:
            continue
        row = df.loc[id_ruta]
        tipo = str(row.get("Tipo", ""))

        with st.expander(f"📋 {ruta_lbl}", expanded=True):
            cobrar:   list[str] = []
            mostrar:  list[str] = []
            c1, c2 = st.columns(2)

            with c1:
                st.caption("Conceptos de ingreso:")
                for nombre, campo in CONCEPTOS_COBRAR:
                    # Flete MX solo aplica en D2D
                    if campo == "Ingreso_MX_USD" and tipo not in {"D2DNB", "D2DSB"}:
                        continue
                    val = safe(row.get(campo, 0))
                    if val <= 0:
                        continue
                    val_show = val * tc if moneda_cot == "MXP" else val
                    checked = st.checkbox(
                        f"{nombre}: ${val_show:,.2f} {moneda_cot}",
                        value=True,
                        key=f"ln_cot_cobrar_{id_ruta}_{campo}",
                    )
                    if checked:
                        cobrar.append(campo)
                    else:
                        mostrar.append(campo)

            with c2:
                st.caption("Otros cargos extras:")
                for nombre, campo in CONCEPTOS_MOSTRAR:
                    val = safe(row.get(campo, 0))
                    if val <= 0:
                        st.caption("Sin extras registrados.")
                        continue
                    val_show = val * tc if moneda_cot == "MXP" else val
                    checked_e = st.checkbox(
                        f"{nombre}: ${val_show:,.2f} {moneda_cot}",
                        value=False,
                        key=f"ln_cot_cobrar_{id_ruta}_{campo}",
                    )
                    if checked_e:
                        cobrar.append(campo)
                    else:
                        mostrar.append(campo)

            rutas_config[ruta_lbl] = {"cobrar": cobrar, "mostrar": mostrar}

    # ── Moneda y notas ────────────────────────────────────────────
    divider()
    notas_default = (
        "Precios sujetos a disponibilidad de unidades. "
        "Cotización válida por 5 días hábiles. "
        "No aplica IVA en servicios de exportación e importación (tasa 0)."
    )
    notas = st.text_area("📝 Notas / Términos y Condiciones",
                          value=notas_default, height=80, key="ln_cot_notas")

    # ── Generar PDF ───────────────────────────────────────────────
    divider()
    if st.button("📄 Generar Cotización PDF", type="primary",
                 use_container_width=True, key="ln_cot_gen",
                 disabled=(len(ids_sel) == 0 or not cliente_nombre.strip())):

        # Calcular páginas necesarias
        lineas      = _contar_lineas(rutas_config, ids_sel, df)
        num_paginas = _estimar_paginas(lineas)

        pdf = PDF(
            orientation="P", unit="in", format="Letter",
            fecha_str=fecha.strftime("%d/%m/%Y"),
            total_pages=num_paginas,
        )
        pdf.set_auto_page_break(auto=False)
        pdf.add_page()

        # ── Datos cliente / empresa en pág 1 ─────────────────────
        pdf.set_body_font(size=10)
        pdf.set_text_color(0, 0, 0)

        # Cliente
        pdf.set_xy(0.85, 2.05); pdf.multi_cell(2.89, 0.24, safe_text(cliente_nombre),    align="L")
        pdf.set_xy(0.85, 2.66); pdf.multi_cell(2.89, 0.18, safe_text(cliente_direccion), align="L")
        pdf.set_xy(0.85, 3.20); pdf.multi_cell(2.89, 0.31, safe_text(cliente_mail),      align="L")
        pdf.set_xy(0.85, 3.60); pdf.cell(1.35, 0.31, safe_text(cliente_telefono), align="L")
        pdf.set_xy(2.39, 3.60); pdf.cell(0.76, 0.31, safe_text(cliente_ext),      align="C")

        # Empresa
        pdf.set_xy(4.76, 2.05); pdf.multi_cell(2.89, 0.24, safe_text(empresa_nombre),    align="R")
        pdf.set_xy(4.76, 2.66); pdf.multi_cell(2.89, 0.18, safe_text(empresa_direccion), align="R")
        pdf.set_xy(4.76, 3.20); pdf.multi_cell(2.89, 0.31, safe_text(empresa_mail),      align="R")
        pdf.set_xy(5.23, 3.60); pdf.cell(1.35, 0.31, safe_text(empresa_telefono), align="R")
        pdf.set_xy(7.03, 3.60); pdf.cell(0.76, 0.31, safe_text(empresa_ext),      align="C")

        # ── Conceptos ─────────────────────────────────────────────
        pdf.set_body_font(size=7)
        y             = 4.50
        y_max_pag1    = 8.60
        y_max_otras   = 9.20
        total_global  = 0.0
        pagina_actual = 1

        for ruta_lbl in ids_sel:
            id_ruta = ruta_lbl.split(" | ")[0]
            if id_ruta not in df.index:
                continue

            row      = df.loc[id_ruta]
            tipo_r   = str(row.get("Tipo", ""))
            origen   = str(row.get("Origen", ""))
            destino  = str(row.get("Destino", ""))
            y_max    = y_max_pag1 if pagina_actual == 1 else y_max_otras

            # Salto si no hay espacio para el header de ruta
            if y + 0.35 > y_max:
                pdf.add_page()
                pagina_actual += 1
                y = 2.00

            # Header de ruta (gris)
            pdf.set_body_font(bold=True, size=7)
            pdf.set_text_color(128, 128, 128)
            pdf.set_xy(0.85, y); pdf.multi_cell(7, 0.15, safe_text(tipo_r), align="L")
            y = pdf.get_y()
            pdf.set_xy(0.85, y); pdf.multi_cell(7, 0.15, safe_text(f"{origen} - {destino}"), align="L")
            y = pdf.get_y() + 0.05

            cfg      = rutas_config.get(ruta_lbl, {"cobrar": [], "mostrar": []})
            todos    = [(c, True) for c in cfg["cobrar"]] + [(c, False) for c in cfg["mostrar"]]

            for campo, es_cobrado in todos:
                val = safe(row.get(campo, 0))
                if val <= 0:
                    continue

                y_max = y_max_pag1 if pagina_actual == 1 else y_max_otras
                if y > y_max:
                    pdf.add_page()
                    pagina_actual += 1
                    y = 1.40

                val_show = val * tc if moneda_cot == "MXP" else val

                # Color: azul si se cobra, gris si solo visual
                if es_cobrado:
                    pdf.set_text_color(37, 45, 128)
                    pdf.set_body_font(bold=False, size=7)
                else:
                    pdf.set_text_color(150, 150, 150)
                    pdf.set_body_font(bold=False, size=7)

                # Nombre del campo
                label = campo.replace("_", " ").replace("Ingreso ", "").replace(" USA", "").title()
                label = safe_text(label[:32])

                pdf.set_xy(0.85, y); pdf.cell(3.20, 0.15, label, border=0, align="L")
                pdf.set_xy(4.00, y); pdf.cell(0.70, 0.15, "", border=0, align="C")  # KM (N/A para Lincoln)
                pdf.set_xy(5.10, y); pdf.cell(0.55, 0.15, "1" if es_cobrado else "", border=0, align="C")
                pdf.set_xy(5.85, y); pdf.cell(0.65, 0.15, moneda_cot, border=0, align="C")
                pdf.set_xy(6.55, y); pdf.cell(1.05, 0.15, f"${val_show:,.2f}", border=0, align="R")

                if es_cobrado:
                    total_global += val_show

                y += 0.18

        # ── Total (solo en última página) ─────────────────────────
        while pdf.page_no() < num_paginas:
            pdf.add_page()

        pdf.set_body_font(bold=True, size=8)
        pdf.set_text_color(0, 0, 0)
        pdf.set_xy(5.85, 9.13); pdf.cell(0.70, 0.15, moneda_cot,            border=0, align="C")
        pdf.set_xy(6.55, 9.13); pdf.cell(1.00, 0.15, f"${total_global:,.2f}", border=0, align="R")

        # Notas
        pdf.set_body_font(size=6.5)
        pdf.set_text_color(100, 100, 100)
        pdf.set_xy(0.90, 9.60); pdf.multi_cell(4.50, 0.12, safe_text(notas), align="L")

        # ── Descargar ─────────────────────────────────────────────
        nombre_cliente = re.sub(r"[^\w\-]", "_", cliente_nombre or "Cliente")
        file_name      = f"Cotizacion_Lincoln_{nombre_cliente}_{fecha.strftime('%d-%m-%Y')}.pdf"
        pdf_bytes      = pdf.output(dest="S").encode("latin-1")

        c1, c2, c3 = st.columns(3)
        c1.metric("📄 Páginas",   num_paginas)
        c2.metric("📊 Líneas",    lineas)
        c3.metric("💾 Tamaño",   f"{len(pdf_bytes)/1024:.1f} KB")

        st.success("✅ PDF generado exitosamente.")
        st.download_button(
            "📥 Descargar Cotización PDF",
            data=pdf_bytes,
            file_name=file_name,
            mime="application/pdf",
            type="primary",
            key="ln_cot_dl",
        )
