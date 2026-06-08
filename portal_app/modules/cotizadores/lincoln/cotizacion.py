"""
cotizacion.py – Lincoln Freight (USA/MX)
Generador de cotización formal en PDF para enviar al cliente.
- Solo muestra conceptos de INGRESO (no costos internos)
- PDF con reportlab (io.BytesIO, sin archivos temporales)
- Columnas alineadas al nuevo _shared.py
"""

from __future__ import annotations

import io
import os
from datetime import date

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from services.supabase_client import get_supabase_client
from ui.components import section_header, alert, divider
from ._shared import TABLE_RUTAS, cargar_datos_generales, safe


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _find_logo() -> str | None:
    img_dir = os.path.join(_project_root(), "img")
    for name in [
        "Lincoln Original.png", "Lincoln White.png",
        "LicolnF Original.png", "LicolnF White.png",
        "ADT PGL GRAL NO TXT.png",
    ]:
        path = os.path.join(img_dir, name)
        if os.path.exists(path):
            return path
    return None


@st.cache_data(show_spinner=False, ttl=120)
def _cargar_rutas(table: str) -> pd.DataFrame:
    sb = get_supabase_client()
    if sb is None:
        return pd.DataFrame()
    try:
        resp = sb.table(table).select("*").execute()
        df = pd.DataFrame(resp.data or [])
        if not df.empty and "Fecha" in df.columns:
            df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d")
        return df
    except Exception:
        return pd.DataFrame()


# Conceptos de ingreso por columna guardada
# (nombre visible al cliente, columna en Supabase, mostrar por defecto)
CONCEPTOS_INGRESO: list[tuple[str, str, bool]] = [
    ("Flete USA",       "Ingreso_Flete_USA",  True),
    ("Fuel Surcharge",  "Ingreso_Fuel_USA",   True),
    ("Cruce",           "Ingreso_Cruce",      True),
    ("Flete MX",        "Ingreso_MX_USD",     False),
]

EXTRAS_CAMPOS: list[tuple[str, str]] = [
    ("Stop Off",          "Otros_Cargos_Ingreso"),   # fallback genérico
]


