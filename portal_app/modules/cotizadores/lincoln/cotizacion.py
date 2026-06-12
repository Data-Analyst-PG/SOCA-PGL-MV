"""
cotizacion.py – Lincoln Freight (USA/MX)
- Cliente/Empresa en 2 columnas (sin tabs)
- Defaults de empresa precargados
- Todos los campos con valor > 0 disponibles (ingresos + costos)
- Solo aparecen conceptos con monto capturado > 0
- PDF con plantilla PNG igual que Igloo/Picus/Set Logis
"""

from __future__ import annotations

import ast
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
# DEFAULTS EMPRESA
# ─────────────────────────────────────────────
EMP_DEFAULTS = {
    "nombre":    "Lincoln Freight LLC",
    "direccion": "Carr. Apto Km 3.8 Blvd Apto. 4, América, Nuevo Laredo, Tamps. 88284",
    "mail":      "xochitl.ceron@lincoln-freight.com",
    "telefono":  "+1 (956) 337-3796",
    "ext":       "1138",
}


# ─────────────────────────────────────────────
# TODOS LOS CONCEPTOS DISPONIBLES
# (nombre visible, columna Supabase, tipo)
# tipo: "ingreso" o "costo"
# ─────────────────────────────────────────────
TODOS_CONCEPTOS: list[tuple[str, str, str]] = [
    # Ingresos
    ("Flete USA",           "Ingreso_Flete_USA",    "ingreso"),
    ("Fuel Surcharge",      "Ingreso_Fuel_USA",     "ingreso"),
    ("Cruce",               "Ingreso_Cruce",        "ingreso"),
    ("Flete MX",            "Ingreso_MX_USD",       "ingreso"),
    ("Otros Cargos",        "Otros_Cargos_Ingreso", "ingreso"),
    # Costos (pueden cotizarse al cliente si aplica)
    ("Diesel",              "Diesel_USA",           "costo"),
    ("Sueldo Operador",     "Sueldo_Operador",      "costo"),
    ("ISR/IMSS",            "ISR_IMSS",             "costo"),
    ("Costo Cruce",         "Costo_Cruce",          "costo"),
    ("Costo Flete MX",      "Costo_MX_USD",         "costo"),
    ("Otros Cargos Costo",  "Otros_Cargos_Costo",   "costo"),
]


# ─────────────────────────────────────────────
# PLANTILLAS (igual que Igloo)
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
    # Pág 1: y=4.50 → y=8.55  → (8.55-4.50)/0.18 ≈ 22 líneas
    # Pág 2+: y=2.10 → y=9.15 → (9.15-2.10)/0.18 ≈ 39 líneas
    LINEAS_PAG1  = 22
    LINEAS_OTRAS = 39
    if lineas <= LINEAS_PAG1:
        return 1
    return 1 + (lineas - LINEAS_PAG1 + LINEAS_OTRAS - 1) // LINEAS_OTRAS


# ─────────────────────────────────────────────
# CLASE PDF
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
        tpl = _get_template(self.page_no(), self.total_pages)
        if tpl:
            self.image(tpl, x=0, y=0, w=8.5, h=11)

    def footer(self):
        pass


