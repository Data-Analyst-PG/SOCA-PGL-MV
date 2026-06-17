"""
banxico.py — Servicio de tipo de cambio FIX
Consulta el TC USD/MXN de Banxico una vez al día (cache 24h).
Token configurado en Streamlit secrets como TOKEN_BMX.
"""

from __future__ import annotations
import streamlit as st
import requests
from datetime import date


SERIE_FIX = "SF43718"  # Serie oficial del tipo de cambio FIX Banxico


@st.cache_data(show_spinner=False, ttl=86400)  # 24 horas
def get_tipo_cambio_fix() -> float:
    """
    Devuelve el tipo de cambio FIX USD/MXN del día desde Banxico.
    Si falla por cualquier razón, devuelve None para que el cotizador
    use su valor por defecto sin romper.
    """
    try:
        token = st.secrets["TOKEN_BMX"]
        url   = f"https://www.banxico.org.mx/SieAPIRest/service/v1/series/{SERIE_FIX}/datos/oportuno"
        resp  = requests.get(url, headers={"Bmx-Token": token}, timeout=5)
        resp.raise_for_status()
        data  = resp.json()
        valor = data["bmx"]["series"][0]["datos"][0]["dato"]
        return float(valor)
    except Exception:
        return None
