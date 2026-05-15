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
# ─────────────────────────────────────────────────────────────────────────────
import streamlit as st
from ui.theme import PGL_NAVY, PGL_RED, PGL_NAVY_LT, PGL_MUTED, PGL_BORDER, PGL_WHITE


# ─────────────────────────────────────────────────────────────────────────────
# 1. BANNER DE PÁGINA
#    Banda azul marino con ícono, título y subtítulo.
#    Úsalo al inicio de cada módulo/página.
#
#    Ejemplo:
#        page_banner("📋", "Solicitudes", "Crea y consulta tus solicitudes")
# ─────────────────────────────────────────────────────────────────────────────
def page_banner(icono: str, titulo: str, subtitulo: str = ""):
    sub_html = f'<div style="font-size:0.82rem; color:rgba(255,255,255,0.65); margin-top:0.3rem;">{subtitulo}</div>' if subtitulo else ""
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, {PGL_NAVY} 0%, {PGL_NAVY_LT} 100%);
        border-radius: 14px;
        padding: 1.3rem 1.8rem;
        margin-bottom: 1.5rem;
        border-left: 5px solid {PGL_RED};
        display: flex;
        align-items: center;
        gap: 1rem;
        position: relative;
        overflow: hidden;
    ">
        <div style="position:absolute; right:-10px; top:-10px; font-size:6rem; opacity:0.06; line-height:1; pointer-events:none;">
            {icono}
        </div>
        <span style="font-size:2rem; flex-shrink:0;">{icono}</span>
        <div>
            <div style="font-size:1.25rem; font-weight:700; color:white; line-height:1.2;">{titulo}</div>
            {sub_html}
        </div>
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# 2. ENCABEZADO DE SECCIÓN
#    Más compacto que page_banner. Úsalo para dividir secciones dentro de
#    una misma página.
#
#    Ejemplo:
#        section_header("📊", "Resumen de rutas", "Últimos 30 días")
# ─────────────────────────────────────────────────────────────────────────────
def section_header(icono: str, titulo: str, subtitulo: str = ""):
    sub_html = f'<div style="font-size:0.75rem; color:{PGL_MUTED}; margin-top:1px;">{subtitulo}</div>' if subtitulo else ""
    st.markdown(f"""
    <div style="
        display: flex;
        align-items: center;
        gap: 0.65rem;
        padding: 0.7rem 1rem;
        background: rgba(27,34,102,0.06);
        border-radius: 10px;
        border-left: 4px solid {PGL_RED};
        margin-bottom: 1rem;
    ">
        <span style="font-size:1.1rem; flex-shrink:0;">{icono}</span>
        <div>
            <div style="font-size:0.95rem; font-weight:700; color:{PGL_NAVY}; line-height:1.2;">{titulo}</div>
            {sub_html}
        </div>
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# 3. FILA DE KPIs
#    Muestra una fila de tarjetas con número grande.
#    Se adapta a 2 columnas en móvil automáticamente.
#
#    items = lista de dicts con claves:
#        icono   → emoji o texto corto
#        label   → nombre del KPI
#        valor   → número o texto a mostrar
#        sub     → texto pequeño debajo del número
#        color   → color hex del acento izquierdo y del número
#
#    Ejemplo:
#        kpi_row([
#            dict(icono="🎫", label="Tickets", valor=24, sub="6 abiertos", color="#1D4ED8"),
#            dict(icono="✅", label="Resueltos", valor=5, sub="históricas", color="#059669"),
#        ])
# ─────────────────────────────────────────────────────────────────────────────
def kpi_row(items: list):
    cards_html = ""
    for item in items:
        icono = item.get("icono", "")
        label = item.get("label", "")
        valor = item.get("valor", 0)
        sub   = item.get("sub", "")
        color = item.get("color", PGL_NAVY)
        cards_html += f"""
        <div style="
            background: {PGL_WHITE};
            border-radius: 12px;
            padding: 1rem 1.1rem;
            border: 1px solid {PGL_BORDER};
            border-left: 4px solid {color};
            box-shadow: 0 2px 8px rgba(27,34,102,0.06);
        ">
            <div style="font-size:0.7rem; font-weight:600; text-transform:uppercase;
                        letter-spacing:0.5px; color:{PGL_MUTED}; margin-bottom:4px;">
                {icono} {label}
            </div>
            <div style="font-size:1.9rem; font-weight:800; color:{color}; line-height:1.1;">
                {valor}
            </div>
            <div style="font-size:0.72rem; color:{PGL_MUTED}; margin-top:3px;">{sub}</div>
        </div>
        """

    st.markdown(f"""
    <div class="pgl-kpi-grid" style="
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
        gap: 10px;
        margin-bottom: 1.5rem;
    ">
        {cards_html}
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# 4. TARJETA DE MÓDULO
#    Card con ícono, título, descripción y badges de conteo.
#    Úsala en el home y en páginas de selección de sub-módulos.
#
#    badges = lista de dicts:
#        texto → texto del badge
#        color → "blue" | "yellow" | "green" | "red" | "gray" | "purple"
#
#    Ejemplo:
#        module_card(
#            icono="🎫", titulo="Tickets", color_acento="#1D4ED8",
#            descripcion="Crea y consulta solicitudes",
#            badges=[
#                dict(texto="3 Nuevos", color="blue"),
#                dict(texto="1 En proceso", color="yellow"),
#            ]
#        )
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
        badges_html += f"""
        <span style="display:inline-block; background:{bg}; color:{fg};
                     font-size:0.72rem; font-weight:700; padding:3px 10px;
                     border-radius:20px; margin-right:5px; margin-top:4px;">
            {b.get("texto", "")}
        </span>
        """

    st.markdown(f"""
    <div style="
        background: {PGL_WHITE};
        border-radius: 14px;
        padding: 1.3rem 1.5rem;
        border: 1px solid {PGL_BORDER};
        border-left: 5px solid {color_acento};
        box-shadow: 0 2px 10px rgba(27,34,102,0.07);
        margin-bottom: 0.75rem;
    ">
        <div style="display:flex; align-items:center; gap:0.75rem; margin-bottom:0.5rem;">
            <span style="font-size:1.7rem;">{icono}</span>
            <div>
                <div style="font-weight:700; font-size:1rem; color:{PGL_NAVY};">{titulo}</div>
                <div style="font-size:0.8rem; color:{PGL_MUTED}; line-height:1.3;">{descripcion}</div>
            </div>
        </div>
        <div style="margin-top:0.4rem;">{badges_html}</div>
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# 5. ALERTAS
#    Caja de mensaje con color según tipo.
#
#    tipo → "info" | "warn" | "error" | "success"
#
#    Ejemplo:
#        alert("success", "Solicitud enviada correctamente. Folio: #00142")
#        alert("warn", "Esta cotización tiene más de 30 días.")
#        alert("error", "No tienes permiso para editar este registro.")
#        alert("info", "Los datos se actualizan cada 24 horas.")
# ─────────────────────────────────────────────────────────────────────────────

_ALERT_STYLES = {
    "info":    ("rgba(27,34,102,0.07)", PGL_NAVY,    "ℹ️"),
    "warn":    ("#FFF8E1",              "#B45309",   "⚠️"),
    "error":   ("#FEE2E2",              "#991B1B",   "❌"),
    "success": ("#D1FAE5",              "#065F46",   "✅"),
}

def alert(tipo: str, mensaje: str):
    bg, border_color, emoji = _ALERT_STYLES.get(tipo, _ALERT_STYLES["info"])
    st.markdown(f"""
    <div style="
        background: {bg};
        border-left: 4px solid {border_color};
        border-radius: 0 8px 8px 0;
        padding: 0.7rem 1rem;
        font-size: 0.88rem;
        color: {border_color};
        margin: 0.5rem 0;
        line-height: 1.4;
    ">
        {emoji} {mensaje}
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# 6. BADGE DE ESTATUS (devuelve HTML — úsalo dentro de st.markdown)
#    Para usar en tablas HTML o textos con unsafe_allow_html=True.
#
#    tipo → "nuevo" | "en_proceso" | "concluido" | "cancelado"
#          "pendiente" | "revision" | "resuelto"
#
#    Ejemplo:
#        st.markdown(status_badge("Nuevo", "nuevo"), unsafe_allow_html=True)
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
        f'<span style="display:inline-block; background:{bg}; color:{fg}; '
        f'font-size:0.72rem; font-weight:700; padding:3px 10px; '
        f'border-radius:20px;">{texto}</span>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# 7. DIVISOR VISUAL
#    Línea separadora con espaciado correcto.
#
#    Ejemplo:
#        divider()
# ─────────────────────────────────────────────────────────────────────────────
def divider():
    st.markdown(f"""
    <hr style="border:none; border-top:1.5px solid {PGL_BORDER}; margin:1.5rem 0;">
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# 8. BANNER DE BIENVENIDA (para el home)
#    Banner personalizado con nombre y rol del usuario.
#
#    Ejemplo:
#        welcome_banner("Heidi Rodriguez", "data_analyst", "Análisis de Datos")
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
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, {PGL_NAVY} 0%, {PGL_NAVY_LT} 100%);
        border-radius: 16px;
        padding: 2rem 2.5rem;
        margin-bottom: 2rem;
        border-left: 5px solid {PGL_RED};
        position: relative;
        overflow: hidden;
    ">
        <div style="position:absolute; right:-20px; top:-20px; font-size:8rem;
                    opacity:0.06; line-height:1; pointer-events:none;">🚚</div>
        <div style="font-size:0.85rem; color:rgba(255,255,255,0.65);
                    font-weight:500; margin-bottom:0.3rem;">Bienvenido de vuelta</div>
        <div style="font-size:1.8rem; font-weight:800; color:white;
                    margin-bottom:0.4rem; line-height:1.2;">{nombre}</div>
        <span style="
            background:{c_bg}; color:{c_texto};
            font-size:0.75rem; font-weight:700;
            padding:3px 12px; border-radius:20px;
            text-transform:uppercase; letter-spacing:0.5px;
            display:inline-block;
        ">{rol}</span>
        <div style="color:rgba(255,255,255,0.5); font-size:0.8rem; margin-top:0.8rem;">
            {subtitulo}
        </div>
    </div>
    """, unsafe_allow_html=True)
