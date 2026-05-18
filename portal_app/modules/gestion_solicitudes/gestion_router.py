# portal_app/modules/gestion_solicitudes/gestion_router.py
# ─────────────────────────────────────────────────────────────────────────────
# Módulo de Seguimiento — gestión de tickets y complementarias para managers
# Permisos requeridos: tickets:manage | complementarias:manage | viaticos:manage
# ─────────────────────────────────────────────────────────────────────────────
import streamlit as st

from services.supabase_client import current_user, get_authed_client
from services.access import check_access
from ui.components import page_banner, section_header, alert, kpi_row, divider


# ── Helpers Supabase ──────────────────────────────────────────────────────────

def _get_tickets():
    try:
        sb = get_authed_client()
        res = sb.table("tickets").select("*").order("created_at", desc=True).limit(500).execute()
        return res.data or []
    except Exception:
        return []

def _get_complementarias():
    try:
        sb = get_authed_client()
        res = (
            sb.table("solicitudes_complementarias")
            .select("*")
            .order("fecha_captura", desc=True)
            .limit(500)
            .execute()
        )
        return res.data or []
    except Exception:
        return []

def _update_ticket(ticket_id, changes: dict):
    sb = get_authed_client()
    sb.table("tickets").update(changes).eq("id", ticket_id).execute()

def _update_complementaria(folio, changes: dict):
    sb = get_authed_client()
    sb.table("solicitudes_complementarias").update(changes).eq("folio", folio).execute()


# ── Sección Tickets ───────────────────────────────────────────────────────────

def _render_tickets():
    section_header("🎫", "Gestión de Tickets", "Administra y actualiza el estatus de los tickets")

    tickets = _get_tickets()
    if not tickets:
        alert("info", "No hay tickets registrados.")
        return

    # KPIs
    from collections import Counter
    conteo = Counter(t.get("estatus", "Nuevo") for t in tickets)
    kpi_row([
        dict(icono="🆕", label="Nuevos",     valor=conteo.get("Nuevo", 0),      color="#1D4ED8"),
        dict(icono="⏳", label="En Proceso",  valor=conteo.get("En Proceso", 0), color="#D97706"),
        dict(icono="✅", label="Concluidos",  valor=conteo.get("Concluido", 0),  color="#059669"),
        dict(icono="🚫", label="Cancelados",  valor=conteo.get("Cancelado", 0),  color="#DC2626"),
    ])

    # Filtros
    col1, col2 = st.columns(2)
    with col1:
        filtro_estatus = st.selectbox(
            "Filtrar por estatus",
            ["Todos", "Nuevo", "En Proceso", "Concluido", "Cancelado"],
            key="gest_ticket_estatus"
        )
    with col2:
        filtro_buscar = st.text_input("Buscar por título o solicitante", key="gest_ticket_buscar")

    filtrados = tickets
    if filtro_estatus != "Todos":
        filtrados = [t for t in filtrados if t.get("estatus") == filtro_estatus]
    if filtro_buscar.strip():
        q = filtro_buscar.strip().lower()
        filtrados = [
            t for t in filtrados
            if q in str(t.get("titulo", "")).lower()
            or q in str(t.get("solicitante", "")).lower()
        ]

    st.write(f"**{len(filtrados)} tickets**")

    for t in filtrados:
        tid   = t.get("id")
        titulo = t.get("titulo") or "(Sin título)"
        est   = t.get("estatus") or "Nuevo"
        solic = t.get("solicitante") or ""
        prio  = t.get("prioridad") or ""
        cat   = t.get("categoria") or ""

        with st.expander(f"#{tid} — {titulo} | {est} | {solic}"):
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                st.write(f"**Prioridad:** {prio}")
                st.write(f"**Categoría:** {cat}")
            with col_b:
                st.write(f"**Empresa:** {t.get('empresa','')}")
                st.write(f"**Departamento:** {t.get('departamento','')}")
            with col_c:
                st.write(f"**Correo:** {t.get('correo','')}")
                st.write(f"**Creado:** {str(t.get('created_at',''))[:10]}")

            st.write(f"**Descripción:** {t.get('descripcion','')}")

            nuevo_est = st.selectbox(
                "Cambiar estatus",
                ["Nuevo", "En Proceso", "Concluido", "Cancelado"],
                index=["Nuevo", "En Proceso", "Concluido", "Cancelado"].index(est) if est in ["Nuevo", "En Proceso", "Concluido", "Cancelado"] else 0,
                key=f"est_ticket_{tid}"
            )
            asignado = st.text_input("Asignado a", value=t.get("assigned_to") or "", key=f"asig_ticket_{tid}")
            comentario = st.text_area("Comentario interno", value=t.get("comentarios") or "", key=f"com_ticket_{tid}")

            if st.button("💾 Guardar cambios", key=f"save_ticket_{tid}"):
                try:
                    _update_ticket(tid, {
                        "estatus": nuevo_est,
                        "assigned_to": asignado,
                        "comentarios": comentario,
                    })
                    st.success("✅ Ticket actualizado.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al actualizar: {e}")


