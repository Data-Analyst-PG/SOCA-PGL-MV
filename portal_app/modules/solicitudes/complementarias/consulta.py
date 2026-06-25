# portal_app/modules/solicitudes/complementarias/consulta.py
# ─────────────────────────────────────────────────────────────────────────────
# Vista "Mis Complementarias" para el usuario final.
# Homologada visualmente con el módulo de tickets.
# Sin HTML propio — visual viene de ui/components.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations
from io import BytesIO

import pandas as pd
import streamlit as st

from services.supabase_client import current_user
from ui.components import (
    section_header, kpi_row, alert,
    solicitud_card, historial_timeline, status_badge_html,
    solicitudes_table,
)
from .shared import get_supabase_client

ESTATUSES_ACTIVOS = {"Pendiente", "En revisión"}

COLS_TABLA = [
    ("folio",               "Folio"),
    ("fecha_captura",       "Fecha captura"),
    ("empresa",             "Empresa"),
    ("sucursal",            "Sucursal"),
    ("numero_trafico",      "Tráfico"),
    ("tipo_complementaria", "Tipo"),
    ("tipo_motivo",         "Tipo de motivo"),
    ("estatus",             "Estatus"),
    ("auditor",             "Auditor"),
    ("fecha_resuelto",      "Fecha resolución"),
]


# ── Query ─────────────────────────────────────────────────────────────────────
_ADMIN_PREVIEW_EMAILS = {"data_analyst@palosgarza.com"}

@st.cache_data(ttl=30, show_spinner=False)
def _mis_complementarias(user_email: str, limite: int = 200) -> list:
    try:
        sb  = get_supabase_client()
        q   = sb.table("solicitudes_complementarias").select(
            "folio,fecha_captura,empresa,sucursal,plataforma,solicitante,correo,"
            "numero_trafico,tipo_complementaria,tipo_motivo,motivo_solicitud,estatus,"
            "fecha_ultima_modificacion,fecha_resuelto,auditor,"
            "comentarios_auditor,historial"
        )
        if user_email not in _ADMIN_PREVIEW_EMAILS:
            q = q.ilike("correo", user_email)
        res = q.order("folio", desc=True).limit(limite).execute()
        return res.data or []
    except Exception:
        return []


# ── Modal de detalle (solo lectura) ──────────────────────────────────────────
@st.dialog("Detalle de complementaria", width="large")
def _modal_detalle(comp: dict):
    import urllib.parse
    from datetime import datetime

    folio = comp.get("folio", "")
    est   = comp.get("estatus", "Pendiente")
    tipo  = comp.get("tipo_complementaria", "")
    badge = status_badge_html(est)

    st.markdown(
        f"**Folio {int(folio):04d}** — {tipo}&nbsp;&nbsp;{badge}",
        unsafe_allow_html=True,
    )
    col1, col2, col3 = st.columns(3)
    col1.markdown(f"**👤 Solicitante:** {comp.get('solicitante','')}")
    col2.markdown(f"**🚛 Tráfico:** {comp.get('numero_trafico','—')}")
    col3.markdown(f"**📅 Capturada:** {str(comp.get('fecha_captura',''))[:10]}")
    st.caption(
        f"🏢 {comp.get('empresa','')}  |  "
        f"📍 {comp.get('sucursal','')}  |  "
        f"💻 {comp.get('plataforma','')}"
    )

    st.divider()

    tipo_mot = comp.get("tipo_motivo","")
    motivo   = comp.get("motivo_solicitud","")
    if tipo_mot:
        st.markdown(f"**Tipo de motivo:** {tipo_mot}")
    if motivo:
        st.markdown(f"**Motivo de la solicitud:** {motivo}")

    col4, col5 = st.columns(2)
    col4.markdown(f"**Auditor:** {comp.get('auditor') or 'Sin asignar'}")
    fecha_res = str(comp.get("fecha_resuelto",""))[:10] if comp.get("fecha_resuelto") else "Pendiente"
    col5.markdown(f"**Fecha resolución:** {fecha_res}")

    com_aud = comp.get("comentarios_auditor","")
    if com_aud:
        st.info(f"💬 **Comentario del auditor:** {com_aud}")

    st.divider()
    st.markdown("**📋 Historial:**")
    historial_timeline(comp.get("historial") or [])

    # ── Reenviar correo ───────────────────────────────────────────────────────
    st.divider()
    folio_fmt    = f"{int(folio):04d}"
    empresa      = comp.get("empresa","")
    trafico      = comp.get("numero_trafico","")
    solicitante  = comp.get("solicitante","")
    correo_sol   = comp.get("correo","")
    plataforma   = comp.get("plataforma","")
    sucursal     = comp.get("sucursal","")

    destinatarios = (
        ["julieta.reyna@palosgarza.com", "e-invoicing@palosgarza.com"]
        if tipo == "Desconclusión"
        else ["auditoria.operaciones@palosgarza.com"]
    )
    subject = f"Complementaria #{folio_fmt} | {empresa} | Tráfico {trafico}"
    body = (
        f"Fecha: {datetime.now().strftime('%d/%m/%Y')}\n"
        f"Folio: #{folio_fmt}\nTráfico: {trafico}\n"
        f"Solicitó: {solicitante}\nCorreo: {correo_sol}\n"
        f"Empresa: {empresa}\nSucursal: {sucursal or 'N/A'}\n"
        f"Plataforma: {plataforma}\nTipo: {tipo}\n"
        f"\nMi folio de complementaria es el '#{folio_fmt}', favor de atender mi solicitud."
    )
    mailto = "mailto:{}?subject={}&body={}".format(
        urllib.parse.quote(",".join(destinatarios)),
        urllib.parse.quote(subject),
        urllib.parse.quote(body),
    )
    st.markdown(f"📧 ¿No enviaste el correo? [**Reenviar notificación**]({mailto})")


