"""
cotizacion.py – Set Logis Plus
Generador de cotización formal PDF para enviar al cliente.
Estructura homologada con Lincoln Freight:
  - EMP_DEFAULTS con datos de empresa
  - TODOS_CONCEPTOS con ingresos y costos disponibles
  - Clase PDF a nivel de módulo con soporte Montserrat
  - Selector usa filtrar_rutas_setlogis + label_ruta_setlogis
  - Carga directa sin cache (datos frescos para PDF)
"""

from __future__ import annotations

import os
from datetime import date

import pandas as pd
import streamlit as st
from fpdf import FPDF  # pyright: ignore[reportMissingModuleSource]

from services.supabase_client import get_supabase_client
from ui.components import section_header, alert, divider
from ._shared import (
    TABLE_RUTAS,
    cargar_datos_generales,
    safe,
    filtrar_rutas_setlogis,
    label_ruta_setlogis,
)


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
# DEFAULTS EMPRESA
# ─────────────────────────────────────────────
EMP_DEFAULTS = {
    "nombre":    "Set Logis Plus",
    "direccion": "Carr. Apto Km 3.8 Blvd Apto. 4, América, Nuevo Laredo, Tamps. 88284",
    "mail":      "operaciones@setlogisplus.com",
    "telefono":  "+1 (956) 337-3796",
    "ext":       "",
}


# ─────────────────────────────────────────────
# TODOS LOS CONCEPTOS DISPONIBLES
# (nombre visible, columna Supabase, tipo)
# tipo: "ingreso" o "costo"
# ─────────────────────────────────────────────
TODOS_CONCEPTOS: list[tuple[str, str, str]] = [
    # Ingresos
    ("Flete USA",           "Flete_USA",           "ingreso"),
    ("Fuel",                "Fuel",                "ingreso"),
    ("Cruce",               "Ingreso_Cruce",       "ingreso"),
    ("Flete MX",            "Ingreso_MX",          "ingreso"),
    ("Extras Ingreso",      "Extras_Ingreso",      "ingreso"),
    # Costos (visibles al cliente si aplica)
    ("Owner Cargado",       "Pago_Owner_Cargado",  "costo"),
    ("Owner Vacío",         "Pago_Owner_Vacio",    "costo"),
    ("Fuel Owner",          "Pago_Fuel_Owner",     "costo"),
    ("Costo Cruce",         "Costo_Cruce",         "costo"),
    ("Costo Flete MX",      "Costo_MX",            "costo"),
    ("Extras Costo",        "Extras_Costo",        "costo"),
]


# ─────────────────────────────────────────────
# PLANTILLAS
# ─────────────────────────────────────────────
def _get_template(pagina_actual: int, total_paginas: int) -> str | None:
    img_dir = _img_dir()
    if total_paginas == 1:
        nombre = "2.0 ADT PGL SLPlus.png"
    elif total_paginas == 2:
        nombre = "2.0 ADT PGL SLPlus (2).png" if pagina_actual == 1 else "2.0 ADT PGL SLPlus (4).png"
    else:
        if pagina_actual == 1:
            nombre = "2.0 ADT PGL SLPlus (2).png"
        elif pagina_actual == total_paginas:
            nombre = "2.0 ADT PGL SLPlus (4).png"
        else:
            nombre = "2.0 ADT PGL SLPlus (3).png"
    path = os.path.join(img_dir, nombre)
    return path if os.path.exists(path) else None


def _estimar_paginas(lineas: int) -> int:
    LINEAS_PAG1  = 20
    LINEAS_OTRAS = 30
    if lineas <= LINEAS_PAG1:
        return 1
    return 1 + (lineas - LINEAS_PAG1 + LINEAS_OTRAS - 1) // LINEAS_OTRAS


def _calcular_lineas(filas: list) -> int:
    total = 0
    for fila in filas:
        total += 2  # header ruta
        for c in fila.get("conceptos", []):
            if c.get("valor", 0) != 0:
                total += 1
    return total


