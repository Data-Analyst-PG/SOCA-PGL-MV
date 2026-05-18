from ui.components import section_header, alert, divider
"""
subastas.py  –  Módulo Ventas
Vendedor: crea solicitudes de subasta y selecciona al ganador.
Gerente:  ve subastas abiertas y oferta su tarifa de forma anónima.
"""

import streamlit as st
import pandas as pd
from datetime import date, timedelta

from services.supabase_client import get_supabase_client, current_user
from services.authz import profile


# ─── helpers ─────────────────────────────────
def _uid():
    u = current_user() or {}
    return u.get("id") or u.get("sub")


def _rol_sf() -> str:
    """Lee rol_sf del usuario desde sf_usuarios."""
    uid = _uid()
    if not uid:
        return ""
    sb = get_supabase_client()
    if sb is None:
        return ""
    try:
        res = sb.table("sf_usuarios").select("rol_sf").eq("user_id", uid).maybe_single().execute()
        return (res.data or {}).get("rol_sf", "")
    except Exception:
        return ""


def _sucursal_id() -> str | None:
    uid = _uid()
    if not uid:
        return None
    sb = get_supabase_client()
    if sb is None:
        return None
    try:
        res = sb.table("sf_usuarios").select("sucursal_id").eq("user_id", uid).maybe_single().execute()
        return (res.data or {}).get("sucursal_id")
    except Exception:
        return None


@st.cache_data(show_spinner=False, ttl=30)
def _cargar_subastas(uid: str) -> pd.DataFrame:
    sb = get_supabase_client()
    if sb is None:
        return pd.DataFrame()
    try:
        resp = sb.table("sf_subastas").select("*").execute()
        return pd.DataFrame(resp.data or [])
    except Exception:
        return pd.DataFrame()


@st.cache_data(show_spinner=False, ttl=30)
def _cargar_ofertas(subasta_id: str) -> pd.DataFrame:
    sb = get_supabase_client()
    if sb is None:
        return pd.DataFrame()
    try:
        resp = sb.table("sf_ofertas").select("*").eq("subasta_id", subasta_id).execute()
        return pd.DataFrame(resp.data or [])
    except Exception:
        return pd.DataFrame()


TIPOS = ["NB", "SB", "D2D SB", "D2D NB", "PPNB", "PPSB", "DOMUSA"]


# ─── Vista Vendedor ────────────────────────────
def _vista_vendedor():
    sb  = get_supabase_client()
    uid = _uid()
section_header("📢", "Mis subastas")

    df = _cargar_subastas(uid)
    mis = df[df["creado_por"] == uid] if not df.empty else pd.DataFrame()

    tab_nueva, tab_activas = st.tabs(["➕ Nueva subasta", "📋 Mis subastas"])

    with tab_nueva:
        with st.form("sf_sub_nueva"):
            c1, c2 = st.columns(2)
            tipo    = c1.selectbox("Tipo de servicio", TIPOS, key="sf_sn_tipo")
            volumen = c2.number_input("Viajes/mes estimados", min_value=1, step=1, key="sf_sn_vol")
            origen  = c1.text_input("Origen",  placeholder="HOUSTON, TX",  key="sf_sn_orig")
            destino = c2.text_input("Destino", placeholder="AMOZOC, PUE",  key="sf_sn_dest")
            cierre  = c1.date_input("Fecha límite de ofertas",
                                     value=date.today() + timedelta(days=7), key="sf_sn_cierre")
            notas   = st.text_area("Notas para gerentes", height=70, key="sf_sn_notas")
            enviado = st.form_submit_button("📢 Publicar subasta", type="primary")

        if enviado:
            if not origen.strip() or not destino.strip():
                alert("error", "❌ Ingresa origen y destino.")
            else:
                try:
                    sb.table("sf_subastas").insert({
                        "creado_por":      uid,
                        "tipo_servicio":   tipo,
                        "ruta_origen":     origen.strip().upper(),
                        "ruta_destino":    destino.strip().upper(),
                        "volumen_mensual": volumen,
                        "fecha_cierre":    cierre.isoformat(),
                        "notas":           notas.strip() or None,
                        "estado":          "abierta",
                    }).execute()
                    alert("success", "✅ Subasta publicada. Los gerentes recibirán notificación.")
                    _cargar_subastas.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ {e}")

    with tab_activas:
        if mis.empty:
            alert("info", "No tienes subastas creadas aún.")
            return

        for _, sub in mis.iterrows():
            estado   = sub.get("estado", "")
            sub_id   = sub.get("id", "")
            color    = "#E6F1FB" if estado == "abierta" else "#E1F5EE" if estado == "cerrada" else "#F1EFE8"
            badge    = "🟢 Abierta" if estado == "abierta" else "✅ Cerrada" if estado == "cerrada" else "❌ Cancelada"

            with st.expander(f"{sub.get('ruta_origen','')} → {sub.get('ruta_destino','')}  |  {badge}"):
                st.caption(f"Tipo: {sub.get('tipo_servicio','')}  ·  Cierre: {sub.get('fecha_cierre','')}  ·  ID: {sub_id[:8]}...")

                ofertas_df = _cargar_ofertas(sub_id)

                if estado == "abierta":
                    st.info(f"⏳ {len(ofertas_df)} oferta(s) recibidas hasta ahora. Aún no puedes ver las tarifas.")
                    if st.button("🔒 Cerrar subasta ahora", key=f"sf_cerrar_{sub_id}"):
                        try:
                            sb.table("sf_subastas").update({"estado": "cerrada"}).eq("id", sub_id).execute()
                            _cargar_subastas.clear()
                            _cargar_ofertas.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ {e}")

                elif estado == "cerrada" and not ofertas_df.empty:
                    st.success(f"✅ Subasta cerrada — {len(ofertas_df)} oferta(s)")
                    # Mostrar ofertas anónimas ordenadas por tarifa
                    ofertas_df = ofertas_df.sort_values("tarifa_usd")
                    for i, oferta in ofertas_df.iterrows():
                        oferta_id    = oferta.get("id","")
                        codigo_anon  = "GER-" + oferta_id[:8].upper()
                        tarifa       = oferta.get("tarifa_usd", 0)
                        costo_est    = oferta.get("costo_estimado")
                        es_ganadora  = oferta.get("es_ganadora", False)

                        borde = "2px solid #0F6E56" if es_ganadora else "0.5px solid var(--border)"
                        with st.container():
                            c_a, c_b = st.columns([3, 1])
                            c_a.markdown(
                                f"**{codigo_anon}** &nbsp; `${tarifa:,.2f} USD`"
                                + (f" · Costo est: ${costo_est:,.2f}" if costo_est else "")
                                + (" ✅ **GANADORA**" if es_ganadora else "")
                            )
                            if not es_ganadora and not any(ofertas_df["es_ganadora"]):
                                if c_b.button("Seleccionar", key=f"sf_win_{oferta_id}"):
                                    try:
                                        sb.table("sf_ofertas").update({"es_ganadora": True}).eq("id", oferta_id).execute()
                                        sb.table("sf_subastas").update({"oferta_ganadora_id": oferta_id}).eq("id", sub_id).execute()
                                        _cargar_subastas.clear()
                                        _cargar_ofertas.clear()
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"❌ {e}")
                elif estado == "cerrada":
                    alert("warn", "No se recibieron ofertas para esta subasta.")


