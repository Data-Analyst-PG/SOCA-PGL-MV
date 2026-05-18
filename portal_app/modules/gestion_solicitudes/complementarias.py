# portal_app/modules/gestion_solicitudes/complementarias.py
import streamlit as st
from collections import Counter
from ui.components import section_header, kpi_row, alert
from .shared import get_complementarias, update_complementaria

ESTATUSES = ["Pendiente", "En revisión", "Resuelto", "Cancelado"]


def render():
    section_header("📋", "Gestión de Complementarias",
                   "Revisa y actualiza solicitudes de complementarias")

    comps = get_complementarias()
    if not comps:
        alert("info", "No hay solicitudes registradas.")
        return

    conteo = Counter(c.get("estatus", "Pendiente") for c in comps)
    kpi_row([
        dict(icono="⏳", label="Pendientes",  valor=conteo.get("Pendiente", 0),   color="#1D4ED8"),
        dict(icono="🔍", label="En Revisión", valor=conteo.get("En revisión", 0), color="#D97706"),
        dict(icono="✅", label="Resueltas",   valor=conteo.get("Resuelto", 0),    color="#059669"),
        dict(icono="🚫", label="Canceladas",  valor=conteo.get("Cancelado", 0),   color="#DC2626"),
    ])

    col1, col2 = st.columns(2)
    with col1:
        filtro_est = st.selectbox("Filtrar por estatus",
                                  ["Todos"] + ESTATUSES, key="gc_comp_est")
    with col2:
        filtro_q = st.text_input("Buscar tráfico o solicitante", key="gc_comp_q")

    filtrados = comps
    if filtro_est != "Todos":
        filtrados = [c for c in filtrados if c.get("estatus") == filtro_est]
    if filtro_q.strip():
        q = filtro_q.strip().lower()
        filtrados = [c for c in filtrados
                     if q in str(c.get("numero_trafico", "")).lower()
                     or q in str(c.get("solicitante", "")).lower()]

    st.caption(f"{len(filtrados)} solicitudes")

    for c in filtrados:
        folio  = c.get("folio")
        trafico = c.get("numero_trafico", "")
        est    = c.get("estatus", "Pendiente")
        solic  = c.get("solicitante", "")
        emp    = c.get("empresa", "")

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

            nuevo_est = st.selectbox("Cambiar estatus", ESTATUSES,
                                     index=ESTATUSES.index(est) if est in ESTATUSES else 0,
                                     key=f"gc_est_c_{folio}")
            comentario = st.text_area("Comentario",
                                      value=c.get("comentarios_auditoria") or "",
                                      key=f"gc_com_c_{folio}")

            if st.button("💾 Guardar", key=f"gc_save_c_{folio}"):
                ok = update_complementaria(folio, {
                    "estatus": nuevo_est,
                    "comentarios_auditoria": comentario,
                })
                if ok:
                    st.success("✅ Actualizado.")
                    st.rerun()
                else:
                    st.error("Error al guardar.")
