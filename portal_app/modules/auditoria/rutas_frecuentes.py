# portal_app/modules/auditoria/rutas_frecuentes.py
import io
from collections import Counter
from typing import Optional, Tuple, List

import pandas as pd
import streamlit as st

from ui.components import page_banner, section_header, alert, divider
from .shared import log_accion
    
# -----------------------------
# Helpers (igual que tu script)
# -----------------------------
def normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def find_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    """Find first matching column name (case-insensitive)."""
    cols_lower = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in cols_lower:
            return cols_lower[cand.lower()]
    return None


def safe_to_datetime(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce")


def mode_value(series: pd.Series):
    s = series.dropna()
    if s.empty:
        return None
    m = s.mode()
    if m.empty:
        return None
    return m.iloc[0]


def top3_with_counts(series: pd.Series) -> str:
    s = series.dropna()
    if s.empty:
        return ""
    c = Counter(s.astype(str))
    return ", ".join([f"{k} ({v})" for k, v in c.most_common(3)])


def build_report(
    df: pd.DataFrame,
    suc_col: str,
    cliente_col: str,
    tipo_col: str,
    ciudad_o_col: str,
    estado_o_col: str,
    ciudad_d_col: str,
    estado_d_col: str,
    date_col: str,
    min_viajes_mes: int,
    year_filter: Optional[int] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    df = normalize_cols(df)

    df["_date"] = safe_to_datetime(df[date_col])
    if year_filter is not None:
        df = df[df["_date"].dt.year == year_filter].copy()

    df["Ruta"] = (
        df[ciudad_o_col].astype(str) + ", " + df[estado_o_col].astype(str)
        + " - " +
        df[ciudad_d_col].astype(str) + ", " + df[estado_d_col].astype(str)
    )

    df["Mes"] = df["_date"].dt.to_period("M")
    df = df[df["_date"].notna()].copy()

    group_month = (
        df.groupby([suc_col, cliente_col, tipo_col, "Ruta", "Mes"])
          .size()
          .reset_index(name="ViajesMes")
    )

    valid_routes = group_month[group_month["ViajesMes"] > min_viajes_mes]
    valid_keys = valid_routes[[suc_col, cliente_col, tipo_col, "Ruta"]].drop_duplicates()

    df_valid = df.merge(valid_keys, on=[suc_col, cliente_col, tipo_col, "Ruta"], how="inner")

    total_viajes = (
        df_valid.groupby([suc_col, cliente_col, tipo_col, "Ruta"])
               .size()
               .reset_index(name="#Viajes")
    )

    cols_I = [c for c in df.columns if isinstance(c, str) and c.startswith("I ")]
    cols_C = [c for c in df.columns if isinstance(c, str) and c.startswith("C ")]

    rows = []
    for _, k in total_viajes.iterrows():
        suc = k[suc_col]
        cli = k[cliente_col]
        tipo = k[tipo_col]
        ruta = k["Ruta"]
        viajes = int(k["#Viajes"])

        subset = df_valid[
            (df_valid[suc_col] == suc) &
            (df_valid[cliente_col] == cli) &
            (df_valid[tipo_col] == tipo) &
            (df_valid["Ruta"] == ruta)
        ]

        row = {
            "Sucursal": suc,
            "#Viajes": viajes,
            "Tipo": tipo,
            "Cliente": cli,
            "Ruta": ruta,
        }

        for col in cols_I:
            row[col] = mode_value(subset[col])

        for col in cols_C:
            row[col] = mode_value(subset[col])

            col_ac = col.replace("C ", "AC ", 1)
            if col_ac in subset.columns:
                row[f"{col_ac} Top3"] = top3_with_counts(subset[col_ac])

        rows.append(row)

    df_report = pd.DataFrame(rows)
    return df_report, valid_keys


def to_excel_bytes(df_report: pd.DataFrame, sheet_name: str = "Rutas Comunes") -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_report.to_excel(writer, index=False, sheet_name=sheet_name)
    return output.getvalue()


# -----------------------------
# UI (encapsulada)
# -----------------------------
def render():
    page_banner("🗺️", "Rutas Frecuentes", "Análisis de rutas comunes por cliente")


    st.write(
        "Sube tu tabla (Excel o CSV) y genera el reporte de rutas más comunes por "
        "**Sucursal + Cliente + Tipo + Ruta**, filtrando solo las que tengan **más de N viajes por mes**."
    )

    uploaded = st.file_uploader("Sube tu archivo", type=["xlsx", "xls", "csv"])
    min_viajes_mes = st.number_input(
        "Mínimo de viajes por mes (validación es > N)", min_value=0, value=2, step=1
    )
    year_filter_txt = st.text_input(
        "Filtrar por año (opcional, ej. 2025). Déjalo vacío para no filtrar.", value=""
    )

    df = None
    sheet_name = None

    if uploaded:
        try:
            if uploaded.name.lower().endswith(".csv"):
                df = pd.read_csv(uploaded)
            else:
                xls = pd.ExcelFile(uploaded)
                sheet_name = st.selectbox("Selecciona hoja", xls.sheet_names)
                df = pd.read_excel(xls, sheet_name=sheet_name)

            df = normalize_cols(df)

        except Exception as e:
            st.error(f"No pude leer el archivo. Error: {e}")
            st.stop()

        section_header("👁️", "Vista previa")
        st.dataframe(df.head(50), use_container_width=True)

        guessed = {
            "Sucursal": find_col(df, ["Sucursal"]),
            "Cliente Operación": find_col(df, ["Cliente Operación", "Cliente Operacion"]),
            "Tipo Viaje": find_col(df, ["Tipo Viaje", "Tipo viaje", "TipoViaje"]),
            "Ciudad Origen": find_col(df, ["Ciudad Origen", "Ciudad origen"]),
            "Estado Origen": find_col(df, ["Estado Origen", "Estado origen"]),
            "Ciudad Destino": find_col(df, ["Ciudad Destino", "Ciudad destino"]),
            "Estado Destino": find_col(df, ["Estado Destino", "Estado destino"]),
            "Fecha": find_col(df, ["Fecha Despacho", "Fecha", "Bill Date..", "Fecha Entrega", "Fecha Concluido"]),
        }

        section_header("🗂️", "Mapeo de columnas (ajusta si hace falta)")
        cols = ["(Selecciona)"] + list(df.columns)

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            suc_col = st.selectbox("Sucursal", cols, index=cols.index(guessed["Sucursal"]) if guessed["Sucursal"] in cols else 0)
            cliente_col = st.selectbox("Cliente Operación", cols, index=cols.index(guessed["Cliente Operación"]) if guessed["Cliente Operación"] in cols else 0)
        with c2:
            tipo_col = st.selectbox("Tipo Viaje", cols, index=cols.index(guessed["Tipo Viaje"]) if guessed["Tipo Viaje"] in cols else 0)
            date_col = st.selectbox("Fecha (para mes)", cols, index=cols.index(guessed["Fecha"]) if guessed["Fecha"] in cols else 0)
        with c3:
            ciudad_o_col = st.selectbox("Ciudad Origen", cols, index=cols.index(guessed["Ciudad Origen"]) if guessed["Ciudad Origen"] in cols else 0)
            estado_o_col = st.selectbox("Estado Origen", cols, index=cols.index(guessed["Estado Origen"]) if guessed["Estado Origen"] in cols else 0)
        with c4:
            ciudad_d_col = st.selectbox("Ciudad Destino", cols, index=cols.index(guessed["Ciudad Destino"]) if guessed["Ciudad Destino"] in cols else 0)
            estado_d_col = st.selectbox("Estado Destino", cols, index=cols.index(guessed["Estado Destino"]) if guessed["Estado Destino"] in cols else 0)

        required = [suc_col, cliente_col, tipo_col, ciudad_o_col, estado_o_col, ciudad_d_col, estado_d_col, date_col]
        if "(Selecciona)" in required:
            alert("warn", "Selecciona todas las columnas requeridas para poder generar el reporte.")
            st.stop()

        yf = None
        year_filter_txt = year_filter_txt.strip()
        if year_filter_txt:
            if not year_filter_txt.isdigit():
                alert("error", "El año debe ser numérico (ej. 2025).")
                st.stop()
            yf = int(year_filter_txt)

        if st.button("Generar reporte", type="primary"):
            with st.spinner("Procesando..."):
                try:
                    df_report, df_keys = build_report(
                        df=df,
                        suc_col=suc_col,
                        cliente_col=cliente_col,
                        tipo_col=tipo_col,
                        ciudad_o_col=ciudad_o_col,
                        estado_o_col=estado_o_col,
                        ciudad_d_col=ciudad_d_col,
                        estado_d_col=estado_d_col,
                        date_col=date_col,
                        min_viajes_mes=int(min_viajes_mes),
                        year_filter=yf,
                    )
                except Exception as e:
                    st.error(f"Error generando el reporte: {e}")
                    st.stop()

            log_accion("aud-rutas", "generar_reporte", {"filas": len(df_report)})
            st.success(f"Listo. Filas generadas: {len(df_report):,}")

            section_header("📊", "Reporte")
            st.dataframe(df_report, use_container_width=True)

            excel_bytes = to_excel_bytes(df_report, sheet_name="Rutas Comunes")
            descargado = st.download_button(
                label="Descargar Excel",
                data=excel_bytes,
                file_name="Reporte_Rutas_Comunes.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            if descargado:
                log_accion("aud-rutas", "exportar_excel", {"filas": len(df_report)})

            with st.expander("Debug: claves válidas (pasaron >N viajes/mes)"):
                st.dataframe(df_keys, use_container_width=True)
