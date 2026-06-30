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
#   banner_tarifa_sugerida(tarifa_base, ingreso_total, moneda_base, valor_secundario)    
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
# 15. CONFIGURACIÓN DE ESTATUS PARA SOLICITUDES (tickets y complementarias)
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
# 16. TIMELINE DE HISTORIAL
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
# 17. CARD DE SOLICITUD (tickets y complementarias)
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
        f'background:#FFFFFF;'
        f'border:1px solid #E5E7EB;'
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

# ─────────────────────────────────────────────────────────────────────────────
# 18. TABLA DE SOLICITUDES CON ESTATUS COLOREADO
# ─────────────────────────────────────────────────────────────────────────────
_TABLA_COL_WIDTHS = {
    "ID": "50px", "Fecha creación": "100px", "Última actualización": "100px",
    "Solicitante": "140px", "Correo": "160px", "Empresa": "100px",
    "Título": "160px", "Categoría": "120px", "Departamento": "110px",
    "Prioridad": "80px", "Estatus": "120px", "Asignado a": "100px",
    "Descripción": "200px",
    # Complementarias
    "Folio": "60px", "Tipo": "130px", "Tráfico": "110px", "Auditor": "110px",
    "Fecha resolución": "110px", "Sucursal": "100px", "Plataforma": "100px",
}
_PRIO_COLORS = {"Alta": "#D97706", "Urgente": "#DC2626", "Normal": "#6B7280"}

def solicitudes_table(df):
    """
    Renderiza un DataFrame como tabla HTML con estatus coloreados.
    Usa ESTATUS_CFG para los badges y soporta columna Prioridad con color.
    Úsalo en gestión de tickets y complementarias en lugar de st.dataframe.

    Uso:
        from ui.components import solicitudes_table
        solicitudes_table(df)
    """
    import pandas as pd

    th = (
        "background:#1B2266;color:white;font-size:0.72rem;font-weight:700;"
        "padding:8px 10px;text-align:left;white-space:nowrap;"
        "text-transform:uppercase;letter-spacing:0.4px;"
    )
    td = (
        "padding:7px 10px;font-size:0.8rem;color:#374151;"
        "border-bottom:1px solid #E5E7EB;vertical-align:middle;"
    )

    headers = "".join(
        f'<th style="{th}min-width:{_TABLA_COL_WIDTHS.get(c, "90px")};">{c}</th>'
        for c in df.columns
    )

    rows_html = ""
    for i, row in df.iterrows():
        bg = "#FAFAFA" if i % 2 == 0 else "#FFFFFF"
        cells = ""
        for col in df.columns:
            val = str(row[col]) if row[col] is not None else ""
            if col == "Estatus":
                cfg   = ESTATUS_CFG.get(val, _ESTATUS_DEFAULT)
                color = cfg["color"]
                est_bg = cfg["bg"]
                cell_val = (
                    f'<span style="background:{est_bg};color:{color};'
                    f'border:1px solid {color};border-radius:12px;'
                    f'padding:2px 10px;font-size:0.72rem;font-weight:700;'
                    f'white-space:nowrap;">{cfg["icono"]} {val}</span>'
                )
            elif col == "Prioridad":
                c = _PRIO_COLORS.get(val, "#6B7280")
                cell_val = f'<span style="color:{c};font-weight:600;">{val}</span>'
            else:
                cell_val = val
            cells += f'<td style="{td}background:{bg};">{cell_val}</td>'
        rows_html += f"<tr>{cells}</tr>"

    html = (
        f'<div style="overflow-x:auto;border-radius:10px;'
        f'border:1px solid #E5E7EB;margin-bottom:0.75rem;">'
        f'<table style="width:100%;border-collapse:collapse;">'
        f'<thead><tr>{headers}</tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        f'</table></div>'
    )
    st.markdown(html, unsafe_allow_html=True)

