# portal_app/modules/home.py
import streamlit as st

from services.supabase_client import current_user, get_authed_client
from services.authz import profile, role as get_role
from services.access import get_user_permissions
from ui.components import welcome_banner, kpi_row, module_card, divider


@st.cache_data(ttl=60, show_spinner=False)
def _get_ticket_counts(user_id: str, user_email: str) -> dict:
    """Conteo de tickets del usuario logueado. Cacheado 60s."""
    try:
        sb = get_authed_client()
        res = (
            sb.table("tickets")
            .select("estatus")
            .ilike("correo", user_email)
            .limit(1000)
            .execute()
        )
        rows = res.data or []
        counts = {"Nuevo": 0, "En Proceso": 0, "Cancelado": 0, "Concluido": 0}
        for r in rows:
            s = r.get("estatus") or "Nuevo"
            if s in counts:
                counts[s] += 1
        return counts
    except Exception:
        return {"Nuevo": 0, "En Proceso": 0, "Cancelado": 0, "Concluido": 0}


@st.cache_data(ttl=60, show_spinner=False)
def _get_comp_counts(user_id: str, user_email: str) -> dict:
    """Conteo de complementarias del usuario logueado. Cacheado 60s."""
    try:
        sb = get_authed_client()
        res = (
            sb.table("solicitudes_complementarias")
            .select("estatus")
            .ilike("correo", user_email)
            .limit(1000)
            .execute()
        )
        rows = res.data or []
        counts = {"Pendiente": 0, "En revisión": 0, "Cancelado": 0, "Resuelto": 0}
        for r in rows:
            s = r.get("estatus") or "Pendiente"
            if s in counts:
                counts[s] += 1
        return counts
    except Exception:
        return {"Pendiente": 0, "En revisión": 0, "Cancelado": 0, "Resuelto": 0}


