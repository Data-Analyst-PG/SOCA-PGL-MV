"""
portal_app/modules/facturacion/facturacion.py

Lógica compartida del módulo de facturación:
  - perfil_riesgo()               → calcula estado de riesgo del cliente
  - generar_pdf_estado_cuenta()   → genera PDF descargable
  - leer_json() / guardar_json()  → acceso al JSON de datos

Las páginas UI están en:
  - pages/pg_fact_estado_cuenta.py  → dashboard
  - pages/pg_fact_cargar_datos.py   → carga de datos
"""
import io
import base64
import json
import os
from datetime import date


# ── Logo ──────────────────────────────────────────────────────────────────────
def _load_logo_b64() -> str:
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "..", "img", "Color PGL MS.png"),
        os.path.join(os.path.dirname(__file__), "..", "..", "img", "PGL LOGO.png"),
    ]
    for p in candidates:
        p = os.path.abspath(p)
        if os.path.exists(p):
            return base64.b64encode(open(p, "rb").read()).decode()
    return ""

LOGO_B64 = _load_logo_b64()

# ── JSON ──────────────────────────────────────────────────────────────────────
_JSON_PATH = os.path.join(os.path.dirname(__file__), "datos_facturacion.json")

def leer_json() -> dict:
    with open(_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def guardar_json(data: dict):
    with open(_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


# ══════════════════════════════════════════════════════════════════════════════
# LÓGICA DE NEGOCIO
# ══════════════════════════════════════════════════════════════════════════════

def perfil_riesgo(dias_max: int, pct_usado: float):
    """Devuelve (etiqueta, color_hex, angulo_aguja)."""
    if dias_max == 0 and pct_usado < 70:
        return "EXCELENTE",    "#059669",  75
    elif dias_max <= 3 and pct_usado < 85:
        return "CLIENTE SANO", "#2E7D32",  25
    elif dias_max <= 10 or pct_usado < 95:
        return "VIGILANCIA",   "#D97706", -25
    else:
        return "RIESGO",       "#DC2626", -75


# ══════════════════════════════════════════════════════════════════════════════
# GENERADOR PDF
# ══════════════════════════════════════════════════════════════════════════════

def generar_pdf_estado_cuenta(cliente: dict, facturas: list,
                               total: float, estado: str, color_r: str) -> bytes:
    """Genera bytes del PDF del estado de cuenta para st.download_button()."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=0.65*inch, rightMargin=0.65*inch,
        topMargin=0.6*inch,   bottomMargin=0.6*inch,
    )

    NAVY  = colors.HexColor("#1B2266")
    GRAY  = colors.HexColor("#6B7280")
    LGRAY = colors.HexColor("#9CA3AF")
    WHITE = colors.white
    FBGR  = colors.HexColor("#F8FAFF")
    BORD  = colors.HexColor("#E5E9F0")
    RISK  = colors.HexColor(color_r)

    styles = getSampleStyleSheet()

    def sty(size=9, bold=False, color=None, align=TA_LEFT):
        color = color or NAVY
        return ParagraphStyle(
            "_", parent=styles["Normal"], fontSize=size,
            fontName="Helvetica-Bold" if bold else "Helvetica",
            textColor=color, alignment=align, leading=size + 3,
        )

    story = []

    # Encabezado
    hdr = Table([[
        Paragraph("<b>ESTADO DE CUENTA</b>", sty(16, True, WHITE, TA_LEFT)),
        Paragraph(f"Emitido: {date.today().strftime('%d de %B de %Y')}",
                  sty(9, False, colors.HexColor("#CBD5E1"), TA_RIGHT)),
    ]], colWidths=[4.5*inch, 2.5*inch])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), NAVY),
        ("LEFTPADDING",   (0,0),(0,-1),  18),
        ("RIGHTPADDING",  (-1,0),(-1,-1),18),
        ("TOPPADDING",    (0,0),(-1,-1), 14),
        ("BOTTOMPADDING", (0,0),(-1,-1), 14),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
    ]))
    story.extend([hdr, Spacer(1, 10)])

    # Info cliente
    cli = Table([[
        Paragraph(f"<b>{cliente['nombre']}</b>", sty(13, True, NAVY)),
        Paragraph(f"<b>● {estado}</b>", sty(10, True, RISK, TA_RIGHT)),
    ],[
        Paragraph(f"{cliente['razon_social']}  ·  {cliente['condiciones_pago']}", sty(9, False, GRAY)),
        "",
    ]], colWidths=[4.5*inch, 2.5*inch])
    cli.setStyle(TableStyle([
        ("TOPPADDING",    (0,0),(-1,-1), 4),
        ("BOTTOMPADDING", (0,0),(-1,-1), 2),
        ("VALIGN",        (0,0),(-1,-1), "TOP"),
    ]))
    story.extend([cli, HRFlowable(width="100%", thickness=1.5, color=BORD, spaceAfter=8)])

    # KPIs
    kpi = Table([[
        Paragraph("LÍMITE DE CRÉDITO", sty(7, False, LGRAY, TA_CENTER)),
        Paragraph("CONDICIONES",        sty(7, False, LGRAY, TA_CENTER)),
        Paragraph("TOTAL BALANCE",      sty(7, False, LGRAY, TA_CENTER)),
        Paragraph("FACTURAS ACTIVAS",   sty(7, False, LGRAY, TA_CENTER)),
    ],[
        Paragraph(f"<b>${cliente['limite_credito']:,.0f} USD</b>", sty(11, True, NAVY, TA_CENTER)),
        Paragraph(f"<b>{cliente['condiciones_pago']}</b>",          sty(11, True, GRAY, TA_CENTER)),
        Paragraph(f"<b>${total:,.0f} USD</b>",                      sty(11, True, RISK, TA_CENTER)),
        Paragraph(f"<b>{len(facturas)}</b>",                        sty(11, True, NAVY, TA_CENTER)),
    ]], colWidths=[1.75*inch]*4)
    kpi.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), FBGR),
        ("BOX",           (0,0),(-1,-1), 0.5, BORD),
        ("INNERGRID",     (0,0),(-1,-1), 0.5, BORD),
        ("TOPPADDING",    (0,0),(-1,-1), 8),
        ("BOTTOMPADDING", (0,0),(-1,-1), 8),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
    ]))
    story.extend([kpi, Spacer(1, 14)])

    # Tabla facturas
    story.append(Paragraph("<b>DETALLE DE FACTURAS</b>", sty(9, True, NAVY)))
    story.append(Spacer(1, 6))

    rows = [["FACTURA","FECHA EMISIÓN","VENCIMIENTO","VIAJE REF.","DÍAS VENCIDO","IMPORTE USD"]]
    for f in facturas:
        rows.append([
            f["folio"],
            f["fecha_emision"].strftime("%d %b %Y"),
            f["fecha_vencimiento"].strftime("%d %b %Y"),
            f["viaje_referencia"],
            str(f["dias_vencido"]),
            f"${f['importe']:,.0f}",
        ])
    rows.append(["","","","","TOTAL BALANCE", f"${total:,.0f}"])

    fact_tbl = Table(rows, colWidths=[1.1*inch,1.0*inch,1.0*inch,1.1*inch,0.9*inch,1.0*inch], repeatRows=1)
    tbl_style = [
        ("BACKGROUND",    (0,0),(-1,0),  NAVY),
        ("TEXTCOLOR",     (0,0),(-1,0),  WHITE),
        ("FONTNAME",      (0,0),(-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0,0),(-1,0),  7),
        ("TOPPADDING",    (0,0),(-1,0),  7),
        ("BOTTOMPADDING", (0,0),(-1,0),  7),
        ("FONTSIZE",      (0,1),(-1,-2), 8),
        ("TOPPADDING",    (0,1),(-1,-2), 5),
        ("BOTTOMPADDING", (0,1),(-1,-2), 5),
        ("ROWBACKGROUNDS",(0,1),(-1,-2), [WHITE, FBGR]),
        ("GRID",          (0,0),(-1,-2), 0.4, BORD),
        ("ALIGN",         (4,0),(5,-1),  "RIGHT"),
        ("BACKGROUND",    (0,-1),(-1,-1), colors.HexColor("#EEF0FF")),
        ("FONTNAME",      (3,-1),(-1,-1), "Helvetica-Bold"),
        ("FONTSIZE",      (0,-1),(-1,-1), 9),
        ("TOPPADDING",    (0,-1),(-1,-1), 7),
        ("BOTTOMPADDING", (0,-1),(-1,-1), 7),
        ("TEXTCOLOR",     (5,-1),(5,-1),  RISK),
        ("SPAN",          (0,-1),(3,-1)),
    ]
    for i, f in enumerate(facturas, start=1):
        if f["dias_vencido"] > 0:
            red = colors.HexColor("#DC2626")
            tbl_style += [("TEXTCOLOR",(0,i),(0,i),red),("TEXTCOLOR",(4,i),(4,i),red),("TEXTCOLOR",(5,i),(5,i),red)]
    fact_tbl.setStyle(TableStyle(tbl_style))
    story.extend([fact_tbl, Spacer(1, 18)])

    # Info de pago
    story.extend([HRFlowable(width="100%", thickness=1, color=BORD, spaceAfter=8),
                  Paragraph("<b>INFORMACIÓN DE PAGO</b>", sty(9, True, NAVY)),
                  Spacer(1, 6)])
    pago_rows = [
        [Paragraph("<b>Banco</b>",    sty(8,True,GRAY)), Paragraph(cliente["banco"],           sty(8))],
        [Paragraph("<b>Empresa</b>",  sty(8,True,GRAY)), Paragraph(cliente["banco_empresa"],   sty(8))],
        [Paragraph("<b>Cuenta</b>",   sty(8,True,GRAY)), Paragraph(cliente["cuenta_bancaria"], sty(8))],
        [Paragraph("<b>SWIFT</b>",    sty(8,True,GRAY)), Paragraph(cliente["swift"],           sty(8))],
        [Paragraph("<b>Teléfono</b>", sty(8,True,GRAY)), Paragraph(cliente["telefono"],        sty(8))],
    ]
    pago_tbl = Table(pago_rows, colWidths=[1.2*inch, 5.9*inch])
    pago_tbl.setStyle(TableStyle([
        ("TOPPADDING",    (0,0),(-1,-1), 4),
        ("BOTTOMPADDING", (0,0),(-1,-1), 4),
        ("ROWBACKGROUNDS",(0,0),(-1,-1), [WHITE, FBGR]),
        ("GRID",          (0,0),(-1,-1), 0.4, BORD),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
    ]))
    story.append(pago_tbl)

    if cliente.get("notas_pago"):
        story.extend([Spacer(1,6), Paragraph(cliente["notas_pago"], sty(7,False,LGRAY))])

    story.extend([Spacer(1,20),
                  HRFlowable(width="100%", thickness=0.5, color=BORD),
                  Spacer(1,4),
                  Paragraph("Generado por SOCA · Palos Garza Logistics · Documento confidencial",
                             sty(7,False,LGRAY,TA_CENTER))])
    doc.build(story)
    return buf.getvalue()


# ── Alias de compatibilidad ───────────────────────────────────────────────────
def estado_cuenta_page():
    """Mantiene compatibilidad con __init__.py existente mientras se migra."""
    import streamlit as st
    st.error("Usa las páginas pg_fact_estado_cuenta.py y pg_fact_cargar_datos.py")
