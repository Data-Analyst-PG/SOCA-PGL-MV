# portal_app/app.py
# ─────────────────────────────────────────────────────────────────────────────
# Punto de entrada de SOCA — Portal Palos Garza Logistics
# ─────────────────────────────────────────────────────────────────────────────
import streamlit as st

st.set_page_config(
    page_title="Portal PGL",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from services.supabase_client import current_user, set_session_in_state
from services.authz import ensure_auth_loaded, profile
from services.access import check_access, get_user_permissions
from modules.auth import render_login_page
from ui.theme import aplicar_tema, user_header


# ── Sesión ────────────────────────────────────────────────────────────────────
u = current_user()
if not u:
    render_login_page()
    st.stop()

if not ensure_auth_loaded():
    render_login_page()
    st.stop()

aplicar_tema()

p              = profile() or {}
nombre_usuario = p.get("full_name") or u.get("email", "Usuario")
rol_usuario    = p.get("role", "")
user_id        = u.get("id") or u.get("sub") or ""

user_header(nombre_usuario, rol_usuario)

# ── Precargar permisos en caché una sola vez por sesión ──────────────────────
perms = get_user_permissions(user_id)
es_admin = perms.get("_is_admin", False) or rol_usuario == "admin"

def _tiene(*claves):
    """True si el usuario tiene AL MENOS uno de los permisos indicados."""
    if es_admin:
        return True
    return any(perms.get(k, False) for k in claves)


# ── Construcción del menú de navegación ──────────────────────────────────────
def construir_navegacion() -> dict:
    secciones = {}

    # Principal
    secciones["Principal"] = [
        st.Page("pages/pg_home.py", title="🏠 Home", default=True),
    ]

    # Solicitudes
    if _tiene("complementarias:create", "complementarias:read",
              "tickets:create", "tickets:read",
              "viaticos:create", "viaticos:read"):
        secciones["Solicitudes"] = [
            st.Page("pages/pg_solicitudes.py", title="📋 Solicitudes", url_path="solicitudes"),
        ]

    # Seguimiento
    if _tiene("complementarias:manage", "tickets:manage", "viaticos:manage"):
        secciones["Seguimiento"] = [
            st.Page("pages/pg_gestion_solicitudes.py", title="📊 Seguimiento", url_path="seguimiento"),
        ]

    # Auditoría
    aud_pages = []
    _AUD = [
        ("auditoria:reporte_auxiliares",      "pages/pg_aud_auxiliares.py",            "📊 Reporte Auxiliares",       "aud-auxiliares"),
        ("auditoria:rutas_frecuentes",         "pages/pg_aud_rutas.py",                 "🗺️ Rutas Frecuentes",         "aud-rutas"),
        ("auditoria:rentabilidad",             "pages/pg_aud_rentabilidad.py",          "💹 Rentabilidad Clientes",    "aud-rentabilidad"),
        ("auditoria:prorrateador",             "pages/pg_aud_prorrateador.py",          "🧮 Prorrateador",             "aud-prorrateador"),
        ("auditoria:sac_ventas",               "pages/pg_aud_sac_ventas.py",            "📈 SAC Ventas",               "aud-sac-ventas"),
        ("auditoria:cartera_proveedores",      "pages/pg_aud_cartera_proveedores.py",   "🫱🏽‍🫲🏼 Cartera Proveedores",    "aud-cartera-proveedores"),
        ("auditoria:reporte_balanza_mensual",  "pages/pg_aud_reporte_balanza_mensual.py","📚 Reporte Balanza",          "aud-reporte-balanza"),
        ("auditoria:admin_manager",            "pages/pg_aud_admin.py",                 "🛠️ Admin Manager",            "aud-admin"),
    ]
    for perm, path, titulo, url in _AUD:
        if _tiene(perm):
            aud_pages.append(st.Page(path, title=titulo, url_path=url))

    # Auditorías por empresa — aparece si tiene acceso a AL MENOS UNA empresa
    _PERMS_AUDITORIAS = [
        "auditoria:lincoln_auditoria",
        "auditoria:igloo_auditoria",
        "auditoria:picus_auditoria",
        "auditoria:set_freight_auditoria",
        "auditoria:set_logis_auditoria",
    ]
    if _tiene(*_PERMS_AUDITORIAS):
        aud_pages.append(st.Page("pages/pg_aud_auditorias.py",
                                 title="🔍 Auditorías", url_path="aud-auditorias"))

    if aud_pages:
        secciones["Auditoría"] = aud_pages

    # Cotizadores
    _EMPRESAS = [
        ("picus",       "🚚 Picus",       "pages/pg_cot_picus.py",       "cot-picus"),
        ("igloo",       "🚛 Igloo",       "pages/pg_cot_igloo.py",       "cot-igloo"),
        ("lincoln",     "🏴 Lincoln",     "pages/pg_cot_lincoln.py",     "cot-lincoln"),
        ("set_logis",   "🚚 Set Logis",   "pages/pg_cot_set_logis.py",   "cot-set-logis"),
        ("set_freight", "📦 Set Freight", "pages/pg_cot_set_freight.py", "cot-set-freight"),
    ]
    _COT_PERMS = ["captura", "consulta", "simulador", "gestion", "cotizacion", "programacion", "concluidos"]
    cot_pages = []
    for slug, titulo, path, url in _EMPRESAS:
        if _tiene(*[f"cotizador_{slug}:{m}" for m in _COT_PERMS]):
            cot_pages.append(st.Page(path, title=titulo, url_path=url))
    if cot_pages:
        secciones["Cotizadores"] = cot_pages

    # Facturación
    if _tiene("facturacion:estado_cuenta"):
        secciones["Facturación"] = [
            st.Page("pages/pg_fact_estado_cuenta.py", title="💳 Estado de Cuenta", url_path="fact-estado-cuenta"),
        ]

    # Ventas
    ventas_pages = []
    if _tiene("ventas:buscador"):
        ventas_pages.append(st.Page("pages/pg_ventas_buscador.py", title="🔎 Buscador de Rutas", url_path="ventas-buscador"))
    if _tiene("ventas:subastas"):
        ventas_pages.append(st.Page("pages/pg_ventas_subastas.py", title="🏷️ Subastas de Tarifas", url_path="ventas-subastas"))
    if ventas_pages:
        secciones["Ventas"] = ventas_pages

    return secciones


# ── Ejecutar navegación ───────────────────────────────────────────────────────
nav = construir_navegacion()
if nav:
    pg = st.navigation(nav, position="top")
    pg.run()
else:
    st.error("Tu usuario no tiene módulos asignados. Contacta al administrador.")
