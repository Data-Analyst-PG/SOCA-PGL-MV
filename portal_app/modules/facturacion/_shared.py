"""
portal_app/modules/facturacion/_shared.py

Lógica compartida del módulo de facturación:
  - perfil_riesgo()               → calcula estado de riesgo del cliente
  - generar_pdf_estado_cuenta()   → genera PDF descargable con velocímetro y barra
  - leer_json() / guardar_json()  → acceso al JSON de datos
"""
import io
import base64
import json
import math
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
# FLOWABLES PERSONALIZADOS PARA PDF
# ══════════════════════════════════════════════════════════════════════════════

def _make_gauge_flowable(estado: str, color_hex: str, angulo: int, width_pt: float):
    """
    Velocímetro vectorial dibujado con reportlab canvas.
    angulo: -75 (riesgo) … +75 (excelente), igual que en el SVG de Streamlit.
    """
    from reportlab.platypus import Flowable
    from reportlab.lib import colors

    class GaugeFlowable(Flowable):
        def __init__(self):
            super().__init__()
            self.width  = width_pt
            self.height = width_pt * 0.72   # proporción del velocímetro

        def draw(self):
            c   = self.canv
            cx  = self.width / 2
            cy  = self.height * 0.52
            r   = min(cx, cy) * 0.82        # radio del arco

            # ── Arcos de color (izq→der: rojo, naranja, verde) ──────────────
            # reportlab arc: ángulo 0 = derecha, 90 = arriba (sentido antihorario)
            # El semicírculo superior va de 0° a 180°.
            # Dividimos en 3 segmentos iguales de 60° cada uno.
            arc_cfg = [
                (colors.HexColor("#DC2626"), 120, 180),   # rojo  (izq)
                (colors.HexColor("#D97706"),  60, 120),   # naranja (centro)
                (colors.HexColor("#059669"),   0,  60),   # verde (der)
            ]
            stroke_w = r * 0.18
            for clr, a1, a2 in arc_cfg:
                c.setStrokeColor(clr)
                c.setLineWidth(stroke_w)
                c.setLineCap(1)   # round caps
                c.arc(
                    cx - r, cy - r,
                    cx + r, cy + r,
                    startAng=a1, extent=a2 - a1,
                )

            # ── Aguja ────────────────────────────────────────────────────────
            # angulo del SVG: 0=arriba, positivo=derecha, negativo=izquierda
            # Mapeamos al sistema de reportlab (0=derecha, +antihorario)
            # SVG +75 → apunta a derecha → reportlab 0°  + offset
            # SVG   0 → apunta arriba    → reportlab 90°
            # SVG -75 → apunta izquierda → reportlab 180°
            needle_angle_rl = 90 - angulo   # conversión
            needle_rad      = math.radians(needle_angle_rl)
            needle_len      = r * 0.78
            nx = cx + needle_len * math.cos(needle_rad)
            ny = cy + needle_len * math.sin(needle_rad)

            c.setStrokeColor(colors.HexColor("#1B2266"))
            c.setLineWidth(stroke_w * 0.38)
            c.setLineCap(1)
            c.line(cx, cy, nx, ny)

            # Círculo central
            dot_r = stroke_w * 0.55
            c.setFillColor(colors.HexColor("#1B2266"))
            c.circle(cx, cy, dot_r, fill=1, stroke=0)
            c.setFillColor(colors.white)
            c.circle(cx, cy, dot_r * 0.5, fill=1, stroke=0)

            # ── Badge de estado ──────────────────────────────────────────────
            badge_color = colors.HexColor(color_hex)
            badge_w, badge_h = self.width * 0.52, 14
            badge_x = cx - badge_w / 2
            badge_y = cy - r * 0.55

            c.setFillColor(badge_color)
            c.roundRect(badge_x, badge_y, badge_w, badge_h, 7, fill=1, stroke=0)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 7)
            c.drawCentredString(cx, badge_y + 4, f"● {estado}")

            # ── Etiquetas Riesgo / Vigilancia / Excelente ───────────────────
            label_y = cy - r * 0.18
            c.setFont("Helvetica", 5.5)
            c.setFillColor(colors.HexColor("#DC2626"))
            c.drawString(cx - r * 0.95, label_y, "Riesgo")
            c.setFillColor(colors.HexColor("#D97706"))
            c.drawCentredString(cx, label_y, "Vigilancia")
            c.setFillColor(colors.HexColor("#059669"))
            c.drawRightString(cx + r * 0.95, label_y, "Excelente")

    return GaugeFlowable()