def render():
    u       = current_user() or {}
    p       = profile() or {}
    user_id = u.get("id") or u.get("sub") or ""
    nombre  = p.get("full_name") or (u.get("email", "").split("@")[0] if u else "Usuario")
    rol     = p.get("job_title") or get_role() or "usuario"
    area    = p.get("area_name") or ""

    welcome_banner(nombre, rol, area)

    # user_email debe definirse ANTES de llamar a las funciones cacheadas
    user_email = (u.get("email") or "").strip().lower()

    t_counts = _get_ticket_counts(user_id, user_email)
    c_counts = _get_comp_counts(user_id, user_email)

    t_total      = sum(t_counts.values())
    t_abiertos   = t_counts["Nuevo"] + t_counts.get("En Proceso", 0)
    c_total      = sum(c_counts.values())
    c_resueltos  = c_counts["Resuelto"]
    c_pendientes = c_counts["Pendiente"] + c_counts["En revisión"]

    st.markdown("### 📊 Resumen general")
    kpi_row([
        dict(icono="🎫", label="Tickets totales",
             valor=t_total, sub=f"{t_abiertos} abiertos", color="#1D4ED8"),
        dict(icono="⏳", label="Tickets abiertos",
             valor=t_abiertos, sub=f"{t_counts['Nuevo']} nuevos", color="#D97706"),
        dict(icono="📬", label="Complementarias total",
             valor=c_total, sub=f"{c_pendientes} pendientes", color="#1B2266"),
        dict(icono="✅", label="Complementarias resueltas",
             valor=c_resueltos, sub="históricas", color="#059669"),
    ])

    st.markdown("### 🚀 Acceso rápido")

    perms    = get_user_permissions(user_id)
    es_admin = perms.get("_is_admin", False) or rol == "admin"

    def _tiene(*claves):
        if es_admin:
            return True
        return any(perms.get(k, False) for k in claves)

    tiene_tickets     = _tiene("tickets:create", "tickets:read")
    tiene_comp        = _tiene("complementarias:create", "complementarias:read")
    tiene_auditoria   = _tiene(
        "auditoria:reporte_auxiliares", "auditoria:rutas_frecuentes",
        "auditoria:rentabilidad",       "auditoria:prorrateador",
        "auditoria:lincoln_auditoria",  "auditoria:sac_ventas",
        "auditoria:cartera_proveedores","auditoria:reporte_balanza_mensual",
    )
    tiene_facturacion = _tiene("facturacion:estado_cuenta")
    tiene_ventas      = _tiene("ventas:buscador", "ventas:subastas")

    _EMPRESAS_COT = [
        ("picus",       "Picus"),
        ("igloo",       "Igloo"),
        ("lincoln",     "Lincoln"),
        ("set_freight", "Set Freight"),
        ("set_logis",   "Set Logis"),
    ]
    _MODOS_COT = ["captura","consulta","simulador","gestion","cotizacion","programacion","concluidos"]

    empresas_accesibles = [
        nombre_emp for slug, nombre_emp in _EMPRESAS_COT
        if _tiene(*[f"cotizador_{slug}:{m}" for m in _MODOS_COT])
    ]
    tiene_cotizadores = len(empresas_accesibles) > 0

    cards_izq = []
    cards_der = []

    if tiene_tickets:
        cards_izq.append(dict(
            icono="🎫",
            titulo="Tickets",
            descripcion="Crea y consulta solicitudes al equipo de Análisis de Datos",
            color_acento="#1D4ED8",
            badges=[
                dict(texto=f"{t_counts['Nuevo']} Nuevos",              color="blue"),
                dict(texto=f"{t_counts.get('En Proceso',0)} En proceso", color="yellow"),
                dict(texto=f"{t_counts.get('Concluido',0)} Concluidos",  color="green"),
            ],
        ))

    if tiene_auditoria:
        n_herr = sum([
            _tiene("auditoria:reporte_auxiliares"),
            _tiene("auditoria:rutas_frecuentes"),
            _tiene("auditoria:rentabilidad"),
            _tiene("auditoria:prorrateador"),
            _tiene("auditoria:lincoln_auditoria"),
            _tiene("auditoria:sac_ventas"),
            _tiene("auditoria:cartera_proveedores"),
            _tiene("auditoria:reporte_balanza_mensual"),
        ])
        cards_izq.append(dict(
            icono="🕵️",
            titulo="Auditoría",
            descripcion="Reporte auxiliares, rutas frecuentes, rentabilidad y prorrateador",
            color_acento="#0077B6",
            badges=[dict(texto=f"{n_herr} herramientas", color="gray")],
        ))

    if tiene_facturacion:
        cards_izq.append(dict(
            icono="💳",
            titulo="Facturación",
            descripcion="Estado de cuenta y módulos de facturación",
            color_acento="#B45309",
            badges=[dict(texto="Estado de cuenta", color="yellow")],
        ))

    if tiene_ventas:
        cards_der.append(dict(
            icono="📈",
            titulo="Ventas",
            descripcion="Buscador de rutas y subastas de tarifas",
            color_acento="#7C3AED",
            badges=[b for b in [
                dict(texto="Buscador", color="purple") if _tiene("ventas:buscador") else None,
                dict(texto="Subastas", color="purple") if _tiene("ventas:subastas") else None,
            ] if b],
        ))

    if tiene_comp:
        cards_der.append(dict(
            icono="📬",
            titulo="Complementarias",
            descripcion="Captura y consulta de solicitudes de complementarias y desconclusiones",
            color_acento="#CC1E1E",
            badges=[
                dict(texto=f"{c_counts['Pendiente']} Pendientes",    color="blue"),
                dict(texto=f"{c_counts['En revisión']} En revisión",  color="yellow"),
                dict(texto=f"{c_counts['Resuelto']} Resueltos",       color="green"),
            ],
        ))

    if tiene_cotizadores:
        cards_der.append(dict(
            icono="🚚",
            titulo="Cotizadores",
            descripcion=f"Herramientas de cotización — {', '.join(empresas_accesibles)}",
            color_acento="#2E7D32",
            badges=[dict(texto=e, color="gray") for e in empresas_accesibles],
        ))

    if not cards_izq and not cards_der:
        st.info("No tienes módulos asignados aún. Contacta al administrador.")
    else:
        col_izq, col_der = st.columns(2)
        with col_izq:
            for c in cards_izq:
                module_card(**c)
        with col_der:
            for c in cards_der:
                module_card(**c)

    st.markdown("<br>", unsafe_allow_html=True)
    divider()

    col_footer, col_btn = st.columns([8, 2])
    with col_footer:
        st.caption("Portal PGL · Palos Garza Logistics")
    with col_btn:
        if st.button("🚪 Cerrar sesión", key="btn_logout_home", use_container_width=True):
            from modules.auth import logout
            logout()
            st.rerun()
