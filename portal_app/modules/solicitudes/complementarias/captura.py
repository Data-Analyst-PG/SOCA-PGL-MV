# portal_app/modules/solicitudes/complementarias/captura.py
# ─────────────────────────────────────────────────────────────────────────────
# Captura de Complementarias — usa sistema de componentes UI
# Lógica de negocio intacta (catálogos, validaciones, Logismex, historial)
# ─────────────────────────────────────────────────────────────────────────────
from datetime import datetime
import streamlit as st
import urllib.parse
import re

from services.supabase_client import current_user
from ui.components import section_header, alert
from .shared import (
    EMPRESAS, MONEDAS, SUCURSALES_POR_EMPRESA, PLATAFORMAS_POR_EMPRESA,
    TIPOS_CONCEPTO, TASAS_IVA, TASAS_RETENCION, RETENCIONES_ISR,
    get_supabase_client, get_conceptos, now_utc_iso, get_profile_name,
    es_plataforma_logismex, calcular_totales_logismex, build_historial_entry,
)


def build_mailto(to_emails: list, subject: str, body: str) -> str:
    return "mailto:{}?subject={}&body={}".format(
        urllib.parse.quote(",".join(to_emails)),
        urllib.parse.quote(subject),
        urllib.parse.quote(body),
    )


# ── Bloque de concepto ────────────────────────────────────────────────────────
def bloque_concepto(prefix: str, titulo: str, plataforma: str):
    st.subheader(titulo)
    show_logismex = es_plataforma_logismex(plataforma)

    col1, col2 = st.columns(2)
    with col1:
        tipo = st.selectbox("Tipo Concepto", TIPOS_CONCEPTO,
                            key=f"{prefix}_tipo", index=None,
                            placeholder="Selecciona un tipo")

    conceptos = get_conceptos(tipo, plataforma) if tipo else []
    concepto_disabled = (not tipo) or (len(conceptos) == 0)

    with col2:
        if concepto_disabled:
            st.selectbox("Concepto",
                         ["Sin datos para mostrar"] if tipo else ["Selecciona primero un tipo"],
                         key=f"{prefix}_concepto", disabled=True)
        else:
            st.selectbox("Concepto", conceptos, key=f"{prefix}_concepto",
                         index=None, placeholder="Selecciona un concepto")

    col3, col4 = st.columns(2)
    with col3:
        proveedor = st.text_input("Proveedor", key=f"{prefix}_proveedor")
        moneda    = st.selectbox("Moneda", MONEDAS, key=f"{prefix}_moneda",
                                 index=None, placeholder="Selecciona moneda")
    with col4:
        importe = st.number_input("Importe", min_value=0.0, step=0.01,
                                  format="%.2f", key=f"{prefix}_importe")

    tasa_iva = tasa_retencion = retencion_isr = totales = None

    if show_logismex:
        alert("info", "Campos fiscales Logismex — IVA, Retención e ISR se calculan automáticamente.")
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            tasa_iva = st.selectbox("Tasa IVA", TASAS_IVA, key=f"{prefix}_tasa_iva",
                                    index=None, placeholder="Selecciona tasa IVA")
        with fc2:
            if tasa_iva == "EXENTO":
                st.selectbox("Tasa Retención", ["No Aplica"],
                             key=f"{prefix}_tasa_ret_display", disabled=True)
                tasa_retencion = "No Aplica"
            else:
                tasa_retencion = st.selectbox("Tasa Retención", TASAS_RETENCION,
                                              key=f"{prefix}_tasa_ret", index=None,
                                              placeholder="Selecciona tasa retención")
        with fc3:
            retencion_isr = st.selectbox("Retención ISR", RETENCIONES_ISR,
                                         key=f"{prefix}_ret_isr", index=None,
                                         placeholder="Selecciona retención ISR")

        if importe > 0 and tasa_iva:
            totales = calcular_totales_logismex(
                importe,
                tasa_iva or "EXENTO",
                tasa_retencion or "EXENTO",
                retencion_isr or "EXENTO",
            )
            tc1, tc2, tc3, tc4 = st.columns(4)
            tc1.metric("IVA",        f"${totales['iva']:,.2f}")
            tc2.metric("Retención",  f"${totales['retencion']:,.2f}")
            tc3.metric("Ret. ISR",   f"${totales['retencion_isr']:,.2f}")
            tc4.metric("Total",      f"${totales['total']:,.2f}")

    return {
        "tipo":              tipo,
        "concepto":          st.session_state.get(f"{prefix}_concepto"),
        "proveedor":         proveedor,
        "moneda":            moneda,
        "importe":           float(importe),
        "tasa_iva":          tasa_iva,
        "tasa_retencion":    tasa_retencion,
        "retencion_isr":     retencion_isr,
        "monto_iva":         totales["iva"]           if totales else None,
        "monto_retencion":   totales["retencion"]     if totales else None,
        "monto_retencion_isr": totales["retencion_isr"] if totales else None,
        "total":             totales["total"]          if totales else None,
    }