# ── Render principal ──────────────────────────────────────────────────────────
def render():
    u = current_user()
    if not u:
        alert("error", "Debes iniciar sesión para consultar complementarias.")
        st.stop()

    user_email = (u.get("email") or "").strip().lower()

    section_header("🔎", "Mis complementarias",
                   "Consulta el estado de tus solicitudes")

    col_lim, _ = st.columns([1, 3])
    with col_lim:
        limite = st.selectbox("Límite", [50, 100, 200, 500], index=1, key="ccomp_lim")

    rows = _mis_complementarias(user_email, int(limite))

    # ── KPIs ─────────────────────────────────────────────────────────────────
    counts: dict[str, int] = {}
    for r in rows:
        s = r.get("estatus", "Pendiente")
        counts[s] = counts.get(s, 0) + 1

    kpi_row([
        dict(icono="🕐", label="Pendientes",
             valor=counts.get("Pendiente", 0), color="#1D4ED8"),
        dict(icono="🔍", label="En revisión",
             valor=counts.get("En revisión", 0), color="#D97706"),
        dict(icono="✅", label="Resueltas",
             valor=counts.get("Resuelto", 0), color="#059669"),
        dict(icono="🚫", label="Canceladas",
             valor=counts.get("Cancelado", 0), color="#DC2626"),
    ])

    if not rows:
        alert("info", "No se encontraron complementarias para tu correo.")
        return

    st.divider()

    # ── Filtros ───────────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        estatuses_pres = sorted(set(r.get("estatus","Pendiente") for r in rows))
        filtro_est = st.selectbox("Estatus", ["Todos"] + estatuses_pres, key="ccomp_est")
    with col2:
        filtro_q = st.text_input(
            "Buscar tráfico o tipo",
            placeholder="Ej. SEP03873/25",
            key="ccomp_q",
        )
    with col3:
        orden = st.selectbox("Ordenar", ["Más recientes","Más antiguos"], key="ccomp_ord")

    filtrados = list(rows)
    if filtro_est != "Todos":
        filtrados = [r for r in filtrados if r.get("estatus") == filtro_est]
    if filtro_q.strip():
        q = filtro_q.strip().lower()
        filtrados = [r for r in filtrados
                     if q in str(r.get("numero_trafico","")).lower()
                     or q in str(r.get("tipo_complementaria","")).lower()]
    if orden == "Más antiguos":
        filtrados = list(reversed(filtrados))

    st.caption(f"Mostrando {len(filtrados)} resultado(s)")

    # ── Abrir modal si hay selección ──────────────────────────────────────────
    if "ccomp_modal_folio" in st.session_state:
        folio_sel = st.session_state.pop("ccomp_modal_folio")
        comp_sel  = next((r for r in rows if r.get("folio") == folio_sel), None)
        if comp_sel:
            _modal_detalle(comp_sel)

    # ── Cards activas primero, luego cerradas ─────────────────────────────────
    activas  = [r for r in filtrados if r.get("estatus") in ESTATUSES_ACTIVOS]
    cerradas = [r for r in filtrados if r.get("estatus") not in ESTATUSES_ACTIVOS]

    for grupo in [activas, cerradas]:
        for r in grupo:
            folio = r.get("folio","")
            est   = r.get("estatus","Pendiente")
            fecha = str(r.get("fecha_captura",""))[:10]

            meta = [
                ("🏢", r.get("empresa","")),
                ("🔖", r.get("tipo_complementaria","")),
                ("📋", f"Tráfico: {r.get('numero_trafico','—')}"),
                ("👤 Auditor:", r.get("auditor") or "Sin asignar"),
            ]

            clicked = solicitud_card(
                id_label=f"Folio {int(folio):04d}" if folio else "—",
                titulo=r.get("tipo_complementaria") or "(Sin tipo)",
                fecha=fecha,
                estatus=est,
                meta=meta,
                on_edit_key=f"ccomp_open_{folio}",
            )
            if clicked:
                st.session_state["ccomp_modal_folio"] = folio
                st.rerun()

    # ── Tabla + descarga (todas las filtradas) ────────────────────────────────
    if filtrados:
        st.divider()
        st.markdown("#### 📊 Resumen descargable")

        df = pd.DataFrame([
            {label: r.get(col,"") for col, label in COLS_TABLA}
            for r in filtrados
        ])
        for fecha_col in ["Fecha captura","Fecha resolución"]:
            if fecha_col in df.columns:
                df[fecha_col] = df[fecha_col].astype(str).str[:10]

        solicitudes_table(df)

        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Complementarias")
        st.download_button(
            "⬇️ Descargar Excel",
            data=buf.getvalue(),
            file_name="mis_complementarias.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="ccomp_dl_excel",
        )
