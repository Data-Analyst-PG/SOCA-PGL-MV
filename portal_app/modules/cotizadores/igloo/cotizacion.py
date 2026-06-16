from ui.components import section_header, alert, divider
import os
import re
from pathlib import Path
from datetime import date
import pandas as pd
import streamlit as st
from fpdf import FPDF # pyright: ignore[reportMissingModuleSource]
from services.supabase_client import get_supabase_client

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
    # .../portal_app/modules/cotizadores/igloo -> subir 3 niveles a portal_app
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
        # Solo una página: plantilla completa
        nombre = "2.0 ADT PGL Igloo.png"
    
    elif total_paginas == 2:
        # Dos páginas
        if pagina_actual == 1:
            nombre = "2.0 ADT PGL Igloo (2).png"  # Primera con headers
        else:
            nombre = "2.0 ADT PGL Igloo (4).png"  # Última con totales
    
    else:  # 3 o más páginas
        if pagina_actual == 1:
            nombre = "2.0 ADT PGL Igloo (2).png"  # Primera con headers
        elif pagina_actual == total_paginas:
            nombre = "2.0 ADT PGL Igloo (4).png"  # Última con totales
        else:
            nombre = "2.0 ADT PGL Igloo (3).png"  # Intermedias solo tabla
    
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

