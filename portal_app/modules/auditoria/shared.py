# portal_app/modules/auditoria/shared.py
from __future__ import annotations

import re
from io import BytesIO
from typing import Dict
import pandas as pd
import streamlit as st
from services.auditoria import registrar_accion

def log_accion(modulo: str, accion: str, detalle: dict | None = None) -> None:
    """Wrapper de auditoría genérico — usado por las herramientas del módulo de auditoría (aud-*)."""
    registrar_accion(modulo, accion, detalle)


def get_empresa_config(nombre_empresa: str):
    """
    Config por empresa:
    - columnas base
    - si aplica filtro/validación de operador logístico
    - prefijo de remolque
    - etiqueta de distancia (Millas/Kilómetros)
    """
    if nombre_empresa == "Lincoln Freight":
        return {
            "candidates_fecha": ["Bill date", "Bill Date", "Fecha", "FECHA", "Date"],
            "candidates_customer": ["Customer", "Cliente", "cliente"],
            "candidates_trip": ["Trip Number", "Trip number", "TripNumber", "Viaje", "No Viaje", "Folio"],
            "candidates_trailer": ["Trailer", "Remolque", "remolque"],
            "candidates_unit": ["Unit", "Unidad", "unidad"],
            "candidates_dist": ["Real Miles", "Real miles", "REAL MILES", "Miles reales", "Real_miles", "Real Mi"],
            "candidates_operador": ["Logistic Operator", "Operador logistico", "Operador logístico"],
            "usa_operador": True,
            "trailer_prefix": "LF",
            "dist_label": "Millas",
        }

    if nombre_empresa == "Set Logis Plus":
        return {
            "candidates_fecha": ["Bill date", "Bill Date", "Fecha", "FECHA", "Date"],
            "candidates_customer": ["Customer", "Cliente", "cliente"],
            "candidates_trip": ["Trip Number", "Trip number", "TripNumber", "Viaje", "No Viaje", "Folio"],
            "candidates_trailer": ["Trailer", "Remolque", "remolque"],
            "candidates_unit": ["Unit", "Unidad", "unidad"],
            "candidates_dist": ["Real Miles", "Real miles", "REAL MILES", "Miles reales", "Real_miles", "Real Mi"],
            "candidates_operador": ["Logistic Operator", "Operador logistico", "Operador logístico"],
            "usa_operador": False,
            "trailer_prefix": "STL",
            "dist_label": "Millas",
        }

    if nombre_empresa == "Picus Carrier":
        return {
            "candidates_fecha": ["Fecha", "FECHA", "Bill date", "Bill Date", "Date"],
            "candidates_customer": ["Cliente", "cliente", "Customer"],
            "candidates_trip": ["Trip Number", "Trip number", "TripNumber", "Viaje", "No Viaje", "Folio", "Folio Viaje"],
            "candidates_trailer": ["Remolque", "remolque", "Trailer"],
            "candidates_unit": ["Unidad", "unidad", "Unit"],
            "candidates_dist": ["KMS Ruta", "Kms Ruta", "KMS_Ruta", "Kilometros", "Kilómetros", "KM", "KMS"],
            "candidates_operador": [],
            "usa_operador": False,
            "trailer_prefix": "PI",
            "dist_label": "Kilómetros",
        }

    # Igloo Carrier (default)
    return {
        "candidates_fecha": ["Fecha", "FECHA", "Bill date", "Bill Date", "Date"],
        "candidates_customer": ["Cliente", "cliente", "Customer"],
        "candidates_trip": ["Trip Number", "Trip number", "TripNumber", "Viaje", "No Viaje", "Folio", "Folio Viaje"],
        "candidates_trailer": ["Remolque", "remolque", "Trailer"],
        "candidates_unit": ["Unidad", "unidad", "Unit"],
        "candidates_dist": ["KMS Ruta", "Kms Ruta", "KMS_Ruta", "Kilometros", "Kilómetros", "KM", "KMS"],
        "candidates_operador": [],
        "usa_operador": False,
        "trailer_prefix": "IGT",
        "dist_label": "Kilómetros",
    }


def normaliza_tipo_distribucion(x):
    if x is None:
        return None
    s = str(x).strip()
    s_low = s.lower()
    if "volumen" in s_low:
        return "Volumen Viajes"
    if "remol" in s_low:
        return "Viajes con Remolque"
    if "unidad" in s_low:
        return "Viajes con unidad"
    if "milla" in s_low:
        return "Millas"
    if "km" in s_low or "kilo" in s_low:
        return "Kilómetros"
    return s


def find_column(df: pd.DataFrame, candidates: list[str]):
    """
    Encuentra la primera columna que matchea (ignorando espacios/_ y mayúsc/minúsc)
    """
    norm_map = {str(c).lower().replace(" ", "").replace("_", ""): c for c in df.columns}
    for cand in candidates:
        key = cand.lower().replace(" ", "").replace("_", "")
        if key in norm_map:
            return norm_map[key]
    return None


OPERADORES_EXCLUIR = {
    "ERICK LARA",
    "JULIETA REYNA",
    "GLADYS GUTIERREZ",
    "JUAN EDUARDO VILLARREAL VALDEZ",
    "LUIS ALDO VELIZ DE LEON",
    "VICTOR CHAVEZ SILVA",
    "ANETTE ROJO",
    "LUIS EDUARDO GUTIERREZ RAMIREZ",
    "GABRIEL ACOSTA VITAL",
    "GRISELDA JIMENEZ",
}


def build_flag_trailer(series_trailer: pd.Series, prefix: str) -> pd.Series:
    s = series_trailer.astype(str).str.strip().str.upper()
    return s.str.startswith(prefix).astype(int)

# -------------------------
# Excel export helper
# -------------------------
def to_excel_bytes_sheets(sheets: Dict[str, pd.DataFrame]) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        for name, df in sheets.items():
            if df is None:
                continue
            df.to_excel(writer, index=False, sheet_name=str(name)[:31])
    return buffer.getvalue()


# -------------------------
# Normalización sucursal
# -------------------------
def suc_key(x: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(x).strip().upper())


def homologar_sucursales_con_gts(df: pd.DataFrame, suc_validas: list[str], col="SUCURSAL"):
    """
    Usa las sucursales del GTS como verdad canónica y homologa variantes:
    "CAR GAR", "CAR-GAR", "CAR/GAR" -> "CAR-GAR" (según GTS)
    """
    df = df.copy()
    mapa = {suc_key(s): s for s in suc_validas}

    df[col] = df[col].astype(str).str.strip().str.upper()
    df[col + "_ORIG"] = df[col]
    df[col] = df[col].apply(lambda s: mapa.get(suc_key(s), s))

    no_recon = df[
        (~df[col].isin(["GASTO GENERAL", "INTERNO", "EXTERNO"])) &
        (~df[col].isin(suc_validas))
    ][col + "_ORIG"].dropna().astype(str).unique().tolist()

    return df, no_recon


# -------------------------
# Cached read excel helper
# -------------------------
@st.cache_data(show_spinner=False)
def read_excel_cached(file_bytes: bytes, sheet_name: str | int | None = 0) -> pd.DataFrame:
    import io
    bio = io.BytesIO(file_bytes)
    df = pd.read_excel(bio, sheet_name=sheet_name)
    return df