# ─── Vista Gerente ─────────────────────────────
def _vista_gerente():
    sb  = get_supabase_client()
    uid = _uid()
    suc_id = _sucursal_id()

section_header("📥", "Subastas disponibles para ofertar")
    alert("info", "Tu identidad es anónima para el vendedor mientras la subasta esté abierta.")

    df = _cargar_subastas(uid)
    abiertas = df[df["estado"] == "abierta"] if not df.empty else pd.DataFrame()

    if abiertas.empty:
        alert("info", "No hay subastas abiertas en este momento.")
        return

    for _, sub in abiertas.iterrows():
        sub_id = sub.get("id","")
        with st.expander(f"📦 {sub.get('ruta_origen','')} → {sub.get('ruta_destino','')}  ·  Cierre: {sub.get('fecha_cierre','')}"):
            st.caption(f"Tipo: {sub.get('tipo_servicio','')}  ·  Volumen: {sub.get('volumen_mensual','')} viajes/mes")
            if sub.get("notas"):
                st.info(f"📝 {sub['notas']}")

            # Verificar si ya ofertó
            mis_ofertas = _cargar_ofertas(sub_id)
            ya_oferto = not mis_ofertas.empty and any(mis_ofertas.get("gerente_id","") == uid)

            if ya_oferto:
                mi_oferta = mis_ofertas[mis_ofertas["gerente_id"] == uid].iloc[0]
                st.success(f"✅ Ya ofertaste: **${mi_oferta.get('tarifa_usd',0):,.2f} USD** — En revisión")
            else:
                with st.form(key=f"sf_of_{sub_id}"):
                    oc1, oc2 = st.columns(2)
                    tarifa    = oc1.number_input("Tu tarifa (USD)", min_value=0.01, step=0.01, format="%.2f", key=f"sf_of_t_{sub_id}")
                    costo_est = oc2.number_input("Costo estimado (USD)", min_value=0.0, step=0.01, format="%.2f", key=f"sf_of_c_{sub_id}")
                    notas_of  = st.text_area("Notas (opcional)", height=60, key=f"sf_of_n_{sub_id}")

                    if tarifa > 0 and costo_est > 0:
                        margen = (tarifa - costo_est) / tarifa
                        st.caption(f"Margen estimado: **{margen:.1%}** · Utilidad: **${tarifa - costo_est:,.2f}**")

                    enviado = st.form_submit_button("📤 Enviar oferta anónima", type="primary")

                if enviado:
                    if tarifa <= 0:
                        alert("error", "❌ Ingresa una tarifa válida.")
                    elif not suc_id:
                        alert("error", "❌ Tu usuario no está asignado a una sucursal.")
                    else:
                        try:
                            sb.table("sf_ofertas").insert({
                                "subasta_id":     sub_id,
                                "gerente_id":     uid,
                                "sucursal_id":    suc_id,
                                "tarifa_usd":     tarifa,
                                "costo_estimado": costo_est or None,
                                "notas":          notas_of.strip() or None,
                            }).execute()
                            alert("success", "✅ Oferta enviada. El vendedor no sabe quién eres hasta que cierre la subasta.")
                            _cargar_subastas.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ {e}")


# ─── Entry point ──────────────────────────────
def render():
    from ui.components import page_banner
    page_banner("🔎", "🏷️ Subastas de Tarifas", "")

    p = profile() or {}
    rol = _rol_sf()

    if rol in ("gerente", "supervisor"):
        vista = st.radio("Ver como:", ["Vendedor (mis subastas)", "Gerente (ofertar)"],
                          horizontal=True, key="sf_sub_vista")
        if "Gerente" in vista:
            _vista_gerente()
        else:
            _vista_vendedor()
    else:
        _vista_vendedor()