def render():
    supabase = get_supabase_client()
    if supabase is None:
        alert("warn", "⚠️ Supabase no configurado. No se pueden cargar rutas para cotizar.")
        return

    TABLE_RUTAS = "Rutas"

    # ---------------------------
    # CARGAR RUTAS
    # ---------------------------
    try:
        respuesta = supabase.table(TABLE_RUTAS).select("*").execute()
        if not respuesta.data:
            alert("warn", "⚠️ No hay rutas registradas en Supabase.")
            return
        df = pd.DataFrame(respuesta.data)
    except Exception as e:
        st.error(f"❌ Error consultando rutas: {e}")
        st.exception(e)
        return

    if "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.date

    if "ID_Ruta" in df.columns:
        df.set_index("ID_Ruta", inplace=True, drop=False)

    fecha = st.date_input("📅 Fecha de cotización", value=date.today(), format="DD/MM/YYYY")

    # ---------------------------
    # DATOS DE CLIENTE Y EMPRESA
    # ---------------------------
    # 🆕 Usar tabs para mejor organización
    tab1, tab2 = st.tabs(["👤 Datos del Cliente", "🏢 Datos de la Empresa"])
    
    with tab1:
        cliente_nombre = st.text_input("Nombre del Cliente")
        cliente_direccion = st.text_input("Dirección del Cliente")
        cliente_mail = st.text_input("📧 Email del Cliente")
        cliente_telefono = st.text_input("📞 Teléfono del Cliente")
        cliente_ext = st.text_input("Ext Cliente")

    with tab2:
        empresa_nombre = st.text_input("Nombre de tu Empresa", "IGLOO TRANSPORT S DE RL DE CV")
        empresa_direccion = st.text_input("Dirección de la Empresa", "Carr. Apto Km 3.8 Blvd Apto. 4, América, Nuevo Laredo, Tamps. 88284")
        empresa_mail = st.text_input("📧 Email de la Empresa", "esmeralda.resendez@palosgarza.com")
        empresa_telefono = st.text_input("📞 Teléfono de la Empresa", "867 718 1823")
        empresa_ext = st.text_input("Ext Empresa", "1104")

    # ---------------------------
    # SELECCIÓN DE RUTAS
    # ---------------------------
    if not {"ID_Ruta", "Tipo", "Origen", "Destino"}.issubset(set(df.columns)):
        alert("error", "La tabla debe contener: ID_Ruta, Tipo, Origen, Destino.")
        return

    opciones = df["ID_Ruta"].astype(str) + " | " + df["Tipo"].astype(str) + " | " + df["Origen"].astype(str) + " → " + df["Destino"].astype(str)

    ids_seleccionados = st.multiselect(
        "🛣️ Elige las rutas que deseas incluir:",
        options=opciones.tolist()
    )

    # ---------------------------
    # MONEDA Y TIPO DE CAMBIO
    # ---------------------------
    moneda_default = "MXP"
    if ids_seleccionados:
        id_ruta_0 = ids_seleccionados[0].split(" | ")[0]
        if id_ruta_0 in df.index:
            moneda_default = df.loc[id_ruta_0].get("Moneda", "MXP") or "MXP"

    section_header("💱", "Moneda y Tipo de Cambio")
    col_moneda, col_tc = st.columns(2)
    
    with col_moneda:
        moneda_cotizacion = st.selectbox(
            "Moneda Principal",
            ["MXP", "USD"],
            index=0 if moneda_default == "MXP" else 1
        )
    
    with col_tc:
        tipo_cambio = st.number_input("Tipo de Cambio USD/MXP", min_value=0.0, value=18.0, step=0.01)

    # ---------------------------
    # SELECCIÓN DE CONCEPTOS POR RUTA
    # ---------------------------
    rutas_config = {}

    CONCEPTOS = [
        "Ingreso_Original", "Cruce_Original",
        "Movimiento_Local", "Puntualidad", "Pension", "Estancia",
        "Pistas_Extra", "Stop", "Falso", "Gatas", "Accesorios",
        "Casetas", "Fianza_Termo", "Guias",
        "Lavado_Termo", "Renta_Termo",
        "Costo_Diesel_Camion", "Costo_Diesel_Termo",
    ]

    if ids_seleccionados:
        section_header("⚙️", "Configuración de Conceptos")
        
        # 🆕 Usar expander para cada ruta (más limpio)
        for ruta_sel in ids_seleccionados:
            with st.expander(f"📋 Configurar: {ruta_sel}", expanded=False):
                default_sumar = ["Ingreso_Original", "Cruce_Original"]
                default_visual = ["Casetas", "Pension", "Estancia"]

                colS, colV = st.columns(2)
                with colS:
                    sumar = st.multiselect(
                        "➕ Sumar al total (Azul)",
                        options=CONCEPTOS,
                        default=[c for c in default_sumar if c in CONCEPTOS],
                        key=f"igloo_sumar_{ruta_sel}"
                    )
                with colV:
                    solo_visual = st.multiselect(
                        "👁️ Mostrar sin sumar (Gris)",
                        options=[c for c in CONCEPTOS if c not in sumar],
                        default=[c for c in default_visual if c not in sumar],
                        key=f"igloo_visual_{ruta_sel}"
                    )

                sumar = [c for c in sumar if c not in solo_visual]
                solo_visual = [c for c in solo_visual if c not in sumar]
                rutas_config[ruta_sel] = {"sumar": sumar, "visual": solo_visual}

    # ---------------------------
    # NOTAS / CONDICIONES
    # ---------------------------
    section_header("📝", "Notas o Condiciones")
    texto_default = (
        "Esta cotización es válida por 15 días. "
        "No aplica IVA y Retenciones en el caso de las importaciones y exportaciones. "
        "Las exportaciones aplican tasa 0."
    )
    notas_cotizacion = st.text_area("Puedes editar este texto:", value=texto_default, height=100)

    # ---------------------------
    # PREVIEW DE ESTIMACIÓN
    # ---------------------------
    if ids_seleccionados:
        lineas = calcular_lineas_necesarias(rutas_config, ids_seleccionados, df)
        paginas_estimadas = estimar_paginas_necesarias(lineas)
        
        st.info(f"📊 Estimación: ~{lineas} líneas de conceptos → ~{paginas_estimadas} página(s)")

    # ---------------------------
    # GENERAR PDF
    # ---------------------------
    if st.button("🎯 Generar Cotización PDF", disabled=(len(ids_seleccionados) == 0), type="primary"):

        # Calcular páginas necesarias
        lineas_totales = calcular_lineas_necesarias(rutas_config, ids_seleccionados, df)

        # Simulación real de Y para contar páginas exactas (igual que Picus)
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

        class PDF(FPDF):
            def __init__(self, orientation="P", unit="in", format="Letter", fecha_str="", total_pages=1, notas=""):
                super().__init__(orientation=orientation, unit=unit, format=format)
                # DESACTIVAR compresión para máxima calidad de imágenes
                self.set_compression(False)
                self.fecha_str = fecha_str
                self.total_pages = total_pages
                self.notas = notas

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

                # Notas/condiciones — aparecen en TODAS las páginas
                self.set_body_font(size=6.5)
                self.set_text_color(100, 100, 100)
                self.set_xy(0.90, 9.60)
                self.multi_cell(4.50, 0.12, safe_text(self.notas), align="L")

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

        pdf = PDF(
            orientation="P", 
            unit="in", 
            format="Letter",
            fecha_str=fecha.strftime('%d/%m/%Y'),
            total_pages=num_paginas_necesarias,
            notas=notas_cotizacion,
        )
        pdf.set_auto_page_break(auto=False)
        pdf.add_page()

        # ---------------------------
        # DATOS EN PRIMERA PÁGINA
        # ---------------------------
        pdf.set_body_font(size=10)

        # 🔧 COORDENADAS PARA DATOS DEL CLIENTE (ajusta según tu plantilla real)
        # Cliente (leave exactly like this)
        pdf.set_xy(0.85, 2.05); pdf.multi_cell(2.89, 0.24, safe_text(cliente_nombre), align="L")
        pdf.set_xy(0.85, 2.66); pdf.multi_cell(2.89, 0.18, safe_text(cliente_direccion), align="L")
        pdf.set_xy(0.85, 3.20); pdf.multi_cell(2.89, 0.31, safe_text(cliente_mail), align="L")
        pdf.set_xy(0.85, 3.60); pdf.cell(1.35, 0.31, safe_text(cliente_telefono), align="L")
        pdf.set_xy(2.39, 3.60); pdf.cell(0.76, 0.31, safe_text(cliente_ext), align="C")

        # Empresa (move this upward)
        pdf.set_xy(4.76, 2.05); pdf.multi_cell(2.89, 0.24, safe_text(empresa_nombre), align="R")
        pdf.set_xy(4.76, 2.66); pdf.multi_cell(2.89, 0.18, safe_text(empresa_direccion), align="R")
        pdf.set_xy(4.76, 3.20); pdf.multi_cell(2.89, 0.31, safe_text(empresa_mail), align="R")
        pdf.set_xy(5.23, 3.60); pdf.cell(1.35, 0.31, safe_text(empresa_telefono), align="R")
        pdf.set_xy(7.03, 3.60); pdf.cell(0.76, 0.31, safe_text(empresa_ext), align="C")

        # ---------------------------
        # DETALLE DE CONCEPTOS
        # ---------------------------
        pdf.set_body_font(size=7)
        
        # 🔧 Y inicial para empezar conceptos (según plantilla debe estar más arriba)
        y = 4.50
        
        # 🔧 Y máximo antes de salto de página
        y_max_pagina_1 = 8.60  # Más arriba para dar espacio al total
        y_max_otras_paginas = 9.20  # Páginas intermedias tienen más espacio
        
        total_global = 0.0
        pagina_actual = 1

        for ruta_sel in ids_seleccionados:
            id_ruta = ruta_sel.split(" | ")[0]
            if id_ruta not in df.index:
                continue

            ruta_data = df.loc[id_ruta]
            tipo_ruta = str(ruta_data.get("Tipo", ""))
            origen = str(ruta_data.get("Origen", ""))
            destino = str(ruta_data.get("Destino", ""))
            descripcion = f"{origen} - {destino}"

            # Verificar si hay espacio para el header de ruta
            y_necesario_header = 0.35  # Espacio que ocupa el header
            y_max = y_max_pagina_1 if pagina_actual == 1 else y_max_otras_paginas
            
            if y + y_necesario_header > y_max:
                pdf.add_page()
                pagina_actual += 1
                y = 2.00  # 🔧 Y inicial en páginas siguientes

            # Título de ruta
            pdf.set_body_font(bold=True, size=7)
            pdf.set_text_color(128, 128, 128)
            pdf.set_xy(0.85, y); pdf.multi_cell(7, 0.15, safe_text(tipo_ruta), align="L")
            y = pdf.get_y()
            pdf.set_xy(0.85, y); pdf.multi_cell(7, 0.15, safe_text(descripcion), align="L")
            y = pdf.get_y() + 0.05

            cfg = rutas_config.get(ruta_sel, {"sumar": [], "visual": []})
            conceptos_orden = cfg["sumar"] + cfg["visual"]

            for campo in conceptos_orden:
                if campo not in ruta_data or pd.isna(ruta_data[campo]) or float(ruta_data[campo]) == 0:
                    continue

                valor = float(ruta_data[campo])

                if campo == "Ingreso_Original":
                    moneda_original = ruta_data.get("Moneda", "MXP")
                elif campo == "Cruce_Original":
                    moneda_original = ruta_data.get("Moneda_Cruce", "MXP")
                else:
                    moneda_original = "MXP"

                valor_convertido = convertir_moneda(valor, moneda_original, moneda_cotizacion, tipo_cambio)

                # Verificar si necesitamos nueva página
                y_max = y_max_pagina_1 if pagina_actual == 1 else y_max_otras_paginas
                if y > y_max:
                    pdf.add_page()
                    pagina_actual += 1
                    y = 1.40  # 🔧 Y inicial en páginas siguientes (más arriba)

                es_cobrado = campo in cfg["sumar"]

                # 🎨 COLORES DIFERENCIADOS:
                # Azul (#252D80) para conceptos cobrados
                # Gris para conceptos no cobrados
                if es_cobrado:
                    pdf.set_text_color(37, 45, 128)  # Azul #252D80
                    pdf.set_body_font(bold=False, size=7)
                else:
                    pdf.set_text_color(150, 150, 150)  # Gris más claro
                    pdf.set_body_font(bold=False, size=7)  # Sin italic para evitar errores

                # 🔧 COORDENADAS XY PARA LOS CONCEPTOS (ajusta según tu plantilla)
                # Concepto
                concepto_texto = safe_text(label_de(campo))
                if len(concepto_texto) > 32:
                    concepto_texto = concepto_texto[:29] + "..."

                pdf.set_xy(0.85, y)
                pdf.cell(3.20, 0.15, concepto_texto, border=0, align="L")

                # KMS — solo aplica al concepto Flete (Ingreso_Original)
                kms_texto = str(ruta_data.get("KM", "") or "") if campo == "Ingreso_Original" else ""

                pdf.set_xy(4.00, y)
                pdf.cell(0.70, 0.15, kms_texto, border=0, align="C")

                # Cantidad
                cantidad_texto = "1" if es_cobrado else ""

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
        
        # 🔧 COORDENADAS PARA EL TOTAL (sin label "TARIFA TOTAL")
        # La palabra "TARIFA TOTAL" ya viene en la plantilla, solo ponemos valores
        pdf.set_xy(5.85, 9.13)
        pdf.cell(0.70, 0.15, moneda_cotizacion, border=0, align="C")

        pdf.set_xy(6.55, 9.13)
        pdf.cell(1.00, 0.15, f"${total_global:,.2f}", border=0, align="R")

        nombre_archivo_cliente = re.sub(r"[^\w\-]", "_", cliente_nombre or "Cliente")
        file_name = f'Cotizacion-{nombre_archivo_cliente}-{fecha.strftime("%d-%m-%Y")}.pdf'
        pdf_bytes = pdf.output(dest="S").encode("latin-1")

        # 🆕 Mostrar métrica del PDF generado
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
