# portal_app/modules/solicitudes/complementarias/consulta.py
import streamlit as st
import pandas as pd

from services.supabase_client import current_user
from ui.components import section_header, kpi_row
from .shared import get_supabase_client


def render():
    u = current_user()
    if not u:
        st.error("Debes iniciar sesión para consultar complementarias.")
        st.stop()

    supabase     = get_supabase_client()
    user_email   = (u.get("email") or "").strip().lower()

    if not user_email:
        st.error("No se pudo identificar el correo del usuario actual.")
        st.stop()

    section_header("🔎", "Mis complementarias",
                   "Busca por tráfico, folio o correo. Si dejas vacío se muestran todas.")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        criterio = st.selectbox("Buscar por",
                                ["(Sin filtro)", "Tráfico", "Folio", "Correo"], index=0)
    with col2:
        q = st.text_input("Búsqueda",
                          placeholder="Ej. SEP03873/25 / 0025 / nombre@dominio.com")
    with col3:
        limite = st.selectbox("Límite", [50, 100, 200, 500], index=1)

    q_clean = q.strip()

    query = (
        supabase.table("solicitudes_complementarias")
        .select(
            "folio,fecha_captura,empresa,sucursal,plataforma,solicitante,correo,"
            "numero_trafico,tipo_complementaria,estatus,"
            "fecha_ultima_modificacion,fecha_resuelto,auditor"
        )
        .ilike("correo", user_email)
        .limit(int(limite))
    )

    if criterio != "(Sin filtro)" and q_clean:
        if criterio == "Tráfico":
            query = query.ilike("numero_trafico", f"%{q_clean.upper()}%")
        elif criterio == "Correo":
            query = query.ilike("correo", f"%{q_clean.lower()}%")
        elif criterio == "Folio":
            try:
                query = query.eq("folio", int(q_clean))
            except Exception:
                st.error("Para buscar por folio ingresa un número (ej. 25 o 0025).")
                st.stop()

    query = query.order("folio", desc=True)

    try:
        rows = query.execute().data or []
    except Exception as e:
        st.error(f"No se pudo consultar: {e}")
        st.stop()

    if not rows:
        st.warning("No se encontraron resultados.")
        st.stop()

    # ── KPIs usando componente responsive ────────────────────────────────────
    kpi_row([
        dict(icono="📥", label="Pendientes",
             valor=sum(1 for r in rows if r.get("estatus") == "Pendiente"),
             sub="", color="#1D4ED8"),
        dict(icono="🔍", label="En revisión",
             valor=sum(1 for r in rows if r.get("estatus") == "En revisión"),
             sub="", color="#D97706"),
        dict(icono="🚫", label="Cancelados",
             valor=sum(1 for r in rows if r.get("estatus") == "Cancelado"),
             sub="", color="#DC2626"),
        dict(icono="✅", label="Resueltos",
             valor=sum(1 for r in rows if r.get("estatus") == "Resuelto"),
             sub="", color="#059669"),
    ])

    st.divider()

    df = pd.DataFrame(rows)

    if "folio" in df.columns:
        try:
            df["folio"] = df["folio"].astype(int).map(lambda x: f"{x:04d}")
        except Exception:
            pass

    order_map = {"Pendiente": 0, "En revisión": 1, "Cancelado": 2, "Resuelto": 3}
    df["_ord"] = df["estatus"].map(lambda x: order_map.get(x, 99))
    df["_folio_int"] = df["folio"].map(lambda x: int(str(x)) if str(x).isdigit() else 0)
    df = df.sort_values(["_ord", "_folio_int"], ascending=[True, False]).drop(
        columns=["_ord", "_folio_int"], errors="ignore"
    )

    st.write(f"**Resultados:** {len(df)}")
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.download_button(
        "⬇️ Descargar CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="consulta_complementarias.csv",
        mime="text/csv",
    )
