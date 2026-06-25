# portal_app/modules/gestion_solicitudes/complementarias.py
# ─────────────────────────────────────────────────────────────────────────────
# Vista de GESTIÓN de complementarias (auditor / admin).
# Sin HTML propio — visual viene de ui/components.
# Modal nativo (@st.dialog) para edición.
#
# Estructura:
#   ① KPIs globales
#   ② Solicitudes ACTIVAS (Pendiente + En revisión) — cards editables
#   ③ Historial completo — tabla con filtros + descarga Excel
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations
from collections import Counter
from io import BytesIO

import pandas as pd
import streamlit as st

from ui.components import (
    section_header, kpi_row, alert,
    solicitud_card, historial_timeline, status_badge_html,
    solicitudes_table, page_banner,
)
from .shared import get_complementarias, update_complementaria, now_iso_utc

# ── Catálogos ─────────────────────────────────────────────────────────────────
ESTATUSES        = ["Pendiente", "En revisión", "Resuelto", "Cancelado"]
ESTATUSES_ACTIVOS = {"Pendiente", "En revisión"}

# Columnas para la tabla / Excel
COLS_TABLA = [
    ("folio",                  "Folio"),
    ("fecha_captura",          "Fecha captura"),
    ("empresa",                "Empresa"),
    ("sucursal",               "Sucursal"),
    ("plataforma",             "Plataforma"),
    ("solicitante",            "Solicitante"),
    ("correo",                 "Correo"),
    ("numero_trafico",         "Tráfico"),
    ("tipo_complementaria",    "Tipo"),
    ("tipo_motivo",            "Tipo de motivo"),
    ("estatus",                "Estatus"),
    ("auditor",                "Auditor"),
    ("fecha_resuelto",         "Fecha resolución"),
    ("comentarios_auditor",    "Comentarios auditor"),
]


