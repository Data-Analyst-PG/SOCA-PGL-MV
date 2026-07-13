"""
cotizacion.py — Cotizador Picus
Genera cotizaciones en PDF con plantillas PNG de Picus.
  - Carga rutas directamente de Supabase (sin cache — datos frescos para el PDF)
  - Filtros opcionales para seleccionar rutas
  - Configuración de conceptos por ruta (cobrados vs solo visual)
  - Sistema de plantillas múltiples según número de páginas
  - Sin lógica de cálculo de utilidades — este módulo solo genera documentos

Homologado (Paso 6):
  - class PDF(FPDF) movida a nivel de módulo (antes vivía anidada dentro de
    render()). Mismo comportamiento exacto, mismas coordenadas, mismo diseño
    — NO se tocó la plantilla ni el layout del PDF.
"""
from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
from fpdf import FPDF  # pyright: ignore[reportMissingModuleSource]

from services.supabase_client import get_supabase_client
from ui.components import section_header, alert, divider


# ---------------------------
# ETIQUETAS VISIBLES
# ---------------------------
DISPLAY_LABELS = {
    "Ingreso_Original": "Flete",
    "Cruce_Original": "Cruce",
}
def label_de(campo: str) -> str:
    return DISPLAY_LABELS.get(campo, campo.replace("_", " ").title())


def convertir_moneda(valor, origen, destino, tipo_cambio):
    if origen == destino:
        return float(valor)
    if origen == "MXP" and destino == "USD":
        return float(valor) / tipo_cambio
    if origen == "USD" and destino == "MXP":
        return float(valor) * tipo_cambio
    return float(valor)

def safe_text(text):
    return str(text).encode("latin-1", "replace").decode("latin-1")

def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

def _img_dir() -> str:
    return os.path.join(_project_root(), "img")

def _fonts_dir() -> str:
    return os.path.join(_project_root(), "fonts")


# ---------------------------
# SISTEMA DE PLANTILLAS MÚLTIPLES
# ---------------------------
def _get_template_for_page(pagina_actual: int, total_paginas: int):
    """
    Devuelve la plantilla correcta según la posición de la página.
    Lógica:
    - Si solo hay 1 página total: usar plantilla básica
    - Si hay 2+ páginas:
        - Primera página: plantilla (2) con headers de cliente/empresa
        - Páginas intermedias: plantilla (3) solo con tabla
        - Última página: plantilla (4) con tabla y totales
    """
    img_dir = _img_dir()

    if total_paginas == 1:
        nombre = "2.0 ADT PGL PICUS.png"

    elif total_paginas == 2:
        if pagina_actual == 1:
            nombre = "2.0 ADT PGL PICUS (2).png"
        else:
            nombre = "2.0 ADT PGL PICUS (4).png"

    else:
        if pagina_actual == 1:
            nombre = "2.0 ADT PGL PICUS (2).png"
        elif pagina_actual == total_paginas:
            nombre = "2.0 ADT PGL PICUS (4).png"
        else:
            nombre = "2.0 ADT PGL PICUS (3).png"

    path = os.path.join(img_dir, nombre)

    if os.path.exists(path):
        return path

    # Si no existe, informar pero continuar
    st.warning(f"⚠️ No se encontró: {nombre}")
    return None


# ---------------------------
# CÁLCULO DE ESPACIO NECESARIO
# ---------------------------
def calcular_lineas_necesarias(rutas_config, ids_seleccionados, df):
    """
    Calcula cuántas líneas necesitaremos para todos los conceptos.
    Esto ayuda a decidir cuántas páginas se necesitan.
    """
    lineas_totales = 0

    for ruta_sel in ids_seleccionados:
        id_ruta = ruta_sel.split(" | ")[0]
        if id_ruta not in df.index:
            continue

        ruta_data = df.loc[id_ruta]

        # 2 líneas por header (tipo + origen-destino)
        lineas_totales += 2

        cfg = rutas_config.get(ruta_sel, {"sumar": [], "visual": []})
        conceptos_orden = cfg["sumar"] + cfg["visual"]

        # Contar conceptos no vacíos
        for campo in conceptos_orden:
            if campo in ruta_data and not pd.isna(ruta_data[campo]) and float(ruta_data[campo]) != 0:
                lineas_totales += 1

    return lineas_totales