# ═════════════════════════════════════════════════════════════════════════════
# COMPONENTES DE COTIZADORES
# Usados por las 4 empresas: Igloo, Picus, Lincoln, Set Logis.
# Regla: NINGUNA función aquí contiene números de empresa ni defaults hardcodeados.
# Todos los umbrales y colores viajan dentro del dict `r` producido por
# calcular_ruta_*() en el helpers/_shared de cada empresa.
# ═════════════════════════════════════════════════════════════════════════════
 
# ─────────────────────────────────────────────────────────────────────────────
# 19. SEMÁFOROS DE RUTA
# ─────────────────────────────────────────────────────────────────────────────
def semaforos_ruta(r: dict) -> None:
    """
    Muestra 4 indicadores semáforo (verde/rojo) para los KPIs de una ruta.
 
    Los umbrales NO están hardcodeados aquí — vienen dentro del dict `r`
    que produce calcular_ruta_*() en el helpers/_shared de cada empresa.
 
    Claves requeridas en `r`:
        Pct_Costo_Directo    (float %)
        Pct_Ut_Bruta         (float %)
        Pct_Costo_Indirecto  (float %)
        Pct_Ut_Neta          (float %)
        umbral_cd            (float) → max % costo directo aceptable
        umbral_ub            (float) → min % utilidad bruta aceptable
        umbral_ci            (float) → max % costo indirecto aceptable
        umbral_un            (float) → min % utilidad neta aceptable
 
    Ejemplo en helpers/_shared de cada empresa:
        UMBRALES = dict(umbral_cd=50.0, umbral_ub=50.0, umbral_ci=35.0, umbral_un=15.0)
        # Se incluyen en el dict que devuelve calcular_utilidades() / calcular_ruta_*()
 
    Llamada desde cualquier módulo:
        from ui.components import semaforos_ruta
        semaforos_ruta(r)   # r ya trae los umbrales correctos de su empresa
    """
    pct_dir = r.get("Pct_Costo_Directo",   0.0)
    pct_utb = r.get("Pct_Ut_Bruta",        0.0)
    pct_ind = r.get("Pct_Costo_Indirecto", 0.0)
    pct_utn = r.get("Pct_Ut_Neta",         0.0)
 
    max_cd = r.get("umbral_cd", 85.0)   # fallback neutral — solo si helpers no lo incluyó
    min_ub = r.get("umbral_ub", 15.0)
    max_ci = r.get("umbral_ci",  9.0)
    min_un = r.get("umbral_un",  6.0)
 
    s1, s2, s3, s4 = st.columns(4)
 
    if pct_dir <= max_cd:
        s1.success(f"C. Directos: {pct_dir:.1f}% (≤{max_cd:.0f}%)")
    else:
        s1.error(f"C. Directos: {pct_dir:.1f}% — EXCEDE {max_cd:.0f}%")
 
    if pct_utb >= min_ub:
        s2.success(f"Ut. Bruta: {pct_utb:.1f}% (≥{min_ub:.0f}%)")
    else:
        s2.error(f"Ut. Bruta: {pct_utb:.1f}% — DEBAJO {min_ub:.0f}%")
 
    if pct_ind <= max_ci:
        s3.success(f"C. Indirecto: {pct_ind:.1f}% (≤{max_ci:.0f}%)")
    else:
        s3.error(f"C. Indirecto: {pct_ind:.1f}% — EXCEDE {max_ci:.0f}%")
 
    if pct_utn >= min_un:
        s4.success(f"Ut. Neta: {pct_utn:.1f}% (≥{min_un:.0f}%)")
    else:
        s4.error(f"Ut. Neta: {pct_utn:.1f}% — DEBAJO {min_un:.0f}%")
 
 