# ─────────────────────────────────────────────
# CACHE RUTAS
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

    # ── Cliente / Empresa en 2 columnas (sin tabs) ────────────────
    divider()
    section_header("👥", "Datos del Cliente y la Empresa")
    col_cli, col_emp = st.columns(2)

    with col_cli:
        st.markdown("**👤 Cliente**")
        cliente_nombre    = st.text_input("Nombre *",      key="ln_cot_cli_nom",  placeholder="NOMBRE DE LA EMPRESA")
        cliente_direccion = st.text_input("Dirección",     key="ln_cot_cli_dir")
        cliente_mail      = st.text_input("📧 Email",      key="ln_cot_cli_mail")
        cliente_telefono  = st.text_input("📞 Teléfono",   key="ln_cot_cli_tel")
        cliente_ext       = st.text_input("Ext.",          key="ln_cot_cli_ext")

    with col_emp:
        st.markdown("**🏢 Empresa**")
        empresa_nombre    = st.text_input("Nombre",    value=EMP_DEFAULTS["nombre"],    key="ln_cot_emp_nom")
        empresa_direccion = st.text_input("Dirección", value=EMP_DEFAULTS["direccion"], key="ln_cot_emp_dir")
        empresa_mail      = st.text_input("📧 Email",  value=EMP_DEFAULTS["mail"],      key="ln_cot_emp_mail")
        empresa_telefono  = st.text_input("📞 Teléfono", value=EMP_DEFAULTS["telefono"], key="ln_cot_emp_tel")
        empresa_ext       = st.text_input("Ext.",      value=EMP_DEFAULTS["ext"],       key="ln_cot_emp_ext")

    divider()

    # ── Moneda ────────────────────────────────────────────────────
    mc1, mc2 = st.columns(2)
    moneda_cot = mc1.selectbox("💱 Moneda de cotización", ["USD", "MXP"], key="ln_cot_moneda")
    tc = float(valores.get("Tipo de Cambio USD/MXP", 18.5))
    if moneda_cot == "MXP":
        tc = mc2.number_input("Tipo de Cambio USD/MXP", value=tc, step=0.1, key="ln_cot_tc")

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
    section_header("2.", "Configuración de Conceptos")
    st.caption(
        "Solo aparecen conceptos con monto > 0. "
        "Selecciona qué va en **Sumar al total (azul)** y qué va en **Mostrar sin sumar (gris)**. "
        "Lo que no selecciones en ninguna lista no aparece en el PDF."
    )

    rutas_config: dict = {}

    for ruta_lbl in ids_sel:
        id_ruta = ruta_lbl.split(" | ")[0]
        if id_ruta not in df.index:
            continue

        row  = df.loc[id_ruta]
        tipo = str(row.get("Tipo", ""))

        # ── Construir catálogo de conceptos disponibles (valor > 0) ──
        # Formato: {label_display: (campo_key, valor_usd)}
        catalogo: dict[str, tuple[str, float]] = {}

        for nombre, campo, tipo_concepto in TODOS_CONCEPTOS:
            if campo == "Ingreso_MX_USD" and tipo not in {"D2DNB", "D2DSB"}:
                continue
            if campo == "Costo_MX_USD" and tipo not in {"D2DNB", "D2DSB"}:
                continue
            # Omitir genérico Otros_Cargos_Ingreso si hay extras individuales
            val = safe(row.get(campo, 0))
            if val > 0:
                val_show = val * tc if moneda_cot == "MXP" else val
                label    = f"{nombre}  (${val_show:,.2f} {moneda_cot})"
                catalogo[label] = (campo, val)

        # Extras individuales del JSON
        extras_json: dict = {}
        json_str = str(row.get("Otros_Cargos_JSON", "") or "")
        if json_str not in ("", "None", "{}"):
            try:
                extras_json = ast.literal_eval(json_str)
            except Exception:
                pass
        # Si hay extras individuales, quitar el genérico Otros_Cargos_Ingreso
        if extras_json:
            catalogo = {k: v for k, v in catalogo.items() if v[0] != "Otros_Cargos_Ingreso"}
        for nombre_e, monto_e in extras_json.items():
            if safe(monto_e) <= 0:
                continue
            val_show = safe(monto_e) * tc if moneda_cot == "MXP" else safe(monto_e)
            label    = f"{nombre_e}  (${val_show:,.2f} {moneda_cot})"
            catalogo[label] = (f"__extra_{nombre_e}", safe(monto_e))

        with st.expander(f"📋 Configurar: {ruta_lbl}", expanded=True):
            if not catalogo:
                st.caption("No hay conceptos con monto capturado para esta ruta.")
                rutas_config[ruta_lbl] = {"cobrar": [], "mostrar": [], "row": row, "extras": extras_json}
                continue

            todas_labels = list(catalogo.keys())

            # Defaults: ingresos van en Sumar, costos en ninguno
            defaults_sumar = [
                lbl for lbl, (campo, _) in catalogo.items()
                if any(campo == c for _, c, t in TODOS_CONCEPTOS if t == "ingreso")
                   or campo.startswith("__extra_")
            ]

            col_az, col_gr = st.columns(2)
            with col_az:
                st.markdown("**➕ Sumar al total (Azul)**")
                sel_sumar = st.multiselect(
                    "Selecciona conceptos que suman al total",
                    options=todas_labels,
                    default=[l for l in defaults_sumar if l in todas_labels],
                    key=f"ln_cot_sumar_{id_ruta}",
                    label_visibility="collapsed",
                )
            with col_gr:
                st.markdown("**👁️ Mostrar sin sumar (Gris)**")
                # Solo pueden elegir mostrar los que NO están en sumar
                disponibles_gris = [l for l in todas_labels if l not in sel_sumar]
                sel_mostrar = st.multiselect(
                    "Selecciona conceptos que solo se muestran",
                    options=disponibles_gris,
                    default=[],
                    key=f"ln_cot_mostrar_{id_ruta}",
                    label_visibility="collapsed",
                )

            # Convertir labels → campos
            cobrar  = [catalogo[l][0] for l in sel_sumar]
            mostrar = [catalogo[l][0] for l in sel_mostrar]

            rutas_config[ruta_lbl] = {
                "cobrar":   cobrar,
                "mostrar":  mostrar,
                "catalogo": catalogo,
                "row":      row,
                "extras":   extras_json,
            }

    # ── Notas ─────────────────────────────────────────────────────
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
    if not cliente_nombre.strip():
        alert("warn", "Ingresa el nombre del cliente para continuar.")
        return

    if st.button("📄 Generar Cotización PDF", type="primary",
                 use_container_width=True, key="ln_cot_gen"):

        # Calcular número de líneas para estimar páginas
        lineas = 0
        for ruta_lbl in ids_sel:
            id_ruta = ruta_lbl.split(" | ")[0]
            if id_ruta not in df.index:
                continue
            cfg = rutas_config.get(ruta_lbl, {})
            lineas += 2  # header tipo + origen-destino
            lineas += len(cfg.get("cobrar", [])) + len(cfg.get("mostrar", []))

        num_paginas = _estimar_paginas(lineas)

        pdf = PDF(
            orientation="P", unit="in", format="Letter",
            fecha_str=fecha.strftime("%d/%m/%Y"),
            total_pages=num_paginas,
        )
        pdf.set_auto_page_break(auto=False)
        pdf.add_page()

        # Datos cliente / empresa — pág 1
        pdf.set_body_font(size=10)
        pdf.set_text_color(0, 0, 0)
        pdf.set_xy(0.85, 2.05); pdf.multi_cell(2.89, 0.24, safe_text(cliente_nombre),    align="L")
        pdf.set_xy(0.85, 2.66); pdf.multi_cell(2.89, 0.18, safe_text(cliente_direccion), align="L")
        pdf.set_xy(0.85, 3.20); pdf.multi_cell(2.89, 0.31, safe_text(cliente_mail),      align="L")
        pdf.set_xy(0.85, 3.60); pdf.cell(1.35, 0.31, safe_text(cliente_telefono), align="L")
        pdf.set_xy(2.39, 3.60); pdf.cell(0.76, 0.31, safe_text(cliente_ext),      align="C")
        pdf.set_xy(4.76, 2.05); pdf.multi_cell(2.89, 0.24, safe_text(empresa_nombre),    align="R")
        pdf.set_xy(4.76, 2.66); pdf.multi_cell(2.89, 0.18, safe_text(empresa_direccion), align="R")
        pdf.set_xy(4.76, 3.20); pdf.multi_cell(2.89, 0.31, safe_text(empresa_mail),      align="R")
        pdf.set_xy(5.23, 3.60); pdf.cell(1.35, 0.31, safe_text(empresa_telefono), align="R")
        pdf.set_xy(7.03, 3.60); pdf.cell(0.76, 0.31, safe_text(empresa_ext),      align="C")

        # Fecha en plantilla (coordenada "DOCUMENT ISSUE DATE")
        pdf.set_body_font(bold=False, size=9)
        pdf.set_text_color(120, 120, 120)
        pdf.set_xy(0.85, 1.28)
        pdf.cell(3.0, 0.18, safe_text(fecha.strftime("%d/%m/%Y")), border=0, align="L")
        pdf.set_text_color(0, 0, 0)

        # Conceptos
        y             = 4.50
        y_max_pag1    = 8.55   # espacio real antes del área de total en pág única/primera
        y_max_otras   = 9.15   # páginas intermedias tienen más espacio
        total_global  = 0.0
        pagina_actual = 1

        for ruta_lbl in ids_sel:
            id_ruta = ruta_lbl.split(" | ")[0]
            if id_ruta not in df.index:
                continue

            cfg    = rutas_config.get(ruta_lbl, {})
            row    = cfg.get("row", df.loc[id_ruta])
            extras = cfg.get("extras", {})
            origen  = str(row.get("Origen", ""))
            destino = str(row.get("Destino", ""))
            tipo_r  = str(row.get("Tipo", ""))
            y_max   = y_max_pag1 if pagina_actual == 1 else y_max_otras

            if y + 0.35 > y_max:
                pdf.add_page(); pagina_actual += 1; y = 2.10

            # Header ruta
            pdf.set_body_font(bold=True, size=7)
            pdf.set_text_color(128, 128, 128)
            pdf.set_xy(0.85, y); pdf.multi_cell(7, 0.15, safe_text(tipo_r), align="L")
            y = pdf.get_y()
            pdf.set_xy(0.85, y); pdf.multi_cell(7, 0.15, safe_text(f"{origen} - {destino}"), align="L")
            y = pdf.get_y() + 0.05

            # Unir cobrar y mostrar en orden
            todos_campos = [(c, True) for c in cfg.get("cobrar", [])] + \
                           [(c, False) for c in cfg.get("mostrar", [])]
            catalogo = cfg.get("catalogo", {})

            for campo, es_cobrado in todos_campos:
                # Obtener valor y label desde el catálogo si está disponible
                label_display = None
                for lbl, (c, v) in catalogo.items():
                    if c == campo:
                        # Limpiar el label (quitar el monto al final)
                        label_display = lbl.split("  ($")[0]
                        break

                if campo.startswith("__extra_"):
                    nombre_e = campo[8:]
                    val      = safe(extras.get(nombre_e, 0))
                    label    = safe_text((label_display or nombre_e)[:32])
                else:
                    label = safe_text((label_display or campo.replace("_", " ").title())[:32])
                    val   = safe(row.get(campo, 0))

                if val <= 0:
                    continue

                y_max = y_max_pag1 if pagina_actual == 1 else y_max_otras
                if y > y_max:
                    pdf.add_page(); pagina_actual += 1; y = 2.10

                val_show = val * tc if moneda_cot == "MXP" else val

                if es_cobrado:
                    pdf.set_text_color(37, 45, 128)
                else:
                    pdf.set_text_color(150, 150, 150)
                pdf.set_body_font(bold=False, size=7)

                # Millas solo en Flete USA (Miles_Load)
                miles_txt = ""
                if campo == "Ingreso_Flete_USA":
                    ml = safe(row.get("Miles_Load") or row.get("Millas_USA", 0))
                    if ml > 0:
                        miles_txt = f"{ml:,.0f}"

                pdf.set_xy(0.85, y); pdf.cell(3.20, 0.15, label,        border=0, align="L")
                pdf.set_xy(4.00, y); pdf.cell(0.70, 0.15, miles_txt,    border=0, align="C")
                pdf.set_xy(5.10, y); pdf.cell(0.55, 0.15, "1" if es_cobrado else "", border=0, align="C")
                pdf.set_xy(5.85, y); pdf.cell(0.65, 0.15, moneda_cot,   border=0, align="C")
                pdf.set_xy(6.55, y); pdf.cell(1.05, 0.15, f"${val_show:,.2f}", border=0, align="R")

                if es_cobrado:
                    total_global += val_show
                y += 0.18

        # Total y notas — siempre en la página actual si es página única,
        # o en la última página si hay más de una
        # No agregar página extra si ya estamos en la correcta
        pagina_total = num_paginas
        if pdf.page_no() < pagina_total:
            while pdf.page_no() < pagina_total:
                pdf.add_page()

        # Coordenada Y del total: en pág única usa la zona de total de la plantilla base
        # En última página (plantilla 4) el total está en y=9.13
        y_total = 9.13
        y_notas = 9.60

        pdf.set_body_font(bold=True, size=8)
        pdf.set_text_color(0, 0, 0)
        pdf.set_xy(5.85, y_total); pdf.cell(0.70, 0.15, moneda_cot,              border=0, align="C")
        pdf.set_xy(6.55, y_total); pdf.cell(1.00, 0.15, f"${total_global:,.2f}", border=0, align="R")

        # Notas
        pdf.set_body_font(size=6.5)
        pdf.set_text_color(100, 100, 100)
        pdf.set_xy(0.90, y_notas); pdf.multi_cell(4.50, 0.12, safe_text(notas), align="L")

        # Descargar
        nombre_cli = re.sub(r"[^\w\-]", "_", cliente_nombre or "Cliente")
        file_name  = f"Cotizacion_Lincoln_{nombre_cli}_{fecha.strftime('%d-%m-%Y')}.pdf"
        pdf_bytes  = pdf.output(dest="S").encode("latin-1")

        c1, c2, c3 = st.columns(3)
        c1.metric("📄 Páginas", num_paginas)
        c2.metric("📊 Líneas",  lineas)
        c3.metric("💾 Tamaño",  f"{len(pdf_bytes)/1024:.1f} KB")

        st.success("✅ PDF generado exitosamente.")
        st.download_button(
            "📥 Descargar Cotización PDF",
            data=pdf_bytes,
            file_name=file_name,
            mime="application/pdf",
            type="primary",
            key="ln_cot_dl",
        )
