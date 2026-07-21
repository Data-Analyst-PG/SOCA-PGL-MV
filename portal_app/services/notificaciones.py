# services/notificaciones.py
# ─────────────────────────────────────────────────────────────────────────────
# Servicio centralizado de notificaciones por correo para SOCA.
# Cualquier módulo (Complementarias, Tickets, Viáticos, etc.) llama solo a
# enviar_notificacion(...) — este archivo se encarga de plantilla, destinatarios,
# envío con Resend, historial, adjuntos y manejo de errores.
#
# Principio: el registro en Supabase SIEMPRE es más importante que el correo.
# Esta función nunca debe lanzar una excepción hacia quien la llama.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import re
from typing import Optional

import resend
import streamlit as st

from services.supabase_client import get_authed_client

REMITENTE = "Notificaciones PG Data Analyst <notificaciones@pgdataanalyst.com>"
LINK_APP  = "https://soca-pgl-mv-nxs7ubwktrszpsbg5z8ynj-pr0d1nter2026v2.streamlit.app"


def _campo(obj, nombre):
    """Lee un campo tanto si la respuesta es dict como si es un objeto
    (el SDK de Resend ha cambiado de formato entre versiones)."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(nombre)
    return getattr(obj, nombre, None)


def _set_resend_api_key() -> bool:
    try:
        resend.api_key = st.secrets["RESEND_API_KEY_V1"]
        return True
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# UTILIDADES DE CORREOS
# ═══════════════════════════════════════════════════════════════════════════════
def normalizar_correos(lista: list[str]) -> list[str]:
    """Limpia espacios, pasa a minúsculas y descarta vacíos."""
    vistos = []
    for c in lista or []:
        c = (c or "").strip().lower()
        if c and c not in vistos:
            vistos.append(c)
    return vistos


def eliminar_duplicados(to: list[str], cc: list[str], bcc: list[str]) -> tuple[list, list, list]:
    """Evita que un correo aparezca repetido entre To/CC/BCC.
    Prioridad: To > CC > BCC (si ya está en To, se quita de CC y BCC, etc.)."""
    to  = normalizar_correos(to)
    cc  = normalizar_correos([c for c in cc if c not in to])
    bcc = normalizar_correos([c for c in bcc if c not in to and c not in cc])
    return to, cc, bcc


# ═══════════════════════════════════════════════════════════════════════════════
# PLANTILLA
# ═══════════════════════════════════════════════════════════════════════════════
def obtener_plantilla(modulo: str, evento: str) -> Optional[dict]:
    """Trae la plantilla activa más reciente para modulo+evento."""
    try:
        supabase = get_authed_client()
        res = (
            supabase.table("plantillas_notificaciones")
            .select("*")
            .eq("modulo", modulo)
            .eq("evento", evento)
            .eq("activo", True)
            .order("version", desc=True)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        return rows[0] if rows else None
    except Exception:
        return None


_VAR_PATTERN = re.compile(r"\{(\w+)\}")


def renderizar_plantilla(texto: str, datos: dict) -> str:
    """Reemplaza {variable} por su valor en datos. Si falta, deja vacío
    en lugar de romper el envío."""
    if not texto:
        return ""

    def _reemplazo(match):
        clave = match.group(1)
        valor = datos.get(clave, "")
        return "" if valor is None else str(valor)

    return _VAR_PATTERN.sub(_reemplazo, texto)


# ═══════════════════════════════════════════════════════════════════════════════
# DESTINATARIOS
# ═══════════════════════════════════════════════════════════════════════════════
def obtener_destinatarios(
    modulo: str,
    evento: str,
    tipo_solicitud: Optional[str] = None,
    empresa: Optional[str] = None,
) -> dict:
    """Consulta destinatarios_notificaciones y regresa {"to": [...], "cc": [...], "bcc": [...]}.

    Reglas: aplica primero coincidencia exacta de tipo_solicitud, y dentro de
    eso incluye tanto las reglas generales (empresa = null) como las
    específicas de la empresa dada.
    """
    resultado = {"to": [], "cc": [], "bcc": []}
    try:
        supabase = get_authed_client()
        query = (
            supabase.table("destinatarios_notificaciones")
            .select("tipo_destinatario,correo")
            .eq("modulo", modulo)
            .eq("evento", evento)
            .eq("activo", True)
        )

        if tipo_solicitud:
            query = query.eq("tipo_solicitud", tipo_solicitud)
        else:
            query = query.is_("tipo_solicitud", "null")

        if empresa:
            query = query.or_(f"empresa.is.null,empresa.eq.{empresa}")
        else:
            query = query.is_("empresa", "null")

        rows = query.execute().data or []
        for r in rows:
            tipo = (r.get("tipo_destinatario") or "").lower()
            correo = r.get("correo")
            if tipo in resultado and correo:
                resultado[tipo].append(correo)
    except Exception:
        pass

    return resultado


# ═══════════════════════════════════════════════════════════════════════════════
# ADJUNTOS
# ═══════════════════════════════════════════════════════════════════════════════
def _construir_adjunto(adjunto: Optional[dict]) -> Optional[list]:
    """Convierte {"filename": str, "content_bytes": bytes} al formato que
    espera el SDK de Resend en Python: {"filename": str, "content": list(bytes)}.
    Regresa None si no hay adjunto o si el archivo pesa más de 35 MB
    (límite práctico de Resend para adjuntos)."""
    if not adjunto:
        return None
    contenido = adjunto.get("content_bytes")
    nombre = adjunto.get("filename")
    if not contenido or not nombre:
        return None
    if len(contenido) > 35 * 1024 * 1024:
        return None
    return [{"filename": nombre, "content": list(contenido)}]


# ═══════════════════════════════════════════════════════════════════════════════
# ENVÍO CON RESEND
# ═══════════════════════════════════════════════════════════════════════════════
def enviar_con_resend(
    to: list, cc: list, bcc: list, asunto: str, html: str, texto: str,
    in_reply_to: Optional[str] = None, references: Optional[list] = None,
    attachments: Optional[list] = None,
) -> dict:
    """Envía el correo. Regresa {"ok": bool, "resend_id": str|None, "error": str|None}.

    Nota: NO intenta leer el message_id aquí — justo después de enviar, Resend
    todavía tiene el correo en estado "queued" y el message_id real se asigna
    unos segundos después. Se recupera más tarde, de forma diferida, en
    obtener_hilo() la próxima vez que se necesite armar el hilo.
    """
    if not _set_resend_api_key():
        return {"ok": False, "resend_id": None, "error": "RESEND_API_KEY_V1 no configurada en secrets."}

    payload = {
        "from": REMITENTE,
        "to": to,
        "subject": asunto,
        "html": html,
    }
    if texto:
        payload["text"] = texto
    if cc:
        payload["cc"] = cc
    if bcc:
        payload["bcc"] = bcc
    if attachments:
        payload["attachments"] = attachments

    # ── Headers de hilo (Fase 5) ────────────────────────────────────────────
    if in_reply_to or references:
        headers = {}
        if in_reply_to:
            headers["In-Reply-To"] = in_reply_to
        if references:
            headers["References"] = " ".join(references)
        payload["headers"] = headers

    try:
        respuesta = resend.Emails.send(payload)
        resend_id = _campo(respuesta, "id")
        return {"ok": True, "resend_id": resend_id, "error": None}
    except Exception as e:
        return {"ok": False, "resend_id": None, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# HISTORIAL
# ═══════════════════════════════════════════════════════════════════════════════
def _idempotency_key(modulo: str, folio: str, evento: str, version: int = 1, sufijo: Optional[str] = None) -> str:
    extra = f":{sufijo}" if sufijo else ""
    return f"{modulo}:{folio}:{evento}:v{version}{extra}"


def _ya_enviado(idempotency_key: str) -> bool:
    """True si ya existe un historial exitoso con esta llave (evita duplicados)."""
    try:
        supabase = get_authed_client()
        res = (
            supabase.table("historial_notificaciones")
            .select("id,estado")
            .eq("idempotency_key", idempotency_key)
            .eq("estado", "enviado")
            .limit(1)
            .execute()
        )
        return bool(res.data)
    except Exception:
        return False


def obtener_hilo(modulo: str, folio: str) -> list[str]:
    """Regresa los Message-ID de todos los correos ya enviados para este
    folio, en orden cronológico — para armar In-Reply-To / References.

    Si algún correo previo todavía no tiene message_id guardado (porque se
    mandó hace muy poco y Resend aún no se lo asignaba), lo busca ahora
    directo en Resend y lo guarda en Supabase para no tener que pedirlo otra vez.
    """
    try:
        supabase = get_authed_client()
        res = (
            supabase.table("historial_notificaciones")
            .select("id,resend_id,message_id")
            .eq("modulo", modulo)
            .eq("folio", str(folio))
            .eq("estado", "enviado")
            .order("fecha_creacion", desc=False)
            .execute()
        )
        filas = res.data or []
    except Exception:
        return []

    resultado = []
    api_key_lista = False

    for fila in filas:
        mid = fila.get("message_id")

        if not mid and fila.get("resend_id"):
            if not api_key_lista:
                api_key_lista = _set_resend_api_key()
            if api_key_lista:
                try:
                    detalle = resend.Emails.get(fila["resend_id"])
                    mid = _campo(detalle, "message_id")
                    if mid:
                        supabase.table("historial_notificaciones").update(
                            {"message_id": mid}
                        ).eq("id", fila["id"]).execute()
                except Exception:
                    pass

        if mid:
            resultado.append(mid)

    return resultado


def registrar_historial(
    modulo: str, folio: str, evento: str, asunto: str,
    to: list, cc: list, bcc: list,
    estado: str, resend_id: Optional[str], error: Optional[str],
    datos_evento: dict, idempotency_key: str,
) -> None:
    try:
        supabase = get_authed_client()
        supabase.table("historial_notificaciones").insert({
            "modulo": modulo,
            "folio": str(folio),
            "evento": evento,
            "asunto": asunto,
            "remitente": REMITENTE,
            "destinatarios_to": to,
            "destinatarios_cc": cc,
            "destinatarios_bcc": bcc,
            "resend_id": resend_id,
            "estado": estado,
            "error": error,
            "datos_evento": datos_evento,
            "idempotency_key": idempotency_key,
        }).execute()
    except Exception:
        # Si ya existe (choque de idempotency_key) o falla el log, no rompemos el flujo.
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL — la única que deben llamar los módulos
# ═══════════════════════════════════════════════════════════════════════════════
def enviar_notificacion(
    modulo: str,
    evento: str,
    folio: str,
    datos: dict,
    tipo_solicitud: Optional[str] = None,
    empresa: Optional[str] = None,
    correo_solicitante: Optional[str] = None,
    clave_unica: Optional[str] = None,
    adjunto: Optional[dict] = None,
) -> dict:
    """
    Punto de entrada único para todos los módulos.

    datos: dict con las variables para la plantilla, ej.
        {"solicitante": ..., "empresa": ..., "sucursal": ..., "plataforma": ...,
         "tipo": ..., "motivo": ..., "numero_trafico": ..., "estatus": ...,
         "fecha_captura": ...}

    correo_solicitante: correo del usuario que generó el evento — se agrega
        dinámicamente al "to" (no vive en la tabla de destinatarios porque
        cambia con cada solicitud).

    clave_unica: opcional — para que un mismo folio+evento pueda repetirse
        (ej. el estatus regresa a un valor ya usado) sin que la protección
        anti-duplicados lo bloquee.

    adjunto: opcional — {"filename": "factura.pdf", "content_bytes": <bytes>}
        para adjuntar un archivo (ej. la factura) al correo.

    Regresa {"ok": bool, "ya_enviado": bool, "error": str|None} — nunca lanza excepción.
    """
    idem_key = _idempotency_key(modulo, folio, evento, sufijo=clave_unica)

    if _ya_enviado(idem_key):
        return {"ok": True, "ya_enviado": True, "error": None}

    plantilla = obtener_plantilla(modulo, evento)
    if not plantilla:
        registrar_historial(
            modulo, folio, evento, "", [], [], [],
            "error", None, "No se encontró plantilla activa.", datos, idem_key,
        )
        return {"ok": False, "ya_enviado": False, "error": "Plantilla no encontrada."}

    destinatarios = obtener_destinatarios(modulo, evento, tipo_solicitud, empresa)

    to  = list(destinatarios["to"])
    cc  = list(destinatarios["cc"])
    bcc = list(destinatarios["bcc"])

    if correo_solicitante:
        to.append(correo_solicitante)

    to, cc, bcc = eliminar_duplicados(to, cc, bcc)

    if not to:
        registrar_historial(
            modulo, folio, evento, "", to, cc, bcc,
            "error", None, "Sin destinatarios configurados.", datos, idem_key,
        )
        return {"ok": False, "ya_enviado": False, "error": "Sin destinatarios configurados."}

    datos_render = dict(datos)
    datos_render.setdefault("folio", folio)
    datos_render.setdefault("link_app", LINK_APP)

    asunto = renderizar_plantilla(plantilla.get("asunto", ""), datos_render)
    html   = renderizar_plantilla(plantilla.get("cuerpo_html", ""), datos_render)
    texto  = renderizar_plantilla(plantilla.get("cuerpo_texto", ""), datos_render)

    hilo_previo = obtener_hilo(modulo, folio)
    in_reply_to = hilo_previo[-1] if hilo_previo else None
    attachments = _construir_adjunto(adjunto)

    resultado = enviar_con_resend(
        to, cc, bcc, asunto, html, texto,
        in_reply_to=in_reply_to,
        references=hilo_previo if hilo_previo else None,
        attachments=attachments,
    )

    registrar_historial(
        modulo, folio, evento, asunto, to, cc, bcc,
        "enviado" if resultado["ok"] else "error",
        resultado["resend_id"], resultado["error"],
        datos, idem_key,
    )

    return {"ok": resultado["ok"], "ya_enviado": False, "error": resultado["error"]}