# ─────────────────────────────────────────────
# CARGA DIRECTA — sin cache (datos frescos para PDF)
# ─────────────────────────────────────────────
def _cargar_rutas(table: str) -> pd.DataFrame:
    sb = get_supabase_client()
    if sb is None:
        return pd.DataFrame()
    try:
        resp = sb.table(table).select("*").order("Fecha", desc=True).execute()
    except Exception:
        return pd.DataFrame()
    df = pd.DataFrame(resp.data or [])
    if not df.empty and "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d")
    return df


# ─────────────────────────────────────────────
# CLASE PDF — nivel de módulo, con Montserrat
# ─────────────────────────────────────────────
class PDF(FPDF):
    def __init__(self, fecha_str: str = "", total_pages: int = 1, **kwargs):
        super().__init__(orientation="P", unit="in", format="Letter", **kwargs)
        self.set_compression(False)
        self.fecha_str   = fecha_str
        self.total_pages = total_pages
        self.has_montserrat = False
        try:
            fonts = _fonts_dir()
            reg  = os.path.join(fonts, "Montserrat-Regular.ttf")
            bold = os.path.join(fonts, "Montserrat-Bold.ttf")
            it   = os.path.join(fonts, "Montserrat-Italic.ttf")
            if os.path.exists(reg):
                self.add_font("Montserrat", "",  reg,  uni=True)
                self.has_montserrat = True
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
                self.set_font("Helvetica", style, size)
        else:
            self.set_font("Helvetica", style, size)

    def header(self):
        tpl = _get_template(self.page_no(), self.total_pages)
        if tpl:
            self.image(tpl, x=0, y=0, w=8.5, h=11)

    def footer(self):
        # Número de página
        pagina_actual = self.page_no()
        self.set_body_font(bold=False, size=8)
        self.set_text_color(80, 80, 80)
        self.set_xy(0.90, 1.10)
        self.cell(1.2, 0.12, safe_text(self.fecha_str), align="L")
        self.set_xy(1.21, 10.14)
        self.cell(0.20, 0.12, str(pagina_actual), align="C")
        self.set_xy(1.51, 10.14)
        self.cell(0.20, 0.12, str(self.total_pages), align="C")
        self.set_text_color(0, 0, 0)


