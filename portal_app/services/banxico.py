"""
banxico.py — Servicio de tipo de cambio FIX
Consulta el TC USD/MXN de Banxico una vez al día (cache 24h).
Token configurado en Streamlit secrets como TOKEN_BMX.
"""

from __future__ import annotations
import requests
import streamlit as st

SERIE_FIX = "SF43718"


@st.cache_data(show_spinner=False, ttl=86400)
def get_tipo_cambio_fix(token: str) -> float | None:
    """
    Recibe el token como parámetro para que st.cache_data funcione correctamente.
    """
    try:
        url  = f"https://www.banxico.org.mx/SieAPIRest/service/v1/series/{SERIE_FIX}/datos/oportuno"
        resp = requests.get(url, headers={"Bmx-Token": token}, timeout=5)
        resp.raise_for_status()
        data  = resp.json()
        valor = data["bmx"]["series"][0]["datos"][0]["dato"]
        return float(valor)
    except Exception:
        return None