def _make_creditbar_flowable(usado: float, limite: float,
                              color_hex: str, width_pt: float):
    """Barra de crédito con porcentaje, montos y etiquetas."""
    from reportlab.platypus import Flowable
    from reportlab.lib import colors

    class CreditBarFlowable(Flowable):
        def __init__(self):
            super().__init__()
            self.width  = width_pt
            self.height = 56

        def draw(self):
            c    = self.canv
            pct  = min(usado / limite * 100, 100) if limite else 0
            disp = 100 - pct
            clr  = colors.HexColor(color_hex)

            # ── Números grandes ──────────────────────────────────────────────
            c.setFont("Helvetica-Bold", 16)
            c.setFillColor(clr)
            c.drawString(0, 38, f"{pct:.0f}%")
            c.setFillColor(colors.HexColor("#059669"))
            c.drawRightString(self.width, 38, f"{disp:.0f}%")

            # Etiquetas pequeñas
            c.setFont("Helvetica", 6)
            c.setFillColor(colors.HexColor("#9CA3AF"))
            c.drawString(0, 30, "UTILIZADO")
            c.drawRightString(self.width, 30, "DISPONIBLE")

            # ── Barra ────────────────────────────────────────────────────────
            bar_y, bar_h, radius = 16, 9, 4
            # Fondo
            c.setFillColor(colors.HexColor("#E5E9F0"))
            c.roundRect(0, bar_y, self.width, bar_h, radius, fill=1, stroke=0)
            # Relleno
            filled_w = max(self.width * pct / 100, radius * 2)
            c.setFillColor(clr)
            c.roundRect(0, bar_y, filled_w, bar_h, radius, fill=1, stroke=0)

            # ── Montos ───────────────────────────────────────────────────────
            c.setFont("Helvetica", 6.5)
            c.setFillColor(colors.HexColor("#6B7280"))
            c.drawString(0, 4, f"Usado:  ${usado:,.0f}")
            c.drawRightString(self.width, 4, f"Limite:  ${limite:,.0f}")

    return CreditBarFlowable()


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
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, KeepTogether,
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=0.65*inch, rightMargin=0.65*inch,
        topMargin=0.6*inch,   bottomMargin=0.6*inch,
    )

    PAGE_W = letter[0] - 1.3*inch   # ancho útil

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

    # ── Encabezado ────────────────────────────────────────────────────────────
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

    # ── Info cliente ──────────────────────────────────────────────────────────
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

    # ── KPIs ──────────────────────────────────────────────────────────────────
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

    # ── Tabla de facturas ─────────────────────────────────────────────────────
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

    fact_tbl = Table(
        rows,
        colWidths=[1.1*inch, 1.0*inch, 1.0*inch, 1.1*inch, 0.9*inch, 1.0*inch],
        repeatRows=1,
    )
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
            tbl_style += [
                ("TEXTCOLOR",(0,i),(0,i),red),
                ("TEXTCOLOR",(4,i),(4,i),red),
                ("TEXTCOLOR",(5,i),(5,i),red),
            ]
    fact_tbl.setStyle(TableStyle(tbl_style))
    story.extend([fact_tbl, Spacer(1, 18)])

    # ── Panel inferior: Velocímetro | Barra crédito | Info pago ──────────────
    story.append(HRFlowable(width="100%", thickness=1, color=BORD, spaceAfter=8))
    story.append(Paragraph("<b>ANÁLISIS DE RIESGO Y CRÉDITO</b>", sty(9, True, NAVY)))
    story.append(Spacer(1, 8))

    # Columnas: velocímetro (2.2") | barra crédito (2.2") | info pago (2.7")
    col_gauge = 2.2 * inch
    col_bar   = 2.2 * inch
    col_pay   = PAGE_W - col_gauge - col_bar

    # Calcular angulo desde el estado
    _angulo_map = {"EXCELENTE": 75, "CLIENTE SANO": 25, "VIGILANCIA": -25, "RIESGO": -75}
    angulo_pdf  = _angulo_map.get(estado, 0)
    pct_usado   = min(total / cliente["limite_credito"] * 100, 100) if cliente["limite_credito"] else 0

    gauge_fw = _make_gauge_flowable(estado, color_r, angulo_pdf, col_gauge - 10)
    bar_fw   = _make_creditbar_flowable(total, cliente["limite_credito"], color_r, col_bar - 10)

    # Info pago como párrafos
    pago_items = [
        ("Banco",   cliente["banco"]),
        ("Empresa", cliente["banco_empresa"]),
        ("Cuenta",  cliente["cuenta_bancaria"]),
        ("SWIFT",   cliente["swift"]),
        ("Tel.",    cliente["telefono"]),
    ]
    pago_rows_pdf = []
    for label, val in pago_items:
        pago_rows_pdf.append([
            Paragraph(f"<b>{label}</b>", sty(7, True, GRAY)),
            Paragraph(val, sty(7)),
        ])
    pago_tbl = Table(pago_rows_pdf, colWidths=[0.65*inch, col_pay - 0.65*inch])
    pago_tbl.setStyle(TableStyle([
        ("TOPPADDING",    (0,0),(-1,-1), 3),
        ("BOTTOMPADDING", (0,0),(-1,-1), 3),
        ("ROWBACKGROUNDS",(0,0),(-1,-1), [WHITE, FBGR]),
        ("GRID",          (0,0),(-1,-1), 0.3, BORD),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
    ]))

    # Labels de sección sobre cada columna
    lbl_gauge = Paragraph("PERFIL DE RIESGO",    sty(6, True, LGRAY, TA_CENTER))
    lbl_bar   = Paragraph("LÍNEA DE CRÉDITO",    sty(6, True, LGRAY, TA_CENTER))
    lbl_pay   = Paragraph("INFORMACIÓN DE PAGO", sty(6, True, LGRAY))

    panel = Table([[
        lbl_gauge, lbl_bar, lbl_pay,
    ],[
        gauge_fw, bar_fw, pago_tbl,
    ]], colWidths=[col_gauge, col_bar, col_pay])
    panel.setStyle(TableStyle([
        ("VALIGN",        (0,0),(-1,-1), "TOP"),
        ("TOPPADDING",    (0,0),(-1,-1), 4),
        ("BOTTOMPADDING", (0,0),(-1,-1), 4),
        ("LEFTPADDING",   (0,0),(-1,-1), 4),
        ("RIGHTPADDING",  (0,0),(-1,-1), 4),
        ("LINEAFTER",     (0,0),(1,-1),  0.4, BORD),
    ]))
    story.append(KeepTogether(panel))

    # ── Notas de pago ─────────────────────────────────────────────────────────
    if cliente.get("notas_pago"):
        story.extend([Spacer(1, 6),
                      Paragraph(cliente["notas_pago"], sty(7, False, LGRAY))])

    # ── Pie ───────────────────────────────────────────────────────────────────
    story.extend([
        Spacer(1, 20),
        HRFlowable(width="100%", thickness=0.5, color=BORD),
        Spacer(1, 4),
        Paragraph(
            "Generado por SOCA · Palos Garza Logistics · Documento confidencial",
            sty(7, False, LGRAY, TA_CENTER),
        ),
    ])

    doc.build(story)
    return buf.getvalue()


# ── Alias de compatibilidad ───────────────────────────────────────────────────
def estado_cuenta_page():
    import streamlit as st
    st.error("Usa las páginas pg_fact_estado_cuenta.py y pg_fact_cargar_datos.py")
