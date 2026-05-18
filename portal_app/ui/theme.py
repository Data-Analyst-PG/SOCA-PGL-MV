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


def aplicar_tema():
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"], .stApp {{
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        background-color: {PGL_BG} !important;
        color: {PGL_TEXT} !important;
    }}
    [data-testid="stSidebar"]        {{ display: none !important; }}
    [data-testid="collapsedControl"] {{ display: none !important; }}
    @media (max-width: 768px) {{
        [data-testid="stSidebar"] {{ display: block !important; }}
        [data-testid="stSidebar"] > div:first-child {{
            background: linear-gradient(135deg, {PGL_NAVY} 0%, {PGL_NAVY_LT} 100%) !important;
            padding-top: 1rem !important;
        }}
        [data-testid="stSidebarNav"] a,
        [data-testid="stSidebarNav"] span,
        [data-testid="stSidebarNav"] p {{
            color: rgba(255,255,255,0.85) !important;
            font-weight: 500 !important;
        }}
        [data-testid="stSidebarNav"] a:hover {{
            color: white !important;
            background: rgba(204,30,30,0.18) !important;
            border-radius: 6px !important;
        }}
        [data-testid="stSidebarNav"] [aria-selected="true"] a,
        [data-testid="stSidebarNav"] [aria-current] {{
            color: white !important;
            background: rgba(204,30,30,0.15) !important;
            border-radius: 6px !important;
            font-weight: 700 !important;
        }}
        [data-testid="stSidebarNav"] .st-emotion-cache-1egp75f {{
            color: rgba(255,255,255,0.5) !important;
            font-size: 0.72rem !important;
            font-weight: 700 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.5px !important;
        }}
        [data-testid="collapsedControl"] {{ display: flex !important; }}
        [data-testid="collapsedControl"] {{
            background: rgba(204,30,30,0.25) !important;
            border-radius: 0 8px 8px 0 !important;
            width: 32px !important;
            height: 32px !important;
            align-items: center !important;
            justify-content: center !important;
            margin-top: 8px !important;
        }}
        [data-testid="stSidebarCollapseButton"] button,
        [data-testid="stSidebar"] [data-testid="collapsedControl"] button {{
            background: rgba(255,255,255,0.15) !important;
            border-radius: 8px !important;
            color: white !important;
        }}
        [data-testid="stSidebarCollapseButton"] svg,
        [data-testid="stSidebar"] button svg {{
            color: white !important;
            fill: white !important;
        }}
        [data-testid="collapsedControl"] svg {{
            color: white !important;
            fill: white !important;
            width: 18px !important;
            height: 18px !important;
        }}
    }}
    #MainMenu {{ visibility: hidden; }}
    footer    {{ visibility: hidden; }}
    [data-testid="stHeader"] {{
        background: linear-gradient(135deg, {PGL_NAVY} 0%, {PGL_NAVY_LT} 100%) !important;
        border-bottom: 3px solid {PGL_RED} !important;
    }}
    [data-testid="stHeader"] * {{ color: white !important; }}
    [data-testid="stNavigation"] {{
        background: linear-gradient(135deg, {PGL_NAVY} 0%, {PGL_NAVY_LT} 100%) !important;
        border-bottom: 3px solid {PGL_RED} !important;
        padding: 0 1rem !important;
        overflow-x: auto !important;
        white-space: nowrap !important;
        -webkit-overflow-scrolling: touch !important;
        scrollbar-width: none !important;
    }}
    [data-testid="stNavigation"]::-webkit-scrollbar {{ display: none !important; }}
    [data-testid="stNavigation"] a,
    [data-testid="stNavigation"] button {{
        color: rgba(255,255,255,0.85) !important;
        font-weight: 500 !important;
        font-size: 0.85rem !important;
        padding: 0.7rem 0.9rem !important;
        border-radius: 0 !important;
        white-space: nowrap !important;
        min-height: 44px !important;
        display: inline-flex !important;
        align-items: center !important;
    }}
    [data-testid="stNavigation"] a:hover,
    [data-testid="stNavigation"] button:hover {{
        color: white !important;
        background: rgba(204,30,30,0.18) !important;
    }}
    [data-testid="stNavigation"] a[aria-selected="true"] {{
        color: white !important;
        border-bottom: 3px solid {PGL_RED} !important;
        background: rgba(204,30,30,0.12) !important;
        font-weight: 700 !important;
    }}
    [data-testid="stNavigation"] ul,
    [data-testid="stNavigation"] [role="menu"] {{
        background: white !important;
        border-radius: 8px !important;
        box-shadow: 0 4px 16px rgba(27,34,102,0.15) !important;
        padding: 4px !important;
    }}
    [data-testid="stNavigation"] ul a,
    [data-testid="stNavigation"] [role="menu"] a,
    [data-testid="stNavigation"] ul li,
    [data-testid="stNavigation"] [role="menuitem"] {{
        color: {PGL_NAVY} !important;
        background: transparent !important;
        border-radius: 6px !important;
        min-height: 36px !important;
    }}
    [data-testid="stNavigation"] ul a:hover,
    [data-testid="stNavigation"] [role="menuitem"]:hover {{
        background: rgba(27,34,102,0.08) !important;
        color: {PGL_NAVY} !important;
    }}
    .block-container {{ padding: 4rem 1.5rem 2rem 1.5rem !important; max-width: 1200px; }}
    .stButton > button[kind="primary"] {{
        background: linear-gradient(135deg, {PGL_RED}, {PGL_RED_LT}) !important;
        border: none !important; color: white !important; font-weight: 600 !important;
        border-radius: 8px !important;
    }}
    .stButton > button[kind="primary"]:hover {{
        background: linear-gradient(135deg, #a81818, {PGL_RED}) !important;
        box-shadow: 0 4px 14px rgba(204,30,30,0.35) !important;
    }}
    .stButton > button:not([kind="primary"]) {{
        border: 1.5px solid {PGL_NAVY} !important;
        color: {PGL_NAVY} !important; border-radius: 8px !important;
        font-weight: 500 !important; background: white !important;
    }}
    .stButton > button:not([kind="primary"]):hover {{
        background: {PGL_NAVY} !important; color: white !important;
    }}
    [data-testid="stMetric"] {{
        background: {PGL_WHITE}; border-radius: 12px; padding: 1rem 1.2rem;
        border: 1px solid {PGL_BORDER}; border-left: 4px solid {PGL_RED};
        box-shadow: 0 2px 8px rgba(27,34,102,0.07);
    }}
    [data-testid="stMetricValue"] {{ font-weight: 700; color: {PGL_NAVY} !important; }}
    [data-testid="stDataFrame"] {{ border-radius: 10px; overflow: hidden; }}
    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input,
    [data-testid="stTextArea"] textarea {{
        border-radius: 8px !important; border: 1.5px solid #D1D8E8 !important;
    }}
    [data-testid="stTextInput"] input:focus,
    [data-testid="stNumberInput"] input:focus,
    [data-testid="stTextArea"] textarea:focus {{
        border-color: {PGL_NAVY} !important;
        box-shadow: 0 0 0 3px rgba(27,34,102,0.12) !important;
    }}
    [data-testid="stSelectbox"] > div > div {{
        border-radius: 8px !important; border: 1.5px solid #D1D8E8 !important;
    }}
    [data-testid="stTabs"] [role="tab"] {{
        font-weight: 600; color: {PGL_MUTED};
    }}
    [data-testid="stTabs"] [role="tab"][aria-selected="true"] {{
        color: {PGL_NAVY} !important; border-bottom: 3px solid {PGL_RED} !important;
    }}
    [data-testid="stExpander"] summary {{ font-weight: 600; color: {PGL_NAVY}; }}
    @media (max-width: 768px) {{
        .block-container {{ padding: 3.5rem 0.75rem 1.5rem 0.75rem !important; }}
        .pgl-kpi-grid {{ grid-template-columns: repeat(2, 1fr) !important; }}
        .pgl-card-grid {{ grid-template-columns: 1fr !important; }}
        .pgl-btn-row {{ flex-direction: column; }}
        .pgl-btn-row .stButton > button {{ width: 100% !important; }}
    }}
    @media (max-width: 480px) {{
        .pgl-kpi-grid {{ grid-template-columns: 1fr !important; }}
    }}
    </style>
    """, unsafe_allow_html=True)


def user_header(nombre: str, rol: str = ""):
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
            f'<div style="display:flex;align-items:center;gap:0.6rem;padding:0.3rem 0 0 0;">'
            f'<span style="font-size:1.4rem;">🚚</span>'
            f'<div>'
            f'<div style="font-weight:800;font-size:0.85rem;color:{PGL_NAVY};line-height:1.1;">PALOS GARZA</div>'
            f'<div style="font-weight:600;font-size:0.68rem;color:{PGL_RED};letter-spacing:1px;text-transform:uppercase;">Logistics</div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )
    with col_right:
        st.markdown(
            f'<div style="display:flex;justify-content:flex-end;align-items:center;padding:0.3rem 0 0.6rem 0;">'
            f'<div style="text-align:right;line-height:1.4;">'
            f'<div style="font-weight:600;font-size:0.85rem;color:{PGL_NAVY};">👤 {nombre}</div>'
            f'<span style="display:inline-block;padding:2px 10px;border-radius:20px;'
            f'font-size:0.7rem;font-weight:700;text-transform:uppercase;'
            f'color:{color_texto};background:{color_bg};">{rol or "usuario"}</span>'
            f'</div></div>',
            unsafe_allow_html=True,
        )
