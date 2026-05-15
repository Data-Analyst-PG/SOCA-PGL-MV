import io
import re
from io import BytesIO

import pandas as pd
import streamlit as st


# =====================================================
# UTILIDADES
# =====================================================

MESES = {
    "enero": "Enero",
    "febrero": "Febrero",
    "marzo": "Marzo",
    "abril": "Abril",
    "mayo": "Mayo",
    "junio": "Junio",
    "julio": "Julio",
    "agosto": "Agosto",
    "septiembre": "Septiembre",
    "setiembre": "Septiembre",
    "octubre": "Octubre",
    "noviembre": "Noviembre",
    "diciembre": "Diciembre",
}

ORDEN_MESES = [
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
]

CUENTA_COMPLETA_RE = re.compile(r"^\d{3}-\d{2}-\d{2}-\d{3}-\d{5}$")


def _normalize_text(x) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip()


def _to_num_safe(x):
    if pd.isna(x):
        return 0.0

    s = str(x).replace(",", "").replace("$", "").strip()

    if s in ("", "-", "nan", "None"):
        return 0.0

    try:
        return float(s)
    except Exception:
        return 0.0


def _read_excel_any(uploaded_file) -> pd.DataFrame:
    """
    Lee la primera hoja del archivo sin asumir header fijo.
    Devuelve todo como DataFrame crudo.
    """
    raw = uploaded_file.read() if hasattr(uploaded_file, "read") else uploaded_file
    bio = io.BytesIO(raw)
    bio.seek(0)
    return pd.read_excel(bio, sheet_name=0, header=None, engine="openpyxl")


def _is_month_name(value) -> bool:
    txt = _normalize_text(value).lower()
    return txt in MESES


def _month_title(value) -> str:
    txt = _normalize_text(value).lower()
    return MESES.get(txt, _normalize_text(value))


# =====================================================
# BALANZA DE COMPROBACIÓN
# =====================================================

def _find_header_row_comprobacion(df_raw: pd.DataFrame) -> int:
    """
    Busca la fila que contiene:
    Cuenta | Descripción | Saldo Inicial | Cargos | Abonos | Saldo Final
    """
    limit = min(30, len(df_raw))

    for i in range(limit):
        row = [str(x).strip().lower() for x in df_raw.iloc[i].tolist()]
        joined = " | ".join(row)

        if (
            "cuenta" in joined
            and ("descripción" in joined or "descripcion" in joined)
            and "cargos" in joined
            and "abonos" in joined
        ):
            return i

    raise ValueError("No encontré la fila de encabezados de la balanza de comprobación.")


def _extract_month_name(df_raw: pd.DataFrame) -> str:
    """
    Busca el texto tipo:
    'Del 1 de marzo al 31 de marzo de 2026'
    y devuelve 'Marzo'.
    """
    scan_rows = min(15, len(df_raw))
    scan_cols = min(15, df_raw.shape[1])

    for r in range(scan_rows):
        for c in range(scan_cols):
            val = str(df_raw.iat[r, c]).strip().lower()

            if "del 1 de" in val or "al 31 de" in val or "de 202" in val:
                for mes_lower, mes_title in MESES.items():
                    if mes_lower in val:
                        return mes_title

    return "Mes"


