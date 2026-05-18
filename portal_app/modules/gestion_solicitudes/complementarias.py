from ui.components import page_banner, section_header, alert, divider
import os
from datetime import datetime
import io
import pandas as pd
import streamlit as st
from services.authz import role

from services.supabase_client import current_user
from .shared import (
    EMPRESAS,
    SUCURSALES_POR_EMPRESA,
    get_supabase_client,
    get_secret,
    now_utc_iso,
    get_profile_name,
    es_plataforma_logismex,
)


def _stat_card(col, titulo: str, valor: str, color: str, icono: str):
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


def _is_na(val) -> bool:
    if val is None:
        return True
    s = str(val).strip()
    return s == "" or s.upper() == "N/A" or s.lower() == "nan"


def show_field(label: str, value):
    if not _is_na(value):
        st.write(f"**{label}:** {value}")


def show_money(label: str, value):
    if value is None:
        return
    try:
        v = float(value)
    except Exception:
        return
    st.write(f"**{label}:** {v:,.2f}")


def _render_campos_logismex(r: dict, sufijo: str, titulo: str):
    """
    Muestra los campos fiscales de Logismex para un bloque (actual o nuevo).
    sufijo: "actual" o "nuevo"
    Solo muestra algo si hay datos de tasa_iva.
    """
    tasa_iva = r.get(f"tasa_iva_{sufijo}")
    if not tasa_iva:
        return

    st.markdown(
        f'<div style="background:rgba(27,34,102,0.04); border-left:3px solid #1B2266; '
        f'padding:0.5rem 0.8rem; border-radius:0 8px 8px 0; margin:0.4rem 0;">'
        f'<strong style="font-size:0.8rem; color:#1B2266;">💹 Datos fiscales ({titulo})</strong>'
        f'</div>',
        unsafe_allow_html=True,
    )

    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        show_field("Tasa IVA", tasa_iva)
        show_money("IVA", r.get(f"monto_iva_{sufijo}"))
    with fc2:
        show_field("Tasa Retención", r.get(f"tasa_retencion_{sufijo}"))
        show_money("Retención", r.get(f"monto_retencion_{sufijo}"))
    with fc3:
        show_field("Retención ISR", r.get(f"retencion_isr_{sufijo}"))
        show_money("Ret. ISR", r.get(f"monto_retencion_isr_{sufijo}"))

    total = r.get(f"total_{sufijo}")
    if total is not None:
        try:
            st.markdown(
                f'<div style="background:#E8F5E9; padding:0.4rem 0.8rem; border-radius:8px; '
                f'display:inline-block; margin:0.3rem 0;">'
                f'<strong style="color:#2E7D32;">Total calculado: ${float(total):,.2f}</strong>'
                f'</div>',
                unsafe_allow_html=True,
            )
        except (ValueError, TypeError):
            pass


def _render_detalle(r: dict, folio_fmt: str):
    """Muestra el detalle completo de una solicitud (sin botones de edición)."""
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        show_field("Fecha captura", r.get("fecha_captura"))
        show_field("Última modificación", r.get("fecha_ultima_modificacion"))
    with col_b:
        show_field("Empresa", r.get("empresa"))
        show_field("Sucursal", r.get("sucursal"))
    with col_c:
        show_field("Plataforma", r.get("plataforma"))
        show_field("Solicitante", r.get("solicitante"))

    show_field("Tráfico", r.get("numero_trafico"))
    show_field("Motivo", r.get("motivo_solicitud"))
    show_field("Tipo complementaria", r.get("tipo_complementaria"))
    show_field("Auditor", r.get("auditor"))
    if r.get("comentarios_auditor"):
        st.write(f"**Comentarios auditor:** {r.get('comentarios_auditor')}")

    divider()
    col_izq, col_der = st.columns(2)
    with col_izq:
        st.markdown("**📋 Datos actuales (como están)**")
        show_field("Tipo concepto (actual)", r.get("tipo_concepto_actual"))
        show_field("Concepto (actual)", r.get("concepto_actual"))
        show_field("Proveedor (actual)", r.get("proveedor_actual"))
        show_field("Moneda (actual)", r.get("moneda_actual"))
        show_money("Importe (actual)", r.get("importe_actual"))
    with col_der:
        st.markdown("**✅ Datos correctos (como deben quedar)**")
        show_field("Tipo concepto (nuevo)", r.get("tipo_concepto_nuevo"))
        show_field("Concepto (nuevo)", r.get("concepto_nuevo"))
        show_field("Proveedor (nuevo)", r.get("proveedor_nuevo"))
        show_field("Moneda (nuevo)", r.get("moneda_nuevo"))
        show_money("Importe (nuevo)", r.get("importe_nuevo"))

    # Campos fiscales Logismex (si aplica)
    if es_plataforma_logismex(r.get("plataforma", "")):
        divider()
        col_fisc_izq, col_fisc_der = st.columns(2)
        with col_fisc_izq:
            _render_campos_logismex(r, "actual", "Datos actuales")
        with col_fisc_der:
            _render_campos_logismex(r, "nuevo", "Datos nuevos")

    # Historial
    divider()
    st.markdown("### 🧠 Historial de esta solicitud")
    historial = r.get("historial") or []
    if not historial:
        alert("info", "Sin historial registrado aún.")
    else:
        for h in reversed(historial):
            if isinstance(h, dict):
                st.write(
                    f"- **{h.get('at')}** | **{h.get('by')}** | "
                    f"{h.get('action')} — {h.get('details')}"
                )


