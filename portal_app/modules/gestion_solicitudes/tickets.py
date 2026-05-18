from ui.components import page_banner, section_header, alert, divider
import io
import pandas as pd
import streamlit as st
from services.supabase_client import current_user
from services.authz import role

from .shared import (
    init_store,
    list_tickets,
    get_ticket,
    update_ticket,
    STATUSES,
    ANALYSTS,
    get_secret,
)



def _stat_card(col, titulo: str, valor: str, color: str, icono: str):
    """Infocard estilo Minimart: fondo blanco, borde izquierdo de color, número grande."""
    colores = {
        "blue":   "#1D4ED8",
        "yellow": "#D97706",
        "red":    "#DC2626",
        "green":  "#059669",
    }
    fg = colores.get(color, "#374151")
    with col:
        st.markdown(f"""
        <div style="background:white; border-radius:12px; padding:1.2rem 1.4rem;
                    border:1px solid #F0F0F0; border-left:4px solid {fg};
                    box-shadow:0 2px 8px rgba(0,0,0,0.06); margin-bottom:0.5rem;">
            <div style="font-size:0.78rem; font-weight:600; color:#888;
                        text-transform:uppercase; letter-spacing:0.5px; margin-bottom:0.3rem;">
                {icono} {titulo}
            </div>
            <div style="font-size:2.2rem; font-weight:800; color:{fg}; line-height:1.1;">{valor}</div>
        </div>
        """, unsafe_allow_html=True)

def _safe_int(x, default=0):
    try:
        return int(x)
    except Exception:
        return default


def _ticket_id_fmt(t) -> str:
    return f"{_safe_int(t.get('id', 0)):04d}"


def _normalize_ticket_row(t: dict) -> dict:
    """
    Normaliza llaves para dataframe (por si tickets viejos no traen todo).
    """
    return {
        "id": _safe_int(t.get("id", 0)),
        "folio": _ticket_id_fmt(t),
        "estatus": t.get("estatus", "") or "Nuevo",
        "created_at": t.get("created_at", ""),
        "updated_at": t.get("updated_at", ""),
        "updated_by": t.get("updated_by", ""),
        "assigned_to": t.get("assigned_to", "Sin asignar"),
        "solicitante": t.get("solicitante", ""),
        "correo": t.get("correo", ""),
        "empresa": t.get("empresa", ""),
        "categoria": t.get("categoria", ""),
        "departamento": t.get("departamento", ""),
        "prioridad": t.get("prioridad", ""),
        "titulo": t.get("titulo", ""),
        "descripcion": t.get("descripcion", ""),
        "comentarios": t.get("comentarios", ""),
    }


def _flatten_history(tickets: list[dict]) -> pd.DataFrame:
    """
    Convierte historial anidado a filas planas:
    ticket_id, folio, at, by, action, details
    """
    rows = []
    for t in tickets:
        tid = _safe_int(t.get("id", 0))
        folio = _ticket_id_fmt(t)
        hist = t.get("historial", []) or []
        if not isinstance(hist, list):
            continue
        for h in hist:
            if not isinstance(h, dict):
                continue
            rows.append(
                {
                    "ticket_id": tid,
                    "folio": folio,
                    "at": h.get("at", ""),
                    "by": h.get("by", ""),
                    "action": h.get("action", ""),
                    "details": h.get("details", ""),
                }
            )
    df = pd.DataFrame(rows)
    if not df.empty:
        # orden: más reciente primero si se puede
        if "at" in df.columns:
            try:
                df = df.sort_values("at", ascending=False)
            except Exception:
                pass
    return df


