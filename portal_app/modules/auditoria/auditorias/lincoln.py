from __future__ import annotations
"""
portal_app/modules/auditoria/lincoln_auditoria.py

Submódulo: Auditoría de viajes Lincoln Freight.
Aplica reglas de servicio, detecta anomalías por conceptos I→C,
valida utilidades y audita operadores logísticos autorizados por sucursal.
"""

import io
from typing import Optional

import pandas as pd
import streamlit as st

from ui.components import section_header, alert, divider
# ─────────────────────────────────────────────────────────────
# CONSTANTES — equivalencias I → C ACTUALIZADAS
# Según hoja "Nuevo mapeo" de Actualización data.xlsx.
# Las columnas de costo se recorrieron: ejemplo C77 anterior → C66 actual.
# ─────────────────────────────────────────────────────────────
FLETE_USA_R3_ING = ["I FREIGHT USATRANSP USA39", "I FUEL CHARGES DIESEL40"]
FLETE_USA_R3_COST = "C FREIGHT USACT TRANSP USA88"

FLETE_MEX_PARES = {
    "I FREIGHT MEXTRANSP MEX19": "C FREIGHT MEXCT TRANSP MEX82",
    "I FREIGHT MEXTRANSP MEX38": "C FREIGHT MEXCT TRANSP MEX87",
    "I FREIGHT MEXTRANSP MEX61": "C FREIGHT MEXCT TRANSP MEX95",
}

# Varios ingresos de cruce comparten la misma columna de costo.
CRUCE_PARES = {
    "I CROSS BORDER EMPTYCRUCE VACIO6": "C CROSS BORDER LOADEDCT CRUCE CARGADO77",
    "I CROSS BORDER LOADEDCRUCE CARGADO7": "C CROSS BORDER LOADEDCT CRUCE CARGADO77",
    "I CROSS BORDER EMPTYCRUCE VACIO24": "C CROSS BORDER LOADEDCT CRUCE CARGADO79",
    "I CROSS BORDER LOADEDCRUCE CARGADO25": "C CROSS BORDER LOADEDCT CRUCE CARGADO79",
    "I CROSS BORDER EMPTYCRUCE VACIO43": "C CROSS BORDER LOADEDCT CRUCE CARGADO84",
    "I CROSS BORDER LOADEDCRUCE CARGADO44": "C CROSS BORDER LOADEDCT CRUCE CARGADO84",
}

# None = sin costo asociado (unidad propia R1/R2)
EXTRA_STOP_PARES = {
    "I EXTRA STOPPARADA EXTRA5": None,
    "I EXTRA STOPPARADA EXTRA23": "C EXTRA STOPCT PARADA EXTRA81",
    "I EXTRA STOPPARADA EXTRA42": "C EXTRA STOPCT PARADA EXTRA86",
}

TNU_PARES = {
    "I TNU - TRUCK NOT USEDMOVIMIENTO EN FALSO14": None,
    "I TNU - TRUCK NOT USEDMOVIMIENTO EN FALSO32": None,
    "I TNU - TRUCK NOT USEDMOVIMIENTO EN FALSO51": "C TNU - TRUCK NOT USEDCT MOVIMIENTO EN FALSO101",
}

HANDLING_PARES = {
    "I HANDLING CHARGESMANIOBRAS13": None,
    "I HANDLING CHARGESMANIOBRAS31": None,
    "I HANDLING CHARGESMANIOBRAS50": "C HANDLING CHARGESCT MANIOBRAS100",
}

UMBRAL = {
    "flete_usa": 200,
    "flete_mex": 200,
    "cruce": 200,
    "extra_stop": 50,
    "tnu": 50,
    "handling": 50,
}

# ─────────────────────────────────────────────────────────────
# OPERADORES AUTORIZADOS
# ─────────────────────────────────────────────────────────────
OPERADORES_GDL = {
    "GABRIEL ACOSTA",
    "JOCELYN VIRIDIANA RODRIGUEZ",
    "JUAN EDUARDO VILLARREAL",
}

OPERADORES_MG = {
    "GLADYS GUTIERREZ",
}

