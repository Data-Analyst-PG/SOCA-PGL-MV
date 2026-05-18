# portal_app/modules/gestion_solicitudes/tickets.py
import streamlit as st
from collections import Counter
from ui.components import section_header, kpi_row, alert
from .shared import get_tickets, update_ticket, now_iso_utc

ESTATUSES = ["Nuevo", "En Proceso", "Concluido", "Cancelado"]


def render():
    section_header("🎫", "Gestión de Tickets",
                   "Administra y actualiza el estatus de los tickets")

    tickets = get_tickets()
    if not tickets:
        alert("info", "No hay tickets registrados.")
        return

    conteo = Counter(t.get("estatus", "Nuevo") for t in tickets)
    kpi_row([
        dict(icono="🆕", label="Nuevos",     valor=conteo.get("Nuevo", 0),      color="#1D4ED8"),
        dict(icono="⏳", label="En Proceso",  valor=conteo.get("En Proceso", 0), color="#D97706"),
        dict(icono="✅", label="Concluidos",  valor=conteo.get("Concluido", 0),  color="#059669"),
        dict(icono="🚫", label="Cancelados",  valor=conteo.get("Cancelado", 0),  color="#DC2626"),
    ])

    col1, col2 = st.columns(2)
    with col1:
        filtro_est = st.selectbox("Filtrar por estatus",
                                  ["Todos"] + ESTATUSES, key="gc_tick_est")
    with col2:
        filtro_q = st.text_input("Buscar título o solicitante", key="gc_tick_q")

    filtrados = tickets
    if filtro_est != "Todos":
        filtrados = [t for t in filtrados if t.get("estatus") == filtro_est]
    if filtro_q.strip():
        q = filtro_q.strip().lower()
        filtrados = [t for t in filtrados
                     if q in str(t.get("titulo", "")).lower()
                     or q in str(t.get("solicitante", "")).lower()]

    st.caption(f"{len(filtrados)} tickets")

    for t in filtrados:
        tid   = t.get("id")
        titulo = t.get("titulo", "(Sin título)")
        est   = t.get("estatus", "Nuevo")
        solic = t.get("solicitante", "")

        with st.expander(f"#{tid} — {titulo} | {est} | {solic}"):
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                st.write(f"**Prioridad:** {t.get('prioridad','')}")
                st.write(f"**Categoría:** {t.get('categoria','')}")
            with col_b:
                st.write(f"**Empresa:** {t.get('empresa','')}")
                st.write(f"**Departamento:** {t.get('departamento','')}")
            with col_c:
                st.write(f"**Correo:** {t.get('correo','')}")
                st.write(f"**Creado:** {str(t.get('created_at',''))[:10]}")
            st.write(f"**Descripción:** {t.get('descripcion','')}")

            nuevo_est = st.selectbox("Cambiar estatus", ESTATUSES,
                                     index=ESTATUSES.index(est) if est in ESTATUSES else 0,
                                     key=f"gc_est_t_{tid}")
            asignado  = st.text_input("Asignado a",
                                      value=t.get("assigned_to") or "",
                                      key=f"gc_asig_t_{tid}")
            comentario = st.text_area("Comentario interno",
                                      value=t.get("comentarios") or "",
                                      key=f"gc_com_t_{tid}")

            if st.button("💾 Guardar", key=f"gc_save_t_{tid}"):
                ok = update_ticket(tid, {
                    "estatus":      nuevo_est,
                    "assigned_to":  asignado,
                    "comentarios":  comentario,
                    "updated_at":   now_iso_utc(),
                })
                if ok:
                    st.success("✅ Actualizado.")
                    st.rerun()
                else:
                    st.error("Error al guardar.")
