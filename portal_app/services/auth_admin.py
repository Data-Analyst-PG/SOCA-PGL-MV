# portal_app/services/auth_admin.py
# ─────────────────────────────────────────────────────────────────────────────
# Operaciones de administración sobre Supabase Auth — crear usuarios y generar
# links de "establecer/restablecer contraseña", enviados por Resend en vez del
# correo genérico de Supabase.
#
# Mecanismo (sin depender de la config de Redirect URLs de Supabase):
#   1. auth.admin.generate_link(type="recovery") devuelve un hashed_token.
#   2. Ese token se manda en un link a NUESTRO propio dominio:
#        {LINK_APP}/?auth_token=...&auth_email=...
#   3. modules/auth/ui.py detecta ese query param y llama
#      auth.verify_otp({"token_hash":..., "type":"recovery"}) + update_user()
#      directo contra el cliente anon — sin necesidad de que Supabase redirija
#      a ningún lado.
#
# SOLO se importa desde módulos ya protegidos por permiso de admin
# (modules/administracion/*) y desde modules/auth/ui.py (login/forgot).
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import secrets as _secrets
import time
from typing import Optional

from services.supabase_client import get_service_client
from services.notificaciones import enviar_notificacion, LINK_APP


def _prop(obj, nombre: str):
    """Lee un atributo tanto si la respuesta del SDK es dict como objeto
    (igual que _campo() en notificaciones.py — el SDK de Supabase también
    ha cambiado de formato entre versiones)."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(nombre)
    return getattr(obj, nombre, None)


def crear_usuario_auth(email: str) -> Optional[str]:
    """Crea el usuario en Supabase Auth, ya confirmado (sin fricción de
    verificación de correo). La contraseña es aleatoria y nunca se usa —
    el usuario la establece él mismo vía el link de bienvenida.
    Devuelve el user_id o None si falló.
    El trigger on_auth_user_created ya crea la fila base en profiles."""
    try:
        sb = get_service_client()
        password_aleatoria = _secrets.token_urlsafe(24)
        res = sb.auth.admin.create_user({
            "email": email.strip().lower(),
            "password": password_aleatoria,
            "email_confirm": True,
        })
        user = _prop(res, "user")
        return _prop(user, "id")
    except Exception as e:
        raise RuntimeError(f"No se pudo crear el usuario en Auth: {e}")


def _generar_hashed_token(email: str) -> Optional[str]:
    """Genera un link de recuperación vía Admin API y extrae el hashed_token
    (no el link completo de Supabase — armamos nuestro propio link)."""
    sb = get_service_client()
    res = sb.auth.admin.generate_link({
        "type": "recovery",
        "email": email.strip().lower(),
    })
    props = _prop(res, "properties")
    token = _prop(props, "hashed_token")
    if not token:
        # Fallback por si esta versión del SDK devuelve la propiedad distinto
        token = _prop(res, "hashed_token")
    return token


def buscar_nombre_por_correo(email: str) -> Optional[str]:
    """Busca full_name en profiles a partir del correo (join con auth.users
    vía RPC no disponible desde el cliente — usamos el listado de usuarios
    de Admin API para resolver user_id, luego profiles)."""
    try:
        sb = get_service_client()
        res = sb.auth.admin.list_users()
        usuarios = res if isinstance(res, list) else _prop(res, "users") or []
        email_l = email.strip().lower()
        user_id = None
        for u in usuarios:
            if (_prop(u, "email") or "").strip().lower() == email_l:
                user_id = _prop(u, "id")
                break
        if not user_id:
            return None
        perfil = sb.table("profiles").select("full_name").eq("user_id", user_id).single().execute()
        return (perfil.data or {}).get("full_name")
    except Exception:
        return None


def enviar_link_password(email: str, nombre: str, es_bienvenida: bool) -> dict:
    """Genera el token y manda el correo (bienvenida o recuperación) vía
    Resend, reusando toda la infraestructura de enviar_notificacion()
    (plantilla, historial, idempotencia). Regresa {"ok": bool, "error": str|None}."""
    if not es_bienvenida:
        nombre_real = buscar_nombre_por_correo(email)
        if nombre_real:
            nombre = nombre_real

    try:
        token = _generar_hashed_token(email)
    except Exception as e:
        return {"ok": False, "error": f"No se pudo generar el link: {e}"}

    if not token:
        return {"ok": False, "error": "Supabase no devolvió un token válido (revisar formato de respuesta del SDK)."}

    link = f"{LINK_APP}/?auth_token={token}&auth_email={email.strip().lower()}"

    evento = "bienvenida" if es_bienvenida else "recuperar_password"
    resultado = enviar_notificacion(
        modulo="auth",
        evento=evento,
        folio=email.strip().lower(),          # no hay folio numérico — usamos el correo
        datos={"nombre": nombre or email, "link": link},
        correo_solicitante=email.strip().lower(),
        clave_unica=str(int(time.time())),    # cada solicitud es válida — no bloquear reenvíos
    )
    return {"ok": resultado.get("ok", False), "error": resultado.get("error")}