# ─────────────────────────────────────────────
# GENERADOR PDF
# ─────────────────────────────────────────────
def _generar_pdf(
    *,
    fecha_cot,
    cli_nombre, cli_dir, cli_mail, cli_tel, cli_ext,
    emp_nombre, emp_dir, emp_mail, emp_tel, emp_ext,
    moneda, tc,
    filas,
    notas,
) -> bytes:

    lineas_totales = _calcular_lineas(filas)
    total_pages    = _estimar_paginas(lineas_totales)

    pdf = PDF(
        fecha_str  = fecha_cot.strftime("%d/%m/%Y"),
        total_pages= total_pages,
    )
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()

    # ── Cliente / Empresa ──────────────────────────────────────────
    pdf.set_body_font(size=10)

    pdf.set_xy(0.85, 2.05); pdf.multi_cell(2.89, 0.24, safe_text(cli_nombre), align="L")
    pdf.set_xy(0.85, 2.66); pdf.multi_cell(2.89, 0.18, safe_text(cli_dir),    align="L")
    pdf.set_xy(0.85, 3.20); pdf.multi_cell(2.89, 0.31, safe_text(cli_mail),   align="L")
    pdf.set_xy(0.85, 3.60); pdf.cell(1.35, 0.31, safe_text(cli_tel), align="L")
    pdf.set_xy(2.39, 3.60); pdf.cell(0.76, 0.31, safe_text(cli_ext), align="C")

    pdf.set_xy(4.76, 2.05); pdf.multi_cell(2.89, 0.24, safe_text(emp_nombre), align="R")
    pdf.set_xy(4.76, 2.66); pdf.multi_cell(2.89, 0.18, safe_text(emp_dir),    align="R")
    pdf.set_xy(4.76, 3.20); pdf.multi_cell(2.89, 0.31, safe_text(emp_mail),   align="R")
    pdf.set_xy(5.23, 3.60); pdf.cell(1.35, 0.31, safe_text(emp_tel),           align="R")
    pdf.set_xy(7.03, 3.60); pdf.cell(0.76, 0.31, safe_text(emp_ext),           align="C")

    # Fecha
    pdf.set_body_font(bold=False, size=9)
    pdf.set_text_color(120, 120, 120)
    pdf.set_xy(0.85, 1.28)
    pdf.cell(3.0, 0.18, safe_text(fecha_cot.strftime("%d/%m/%Y")), border=0, align="L")
    pdf.set_text_color(0, 0, 0)

    # ── Conceptos ─────────────────────────────────────────────────
    y             = 4.50
    y_max_pag1    = 8.20
    y_max_otras   = 8.80
    total_global  = 0.0
    pagina_actual = 1

    for fila in filas:
        kms_fila    = fila.get("kms", "")
        ruta_label  = fila.get("ruta_label", {})
        tipo_ruta   = ruta_label.get("tipo",    "")
        origen      = ruta_label.get("origen",  "")
        destino     = ruta_label.get("destino", "")
        cliente_txt = ruta_label.get("cliente", "")

        y_max = y_max_pag1 if pagina_actual == 1 else y_max_otras

        if y + 0.35 > y_max:
            pdf.add_page()
            pagina_actual += 1
            y = 2.00

        # Header ruta
        pdf.set_body_font(bold=True, size=7)
        pdf.set_text_color(128, 128, 128)
        pdf.set_xy(0.85, y)
        pdf.multi_cell(7, 0.15, safe_text(tipo_ruta), align="L")
        y = pdf.get_y()

        segunda_linea = f"{origen} → {destino} — {cliente_txt}"
        pdf.set_xy(0.85, y)
        pdf.multi_cell(7, 0.15, safe_text(segunda_linea), align="L")
        y = pdf.get_y() + 0.05
        pdf.set_text_color(0, 0, 0)

        for c in fila.get("conceptos", []):
            y_max = y_max_pag1 if pagina_actual == 1 else y_max_otras

            if y > y_max:
                pdf.add_page()
                pagina_actual += 1
                y = 1.40

            valor = float(c.get("valor", 0))
            valor_show = valor * tc if moneda == "MXP" else valor

            pdf.set_body_font(size=7)

            pdf.set_xy(0.85, y)
            pdf.cell(3.20, 0.15, safe_text(c.get("nombre", "")), border=0, align="L")

            pdf.set_xy(4.00, y)
            pdf.cell(0.70, 0.15, safe_text(str(kms_fila) if kms_fila else ""), border=0, align="C")

            pdf.set_xy(5.10, y)
            pdf.cell(0.55, 0.15, "1", border=0, align="C")

            pdf.set_xy(5.85, y)
            pdf.cell(0.65, 0.15, moneda, border=0, align="C")

            pdf.set_xy(6.55, y)
            pdf.cell(1.05, 0.15, f"${valor_show:,.2f}", border=0, align="R")

            total_global += valor_show
            y += 0.16

    # Rellenar páginas si faltan
    while pdf.page_no() < total_pages:
        pdf.add_page()

    # Total
    pdf.set_body_font(bold=True, size=8)
    pdf.set_xy(5.85, 9.13)
    pdf.cell(0.70, 0.15, moneda, align="C")
    pdf.set_xy(6.55, 9.13)
    pdf.cell(1.00, 0.15, f"${total_global:,.2f}", align="R")

    # Notas
    pdf.set_body_font(size=6.5)
    pdf.set_xy(0.90, 9.60)
    pdf.multi_cell(4.20, 0.11, safe_text(notas))

    return pdf.output(dest="S").encode("latin-1")