def reset_concepto_prefix(prefix: str):
    keys = [f"{prefix}_{k}" for k in [
        "tipo","concepto","proveedor","moneda","importe",
        "tasa_iva","tasa_ret","tasa_ret_display","ret_isr",
    ]]
    for k in keys:
        if k in st.session_state:
            st.session_state[k] = None


def reset_form_complementaria():
    keys = [
        "comp_confirm_ok","comp_success_payload",
        "actual_tipo","actual_concepto","actual_proveedor","actual_moneda","actual_importe",
        "actual_tasa_iva","actual_tasa_ret","actual_tasa_ret_display","actual_ret_isr",
        "nuevo_tipo","nuevo_concepto","nuevo_proveedor","nuevo_moneda","nuevo_importe",
        "nuevo_tasa_iva","nuevo_tasa_ret","nuevo_tasa_ret_display","nuevo_ret_isr",
    ]
    for k in keys:
        st.session_state.pop(k, None)


def _check_duplicado_por_concepto(supabase, numero_trafico, tipo_concepto_nuevo, concepto_nuevo):
    try:
        q = (
            supabase.table("solicitudes_complementarias")
            .select("folio,fecha_captura,solicitante,tipo_concepto_nuevo,concepto_nuevo,estatus")
            .eq("numero_trafico", numero_trafico)
            .eq("tipo_complementaria", "Modificación")
            .eq("tipo_concepto_nuevo", tipo_concepto_nuevo)
        )
        if tipo_concepto_nuevo == "OTROS" and concepto_nuevo:
            q = q.eq("concepto_nuevo", concepto_nuevo)
        return (q.order("folio", desc=True).limit(10).execute().data or [])
    except Exception:
        return []