def render():
    init_store()

    u = current_user()
    if not u:
        alert("error", "Debes iniciar sesión para gestionar tickets.")
        st.stop()

    if role() != "data_analyst":
        alert("error", "No tienes permisos para gestionar tickets.")
        st.stop()

    section_header("🛠️", "Gestión de Tickets")
    st.caption("Asignación, estatus y seguimiento interno")

    admin_pwd = st.text_input("Contraseña equipo", type="password")
    secret_pwd = get_secret("TICKETS_ADMIN_PASSWORD")

    if not secret_pwd:
        st.warning(
            "No existe `TICKETS_ADMIN_PASSWORD` en secrets o variables de entorno.\n"
            "Agrégala para habilitar la gestión."
        )
        st.stop()

    if not admin_pwd:
        alert("info", "Ingresa la contraseña para continuar.")
        st.stop()

    if admin_pwd != secret_pwd:
        alert("error", "Contraseña incorrecta.")
        st.stop()

    tickets = list_tickets()
    if not tickets:
        alert("info", "No hay tickets todavía.")
        st.stop()

    # =========================
    # INFO CARDS (antes de select)
    # =========================
    def count_status(name: str) -> int:
        return sum(1 for t in tickets if (t.get("estatus") or "Nuevo") == name)

    nuevos = count_status("Nuevo")
    en_proceso = count_status("En Proceso")
    cancelados = count_status("Cancelado")
    concluidos = count_status("Concluido")




    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _stat_card(c1, "Nuevos", str(nuevos), "blue", "🆕")
    with c2:
        _stat_card(c2, "En proceso", str(en_proceso), "yellow", "⏳")
    with c3:
        _stat_card(c3, "Cancelados", str(cancelados), "red", "🚫")
    with c4:
        _stat_card(c4, "Concluidos", str(concluidos), "green", "✅")

    divider()

    # =========================
    # SELECT TICKET
    # =========================
    opciones = [
        f"#{_ticket_id_fmt(t)} | {t.get('estatus','')} | {t.get('titulo','')}"
        for t in sorted(tickets, key=lambda x: _safe_int(x.get("id", 0)), reverse=True)
    ]
    sel = st.selectbox("Selecciona un ticket", opciones)

    sel_id = int(sel.split("|")[0].strip().replace("#", ""))
    t = get_ticket(sel_id)
    if not t:
        alert("error", "No se encontró el ticket.")
        st.stop()

    # =========================
    # TABLA DE ABIERTOS (después de seleccionar)
    # =========================
    st.markdown("### 📋 Tickets abiertos (Nuevo / En Proceso)")
    abiertos = [x for x in tickets if (x.get("estatus") or "Nuevo") in ["Nuevo", "En Proceso"]]
    df_abiertos = pd.DataFrame([_normalize_ticket_row(x) for x in abiertos])

    if df_abiertos.empty:
        alert("info", "No hay tickets abiertos.")
    else:
        # Orden: más reciente primero por id
        df_abiertos = df_abiertos.sort_values("id", ascending=False)

        # columnas “full” (toda la info)
        cols = [
            "folio",
            "estatus",
            "assigned_to",
            "prioridad",
            "empresa",
            "categoria",
            "departamento",
            "titulo",
            "solicitante",
            "correo",
            "created_at",
            "updated_at",
            "updated_by",
            "comentarios",
            "descripcion",
        ]
        cols = [c for c in cols if c in df_abiertos.columns]
        st.dataframe(df_abiertos[cols], use_container_width=True, hide_index=True)

    divider()

    # =========================
    # DETALLE DEL SELECCIONADO
    # =========================
    st.markdown("### 🧾 Detalle del ticket seleccionado")
    colA, colB, colC = st.columns(3)
    with colA:
        st.write(f"**ID:** #{_ticket_id_fmt(t)}")
        st.write(f"**Creado:** {t.get('created_at')}")
    with colB:
        st.write(f"**Última actualización:** {t.get('updated_at')}")
        st.write(f"**Actualizó:** {t.get('updated_by')}")
    with colC:
        st.write(f"**Solicitante:** {t.get('solicitante')}")
        st.write(f"**Correo:** {t.get('correo')}")

    st.write(f"**Empresa:** {t.get('empresa')}")
    st.write(f"**Prioridad:** {t.get('prioridad')}")
    st.write(f"**Categoría:** {t.get('categoria')}")
    st.write(f"**Departamento:** {t.get('departamento')}")
    st.write(f"**Título:** {t.get('titulo')}")
    st.text_area("Descripción", value=t.get("descripcion", ""), height=140, disabled=True)

    divider()
    st.markdown("### ✏️ Actualizar")

    col1, col2 = st.columns(2)
    with col1:
        estatus_actual = t.get("estatus", "Nuevo")
        idx_status = STATUSES.index(estatus_actual) if estatus_actual in STATUSES else 0
        nuevo_estatus = st.selectbox("Estatus", STATUSES, index=idx_status)

    with col2:
        assigned_actual = t.get("assigned_to") or "Sin asignar"
        idx_asg = ANALYSTS.index(assigned_actual) if assigned_actual in ANALYSTS else 0
        assigned_to = st.selectbox("Asignar a", ANALYSTS, index=idx_asg)

    comentarios = st.text_area("Comentarios internos (equipo)", value=t.get("comentarios", ""), height=120)
    updated_by = st.text_input("Tu nombre (quién actualiza)", value=t.get("updated_by") or "")

    if st.button("Guardar cambios", type="primary"):
        ok = update_ticket(
            sel_id,
            estatus=nuevo_estatus,
            assigned_to=assigned_to,
            comentarios=comentarios,
            updated_by=(updated_by.strip() or "equipo data"),
        )
        if ok:
            alert("success", "Ticket actualizado.")
            st.rerun()
        else:
            alert("error", "No se pudo actualizar el ticket.")

    # =========================
    # HISTORIAL DEL TICKET
    # =========================
    divider()
    st.markdown("### 🧠 Historial del ticket seleccionado")
    hist = list(reversed(t.get("historial", [])))
    if not hist:
        alert("info", "Sin historial aún.")
    else:
        for h in hist[:60]:
            if isinstance(h, dict):
                st.write(f"- **{h.get('at')}** | **{h.get('by')}** | {h.get('action')} — {h.get('details')}")
            else:
                st.write(f"- {h}")

    # =========================
    # EXPORT (Excel: todo + abiertos + historial)
    # =========================
    divider()
    st.markdown("### 📦 Exportar")

    df_all = pd.DataFrame([_normalize_ticket_row(x) for x in tickets]).sort_values("id", ascending=False)
    df_hist = _flatten_history(tickets)

    # Abiertos ya lo tenemos
    df_open = df_abiertos.copy() if not df_abiertos.empty else pd.DataFrame()

    # Genera Excel en memoria
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_all.to_excel(writer, index=False, sheet_name="Tickets")
        if not df_open.empty:
            df_open.to_excel(writer, index=False, sheet_name="Abiertos")
        else:
            pd.DataFrame([{"info": "No hay tickets abiertos"}]).to_excel(writer, index=False, sheet_name="Abiertos")

        if not df_hist.empty:
            df_hist.to_excel(writer, index=False, sheet_name="Historial")
        else:
            pd.DataFrame([{"info": "No hay historial"}]).to_excel(writer, index=False, sheet_name="Historial")

    st.download_button(
        "Descargar Excel (Tickets + Abiertos + Historial)",
        data=output.getvalue(),
        file_name="tickets_export.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