def render():
    u = current_user()
    if not u:
        alert("error", "Debes iniciar sesión para entrar a Auditor.")
        st.stop()

    if role() not in ("auditor", "data_analyst"):
        alert("error", "No tienes permisos para entrar al módulo de Auditor.")
        st.stop()

    # Leer nombre completo del auditor logueado desde profiles
    user_id = u.get("id") or u.get("sub") or ""
    nombre_auditor = get_profile_name(user_id) or (u.get("email") or "Auditor desconocido")

    supabase = get_supabase_client()

section_header("🛡️", "Gestión Complementarias")
    st.caption("Panel de segumiento de solicitudes de complementarias y desconclusiones")

    auditor_pwd = st.text_input("Contraseña auditor", type="password")
    secret_pwd = get_secret("AUDITOR_PASSWORD") or os.getenv("AUDITOR_PASSWORD")

    if not secret_pwd:
        alert("error", "No existe AUDITOR_PASSWORD en secrets/variables. Agrégala para usar Auditor.")
        st.stop()

    if auditor_pwd == "":
        alert("info", "Ingresa la contraseña para ver las solicitudes.")
        st.stop()

    if auditor_pwd != secret_pwd:
        alert("error", "Contraseña incorrecta.")
        st.stop()

    ESTATUS_OPCIONES = ["Pendiente", "En revisión", "Cancelado", "Resuelto"]
    ESTATUS_ABIERTOS = ["Pendiente", "En revisión"]
    ESTATUS_CERRADOS = ["Resuelto", "Cancelado"]

    # CSS para las secciones con borde
    st.markdown("""
    <style>
    .seccion-card {
        border: 2px solid #E2E8F0;
        border-radius: 14px;
        padding: 1.4rem 1.6rem 1rem 1.6rem;
        margin-bottom: 1.5rem;
        background: #FAFBFF;
    }
    .seccion-card-detalle {
        border: 2px solid #C7D2FE;
        border-radius: 14px;
        padding: 1.4rem 1.6rem 1rem 1.6rem;
        margin-top: 0.8rem;
        margin-bottom: 1rem;
        background: white;
    }
    .seccion-historico {
        border: 2px solid #D1FAE5;
        border-radius: 14px;
        padding: 1.4rem 1.6rem 1rem 1.6rem;
        margin-bottom: 1.5rem;
        background: #F0FDF4;
    }
    </style>
    """, unsafe_allow_html=True)

    # ─────────────────────────────────────────
    # Cargar TODOS los registros
    # ─────────────────────────────────────────
    try:
        res_all = (
            supabase.table("solicitudes_complementarias")
            .select("*")
            .order("folio", desc=True)
            .limit(500)
            .execute()
        )
        rows_all = res_all.data or []
    except Exception as e:
        st.error(f"No se pudieron cargar solicitudes: {e}")
        st.stop()

    # ─────────────────────────────────────────
    # STAT CARDS
    # ─────────────────────────────────────────
    pendientes_all = sum(1 for r in rows_all if (r.get("estatus") or "") == "Pendiente")
    en_revision_all = sum(1 for r in rows_all if (r.get("estatus") or "") == "En revisión")
    cancelados_all = sum(1 for r in rows_all if (r.get("estatus") or "") == "Cancelado")
    resueltos_all = sum(1 for r in rows_all if (r.get("estatus") or "") == "Resuelto")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _stat_card(c1, "Pendientes", str(pendientes_all), "blue", "📥")
    with c2:
        _stat_card(c2, "En revisión", str(en_revision_all), "yellow", "🔍")
    with c3:
        _stat_card(c3, "Cancelados", str(cancelados_all), "red", "🚫")
    with c4:
        _stat_card(c4, "Resueltos", str(resueltos_all), "green", "✅")

    divider()

    # ─────────────────────────────────────────
    # SOLICITUDES ACTIVAS
    # ─────────────────────────────────────────
    st.markdown('<div class="seccion-card">', unsafe_allow_html=True)
    st.markdown("### 📥 Solicitudes Activas (Pendiente / En revisión)")
    st.caption("Usa los filtros para acotar resultados, luego selecciona una solicitud para ver su detalle.")

    colf1, colf2, colf3, colf4 = st.columns(4)
    with colf1:
        f_empresa = st.selectbox("Empresa", ["(Todas)"] + EMPRESAS, index=0, key="f_emp_abiertos")
    with colf2:
        suc_opts = ["(Todas)"]
        if f_empresa != "(Todas)":
            suc_list = SUCURSALES_POR_EMPRESA.get(f_empresa, [])
            suc_opts += (suc_list if suc_list else ["N/A"])
        else:
            suc_opts += ["N/A"]
        f_sucursal = st.selectbox("Sucursal", suc_opts, index=0, key="f_suc_abiertos")
    with colf3:
        f_estatus_ab = st.selectbox("Estatus", ["(Todos)"] + ESTATUS_ABIERTOS, index=0, key="f_est_abiertos")
    with colf4:
        texto_ab = st.text_input("Buscar (folio / solicitante / tráfico)", key="txt_abiertos")

    # Filtrar abiertos
    abiertos = [r for r in rows_all if r.get("estatus") in ESTATUS_ABIERTOS]
    if f_empresa != "(Todas)":
        abiertos = [r for r in abiertos if r.get("empresa") == f_empresa]
    if f_sucursal not in ("(Todas)", "N/A"):
        abiertos = [r for r in abiertos if r.get("sucursal") == f_sucursal]
    if f_estatus_ab != "(Todos)":
        abiertos = [r for r in abiertos if r.get("estatus") == f_estatus_ab]
    if texto_ab.strip():
        t = texto_ab.strip().lower()
        abiertos = [
            r for r in abiertos
            if t in f"{int(r.get('folio', 0)):04d}".lower()
            or t in str(r.get("solicitante", "")).lower()
            or t in str(r.get("numero_trafico", "")).lower()
        ]

    st.write(f"**Total activas: {len(abiertos)}**")

    if not abiertos:
        alert("info", "No hay solicitudes activas con los filtros actuales.")
    else:
        # ── SELECT de solicitud activa (empieza sin selección) ───────
        opciones_ab = [
            f"#{int(r['folio']):04d} | {r.get('estatus','')} | {r.get('empresa','')} | {r.get('numero_trafico','')}"
            for r in abiertos
        ]
        sel_ab = st.selectbox(
            "👆 Selecciona una solicitud para ver su detalle",
            opciones_ab,
            index=None,
            placeholder="— Selecciona un folio —",
            key="sel_abierto",
        )

    st.markdown('</div>', unsafe_allow_html=True)

    # ── Detalle fuera del card de filtros, solo si hay selección ────
    if abiertos and "sel_abierto" in st.session_state and st.session_state["sel_abierto"] is not None:
        sel_ab = st.session_state["sel_abierto"]
        sel_folio_ab = int(sel_ab.split("|")[0].strip().replace("#", ""))
        r_sel = next((r for r in abiertos if int(r["folio"]) == sel_folio_ab), None)

        if r_sel:
            folio_fmt = f"{int(r_sel['folio']):04d}"
            estatus_actual = r_sel.get("estatus") or "Pendiente"
            tipo_comp = r_sel.get("tipo_complementaria")

            st.markdown('<div class="seccion-card-detalle">', unsafe_allow_html=True)
            st.markdown(f"#### 📄 Detalle — Folio #{folio_fmt} | {r_sel.get('empresa')} | {estatus_actual}")

            # Info básica
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                show_field("Fecha captura", r_sel.get("fecha_captura"))
                show_field("Última modificación", r_sel.get("fecha_ultima_modificacion"))
            with col_b:
                show_field("Empresa", r_sel.get("empresa"))
                show_field("Sucursal", r_sel.get("sucursal"))
            with col_c:
                show_field("Plataforma", r_sel.get("plataforma"))
                show_field("Solicitante", r_sel.get("solicitante"))

            show_field("Tráfico", r_sel.get("numero_trafico"))
            show_field("Motivo", r_sel.get("motivo_solicitud"))
            show_field("Tipo complementaria", tipo_comp)

            divider()
            col_izq, col_der = st.columns(2)
            with col_izq:
                st.markdown("**📋 Datos actuales (como están)**")
                show_field("Tipo concepto (actual)", r_sel.get("tipo_concepto_actual"))
                show_field("Concepto (actual)", r_sel.get("concepto_actual"))
                show_field("Proveedor (actual)", r_sel.get("proveedor_actual"))
                show_field("Moneda (actual)", r_sel.get("moneda_actual"))
                show_money("Importe (actual)", r_sel.get("importe_actual"))
            with col_der:
                st.markdown("**✅ Datos correctos (como deben quedar)**")
                show_field("Tipo concepto (nuevo)", r_sel.get("tipo_concepto_nuevo"))
                show_field("Concepto (nuevo)", r_sel.get("concepto_nuevo"))
                show_field("Proveedor (nuevo)", r_sel.get("proveedor_nuevo"))
                show_field("Moneda (nuevo)", r_sel.get("moneda_nuevo"))
                show_money("Importe (nuevo)", r_sel.get("importe_nuevo"))

            # Campos fiscales Logismex (si aplica)
            if es_plataforma_logismex(r_sel.get("plataforma", "")):
                divider()
                col_fisc_izq, col_fisc_der = st.columns(2)
                with col_fisc_izq:
                    _render_campos_logismex(r_sel, "actual", "Datos actuales")
                with col_fisc_der:
                    _render_campos_logismex(r_sel, "nuevo", "Datos nuevos")

            divider()
            st.markdown("### ✏️ Actualizar solicitud")

            folio_num = int(r_sel["folio"])
            c_edit1, c_edit2 = st.columns([2, 1])
            with c_edit1:
                nuevo_estatus = st.selectbox(
                    "Cambiar estatus",
                    ESTATUS_OPCIONES,
                    index=ESTATUS_OPCIONES.index(estatus_actual) if estatus_actual in ESTATUS_OPCIONES else 0,
                    key=f"estatus_{folio_num}",
                )
                # Auditor detectado automáticamente del login
                st.info(f"👤 Registrando cambios como: **{nombre_auditor}**")
                auditor_sel = nombre_auditor
                comentarios_prev = r_sel.get("comentarios_auditor") or ""
                comentarios = st.text_area(
                    "Comentarios del auditor",
                    value=comentarios_prev,
                    height=120,
                    key=f"coment_{folio_num}",
                )
            with c_edit2:
                st.markdown("<br><br>", unsafe_allow_html=True)
                if st.button("💾 Guardar cambios", key=f"btn_guardar_{folio_num}", type="primary"):
                    now_iso = now_utc_iso()

                    # Construir entrada del historial
                    detalles = []
                    if nuevo_estatus != estatus_actual:
                        detalles.append(f"estatus: {estatus_actual}→{nuevo_estatus}")
                    if comentarios.strip() != comentarios_prev.strip():
                        detalles.append("comentarios_auditor actualizado")
                    if not detalles:
                        detalles.append("sin cambios detectados")

                    nueva_entrada = {
                        "at": now_iso,
                        "by": auditor_sel,
                        "action": "update",
                        "details": " | ".join(detalles),
                    }

                    historial_actual = r_sel.get("historial") or []
                    if not isinstance(historial_actual, list):
                        historial_actual = []
                    historial_actual.append(nueva_entrada)

                    update_payload = {
                        "estatus": nuevo_estatus,
                        "auditor": auditor_sel,
                        "comentarios_auditor": comentarios.strip(),
                        "fecha_ultima_modificacion": now_iso,
                        "historial": historial_actual,
                    }

                    if nuevo_estatus in ["Resuelto", "Cancelado"]:
                        update_payload["fecha_resuelto"] = now_iso
                    else:
                        update_payload["fecha_resuelto"] = None

                    try:
                        (
                            supabase.table("solicitudes_complementarias")
                            .update(update_payload)
                            .eq("folio", folio_num)
                            .execute()
                        )
                        st.success(f"✅ Actualizado folio #{folio_fmt}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"No se pudo actualizar: {e}")

            # Historial de la solicitud activa
            divider()
            st.markdown("### 🧠 Historial de esta solicitud")
            historial = r_sel.get("historial") or []
            if not historial:
                alert("info", "Sin historial registrado aún.")
            else:
                for h in reversed(historial):
                    if isinstance(h, dict):
                        st.write(
                            f"- **{h.get('at')}** | **{h.get('by')}** | "
                            f"{h.get('action')} — {h.get('details')}"
                        )
            st.markdown('</div>', unsafe_allow_html=True)

    # ─────────────────────────────────────────
    # SECCIÓN HISTÓRICO (Resueltos / Cancelados)
    # ─────────────────────────────────────────
    st.markdown('<div class="seccion-historico">', unsafe_allow_html=True)
    st.markdown("### 📁 Histórico — Resueltos y Cancelados")
    st.caption("Filtra y selecciona una solicitud cerrada para consultar qué pasó con ella.")

    # Filtros para cerrados
    hf1, hf2, hf3, hf4 = st.columns(4)
    with hf1:
        h_empresa = st.selectbox("Empresa", ["(Todas)"] + EMPRESAS, index=0, key="h_emp")
    with hf2:
        h_suc_opts = ["(Todas)"]
        if h_empresa != "(Todas)":
            h_suc_list = SUCURSALES_POR_EMPRESA.get(h_empresa, [])
            h_suc_opts += (h_suc_list if h_suc_list else ["N/A"])
        else:
            h_suc_opts += ["N/A"]
        h_sucursal = st.selectbox("Sucursal", h_suc_opts, index=0, key="h_suc")
    with hf3:
        h_estatus = st.selectbox("Estatus", ["(Todos)"] + ESTATUS_CERRADOS, index=0, key="h_est")
    with hf4:
        texto_hist = st.text_input("Buscar (folio / solicitante / tráfico)", key="txt_hist")

    cerrados = [r for r in rows_all if r.get("estatus") in ESTATUS_CERRADOS]
    if h_empresa != "(Todas)":
        cerrados = [r for r in cerrados if r.get("empresa") == h_empresa]
    if h_sucursal not in ("(Todas)", "N/A"):
        cerrados = [r for r in cerrados if r.get("sucursal") == h_sucursal]
    if h_estatus != "(Todos)":
        cerrados = [r for r in cerrados if r.get("estatus") == h_estatus]
    if texto_hist.strip():
        t = texto_hist.strip().lower()
        cerrados = [
            r for r in cerrados
            if t in f"{int(r.get('folio', 0)):04d}".lower()
            or t in str(r.get("solicitante", "")).lower()
            or t in str(r.get("numero_trafico", "")).lower()
        ]

    st.write(f"**Total en histórico: {len(cerrados)}**")

    if not cerrados:
        alert("info", "No hay registros en el histórico con esos filtros.")
    else:
        # ── SELECT para ver detalle de cerrado (empieza sin selección) ──
        opciones_cerr = [
            f"#{int(r['folio']):04d} | {r.get('estatus','')} | {r.get('empresa','')} | {r.get('numero_trafico','')}"
            for r in cerrados
        ]
        sel_cerr = st.selectbox(
            "👆 Selecciona una solicitud para ver su historial completo",
            opciones_cerr,
            index=None,
            placeholder="— Selecciona un folio —",
            key="sel_cerrado",
        )

    st.markdown('</div>', unsafe_allow_html=True)

    # ── Detalle histórico, solo si hay selección ────────────────────
    if cerrados and "sel_cerrado" in st.session_state and st.session_state["sel_cerrado"] is not None:
        sel_cerr = st.session_state["sel_cerrado"]
        sel_folio_cerr = int(sel_cerr.split("|")[0].strip().replace("#", ""))
        r_cerr = next((r for r in cerrados if int(r["folio"]) == sel_folio_cerr), None)

        if r_cerr:
            folio_fmt_cerr = f"{int(r_cerr['folio']):04d}"
            st.markdown('<div class="seccion-card-detalle">', unsafe_allow_html=True)
            st.markdown(
                f"#### 📄 Detalle Histórico — Folio #{folio_fmt_cerr} | "
                f"{r_cerr.get('empresa')} | {r_cerr.get('estatus')}"
            )
            _render_detalle(r_cerr, folio_fmt_cerr)
            st.markdown('</div>', unsafe_allow_html=True)

    # ── Tabla resumen + descarga (siempre al final) ──────────────────
    if cerrados:
        df_cerr = pd.DataFrame(cerrados)
        divider()
        st.markdown("#### 📊 Tabla resumen del histórico filtrado")
        st.dataframe(df_cerr, use_container_width=True, hide_index=True)

        csv_bytes = df_cerr.to_csv(index=False).encode("utf-8")
        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            st.download_button(
                "Descargar CSV (histórico)",
                data=csv_bytes,
                file_name="historico_complementarias.csv",
                mime="text/csv",
            )
        with col_dl2:
            try:
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                    df_cerr.to_excel(writer, index=False, sheet_name="Historico")
                st.download_button(
                    "Descargar Excel (histórico)",
                    data=buf.getvalue(),
                    file_name="historico_complementarias.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            except Exception as e:
                st.warning(f"No se pudo generar Excel: {e}")
