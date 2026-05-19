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
    "data_analyst": ("#1B2266", "#EEF0FF"),
    "auditor":      ("#0077B6", "#E8F4FC"),
    "user":         ("#2E7D32", "#E8F5E9"),
    "operaciones":  ("#E65100", "#FFF3E0"),
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
