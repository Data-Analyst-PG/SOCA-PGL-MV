import os
import re
from pathlib import Path
from datetime import date
import pandas as pd
import streamlit as st
from fpdf import FPDF # pyright: ignore[reportMissingModuleSource]
from services.supabase_client import get_supabase_client
from ui.components import section_header, alert, divider
# --------- Opcional: optimización de plantilla con Pillow ---------
try:
    from PIL import Image
    HAS_PIL = True
except Exception:
    HAS_PIL = False

# ---------------------------
# ETIQUETAS VISIBLES (renombrar en PDF)
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
    # FPDF latin-1 friendly
    return str(text).encode("latin-1", "replace").decode("latin-1")

def _project_root() -> str:
    # .../portal_app/modules/cotizadores/picus -> subir 3 niveles a portal_app
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

def _img_dir() -> str:
    return os.path.join(_project_root(), "img")

def _fonts_dir() -> str:
    return os.path.join(_project_root(), "fonts")

PLANTILLA_CANDIDATAS = [
    # nombres comunes en tu carpeta img
    "ADT PGL GRAL NO TXT.png",
    "Cotización Picus.jpg",
    "Cotización Picus.png",
    "Picus BG.png",
    "PICUS W.png",
]

def _find_template():
    img_dir = _img_dir()
    for name in PLANTILLA_CANDIDATAS:
        p = os.path.join(img_dir, name)
        if os.path.exists(p):
            return p
    # fallback: si alguien deja ruta absoluta en el futuro
    for p in PLANTILLA_CANDIDATAS:
        if os.path.exists(p):
            return p
    return None

def _optimize_to_jpg(path_png, max_kb=750, target_w=1275, target_h=1650, quality=85):
    """Convierte PNG pesado a JPG optimizado. Devuelve ruta final."""
    if not HAS_PIL:
        return path_png
    try:
        img = Image.open(path_png).convert("RGB")
        img.thumbnail((target_w, target_h), Image.LANCZOS)
        out = Path(path_png).with_suffix("")
        out = f"{out}-opt.jpg"
        img.save(out, "JPEG", quality=quality, optimize=True, progressive=True)
        if os.path.getsize(out) > max_kb * 1024:
            img.save(out, "JPEG", quality=75, optimize=True, progressive=True)
        return out
    except Exception:
        return path_png