OPERADORES_NLD = {
    "LUIS FERNANDO MARTINEZ",
}

OPERADORES_MATRIZ = {
    "GABRIELA ELIZABETH MAGALLANES",
    "JESUS BEATRIZ",
    "LESLIE GAUDALUPE COLUNGA",
    "LILIANA MARILI CAMPOS",
    "ROXANA TORRES",
}

NO_AUTORIZADOS = {
    "JULIO CESAR JAIME",
    "JULIO CESAR ORNELAS",
    "XOCHITL CERON",
}

PENDIENTES = {
    "ADELA ELIZABETH ALVARADO",
    "DAVID RICARDO MENDEZ",
    "ESTEBAN ORTEGA",
    "MIRIAM ELIZABETH REYNA",
}

CASOS_ESPECIALES = {
    "ALMA JULIETA REYNA": "Autorizada, pero revisar si corresponde a renta de cajas.",
}

SUCURSAL_ESPERADA = {
    **{op: "GUADALAJARA" for op in OPERADORES_GDL},
    **{op: "MG HAULERS" for op in OPERADORES_MG},
    **{op: "NUEVO LAREDO" for op in OPERADORES_NLD},
    **{op: "MATRIZ - LFC" for op in OPERADORES_MATRIZ},
}

# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
def _v(row: dict, col: str) -> float:
    try:
        return float(row.get(col, 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _fmt(val: float) -> str:
    return f"${abs(val):,.2f}"


def _norm(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip().upper()
    if text in {"0", "0.0", "NAN", "NONE", "(EN BLANCO)"}:
        return ""
    return " ".join(text.split())


def _get_regla(row: dict) -> int:
    serv = _norm(row.get("Servicio", ""))
    tracto = _norm(row.get("Número Tracto", ""))
    if "CARRETERA" in serv and tracto:
        return 1
    if "BROKER" in serv and tracto:
        return 2
    if "BROKER" in serv and not tracto:
        return 3
    return 0


def _chip(ok: bool) -> str:
    return "✅ OK" if ok else "❌ Anomalía"


def _chip_operador(ok: bool, advertencia: bool = False) -> str:
    if advertencia:
        return "⚠️ Advertencia"
    return _chip(ok)


# ─────────────────────────────────────────────────────────────
# LÓGICAS DE AUDITORÍA
# ─────────────────────────────────────────────────────────────
def _audit_operadores(row: dict) -> Optional[dict]:
    operador = _norm(row.get("Operador Logístico", ""))
    sucursal = _norm(row.get("Sucursal", ""))
    viaje = row.get("Número De Viaje", "")
    servicio = row.get("Servicio", "")
    cliente = row.get("Cliente", "")
    tipo = row.get("Tipo Viaje", "")

    if not operador:
        return None

    base = {
        "Número Viaje": viaje,
        "Sucursal": sucursal,
        "Operador": operador,
        "Servicio": servicio,
        "Cliente": cliente,
        "Tipo Viaje": tipo,
    }

    if operador in NO_AUTORIZADOS:
        return {
            **base,
            "Estado": "❌ Anomalía",
            "OK": False,
            "Observación": "Usuario no autorizado para generar tráfico.",
        }

    if operador in PENDIENTES:
        return {
            **base,
            "Estado": "⚠️ Advertencia",
            "OK": True,
            "Observación": "Usuario pendiente de autorización; revisar si procede.",
        }

    if operador in CASOS_ESPECIALES:
        return {
            **base,
            "Estado": "⚠️ Advertencia",
            "OK": True,
            "Observación": CASOS_ESPECIALES[operador],
        }

    suc_esperada = SUCURSAL_ESPERADA.get(operador)
    if suc_esperada and sucursal != suc_esperada:
        return {
            **base,
            "Estado": "❌ Anomalía",
            "OK": False,
            "Observación": f"Operador autorizado solo para sucursal {suc_esperada}.",
        }

    return None


def _audit_flete_usa(row: dict) -> Optional[dict]:
    regla = _get_regla(row)
    viaje = row.get("Número De Viaje", "")
    tracto = row.get("Número Tracto", "")
    tipo = row.get("Tipo Viaje", "")
    ok = True
    obs: list[str] = []
    costos_r12 = [
        "C FREIGHT USACT TRANSP USA83",
        "C FREIGHT USACT TRANSP USA88",
        "C FREIGHT USACT TRANSP USA89",
    ]

    if regla == 1:
        i_flete = _v(row, "I FREIGHT USATRANSP USA2")
        i_fuel = _v(row, "I FUEL CHARGES DIESEL3")
        i_total = i_flete + i_fuel
        costo = sum(_v(row, c) for c in costos_r12)
        if i_total == 0:
            return None
        if costo > 0:
            ok = False
            obs.append(f"R1: no debe haber costo para unidad propia (C={_fmt(costo)}).")
    elif regla == 2:
        i_flete = _v(row, "I FREIGHT USATRANSP USA20")
        i_fuel = _v(row, "I FUEL CHARGES DIESEL21")
        i_total = i_flete + i_fuel
        costo = sum(_v(row, c) for c in costos_r12)
        if i_total == 0:
            return None
        if costo > 0:
            ok = False
            obs.append(f"R2: no debe haber costo con unidad capturada (C={_fmt(costo)}).")
    elif regla == 3:
        i_flete = _v(row, FLETE_USA_R3_ING[0])
        i_fuel = _v(row, FLETE_USA_R3_ING[1])
        i_total = i_flete + i_fuel
        costo = _v(row, FLETE_USA_R3_COST)
        if i_total == 0 and costo == 0:
            return None
        if i_total > 0 and costo == 0:
            ok = False
            obs.append(f"R3: ingreso {_fmt(i_total)} sin costo — tercero debe tener costo.")
        elif i_total == 0 and costo > 0:
            ok = False
            obs.append(f"R3: costo {_fmt(costo)} sin ingreso.")
        else:
            diff = abs(i_total - costo)
            if diff > UMBRAL["flete_usa"]:
                ok = False
                obs.append(
                    f"R3: variación {_fmt(diff)} excede ${UMBRAL['flete_usa']} "
                    f"(I={_fmt(i_flete)}+fuel={_fmt(i_fuel)}={_fmt(i_total)}, C={_fmt(costo)})."
                )
    else:
        return None

    return {
        "Número Viaje": viaje,
        "Tracto": tracto,
        "Tipo Viaje": tipo,
        "Regla": f"R{regla}",
        "I Flete": i_flete,
        "I Fuel": i_fuel,
        "I Total": i_total,
        "Costo": costo,
        "Diferencia": i_total - costo,
        "Estado": _chip(ok),
        "OK": ok,
        "Observación": " / ".join(obs),
    }


def _audit_flete_mex(row: dict) -> list[dict]:
    viaje = row.get("Número De Viaje", "")
    tracto = row.get("Número Tracto", "")
    tipo = row.get("Tipo Viaje", "")
    regla = _get_regla(row)
    out = []
    for col_i, col_c in FLETE_MEX_PARES.items():
        i_val = _v(row, col_i)
        c_val = _v(row, col_c) if col_c else 0.0
        if i_val == 0 and c_val == 0:
            continue
        ok, obs = True, []
        if i_val > 0 and c_val == 0:
            ok = False
            obs.append(f"Ingreso MX {_fmt(i_val)} sin costo (siempre tercero).")
        elif i_val == 0 and c_val > 0:
            ok = False
            obs.append(f"Costo MX {_fmt(c_val)} sin ingreso.")
        elif abs(i_val - c_val) > UMBRAL["flete_mex"]:
            ok = False
            obs.append(
                f"Variación {_fmt(abs(i_val - c_val))} excede ${UMBRAL['flete_mex']} "
                f"(I={_fmt(i_val)}, C={_fmt(c_val)})."
            )
        out.append({
            "Número Viaje": viaje,
            "Tracto": tracto,
            "Tipo Viaje": tipo,
            "Regla": f"R{regla}",
            "Col Ingreso": col_i,
            "Col Costo": col_c or "—",
            "Ingreso": i_val,
            "Costo": c_val,
            "Diferencia": i_val - c_val,
            "Estado": _chip(ok),
            "OK": ok,
            "Observación": " / ".join(obs),
        })
    return out


def _audit_cruce(row: dict) -> list[dict]:
    viaje = row.get("Número De Viaje", "")
    tracto = row.get("Número Tracto", "")
    tipo = row.get("Tipo Viaje", "")
    regla = _get_regla(row)
    grupos: dict[str, float] = {}
    for col_i, col_c in CRUCE_PARES.items():
        i_val = _v(row, col_i)
        if i_val > 0:
            grupos[col_c] = grupos.get(col_c, 0.0) + i_val
    out = []
    for col_c, i_total in grupos.items():
        c_val = _v(row, col_c)
        ok, obs = True, []
        if i_total > 0 and c_val == 0:
            if regla == 3:
                ok = False
                obs.append(f"Cruce: ingreso {_fmt(i_total)} sin costo (tercero).")
        elif i_total == 0 and c_val > 0:
            ok = False
            obs.append(f"Cruce: costo {_fmt(c_val)} sin ingreso.")
        elif i_total > 0 and c_val > 0:
            diff = abs(i_total - c_val)
            if diff > UMBRAL["cruce"]:
                ok = False
                obs.append(f"Variación {_fmt(diff)} excede ${UMBRAL['cruce']} (I={_fmt(i_total)}, C={_fmt(c_val)}).")
            if c_val > 400:
                ok = False
                obs.append(f"Costo {_fmt(c_val)} fuera del rango de mercado ($100–$200).")
        out.append({
            "Número Viaje": viaje,
            "Tracto": tracto,
            "Tipo Viaje": tipo,
            "Regla": f"R{regla}",
            "Col Costo": col_c,
            "I Cruce Total": i_total,
            "Costo": c_val,
            "Diferencia": i_total - c_val,
            "Estado": _chip(ok),
            "OK": ok,
            "Observación": " / ".join(obs),
        })
    return out


def _audit_simple(row: dict, pares: dict, umbral: int, nombre: str) -> list[dict]:
    viaje = row.get("Número De Viaje", "")
    tracto = row.get("Número Tracto", "")
    tipo = row.get("Tipo Viaje", "")
    regla = _get_regla(row)
    out = []
    for col_i, col_c in pares.items():
        i_val = _v(row, col_i)
        c_val = _v(row, col_c) if col_c else 0.0
        if i_val == 0 and c_val == 0:
            continue
        ok, obs = True, []
        if col_c is None:
            if nombre == "Extra Stop" and i_val > 300:
                ok = False
                obs.append(f"Ingreso {_fmt(i_val)} parece elevado (>$300).")
            if nombre == "Handling" and i_val > 1500:
                ok = False
                obs.append(f"Ingreso {_fmt(i_val)} parece elevado (>$1,500).")
        else:
            if i_val > 0 and c_val == 0:
                ok = False
                obs.append(f"Ingreso {_fmt(i_val)} sin costo (tercero debe tener costo).")
            elif i_val == 0 and c_val > 0:
                ok = False
                obs.append(f"Costo {_fmt(c_val)} sin ingreso — revisar.")
            elif abs(i_val - c_val) > umbral:
                ok = False
                obs.append(f"Variación {_fmt(abs(i_val - c_val))} excede ${umbral} (I={_fmt(i_val)}, C={_fmt(c_val)}).")
        out.append({
            "Número Viaje": viaje,
            "Tracto": tracto,
            "Tipo Viaje": tipo,
            "Regla": f"R{regla}",
            "Col Ingreso": col_i,
            "Col Costo": col_c or "—",
            "Ingreso": i_val,
            "Costo": c_val,
            "Diferencia": i_val - c_val,
            "Estado": _chip(ok),
            "OK": ok,
            "Observación": " / ".join(obs),
        })
    return out


# ─────────────────────────────────────────────────────────────
# PROCESAMIENTO PRINCIPAL
# ─────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def _procesar(file_bytes: bytes) -> tuple[dict[str, pd.DataFrame], dict, set[str]]:
    df = pd.read_excel(io.BytesIO(file_bytes), sheet_name="Companies")
    df = df.fillna(0)

    if "Número Tracto" in df.columns:
        df["Número Tracto"] = df["Número Tracto"].apply(
            lambda x: "" if _norm(x) == "" else str(x).strip()
        )

    buckets: dict[str, list] = {
        "flete_usa": [],
        "flete_mex": [],
        "cruce": [],
        "extra_stop": [],
        "tnu": [],
        "handling": [],
        "operadores": [],
        "cancelados": [],
        "utilidades": [],
    }

    for _, row in df.iterrows():
        d = row.to_dict()

        r_operador = _audit_operadores(d)
        if r_operador:
            buckets["operadores"].append(r_operador)

        if "CANCELADO" in _norm(d.get("Estado Factura", "")):
            buckets["cancelados"].append(d)
            continue

        r = _audit_flete_usa(d)
        if r:
            buckets["flete_usa"].append(r)

        buckets["flete_mex"].extend(_audit_flete_mex(d))
        buckets["cruce"].extend(_audit_cruce(d))
        buckets["extra_stop"].extend(_audit_simple(d, EXTRA_STOP_PARES, UMBRAL["extra_stop"], "Extra Stop"))
        buckets["tnu"].extend(_audit_simple(d, TNU_PARES, UMBRAL["tnu"], "TNU"))
        buckets["handling"].extend(_audit_simple(d, HANDLING_PARES, UMBRAL["handling"], "Handling"))

        ingreso = float(d.get("Importe Ingreso", 0) or 0)
        costo = float(d.get("Importe Costo", 0) or 0)
        utilidad = float(d.get("Importe Utilidad", 0) or 0)
        pct = float(d.get("% Utilidad", 0) or 0)
        tracto = str(d.get("Número Tracto", "")).strip()
        umbral_ut = 0.40 if tracto else 0.20
        alerta_ut = ingreso > 0 and pct < umbral_ut
        buckets["utilidades"].append({
            "Número Viaje": d.get("Número De Viaje", ""),
            "Tracto": tracto,
            "Servicio": d.get("Servicio", ""),
            "Cliente": d.get("Cliente", ""),
            "Ingreso": ingreso,
            "Costo": costo,
            "Utilidad": utilidad,
            "% Utilidad": pct,
            "Umbral": umbral_ut,
            "Alerta UT": "⚠️ Baja" if alerta_ut else "✅ OK",
            "OK": not alerta_ut,
        })

    dfs = {k: pd.DataFrame(v) if v else pd.DataFrame() for k, v in buckets.items()}

    with_anomaly: set[str] = set()
    for key in ("flete_usa", "flete_mex", "cruce", "extra_stop", "tnu", "handling", "operadores"):
        df_k = dfs[key]
        if not df_k.empty and "OK" in df_k.columns:
            with_anomaly.update(df_k[df_k["OK"] == False]["Número Viaje"].astype(str).unique())

    n_total = len(df)
    n_canc = len(dfs["cancelados"])
    n_adv_oper = 0
    if not dfs["operadores"].empty and "Estado" in dfs["operadores"].columns:
        n_adv_oper = int(dfs["operadores"]["Estado"].astype(str).str.contains("Advertencia", na=False).sum())

    stats = {
        "total": n_total,
        "cancelados": n_canc,
        "anomalias": len(with_anomaly),
        "advertencias": n_adv_oper,
        "ok": max(0, n_total - n_canc - len(with_anomaly)),
    }
    return dfs, stats, with_anomaly


def _to_excel(dfs: dict[str, pd.DataFrame]) -> bytes:
    buf = io.BytesIO()
    labels = {
        "flete_usa": "Flete USA",
        "flete_mex": "Flete MX",
        "cruce": "Cruce",
        "extra_stop": "Extra Stop",
        "tnu": "TNU",
        "handling": "Handling",
        "operadores": "Operadores",
        "cancelados": "Cancelados",
        "utilidades": "Utilidades",
    }
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        for key, label in labels.items():
            df_k = dfs.get(key, pd.DataFrame())
            if df_k.empty:
                continue
            cols = [c for c in df_k.columns if c != "OK"]
            df_k[cols].to_excel(writer, sheet_name=label, index=False)
    buf.seek(0)
    return buf.read()


# ─────────────────────────────────────────────────────────────
# UI HELPERS
# ─────────────────────────────────────────────────────────────
_COL_CONFIG = {
    "Diferencia": st.column_config.NumberColumn(format="$%.2f"),
    "Ingreso": st.column_config.NumberColumn(format="$%.2f"),
    "Costo": st.column_config.NumberColumn(format="$%.2f"),
    "I Total": st.column_config.NumberColumn(format="$%.2f"),
    "I Flete": st.column_config.NumberColumn(format="$%.2f"),
    "I Fuel": st.column_config.NumberColumn(format="$%.2f"),
    "I Cruce Total": st.column_config.NumberColumn(format="$%.2f"),
    "Utilidad": st.column_config.NumberColumn(format="$%.2f"),
    "% Utilidad": st.column_config.NumberColumn(format="%.1%"),
    "Umbral": st.column_config.NumberColumn(format="%.0%"),
}


def _tabla(df: pd.DataFrame, filtro: str, search_key: str) -> None:
    if df.empty:
        alert("info", "Sin registros en esta sección.")
        return

    df_show = df.copy()
    q = st.text_input("🔎 Buscar número de viaje", key=search_key)
    if q and "Número Viaje" in df_show.columns:
        df_show = df_show[df_show["Número Viaje"].astype(str).str.contains(q, case=False, na=False)]

    if "OK" in df_show.columns:
        if filtro == "Con anomalía":
            df_show = df_show[df_show["OK"] == False]
        elif filtro == "Sin anomalía":
            df_show = df_show[df_show["OK"] == True]
        elif filtro == "Advertencias" and "Estado" in df_show.columns:
            df_show = df_show[df_show["Estado"].astype(str).str.contains("Advertencia", na=False)]

    cols = [c for c in df_show.columns if c != "OK"]
    st.dataframe(df_show[cols], use_container_width=True, hide_index=True, column_config=_COL_CONFIG)

    n_err = int((df["OK"] == False).sum()) if "OK" in df.columns else 0
    n_adv = int(df["Estado"].astype(str).str.contains("Advertencia", na=False).sum()) if "Estado" in df.columns else 0
    st.caption(f"{len(df_show)} registros mostrados  |  {n_err} anomalías  |  {n_adv} advertencias")


def _seccion(titulo: str, icono: str, df: pd.DataFrame, nota: str, key: str) -> None:
    section_header(icono, titulo)
    if not df.empty and "OK" in df.columns:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Registros", len(df))
        c2.metric("✅ Sin anomalía", int((df["OK"] == True).sum()))
        c3.metric("❌ Con anomalía", int((df["OK"] == False).sum()))
        n_adv = int(df["Estado"].astype(str).str.contains("Advertencia", na=False).sum()) if "Estado" in df.columns else 0
        c4.metric("⚠️ Advertencias", n_adv)

    opciones = ["Todos", "Con anomalía", "Sin anomalía"]
    if not df.empty and "Estado" in df.columns and df["Estado"].astype(str).str.contains("Advertencia", na=False).any():
        opciones.append("Advertencias")

    filtro = st.radio("Mostrar", opciones, horizontal=True, key=f"{key}_radio")
    st.caption(nota)
    _tabla(df, filtro, f"{key}_search")
    divider()


# ─────────────────────────────────────────────────────────────
# PUNTO DE ENTRADA
# ─────────────────────────────────────────────────────────────
def render() -> None:
    section_header("🔍", "Auditoría Lincoln Freight", "Auditoría automatizada de reporte mensual")

    st.caption(
        "Carga el archivo **Automatización_lincoln.xlsx** (hoja Companies). "
        "El sistema aplica las reglas de servicio, detecta anomalías por concepto "
        "y valida operadores logísticos autorizados."
    )

    uploaded = st.file_uploader(
        "Archivo Automatización Lincoln (.xlsx)",
        type=["xlsx", "xls"],
        help="Debe contener la hoja 'Companies' con los viajes del periodo.",
    )

    with st.expander("📖 Ver guía de uso y reglas de auditoría", expanded=not uploaded):
        c1, c2, c3 = st.columns(3)
        c1.info("**📥 1. Carga el Excel**\n\nSube el archivo. Debe contener la hoja 'Companies'.")
        c2.info("**🔍 2. Auditoría automática**\n\nSe aplican reglas de negocio, mapeos I→C y operadores.")
        c3.info("**📋 3. Revisa y exporta**\n\nFiltra por concepto y descarga el reporte en Excel.")
        divider()
        c1.success("**R1** Carretera + unidad\n\nSin costo USA.")
        c2.info("**R2** Broker + unidad\n\nSin costo USA. MX siempre con costo.")
        c3.warning("**R3** Broker + sin unidad\n\nTercero. I39+Fuel40 ≈ C77 (±$200).")
        alert("warn", "**Operadores**: valida que cada operador logístico esté autorizado para su sucursal.")

    if not uploaded:
        return

    file_bytes = uploaded.getvalue()
    with st.spinner("Procesando y aplicando reglas de auditoría..."):
        try:
            dfs, stats, viajes_anomalia = _procesar(file_bytes)
        except Exception as e:
            st.error(f"Error procesando el archivo: {e}")
            st.caption("Verifica que el archivo contenga la hoja 'Companies' y las columnas del nuevo mapeo.")
            return

    # Métricas globales + botón de descarga
    cm1, cm2, cm3, cm4, cm5, cdl = st.columns([2, 2, 2, 2, 2, 3])
    cm1.metric("Total viajes", stats["total"])
    cm2.metric("✅ Sin anomalía", stats["ok"])
    cm3.metric("❌ Con anomalía", stats["anomalias"])
    cm4.metric("⚠️ Advertencias", stats.get("advertencias", 0))
    cm5.metric("🚫 Cancelados", stats["cancelados"])

    with cdl:
        st.download_button(
            "⬇️ Exportar auditoría Excel",
            data=_to_excel(dfs),
            file_name="auditoria_lincoln.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    divider()

    tabs = st.tabs([
        "📊 Resumen",
        "🚛 Flete USA",
        "🇲🇽 Flete MX",
        "🌉 Cruce",
        "📍 Extra Stop",
        "🚫 TNU",
        "📦 Handling",
        "👤 Operadores",
        "💰 Utilidades",
        "❌ Cancelados",
    ])

    with tabs[0]:
        section_header("⚠️", "Viajes con anomalías")
        if not viajes_anomalia:
            alert("success", "¡Sin anomalías! Todos los viajes cumplen las reglas críticas.")
        else:
            rows = []
            for key, nombre in [
                ("flete_usa", "Flete USA"),
                ("flete_mex", "Flete MX"),
                ("cruce", "Cruce"),
                ("extra_stop", "Extra Stop"),
                ("tnu", "TNU"),
                ("handling", "Handling"),
                ("operadores", "Operadores"),
            ]:
                df_k = dfs[key]
                if df_k.empty or "OK" not in df_k.columns:
                    continue
                for _, r in df_k[df_k["OK"] == False].iterrows():
                    rows.append({
                        "Número Viaje": r["Número Viaje"],
                        "Concepto": nombre,
                        "Regla": r.get("Regla", ""),
                        "Estado": r.get("Estado", ""),
                        "Observación": r.get("Observación", ""),
                    })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        section_header("⚠️", "Advertencias")
        df_op = dfs["operadores"]
        if df_op.empty or "Estado" not in df_op.columns:
            alert("info", "Sin advertencias de operadores.")
        else:
            df_adv = df_op[df_op["Estado"].astype(str).str.contains("Advertencia", na=False)]
            if df_adv.empty:
                alert("info", "Sin advertencias de operadores.")
            else:
                cols_adv = [c for c in df_adv.columns if c != "OK"]
                st.dataframe(df_adv[cols_adv], use_container_width=True, hide_index=True)

        divider()
        cnt = []
        for key, nombre in [
            ("flete_usa", "Flete USA"),
            ("flete_mex", "Flete MX"),
            ("cruce", "Cruce"),
            ("extra_stop", "Extra Stop"),
            ("tnu", "TNU"),
            ("handling", "Handling"),
            ("operadores", "Operadores"),
        ]:
            df_k = dfs[key]
            n_tot = len(df_k)
            n_err = int((df_k["OK"] == False).sum()) if not df_k.empty and "OK" in df_k.columns else 0
            n_adv = int(df_k["Estado"].astype(str).str.contains("Advertencia", na=False).sum()) if not df_k.empty and "Estado" in df_k.columns else 0
            cnt.append({"Concepto": nombre, "Registros": n_tot, "Anomalías": n_err, "Advertencias": n_adv, "OK": n_tot - n_err})
        st.dataframe(pd.DataFrame(cnt), use_container_width=True, hide_index=True)

    with tabs[1]:
        _seccion(
            "Flete USA",
            "🚛",
            dfs["flete_usa"],
            "R1/R2: sin costo. R3: I39+Fuel40 ≈ C77 · variación máx. ±$200.",
            "fusa",
        )
    with tabs[2]:
        _seccion(
            "Flete México",
            "🇲🇽",
            dfs["flete_mex"],
            "Todo ingreso MX debe tener costo (siempre tercero). Variación máx. ±$200.",
            "fmex",
        )
    with tabs[3]:
        _seccion(
            "Cruce",
            "🌉",
            dfs["cruce"],
            "Mercado $100–$200. R3 exige costo. >$400 en costo = anomalía. Variación máx. ±$200.",
            "cruce",
        )
    with tabs[4]:
        _seccion(
            "Extra Stop",
            "📍",
            dfs["extra_stop"],
            "Variación máx. ±$50. Costo sin ingreso = anomalía prioritaria.",
            "exstop",
        )
    with tabs[5]:
        _seccion(
            "Truck Not Used",
            "🚫",
            dfs["tnu"],
            "R3: ingreso_51 → costo_90. Variación máx. ±$50.",
            "tnu",
        )
    with tabs[6]:
        _seccion(
            "Handling",
            "📦",
            dfs["handling"],
            "R3: ingreso_50 → costo_89. Ingreso >$1,500 = alerta. Variación máx. ±$50.",
            "handling",
        )
    with tabs[7]:
        _seccion(
            "Operadores logísticos",
            "👤",
            dfs["operadores"],
            "Valida operadores autorizados por sucursal. Pendientes y casos especiales salen como advertencia.",
            "operadores",
        )
    with tabs[8]:
        section_header("💰", "Utilidades por viaje")
        st.caption("Unidad propia: alerta si % utilidad < 40%  ·  Sin unidad: alerta si < 20%")
        df_ut = dfs["utilidades"]
        if df_ut.empty:
            alert("info", "Sin datos de utilidad.")
        else:
            filtro_ut = st.radio("Mostrar", ["Todos", "⚠️ Alerta", "✅ OK"], horizontal=True, key="ut_radio")
            df_show = df_ut.copy()
            if filtro_ut == "⚠️ Alerta":
                df_show = df_show[df_show["OK"] == False]
            elif filtro_ut == "✅ OK":
                df_show = df_show[df_show["OK"] == True]
            cols = [c for c in df_show.columns if c != "OK"]
            st.dataframe(df_show[cols], use_container_width=True, hide_index=True, column_config=_COL_CONFIG)
            st.caption(f"{len(df_show)} registros  |  {int((df_ut['OK'] == False).sum())} con alerta")

    with tabs[9]:
        df_c = dfs["cancelados"]
        section_header("❌", "Viajes cancelados")
        if df_c.empty:
            alert("info", "No hay viajes cancelados.")
        else:
            cols_m = [
                "Número De Viaje",
                "Estatus",
                "Cliente",
                "Servicio",
                "Importe Ingreso",
                "Importe Costo",
                "Importe Utilidad",
            ]
            cols_d = [c for c in cols_m if c in df_c.columns]
            st.dataframe(df_c[cols_d] if cols_d else df_c, use_container_width=True, hide_index=True)
            st.caption(f"{len(df_c)} viajes cancelados")