def estimar_paginas_necesarias(lineas_totales):
    """
    Estima cuántas páginas se necesitan basándose en las líneas.

    Criterio aproximado:
    - Primera página: ~20 líneas (tiene encabezados de cliente/empresa)
    - Páginas siguientes: ~30 líneas cada una
    """
    if lineas_totales <= 20:
        return 1

    lineas_restantes = lineas_totales - 20
    paginas_adicionales = (lineas_restantes + 29) // 30  # División con redondeo hacia arriba

    return 1 + paginas_adicionales


# ─────────────────────────────────────────────
# CLASE PDF — nivel de módulo (Paso 6: antes anidada en render())
# Mismo comportamiento exacto que la versión anterior, sin cambios de
# diseño, coordenadas ni plantilla.
# ─────────────────────────────────────────────
class PDF(FPDF):
    def __init__(self, orientation="P", unit="in", format="Letter", fecha_str="", total_pages=1):
        super().__init__(orientation=orientation, unit=unit, format=format)
        # DESACTIVAR compresión para máxima calidad de imágenes
        self.set_compression(False)
        self.fecha_str = fecha_str
        self.total_pages = total_pages

        # Fuentes Montserrat
        self.has_montserrat = False
        try:
            fonts_dir = _fonts_dir()
            reg = os.path.join(fonts_dir, "Montserrat-Regular.ttf")
            bold = os.path.join(fonts_dir, "Montserrat-Bold.ttf")
            it = os.path.join(fonts_dir, "Montserrat-Italic.ttf")

            if os.path.exists(reg):
                self.add_font("Montserrat", "", reg, uni=True)
                self.has_montserrat = True
            if os.path.exists(bold):
                self.add_font("Montserrat", "B", bold, uni=True)
            if os.path.exists(it):
                self.add_font("Montserrat", "I", it, uni=True)
        except Exception:
            self.has_montserrat = False

    def header(self):
        # Obtener la plantilla correcta para esta página
        pagina_actual = self.page_no()
        plantilla_path = _get_template_for_page(pagina_actual, self.total_pages)

        # Aplicar plantilla de fondo con MÁXIMA CALIDAD
        if plantilla_path and os.path.exists(plantilla_path):
            # Cargar imagen a resolución completa sin degradación
            self.image(plantilla_path, x=0, y=0, w=8.5, h=11)
        else:
            # Fondo blanco simple si no hay plantilla
            self.set_fill_color(255, 255, 255)
            self.rect(0, 0, 8.5, 11, "F")

        # Fecha - va en el espacio "DD / MM / AAA"
        self.set_body_font(size=8)
        self.set_text_color(80, 80, 80)
        self.set_xy(0.90, 1.10)  # Espacio para DD/MM/AAA
        self.cell(1.2, 0.12, safe_text(self.fecha_str), align="L")

        # Número de página - solo los números, "Página X de Y" ya viene en plantilla
        self.set_body_font(size=8)
        # número izquierdo
        self.set_xy(1.21, 10.14)
        self.cell(0.20, 0.12, str(pagina_actual), align="C")

        # espacio central (vacío)
        self.set_xy(1.35, 10.14)
        self.cell(0.35, 0.12, "", align="C")

        # número derecho
        self.set_xy(1.51, 10.14)
        self.cell(0.20, 0.12, str(self.total_pages), align="C")

    def set_body_font(self, bold=False, italic=False, size=7):
        style = ("B" if bold else "") + ("I" if italic else "")
        if self.has_montserrat:
            try:
                self.set_font("Montserrat", style, size)
            except Exception:
                # Si falla (por ej. italic no disponible), usar sin estilo
                self.set_font("Montserrat", "", size)
        else:
            self.set_font("Helvetica", style, size)


