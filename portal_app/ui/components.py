# portal_app/ui/components.py
# ─────────────────────────────────────────────────────────────────────────────
# Sistema de componentes UI de Palos Garza Logistics
#
# USO RÁPIDO — importa lo que necesites en cualquier módulo:
#   from ui.components import page_banner, kpi_row, module_card, alert, section_header
#
# COMPONENTES DISPONIBLES:
#   page_banner(icono, titulo, subtitulo)
#   section_header(icono, titulo, subtitulo)
#   kpi_row(items)              → items = lista de dicts
#   module_card(...)            → tarjeta con badges de conteo
#   alert(tipo, mensaje)        → info | warn | error | success
#   status_badge(texto, tipo)   → devuelve HTML de un badge
#   divider()                   → separador visual
#   welcome_banner(nombre, rol, area)
# ─────────────────────────────────────────────────────────────────────────────
import streamlit as st
from ui.theme import PGL_NAVY, PGL_RED, PGL_NAVY_LT, PGL_MUTED, PGL_BORDER, PGL_WHITE


# ─────────────────────────────────────────────────────────────────────────────
# 1. BANNER DE PÁGINA
# ─────────────────────────────────────────────────────────────────────────────
def page_banner(icono: str, titulo: str, subtitulo: str = ""):
    sub_html = (
        f'<div style="font-size:0.82rem;color:rgba(255,255,255,0.65);margin-top:0.3rem;">'
        f'{subtitulo}</div>'
    ) if subtitulo else ""
    html = (
        f'<div style="background:linear-gradient(135deg,{PGL_NAVY} 0%,{PGL_NAVY_LT} 100%);'
        f'border-radius:14px;padding:1.3rem 1.8rem;margin-bottom:1.5rem;'
        f'border-left:5px solid {PGL_RED};display:flex;align-items:center;'
        f'gap:1rem;position:relative;overflow:hidden;">'
        f'<div style="position:absolute;right:-10px;top:-10px;font-size:6rem;'
        f'opacity:0.06;line-height:1;pointer-events:none;">{icono}</div>'
        f'<span style="font-size:2rem;flex-shrink:0;">{icono}</span>'
        f'<div>'
        f'<div style="font-size:1.25rem;font-weight:700;color:white;line-height:1.2;">{titulo}</div>'
        f'{sub_html}'
        f'</div>'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# 2. ENCABEZADO DE SECCIÓN
# ─────────────────────────────────────────────────────────────────────────────
def section_header(icono: str, titulo: str, subtitulo: str = ""):
    sub_html = (
        f'<div style="font-size:0.75rem;color:{PGL_MUTED};margin-top:1px;">'
        f'{subtitulo}</div>'
    ) if subtitulo else ""
    html = (
        f'<div style="display:flex;align-items:center;gap:0.65rem;padding:0.7rem 1rem;'
        f'background:rgba(27,34,102,0.06);border-radius:10px;'
        f'border-left:4px solid {PGL_RED};margin-bottom:1rem;">'
        f'<span style="font-size:1.1rem;flex-shrink:0;">{icono}</span>'
        f'<div>'
        f'<div style="font-size:0.95rem;font-weight:700;color:{PGL_NAVY};line-height:1.2;">{titulo}</div>'
        f'{sub_html}'
        f'</div>'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# 3. FILA DE KPIs
# ─────────────────────────────────────────────────────────────────────────────
def kpi_row(items: list):
    cards_html = ""
    for item in items:
        icono = item.get("icono", "")
        label = item.get("label", "")
        valor = item.get("valor", 0)
        sub   = item.get("sub", "")
        color = item.get("color", PGL_NAVY)
        cards_html += (
            f'<div style="background:{PGL_WHITE};border-radius:12px;padding:1rem 1.1rem;'
            f'border:1px solid {PGL_BORDER};border-left:4px solid {color};'
            f'box-shadow:0 2px 8px rgba(27,34,102,0.06);">'
            f'<div style="font-size:0.7rem;font-weight:600;text-transform:uppercase;'
            f'letter-spacing:0.5px;color:{PGL_MUTED};margin-bottom:4px;">'
            f'{icono} {label}</div>'
            f'<div style="font-size:1.9rem;font-weight:800;color:{color};line-height:1.1;">'
            f'{valor}</div>'
            f'<div style="font-size:0.72rem;color:{PGL_MUTED};margin-top:3px;">{sub}</div>'
            f'</div>'
        )
    html = (
        f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));'
        f'gap:10px;margin-bottom:1.5rem;">'
        f'{cards_html}'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# 4. TARJETA DE MÓDULO
# ─────────────────────────────────────────────────────────────────────────────
_BADGE_COLORS = {
    "blue":   ("#DBEAFE", "#1E40AF"),
    "yellow": ("#FEF9C3", "#92400E"),
    "green":  ("#D1FAE5", "#065F46"),
    "red":    ("#FEE2E2", "#7F1D1D"),
    "gray":   ("#F3F4F6", "#374151"),
    "purple": ("#EDE9FE", "#4C1D95"),
    "orange": ("#FFF7ED", "#9A3412"),
}

def module_card(icono: str, titulo: str, descripcion: str,
                badges: list = None, color_acento: str = "#1B2266"):
    badges = badges or []
    badges_html = ""
    for b in badges:
        bg, fg = _BADGE_COLORS.get(b.get("color", "gray"), _BADGE_COLORS["gray"])
        badges_html += (
            f'<span style="display:inline-block;background:{bg};color:{fg};'
            f'font-size:0.72rem;font-weight:700;padding:3px 10px;'
            f'border-radius:20px;margin-right:5px;margin-top:4px;">'
            f'{b.get("texto", "")}</span>'
        )
    html = (
        f'<div style="background:{PGL_WHITE};border-radius:14px;padding:1.3rem 1.5rem;'
        f'border:1px solid {PGL_BORDER};border-left:5px solid {color_acento};'
        f'box-shadow:0 2px 10px rgba(27,34,102,0.07);margin-bottom:0.75rem;">'
        f'<div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:0.5rem;">'
        f'<span style="font-size:1.7rem;">{icono}</span>'
        f'<div>'
        f'<div style="font-weight:700;font-size:1rem;color:{PGL_NAVY};">{titulo}</div>'
        f'<div style="font-size:0.8rem;color:{PGL_MUTED};line-height:1.3;">{descripcion}</div>'
        f'</div>'
        f'</div>'
        f'<div style="margin-top:0.4rem;">{badges_html}</div>'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# 5. ALERTAS
# ─────────────────────────────────────────────────────────────────────────────
_ALERT_STYLES = {
    "info":    ("rgba(27,34,102,0.07)", PGL_NAVY,  "ℹ️"),
    "warn":    ("#FFF8E1",              "#B45309",  "⚠️"),
    "error":   ("#FEE2E2",              "#991B1B",  "❌"),
    "success": ("#D1FAE5",              "#065F46",  "✅"),
}

def alert(tipo: str, mensaje: str):
    bg, border_color, emoji = _ALERT_STYLES.get(tipo, _ALERT_STYLES["info"])
    html = (
        f'<div style="background:{bg};border-left:4px solid {border_color};'
        f'border-radius:0 8px 8px 0;padding:0.7rem 1rem;font-size:0.88rem;'
        f'color:{border_color};margin:0.5rem 0;line-height:1.4;">'
        f'{emoji} {mensaje}'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# 6. BADGE DE ESTATUS (devuelve HTML)
# ─────────────────────────────────────────────────────────────────────────────
_STATUS_COLORS = {
    "nuevo":      ("#DBEAFE", "#1E40AF"),
    "en_proceso": ("#FEF9C3", "#92400E"),
    "concluido":  ("#D1FAE5", "#065F46"),
    "cancelado":  ("#FEE2E2", "#7F1D1D"),
    "pendiente":  ("#DBEAFE", "#1E40AF"),
    "revision":   ("#FEF9C3", "#92400E"),
    "resuelto":   ("#D1FAE5", "#065F46"),
    "abierta":    ("#EDE9FE", "#4C1D95"),
    "cerrada":    ("#F3F4F6", "#374151"),
}

def status_badge(texto: str, tipo: str) -> str:
    bg, fg = _STATUS_COLORS.get(tipo.lower(), ("#F3F4F6", "#374151"))
    return (
        f'<span style="display:inline-block;background:{bg};color:{fg};'
        f'font-size:0.72rem;font-weight:700;padding:3px 10px;'
        f'border-radius:20px;">{texto}</span>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# 7. DIVISOR VISUAL
# ─────────────────────────────────────────────────────────────────────────────
def divider():
    html = f'<hr style="border:none;border-top:1.5px solid {PGL_BORDER};margin:1.5rem 0;">'
    st.markdown(html, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# 8. BANNER DE BIENVENIDA
# ─────────────────────────────────────────────────────────────────────────────
_ROL_COLORS = {
    "admin":        ("#CC1E1E", "#FFF0F0"),
    "analista de datos": ("#1B2266", "#EEF0FF"),
    "auditor":      ("#0077B6", "#E8F4FC"),
    "user":         ("#2E7D32", "#E8F5E9"),
    "operaciones":  ("#E65100", "#FFF3E0"),
    "gerente":      ("#6D28D9", "#EDE9FE"),
    "contralor":    ("#B45309", "#FEF3C7"),
    "coordinador":  ("#0E7490", "#CFFAFE"),
    "ejecutivo":    ("#1D4ED8", "#DBEAFE"),
}

def welcome_banner(nombre: str, rol: str, area: str = ""):
    c_texto, c_bg = _ROL_COLORS.get(rol.lower(), ("#6B7280", "#F3F4F6"))
    subtitulo = f"Portal de Palos Garza Logistics · {area}" if area else "Portal de Palos Garza Logistics"
    html = (
        f'<div style="background:linear-gradient(135deg,{PGL_NAVY} 0%,{PGL_NAVY_LT} 100%);'
        f'border-radius:16px;padding:2rem 2.5rem;margin-bottom:2rem;'
        f'border-left:5px solid {PGL_RED};position:relative;overflow:hidden;">'
        f'<div style="position:absolute;right:-20px;top:-20px;font-size:8rem;'
        f'opacity:0.06;line-height:1;pointer-events:none;">🚚</div>'
        f'<div style="font-size:0.85rem;color:rgba(255,255,255,0.65);'
        f'font-weight:500;margin-bottom:0.3rem;">Bienvenido de vuelta</div>'
        f'<div style="font-size:1.8rem;font-weight:800;color:white;'
        f'margin-bottom:0.4rem;line-height:1.2;">{nombre}</div>'
        f'<span style="background:{c_bg};color:{c_texto};font-size:0.75rem;font-weight:700;'
        f'padding:3px 12px;border-radius:20px;text-transform:uppercase;'
        f'letter-spacing:0.5px;display:inline-block;">{rol}</span>'
        f'<div style="color:rgba(255,255,255,0.5);font-size:0.8rem;margin-top:0.8rem;">'
        f'{subtitulo}</div>'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)

# ═════════════════════════════════════════════════════════════════════════════
# COMPONENTES FACTURACIÓN
# Estos componentes centralizan el HTML de las páginas de facturación.
# Úsalos así:
#   from ui.components import client_header, kpi_card, gauge_riesgo, credit_bar, facturas_table, payment_info
# ═════════════════════════════════════════════════════════════════════════════
from datetime import date as _date
 
 
# ─────────────────────────────────────────────────────────────────────────────
# 9. ENCABEZADO DE CLIENTE
# ─────────────────────────────────────────────────────────────────────────────
def client_header(cliente: dict, estado: str, color_r: str, logo_b64: str = ""):
    """
    Encabezado con logo, nombre, razón social, condiciones y badge de riesgo.
 
    Uso:
        client_header(cliente, estado, color_r, LOGO_B64)
    """
    logo_html = (
        f'<img src="data:image/png;base64,{logo_b64}" '
        f'style="height:44px;width:auto;object-fit:contain;">'
    ) if logo_b64 else ""
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:1rem;'
        f'padding:0.8rem 0.2rem 0.6rem 0.2rem;'
        f'border-bottom:2px solid #E5E9F0;margin-bottom:1rem;">'
        f'{logo_html}'
        f'<div style="flex:1;">'
        f'<div style="font-size:1.5rem;font-weight:800;color:#1B2266;line-height:1.1;">'
        f'{cliente["nombre"]}</div>'
        f'<div style="font-size:0.8rem;color:#9CA3AF;margin-top:0.1rem;">'
        f'{cliente["razon_social"]} &nbsp;·&nbsp; '
        f'<span style="color:{color_r};font-weight:700;">{cliente["condiciones_pago"]}</span>'
        f' &nbsp;·&nbsp; Emitido: {_date.today().strftime("%d de %B, %Y")}</div>'
        f'</div>'
        f'<span style="background:{color_r}22;color:{color_r};font-size:0.75rem;'
        f'font-weight:700;padding:5px 14px;border-radius:20px;'
        f'border:1.5px solid {color_r};text-transform:uppercase;white-space:nowrap;">'
        f'● {estado}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
 
 
# ─────────────────────────────────────────────────────────────────────────────
# 10. KPI CARD INDIVIDUAL
# ─────────────────────────────────────────────────────────────────────────────
def kpi_card(col, label: str, valor: str, color: str = "#1B2266"):
    """
    Tarjeta KPI con borde superior de color. Se usa dentro de columnas st.columns().
 
    Uso:
        k1, k2 = st.columns(2)
        kpi_card(k1, "Total Balance", "$120,000 USD", "#DC2626")
    """
    col.markdown(
        f'<div style="background:white;border-radius:10px;padding:0.9rem 1rem;'
        f'border:1px solid #E5E9F0;border-top:3px solid {color};">'
        f'<div style="font-size:0.63rem;color:#9CA3AF;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:0.5px;">{label}</div>'
        f'<div style="font-size:1.1rem;font-weight:800;color:{color};margin-top:0.2rem;">'
        f'{valor}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
 
 
# ─────────────────────────────────────────────────────────────────────────────
# 11. VELOCÍMETRO DE RIESGO
# ─────────────────────────────────────────────────────────────────────────────
def gauge_riesgo(estado: str, color: str, angulo: int):
    """
    SVG velocímetro con aguja y badge de estatus.
    angulo: -75=RIESGO | -25=VIGILANCIA | 25=CLIENTE SANO | 75=EXCELENTE
 
    Uso:
        gauge_riesgo(estado, color_r, angulo)
    """
    rot = f"rotate({angulo})"
    st.markdown(
        f'<div style="text-align:center;padding:0.5rem 0;">'
        f'<svg viewBox="0 0 200 130" width="190" style="display:block;margin:auto;">'
        f'<path d="M 25 105 A 80 80 0 0 1 75 30" fill="none" stroke="#DC2626" stroke-width="14" stroke-linecap="round"/>'
        f'<path d="M 75 30 A 80 80 0 0 1 125 30" fill="none" stroke="#D97706" stroke-width="14" stroke-linecap="round"/>'
        f'<path d="M 125 30 A 80 80 0 0 1 175 105" fill="none" stroke="#059669" stroke-width="14" stroke-linecap="round"/>'
        f'<g transform="translate(100,105)">'
        f'<line x1="0" y1="0" x2="0" y2="-60" stroke="#1B2266" stroke-width="3.5" stroke-linecap="round" transform="{rot}"/>'
        f'<circle cx="0" cy="0" r="7" fill="#1B2266"/>'
        f'<circle cx="0" cy="0" r="3.5" fill="white"/>'
        f'</g></svg>'
        f'<div style="margin-top:-0.3rem;">'
        f'<span style="background:{color};color:white;font-size:0.75rem;font-weight:700;'
        f'padding:4px 18px;border-radius:20px;text-transform:uppercase;letter-spacing:0.5px;">'
        f'● {estado}</span>'
        f'</div>'
        f'<div style="display:flex;justify-content:space-between;padding:0 0.5rem;'
        f'font-size:0.65rem;margin-top:0.5rem;">'
        f'<span style="color:#DC2626;font-weight:600;">Riesgo</span>'
        f'<span style="color:#D97706;font-weight:600;">Vigilancia</span>'
        f'<span style="color:#059669;font-weight:600;">Excelente</span>'
        f'</div></div>',
        unsafe_allow_html=True,
    )
 
 
# ─────────────────────────────────────────────────────────────────────────────
# 12. BARRA DE CRÉDITO
# ─────────────────────────────────────────────────────────────────────────────
def credit_bar(usado: float, limite: float, color_perfil: str):
    """
    Barra de porcentaje de crédito utilizado con métricas de usado/disponible.
 
    Uso:
        credit_bar(total, cliente["limite_credito"], color_r)
    """
    pct = min(usado / limite * 100, 100) if limite else 0
    st.markdown(
        f'<div style="padding:0.2rem 0;">'
        f'<div style="display:flex;justify-content:space-between;margin-bottom:0.4rem;">'
        f'<div><div style="font-size:1.5rem;font-weight:800;color:{color_perfil};">{pct:.0f}%</div>'
        f'<div style="font-size:0.65rem;color:#9CA3AF;text-transform:uppercase;">UTILIZADO</div></div>'
        f'<div style="text-align:right;">'
        f'<div style="font-size:1.5rem;font-weight:800;color:#059669;">{100-pct:.0f}%</div>'
        f'<div style="font-size:0.65rem;color:#9CA3AF;text-transform:uppercase;">DISPONIBLE</div></div>'
        f'</div>'
        f'<div style="background:#E5E9F0;border-radius:8px;height:10px;overflow:hidden;">'
        f'<div style="background:{color_perfil};width:{pct}%;height:100%;border-radius:8px;"></div></div>'
        f'<div style="display:flex;justify-content:space-between;margin-top:0.4rem;'
        f'font-size:0.76rem;color:#6B7280;">'
        f'<span>Usado: <b style="color:{color_perfil};">${usado:,.0f}</b></span>'
        f'<span>Límite: <b style="color:#1B2266;">${limite:,.0f}</b></span>'
        f'</div></div>',
        unsafe_allow_html=True,
    )
 
 
# ─────────────────────────────────────────────────────────────────────────────
# 13. TABLA DE FACTURAS
# ─────────────────────────────────────────────────────────────────────────────
def facturas_table(facturas: list, filtro: str = "Todas"):
    """
    Tabla HTML de facturas con colores según vencimiento.
    filtro: "Todas" | "Vencidas" | "Al corriente"
 
    Uso:
        facturas_table(facturas, filtro)
    """
    filas = ""
    for f in facturas:
        dias    = f["dias_vencido"]
        vencida = dias > 0
        if filtro == "Vencidas"     and not vencida: continue
        if filtro == "Al corriente" and vencida:     continue
        cf = "#DC2626" if vencida else "#1B2266"
        cd = "#DC2626" if vencida else "#059669"
        bd = "#FEE2E2" if vencida else "#D1FAE5"
        ci = "#DC2626" if vencida else "#1B2266"
        td = "padding:0.7rem 0.8rem;"
        filas += (
            f'<tr style="border-bottom:1px solid #F1F5F9;">'
            f'<td style="{td}font-weight:700;color:{cf};">{f["folio"]}</td>'
            f'<td style="{td}color:#6B7280;font-size:0.85rem;">{f["fecha_emision"].strftime("%d %b %Y")}</td>'
            f'<td style="{td}color:#6B7280;font-size:0.85rem;">{f["fecha_vencimiento"].strftime("%d %b %Y")}</td>'
            f'<td style="{td}"><span style="background:#EEF0FF;color:#1B2266;font-size:0.78rem;'
            f'font-weight:600;padding:3px 10px;border-radius:6px;font-family:monospace;">'
            f'{f["viaje_referencia"]}</span></td>'
            f'<td style="{td}text-align:center;">'
            f'<span style="background:{bd};color:{cd};font-weight:700;font-size:0.82rem;'
            f'padding:3px 10px;border-radius:20px;min-width:32px;display:inline-block;text-align:center;">'
            f'{dias}</span></td>'
            f'<td style="{td}text-align:right;font-weight:700;font-size:1rem;color:{ci};">'
            f'${f["importe"]:,.0f}</td>'
            f'</tr>'
        )
    if not filas:
        filas = '<tr><td colspan="6" style="text-align:center;padding:2rem;color:#9CA3AF;">Sin facturas con este filtro</td></tr>'
    th = "padding:0.7rem 0.8rem;font-size:0.72rem;color:#9CA3AF;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;"
    st.markdown(
        f'<div style="background:white;border-radius:14px;overflow:hidden;'
        f'border:1px solid #E5E9F0;box-shadow:0 2px 12px rgba(27,34,102,0.07);">'
        f'<table style="width:100%;border-collapse:collapse;">'
        f'<thead><tr style="background:#F8FAFF;border-bottom:2px solid #E5E9F0;">'
        f'<th style="{th}text-align:left;">FACTURA</th>'
        f'<th style="{th}text-align:left;">FECHA</th>'
        f'<th style="{th}text-align:left;">VENCIMIENTO</th>'
        f'<th style="{th}text-align:left;">VIAJE</th>'
        f'<th style="{th}text-align:center;">DÍAS VENCIDO</th>'
        f'<th style="{th}text-align:right;">IMPORTE USD</th>'
        f'</tr></thead>'
        f'<tbody>{filas}</tbody>'
        f'</table></div>',
        unsafe_allow_html=True,
    )
 
 
# ─────────────────────────────────────────────────────────────────────────────
# 14. PANEL DE INFORMACIÓN DE PAGO
# ─────────────────────────────────────────────────────────────────────────────
def payment_info(cliente: dict):
    """
    Panel con banco, cuenta, SWIFT, teléfono y notas de pago del cliente.
 
    Uso:
        payment_info(cliente)
    """
    st.markdown(
        f'<div style="background:white;border-radius:12px;padding:1rem 1.1rem;border:1px solid #E5E9F0;">'
        f'<div style="font-weight:700;font-size:0.9rem;color:#1B2266;margin-bottom:0.15rem;">{cliente["banco"]}</div>'
        f'<div style="font-size:0.75rem;color:#9CA3AF;margin-bottom:0.8rem;">{cliente["banco_empresa"]}</div>'
        f'<div style="display:flex;justify-content:space-between;padding:0.4rem 0;'
        f'border-bottom:1px solid #F1F5F9;font-size:0.8rem;">'
        f'<span style="color:#9CA3AF;">Cuenta</span>'
        f'<span style="font-weight:700;color:#1B2266;font-family:monospace;">{cliente["cuenta_bancaria"]}</span></div>'
        f'<div style="display:flex;justify-content:space-between;padding:0.4rem 0;'
        f'border-bottom:1px solid #F1F5F9;font-size:0.8rem;">'
        f'<span style="color:#9CA3AF;">SWIFT</span>'
        f'<span style="font-weight:700;color:#1B2266;font-family:monospace;">{cliente["swift"]}</span></div>'
        f'<div style="margin-top:0.8rem;padding:0.5rem 0.8rem;background:#EEF0FF;'
        f'border-radius:8px;text-align:center;">'
        f'<span style="color:#CC1E1E;font-weight:700;font-size:0.83rem;">📞 {cliente["telefono"]}</span></div>'
        f'<div style="font-size:0.70rem;color:#9CA3AF;margin-top:0.7rem;line-height:1.4;text-align:center;">'
        f'{cliente.get("notas_pago","")}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────────────────────────────────────
# 12. CONFIGURACIÓN DE ESTATUS PARA SOLICITUDES (tickets y complementarias)
# ─────────────────────────────────────────────────────────────────────────────
# Catálogo centralizado de colores/íconos por estatus.
# Úsalo en cualquier módulo que necesite colorear un estatus:
#   from ui.components import ESTATUS_CFG, status_badge_html, solicitud_card, historial_timeline

ESTATUS_CFG = {
    # Tickets — fases de desarrollo
    "Nuevo":         {"color": "#1D4ED8", "bg": "#EFF6FF", "border": "#BFDBFE", "icono": "🆕"},
    "Capacitación":  {"color": "#7C3AED", "bg": "#F5F3FF", "border": "#DDD6FE", "icono": "📚"},
    "Planteamiento": {"color": "#0891B2", "bg": "#ECFEFF", "border": "#A5F3FC", "icono": "📝"},
    "Desarrollo":    {"color": "#D97706", "bg": "#FFFBEB", "border": "#FDE68A", "icono": "⚙️"},
    "Pruebas":       {"color": "#EA580C", "bg": "#FFF7ED", "border": "#FED7AA", "icono": "🧪"},
    "Entrega":       {"color": "#059669", "bg": "#ECFDF5", "border": "#A7F3D0", "icono": "📦"},
    "Concluido":     {"color": "#16A34A", "bg": "#F0FDF4", "border": "#BBF7D0", "icono": "✅"},
    "Cancelado":     {"color": "#DC2626", "bg": "#FEF2F2", "border": "#FECACA", "icono": "🚫"},
    # Tickets — estatus legacy
    "En Proceso":    {"color": "#D97706", "bg": "#FFFBEB", "border": "#FDE68A", "icono": "⏳"},
    # Complementarias
    "Pendiente":     {"color": "#1D4ED8", "bg": "#EFF6FF", "border": "#BFDBFE", "icono": "🕐"},
    "En revisión":   {"color": "#D97706", "bg": "#FFFBEB", "border": "#FDE68A", "icono": "🔍"},
    "Resuelto":      {"color": "#16A34A", "bg": "#F0FDF4", "border": "#BBF7D0", "icono": "✅"},
    # Viáticos
    "Pendiente Autorización": {"color": "#D97706", "bg": "#FFFBEB", "border": "#FDE68A", "icono": "⏳"},
    "Autorizado":    {"color": "#059669", "bg": "#ECFDF5", "border": "#A7F3D0", "icono": "✅"},
    "Rechazado":     {"color": "#DC2626", "bg": "#FEF2F2", "border": "#FECACA", "icono": "🚫"},
    "Cerrado":       {"color": "#6B7280", "bg": "#F9FAFB", "border": "#E5E7EB", "icono": "🔒"},
}
_ESTATUS_DEFAULT = {"color": "#6B7280", "bg": "#F9FAFB", "border": "#E5E7EB", "icono": "📋"}


def status_badge_html(estatus: str) -> str:
    """
    Devuelve HTML de un badge de estatus con color y ícono.
    No renderiza — solo retorna el string HTML para embeber en markdown mayor.

    Uso:
        badge = status_badge_html("Nuevo")
        st.markdown(f"Estado: {badge}", unsafe_allow_html=True)
    """
    cfg = ESTATUS_CFG.get(estatus, _ESTATUS_DEFAULT)
    return (
        f'<span style="background:{cfg["color"]}22;color:{cfg["color"]};'
        f'border:1.5px solid {cfg["color"]};border-radius:20px;'
        f'padding:3px 13px;font-size:0.73rem;font-weight:700;white-space:nowrap;">'
        f'{cfg["icono"]} {estatus}</span>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# 13. TIMELINE DE HISTORIAL
# ─────────────────────────────────────────────────────────────────────────────
_ACCION_ICONO = {
    "create":  "🆕",
    "update":  "✏️",
    "comment": "💬",
    "fase":    "🔄",
    "assign":  "👤",
    "resolve": "✅",
    "cancel":  "🚫",
}


def historial_timeline(historial: list):
    """
    Renderiza un timeline visual del historial de una solicitud.
    Cada entrada debe ser un dict con: at, by, action, details.

    Uso:
        historial_timeline(ticket.get("historial") or [])
    """
    if not historial:
        st.caption("Sin historial registrado.")
        return

    filas_html = ""
    for entry in reversed(historial):
        at_raw = str(entry.get("at", ""))[:16].replace("T", " ")
        by_    = entry.get("by", "Sistema")
        action = entry.get("action", "")
        detail = entry.get("details", "")
        icono  = _ACCION_ICONO.get(action, "📌")

        filas_html += (
            f'<div style="display:flex;gap:0.6rem;padding:0.45rem 0;'
            f'border-bottom:1px solid #E5E7EB;">'
            f'<span style="font-size:1rem;flex-shrink:0;padding-top:1px;">{icono}</span>'
            f'<div style="flex:1;font-size:0.82rem;">'
            f'<div><b style="color:#1B2266;">{by_}</b> '
            f'<span style="color:#9CA3AF;font-size:0.75rem;">{at_raw}</span></div>'
            f'<div style="color:#374151;margin-top:1px;">{detail}</div>'
            f'</div>'
            f'</div>'
        )

    st.markdown(
        f'<div style="max-height:240px;overflow-y:auto;padding:0.5rem 0.75rem;'
        f'background:#F9FAFB;border:1px solid #E5E7EB;border-radius:8px;">'
        f'{filas_html}</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 14. CARD DE SOLICITUD (tickets y complementarias)
# ─────────────────────────────────────────────────────────────────────────────
def solicitud_card(
    *,
    id_label: str,
    titulo: str,
    fecha: str,
    estatus: str,
    meta: list[tuple[str, str]] | None = None,
    on_edit_key: str | None = None,
):
    """
    Card visual para una solicitud (ticket, complementaria, etc.).
    Homologada entre módulos — sin HTML en los módulos que la usan.

    Parámetros:
        id_label    : Texto del ID/folio (ej. "#10" o "Folio 0042")
        titulo      : Título o descripción corta de la solicitud
        fecha       : Fecha como string (ej. "2026-05-20")
        estatus     : Clave del estatus (debe existir en ESTATUS_CFG)
        meta        : Lista de tuplas (icono_texto, valor) para mostrar debajo del título
                      Ej. [("🏢 Empresa", "Picus"), ("📂 Categoría", "Tickets")]
        on_edit_key : Si se pasa, muestra un botón "Ver / Editar" que devuelve True
                      cuando es clickeado. Usar como: if solicitud_card(...): open_modal()

    Retorna True si se clickeó el botón de editar, False en caso contrario.

    Uso básico (solo lectura):
        solicitud_card(id_label="#10", titulo="Reporte", fecha="2026-05-20",
                       estatus="Nuevo", meta=[("🏢", "Picus")])

    Uso con botón de edición:
        clicked = solicitud_card(..., on_edit_key="edit_10")
        if clicked:
            st.session_state["modal_ticket_id"] = 10
            st.rerun()
    """
    cfg = ESTATUS_CFG.get(estatus, _ESTATUS_DEFAULT)
    badge = status_badge_html(estatus)

    # Meta info (ícono + valor)
    meta = meta or []
    meta_html = ""
    for item in meta:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            meta_html += (
                f'<span style="color:#6B7280;font-size:0.79rem;">'
                f'{item[0]}&nbsp;{item[1]}</span> &nbsp;·&nbsp; '
            )
    meta_html = meta_html.rstrip(" &nbsp;·&nbsp; ")

    html = (
        f'<div style="'
        f'background:{cfg["bg"]};'
        f'border:1px solid {cfg["border"]};'
        f'border-left:5px solid {cfg["color"]};'
        f'border-radius:10px;'
        f'padding:0.9rem 1.1rem 0.75rem 1.1rem;'
        f'margin-bottom:0.65rem;'
        f'">'
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:0.4rem;">'
        f'  <div style="flex:1;min-width:0;">'
        f'    <div style="font-size:0.7rem;color:#9CA3AF;font-weight:600;'
        f'text-transform:uppercase;letter-spacing:0.4px;margin-bottom:2px;">'
        f'      {id_label} · {fecha}'
        f'    </div>'
        f'    <div style="font-size:1rem;font-weight:700;color:#1B2266;'
        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'
        f'      {titulo}'
        f'    </div>'
        f'    <div style="margin-top:0.3rem;line-height:1.6;">{meta_html}</div>'
        f'  </div>'
        f'  <div style="flex-shrink:0;margin-top:2px;">{badge}</div>'
        f'</div>'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)

    # Botón de editar (si se pasó una key)
    if on_edit_key:
        return st.button("✏️ Ver / Editar", key=on_edit_key, use_container_width=False)
    return False