def render():
    supabase = get_supabase_client()
    if supabase is None:
        alert("warn", "⚠️ Supabase no configurado. No se pueden cargar rutas para cotizar.")
        return

    # ── Recargar ──────────────────────────────────────────────────
    rc1, rc2 = st.columns([1, 4])
    with rc1:
        if st.button("🔄 Recargar rutas", key="pic_cot_reload"):
            st.rerun()
    with rc2:
        st.caption("Carga cacheada. Usa 'Recargar' si acabas de guardar rutas nuevas.")

    # ── Cargar rutas ───────────────────────────────────────────────
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

    # ── Fecha ──────────────────────────────────────────────────────
    divider()
    section_header("📅", "Fecha de Cotización")
    fecha = st.date_input("Fecha", value=date.today(), format="DD/MM/YYYY", key="pic_cot_fecha")

    # ── Datos cliente / empresa ────────────────────────────────────
    divider()
    section_header("🏢", "Datos del Cliente y Empresa")
    col_cli, col_emp = st.columns(2)

    with col_cli:
        st.markdown("#### 👤 Cliente")
        cliente_nombre    = st.text_input("Nombre del Cliente",    key="pic_cot_cli_nom",  placeholder="NOMBRE DE LA EMPRESA")
        cliente_direccion = st.text_input("Dirección del Cliente",  key="pic_cot_cli_dir",  placeholder="Calle, Ciudad, Estado")
        cliente_mail      = st.text_input("Email del Cliente",      key="pic_cot_cli_mail", placeholder="correo@empresa.com")
        cli_c1, cli_c2    = st.columns(2)
        cliente_telefono  = cli_c1.text_input("Teléfono",          key="pic_cot_cli_tel",  placeholder="867 123 4567")
        cliente_ext       = cli_c2.text_input("Ext.",              key="pic_cot_cli_ext",  placeholder="1000")

    with col_emp:
        st.markdown("#### 🏢 Empresa")
        empresa_nombre    = st.text_input("Nombre de la Empresa",   key="pic_cot_emp_nom",  value="PICUS SA DE CV")
        empresa_direccion = st.text_input("Dirección de la Empresa", key="pic_cot_emp_dir",  placeholder="Dirección completa")
        empresa_mail      = st.text_input("Email de la Empresa",     key="pic_cot_emp_mail", placeholder="operaciones@picus.com")
        emp_c1, emp_c2    = st.columns(2)
        empresa_telefono  = emp_c1.text_input("Teléfono Empresa",   key="pic_cot_emp_tel",  placeholder="867 718 1823")
        empresa_ext       = emp_c2.text_input("Ext. Empresa",       key="pic_cot_emp_ext",  placeholder="1100")

    # ── Filtros de rutas ───────────────────────────────────────────
    divider()
    section_header("🔎", "Selección de Rutas")
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

    # ── Moneda y tipo de cambio ────────────────────────────────────
    divider()
    section_header("💱", "Moneda y Tipo de Cambio")
    moneda_default = "MXP"
    if ids_seleccionados:
        id_0 = ids_seleccionados[0].split(" | ")[0].strip()
        if id_0 in df.index:
            moneda_default = str(df.loc[id_0].get("Moneda", "MXP") or "MXP")

    col_mon, col_tc = st.columns(2)
    moneda_cotizacion = col_mon.selectbox(
        "Moneda Principal",
        ["MXP", "USD"],
        index=0 if moneda_default == "MXP" else 1,
        key="pic_cot_moneda",
    )
    tipo_cambio = col_tc.number_input(
        "Tipo de Cambio USD/MXP",
        min_value=0.0, value=18.0, step=0.01,
        key="pic_cot_tc",
    )

    # ── Configuración de conceptos por ruta ───────────────────────
    # Solo muestra los conceptos que tienen valor > 0 en cada ruta
    CONCEPTOS_TODOS = [
        "Ingreso_Original", "Cruce_Original", "Movimiento_Local", "Puntualidad",
        "Pension", "Estancia", "Pistas_Extra", "Stop", "Falso", "Gatas",
        "Accesorios", "Casetas", "Fianza", "Guias", "Costo_Diesel_Camion",
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
            default_visual = [c for c in ["Casetas", "Pension", "Estancia", "Movimiento_Local", "Puntualidad"] if c in conceptos_disponibles]

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

    # ── Notas ──────────────────────────────────────────────────────
    divider()
    section_header("📝", "Notas o Condiciones")
    texto_default = (
        "Esta cotización es válida por 15 días. "
        "No aplica IVA y Retenciones en el caso de las importaciones y exportaciones. "
        "Las exportaciones aplican tasa 0."
    )
    notas_cotizacion = st.text_area(
        "Puedes editar este texto si lo deseas:",
        value=texto_default, height=100,
        key="pic_cot_notas",
    )

    # ── Plantilla ──────────────────────────────────────────────────
    plantilla_path = _find_template()
    if plantilla_path and plantilla_path.lower().endswith(".png"):
        try:
            if os.path.getsize(plantilla_path) > 900 * 1024:
                plantilla_path = _optimize_to_jpg(plantilla_path)
        except Exception:
            pass

    if plantilla_path:
        st.caption(f"Plantilla detectada: `{os.path.basename(plantilla_path)}`")
    else:
        alert("warn", "⚠️ No encontré plantilla en portal_app/img. Se usará encabezado básico.")

    # ── Generar PDF ────────────────────────────────────────────────
    divider()
    if st.button(
        "🎯 Generar Cotización PDF",
        disabled=(len(ids_seleccionados) == 0),
        type="primary",
        key="pic_cot_gen",
        use_container_width=True,
    ):

        class PDF(FPDF):
            def __init__(self, orientation="P", unit="in", format="Letter", fecha_str="", total_pages=1):
                super().__init__(orientation=orientation, unit=unit, format=format)

                self.set_compression(False)
                self.fecha_str = fecha_str
                self.total_pages = total_pages
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

            def set_body_font(self, bold=False, italic=False, size=7):
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

                if page == 1:
                    bg_name = "2.0 ADT PGL PICUS (2).png"
                elif page == self.total_pages:
                    bg_name = "2.0 ADT PGL PICUS (4).png"
                else:
                    bg_name = "2.0 ADT PGL PICUS (3).png"

                bg_path = os.path.join(_img_dir(), bg_name)

                if bg_path and os.path.exists(bg_path):
                    self.image(bg_path, x=0, y=0, w=8.5, h=11)

                self.set_body_font(size=8)
                self.set_text_color(80, 80, 80)

                self.set_xy(0.90, 1.10)
                self.cell(1.2, 0.12, safe_text(self.fecha_str), align="L")

                # número izquierdo
                self.set_xy(1.21, 10.14)
                self.cell(0.20, 0.12, str(page), align="C")

                # espacio central (donde iría DE, pero vacío)
                self.set_xy(1.35, 10.14)
                self.cell(0.35, 0.12, "", align="C")

                # número derecho
                self.set_xy(1.51, 10.14)
                self.cell(0.20, 0.12, str(self.total_pages), align="C")

        # ---------------------------
        # CALCULAR PAGINAS NECESARIAS
        # ---------------------------
        lineas_totales = 0

        for ruta_sel in ids_seleccionados:
            id_ruta = ruta_sel.split(" | ")[0]

            if id_ruta not in df.index:
                continue

            ruta_data = df.loc[id_ruta]

            # Header ruta + concepto + kms + cantidad
            lineas_totales += 4

            cfg = rutas_config.get(ruta_sel, {"sumar": [], "visual": []})

            conceptos_orden = [
                "Ingreso_Original",
                "Cruce_Original",
                "Casetas",
                "Pension",
                "Estancia",
                "Movimiento_Local",
                "Puntualidad"
            ]

            for campo in conceptos_orden:
                if (
                    campo in ruta_data
                    and not pd.isna(ruta_data[campo])
                    and float(ruta_data[campo]) != 0
                ):
                    lineas_totales += 1

        if lineas_totales <= 12:
            total_pages_needed = 1
        else:
            restantes = lineas_totales - 12
            extra_pages = (restantes + 29) // 30
            total_pages_needed = 1 + extra_pages

        pdf = PDF(
            orientation="P",
            unit="in",
            format="Letter",
            fecha_str=fecha.strftime("%d/%m/%Y"),
            total_pages=total_pages_needed
        )

        pdf.set_auto_page_break(auto=False)
        pdf.add_page()
        pdf.set_body_font(size=10)

        # ---------------------------
        # CLIENTE / EMPRESA
        # ---------------------------

        def texto_2_lineas(pdf, x, y, texto, align="L"):
            """
            EXACTAMENTE máximo 2 líneas
            Máximo 40 caracteres por línea
            Nunca permite 3 líneas
            Nunca mueve columnas
            No usa multi_cell()
            """

            texto = safe_text(texto).strip()

            if not texto:
                return

            max_chars = 40
            ancho_fijo = 2.89
            altura_linea = 0.15

            palabras = texto.split()

            linea1 = ""
            linea2 = ""

            for palabra in palabras:
                test1 = f"{linea1} {palabra}".strip()

                if len(test1) <= max_chars:
                    linea1 = test1
                    continue

                test2 = f"{linea2} {palabra}".strip()

                if len(test2) <= max_chars:
                    linea2 = test2
                    continue

                # si ya no cabe → truncar segunda línea
                if not linea2:
                    linea2 = palabra[:max_chars - 3] + "..."
                else:
                    while len(linea2) > max_chars - 3:
                        linea2 = linea2[:-1].rstrip()

                    linea2 += "..."

                break

            # línea 1
            pdf.set_xy(x, y)
            pdf.cell(
                ancho_fijo,
                altura_linea,
                linea1,
                align=align
            )

            # línea 2 (solo si existe)
            if linea2:
                pdf.set_xy(x, y + altura_linea)
                pdf.cell(
                    ancho_fijo,
                    altura_linea,
                    linea2,
                    align=align
                )

        # ---------------------------
        # CLIENTE
        # ---------------------------

        texto_2_lineas(
            pdf,
            x=0.85,
            y=2.15,
            texto=cliente_nombre,
            align="L"
        )

        texto_2_lineas(
            pdf,
            x=0.85,
            y=2.70,
            texto=cliente_direccion,
            align="L"
        )

        pdf.set_xy(0.85, 3.20)
        pdf.cell(2.89, 0.31, safe_text(cliente_mail), align="L")

        pdf.set_xy(1.00, 3.60)
        pdf.cell(1.35, 0.31, safe_text(cliente_telefono), align="L")

        pdf.set_xy(2.39, 3.60)
        pdf.cell(0.76, 0.31, safe_text(cliente_ext), align="C")

        # ---------------------------
        # EMPRESA
        # ---------------------------

        texto_2_lineas(
            pdf,
            x=4.76,
            y=2.15,
            texto=empresa_nombre,
            align="R"
        )

        texto_2_lineas(
            pdf,
            x=4.76,
            y=2.70,
            texto=empresa_direccion,
            align="R"
        )

        pdf.set_xy(4.76, 3.20)
        pdf.cell(2.89, 0.31, safe_text(empresa_mail), align="R")

        pdf.set_xy(5.23, 3.60)
        pdf.cell(1.35, 0.31, safe_text(empresa_telefono), align="R")

        pdf.set_xy(7.03, 3.60)
        pdf.cell(0.76, 0.31, safe_text(empresa_ext), align="C")

        # ---------------------------
        # DETALLE DE CONCEPTOS
        # ---------------------------
        total_global = 0
        y = 4.50
        pagina_actual = 1

        y_max_pagina_1 = 8.60
        y_max_otras_paginas = 9.20

        for ruta_sel in ids_seleccionados:
            id_ruta = ruta_sel.split(" | ")[0]

            if id_ruta not in df.index:
                continue

            ruta_data = df.loc[id_ruta]

            concepto_ruta = str(ruta_data.get("Concepto", ""))
            kms_ruta = str(ruta_data.get("KMS", ""))
            cantidad_ruta = str(ruta_data.get("Cantidad", ""))
            origen = str(ruta_data.get("Origen", ""))
            destino = str(ruta_data.get("Destino", ""))

            pdf.set_body_font(bold=True, size=7)

            pdf.set_xy(0.85, y)
            pdf.cell(
                5.50,
                0.16,
                safe_text(f"{origen} - {destino}"),
                align="L"
            )
            y += 0.18

            pdf.set_body_font(size=6.5)

            pdf.set_xy(0.85, y)
            pdf.cell(
                2.50,
                0.15,
                safe_text(concepto_ruta),
                align="L"
            )

            pdf.set_xy(3.50, y)
            pdf.cell(
                1.20,
                0.15,
                safe_text(kms_ruta),
                align="L"
            )

            pdf.set_xy(5.00, y)
            pdf.cell(
                1.50,
                0.15,
                safe_text(cantidad_ruta),
                align="L"
            )

            y += 0.25

            # salto de pagina antes del bloque de ruta
            y_max = y_max_pagina_1 if pagina_actual == 1 else y_max_otras_paginas

            if y + 0.35 > y_max:
                pdf.add_page()
                pagina_actual += 1
                y = 2.00

            cfg = rutas_config.get(ruta_sel, {"sumar": [], "visual": []})
            conceptos_orden = cfg["sumar"] + cfg["visual"]

            for campo in conceptos_orden:
                if campo not in ruta_data or pd.isna(ruta_data[campo]):
                    continue

                valor = float(ruta_data[campo] or 0)

                if campo == "Ingreso_Original":
                    moneda_original = ruta_data.get("Moneda", "MXP")
                elif campo == "Cruce_Original":
                    moneda_original = ruta_data.get("Moneda_Cruce", "MXP")
                else:
                    moneda_original = "MXP"

                valor_convertido = convertir_moneda(
                    valor,
                    moneda_original,
                    moneda_cotizacion,
                    tipo_cambio
                )

                es_cobrado = campo in cfg["sumar"]

                if es_cobrado:
                    pdf.set_text_color(37, 45, 128)
                else:
                    pdf.set_text_color(150, 150, 150)

                pdf.set_body_font(size=7)

                pdf.set_xy(0.85, y)
                pdf.cell(3.20, 0.15, safe_text(label_de(campo)), align="L")

                pdf.set_xy(4.00, y)
                pdf.cell(0.70, 0.15, safe_text(str(ruta_data.get("KM", "") or "")), align="C")

                pdf.set_xy(5.10, y)
                pdf.cell(0.55, 0.15, "1" if es_cobrado else "", align="C")

                pdf.set_xy(5.85, y)
                pdf.cell(0.65, 0.15, moneda_cotizacion, align="C")

                pdf.set_xy(6.55, y)
                pdf.cell(1.05, 0.15, f"${valor_convertido:,.2f}", align="R")

                if es_cobrado:
                    total_global += valor_convertido

                y += 0.18

        # ---------------------------
        # TOTAL
        # ---------------------------
        pdf.set_body_font(bold=True, size=8)

        pdf.set_xy(5.85, 9.15)
        pdf.cell(0.70, 0.15, moneda_cotizacion, align="C")

        pdf.set_xy(6.55, 9.15)
        pdf.cell(1.00, 0.15, f"${total_global:,.2f}", align="R")

        # ---------------------------
        # NOTAS
        # ---------------------------
        pdf.set_body_font(size=6.5)

        pdf.set_xy(0.90, 9.60)
        pdf.multi_cell(
            4.50,
            0.12,
            safe_text(notas_cotizacion),
            align="L"
        )

        file_name = f"Cotizacion-Picus-{fecha.strftime('%d-%m-%Y')}.pdf"
        pdf_bytes = pdf.output(dest="S").encode("latin-1")

        st.download_button(
            "📄 Descargar Cotización en PDF",
            data=pdf_bytes,
            file_name=file_name,
            mime="application/pdf"
        )