# ── Excel ─────────────────────────────────────────────────────────────────────
def _to_excel(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Complementarias")
        ws = writer.sheets["Complementarias"]
        for col_cells in ws.columns:
            max_len = max(
                len(str(c.value)) if c.value is not None else 0
                for c in col_cells
            )
            ws.column_dimensions[col_cells[0].column_letter].width = min(max_len + 4, 50)
        from openpyxl.styles import Font, PatternFill, Alignment
        fill = PatternFill("solid", fgColor="1B2266")
        font = Font(color="FFFFFF", bold=True)
        for cell in ws[1]:
            cell.fill      = fill
            cell.font      = font
            cell.alignment = Alignment(horizontal="center", vertical="center")
    return buf.getvalue()


# ── Modal de edición ──────────────────────────────────────────────────────────
@st.dialog("Actualizar complementaria", width="large")
def _modal_edicion(comp: dict, gestor: str):
    folio = comp.get("folio")
    est   = comp.get("estatus", "Pendiente")
    badge = status_badge_html(est)
    tipo  = comp.get("tipo_complementaria", "")
    es_desconclusion = tipo == "Desconclusión"

    st.markdown(
        f"**Folio {int(folio):04d}** — {tipo}&nbsp;&nbsp;{badge}",
        unsafe_allow_html=True,
    )
    st.caption(
        f"Solicitante: {comp.get('solicitante','')}  |  "
        f"Tráfico: {comp.get('numero_trafico','—')}  |  "
        f"Capturada: {str(comp.get('fecha_captura',''))[:10]}"
    )

    col1, col2, col3 = st.columns(3)
    col1.markdown(f"**Empresa:** {comp.get('empresa','')}")
    col2.markdown(f"**Sucursal:** {comp.get('sucursal','')}")
    col3.markdown(f"**Plataforma:** {comp.get('plataforma','')}")

    st.divider()

    # ── Motivo ────────────────────────────────────────────────────────────────
    motivo = comp.get("motivo_solicitud", "")
    tipo_motivo = comp.get("tipo_motivo", "")
    if tipo_motivo:
        st.markdown(f"**Tipo de motivo:** {tipo_motivo}")
    if motivo:
        with st.expander("📄 Ver motivo de solicitud"):
            st.write(motivo)

    # ── Detalle del concepto ──────────────────────────────────────────────────
    if not es_desconclusion:
        st.divider()
        st.markdown("**📦 Detalle de la solicitud:**")

        def _fila(label, valor):
            if valor not in [None, "", "N/A", "Sin datos"]:
                st.markdown(f"- **{label}:** {valor}")

        if tipo == "Modificación":
            ca, cn = st.columns(2)
            with ca:
                st.markdown("**📝 Datos actuales**")
                _fila("Tipo concepto",  comp.get("tipo_concepto_actual"))
                _fila("Concepto",       comp.get("concepto_actual"))
                _fila("Proveedor",      comp.get("proveedor_actual"))
                _fila("Moneda",         comp.get("moneda_actual"))
                imp_a = comp.get("importe_actual")
                if imp_a is not None:
                    st.markdown(f"- **Importe:** ${float(imp_a):,.2f}")
                _fila("Tasa IVA",       comp.get("tasa_iva_actual"))
                _fila("Tasa Retención", comp.get("tasa_retencion_actual"))
                _fila("Retención ISR",  comp.get("retencion_isr_actual"))
                tot_a = comp.get("total_actual")
                if tot_a is not None:
                    st.markdown(f"- **Total calculado:** ${float(tot_a):,.2f}")
            with cn:
                st.markdown("**✅ Datos correctos**")
                _fila("Tipo concepto",  comp.get("tipo_concepto_nuevo"))
                _fila("Concepto",       comp.get("concepto_nuevo"))
                _fila("Proveedor",      comp.get("proveedor_nuevo"))
                _fila("Moneda",         comp.get("moneda_nuevo"))
                imp_n = comp.get("importe_nuevo")
                if imp_n is not None:
                    st.markdown(f"- **Importe:** ${float(imp_n):,.2f}")
                _fila("Tasa IVA",       comp.get("tasa_iva_nuevo"))
                _fila("Tasa Retención", comp.get("tasa_retencion_nuevo"))
                _fila("Retención ISR",  comp.get("retencion_isr_nuevo"))
                tot_n = comp.get("total_nuevo")
                if tot_n is not None:
                    st.markdown(f"- **Total calculado:** ${float(tot_n):,.2f}")
        else:
            # Agregar Concepto — solo lado nuevo
            st.markdown("**✅ Concepto a agregar**")
            _fila("Tipo concepto",  comp.get("tipo_concepto_nuevo"))
            _fila("Concepto",       comp.get("concepto_nuevo"))
            _fila("Proveedor",      comp.get("proveedor_nuevo"))
            _fila("Moneda",         comp.get("moneda_nuevo"))
            imp_n = comp.get("importe_nuevo")
            if imp_n is not None:
                st.markdown(f"- **Importe:** ${float(imp_n):,.2f}")
            _fila("Tasa IVA",       comp.get("tasa_iva_nuevo"))
            _fila("Tasa Retención", comp.get("tasa_retencion_nuevo"))
            _fila("Retención ISR",  comp.get("retencion_isr_nuevo"))
            tot_n = comp.get("total_nuevo")
            if tot_n is not None:
                st.markdown(f"- **Total calculado:** ${float(tot_n):,.2f}")

    st.divider()
    st.markdown("**📋 Historial:**")
    historial_timeline(comp.get("historial") or [])
    st.divider()

    st.markdown("**✏️ Registrar actualización:**")

    col_a, col_b = st.columns(2)
    with col_a:
        idx_est    = ESTATUSES.index(est) if est in ESTATUSES else 0
        nuevo_est  = st.selectbox("Nuevo estatus", ESTATUSES, index=idx_est, key=f"gc_comp_est_{folio}")
    with col_b:
        aud_actual = comp.get("auditor") or "Sin asignar"
        nuevo_aud  = gestor
        st.text_input("Auditor", value=gestor, disabled=True,
                      help="Se asigna automáticamente al usuario que gestiona la solicitud.")

    comentario = st.text_area(
        "Comentario del auditor",
        value=comp.get("comentarios_auditor") or "",
        placeholder="Observaciones, resolución, motivo de cancelación...",
        height=100,
        key=f"gc_comp_com_{folio}",
    )

    col_b1, col_b2 = st.columns([1, 3])
    with col_b1:
        guardar = st.button("💾 Guardar", type="primary", key=f"gc_comp_save_{folio}")
    with col_b2:
        if st.button("✖️ Cancelar", key=f"gc_comp_cancel_{folio}"):
            st.rerun()

    if guardar:
        cambios_texto = []
        if nuevo_est != est:
            cambios_texto.append(f"Estatus: {est} → {nuevo_est}")
        if nuevo_aud != aud_actual:
            cambios_texto.append(f"Auditor: {aud_actual} → {nuevo_aud}")
        if comentario.strip() != (comp.get("comentarios_auditor") or "").strip():
            cambios_texto.append(f"Comentario actualizado")

        if not cambios_texto:
            st.warning("No hay cambios que guardar.")
            return

        now = now_iso_utc()
        historial = list(comp.get("historial") or [])
        historial.append({
            "at":      now,
            "by":      gestor,
            "action":  "update",
            "details": " | ".join(cambios_texto),
        })

        changes = {
            "fecha_ultima_modificacion": now,
            "auditor":               nuevo_aud,
            "comentarios_auditor":   comentario.strip(),
            "historial":             historial,
        }
        if nuevo_est != est:
            changes["estatus"] = nuevo_est
            if nuevo_est == "Resuelto":
                changes["fecha_resuelto"] = now[:10]

        if update_complementaria(folio, changes):
            st.success("✅ Cambios guardados.")
            st.cache_data.clear()
            st.rerun()


# ── Render principal ──────────────────────────────────────────────────────────
def render():
    page_banner("📋", "Gestión de Complementarias",
                   "Revisa y actualiza solicitudes de complementarias")

    perfil = st.session_state.get("user_profile") or {}
    from services.supabase_client import current_user
    u      = current_user() or {}
    gestor = perfil.get("full_name") or u.get("email", "Auditor")

    comps = get_complementarias()
    if not comps:
        alert("info", "No hay solicitudes registradas.")
        return

    # ── ① KPIs ───────────────────────────────────────────────────────────────
    conteo = Counter(c.get("estatus", "Pendiente") for c in comps)
    kpi_row([
        dict(icono="🕐", label="Pendientes",
             valor=conteo.get("Pendiente", 0), color="#1D4ED8"),
        dict(icono="🔍", label="En revisión",
             valor=conteo.get("En revisión", 0), color="#D97706"),
        dict(icono="✅", label="Resueltas",
             valor=conteo.get("Resuelto", 0), color="#059669"),
        dict(icono="🚫", label="Canceladas",
             valor=conteo.get("Cancelado", 0), color="#DC2626"),
    ])

    st.divider()

    # ── Abrir modal si hay selección ──────────────────────────────────────────
    if "gc_comp_modal_folio" in st.session_state:
        folio_sel = st.session_state.pop("gc_comp_modal_folio")
        comp_sel  = next((c for c in comps if c.get("folio") == folio_sel), None)
        if comp_sel:
            _modal_edicion(comp_sel, gestor)

    # ── ② ACTIVAS ─────────────────────────────────────────────────────────────
    activas = [c for c in comps if c.get("estatus", "Pendiente") in ESTATUSES_ACTIVOS]

    if activas:
        st.markdown(f"#### 🔄 Solicitudes activas ({len(activas)})")
        for c in activas:
            folio = c.get("folio", "")
            est   = c.get("estatus", "Pendiente")
            fecha = str(c.get("fecha_captura", ""))[:10]

            meta = [
                ("🏢", c.get("empresa", "")),
                ("🔖", c.get("tipo_complementaria", "")),
                ("📋", f"Tráfico: {c.get('numero_trafico','—')}"),
                ("👤 Sol.", c.get("solicitante", "")),
                ("🔍", c.get("auditor") or "Sin asignar"),
            ]

            clicked = solicitud_card(
                id_label=f"Folio {int(folio):04d}" if folio else "—",
                titulo=c.get("tipo_complementaria") or "(Sin tipo)",
                fecha=fecha,
                estatus=est,
                meta=meta,
                on_edit_key=f"gc_comp_open_{folio}",
            )
            if clicked:
                st.session_state["gc_comp_modal_folio"] = folio
                st.rerun()
    else:
        st.info("No hay solicitudes activas en este momento. ✅")

    st.divider()

    # ── ③ HISTORIAL COMPLETO ──────────────────────────────────────────────────
    st.markdown("#### 📋 Historial completo")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        filtro_est = st.selectbox(
            "Estatus", ["Todos"] + ESTATUSES, key="gc_comp_h_est"
        )
    with col2:
        todas_emp = ["Todas"] + sorted(set(
            c.get("empresa", "") for c in comps if c.get("empresa")
        ))
        filtro_emp = st.selectbox("Empresa", todas_emp, key="gc_comp_h_emp")
    with col3:
        filtro_desde = st.date_input("Desde", value=None, key="gc_comp_h_desde")
    with col4:
        filtro_q = st.text_input(
            "Tráfico o solicitante", placeholder="Buscar...", key="gc_comp_h_q"
        )

    filtrados = list(comps)
    if filtro_est != "Todos":
        filtrados = [c for c in filtrados if c.get("estatus") == filtro_est]
    if filtro_emp != "Todas":
        filtrados = [c for c in filtrados if c.get("empresa", "") == filtro_emp]
    if filtro_desde:
        filtrados = [
            c for c in filtrados
            if str(c.get("fecha_captura", ""))[:10] >= str(filtro_desde)
        ]
    if filtro_q.strip():
        q = filtro_q.strip().lower()
        filtrados = [
            c for c in filtrados
            if q in str(c.get("numero_trafico", "")).lower()
            or q in str(c.get("solicitante", "")).lower()
        ]

    st.caption(f"Mostrando {len(filtrados)} de {len(comps)} solicitud(es)")

    if filtrados:
        df = pd.DataFrame([
            {label: c.get(col, "") for col, label in COLS_TABLA}
            for c in filtrados
        ])
        for fecha_col in ["Fecha captura", "Fecha resolución"]:
            if fecha_col in df.columns:
                df[fecha_col] = df[fecha_col].astype(str).str[:10]

        solicitudes_table(df)

        excel_bytes = _to_excel(df)
        st.download_button(
            "⬇️ Descargar Excel",
            data=excel_bytes,
            file_name="complementarias.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="gc_comp_dl_excel",
        )
    else:
        st.info("No hay resultados con los filtros aplicados.")