# ── Sección Complementarias ───────────────────────────────────────────────────

def _render_complementarias():
    section_header("📋", "Gestión de Complementarias", "Revisa y actualiza solicitudes de complementarias")

    comps = _get_complementarias()
    if not comps:
        alert("info", "No hay solicitudes de complementarias registradas.")
        return

    from collections import Counter
    conteo = Counter(c.get("estatus", "Pendiente") for c in comps)
    kpi_row([
        dict(icono="⏳", label="Pendientes",  valor=conteo.get("Pendiente", 0),   color="#1D4ED8"),
        dict(icono="🔍", label="En Revisión", valor=conteo.get("En revisión", 0), color="#D97706"),
        dict(icono="✅", label="Resueltas",   valor=conteo.get("Resuelto", 0),    color="#059669"),
        dict(icono="🚫", label="Canceladas",  valor=conteo.get("Cancelado", 0),   color="#DC2626"),
    ])

    col1, col2 = st.columns(2)
    with col1:
        filtro_est = st.selectbox(
            "Filtrar por estatus",
            ["Todos", "Pendiente", "En revisión", "Resuelto", "Cancelado"],
            key="gest_comp_estatus"
        )
    with col2:
        filtro_q = st.text_input("Buscar por tráfico o solicitante", key="gest_comp_buscar")

    filtrados = comps
    if filtro_est != "Todos":
        filtrados = [c for c in filtrados if c.get("estatus") == filtro_est]
    if filtro_q.strip():
        q = filtro_q.strip().lower()
        filtrados = [
            c for c in filtrados
            if q in str(c.get("numero_trafico", "")).lower()
            or q in str(c.get("solicitante", "")).lower()
        ]

    st.write(f"**{len(filtrados)} solicitudes**")

    ESTATUSES_COMP = ["Pendiente", "En revisión", "Resuelto", "Cancelado"]

    for c in filtrados:
        folio  = c.get("folio")
        trafico = c.get("numero_trafico") or ""
        est    = c.get("estatus") or "Pendiente"
        solic  = c.get("solicitante") or ""
        emp    = c.get("empresa") or ""

        with st.expander(f"#{folio} — {trafico} | {emp} | {est} | {solic}"):
            col_a, col_b = st.columns(2)
            with col_a:
                st.write(f"**Empresa:** {emp}")
                st.write(f"**Plataforma:** {c.get('plataforma','')}")
                st.write(f"**Tipo:** {c.get('tipo_complementaria','')}")
            with col_b:
                st.write(f"**Correo:** {c.get('correo','')}")
                st.write(f"**Fecha:** {str(c.get('fecha_captura',''))[:10]}")

            st.write(f"**Motivo:** {c.get('motivo_solicitud','')}")

            nuevo_est = st.selectbox(
                "Cambiar estatus",
                ESTATUSES_COMP,
                index=ESTATUSES_COMP.index(est) if est in ESTATUSES_COMP else 0,
                key=f"est_comp_{folio}"
            )
            comentario = st.text_area("Comentario", value=c.get("comentarios_auditoria") or "", key=f"com_comp_{folio}")

            if st.button("💾 Guardar cambios", key=f"save_comp_{folio}"):
                try:
                    _update_complementaria(folio, {
                        "estatus": nuevo_est,
                        "comentarios_auditoria": comentario,
                    })
                    st.success("✅ Solicitud actualizada.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al actualizar: {e}")


# ── Render principal ──────────────────────────────────────────────────────────

def render():
    page_banner("📊", "Seguimiento", "Gestión de tickets y solicitudes — vista de manager")

    u = current_user() or {}
    user_id = u.get("id") or u.get("sub") or ""

    if not user_id:
        alert("error", "Debes iniciar sesión.")
        return

    tiene_tickets = check_access(user_id, None, "tickets:manage")
    tiene_comp    = check_access(user_id, None, "complementarias:manage")

    if not tiene_tickets and not tiene_comp:
        alert("error", "No tienes permisos de gestión. Contacta al administrador.")
        return

    tabs_labels = []
    if tiene_tickets:
        tabs_labels.append("🎫 Tickets")
    if tiene_comp:
        tabs_labels.append("📋 Complementarias")

    tabs = st.tabs(tabs_labels)
    idx = 0

    if tiene_tickets:
        with tabs[idx]:
            _render_tickets()
        idx += 1

    if tiene_comp:
        with tabs[idx]:
            _render_complementarias()