# ─────────────────────────────────────────────────────────────────────────────
# 20. MOSTRAR RESULTADOS DE RUTA (canónica — todas las empresas)
# ─────────────────────────────────────────────────────────────────────────────
def mostrar_resultados_ruta(r: dict, titulo: str = "Resultado del Cálculo") -> None:
    """
    Muestra las 5 cards KPI + semáforos de una ruta cotizada.
    Función canónica — igual para las 4 empresas.
 
    El dict `r` debe venir de calcular_ruta_*() / calcular_utilidades() del
    helpers/_shared de cada empresa e incluir OBLIGATORIAMENTE:
 
        # Valores monetarios
        ingreso_total        (float)
        costo_directo        (float)
        utilidad_bruta       (float)
        costos_indirectos    (float)
        utilidad_neta        (float)
 
        # Porcentajes
        Pct_Costo_Directo    (float %)
        Pct_Ut_Bruta         (float %)
        Pct_Costo_Indirecto  (float %)
        Pct_Ut_Neta          (float %)
 
        # Colores calculados con umbrales de la empresa
        Color_Directo        (str hex)
        Color_Indirecto      (str hex)
        Color_Ut_Neta        (str hex)
 
        # Umbrales de la empresa (para semaforos_ruta)
        umbral_cd            (float)
        umbral_ub            (float)
        umbral_ci            (float)
        umbral_un            (float)
 
    Uso en cualquier módulo de cualquier empresa:
        from ui.components import mostrar_resultados_ruta
        r = calcular_ruta_igloo(...)   # o lincoln, picus, set_logis
        mostrar_resultados_ruta(r)
    """
    section_header("📊", titulo)
 
    moneda = r.get("moneda_display", "MXP")   # helpers puede incluir "USD" o "MXP"
 
    kpi_row([
        {
            "icono": "💰",
            "label": "Ingreso Total",
            "valor": f"${r.get('ingreso_total', 0):,.2f}",
            "sub":   moneda,
            "color": PGL_NAVY,
        },
        {
            "icono": "📉",
            "label": "Costo Directo",
            "valor": f"${r.get('costo_directo', 0):,.2f}",
            "sub":   f"{r.get('Pct_Costo_Directo', 0):.1f}%",
            "color": r.get("Color_Directo", "#DC2626"),
        },
        {
            "icono": "📈",
            "label": "Utilidad Bruta",
            "valor": f"${r.get('utilidad_bruta', 0):,.2f}",
            "sub":   f"{r.get('Pct_Ut_Bruta', 0):.1f}%",
            "color": "#059669" if r.get("utilidad_bruta", 0) >= 0 else "#DC2626",
        },
        {
            "icono": "📊",
            "label": "Costos Indirectos",
            "valor": f"${r.get('costos_indirectos', 0):,.2f}",
            "sub":   f"{r.get('Pct_Costo_Indirecto', 0):.1f}%",
            "color": r.get("Color_Indirecto", "#D97706"),
        },
        {
            "icono": "✅",
            "label": "Utilidad Neta",
            "valor": f"${r.get('utilidad_neta', 0):,.2f}",
            "sub":   f"{r.get('Pct_Ut_Neta', 0):.1f}%",
            "color": r.get("Color_Ut_Neta", "#DC2626"),
        },
    ])
 
    divider()
    semaforos_ruta(r)
 
 
