# portal_app/modules/solicitudes/tickets/consultar.py
import streamlit as st

from ui.components import section_header, kpi_row
from .shared import init_store, list_tickets, counts_by_status


def render():
    init_store()

    section_header("🎫", "Mis tickets",
                   "Consulta el estado de tus solicitudes")

    counts = counts_by_status()

    kpi_row([
        dict(icono="🆕", label="Nuevos",
             valor=counts.get("Nuevo", 0),     sub="", color="#1D4ED8"),
        dict(icono="⏳", label="En proceso",
             valor=counts.get("En Proceso", 0), sub="", color="#D97706"),
        dict(icono="🚫", label="Cancelados",
             valor=counts.get("Cancelado", 0),  sub="", color="#DC2626"),
        dict(icono="✅", label="Concluidos",
             valor=counts.get("Concluido", 0),  sub="", color="#059669"),
    ])

    st.divider()

    st.markdown("**Filtrar por correo**")
    q = st.text_input("Correo", placeholder="tu@correo.com", label_visibility="collapsed")

    tickets = list_tickets()
    if q.strip():
        qq = q.strip().lower()
        tickets = [t for t in tickets if str(t.get("correo", "")).strip().lower() == qq]

    if not tickets:
        st.info("No se encontraron tickets con ese correo.")
        return

    st.write(f"**Resultados:** {len(tickets)}")
    st.dataframe(list(reversed(tickets)), use_container_width=True, hide_index=True)