# ─────────────────────────────────────────────
# RENDER
# ─────────────────────────────────────────────
def render() -> None:
    supabase = get_supabase_client()
    if supabase is None:
        alert("warn", "⚠️ Supabase no configurado.")
        return

    # Recargar
    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("🔄 Recargar rutas", key="sl_cot_reload"):
            st.rerun()
    with c2:
        st.caption("Siempre carga datos frescos — sin cache.")

    df = _cargar_rutas(TABLE_RUTAS)
    if df.empty:
        alert("warn", "⚠️ No hay rutas guardadas.")
        alert("info", "💡 Captura rutas primero para poder generar cotizaciones.")
        return

    valores = cargar_datos_generales()

    # ── Filtros — igual que Lincoln ────────────────────────────────
    with st.expander("🔍 Filtros de búsqueda", expanded=False):
        df_fil = filtrar_rutas_setlogis(df, "sl_cot")
    if df_fil.empty:
        alert("warn", "⚠️ No hay rutas con esos filtros.")
        return

    # ── Selector de rutas a incluir ────────────────────────────────
    section_header("📋", "Selecciona Rutas a Cotizar")

    opciones = df_fil["ID_Ruta"].dropna().astype(str).tolist()
    st.caption(f"Rutas disponibles: **{len(opciones)}**")

    ids_sel = st.multiselect(
        "Rutas a incluir en la cotización",
        options=opciones,
        format_func=lambda i: label_ruta_setlogis(
            df_fil[df_fil["ID_Ruta"] == i].iloc[0].to_dict()
        ),
        key="sl_cot_ids",
    )
    if not ids_sel:
        alert("info", "Selecciona al menos una ruta para continuar.")
        return

    df_sel = df_fil[df_fil["ID_Ruta"].isin(ids_sel)].set_index("ID_Ruta", drop=False)

    # ── Cliente / Empresa ──────────────────────────────────────────
    divider()
    section_header("📝", "Datos del Documento")

    col_cli, col_emp = st.columns(2)
    with col_cli:
        st.markdown("**👤 Cliente**")
        cli_nombre = st.text_input("Nombre",    key="sl_cot_cli_nombre")
        cli_dir    = st.text_input("Dirección", key="sl_cot_cli_dir")
        cli_mail   = st.text_input("Email",     key="sl_cot_cli_mail")
        cc1, cc2   = st.columns(2)
        cli_tel    = cc1.text_input("Teléfono", key="sl_cot_cli_tel")
        cli_ext    = cc2.text_input("Ext.",     key="sl_cot_cli_ext")

    with col_emp:
        st.markdown("**🏢 Empresa (Set Logis)**")
        emp_nombre = st.text_input("Nombre",    value=EMP_DEFAULTS["nombre"],    key="sl_cot_emp_nombre")
        emp_dir    = st.text_input("Dirección", value=EMP_DEFAULTS["direccion"], key="sl_cot_emp_dir")
        emp_mail   = st.text_input("Email",     value=EMP_DEFAULTS["mail"],      key="sl_cot_emp_mail")
        ec1, ec2   = st.columns(2)
        emp_tel    = ec1.text_input("Teléfono", value=EMP_DEFAULTS["telefono"],  key="sl_cot_emp_tel")
        emp_ext    = ec2.text_input("Ext.",     value=EMP_DEFAULTS["ext"],       key="sl_cot_emp_ext")

    divider()
    dc1, dc2, dc3 = st.columns(3)
    fecha_cot = dc1.date_input("📅 Fecha cotización", value=date.today(), key="sl_cot_fecha")
    moneda    = dc2.selectbox("💱 Moneda",            ["USD", "MXP"],     key="sl_cot_moneda")
    tc_val    = float(valores.get("Tipo de Cambio USD/MXP", 18.50))
    tc        = dc3.number_input("TC USD/MXP", value=tc_val, step=0.01, format="%.4f", key="sl_cot_tc")

    # ── Configuración de conceptos por ruta ───────────────────────
    divider()
    section_header("⚙️", "Configurar Conceptos por Ruta")

    rutas_config: dict = {}

    for id_ruta in ids_sel:
        if id_ruta not in df_sel.index:
            continue

        row = df_sel.loc[id_ruta]

        # Construir catálogo de conceptos disponibles con valor > 0
        catalogo: dict[str, tuple[str, float]] = {}
        for nombre_vis, columna, _ in TODOS_CONCEPTOS:
            val = safe(row.get(columna, 0))
            if val > 0:
                catalogo[nombre_vis] = (columna, val)

        etiqueta = label_ruta_setlogis(row.to_dict())
        with st.expander(f"📍 {etiqueta}", expanded=True):
            kms = st.text_input(
                "Kms / Millas (opcional)",
                value=str(int(safe(row.get("Miles_Load", 0)))) if safe(row.get("Miles_Load", 0)) > 0 else "",
                key=f"sl_cot_kms_{id_ruta}",
            )

            if not catalogo:
                st.caption("⚠️ Esta ruta no tiene conceptos con valor > 0.")
                rutas_config[id_ruta] = {"cobrar": [], "mostrar": [], "row": row, "kms": kms}
                continue

            todas_labels = list(catalogo.keys())

            # Default: ingresos en "Sumar", costos en ninguno
            defaults_sumar = [
                lbl for lbl, (campo, _) in catalogo.items()
                if any(campo == c for _, c, t in TODOS_CONCEPTOS if t == "ingreso")
            ]

            col_az, col_gr = st.columns(2)
            with col_az:
                st.markdown("**➕ Sumar al total (Azul)**")
                sel_sumar = st.multiselect(
                    "Selecciona conceptos que suman al total",
                    options=todas_labels,
                    default=[l for l in defaults_sumar if l in todas_labels],
                    key=f"sl_cot_sumar_{id_ruta}",
                    label_visibility="collapsed",
                )
            with col_gr:
                st.markdown("**👁️ Mostrar sin sumar (Gris)**")
                disponibles_gris = [l for l in todas_labels if l not in sel_sumar]
                sel_mostrar = st.multiselect(
                    "Selecciona conceptos que solo se muestran",
                    options=disponibles_gris,
                    default=[],
                    key=f"sl_cot_mostrar_{id_ruta}",
                    label_visibility="collapsed",
                )

            rutas_config[id_ruta] = {
                "cobrar":   [catalogo[l][0] for l in sel_sumar],
                "mostrar":  [catalogo[l][0] for l in sel_mostrar],
                "catalogo": catalogo,
                "row":      row,
                "kms":      kms,
            }

    # ── Notas ──────────────────────────────────────────────────────
    divider()
    notas_default = (
        "Precios sujetos a disponibilidad de unidades. "
        "Cotización válida por 5 días hábiles. "
        "No aplica IVA en servicios de exportación e importación (tasa 0)."
    )
    notas = st.text_area(
        "📝 Notas / Términos y Condiciones",
        value=notas_default,
        height=80,
        key="sl_cot_notas",
    )

    # ── Generar PDF ────────────────────────────────────────────────
    divider()
    if not cli_nombre.strip():
        alert("warn", "Ingresa el nombre del cliente para continuar.")
        return

    if st.button("📄 Generar PDF", type="primary", use_container_width=True, key="sl_cot_gen"):
        filas = []
        for id_ruta in ids_sel:
            if id_ruta not in rutas_config:
                continue
            cfg = rutas_config[id_ruta]
            row = cfg["row"]
            conceptos = []
            for nombre_vis, columna, _ in TODOS_CONCEPTOS:
                if columna in cfg["cobrar"] or columna in cfg["mostrar"]:
                    val = safe(row.get(columna, 0))
                    conceptos.append({
                        "nombre": nombre_vis,
                        "valor":  val if columna in cfg["cobrar"] else 0,
                        "mostrar_solo": columna in cfg["mostrar"],
                    })

            filas.append({
                "ruta_label": {
                    "tipo":    str(row.get("Tipo_Viaje", "")),
                    "origen":  str(row.get("Origen",    "")),
                    "destino": str(row.get("Destino",   "")),
                    "cliente": str(row.get("Cliente",   "")),
                },
                "kms":       cfg.get("kms", ""),
                "conceptos": conceptos,
            })

        try:
            pdf_bytes = _generar_pdf(
                fecha_cot  = fecha_cot,
                cli_nombre = cli_nombre,
                cli_dir    = cli_dir,
                cli_mail   = cli_mail,
                cli_tel    = cli_tel,
                cli_ext    = cli_ext,
                emp_nombre = emp_nombre,
                emp_dir    = emp_dir,
                emp_mail   = emp_mail,
                emp_tel    = emp_tel,
                emp_ext    = emp_ext,
                moneda     = moneda,
                tc         = tc,
                filas      = filas,
                notas      = notas,
            )

            nombre_pdf = (
                f"Cotizacion_SetLogis_{cli_nombre.replace(' ','_')}"
                f"_{fecha_cot.strftime('%Y%m%d')}.pdf"
            )
            st.download_button(
                label="📥 Descargar PDF",
                data=pdf_bytes,
                file_name=nombre_pdf,
                mime="application/pdf",
                use_container_width=True,
                key="sl_cot_dl",
            )
        except Exception as ex:
            alert("error", f"❌ Error generando PDF: {ex}")
