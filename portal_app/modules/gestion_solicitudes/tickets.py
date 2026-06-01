# portal_app/modules/gestion_solicitudes/tickets.py
# ─────────────────────────────────────────────────────────────────────────────
# Vista de GESTIÓN de tickets (admin / equipo de análisis).
# Sin HTML propio — visual viene de ui/components.
# Modal nativo de Streamlit (@st.dialog) para edición.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from services.supabase_client import current_user, get_authed_client
from ui.components import (
    section_header, kpi_row, alert,
    solicitud_card, historial_timeline, status_badge_html,
)

# ── Catálogos ─────────────────────────────────────────────────────────────────
FASES = ["Nuevo", "Capacitación", "Planteamiento", "Desarrollo",
         "Pruebas", "Entrega", "Concluido", "Cancelado"]
FASES_EN_PROCESO = {"Capacitación", "Planteamiento", "Desarrollo", "Pruebas", "Entrega", "En Proceso"}
ANALYSTS = ["Sin asignar", "Abel", "Sasha", "Adrian", "Heidi"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _gestor_nombre() -> str:
    """Nombre del usuario gestor logueado."""
    u = current_user() or {}
    perfil = st.session_state.get("profile") or {}
    return perfil.get("full_name") or u.get("email", "Gestor")


# ── Query ─────────────────────────────────────────────────────────────────────
def _get_tickets(limit: int = 500) -> list:
    try:
        sb = get_authed_client()
        res = (
            sb.table("tickets")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []
    except Exception:
        return []


def _update_ticket(ticket_id: int, changes: dict) -> bool:
    try:
        get_authed_client().table("tickets").update(changes).eq("id", ticket_id).execute()
        return True
    except Exception as e:
        st.error(f"Error al guardar: {e}")
        return False


# ── Modal de edición ──────────────────────────────────────────────────────────
@st.dialog("Actualizar ticket", width="large")
def _modal_edicion(ticket: dict, gestor: str):
    tid   = ticket.get("id")
    est   = ticket.get("estatus", "Nuevo")
    badge = status_badge_html(est)

    # Encabezado del modal
    st.markdown(
        f"**#{tid}** — {ticket.get('titulo','')}&nbsp;&nbsp;{badge}",
        unsafe_allow_html=True,
    )
    st.caption(
        f"Solicitante: {ticket.get('solicitante','')}  |  "
        f"Creado: {str(ticket.get('created_at',''))[:10]}"
    )

    # Info de contexto
    col1, col2, col3 = st.columns(3)
    col1.markdown(f"**Empresa:** {ticket.get('empresa','')}")
    col2.markdown(f"**Categoría:** {ticket.get('categoria','')}")
    col3.markdown(f"**Departamento:** {ticket.get('departamento','')}")

    desc = ticket.get("descripcion", "")
    if desc:
        with st.expander("Ver descripción original"):
            st.write(desc)

    st.divider()

    # Historial
    st.markdown("**📋 Historial:**")
    historial_timeline(ticket.get("historial") or [])

    st.divider()

    # Formulario de actualización
    st.markdown("**✏️ Registrar actualización:**")

    col_a, col_b = st.columns(2)
    with col_a:
        idx_est = FASES.index(est) if est in FASES else 0
        nueva_fase = st.selectbox("Nueva fase / estatus", FASES, index=idx_est, key=f"md_fase_{tid}")
    with col_b:
        asig_actual = ticket.get("assigned_to", "Sin asignar")
        idx_asig = ANALYSTS.index(asig_actual) if asig_actual in ANALYSTS else 0
        nuevo_asig = st.selectbox("Asignado a", ANALYSTS, index=idx_asig, key=f"md_asig_{tid}")

    comentario = st.text_area(
        "Comentario / nota de esta actualización",
        placeholder="Describe el avance, acuerdo o ajuste...",
        height=110,
        key=f"md_com_{tid}",
    )

    col_btn1, col_btn2 = st.columns([1, 3])
    with col_btn1:
        guardar = st.button("💾 Guardar", type="primary", key=f"md_save_{tid}")
    with col_btn2:
        if st.button("✖️ Cancelar", key=f"md_cancel_{tid}"):
            st.rerun()

    if guardar:
        cambios_texto = []
        if nueva_fase != est:
            cambios_texto.append(f"Fase: {est} → {nueva_fase}")
        if nuevo_asig != asig_actual:
            cambios_texto.append(f"Asignado: {asig_actual} → {nuevo_asig}")
        if comentario.strip():
            cambios_texto.append(f"Comentario: {comentario.strip()}")

        if not cambios_texto:
            st.warning("No hay cambios que guardar.")
            return

        now        = _now()
        historial  = list(ticket.get("historial") or [])
        action_type = "comment" if comentario.strip() and nueva_fase == est else "fase"

        historial.append({
            "at":      now,
            "by":      gestor,
            "action":  action_type,
            "details": " | ".join(cambios_texto),
        })

        changes = {
            "updated_at":  now,
            "updated_by":  gestor,
            "historial":   historial,
            "assigned_to": nuevo_asig,
        }
        if nueva_fase != est:
            changes["estatus"] = nueva_fase

        if _update_ticket(tid, changes):
            st.success("✅ Cambios guardados correctamente.")
            st.cache_data.clear()
            st.rerun()


# ── Render principal ──────────────────────────────────────────────────────────
def render():
    section_header("🎫", "Gestión de Tickets",
                   "Administra fases, asignaciones y comentarios de los tickets")

    gestor  = _gestor_nombre()
    tickets = _get_tickets()

    if not tickets:
        alert("info", "No hay tickets registrados.")
        return

    # ── KPIs ─────────────────────────────────────────────────────────────────
    conteo = Counter(t.get("estatus", "Nuevo") for t in tickets)
    kpi_row([
        dict(icono="🆕", label="Nuevos",
             valor=conteo.get("Nuevo", 0), color="#1D4ED8"),
        dict(icono="⏳", label="En proceso",
             valor=sum(conteo.get(f, 0) for f in FASES_EN_PROCESO), color="#D97706"),
        dict(icono="✅", label="Concluidos",
             valor=conteo.get("Concluido", 0), color="#059669"),
        dict(icono="🚫", label="Cancelados",
             valor=conteo.get("Cancelado", 0), color="#DC2626"),
    ])

    # ── Filtros ───────────────────────────────────────────────────────────────
    col1, col2 = st.columns(2)
    with col1:
        filtro_est = st.selectbox("Fase / estatus", ["Todos"] + FASES, key="gc_tick_est")
    with col2:
        filtro_q = st.text_input("Buscar título o solicitante", key="gc_tick_q")

    # ── Descarga ──────────────────────────────────────────────────────────────
    cols_exp = ["id","created_at","updated_at","solicitante","correo",
                "empresa","titulo","categoria","departamento","prioridad",
                "estatus","assigned_to","descripcion"]
    df = pd.DataFrame([{c: t.get(c,"") for c in cols_exp} for t in tickets])
    st.download_button("⬇️ Descargar CSV", data=df.to_csv(index=False).encode(),
                       file_name="tickets.csv", mime="text/csv", key="gc_tick_dl")

    # ── Aplicar filtros ───────────────────────────────────────────────────────
    filtrados = list(tickets)
    if filtro_est != "Todos":
        filtrados = [t for t in filtrados if t.get("estatus") == filtro_est]
    if filtro_q.strip():
        q = filtro_q.strip().lower()
        filtrados = [t for t in filtrados
                     if q in str(t.get("titulo","")).lower()
                     or q in str(t.get("solicitante","")).lower()]

    st.caption(f"{len(filtrados)} ticket(s)")
    st.divider()

    # ── Abrir modal si hay ticket seleccionado ────────────────────────────────
    if "gc_modal_id" in st.session_state:
        tid_sel = st.session_state.pop("gc_modal_id")
        ticket_sel = next((t for t in tickets if t.get("id") == tid_sel), None)
        if ticket_sel:
            _modal_edicion(ticket_sel, gestor)

    # ── Cards ─────────────────────────────────────────────────────────────────
    for t in filtrados:
        tid   = t.get("id")
        est   = t.get("estatus", "Nuevo")
        fecha = str(t.get("created_at", ""))[:10]

        meta = [
            ("🏢", t.get("empresa", "")),
            ("📂", t.get("categoria", "")),
            ("👤 Sol.", t.get("solicitante", "")),
            ("🔧", t.get("assigned_to", "Sin asignar")),
        ]

        clicked = solicitud_card(
            id_label=f"#{tid}",
            titulo=t.get("titulo", "(Sin título)"),
            fecha=fecha,
            estatus=est,
            meta=meta,
            on_edit_key=f"gc_open_{tid}",
        )
        if clicked:
            st.session_state["gc_modal_id"] = tid
            st.rerun()
