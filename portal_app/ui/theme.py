# portal_app/ui/theme.py
import streamlit as st

PGL_NAVY    = "#1B2266"
PGL_RED     = "#CC1E1E"
PGL_NAVY_LT = "#252D80"
PGL_RED_LT  = "#E02424"
PGL_BG      = "#F4F6FB"
PGL_WHITE   = "#FFFFFF"
PGL_TEXT    = "#1B2266"
PGL_MUTED   = "#6B7280"
PGL_BORDER  = "#E5E9F0"

_COLORES_ROL = {
    "admin":        ("#CC1E1E", "#FFF0F0"),
    "data_analyst": ("#1B2266", "#EEF0FF"),
    "auditor":      ("#0077B6", "#E8F4FC"),
    "user":         ("#2E7D32", "#E8F5E9"),
    "operaciones":  ("#E65100", "#FFF3E0"),
}


def aplicar_tema():
    """Inyecta CSS global responsive de Palos Garza Logistics."""
    css = """
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"], .stApp {
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        background-color: """ + PGL_BG + """ !important;
        color: """ + PGL_TEXT + """ !important;
    }

    [data-testid="stSidebar"]        { display: none !important; }
    [data-testid="collapsedControl"] { display: none !important; }
    #MainMenu { visibility: hidden; }
    footer    { visibility: hidden; }

    /* ── Header ── */
    [data-testid="stHeader"] {
        background: linear-gradient(135deg, """ + PGL_NAVY + """ 0%, """ + PGL_NAVY_LT + """ 100%) !important;
        border-bottom: 3px solid """ + PGL_RED + """ !important;
        overflow: visible !important;
    }
    [data-testid="stHeader"] * { color: white !important; }

    /* ── Navegación — scroll horizontal en móvil ── */
    [data-testid="stNavigation"] {
        background: linear-gradient(135deg, """ + PGL_NAVY + """ 0%, """ + PGL_NAVY_LT + """ 100%) !important;
        border-bottom: 3px solid """ + PGL_RED + """ !important;
        padding: 0 !important;
        overflow-x: auto !important;
        overflow-y: visible !important;
        white-space: nowrap !important;
        -webkit-overflow-scrolling: touch !important;
        scrollbar-width: none !important;
        display: flex !important;
        flex-wrap: nowrap !important;
        align-items: stretch !important;
    }
    [data-testid="stNavigation"]::-webkit-scrollbar {
        display: none !important;
    }
    [data-testid="stNavigation"] a,
    [data-testid="stNavigation"] button,
    [data-testid="stNavigation"] [role="button"] {
        color: rgba(255,255,255,0.85) !important;
        font-weight: 500 !important;
        font-size: 0.82rem !important;
        padding: 0.7rem 0.9rem !important;
        border-radius: 0 !important;
        letter-spacing: 0.2px !important;
        transition: all 0.2s !important;
        display: inline-flex !important;
        align-items: center !important;
        white-space: nowrap !important;
        text-decoration: none !important;
        min-height: 44px !important;
        cursor: pointer !important;
        background: transparent !important;
        border: none !important;
        flex-shrink: 0 !important;
    }
    [data-testid="stNavigation"] a:hover,
    [data-testid="stNavigation"] button:hover {
        color: white !important;
        background: rgba(204,30,30,0.2) !important;
    }
    [data-testid="stNavigation"] a[aria-selected="true"],
    [data-testid="stNavigation"] [aria-selected="true"] {
        color: white !important;
        border-bottom: 3px solid """ + PGL_RED + """ !important;
        background: rgba(204,30,30,0.15) !important;
        font-weight: 700 !important;
    }
    /* Ocultar flechas nativas que bloquean el scroll */
    [data-testid="stNavigation"] svg {
        display: none !important;
    }

    /* ── Padding general ── */
    .block-container {
        padding: 4rem 1.5rem 2rem 1.5rem !important;
        max-width: 1200px;
    }

    /* ── Botón primario ── */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, """ + PGL_RED + """, """ + PGL_RED_LT + """) !important;
        border: none !important; color: white !important; font-weight: 600 !important;
        border-radius: 8px !important; font-family: 'Plus Jakarta Sans', sans-serif !important;
    }
    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #a81818, """ + PGL_RED + """) !important;
        box-shadow: 0 4px 14px rgba(204,30,30,0.35) !important;
    }

    /* ── Botón secundario ── */
    .stButton > button:not([kind="primary"]) {
        border: 1.5px solid """ + PGL_NAVY + """ !important;
        color: """ + PGL_NAVY + """ !important; border-radius: 8px !important;
        font-weight: 500 !important; background: white !important;
        font-family: 'Plus Jakarta Sans', sans-serif !important;
    }
    .stButton > button:not([kind="primary"]):hover {
        background: """ + PGL_NAVY + """ !important; color: white !important;
    }

    /* ── Métricas ── */
    [data-testid="stMetric"] {
        background: """ + PGL_WHITE + """; border-radius: 12px; padding: 1rem 1.2rem;
        border: 1px solid """ + PGL_BORDER + """; border-left: 4px solid """ + PGL_RED + """;
        box-shadow: 0 2px 8px rgba(27,34,102,0.07);
    }
    [data-testid="stMetricValue"] { font-weight: 700; color: """ + PGL_NAVY + """ !important; }

    /* ── DataFrames ── */
    [data-testid="stDataFrame"] {
        border-radius: 10px; overflow: hidden;
        box-shadow: 0 2px 8px rgba(27,34,102,0.06);
    }

    /* ── Inputs ── */
    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input,
    [data-testid="stTextArea"] textarea {
        border-radius: 8px !important; border: 1.5px solid #D1D8E8 !important;
        font-family: 'Plus Jakarta Sans', sans-serif !important;
    }
    [data-testid="stTextInput"] input:focus,
    [data-testid="stNumberInput"] input:focus,
    [data-testid="stTextArea"] textarea:focus {
        border-color: """ + PGL_NAVY + """ !important;
        box-shadow: 0 0 0 3px rgba(27,34,102,0.12) !important;
    }

    /* ── Selectboxes ── */
    [data-testid="stSelectbox"] > div > div {
        border-radius: 8px !important; border: 1.5px solid #D1D8E8 !important;
    }

    /* ── Tabs ── */
    [data-testid="stTabs"] [role="tab"] {
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        font-weight: 600; color: """ + PGL_MUTED + """;
    }
    [data-testid="stTabs"] [role="tab"][aria-selected="true"] {
        color: """ + PGL_NAVY + """ !important;
        border-bottom: 3px solid """ + PGL_RED + """ !important;
    }

    /* ── Expanders ── */
    [data-testid="stExpander"] summary { font-weight: 600; color: """ + PGL_NAVY + """; }

    /* ── RESPONSIVE MÓVIL ── */
    @media (max-width: 768px) {
        .block-container { padding: 3.5rem 0.75rem 1.5rem 0.75rem !important; }
        .pgl-kpi-grid    { grid-template-columns: repeat(2, 1fr) !important; }
        .pgl-card-grid   { grid-template-columns: 1fr !important; }
        .pgl-banner-title { font-size: 1rem !important; }
        .pgl-btn-row     { flex-direction: column; }
        .pgl-btn-row .stButton > button { width: 100% !important; }

        /* Menú más compacto en móvil */
        [data-testid="stNavigation"] a,
        [data-testid="stNavigation"] button,
        [data-testid="stNavigation"] [role="button"] {
            font-size: 0.75rem !important;
            padding: 0.65rem 0.7rem !important;
            min-height: 44px !important;
        }
    }
    @media (max-width: 480px) {
        .pgl-kpi-grid { grid-template-columns: 1fr !important; }
    }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


def user_header(nombre: str, rol: str = ""):
    """Barra superior: logo izquierda | nombre + rol derecha."""
    _colores_rol = {
        "admin":        ("#CC1E1E", "#FFF0F0"),
        "data_analyst": ("#1B2266", "#EEF0FF"),
        "auditor":      ("#0077B6", "#E8F4FC"),
        "user":         ("#2E7D32", "#E8F5E9"),
        "operaciones":  ("#E65100", "#FFF3E0"),
    }
    rol_limpio = (rol or "").lower()
    color_texto, color_bg = _colores_rol.get(rol_limpio, ("#6B7280", "#F3F4F6"))

    col_logo, col_right = st.columns([3, 9])

    with col_logo:
        st.markdown(
            '<div style="display:flex; align-items:center; gap:0.6rem; padding:0.3rem 0 0 0;">'
            '<span style="font-size:1.4rem;">🚚</span>'
            '<div>'
            '<div style="font-weight:800; font-size:0.85rem; color:' + PGL_NAVY + '; line-height:1.1;">PALOS GARZA</div>'
            '<div style="font-weight:600; font-size:0.68rem; color:' + PGL_RED + '; letter-spacing:1px; text-transform:uppercase;">Logistics</div>'
            '</div></div>',
            unsafe_allow_html=True
        )

    with col_right:
        st.markdown(
            '<div style="display:flex; justify-content:flex-end; align-items:center; gap:0.8rem; padding:0.3rem 0 0.6rem 0;">'
            '<div style="text-align:right; line-height:1.4;">'
            '<div style="font-weight:600; font-size:0.85rem; color:' + PGL_NAVY + '; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">'
            '👤 ' + nombre +
            '</div>'
            '<span style="display:inline-block; padding:2px 10px; border-radius:20px; font-size:0.7rem; font-weight:700; letter-spacing:0.5px; text-transform:uppercase; color:' + color_texto + '; background:' + color_bg + ';">'
            + (rol or "usuario") +
            '</span>'
            '</div></div>',
            unsafe_allow_html=True
        )