# ── Render principal ──────────────────────────────────────────────────────────
def render():
    u = current_user()
    if not u:
        alert("error", "Debes iniciar sesión para registrar complementarias.")
        st.stop()

    user_id        = u.get("id") or u.get("sub") or ""
    nombre_usuario = get_profile_name(user_id)
    correo_usuario = (u.get("email") or "").strip().lower()
    supabase       = get_supabase_client()

    section_header("📬", "Nueva Complementaria",
                   "Captura la solicitud de cargo complementario o desconclusión")

    st.text_input("Fecha", value=datetime.now().strftime("%d/%m/%Y"), disabled=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        empresa = st.selectbox("Empresa", EMPRESAS, index=None,
                               placeholder="Selecciona una empresa")

    empresa_key         = empresa.strip() if empresa else ""
    sucursales_opciones = SUCURSALES_POR_EMPRESA.get(empresa_key, [])

    with c2:
        if not empresa:
            st.selectbox("Sucursal", ["Selecciona primero una empresa"],
                         index=0, disabled=True)
            sucursal = None
        elif not sucursales_opciones:
            sucursal = "N/A"
            st.text_input("Sucursal", value="N/A", disabled=True)
        else:
            sucursal = st.selectbox("Sucursal", sucursales_opciones,
                                    index=None, placeholder="Selecciona una sucursal")

    plataformas_opciones = PLATAFORMAS_POR_EMPRESA.get(empresa_key, [])
    with c3:
        plataforma = st.selectbox(
            "Plataforma", plataformas_opciones, index=None,
            placeholder="Selecciona una plataforma" if empresa else "Selecciona primero empresa",
            disabled=(empresa is None),
        )

    if plataforma and es_plataforma_logismex(plataforma):
        alert("warn", "Plataforma Logismex — Se habilitarán campos fiscales adicionales.")

    TIPOS_MOTIVO = [
        "Concepto Incorrecto",
        "Costo no capturado",
        "Monto Incorrecto",
        "Moneda Incorrecta",
        "Proveedor Incorrecto",
        "Otro",
    ]

    csol1, csol2, csol3 = st.columns(3)
    with csol1:
        solicitante = st.text_input(
            "Solicitante*", value=nombre_usuario, disabled=bool(nombre_usuario),
            placeholder="nombre completo",
            help="Detectado automáticamente desde tu cuenta." if nombre_usuario
                 else "Escribe tu nombre completo.",
        )
    with csol2:
        correo = st.text_input("Correo*", value=correo_usuario, disabled=True,
                               help="Detectado automáticamente desde tu cuenta.")
    with csol3:
        tipo_motivo_sel = st.multiselect(
            "Tipo de motivo*",
            options=TIPOS_MOTIVO,
            placeholder="Selecciona uno o más",
            help="Puedes seleccionar varios. Se guardarán en orden alfabético.",
        )
        tipo_motivo = ", ".join(sorted(tipo_motivo_sel)) if tipo_motivo_sel else ""

    motivo_solicitud = st.text_area(
        "Motivo de la solicitud*",
        placeholder="Ejemplo: se capturó un proveedor incorrecto",
    )

    c1, c2 = st.columns(2)
    with c1:
        numero_trafico = st.text_input("Número de tráfico", placeholder="SEP03873/25")
    with c2:
        tipo_complementaria = st.radio(
            "Tipo de complementaria/desconclusión",
            ["Desconclusión", "Modificación", "Agregar Concepto"],
            horizontal=True,
        )

    st.divider()

    es_desconclusion         = tipo_complementaria == "Desconclusión"
    plataforma_para_conceptos = plataforma or ""

    if es_desconclusion:
        reset_concepto_prefix("actual")
        reset_concepto_prefix("nuevo")
        alert("info", "Modo Desconclusión — Solo se captura la información base.")
        _vacio = {
            "tipo": None, "concepto": None, "proveedor": None, "moneda": None,
            "importe": None, "tasa_iva": None, "tasa_retencion": None,
            "retencion_isr": None, "monto_iva": None, "monto_retencion": None,
            "monto_retencion_isr": None, "total": None,
        }
        actual = _vacio
        nuevo  = dict(_vacio)
    else:
        if tipo_complementaria == "Modificación":
            actual = bloque_concepto("actual", "📝 Datos actuales (como están)",
                                     plataforma_para_conceptos)
            st.divider()
        else:
            actual = {
                "tipo": "N/A", "concepto": "N/A", "proveedor": "N/A",
                "moneda": "N/A", "importe": None, "tasa_iva": None,
                "tasa_retencion": None, "retencion_isr": None,
                "monto_iva": None, "monto_retencion": None,
                "monto_retencion_isr": None, "total": None,
            }
        nuevo = bloque_concepto("nuevo", "✅ Datos correctos (como deben quedar)",
                                plataforma_para_conceptos)

    st.divider()

    if "comp_confirm_ok"       not in st.session_state: st.session_state.comp_confirm_ok = False
    if "comp_success_payload"  not in st.session_state: st.session_state.comp_success_payload = None

    if st.session_state.comp_success_payload:
        payload = st.session_state.comp_success_payload

        @st.dialog("✅ Solicitud registrada correctamente")
        def _dlg_success():
            st.success(f"Solicitud **#{payload['folio']}** registrada correctamente.")
            st.markdown(f"👉 **Enviar notificación:** [Abrir correo]({payload['mailto']})")
            st.caption("O copia este mensaje manualmente:")
            st.code(payload["mensaje_manual"], language="text")
            if st.button("OK", type="primary"):
                reset_form_complementaria()
                st.rerun()

        _dlg_success()
        st.stop()

    if not st.button("Registrar", type="primary"):
        return

    # ── Validaciones ──────────────────────────────────────────────────────────
    errores = []
    if not empresa:    errores.append("Debes seleccionar una empresa.")
    if not plataforma: errores.append("Debes seleccionar una plataforma.")
    if not solicitante.strip(): errores.append("El campo 'Solicitante' es obligatorio.")
    if not correo.strip():      errores.append("El campo 'Correo' es obligatorio.")
    if not motivo_solicitud.strip(): errores.append("El campo 'Motivo de la solicitud' es obligatorio.")
    if not numero_trafico.strip():
        errores.append("El campo 'Número de tráfico' es obligatorio.")
    else:
        numero_trafico_clean = numero_trafico.strip().upper()
        if not re.match(r"^[A-Z]{3}[0-9]{5}/[0-9]{2}$", numero_trafico_clean):
            errores.append("El número de tráfico debe tener formato AAA00000/00 (ej. SEP03873/25).")

    if empresa and SUCURSALES_POR_EMPRESA.get(empresa, []):
        if not sucursal or not str(sucursal).strip():
            errores.append("Debes seleccionar una sucursal.")

    blocks_to_validate = []
    if not es_desconclusion:
        blocks_to_validate = [("correcto", nuevo)]
        if tipo_complementaria == "Modificación":
            blocks_to_validate.insert(0, ("actual", actual))

    for label, block in blocks_to_validate:
        if not block["tipo"]:
            errores.append(f"Debes seleccionar 'Tipo Concepto' ({label}).")
        if block["tipo"] and get_conceptos(block["tipo"], plataforma_para_conceptos):
            if not block["concepto"] or "Sin datos" in str(block["concepto"]):
                errores.append(f"Debes seleccionar 'Concepto' ({label}).")
        if not str(block.get("proveedor", "")).strip():
            errores.append(f"Debes capturar 'Proveedor' ({label}).")
        if not block.get("moneda"):
            errores.append(f"Debes seleccionar 'Moneda' ({label}).")
        if block.get("importe") in [None, ""]:
            errores.append(f"Debes capturar 'Importe' ({label}).")
        if es_plataforma_logismex(plataforma_para_conceptos):
            if not block.get("tasa_iva"):
                errores.append(f"Debes seleccionar 'Tasa IVA' ({label}).")
            if block.get("tasa_iva") != "EXENTO" and not block.get("tasa_retencion"):
                errores.append(f"Debes seleccionar 'Tasa Retención' ({label}).")
            if not block.get("retencion_isr"):
                errores.append(f"Debes seleccionar 'Retención ISR' ({label}).")
        if not tipo_motivo_sel:
            errores.append("Debes seleccionar al menos un tipo de motivo.")

    if errores:
        for e in errores: st.error(e)
        st.stop()

    numero_trafico_clean = numero_trafico.strip().upper()

    # ── Validación de duplicados ──────────────────────────────────────────────
    if tipo_complementaria == "Desconclusión":
        try:
            dup_rows = (
                supabase.table("solicitudes_complementarias")
                .select("folio,fecha_captura,solicitante,estatus,tipo_complementaria")
                .eq("numero_trafico", numero_trafico_clean)
                .order("folio", desc=True).limit(20).execute().data or []
            )
        except Exception:
            dup_rows = []

        if dup_rows and not st.session_state.comp_confirm_ok:
            @st.dialog("ℹ️ Este tráfico ya tiene registros previos")
            def _dlg_desc():
                st.write(f"**Tráfico:** {numero_trafico_clean}")
                st.write(f"**Registros previos:** {len(dup_rows)}")
                for d in dup_rows[:8]:
                    st.write(
                        f"- **#{int(d.get('folio',0)):04d}** | {d.get('estatus','')} | "
                        f"{d.get('tipo_complementaria','')} | {d.get('solicitante','')}"
                    )
                st.info("Las desconclusiones no tienen límite. Puedes continuar.")
                if st.button("Continuar y registrar", type="primary"):
                    st.session_state.comp_confirm_ok = True
                    st.rerun()
            _dlg_desc()
            st.stop()

    if tipo_complementaria == "Modificación":
        previas = _check_duplicado_por_concepto(
            supabase, numero_trafico_clean, nuevo["tipo"], nuevo["concepto"]
        )
        if previas and not st.session_state.comp_confirm_ok:
            concepto_display = (
                f"{nuevo['tipo']} → {nuevo['concepto']}"
                if nuevo["tipo"] == "OTROS" and nuevo.get("concepto")
                else nuevo["tipo"]
            )
            @st.dialog("🚫 Ya existe una modificación para este concepto")
            def _dlg_block():
                st.write(f"**Tráfico:** {numero_trafico_clean}")
                st.error(
                    f"Ya se registró una Modificación para **{concepto_display}**. "
                    f"Solo se permite 1 modificación por concepto."
                )
                for d in previas[:5]:
                    st.write(
                        f"- **#{int(d.get('folio',0)):04d}** | {d.get('estatus','')} | "
                        f"{d.get('tipo_concepto_nuevo','')} | {d.get('concepto_nuevo','')}"
                    )
                st.caption("Para cambios adicionales contacta al equipo de auditoría.")
                st.button("Entendido", type="primary")
            _dlg_block()
            st.stop()

    # ── Historial inicial ─────────────────────────────────────────────────────
    if es_desconclusion:
        hist_details = f"Desconclusión registrada para tráfico {numero_trafico_clean}"
    elif tipo_complementaria == "Agregar Concepto":
        hist_details = (
            f"Agregar concepto: {nuevo['tipo']}"
            + (f" → {nuevo['concepto']}" if nuevo.get("concepto") else "")
            + f" | Importe: {nuevo['importe']}"
            + (f" {nuevo['moneda']}" if nuevo.get("moneda") else "")
        )
    else:
        hist_details = (
            f"Modificación: {nuevo['tipo']}"
            + (f" → {nuevo['concepto']}" if nuevo.get("concepto") else "")
            + f" | {actual.get('importe', 'N/A')} → {nuevo['importe']}"
            + (f" {nuevo['moneda']}" if nuevo.get("moneda") else "")
        )

    historial_inicial = [build_historial_entry(solicitante.strip(), "create", hist_details)]

    data_insert = {
        "fecha_captura": now_utc_iso(),
        "estatus": "Pendiente",
        "empresa": empresa,
        "sucursal": sucursal if sucursal else "N/A",
        "plataforma": plataforma,
        "solicitante": solicitante.strip(),
        "correo": correo_usuario,
        "motivo_solicitud": motivo_solicitud.strip(),
        "tipo_complementaria": tipo_complementaria,
        "numero_trafico": numero_trafico_clean,
        # Datos actuales
        "tipo_concepto_actual":      None if es_desconclusion else actual["tipo"],
        "concepto_actual":           None if es_desconclusion else (
            None if "Sin datos" in str(actual.get("concepto","")) else actual.get("concepto")),
        "proveedor_actual":          None if es_desconclusion else str(actual.get("proveedor","")).strip(),
        "moneda_actual":             None if es_desconclusion else actual.get("moneda"),
        "importe_actual":            None if es_desconclusion else (
            None if actual.get("importe") is None else float(actual["importe"])),
        # Datos nuevos
        "tipo_concepto_nuevo":       None if es_desconclusion else nuevo["tipo"],
        "concepto_nuevo":            None if es_desconclusion else (
            None if "Sin datos" in str(nuevo.get("concepto","")) else nuevo.get("concepto")),
        "proveedor_nuevo":           None if es_desconclusion else str(nuevo.get("proveedor","")).strip(),
        "moneda_nuevo":              None if es_desconclusion else nuevo.get("moneda"),
        "importe_nuevo":             None if es_desconclusion else float(nuevo["importe"]),
        # Campos fiscales Logismex
        "tasa_iva_actual":           None if es_desconclusion else actual.get("tasa_iva"),
        "tasa_retencion_actual":     None if es_desconclusion else actual.get("tasa_retencion"),
        "retencion_isr_actual":      None if es_desconclusion else actual.get("retencion_isr"),
        "monto_iva_actual":          None if es_desconclusion else actual.get("monto_iva"),
        "monto_retencion_actual":    None if es_desconclusion else actual.get("monto_retencion"),
        "monto_retencion_isr_actual":None if es_desconclusion else actual.get("monto_retencion_isr"),
        "total_actual":              None if es_desconclusion else actual.get("total"),
        "tasa_iva_nuevo":            None if es_desconclusion else nuevo.get("tasa_iva"),
        "tasa_retencion_nuevo":      None if es_desconclusion else nuevo.get("tasa_retencion"),
        "retencion_isr_nuevo":       None if es_desconclusion else nuevo.get("retencion_isr"),
        "monto_iva_nuevo":           None if es_desconclusion else nuevo.get("monto_iva"),
        "monto_retencion_nuevo":     None if es_desconclusion else nuevo.get("monto_retencion"),
        "monto_retencion_isr_nuevo": None if es_desconclusion else nuevo.get("monto_retencion_isr"),
        "total_nuevo":               None if es_desconclusion else nuevo.get("total"),
        # Gestión
        "fecha_resuelto": None, "fecha_ultima_modificacion": None,
        "auditor": None, "comentarios_auditor": None,
        "historial": historial_inicial,
        "tipo_motivo": tipo_motivo,
    }

    try:
        res = supabase.table("solicitudes_complementarias").insert(data_insert).execute()
        if not res.data:
            st.error("No se pudo insertar la solicitud en la base de datos.")
            st.stop()
        folio_num = int(res.data[0]["folio"])
    except Exception as e:
        st.error(f"Error al guardar: {e}")
        st.stop()

    folio_formateado = f"{folio_num:04d}"

    # ── Mailto ────────────────────────────────────────────────────────────────
    destinatarios = (
        ["julieta.reyna@palosgarza.com", "e-invoicing@palosgarza.com"]
        if tipo_complementaria == "Desconclusión"
        else ["auditoria.operaciones@palosgarza.com"]
    )
    subject = f"Complementaria #{folio_formateado} | {empresa} | Tráfico {numero_trafico_clean}"
    body = (
        f"Fecha: {datetime.now().strftime('%d/%m/%Y')}\n"
        f"Folio: #{folio_formateado}\nTráfico: {numero_trafico_clean}\n"
        f"Solicitó: {solicitante.strip()}\nCorreo: {correo_usuario}\n"
        f"Empresa: {empresa}\nSucursal: {sucursal or 'N/A'}\n"
        f"Plataforma: {plataforma}\nTipo: {tipo_complementaria}\n"
    )
    if not es_desconclusion:
        body += (
            f"\nConcepto nuevo: {nuevo['tipo']}"
            + (f" → {nuevo['concepto']}" if nuevo.get("concepto") else "")
            + f"\nImporte nuevo: ${nuevo['importe']:,.2f} {nuevo.get('moneda','')}\n"
        )
        if nuevo.get("tasa_iva"):
            body += (
                f"Tasa IVA: {nuevo['tasa_iva']}\n"
                f"Tasa Retención: {nuevo.get('tasa_retencion','N/A')}\n"
                f"Retención ISR: {nuevo.get('retencion_isr','N/A')}\n"
                f"Total calculado: ${nuevo.get('total',0):,.2f}\n"
            )

    st.session_state.comp_success_payload = {
        "folio": folio_formateado,
        "mailto": build_mailto(destinatarios, subject, body),
        "mensaje_manual": f"Mi folio de complementaria es el '#{folio_formateado}', favor de atender mi solicitud",
    }
    st.session_state.comp_confirm_ok = False
    st.rerun()
