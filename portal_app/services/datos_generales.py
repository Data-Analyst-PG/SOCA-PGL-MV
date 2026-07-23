"""
services/datos_generales.py
Persistencia de "Datos Generales" (parámetros configurables) de los cotizadores.

Reemplaza el patrón anterior basado en CSV local (efímero en Streamlit Cloud —
se perdía en cada reinicio/redeploy) por la tabla `datos_generales_cotizadores`
en Supabase (una fila por empresa, valores en JSONB).

Uso desde cada _helpers.py de cotizador:
    from services.datos_generales import (
        cargar_datos_generales as _cargar_dg,
        guardar_datos_generales as _guardar_dg,
    )

    def cargar_datos_generales() -> dict:
        return _cargar_dg("igloo", DEFAULTS, tc_key="Tipo de cambio USD")

    def guardar_datos_generales(valores: dict) -> None:
        _guardar_dg("igloo", valores)
"""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from services.supabase_client import get_authed_client

TABLE = "datos_generales_cotizadores"


@st.cache_data(show_spinner=False, ttl=60)
def _leer_valores_guardados(empresa: str) -> dict:
    """Lee los valores guardados para una empresa. Cache corto (60s) para no
    golpear Supabase en cada rerun de Streamlit."""
    sb = get_authed_client()
    if sb is None:
        return {}
    try:
        res = (
            sb.table(TABLE)
            .select("valores")
            .eq("empresa", empresa)
            .maybe_single()
            .execute()
        )
        data = res.data or {}
        return data.get("valores") or {}
    except Exception:
        return {}


def cargar_datos_generales(empresa: str, defaults: dict, tc_key: str | None = None) -> dict:
    """
    Fusiona DEFAULTS del cotizador con lo guardado en Supabase para `empresa`.
    Si `tc_key` se especifica y Banxico está disponible, sobreescribe ese
    parámetro con el valor FIX del día (cacheado 24h en services.banxico),
    igual que el comportamiento anterior basado en CSV.
    """
    guardados = _leer_valores_guardados(empresa)
    resultado = {**defaults, **guardados}

    if tc_key:
        try:
            from services.banxico import get_tipo_cambio_fix
            token = st.secrets.get("TOKEN_BMX", "")
            tc = get_tipo_cambio_fix(token) if token else None
            if tc:
                resultado[tc_key] = tc
        except Exception:
            pass  # si Banxico falla, conserva el valor guardado sin romper nada

    return resultado


def guardar_datos_generales(empresa: str, valores: dict) -> None:
    """Guarda (upsert) el diccionario de valores para `empresa` en Supabase."""
    sb = get_authed_client()
    if sb is None:
        raise RuntimeError("Supabase no configurado.")

    u = None
    try:
        from services.supabase_client import current_user
        u = (current_user() or {}).get("id") or (current_user() or {}).get("sub")
    except Exception:
        pass

    payload = {
        "empresa": empresa,
        "valores": valores,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if u:
        payload["updated_by"] = u

    sb.table(TABLE).upsert(payload, on_conflict="empresa").execute()
    _leer_valores_guardados.clear()  # invalidar cache para que el próximo load traiga lo nuevo