# ─────────────────────────────────────────────
# RENDER
# ─────────────────────────────────────────────
def render():
    supabase = get_supabase_client()
    if supabase is None:
        alert("warn", "⚠️ Supabase no configurado. No se pueden cargar rutas para cotizar.")
        return

    # ── Recargar ─────────────────────────────────────────────────
    rc1, rc2 = st.columns([1, 4])
    with rc1:
        if st.button("🔄 Recargar rutas", key="pic_cot_reload"):
            st.rerun()
    with rc2:
        st.caption("Usa 'Recargar' si acabas de guardar rutas nuevas.")

    # ── Cargar rutas ──────────────────────────────────────────────
    try:
        respuesta = supabase.table("Rutas_Picus").select("*").order("Fecha", desc=True).execute()
        if not respuesta.data:
            alert("warn", "⚠️ No hay rutas registradas. Captura rutas primero.")
            return
        df = pd.DataFrame(respuesta.data)
    except Exception as e:
        alert("error", f"Error cargando rutas: {e}")
        return

    if "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.date

    for col in ["Origen", "Destino", "Cliente", "Tipo"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.upper()

    if "ID_Ruta" in df.columns:
        df.set_index("ID_Ruta", inplace=True, drop=False)

    if not {"ID_Ruta", "Tipo", "Origen", "Destino"}.issubset(set(df.columns)):
        alert("error", "La tabla debe tener: ID_Ruta, Tipo, Origen, Destino.")
        return

    # ── Fecha ─────────────────────────────────────────────────────
    divider()
    section_header("📅", "Fecha de Cotización")
    fecha = st.date_input("Fecha", value=date.today(), format="DD/MM/YYYY", key="pic_cot_fecha")

    # ── Datos cliente / empresa ───────────────────────────────────
    divider()
    section_header("🏢", "Datos del Cliente y Empresa")
    col_cli, col_emp = st.columns(2)

    with col_cli:
        st.markdown("#### 👤 Cliente")
        cliente_nombre    = st.text_input("Nombre del Cliente",     key="pic_cot_cli_nom",  placeholder="NOMBRE DE LA EMPRESA")
        cliente_direccion = st.text_input("Dirección del Cliente",   key="pic_cot_cli_dir",  placeholder="Calle, Ciudad, Estado")
        cliente_mail      = st.text_input("Email del Cliente",       key="pic_cot_cli_mail", placeholder="correo@empresa.com")
        cli_c1, cli_c2    = st.columns(2)
        cliente_telefono  = cli_c1.text_input("Teléfono",           key="pic_cot_cli_tel",  placeholder="867 123 4567")
        cliente_ext       = cli_c2.text_input("Ext.",               key="pic_cot_cli_ext",  placeholder="1000")

    with col_emp:
        st.markdown("#### 🏢 Empresa")
        empresa_nombre    = st.text_input("Nombre de la Empresa",    key="pic_cot_emp_nom",  value="PICUS SA DE CV")
        empresa_direccion = st.text_input("Dirección de la Empresa", key="pic_cot_emp_dir",  value="Carr. Apto Km 3.8 Blvd Apto. 4, América, Nuevo Laredo, Tamps. 88284")
        empresa_mail      = st.text_input("Email de la Empresa",     key="pic_cot_emp_mail", placeholder="operaciones@picus.com")
        emp_c1, emp_c2    = st.columns(2)
        empresa_telefono  = emp_c1.text_input("Teléfono Empresa",   key="pic_cot_emp_tel",  placeholder="867 718 1823")
        empresa_ext       = emp_c2.text_input("Ext. Empresa",       key="pic_cot_emp_ext",  placeholder="1100")

    # ── Filtros + selección de rutas ──────────────────────────────
    divider()
    section_header("🛣️", "Selección de Rutas")
    with st.expander("Filtros opcionales", expanded=False):
        fc1, fc2, fc3, fc4, fc5 = st.columns(5)
        tipos_disp    = ["Todos"] + sorted(df["Tipo"].dropna().unique().tolist())
        clientes_disp = ["Todos"] + sorted(df["Cliente"].dropna().astype(str).unique().tolist())
        f_tipo    = fc1.selectbox("Tipo",              tipos_disp,    key="pic_cot_ftipo")
        f_cliente = fc2.selectbox("Cliente",           clientes_disp, key="pic_cot_fcli")
        f_origen  = fc3.text_input("Origen contiene",                 key="pic_cot_fori")
        f_destino = fc4.text_input("Destino contiene",                key="pic_cot_fdest")
        f_id      = fc5.text_input("ID contiene",                     key="pic_cot_fid")

    df_f = df.copy()
    if f_tipo    != "Todos": df_f = df_f[df_f["Tipo"].astype(str) == f_tipo]
    if f_cliente != "Todos": df_f = df_f[df_f["Cliente"].astype(str) == f_cliente]
    if f_origen.strip():  df_f = df_f[df_f["Origen"].astype(str).str.upper().str.contains(f_origen.upper(),  na=False)]
    if f_destino.strip(): df_f = df_f[df_f["Destino"].astype(str).str.upper().str.contains(f_destino.upper(), na=False)]
    if f_id.strip():      df_f = df_f[df_f["ID_Ruta"].astype(str).str.upper().str.contains(f_id.upper(),     na=False)]

    opciones = (
        df_f["ID_Ruta"].astype(str) + " | " +
        df_f["Tipo"].astype(str)    + " | " +
        df_f["Cliente"].astype(str) + " | " +
        df_f["Origen"].astype(str)  + " -> " +
        df_f["Destino"].astype(str)
    ).tolist()

    ids_seleccionados = st.multiselect(
        f"Elige las rutas a incluir ({len(df_f)} disponibles):",
        options=opciones,
        key="pic_cot_ids",
    )

    # ── Moneda y tipo de cambio ───────────────────────────────────
    divider()
    section_header("💱", "Moneda y Tipo de Cambio")
    moneda_default = "MXP"
    if ids_seleccionados:
        id_0 = ids_seleccionados[0].split(" | ")[0].strip()
        if id_0 in df.index:
            moneda_default = str(df.loc[id_0].get("Moneda", "MXP") or "MXP")

    col_mon, col_tc = st.columns(2)
    moneda_cotizacion = col_mon.selectbox(
        "Moneda Principal", ["MXP", "USD"],
        index=0 if moneda_default == "MXP" else 1,
        key="pic_cot_moneda",
    )
    tipo_cambio = col_tc.number_input(
        "Tipo de Cambio USD/MXP", min_value=0.0, value=18.0, step=0.01, key="pic_cot_tc"
    )

    # ── Configuración de conceptos ────────────────────────────────
    # Solo campos de Picus (sin termo)
    CONCEPTOS_TODOS = [
        "Ingreso_Original", "Cruce_Original",
        "Movimiento_Local", "Puntualidad", "Pension", "Estancia",
        "Pistas_Extra", "Stop", "Falso", "Gatas", "Accesorios",
        "Casetas", "Fianza", "Guias", "Costo_Diesel_Camion",
    ]

    rutas_config = {}

    if ids_seleccionados:
        divider()
        section_header("⚙️", "Configuración de Conceptos por Ruta")
        for ruta_sel in ids_seleccionados:
            id_ruta = ruta_sel.split(" | ")[0].strip()
            if id_ruta not in df.index:
                continue
            ruta_data = df.loc[id_ruta]

            # Solo conceptos con valor capturado > 0
            conceptos_disponibles = [
                c for c in CONCEPTOS_TODOS
                if c in ruta_data
                and ruta_data[c] is not None
                and not pd.isna(ruta_data[c])
                and float(ruta_data[c] or 0) > 0
            ]

            default_sumar  = [c for c in ["Ingreso_Original", "Cruce_Original"] if c in conceptos_disponibles]
            default_visual = [c for c in ["Casetas", "Pension", "Estancia"] if c in conceptos_disponibles]

            with st.expander(f"📋 Configurar: {ruta_sel}", expanded=False):
                if not conceptos_disponibles:
                    alert("info", "Esta ruta no tiene conceptos con valor capturado.")
                    rutas_config[ruta_sel] = {"sumar": [], "visual": []}
                    continue
                colS, colV = st.columns(2)
                with colS:
                    sumar = st.multiselect(
                        "➕ Sumar al total (Azul)",
                        options=conceptos_disponibles,
                        default=default_sumar,
                        key=f"pic_cot_sumar_{ruta_sel}",
                        format_func=label_de,
                    )
                with colV:
                    solo_visual = st.multiselect(
                        "👁️ Mostrar sin sumar (Gris)",
                        options=[c for c in conceptos_disponibles if c not in sumar],
                        default=[c for c in default_visual if c not in sumar],
                        key=f"pic_cot_visual_{ruta_sel}",
                        format_func=label_de,
                    )
                sumar       = [c for c in sumar       if c not in solo_visual]
                solo_visual = [c for c in solo_visual if c not in sumar]
                rutas_config[ruta_sel] = {"sumar": sumar, "visual": solo_visual}

    # ── Notas ─────────────────────────────────────────────────────
    divider()
    section_header("📝", "Notas o Condiciones")
    texto_default = (
        "Esta cotización es válida por 15 días. "
        "No aplica IVA y Retenciones en el caso de las importaciones y exportaciones. "
        "Las exportaciones aplican tasa 0."
    )
    notas_cotizacion = st.text_area(
        "Puedes editar este texto:", value=texto_default, height=100, key="pic_cot_notas"
    )

    # ── Estimación ────────────────────────────────────────────────
    if ids_seleccionados:
        lineas = calcular_lineas_necesarias(rutas_config, ids_seleccionados, df)
        paginas_estimadas = estimar_paginas_necesarias(lineas)
        st.info(f"📊 Estimación: ~{lineas} líneas → ~{paginas_estimadas} página(s)")

    # ── Generar PDF ───────────────────────────────────────────────
    divider()
    if st.button(
        "🎯 Generar Cotización PDF",
        disabled=(len(ids_seleccionados) == 0),
        type="primary",
        key="pic_cot_gen",
        use_container_width=True,
    ):
        lineas_totales = calcular_lineas_necesarias(rutas_config, ids_seleccionados, df)

        # ── Simulación de páginas reales (recuento de Y sin renderizar) ──
        # Esto evita páginas en blanco por sobreestimación.
        _y_sim = 4.50
        _paginas_sim = 1
        _y_max_1 = 8.60
        _y_max_n = 9.20

        for _ruta_sel in ids_seleccionados:
            _id = _ruta_sel.split(" | ")[0].strip()
            if _id not in df.index:
                continue
            _rd = df.loc[_id]
            _cfg = rutas_config.get(_ruta_sel, {"sumar": [], "visual": []})
            _conceptos = _cfg["sumar"] + _cfg["visual"]

            # header de ruta: 2 líneas × 0.15 + 0.05 de margen
            _y_sim += 0.35
            _y_max = _y_max_1 if _paginas_sim == 1 else _y_max_n
            if _y_sim > _y_max:
                _paginas_sim += 1
                _y_sim = 2.00

            for _campo in _conceptos:
                if _campo not in _rd or pd.isna(_rd[_campo]) or float(_rd[_campo] or 0) == 0:
                    continue
                _y_max = _y_max_1 if _paginas_sim == 1 else _y_max_n
                if _y_sim > _y_max:
                    _paginas_sim += 1
                    _y_sim = 1.40
                _y_sim += 0.18

        num_paginas_necesarias = _paginas_sim

        pdf = PDF(
            orientation="P",
            unit="in",
            format="Letter",
            fecha_str=fecha.strftime('%d/%m/%Y'),
            total_pages=num_paginas_necesarias
        )
        pdf.set_auto_page_break(auto=False)
        pdf.add_page()

        # ---------------------------
        # DATOS EN PRIMERA PÁGINA
        # ---------------------------
        pdf.set_body_font(size=10)

        # Cliente
        pdf.set_xy(0.85, 2.05); pdf.multi_cell(2.89, 0.24, safe_text(cliente_nombre), align="L")
        pdf.set_xy(0.85, 2.66); pdf.multi_cell(2.89, 0.18, safe_text(cliente_direccion), align="L")
        pdf.set_xy(0.85, 3.20); pdf.multi_cell(2.89, 0.31, safe_text(cliente_mail), align="L")
        pdf.set_xy(0.85, 3.60); pdf.cell(1.35, 0.31, safe_text(cliente_telefono), align="L")
        pdf.set_xy(2.39, 3.60); pdf.cell(0.76, 0.31, safe_text(cliente_ext), align="C")

        # Empresa
        pdf.set_xy(4.76, 2.05); pdf.multi_cell(2.89, 0.24, safe_text(empresa_nombre), align="R")
        pdf.set_xy(4.76, 2.66); pdf.multi_cell(2.89, 0.18, safe_text(empresa_direccion), align="R")
        pdf.set_xy(4.76, 3.20); pdf.multi_cell(2.89, 0.31, safe_text(empresa_mail), align="R")
        pdf.set_xy(5.23, 3.60); pdf.cell(1.35, 0.31, safe_text(empresa_telefono), align="R")
        pdf.set_xy(7.03, 3.60); pdf.cell(0.76, 0.31, safe_text(empresa_ext), align="C")

        # ---------------------------
        # DETALLE DE CONCEPTOS
        # ---------------------------
        pdf.set_body_font(size=7)

        y = 4.50
        y_max_1 = 8.60
        y_max_n = 9.20
        pagina_actual_pdf = 1
        total_global = 0.0

        for ruta_sel in ids_seleccionados:
            id_ruta = ruta_sel.split(" | ")[0].strip()
            if id_ruta not in df.index:
                continue
            ruta_data = df.loc[id_ruta]
            cfg = rutas_config.get(ruta_sel, {"sumar": [], "visual": []})
            conceptos_orden = [(c, True) for c in cfg["sumar"]] + [(c, False) for c in cfg["visual"]]

            y_max = y_max_1 if pagina_actual_pdf == 1 else y_max_n
            if y > y_max:
                pdf.add_page()
                pagina_actual_pdf += 1
                y = 2.00

            pdf.set_body_font(bold=True, size=8)
            pdf.set_xy(0.85, y)
            pdf.cell(0, 0.15, safe_text(f"{ruta_data.get('Tipo','')} — {ruta_data.get('Origen','')} → {ruta_data.get('Destino','')}"), border=0, align="L")
            y += 0.18

            for campo, es_cobrado in conceptos_orden:
                if campo not in ruta_data or pd.isna(ruta_data[campo]) or float(ruta_data[campo] or 0) == 0:
                    continue

                y_max = y_max_1 if pagina_actual_pdf == 1 else y_max_n
                if y > y_max:
                    pdf.add_page()
                    pagina_actual_pdf += 1
                    y = 1.40

                valor_original    = float(ruta_data[campo])
                valor_convertido  = convertir_moneda(
                    valor_original,
                    str(ruta_data.get("Moneda", "MXP")),
                    moneda_cotizacion,
                    tipo_cambio,
                )
                cantidad_texto = "1"

                pdf.set_body_font(bold=False, size=7)
                pdf.set_text_color(0, 0, 0) if es_cobrado else pdf.set_text_color(120, 120, 120)
                pdf.set_xy(0.95, y)
                pdf.cell(4.00, 0.15, safe_text(label_de(campo)), border=0, align="L")

                pdf.set_xy(5.10, y)
                pdf.cell(0.55, 0.15, cantidad_texto, border=0, align="C")

                # Moneda
                pdf.set_xy(5.85, y)
                pdf.cell(0.65, 0.15, moneda_cotizacion, border=0, align="C")

                # Precio
                pdf.set_xy(6.55, y)
                pdf.cell(1.05, 0.15, f"${valor_convertido:,.2f}", border=0, align="R")

                if es_cobrado:
                    total_global += valor_convertido

                y += 0.18

        # ---------------------------
        # TOTAL (solo en última página, sin páginas en blanco)
        # ---------------------------
        pdf.set_body_font(bold=True, size=8)
        pdf.set_text_color(0, 0, 0)

        # La palabra "TARIFA TOTAL" ya viene en la plantilla, solo ponemos valores
        pdf.set_xy(5.85, 9.13)
        pdf.cell(0.70, 0.15, moneda_cotizacion, border=0, align="C")

        pdf.set_xy(6.55, 9.13)
        pdf.cell(1.00, 0.15, f"${total_global:,.2f}", border=0, align="R")

        nombre_archivo_cliente = re.sub(r"[^\w\-]", "_", cliente_nombre or "Cliente")
        file_name = f'Cotizacion-{nombre_archivo_cliente}-{fecha.strftime("%d-%m-%Y")}.pdf'
        pdf_bytes = pdf.output(dest="S").encode("latin-1")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("📄 Páginas", num_paginas_necesarias)
        with col2:
            st.metric("📊 Líneas", lineas_totales)
        with col3:
            tamaño_kb = len(pdf_bytes) / 1024
            st.metric("💾 Tamaño", f"{tamaño_kb:.1f} KB")

        st.success(f"✅ PDF generado exitosamente con {num_paginas_necesarias} página(s)")

        st.download_button(
            "📥 Descargar Cotización en PDF",
            data=pdf_bytes,
            file_name=file_name,
            mime="application/pdf",
            type="primary"
        )
