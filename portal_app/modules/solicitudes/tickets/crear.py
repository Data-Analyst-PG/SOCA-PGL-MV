# portal_app/modules/solicitudes/tickets/crear.py
import streamlit as st

from services.supabase_client import current_user, get_authed_client
from ui.components import section_header, alert
from services.notificaciones import enviar_notificacion
from .shared import (
    add_ticket,
    build_mailto,
    now_iso_utc,
    TICKET_NOTIFICATION_EMAILS,
    log_accion,
)

EMPRESAS      = ["Picus", "Igloo", "Set Freight", "Lincoln Freight", "Set Logis Plus"]
CATEGORIAS    = ["Cotizadores", "Complementarias", "SPGC", "App Eq. Matto",
                 "Tickets", "Nuevo Desarrollo"]
DEPARTAMENTOS = ["Operaciones", "Contabilidad", "Auditoria", "Matto",
                 "Safety", "Monitoreo", "Fac & Cob", "Liquidaciones", "Control de Diesel", "Otro"]
PRIORIDADES   = ["Normal", "Alta", "Urgente"]


def _get_profile_name(user_id: str) -> str:
    if not user_id:
        return ""
    try:
        res = (
            get_authed_client()
            .table("profiles")
            .select("full_name")
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        return (res.data or {}).get("full_name") or ""
    except Exception:
        return ""


def render():
    section_header("🎫", "Crear Ticket",
                   "Envía una solicitud al equipo de Análisis de Datos")

    u = current_user()
    if not u:
        alert("error", "Debes iniciar sesión para crear tickets.")
        st.stop()

    user_id        = u.get("id") or u.get("sub") or ""
    nombre_usuario = _get_profile_name(user_id)
    correo_usuario = (u.get("email") or "").strip().lower()

    with st.form("ticket_form", clear_on_submit=True):
        colA, colB, colC = st.columns([1, 1, 1])
        with colA:
            solicitante = st.text_input(
                "Nombre solicitante*",
                value=nombre_usuario,
                disabled=bool(nombre_usuario),
                placeholder="Tu nombre",
                help="Detectado automáticamente desde tu cuenta." if nombre_usuario
                     else "Escribe tu nombre completo.",
            )
        with colB:
            correo = st.text_input(
                "Correo*", value=correo_usuario, disabled=True,
                help="Detectado automáticamente desde tu cuenta.",
            )
        with colC:
            empresa = st.selectbox("Empresa*", EMPRESAS, index=0)

        col1, col2, col3 = st.columns(3)
        with col1:
            prioridad   = st.selectbox("Prioridad", PRIORIDADES, index=0)
        with col2:
            categoria   = st.selectbox("Categoría*", CATEGORIAS, index=0)
        with col3:
            departamento = st.selectbox("Departamento*", DEPARTAMENTOS, index=0)

        titulo      = st.text_input("Título*",
                                    placeholder="Ej. Reporte de ventas por sucursal")
        descripcion = st.text_area(
            "Descripción*", height=170,
            placeholder="Objetivo, alcance, fecha límite, filtros, ejemplo, etc.",
        )
        submit = st.form_submit_button("Crear ticket", type="primary")

    if not submit:
        return

    # ── Validaciones ──────────────────────────────────────────────────────────
    errores = []
    if not solicitante.strip(): errores.append("Falta nombre solicitante.")
    if not empresa:             errores.append("Falta empresa.")
    if not categoria:           errores.append("Falta categoría.")
    if not departamento:        errores.append("Falta departamento.")
    if not titulo.strip():      errores.append("Falta título.")
    if not descripcion.strip(): errores.append("Falta descripción.")

    if errores:
        for e in errores:
            st.error(e)
        st.stop()

    # ── Insertar ──────────────────────────────────────────────────────────────
    now = now_iso_utc()
    payload = {
        "created_at":   now,
        "updated_at":   now,
        "updated_by":   solicitante.strip(),
        "solicitante":  solicitante.strip(),
        "correo":       correo_usuario,
        "empresa":      empresa,
        "categoria":    categoria,
        "departamento": departamento,
        "prioridad":    prioridad,
        "titulo":       titulo.strip(),
        "descripcion":  descripcion.strip(),
        "estatus":      "Nuevo",
        "assigned_to":  "Sin asignar",
        "comentarios":  "",
        "historial": [{
            "at": now, "by": solicitante.strip(),
            "action": "create", "details": "ticket creado",
        }],
    }

    try:
        created   = add_ticket(payload)
        ticket_id = created.get("id")
        log_accion("crear_solicitud", {"ticket_id": ticket_id})
    except Exception as e:
        st.error(f"No se pudo crear el ticket: {e}")
        st.stop()

    # ── Notificación automática por correo ────────────────────────────────────
    folio_fmt = f"{int(ticket_id):04d}"

    resultado_correo = enviar_notificacion(
        modulo="tickets",
        evento="ticket_creado",
        folio=folio_fmt,
        datos={
            "solicitante": payload["solicitante"],
            "empresa": payload["empresa"],
            "categoria": payload["categoria"],
            "departamento": payload["departamento"],
            "prioridad": payload["prioridad"],
            "titulo": payload["titulo"],
            "descripcion": payload["descripcion"],
        },
        correo_solicitante=payload["correo"],
    )

    st.success(f"✅ Ticket **#{folio_fmt}** creado exitosamente.")
    if resultado_correo.get("ok"):
        st.info("📧 Se envió la notificación por correo automáticamente.")
    else:
        st.warning("⚠️ El ticket se guardó, pero la notificación por correo no pudo enviarse.")
