# portal_app/modules/auditoria/reporte_auxiliares.py
import streamlit as st
import pandas as pd
import re
from io import BytesIO
import io

# Imports opcionales (para HTML “tipo Excel”)
try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

try:
    from lxml import etree
except Exception:
    etree = None


# =====================================================
# --- UTILIDADES BÁSICAS ---
# =====================================================

def _to_num_safe(x):
    if pd.isna(x):
        return 0.0
    s = str(x).replace(",", "").replace("$", "").strip()
    try:
        return float(s)
    except Exception:
        return 0.0


def _drop_summary_rows(df: pd.DataFrame, cols: list[str] | None = None) -> pd.DataFrame:
    if cols is None:
        cols = list(df.columns)

    summary_re = re.compile(
        r"^\s*(sumas?\s+totales?|suma\s+total|totales?|total|saldo|saldos?|saldo\s+inicial:?)\s*$",
        re.IGNORECASE,
    )

    mask = pd.Series(False, index=df.index)
    for c in cols:
        if c in df.columns:
            mask |= (
                df[c].astype(str)
                    .str.replace("\xa0", " ", regex=False)
                    .str.strip()
                    .str.match(summary_re)
            )
    return df.loc[~mask].reset_index(drop=True)


def _read_excel_any(uploaded_file):
    raw = uploaded_file.read() if hasattr(uploaded_file, "read") else uploaded_file
    bio = io.BytesIO(raw)

    head = raw[:4096]
    head_stripped = head.lstrip().lower()

    def _as_str(df: pd.DataFrame) -> pd.DataFrame:
        return df.fillna("").astype(str)

    # 1) XLSX (ZIP)
    if head.startswith(b"PK"):
        bio.seek(0)
        return _as_str(pd.read_excel(bio, sheet_name=0, engine="openpyxl", header=None))

    # 2) XLS (CFBF/BIFF)
    if head.startswith(b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"):
        bio.seek(0)
        try:
            return _as_str(pd.read_excel(bio, sheet_name=0, engine="xlrd", header=None))
        except Exception:
            bio.seek(0)
            return _as_str(pd.read_excel(bio, sheet_name=0, header=None))

    # 3) HTML (incluye .xls “disfrazado”)
    is_html = (
        head_stripped.startswith(b"<!doctype html")
        or head_stripped.startswith(b"<html")
        or (b"<table" in head_stripped[:1024])
        or (b"xmlns:x=\"urn:schemas-microsoft-com:office:excel\"" in head)
    )
    if is_html:
        # Si no existen dependencias, avisa bonito
        if BeautifulSoup is None or etree is None:
            raise ValueError(
                "El archivo parece HTML tipo Excel, pero faltan dependencias: "
                "instala 'beautifulsoup4' y 'lxml'."
            )

        # 3.a: intento con read_html
        bio.seek(0)
        try:
            tables = pd.read_html(bio, header=None, flavor="lxml")
            if tables:
                return _as_str(tables[0])
        except Exception:
            pass

        # 3.b: BeautifulSoup primera tabla
        bio.seek(0)
        soup = BeautifulSoup(bio.read(), "lxml")

        def _is_table(tag):
            if not getattr(tag, "name", None):
                return False
            name = tag.name.lower()
            return name == "table" or name.endswith(":table")

        table = soup.find(_is_table)
        if table:
            def _match(tag, names):
                if not getattr(tag, "name", None):
                    return False
                n = tag.name.lower()
                return (n in names) or any(n.endswith(":" + nm) for nm in names)

            rows = []
            for tr in table.find_all(lambda t: _match(t, {"tr"})):
                cells = [td.get_text(strip=True) for td in tr.find_all(lambda t: _match(t, {"td", "th"}))]
                if cells:
                    rows.append(cells)
            if rows:
                width = max(len(r) for r in rows)
                rows = [r + [""] * (width - len(r)) for r in rows]
                return _as_str(pd.DataFrame(rows))

        # 3.c: SpreadsheetML incrustado
        xml_block = soup.find("xml")
        if xml_block and ("urn:schemas-microsoft-com:office:spreadsheet" in xml_block.text):
            xml_bytes = xml_block.text.encode("utf-8", errors="ignore")
            try:
                tree = etree.fromstring(xml_bytes)
            except Exception:
                try:
                    tree = etree.XML(xml_bytes)
                except Exception:
                    tree = None

            if tree is not None:
                ns = {"ss": "urn:schemas-microsoft-com:office:spreadsheet"}
                table = tree.find(".//ss:Worksheet/ss:Table", namespaces=ns)
                if table is not None:
                    rows = []
                    for row in table.findall("ss:Row", namespaces=ns):
                        row_vals, cur_col = [], 1
                        for cell in row.findall("ss:Cell", namespaces=ns):
                            idx = cell.get("{urn:schemas-microsoft-com:office:spreadsheet}Index")
                            if idx is not None:
                                idx = int(idx)
                                while cur_col < idx:
                                    row_vals.append("")
                                    cur_col += 1
                            data_el = cell.find("ss:Data", namespaces=ns)
                            val = data_el.text if data_el is not None else ""
                            row_vals.append(val if val is not None else "")
                            cur_col += 1
                        rows.append(row_vals)
                    if rows:
                        width = max(len(r) for r in rows)
                        rows = [r + [""] * (width - len(r)) for r in rows]
                        return _as_str(pd.DataFrame(rows))

        raise ValueError("El archivo es HTML pero no contiene una tabla utilizable.")

    # 4) SpreadsheetML (XML plano)
    if (b"<Workbook" in head) or (b"urn:schemas-microsoft-com:office:spreadsheet" in head):
        if etree is None:
            raise ValueError("El archivo es XML SpreadsheetML pero falta 'lxml'.")
        bio.seek(0)
        tree = etree.parse(bio)
        ns = {"ss": "urn:schemas-microsoft-com:office:spreadsheet"}
        table = tree.find(".//ss:Worksheet/ss:Table", namespaces=ns)
        if table is None:
            raise ValueError("XML SpreadsheetML sin <Worksheet>/<Table>.")
        rows = []
        for row in table.findall("ss:Row", namespaces=ns):
            row_vals, cur_col = [], 1
            for cell in row.findall("ss:Cell", namespaces=ns):
                idx = cell.get("{urn:schemas-microsoft-com:office:spreadsheet}Index")
                if idx is not None:
                    idx = int(idx)
                    while cur_col < idx:
                        row_vals.append("")
                        cur_col += 1
                data_el = cell.find("ss:Data", namespaces=ns)
                val = data_el.text if data_el is not None else ""
                row_vals.append(val if val is not None else "")
                cur_col += 1
            rows.append(row_vals)
        if rows:
            width = max(len(r) for r in rows)
            rows = [r + [""] * (width - len(r)) for r in rows]
            return _as_str(pd.DataFrame(rows))

    # 5) Último intento
    bio.seek(0)
    try:
        return _as_str(pd.read_excel(bio, sheet_name=0, engine="openpyxl", header=None))
    except Exception:
        bio.seek(0)
        return _as_str(pd.read_excel(bio, sheet_name=0, engine="xlrd", header=None))


# =====================================================
# --- DETECCIÓN DEL MODO ---
# =====================================================

def _detect_mode(df_raw: pd.DataFrame) -> str:
    try:
        df_guess, _ = _guess_header(df_raw.copy())
    except Exception:
        df_guess = df_raw.copy()

    cols_norm = [str(c).strip().lower().replace("\xa0", " ") for c in df_guess.columns]
    header_join = " ".join(cols_norm)

    # STAR 1 Balanza: tiene columna Poliza, pero las cuentas vienen como filas padre
    # en la misma columna Poliza y el concepto de cuenta viene a un lado.
    # Ejemplo: 200-01-01-001-01-001-0001 | SUELDO A OPERADORES | ... | Saldo Inicial:
    if any(c == "poliza" for c in cols_norm):
        sample = df_guess.head(80).fillna("").astype(str)
        first_col = sample.iloc[:, 0].str.replace("\xa0", " ", regex=False).str.strip() if sample.shape[1] else pd.Series(dtype=str)
        has_balanza_parent = first_col.str.match(
            r"^\d{3}-\d{2}-\d{2}-\d{3}-\d{2}-\d{3}-\d{4}$"
        ).any()
        has_saldo_inicial = sample.apply(
            lambda r: r.str.replace("\xa0", " ", regex=False).str.contains(
                r"saldo\s+inicial", case=False, regex=True
            ).any(),
            axis=1,
        ).any()
        if has_balanza_parent and has_saldo_inicial:
            return "star1_balanza"

        # STAR 2.0: conserva su comportamiento anterior.
        return "star2"

    if len(df_guess.index) >= 1 and len(df_guess.columns) >= 1:
        a2 = str(df_guess.iloc[0, 0] if df_guess.shape[1] > 0 else "")
        if a2.replace("\xa0", " ").strip().startswith(":"):
            return "star2"

    if ("poliza" in header_join and "concepto" in header_join) or ("poliza" in header_join and "fecha" in header_join):
        return "star2"

    return "star1"


def _guess_header(df):
    header_idx = None
    limit = min(12, len(df))

    for i in range(limit):
        row_vals = df.iloc[i].astype(str).str.replace("\xa0", " ", regex=False).str.strip().tolist()
        row_join = " ".join([v for v in row_vals if v and v.lower() != "nan"])

        if re.search(r"cuenta.*concepto", row_join, re.IGNORECASE) and re.search(
            r"(saldo|cargos|abonos)", row_join, re.IGNORECASE
        ):
            header_idx = i
            break

        if re.search(r"\bpoliza\b", row_join, re.IGNORECASE) and re.search(
            r"\b(concepto|fecha|saldo|cargos|abonos)\b", row_join, re.IGNORECASE
        ):
            header_idx = i
            break

    if header_idx is not None:
        new_cols = df.iloc[header_idx].astype(str).str.replace("\xa0", " ", regex=False).str.strip().tolist()
        new_cols = [c if c and c.lower() != "nan" else f"col{j}" for j, c in enumerate(new_cols)]
        df2 = df.iloc[header_idx + 1:].reset_index(drop=True)
        df2.columns = new_cols[: df2.shape[1]]
        return df2, list(df2.columns)

    base_cols = ["Cuenta / Concepto", "Cheque", "Trafico", "Factura", "Fecha", "Cargos", "Abonos", "Saldo"]
    cols = base_cols + [f"col{j}" for j in range(len(base_cols), df.shape[1])]
    df2 = df.copy()
    df2.columns = cols[: df.shape[1]]
    return df2, list(df2.columns)


# =====================================================
# --- UTILIDADES DE FECHAS ---
# =====================================================

def _normalize_date_series(s: pd.Series) -> pd.Series:
    """
    Convierte a dd/mm/yyyy respetando dayfirst e incluye seriales de Excel.
    """
    s2 = s.copy()

    as_num = pd.to_numeric(s2, errors="coerce")
    mask_num = as_num.notna()
    if mask_num.any():
        s2.loc[mask_num] = pd.to_datetime(as_num[mask_num], unit="d", origin="1899-12-30").dt.strftime("%d/%m/%Y")

    mask_txt = ~mask_num
    if mask_txt.any():
        parsed = pd.to_datetime(s2[mask_txt].astype(str).str.strip(), errors="coerce", dayfirst=True)
        need_retry = parsed.isna()
        if need_retry.any():
            parsed2 = pd.to_datetime(s2[mask_txt][need_retry], errors="coerce", dayfirst=False)
            parsed.loc[need_retry] = parsed2
        s2.loc[mask_txt] = parsed.dt.strftime("%d/%m/%Y")
        s2 = s2.replace({"NaT": ""})

    return s2



# =====================================================
# --- STAR 1: BALANZA DE COMPROBACIÓN ---
# =====================================================

_CUENTA_BALANZA_RE = re.compile(r"^\s*(\d{3}-\d{2}-\d{2}-\d{3}-\d{2}-\d{3}-\d{4})\s*$")


def process_star1_balanza(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    STAR 1 (Balanza de Comprobacion): auxiliar con columna Poliza.

    La cuenta aparece como fila padre en la columna Poliza y el concepto de
    cuenta aparece en la columna Concepto. Las pólizas detalle quedan debajo.
    Resultado: se agregan al inicio las columnas Cuenta y Concepto cuenta,
    se eliminan Saldo Inicial / SUMAS TOTALES y se conserva el detalle.
    """
    df, _ = _guess_header(df_raw.copy())

    def _norm_name(c: str) -> str:
        s = str(c).strip().replace("\xa0", " ")
        s_l = re.sub(r"\s+", " ", s.lower())
        if s_l == "poliza": return "Poliza"
        if s_l == "concepto": return "Concepto"
        if s_l == "cheque": return "Cheque"
        if s_l in ("trafico", "tráfico"): return "Trafico"
        if s_l == "factura": return "Factura"
        if s_l == "fecha": return "Fecha"
        if s_l == "cargos": return "Cargos"
        if s_l == "abonos": return "Abonos"
        if s_l == "saldo": return "Saldo"
        return s

    df = df.rename(columns={c: _norm_name(c) for c in df.columns}).copy()

    required = ["Poliza", "Concepto", "Cheque", "Trafico", "Factura", "Fecha", "Cargos", "Abonos", "Saldo"]
    for c in required:
        if c not in df.columns:
            df[c] = ""

    last_cuenta = ""
    last_concepto_cuenta = ""
    rows_to_drop = []

    for idx, row in df.iterrows():
        poliza = str(row.get("Poliza", "")).replace("\xa0", " ").strip()
        concepto = str(row.get("Concepto", "")).replace("\xa0", " ").strip()
        row_text = " ".join(str(v).replace("\xa0", " ").strip() for v in row.values)

        # Fila padre de cuenta: cuenta exacta en Poliza + concepto de cuenta + Saldo Inicial.
        if _CUENTA_BALANZA_RE.match(poliza) and (concepto or re.search(r"saldo\s+inicial", row_text, re.IGNORECASE)):
            last_cuenta = poliza
            last_concepto_cuenta = concepto
            rows_to_drop.append(idx)
            continue

        # Filas de resumen del bloque.
        if re.search(r"\b(sumas?\s+totales?|saldo\s+inicial)\b", row_text, re.IGNORECASE):
            rows_to_drop.append(idx)
            continue

        df.at[idx, "Cuenta"] = last_cuenta if last_cuenta else "__SIN_CUENTA_DETECTADA__"
        df.at[idx, "Concepto cuenta"] = last_concepto_cuenta if last_concepto_cuenta else "__SIN_CONCEPTO_CUENTA__"

    df = df.drop(index=rows_to_drop).reset_index(drop=True)
    df = _drop_summary_rows(df)

    # El detalle válido debe tener póliza y algún importe/saldo.
    df = df[df["Poliza"].astype(str).str.replace("\xa0", " ", regex=False).str.strip().ne("")]
    df = df[~df["Poliza"].astype(str).str.match(_CUENTA_BALANZA_RE, na=False)]

    for col in ["Cargos", "Abonos", "Saldo"]:
        df[col] = df[col].apply(_to_num_safe)

    amt_cols = ["Cargos", "Abonos", "Saldo"]
    df = df[df[amt_cols].fillna(0).abs().sum(axis=1) > 0].reset_index(drop=True)

    # Mantener formato del auxiliar tal como viene; solo normalizar si llega como serial.
    # Si viene como datetime/string de Excel, se conserva como texto legible.
    if "Fecha" in df.columns:
        fecha_raw = df["Fecha"].astype(str).str.strip()
        serial_mask = pd.to_numeric(fecha_raw, errors="coerce").notna()
        if serial_mask.any():
            df.loc[serial_mask, "Fecha"] = _normalize_date_series(df.loc[serial_mask, "Fecha"])

    desired = ["Cuenta", "Concepto cuenta", "Poliza", "Concepto", "Cheque", "Trafico", "Factura", "Fecha", "Cargos", "Abonos", "Saldo"]
    ordered = [c for c in desired if c in df.columns]
    rest = [c for c in df.columns if c not in ordered]
    return df[ordered + rest]


def process_star1_balanza_many(raws):
    frames = [process_star1_balanza(df_raw) for df_raw in raws]
    if not frames:
        return pd.DataFrame(columns=["Cuenta", "Concepto cuenta", "Poliza", "Concepto", "Cheque", "Trafico", "Factura", "Fecha", "Cargos", "Abonos", "Saldo"])
    return pd.concat(frames, ignore_index=True)


# =====================================================
# --- STAR 2.0 ---
# =====================================================

def process_star2_single(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    STAR 2.0: un archivo puede contener MÚLTIPLES cuentas.
    Cada cuenta inicia con "Cuenta: XXX..." y termina cuando en la columna 'Fecha' aparece 'Total'.
    Se ignoran las filas de Saldo inicial y Total.
    """
    df, _ = _guess_header(df_raw.copy())

    def _norm_name(c: str) -> str:
        s = str(c).strip().replace("\xa0", " ")
        s_l = re.sub(r"\s+", " ", s.lower())
        if s_l == "poliza":    return "Poliza"
        if s_l == "concepto":  return "Concepto"
        if "cliente" in s_l and "proveedor" in s_l: return "Cliente / Proveedor"
        if "sucursal" in s_l or s_l in ("suc", "suc."): return "Sucursal"
        if s_l == "cheque":    return "Cheque"
        if s_l in ("trafico", "tráfico"): return "Trafico"
        if s_l == "factura":   return "Factura"
        if s_l == "fecha":     return "Fecha"
        if s_l == "cargos":    return "Cargos"
        if s_l == "abonos":    return "Abonos"
        if s_l == "saldo":     return "Saldo"
        return s

    df = df.rename(columns={c: _norm_name(c) for c in df.columns})

    # Asegurar columna Cuenta
    if "Cuenta" not in df.columns:
        df.insert(0, "Cuenta", "")

    # ✅ NUEVO: detectar encabezados "Cuenta: ...." dentro del mismo archivo y propagar por bloque
    cuenta_col = "Poliza" if "Poliza" in df.columns else df.columns[0]

    cuenta_re = re.compile(r"^\s*(cuenta\s*:)\s*(.+)$", re.IGNORECASE)
    # Formato típico: 200-03-99-001-02850 ...
    acct_code_re = re.compile(r"^\s*\d{3}-\d{2}-\d{2}-\d{3}-\d{5}\b.*", re.IGNORECASE)

    last_cuenta = None
    rows_to_drop = []
    in_cuenta_block = False

    for idx, val in df[cuenta_col].astype(str).items():
        text = val.replace("\xa0", " ").strip()

        m = cuenta_re.match(text)
        if m:
            last_cuenta = m.group(2).strip()
            rows_to_drop.append(idx)   # eliminamos la fila "Cuenta: ..."
            in_cuenta_block = True
            continue

        # Por si alguna vez llega SIN "Cuenta:" pero con el código al inicio y sin otros datos
        if acct_code_re.match(text):
            other_has = any(
                str(df.at[idx, c]).strip() not in {"", "nan", "None"}
                for c in df.columns if c != cuenta_col
            )
            if not other_has:
                last_cuenta = text
                rows_to_drop.append(idx)
                in_cuenta_block = True
                continue

        # Verificar si llegamos al Total (fin del bloque de cuenta)
        if in_cuenta_block and "Fecha" in df.columns:
            fecha_val = str(df.at[idx, "Fecha"]).replace("\xa0", " ").strip().lower()
            if fecha_val == "total":
                rows_to_drop.append(idx)  # eliminamos la fila "Total"
                in_cuenta_block = False
                last_cuenta = None  # resetear cuenta para el siguiente bloque
                continue

        if last_cuenta and in_cuenta_block:
            df.at[idx, "Cuenta"] = last_cuenta

    df = df.drop(index=rows_to_drop).reset_index(drop=True)

    # Eliminar filas-resumen (Total / Saldo inicial / etc.)
    df = _drop_summary_rows(df)

    # Filtrar conceptos vacíos
    if "Concepto" in df.columns:
        df = df[df["Concepto"].astype(str).str.strip().ne("")]

    # Montos a numérico
    for col in ["Cargos", "Abonos", "Saldo"]:
        if col in df.columns:
            df[col] = df[col].apply(_to_num_safe)

    # Mantener filas con algún monto (si existen columnas de monto)
    amt_cols = [c for c in ["Cargos", "Abonos", "Saldo"] if c in df.columns]
    if amt_cols:
        df = df[df[amt_cols].fillna(0).abs().sum(axis=1) > 0].reset_index(drop=True)

    # Normalizar fechas si existe la columna
    if "Fecha" in df.columns:
        df["Fecha"] = _normalize_date_series(df["Fecha"])

    desired = ["Cuenta", "Poliza", "Concepto", "Cliente / Proveedor", "Sucursal",
               "Cheque", "Trafico", "Factura", "Fecha", "Cargos", "Abonos", "Saldo"]
    ordered = [c for c in desired if c in df.columns]
    rest = [c for c in df.columns if c not in ordered]
    return df[ordered + rest]


def process_star2_many(raws):
    frames = [process_star2_single(df_raw) for df_raw in raws]
    if not frames:
        return pd.DataFrame(columns=[
            "Cuenta", "Poliza", "Concepto", "Cliente / Proveedor", "Sucursal",
            "Cheque", "Trafico", "Factura", "Fecha", "Cargos", "Abonos", "Saldo"
        ])
    return pd.concat(frames, ignore_index=True)


# =====================================================
# --- STAR 1 ---
# =====================================================

def process_report(df_raw):
    df = df_raw.copy()

    if len(df) > 0:
        df = df.iloc[1:].reset_index(drop=True)

    df, _ = _guess_header(df)

    if "Cuenta" not in df.columns:
        df.insert(0, "Cuenta", "")

    def find_col(pat, default=None):
        for c in df.columns:
            if re.search(pat, str(c), re.IGNORECASE):
                return c
        return default

    col_cc     = find_col(r"cuenta.*concepto", df.columns[1] if len(df.columns) > 1 else df.columns[0])
    col_cheque = find_col(r"cheq")
    col_traf   = find_col(r"traf")
    col_fact   = find_col(r"fact")
    col_cargos = find_col(r"cargos")
    col_abonos = find_col(r"abonos")
    col_saldo  = find_col(r"saldo")

    cuenta_pat = re.compile(r"^\s*\d{3}-\d{2}-\d{2}-\d{3}-\d{2}-\d{3}-\d{4}\s+-\s+.+", re.IGNORECASE)

    last_cuenta = None
    rows_to_drop = []

    for idx, val in df[col_cc].astype(str).items():
        text = val.replace("\xa0", " ").strip()

        if cuenta_pat.match(text):
            last_cuenta = text
            rows_to_drop.append(idx)
            continue

        is_summary_word = text.lower() in {"saldo", "sumas totales"}
        has_detail_refs = any(
            c and str(df.at[idx, c]).strip() not in {"", "nan", "None"}
            for c in [col_cheque, col_traf, col_fact]
        )

        if is_summary_word and not has_detail_refs:
            rows_to_drop.append(idx)
            continue

        df.at[idx, "Cuenta"] = last_cuenta if last_cuenta else "__SIN_CUENTA_DETECTADA__"

    df = df.drop(index=rows_to_drop).reset_index(drop=True)
    df = _drop_summary_rows(df)

    for col in [col_cargos, col_abonos, col_saldo]:
        if col:
            df[col] = df[col].apply(_to_num_safe)

    for c in df.columns:
        if re.search(r"fecha", str(c), re.IGNORECASE):
            df[c] = _normalize_date_series(df[c])

    amt_cols = [c for c in [col_cargos, col_abonos, col_saldo] if c]
    if amt_cols:
        for c in amt_cols:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        if col_cc in df.columns:
            df = df[df[col_cc].astype(str).str.strip().ne("")]
        df = df[df[amt_cols].fillna(0).abs().sum(axis=1) > 0].reset_index(drop=True)

    non_cuenta_cols = [c for c in df.columns if c != "Cuenta"]

    def _row_is_empty(series):
        for v in series.values:
            s = str(v).replace("\xa0", " ").strip().lower()
            if s not in {"", "nan", "none"}:
                return False
        return True

    df["__empty__"] = df[non_cuenta_cols].astype(str).apply(_row_is_empty, axis=1)
    df = df.loc[~df["__empty__"]].drop(columns="__empty__").reset_index(drop=True)

    first_cols = ["Cuenta"]
    rest = [c for c in df.columns if c not in first_cols]
    return df[first_cols + rest]


# =====================================================
# --- FORMATO 2: DIVISIÓN DE COLUMNA CUENTA ---
# =====================================================

# Patrón: 000-00-00-000-00-000-0000 - TEXTO DEL CONCEPTO
_CUENTA_NUM_RE = re.compile(
    r"^\s*(\d{3}-\d{2}-\d{2}-\d{3}-\d{2}-\d{3}-\d{4})\s+-\s+(.+)$"
)

def _aplicar_formato2(df: pd.DataFrame) -> pd.DataFrame:
    """
    Sustituye la columna 'Cuenta' por dos columnas:
      - 'Numero Cuenta'      → solo el código  (ej. 100-01-01-001-01-051-9591)
      - 'Concepto de Cuenta' → solo el texto   (ej. COSTO SS MANIOBRAS DE CARGA Y DESCARGA ...)
    Si el valor no coincide con el patrón, ambas columnas heredan el texto original.
    """
    if "Cuenta" not in df.columns:
        return df

    df = df.copy()
    num_cuenta = []
    concepto   = []

    for val in df["Cuenta"].astype(str):
        m = _CUENTA_NUM_RE.match(val)
        if m:
            num_cuenta.append(m.group(1).strip())
            concepto.append(m.group(2).strip())
        else:
            num_cuenta.append(val.strip())
            concepto.append(val.strip())

    cuenta_pos = df.columns.get_loc("Cuenta")
    df.insert(cuenta_pos,     "Numero Cuenta",      num_cuenta)
    df.insert(cuenta_pos + 1, "Concepto de Cuenta", concepto)
    df = df.drop(columns=["Cuenta"])

    return df


# =====================================================
# --- PUNTO DE ENTRADA DEL MÓDULO ---
# =====================================================

def render():
    from ui.components import page_banner, section_header, alert, divider
    page_banner("📊", "Reporte de Cuentas", "Limpieza automática de auxiliares contables")

    st.caption(
        "Sube el Excel (.xls o .xlsx) tal como lo descargas. "
        "La página eliminará encabezados/sumarios, propagará la cuenta y te dará un archivo limpio."
    )

    col_modo, col_formato = st.columns(2)

    with col_modo:
        mode = st.selectbox(
            "Modo de procesamiento",
            ["Auto", "STAR 1 (Balanza de Comprobacion)", "STAR 1 (Fichero Excel)", "STAR 2.0 (por cuenta, múltiples archivos)"],
            index=0,
            key="ra_mode"
        )

    with col_formato:
        formato_reporte = st.selectbox(
            "Tipo de reporte",
            ["Formato Auditoría", "Formato 2"],
            index=0,
            key="ra_formato",
            help=(
                "Formato Auditoría: columna Cuenta con código y nombre completo.\n\n"
                "Formato 2: separa en Numero Cuenta y Concepto de Cuenta."
            ),
        )

    uploaded_files = st.file_uploader(
        "Sube uno o varios archivos (.xls, .xlsx, .html, .htm)",
        type=["xls", "xlsx", "html", "htm"],
        accept_multiple_files=True
    )

    if not uploaded_files:
        alert("info", "Sube tus archivos para procesar.\n\n• **STAR 1**: un solo archivo con todas las cuentas.\n• **STAR 2.0**: varios archivos (uno por cuenta) y los consolidamos.")
        return

    try:
        raws = [_read_excel_any(up) for up in uploaded_files]

        if mode.startswith("Auto"):
            eff_mode = _detect_mode(raws[0])
        elif mode.startswith("STAR 1 (Balanza"):
            eff_mode = "star1_balanza"
        elif mode.startswith("STAR 1"):
            eff_mode = "star1"
        else:
            eff_mode = "star2"

        if eff_mode == "star1_balanza":
            df_clean = process_star1_balanza_many(raws)
        elif eff_mode == "star1":
            if len(raws) > 1:
                alert("warn", "Modo STAR 1: se tomará solo el primer archivo.")
            df_clean = process_report(raws[0])
        else:
            df_clean = process_star2_many(raws)

        # Aplicar formato seleccionado
        df_out = _aplicar_formato2(df_clean) if formato_reporte == "Formato 2" else df_clean

        st.success(f"✅ Listo. Filas finales: {len(df_out):,}")
        st.dataframe(df_out.head(1000), use_container_width=True)

        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df_out.to_excel(writer, index=False, sheet_name="REPORTE")

        st.download_button(
            "⬇️ Descargar Excel procesado",
            data=buf.getvalue(),
            file_name="Reporte_procesado.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    except Exception as e:
        st.error(f"Ocurrió un error procesando: {e}")
        st.exception(e)