# ─────────────────────────────────────────────
# GENERADOR PDF
# ─────────────────────────────────────────────
def _generar_pdf(
    *,
    fecha_cot: date,
    cli_nombre: str,
    cli_dir: str,
    cli_mail: str,
    emp_nombre: str,
    emp_mail: str,
    emp_tel: str,
    moneda: str,
    tc: float,
    filas: list[dict],   # [{ruta_label, conceptos: [{nombre, valor_usd}]}]
    notas: str,
    logo_path: str | None,
) -> bytes:
    """
    Genera cotización en PDF usando reportlab.
    filas: cada elemento tiene ruta_label y una lista de conceptos con nombre y valor_usd.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=12 * mm,  bottomMargin=12 * mm,
    )

    styles = getSampleStyleSheet()
    AZUL   = colors.HexColor("#1B2266")
    AZUL_L = colors.HexColor("#dee6f5")
    GRIS   = colors.HexColor("#f5f5ff")
    BLANCO = colors.white

    h1_s  = ParagraphStyle("H1",  parent=styles["Normal"],  fontSize=16, textColor=AZUL,
                             fontName="Helvetica-Bold", spaceAfter=2)
    h2_s  = ParagraphStyle("H2",  parent=styles["Normal"],  fontSize=10, textColor=AZUL,
                             fontName="Helvetica-Bold", spaceAfter=2)
    sub_s = ParagraphStyle("Sub", parent=styles["Normal"],  fontSize=8,  textColor=colors.HexColor("#555"),
                             spaceAfter=1)
    norm  = ParagraphStyle("N",   parent=styles["Normal"],  fontSize=9,  leading=13)
    foot  = ParagraphStyle("F",   parent=styles["Normal"],  fontSize=7,
                             textColor=colors.HexColor("#888"), alignment=TA_CENTER)

    story: list = []

    # ── Encabezado (logo + datos empresa) ────────────────────────
    logo_cell: list = []
    if logo_path and os.path.exists(logo_path):
        try:
            logo_cell = [Image(logo_path, width=45 * mm, height=18 * mm)]
        except Exception:
            logo_cell = [Paragraph("LINCOLN FREIGHT", h1_s)]
    else:
        logo_cell = [Paragraph("<b>LINCOLN FREIGHT</b>", h1_s)]

    empresa_info = [
        Paragraph(f"<b>{emp_nombre}</b>", h2_s),
        Paragraph(emp_mail,  sub_s),
        Paragraph(emp_tel,   sub_s),
    ]

    hdr_tbl = Table(
        [[logo_cell, empresa_info]],
        colWidths=[80 * mm, None],
    )
    hdr_tbl.setStyle(TableStyle([
        ("VALIGN",  (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",   (1, 0), (1, 0),   "RIGHT"),
    ]))
    story.append(hdr_tbl)
    story.append(Spacer(1, 6 * mm))

    # ── Título + datos cliente ────────────────────────────────────
    cot_hdr = Table([[
        Paragraph("<b>COTIZACIÓN DE FLETE</b>",
                  ParagraphStyle("CH", parent=styles["Normal"], fontSize=13,
                                 textColor=BLANCO, fontName="Helvetica-Bold")),
        Paragraph(f"Fecha: {fecha_cot}",
                  ParagraphStyle("CF", parent=styles["Normal"], fontSize=9,
                                 textColor=BLANCO, alignment=TA_RIGHT)),
    ]], colWidths=[110 * mm, None])
    cot_hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), AZUL),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (0, -1),  10),
        ("RIGHTPADDING",  (-1, 0), (-1, -1), 10),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(cot_hdr)
    story.append(Spacer(1, 4 * mm))

    cli_rows = [
        ["Cliente:", cli_nombre],
        ["Dirección:", cli_dir or "—"],
        ["Email:", cli_mail  or "—"],
    ]
    cli_tbl = Table(cli_rows, colWidths=[25 * mm, None])
    cli_tbl.setStyle(TableStyle([
        ("FONTNAME",  (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE",  (0, 0), (-1, -1), 9),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(cli_tbl)
    story.append(Spacer(1, 5 * mm))

    # ── Tabla de conceptos ────────────────────────────────────────
    col_w_desc = 115 * mm
    col_w_val  = 55  * mm

    # Encabezado de tabla
    tbl_data: list[list] = [[
        Paragraph("RUTA / CONCEPTO",
                  ParagraphStyle("TH", parent=styles["Normal"], fontSize=9,
                                 textColor=BLANCO, fontName="Helvetica-Bold")),
        Paragraph(f"TARIFA ({moneda})",
                  ParagraphStyle("THR", parent=styles["Normal"], fontSize=9,
                                 textColor=BLANCO, fontName="Helvetica-Bold", alignment=TA_RIGHT)),
    ]]

    total_general = 0.0
    row_styles: list[tuple] = [
        ("BACKGROUND",    (0, 0), (-1, 0),  AZUL),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  BLANCO),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
    ]
    fill = True
    row_idx = 1   # 0 es el header

    for fila in filas:
        subtotal_usd = sum(c["valor_usd"] for c in fila["conceptos"])
        subtotal_show = subtotal_usd * tc if moneda == "MXP" else subtotal_usd

        # Fila de ruta (subtítulo)
        tbl_data.append([
            Paragraph(f"<b>{fila['ruta_label']}</b>",
                      ParagraphStyle("RL", parent=styles["Normal"], fontSize=9,
                                     fontName="Helvetica-Bold")),
            Paragraph(f"<b>${subtotal_show:,.2f}</b>",
                      ParagraphStyle("RLR", parent=styles["Normal"], fontSize=9,
                                     fontName="Helvetica-Bold", alignment=TA_RIGHT)),
        ])
        row_styles.append(("BACKGROUND", (0, row_idx), (-1, row_idx), AZUL_L))
        row_idx += 1

        # Líneas de conceptos
        for concepto in fila["conceptos"]:
            v_show = concepto["valor_usd"] * tc if moneda == "MXP" else concepto["valor_usd"]
            bg = GRIS if fill else BLANCO
            tbl_data.append([
                Paragraph(f"  · {concepto['nombre']}", norm),
                Paragraph(f"${v_show:,.2f}",
                          ParagraphStyle("CR", parent=styles["Normal"], fontSize=9,
                                         alignment=TA_RIGHT)),
            ])
            row_styles.append(("BACKGROUND", (0, row_idx), (-1, row_idx), bg))
            row_idx += 1
            fill = not fill

        total_general += subtotal_usd

    # Fila de total
    total_show = total_general * tc if moneda == "MXP" else total_general
    tbl_data.append([
        Paragraph("<b>TOTAL GENERAL</b>",
                  ParagraphStyle("TOT", parent=styles["Normal"], fontSize=10,
                                 textColor=BLANCO, fontName="Helvetica-Bold")),
        Paragraph(f"<b>${total_show:,.2f} {moneda}</b>",
                  ParagraphStyle("TOTR", parent=styles["Normal"], fontSize=10,
                                 textColor=BLANCO, fontName="Helvetica-Bold",
                                 alignment=TA_RIGHT)),
    ])
    row_styles += [
        ("BACKGROUND", (0, row_idx), (-1, row_idx), AZUL),
        ("TEXTCOLOR",  (0, row_idx), (-1, row_idx), BLANCO),
        ("FONTNAME",   (0, row_idx), (-1, row_idx), "Helvetica-Bold"),
    ]

    tbl = Table(tbl_data, colWidths=[col_w_desc, col_w_val])
    tbl.setStyle(TableStyle(row_styles))
    story.append(tbl)

    # ── Notas ────────────────────────────────────────────────────
    if notas.strip():
        story.append(Spacer(1, 5 * mm))
        story.append(Paragraph("<b>Notas:</b>", h2_s))
        story.append(Paragraph(notas.replace("\n", "<br/>"), norm))

    # ── Footer ───────────────────────────────────────────────────
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(
        f"Cotización generada por {emp_nombre} · {fecha_cot}",
        foot,
    ))

    doc.build(story)
    return buf.getvalue()


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
        alert("warn", "No hay rutas guardadas.")
        alert("info", "Captura rutas primero desde la pestaña Captura de Rutas.")
        return

    valores = cargar_datos_generales()

    # ── Label para selector ───────────────────────────────────────
    def _label(row: pd.Series) -> str:
        return (
            f"{row.get('ID_Ruta', '')} | {row.get('Fecha', '')} | "
            f"{row.get('Tipo', '')} | {row.get('Cliente', '—')} | "
            f"{row.get('Origen', '')} → {row.get('Destino', '')}"
        )

    df["_label"] = df.apply(_label, axis=1)

    # ══════════════════════════════════════════════════════════════
    # 1. Selección de rutas
    # ══════════════════════════════════════════════════════════════
    section_header("1.", "Seleccionar rutas a cotizar")
    rutas_sel = st.multiselect(
        "Rutas disponibles",
        df["_label"].tolist(),
        key="ln_cot_rutas",
    )
    if not rutas_sel:
        alert("info", "Selecciona al menos una ruta para continuar.")
        return

    rows_sel = df[df["_label"].isin(rutas_sel)]

    # ══════════════════════════════════════════════════════════════
    # 2. Conceptos por ruta
    # ══════════════════════════════════════════════════════════════
    divider()
    section_header("2.", "Conceptos a incluir por ruta")
    st.caption("Solo se muestran conceptos con valor > 0. Marca los que quieras incluir.")

    filas_pdf: list[dict] = []

    for _, row in rows_sel.iterrows():
        id_ruta    = row.get("ID_Ruta", "")
        ruta_label = (
            f"{row.get('Tipo', '')} | "
            f"{row.get('Origen', '')} → {row.get('Destino', '')} | "
            f"{row.get('Cliente', '')}"
        )

        with st.expander(f"📋 {ruta_label}", expanded=True):
            conceptos_seleccionados: list[dict] = []
            col_l, col_r = st.columns(2)

            # Conceptos principales
            with col_l:
                st.caption("Conceptos de ingreso:")
                for nombre, campo, default_on in CONCEPTOS_INGRESO:
                    val = safe(row.get(campo, 0))
                    if val > 0:
                        checked = st.checkbox(
                            f"{nombre} (${val:,.2f})",
                            value=default_on,
                            key=f"ln_cot_{id_ruta}_{campo}",
                        )
                        if checked:
                            conceptos_seleccionados.append({"nombre": nombre, "valor_usd": val})

            # Otros cargos
            with col_r:
                st.caption("Otros cargos extras:")
                otros_json_str = str(row.get("Otros_Cargos_JSON", "") or "")
                otros_ing      = safe(row.get("Otros_Cargos_Ingreso", 0))

                # Intentar parsear JSON de otros cargos
                extras_parseados: dict = {}
                if otros_json_str and otros_json_str not in ("", "None", "{}"):
                    try:
                        import ast
                        extras_parseados = ast.literal_eval(otros_json_str)
                    except Exception:
                        pass

                if extras_parseados:
                    for nombre_e, monto_e in extras_parseados.items():
                        if safe(monto_e) > 0:
                            checked_e = st.checkbox(
                                f"{nombre_e} (${safe(monto_e):,.2f})",
                                value=True,
                                key=f"ln_cot_{id_ruta}_ext_{nombre_e}",
                            )
                            if checked_e:
                                conceptos_seleccionados.append(
                                    {"nombre": nombre_e, "valor_usd": safe(monto_e)}
                                )
                elif otros_ing > 0:
                    checked_o = st.checkbox(
                        f"Otros Cargos (${otros_ing:,.2f})",
                        value=False,
                        key=f"ln_cot_{id_ruta}_otros",
                    )
                    if checked_o:
                        conceptos_seleccionados.append(
                            {"nombre": "Otros Cargos", "valor_usd": otros_ing}
                        )
                else:
                    st.caption("Sin extras registrados.")

        filas_pdf.append({"ruta_label": ruta_label, "conceptos": conceptos_seleccionados})

    # ══════════════════════════════════════════════════════════════
    # 3. Datos del cliente
    # ══════════════════════════════════════════════════════════════
    divider()
    section_header("3.", "Datos del Cliente")
    c1, c2 = st.columns(2)
    cli_nombre = c1.text_input("Nombre del cliente *", key="ln_cot_cli")
    cli_mail   = c2.text_input("Email del cliente",    key="ln_cot_cli_mail")
    cli_dir    = st.text_input("Dirección (opcional)", key="ln_cot_cli_dir")

    # ══════════════════════════════════════════════════════════════
    # 4. Datos del emisor y moneda
    # ══════════════════════════════════════════════════════════════
    divider()
    section_header("4.", "Emisor y Moneda")
    e1, e2, e3 = st.columns(3)
    emp_nombre = e1.text_input("Empresa emisora", value="Lincoln Freight LLC", key="ln_cot_emp")
    emp_mail   = e2.text_input("Email empresa",   key="ln_cot_emp_mail")
    emp_tel    = e3.text_input("Teléfono",        key="ln_cot_tel")

    m1, m2, m3 = st.columns(3)
    moneda    = m1.selectbox("Moneda", ["USD", "MXP"], key="ln_cot_moneda")
    tc_raw    = float(valores.get("Tipo de Cambio USD/MXP", 18.50))
    tc_cot    = m2.number_input("Tipo de Cambio USD/MXP",
                                 value=tc_raw, step=0.1, format="%.2f", key="ln_cot_tc")
    fecha_cot = m3.date_input("Fecha de cotización", value=date.today(), key="ln_cot_fecha")

    # ══════════════════════════════════════════════════════════════
    # 5. Notas y generación
    # ══════════════════════════════════════════════════════════════
    divider()
    notas = st.text_area(
        "📝 Notas / Términos y Condiciones (opcional)",
        placeholder="Ej: Vigencia 5 días hábiles. Sujeto a disponibilidad de unidades…",
        height=80,
        key="ln_cot_notas",
    )

    divider()
    if st.button("📄 Generar PDF de Cotización", type="primary",
                 use_container_width=True, key="ln_cot_gen"):

        if not cli_nombre.strip():
            alert("error", "Ingresa el nombre del cliente.")
            return

        tiene_conceptos = any(len(f["conceptos"]) > 0 for f in filas_pdf)
        if not tiene_conceptos:
            alert("warn", "Selecciona al menos un concepto para incluir en el PDF.")
            return

        try:
            pdf_bytes = _generar_pdf(
                fecha_cot      = fecha_cot,
                cli_nombre     = cli_nombre.strip(),
                cli_dir        = cli_dir.strip(),
                cli_mail       = cli_mail.strip(),
                emp_nombre     = emp_nombre.strip(),
                emp_mail       = emp_mail.strip(),
                emp_tel        = emp_tel.strip(),
                moneda         = moneda,
                tc             = tc_cot,
                filas          = filas_pdf,
                notas          = notas,
                logo_path      = _find_logo(),
            )
            fname = (
                f"Cotizacion_Lincoln_{cli_nombre.strip().replace(' ','_')}_{fecha_cot}.pdf"
            )
            st.download_button(
                "📥 Descargar Cotización",
                data      = pdf_bytes,
                file_name = fname,
                mime      = "application/pdf",
                use_container_width=True,
                key       = "ln_cot_dl",
            )
            alert("success", "✅ PDF generado exitosamente.")
        except Exception as e:
            alert("error", f"Error generando PDF: {e}")