def _prepare_balanza_comprobacion_dataframe(df_raw: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """
    Convierte el raw de balanza de comprobación en columnas estándar.
    """
    month_name = _extract_month_name(df_raw)
    header_row = _find_header_row_comprobacion(df_raw)

    df = df_raw.iloc[header_row + 1:].reset_index(drop=True).copy()

    df.columns = ["Cuenta", "Descripción", "Saldo Inicial", "Cargos", "Abonos", "Saldo Final"] + [
        f"extra_{i}" for i in range(max(0, df.shape[1] - 6))
    ]

    df = df.iloc[:, :6].copy()

    df["Cuenta"] = df["Cuenta"].astype(str).str.strip()
    df["Descripción"] = df["Descripción"].astype(str).str.strip()

    df["Saldo Inicial"] = df["Saldo Inicial"].apply(_to_num_safe)
    df["Cargos"] = df["Cargos"].apply(_to_num_safe)
    df["Abonos"] = df["Abonos"].apply(_to_num_safe)
    df["Saldo Final"] = df["Saldo Final"].apply(_to_num_safe)

    return df, month_name


def transformar_balanza_comprobacion_a_mensual(df_raw: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """
    Toma la balanza de comprobación y produce:
    Resumen cuenta | Cuenta | Concepto | [Mes]
    """
    df, month_name = _prepare_balanza_comprobacion_dataframe(df_raw)

    df = df[df["Cuenta"].str.match(CUENTA_COMPLETA_RE, na=False)].copy()

    df["Resumen cuenta"] = df["Cuenta"].str[:3]
    df[month_name] = df["Abonos"] - df["Cargos"]

    out = df[["Resumen cuenta", "Cuenta", "Descripción", month_name]].copy()
    out = out.rename(columns={"Descripción": "Concepto"})

    out["Resumen cuenta"] = pd.to_numeric(out["Resumen cuenta"], errors="coerce").fillna(0).astype(int)
    out["Cuenta"] = out["Cuenta"].astype(str).str.strip()
    out["Concepto"] = out["Concepto"].astype(str).str.strip()
    out[month_name] = pd.to_numeric(out[month_name], errors="coerce").fillna(0.0)

    return out.reset_index(drop=True), month_name


# =====================================================
# BALANZA COMPARATIVA
# =====================================================

def _find_header_rows_comparativa(df_raw: pd.DataFrame) -> tuple[int, int]:
    """
    Detecta balanza comparativa con encabezados en 2 filas.

    Ejemplo:
    Fila superior:  Total | Mayo | Abril | Marzo | Febrero | Enero
    Fila inferior:  Cuenta | Descripción
    """
    limit = min(30, len(df_raw))

    for i in range(limit - 1):
        row_top = [_normalize_text(x).lower() for x in df_raw.iloc[i].tolist()]
        row_bottom = [_normalize_text(x).lower() for x in df_raw.iloc[i + 1].tolist()]

        top_has_month = any(x in MESES for x in row_top)
        bottom_has_cuenta = any(x == "cuenta" for x in row_bottom)
        bottom_has_desc = any(x in ("descripción", "descripcion") for x in row_bottom)

        if top_has_month and bottom_has_cuenta and bottom_has_desc:
            return i, i + 1

    raise ValueError("No encontré los encabezados de la balanza comparativa.")


def _build_comparativa_columns(df_raw: pd.DataFrame, top_row: int, bottom_row: int) -> tuple[list[str], list[str]]:
    """
    Construye los nombres de columnas finales para una balanza comparativa.

    Devuelve:
    - columnas finales para asignar al DataFrame
    - meses detectados
    """
    columns = []
    months_found = []

    for col_idx in range(df_raw.shape[1]):
        top = _normalize_text(df_raw.iat[top_row, col_idx])
        bottom = _normalize_text(df_raw.iat[bottom_row, col_idx])

        bottom_lower = bottom.lower()
        top_lower = top.lower()

        if bottom_lower == "cuenta":
            columns.append("Cuenta")
            continue

        if bottom_lower in ("descripción", "descripcion"):
            columns.append("Descripción")
            continue

        if top_lower in MESES:
            month_name = MESES[top_lower]
            columns.append(month_name)
            months_found.append(month_name)
            continue

        if top_lower == "total":
            columns.append("Total")
            continue

        columns.append(f"extra_{col_idx}")

    # Quita duplicados conservando el primer mes encontrado
    months_found_unique = []
    for mes in months_found:
        if mes not in months_found_unique:
            months_found_unique.append(mes)

    return columns, months_found_unique


def transformar_balanza_comparativa(df_raw: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """
    Toma la balanza comparativa y produce:
    Cuenta | Descripción | [Meses detectados]

    Los meses son dinámicos:
    - Si viene solo Enero, solo sale Enero.
    - Si viene Enero a Mayo, salen esos 5 meses.
    - Si viene Enero a Diciembre, salen los 12 meses.
    """
    top_row, bottom_row = _find_header_rows_comparativa(df_raw)
    columns, months_found = _build_comparativa_columns(df_raw, top_row, bottom_row)

    if not months_found:
        raise ValueError("No encontré columnas de meses en la balanza comparativa.")

    df = df_raw.iloc[bottom_row + 1:].reset_index(drop=True).copy()
    df.columns = columns

    keep_cols = ["Cuenta", "Descripción"] + months_found

    missing = [c for c in ["Cuenta", "Descripción"] if c not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas obligatorias en la balanza comparativa: {missing}")

    df = df[keep_cols].copy()

    df["Cuenta"] = df["Cuenta"].astype(str).str.strip()
    df["Descripción"] = df["Descripción"].astype(str).str.strip()

    df = df[df["Cuenta"].str.match(CUENTA_COMPLETA_RE, na=False)].copy()

    for mes in months_found:
        df[mes] = df[mes].apply(_to_num_safe)

    # Orden cronológico opcional: Enero, Febrero, Marzo...
    # Si prefieres respetar el orden del archivo, cambia esta línea por:
    # ordered_months = months_found
    ordered_months = [m for m in ORDEN_MESES if m in months_found]

    out = df[["Cuenta", "Descripción"] + ordered_months].copy()

    return out.reset_index(drop=True), ordered_months


# =====================================================
# DETECCIÓN AUTOMÁTICA DE FORMATO
# =====================================================

def detectar_tipo_balanza(df_raw: pd.DataFrame) -> str:
    """
    Detecta automáticamente si el archivo es:
    - comparativa
    - comprobacion
    """
    try:
        _find_header_rows_comparativa(df_raw)
        return "comparativa"
    except Exception:
        pass

    try:
        _find_header_row_comprobacion(df_raw)
        return "comprobacion"
    except Exception:
        pass

    raise ValueError(
        "No pude identificar el formato del archivo. "
        "Debe ser una balanza de comprobación o una balanza comparativa."
    )


def transformar_balanza(df_raw: pd.DataFrame) -> tuple[pd.DataFrame, str, list[str]]:
    """
    Transforma automáticamente según el tipo de archivo.

    Devuelve:
    - DataFrame final
    - tipo de balanza
    - meses/mes detectado
    """
    tipo = detectar_tipo_balanza(df_raw)

    if tipo == "comparativa":
        df_final, meses = transformar_balanza_comparativa(df_raw)
        return df_final, tipo, meses

    df_final, mes = transformar_balanza_comprobacion_a_mensual(df_raw)
    return df_final, tipo, [mes]


def dataframe_to_excel_bytes(df: pd.DataFrame, sheet_name: str = "REPORTE") -> bytes:
    buf = BytesIO()

    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)

        ws = writer.sheets[sheet_name]

        for col in ws.columns:
            max_len = 0
            col_letter = col[0].column_letter

            for cell in col:
                try:
                    val = "" if cell.value is None else str(cell.value)
                    max_len = max(max_len, len(val))
                except Exception:
                    pass

            ws.column_dimensions[col_letter].width = min(max_len + 2, 45)

        # Formato numérico para columnas de importes
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                if isinstance(cell.value, (int, float)):
                    cell.number_format = '#,##0.00'

    return buf.getvalue()


# =====================================================
# STREAMLIT
# =====================================================

def render():
    from ui.components import page_banner, section_header, alert, divider
    page_banner("📘", "Balanza Mensual", "Convierte balanza de comprobación o comparativa a formato mensual")

    st.caption(
        "Sube un archivo de balanza de comprobación o balanza comparativa. "
        "El sistema detectará automáticamente el formato."
    )

    uploaded_file = st.file_uploader(
        "Sube el archivo de balanza (.xlsx)",
        type=["xlsx"],
        accept_multiple_files=False,
    )

    if not uploaded_file:
        alert("info", "Sube un archivo para procesarlo.")
        return

    try:
        df_raw = _read_excel_any(uploaded_file)
        df_final, tipo, meses = transformar_balanza(df_raw)

        if tipo == "comparativa":
            st.success(
                f"✅ Balanza comparativa procesada. "
                f"Meses detectados: {', '.join(meses)}. "
                f"Filas finales: {len(df_final):,}"
            )
            file_name = "Balanza_Comparativa_Procesada.xlsx"
            sheet_name = "COMPARATIVA"
        else:
            st.success(
                f"✅ Balanza de comprobación procesada. "
                f"Mes detectado: {meses[0]}. "
                f"Filas finales: {len(df_final):,}"
            )
            file_name = f"Balanza_{meses[0]}.xlsx"
            sheet_name = meses[0].upper()

        st.dataframe(df_final, use_container_width=True)

        excel_bytes = dataframe_to_excel_bytes(df_final, sheet_name=sheet_name)

        st.download_button(
            "⬇️ Descargar Excel procesado",
            data=excel_bytes,
            file_name=file_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    except Exception as e:
        st.error(f"Ocurrió un error procesando la balanza: {e}")
        st.exception(e)