# ─────────────────────────────────────────────────────────────────────────────
# 21. DESGLOSE DE RUTA POR TRAMO
# ─────────────────────────────────────────────────────────────────────────────
def desglose_ruta(
    r: dict,
    *,
    filas_costo_americana: list[tuple[str, float]] | None = None,
    modalidad: str = "Flat",
    cxm_flete: float = 0.0,
    cxm_fuel:  float = 0.0,
    moneda_mx:  str   = "USD",
    tc:         float = 1.0,
) -> None:
    """
    Expander con tabs de desglose ingreso/costo por tramo.
    Solo muestra los tramos que tengan datos (importe > 0).
    Funciona para los 4 cotizadores: Igloo, Picus, Lincoln, Set Logis.
 
    Parámetros:
        r                     : dict resultado de calcular_ruta_*()
        filas_costo_americana : lista de (label, valor) para costos USA.
                                OBLIGATORIO para americanas (Lincoln/Set Logis).
                                Igloo/Picus no tienen tramo americano — no lo pasan.
        modalidad             : "Desglosada" | "Flat" — afecta display ingreso USA
        cxm_flete / cxm_fuel  : solo se usan si modalidad == "Desglosada"
        moneda_mx             : "MXP" o "USD" — moneda en que están los valores MX del dict
        tc                    : tipo de cambio MXP→USD (solo se usa si moneda_mx == "MXP")
 
    Empresas americanas (Lincoln y Set Logis):
        desglose_ruta(
            r,
            filas_costo_americana=[
                ("Sueldo Cargado (1000 SM × $0.48)", r["sueldo_base"]),
                ("Diesel", r["diesel_usa"]),
                ("ISR/IMSS", r["isr_imss"]),
            ],
            modalidad=modalidad,
            cxm_flete=cxm_flete,
            cxm_fuel=cxm_fuel,
        )
 
    Empresas mexicanas (Igloo y Picus):
        desglose_ruta(r, moneda_mx="MXP", tc=tc)
        # El tramo americano no aplica — no se muestra si filas_costo_americana es None
        # y los valores de Flete_USA / Fuel son 0
    """
    def _s(k):
        v = r.get(k, 0.0)
        try:
            return float(v) if v is not None else 0.0
        except Exception:
            return 0.0
 
    def _mx(valor_raw: float) -> float:
        """Convierte valor a USD si viene en MXP."""
        if moneda_mx == "MXP" and tc and tc > 0:
            return valor_raw / tc
        return valor_raw
 
    ing_ame   = _s("Flete_USA") + _s("Fuel") + _s("Extras_Ingreso")
    ing_cruce = _s("Ingreso_Cruce")
    ing_mx    = _mx(_s("Ingreso_MX"))
    cos_cruce = _s("Costo_Cruce")
    cos_mx    = _mx(_s("Costo_MX"))
 
    # Costos americanos: SIEMPRE los pasa la empresa — no hay default hardcodeado
    if filas_costo_americana is None:
        filas_costo_americana = []
 
    cos_ame = sum(v for _, v in filas_costo_americana)
    ut_ame  = ing_ame   - cos_ame
    ut_cruc = ing_cruce - cos_cruce
    ut_mx   = ing_mx    - cos_mx
 
    # Construir tabs solo para tramos con datos
    tab_labels = []
    if ing_ame > 0 or cos_ame > 0:
        tab_labels.append("🇺🇸 Ruta Americana")
    if ing_cruce > 0 or cos_cruce > 0:
        tab_labels.append("🛂 Cruce")
    if ing_mx > 0 or cos_mx > 0:
        tab_labels.append("🇲🇽 Ruta MX")
 
    if not tab_labels:
        return
 
    with st.expander("🔍 Ver Desglose por Tramo", expanded=False):
        if len(tab_labels) == 1:
            tabs = [st.container()]
        else:
            tabs = st.tabs(tab_labels)
 
        idx = 0
 
        # ── Tramo Americano ───────────────────────────────────────────────────
        if "🇺🇸 Ruta Americana" in tab_labels:
            with tabs[idx]:
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**Ingresos**")
                    if modalidad == "Desglosada" and cxm_flete > 0:
                        ml = _s("Miles_Load")
                        st.caption(f"Flete ({ml:.0f} mi × ${cxm_flete:.4f}): **${_s('Flete_USA'):,.2f}**")
                        if cxm_fuel > 0:
                            st.caption(f"Fuel  ({ml:.0f} mi × ${cxm_fuel:.4f}): **${_s('Fuel'):,.2f}**")
                    else:
                        if _s("Flete_USA") > 0:
                            st.caption(f"Flete USA: **${_s('Flete_USA'):,.2f}**")
                        if _s("Fuel") > 0:
                            st.caption(f"Fuel: **${_s('Fuel'):,.2f}**")
                    if _s("Extras_Ingreso") > 0:
                        st.caption(f"Extras cobrados: **${_s('Extras_Ingreso'):,.2f}**")
                    st.markdown(f"**Total: ${ing_ame:,.2f}**")
                with c2:
                    st.markdown("**Costos**")
                    for label, valor in filas_costo_americana:
                        st.caption(f"{label}: **${valor:,.2f}**")
                    st.markdown(f"**Total: ${cos_ame:,.2f}**")
                color_ut = "#059669" if ut_ame >= 0 else "#DC2626"
                st.markdown(
                    f'<div style="margin-top:0.5rem;padding:0.5rem 0.75rem;'
                    f'background:#F9FAFB;border-radius:8px;border-left:3px solid {color_ut};">'
                    f'Utilidad Americana: <b style="color:{color_ut};">${ut_ame:,.2f}</b>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            idx += 1
 
        # ── Tramo Cruce ───────────────────────────────────────────────────────
        if "🛂 Cruce" in tab_labels:
            with tabs[idx]:
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**Ingresos**")
                    tipo_cruce = str(r.get("Tipo_Cruce", ""))
                    st.caption(f"Ingreso Cruce{' (' + tipo_cruce + ')' if tipo_cruce else ''}: **${ing_cruce:,.2f}**")
                    st.markdown(f"**Total: ${ing_cruce:,.2f}**")
                with c2:
                    st.markdown("**Costos**")
                    if cos_cruce > 0:
                        st.caption(f"Costo Cruce: **${cos_cruce:,.2f}**")
                    else:
                        st.caption("Cruce propio — sin costo directo")
                    st.markdown(f"**Total: ${cos_cruce:,.2f}**")
                color_ut = "#059669" if ut_cruc >= 0 else "#DC2626"
                st.markdown(
                    f'<div style="margin-top:0.5rem;padding:0.5rem 0.75rem;'
                    f'background:#F9FAFB;border-radius:8px;border-left:3px solid {color_ut};">'
                    f'Utilidad Cruce: <b style="color:{color_ut};">${ut_cruc:,.2f}</b>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            idx += 1
 
        # ── Tramo MX ──────────────────────────────────────────────────────────
        if "🇲🇽 Ruta MX" in tab_labels:
            with tabs[idx]:
                sufijo = " (conv. a USD)" if moneda_mx == "MXP" else ""
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown(f"**Ingresos{sufijo}**")
                    st.caption(f"Ingreso MX: **${ing_mx:,.2f}**")
                    st.markdown(f"**Total: ${ing_mx:,.2f}**")
                with c2:
                    st.markdown(f"**Costos{sufijo}**")
                    if cos_mx > 0:
                        st.caption(f"Costo MX: **${cos_mx:,.2f}**")
                    st.markdown(f"**Total: ${cos_mx:,.2f}**")
                color_ut = "#059669" if ut_mx >= 0 else "#DC2626"
                st.markdown(
                    f'<div style="margin-top:0.5rem;padding:0.5rem 0.75rem;'
                    f'background:#F9FAFB;border-radius:8px;border-left:3px solid {color_ut};">'
                    f'Utilidad MX: <b style="color:{color_ut};">${ut_mx:,.2f}</b>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
 
 
# ─────────────────────────────────────────────────────────────────────────────
# 22. RUTA VISUAL DE NODOS (simulador — todas las empresas)
# ─────────────────────────────────────────────────────────────────────────────
def ruta_visual_nodos(pasos: list[dict]) -> None:
    """
    Renderiza una secuencia visual de ciudades con flechas para el simulador.
    Funciona para las 4 empresas. El helpers/_shared de cada empresa construye
    la lista de pasos y llama a esta función.
 
    Cada paso en la lista es un dict:
        {
            "icono":    str,   # emoji del nodo (🇲🇽 🇺🇸 🛂 ⬜ 🔁 🏁 📍)
            "ciudad":   str,   # nombre de la ciudad/estado
            "etiqueta": str,   # texto secundario (ej. "Origen USA (NB)")
        }
        O el string especial "→" para insertar una flecha entre nodos.
 
    Ejemplo de uso en simulador.py de cualquier empresa:
        from ui.components import ruta_visual_nodos, section_header
        section_header("🗺️", "Secuencia del Road Trip")
        pasos = [
            {"icono": "🇲🇽", "ciudad": "MONTERREY, NL", "etiqueta": "Origen MX"},
            "→",
            {"icono": "🛂", "ciudad": "LAREDO, TX",    "etiqueta": "Cruce"},
            "→",
            {"icono": "🇺🇸", "ciudad": "DALLAS, TX",   "etiqueta": "Destino USA"},
        ]
        ruta_visual_nodos(pasos)
 
    Para Igloo y Picus (solo MX + cruce):
        pasos = [
            {"icono": "🇲🇽", "ciudad": origen,  "etiqueta": "Origen"},
            "→",
            {"icono": "📍",  "ciudad": destino, "etiqueta": "Destino"},
        ]
        ruta_visual_nodos(pasos)
    """
    nodos_html = ""
    flecha_html = '<div style="font-size:1.3rem;padding:0 4px;align-self:center;color:#6B7280;">→</div>'
 
    for paso in pasos:
        if paso == "→":
            nodos_html += flecha_html
        else:
            icono    = paso.get("icono", "📍")
            ciudad   = paso.get("ciudad", "")
            etiqueta = paso.get("etiqueta", "")
            nodos_html += (
                f'<div style="text-align:center;min-width:90px;">'
                f'<div style="font-size:1.4rem;">{icono}</div>'
                f'<div style="font-weight:700;font-size:0.78rem;color:{PGL_NAVY};">{ciudad}</div>'
                f'<div style="font-size:0.68rem;color:#6B7280;">{etiqueta}</div>'
                f'</div>'
            )
 
    st.markdown(
        f'<div style="display:flex;flex-wrap:wrap;align-items:center;'
        f'gap:4px;padding:1rem;background:#F9FAFB;'
        f'border-radius:10px;border:1px solid #E5E7EB;margin-bottom:1rem;">'
        f'{nodos_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 23. BANNER DE TARIFA SUGERIDA (cotizadores — todas las empresas)
# ─────────────────────────────────────────────────────────────────────────────
def banner_tarifa_sugerida(
    costo_directo:    float,
    ingreso_total:    float,
    umbral_cd:        float,
    moneda_base:      str   = "MXP",
    valor_secundario: float = 0.0,
    modalidad:        str   = "",
    miles_load:       float = 0.0,
    fuel_capturado:   float = 0.0,
) -> None:
    """
    Muestra una banda con la tarifa sugerida basada en el umbral de costo directo.
 
    Parámetros — el helpers/_shared de cada empresa los calcula y pasa:
        costo_directo    : costo directo total de la ruta
        ingreso_total    : ingreso actual capturado (0 si aún no se calculó)
        umbral_cd        : % máximo de costo directo aceptable (viene del dict r)
                           Igloo/Picus: 50.0  |  Lincoln/Set Logis: el suyo
        moneda_base      : "MXP" → bloque mexicano | "USD" → bloque americano
        valor_secundario : equivalente en la otra moneda (0 si no aplica)
                           MXP → tarifa_sugerida / tc   |  USD → tarifa_sugerida * tc
        modalidad        : solo americanas — "Flat" | "Desglosada" | "" (D2D o sin millas)
        miles_load       : solo americanas — millas de carga para calcular $/milla
        fuel_capturado    : solo americanas, modalidad Desglosada — monto de fuel ya
                           cobrado al cliente (ingreso_fuel_usa). Se resta del total
                           sugerido antes de dividir entre millas, para que el $/mi
                           sugerido sea solo de flete (comparable contra lo capturado).
                           
    ── BLOQUE MEXICANO (moneda_base == "MXP") ───────────────────────────────
        No se toca. Lógica original de Igloo/Picus:
        tarifa_sugerida = costo_directo × 2  (umbral 50% fijo)
 
    ── BLOQUE AMERICANO (moneda_base == "USD") ──────────────────────────────
        tarifa_sugerida = costo_directo / (umbral_cd / 100)
 
        Si modalidad == "Flat" o miles_load == 0:
            → muestra monto flat sugerido en USD
        Si modalidad == "Desglosada" y miles_load > 0:
            → muestra $/milla sugerida + advertencia de que incluye fuel
        Si modalidad == "" (D2D o rutas combinadas):
            → muestra monto flat sugerido + nota referencial
        Siempre muestra diferencia vs ingreso actual y advertencia general.
 
    Comportamiento visual:
        - Amarillo : ingreso_total == 0 → solo muestra la tarifa sugerida
        - Azul     : hay ingreso        → compara ingreso vs tarifa sugerida
    """
    if costo_directo <= 0:
        return
 
    # ── BLOQUE MEXICANO ───────────────────────────────────────────────────────
    if moneda_base == "MXP":
        pct_frac_mx = (umbral_cd / 100.0) if umbral_cd else 0.50
        tarifa_base = costo_directo / pct_frac_mx if pct_frac_mx else 0.0
        moneda_alt  = "USD"
        sec_html    = (
            f"&nbsp;/&nbsp;{moneda_alt} ${valor_secundario:,.2f}"
            if valor_secundario > 0 else ""
        )
        if ingreso_total == 0:
            st.markdown(
                f'<div style="background:#fffbeb;border-left:4px solid #f59e0b;'
                f'padding:10px 16px;border-radius:8px;margin-bottom:14px;'
                f'font-size:0.9rem;color:#92400e;">'
                f'💡 <b>Tarifa sugerida ({umbral_cd:.0f}% C.D.):</b>&nbsp;'
                f'MXP ${tarifa_base:,.2f}{sec_html}<br>'
                f'<span style="font-size:0.78rem;opacity:0.8;">'
                f'El costo directo debe representar el {umbral_cd:.0f}% del ingreso total.'
                f'</span></div>',
                unsafe_allow_html=True,
            )
        else:
            diff     = ingreso_total - tarifa_base
            diff_pct = (diff / tarifa_base * 100) if tarifa_base else 0
            signo    = "+" if diff >= 0 else ""
            color    = "#059669" if diff >= 0 else "#DC2626"
            icono    = "✅" if diff >= 0 else "⚠️"
            st.markdown(
                f'<div style="background:#eff6ff;border-left:4px solid #3b82f6;'
                f'padding:10px 16px;border-radius:8px;margin-bottom:14px;'
                f'font-size:0.9rem;color:#1e3a5f;">'
                f'📊 <b>Tarifa sugerida ({umbral_cd:.0f}% C.D.):</b>&nbsp;'
                f'MXP ${tarifa_base:,.2f}{sec_html}'
                f'&nbsp;&nbsp;{icono}&nbsp;'
                f'<span style="color:{color};font-weight:600;">'
                f'Tu tarifa está {signo}{diff_pct:.1f}%'
                f'&nbsp;(MXP {signo}${diff:,.2f}) vs la sugerida'
                f'</span></div>',
                unsafe_allow_html=True,
            )
        return
 
    # ── BLOQUE AMERICANO — nuevo ──────────────────────────────────────────────
    # tarifa_sugerida = costo_directo / (umbral_cd / 100)
    # Ejemplo: costo $500, umbral 85% → sugerida = 500 / 0.85 = $588.24
    pct_frac     = (umbral_cd / 100.0) if umbral_cd else 0.85
    tarifa_usd   = costo_directo / pct_frac if pct_frac else 0.0
 
    # $/mi sugerido SOLO de flete: se resta el fuel ya capturado antes de dividir
    tarifa_flete_usd = max(tarifa_usd - fuel_capturado, 0.0)
    xmilla            = (tarifa_flete_usd / miles_load) if miles_load > 0 else 0.0
 
    # Texto secundario — equivalente en MXP si se pasó el TC
    sec_html = (
        f"&nbsp;/&nbsp;MXP ${valor_secundario:,.2f}"
        if valor_secundario > 0 else ""
    )
 
    # Línea de modalidad: qué mostrar como tarifa de referencia
    if modalidad == "Desglosada" and xmilla > 0:
        tarifa_ref_html = (
            f'<b>USD ${tarifa_usd:,.2f}</b> flat'
            f'&nbsp;·&nbsp;'
            f'<b>${xmilla:,.4f}/mi</b> de flete'
            f'&nbsp;<span style="font-size:0.78rem;opacity:0.8;">'
            f'(fuel ${fuel_capturado:,.2f} ya descontado)</span>'
        )
        nota_modal = (
            f'<br><span style="font-size:0.76rem;opacity:0.75;">'
            f'⚠️ El $/mi sugerido es solo de flete — el fuel se cobra aparte '
            f'según lo ya capturado.</span>'
        )
    elif modalidad == "Flat" or miles_load == 0:
        tarifa_ref_html = f'<b>USD ${tarifa_usd:,.2f}</b> flat'
        nota_modal      = ""
    else:
        # D2D u otras rutas combinadas — solo flat referencial
        tarifa_ref_html = f'<b>USD ${tarifa_usd:,.2f}</b> flat referencial'
        nota_modal      = (
            f'<br><span style="font-size:0.76rem;opacity:0.75;">'
            f'ℹ️ Tarifa referencial general — no incluye ajuste por vacíos o cruces.</span>'
        )
 
    advertencia = (
        f'<br><span style="font-size:0.76rem;opacity:0.75;">'
        f'⚠️ Referencia basada en costo directo al {umbral_cd:.0f}%. '
        f'No incluye ajuste por vacíos o cruces independientes.</span>'
    )
 
    if ingreso_total == 0:
        st.markdown(
            f'<div style="background:#fffbeb;border-left:4px solid #f59e0b;'
            f'padding:10px 16px;border-radius:8px;margin-bottom:14px;'
            f'font-size:0.9rem;color:#92400e;">'
            f'💡 <b>Tarifa sugerida ({umbral_cd:.0f}% C.D.):</b>&nbsp;'
            f'{tarifa_ref_html}{sec_html}'
            f'{nota_modal}{advertencia}'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        diff     = ingreso_total - tarifa_usd
        diff_pct = (diff / tarifa_usd * 100) if tarifa_usd else 0
        signo    = "+" if diff >= 0 else ""
        color    = "#059669" if diff >= 0 else "#DC2626"
        icono    = "✅" if diff >= 0 else "⚠️"
        st.markdown(
            f'<div style="background:#eff6ff;border-left:4px solid #3b82f6;'
            f'padding:10px 16px;border-radius:8px;margin-bottom:14px;'
            f'font-size:0.9rem;color:#1e3a5f;">'
            f'📊 <b>Tarifa sugerida ({umbral_cd:.0f}% C.D.):</b>&nbsp;'
            f'{tarifa_ref_html}{sec_html}'
            f'&nbsp;&nbsp;{icono}&nbsp;'
            f'<span style="color:{color};font-weight:600;">'
            f'Tu tarifa está {signo}{diff_pct:.1f}%'
            f'&nbsp;(USD {signo}${diff:,.2f}) vs la sugerida'
            f'</span>'
            f'{nota_modal}{advertencia}'
            f'</div>',
            unsafe_allow_html=True,
        )
