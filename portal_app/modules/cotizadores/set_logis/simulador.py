"""
simulador.py – Set Logis Plus
Simulador de Vuelta Redonda con sugerencias de tramo Empty.

Flujo:
  1. Selecciona ruta principal (NB / SB / D2DNB / D2DSB)
  2. El sistema sugiere rutas Empty ordenadas por % Ut. Bruta
     - Para NB/D2DNB: Empty cuyo origen coincide con el DESTINO USA de la ruta
     - Para SB/D2DSB: Empty cuyo destino coincide con el ORIGEN USA de la ruta
  3. Usuario elige una Empty (o ninguna)
  4. Resumen combinado con ruta visual en orden correcto:
     - NB/D2DNB: Origen USA → Destino USA → [Origen Empty → Destino Empty] → [Origen MX → Destino MX]
     - SB/D2DSB: [Origen MX → Destino MX] → [Origen Empty → Destino Empty] → Origen USA → Destino USA

Notas de cálculo:
  - Las rutas se usan tal como están guardadas (ya recalculadas en _shared).
  - NO se recalculan millas vacías en el combinado: cada ruta trae su propio costo.
  - La Empty ya tiene su costo de millas vacías capturado al guardarla.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from services.supabase_client import get_supabase_client
from ui.components import section_header, alert, divider, kpi_row, semaforos_ruta
from ._shared import (
    TABLE_RUTAS,
    TIPOS_SUBIDA,
    TIPOS_BAJADA,
    cargar_datos_generales,
    safe,
)

TIPOS_PRINCIPAL = ["NB", "SB", "D2DNB", "D2DSB"]
TIPO_EMPTY      = "Empty"


# ─────────────────────────────────────────────
# CACHE
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=120)
def _cargar_rutas(table: str) -> pd.DataFrame:
    sb = get_supabase_client()
    if sb is None:
        return pd.DataFrame()
    try:
        resp = sb.table(table).select("*").order("Fecha", desc=True).execute()
        df = pd.DataFrame(resp.data or [])
        if df.empty:
            return df
        for col in ["Ingreso_Global", "Costo_Directo", "Costo_Total",
                    "Utilidad_Bruta", "Utilidad_Neta", "Pct_Ut_Bruta", "Pct_Ut_Neta"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        if "Fecha" in df.columns:
            df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d")
        return df
    except Exception:
        return pd.DataFrame()


# ─────────────────────────────────────────────
# HELPERS DE RUTA
# ─────────────────────────────────────────────
def _origen_usa(ruta: pd.Series) -> str:
    """Primer tramo de Ruta_USA: 'LAREDO, TX - DALLAS, TX' → 'LAREDO, TX'"""
    ruta_str = str(ruta.get("Ruta_USA", ""))
    partes = ruta_str.split(" - ", 1)
    return partes[0].strip().upper()


def _destino_usa(ruta: pd.Series) -> str:
    """Último tramo de Ruta_USA."""
    ruta_str = str(ruta.get("Ruta_USA", ""))
    partes = ruta_str.split(" - ", 1)
    return partes[-1].strip().upper()


def _coincide(a: str, b: str) -> bool:
    """Coincidencia flexible: compara las primeras palabras del texto."""
    if not a or not b:
        return False
    # Primeras 2 palabras de cada ciudad para tolerancia de abreviaciones
    def _palabras(s):
        return " ".join(s.upper().strip().split()[:2])
    return _palabras(a) == _palabras(b)


def _sugerir_empty(df_empty: pd.DataFrame, ruta_principal: pd.Series) -> pd.DataFrame:
    """
    Filtra y ordena las rutas Empty según la ruta principal.
    - NB/D2DNB → busca Empty cuyo ORIGEN coincide con DESTINO USA de la ruta principal
    - SB/D2DSB → busca Empty cuyo DESTINO coincide con ORIGEN USA de la ruta principal
    Ordena de mayor a menor % Ut. Bruta (sin contar millas vacías adicionales).
    """
    if df_empty.empty:
        return pd.DataFrame()

    tipo = str(ruta_principal.get("Tipo_Viaje", ""))
    destino_p = _destino_usa(ruta_principal)
    origen_p  = _origen_usa(ruta_principal)

    if tipo in TIPOS_SUBIDA:
        # Empty sale del destino de la subida
        mask = df_empty.apply(lambda r: _coincide(_origen_usa(r), destino_p), axis=1)
    else:
        # Empty llega al origen de la bajada
        mask = df_empty.apply(lambda r: _coincide(_destino_usa(r), origen_p), axis=1)

    sugeridas = df_empty[mask].copy()

    # Si no hay coincidencias exactas mostramos todas ordenadas
    if sugeridas.empty:
        sugeridas = df_empty.copy()

    return sugeridas.sort_values("Pct_Ut_Bruta", ascending=False)


def _label_ruta(row: pd.Series, mostrar_pct: bool = True) -> str:
    pct = f" | {safe(row.get('Pct_Ut_Bruta')):.1f}% Ut.B" if mostrar_pct else ""
    return (
        f"{row.get('ID_Ruta', '')} | "
        f"{row.get('Fecha', '')} | "
        f"{row.get('Tipo_Viaje', '')} | "
        f"{row.get('Cliente', '')} | "
        f"{row.get('Ruta_USA', '')}"
        f"{pct}"
    )


# ─────────────────────────────────────────────
# VISUALIZACIÓN DE RUTA COMPLETA
# ─────────────────────────────────────────────
def _mostrar_ruta_visual(
    ruta_p: pd.Series,
    ruta_e: pd.Series | None,
) -> None:
    """
    Muestra la secuencia visual de la ruta completa en orden correcto.
    NB/D2DNB: Origen USA → Destino USA → [Origen E → Destino E] → [Origen MX → Destino MX]
    SB/D2DSB: [Origen MX → Destino MX] → [Origen E → Destino E] → Origen USA → Destino USA
    """
    tipo = str(ruta_p.get("Tipo_Viaje", ""))
    es_subida = tipo in TIPOS_SUBIDA

    origen_usa  = _origen_usa(ruta_p)
    destino_usa = _destino_usa(ruta_p)
    origen_mx   = str(ruta_p.get("Origen_MX", "")).strip()
    destino_mx  = str(ruta_p.get("Destino_MX", "")).strip()
    tiene_mx    = bool(origen_mx and destino_mx)

    if ruta_e is not None:
        origen_e  = _origen_usa(ruta_e)
        destino_e = _destino_usa(ruta_e)
    else:
        origen_e = destino_e = None

    # Construir secuencia
    if es_subida:
        pasos = []
        pasos.append(("🇺🇸", origen_usa, "Origen USA"))
        pasos.append(("📍", destino_usa, "Destino USA"))
        if origen_e:
            pasos.append(("⬜", origen_e,  "Inicio Vacío"))
            pasos.append(("⬜", destino_e, "Fin Vacío"))
        if tiene_mx:
            pasos.append(("🇲🇽", origen_mx,  "Origen MX"))
            pasos.append(("🇲🇽", destino_mx,  "Destino MX"))
    else:
        pasos = []
        if tiene_mx:
            pasos.append(("🇲🇽", origen_mx,  "Origen MX"))
            pasos.append(("🇲🇽", destino_mx,  "Destino MX"))
        if origen_e:
            pasos.append(("⬜", origen_e,  "Inicio Vacío"))
            pasos.append(("⬜", destino_e, "Fin Vacío"))
        pasos.append(("🇺🇸", origen_usa, "Origen USA"))
        pasos.append(("📍", destino_usa, "Destino USA"))

    # Renderizar
    partes_html = []
    for icono, lugar, etiqueta in pasos:
        partes_html.append(
            f'<span style="font-size:0.75rem;color:#6B7280;">{etiqueta}</span><br>'
            f'<span style="font-weight:600;">{icono} {lugar or "—"}</span>'
        )

    separador = ' &nbsp;<span style="color:#1B2266;font-size:1.2rem;">→</span>&nbsp; '
    st.markdown(
        f'<div style="background:#F0F4FF;border-radius:8px;padding:12px 16px;'
        f'display:flex;flex-wrap:wrap;gap:8px;align-items:center;">'
        + separador.join(partes_html)
        + '</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────
# TARJETA DE RUTA INDIVIDUAL
# ─────────────────────────────────────────────
def _tarjeta_ruta(titulo: str, ruta: pd.Series, badge: str = "") -> None:
    ut_bruta = safe(ruta.get("Utilidad_Bruta"))
    pct_ub   = safe(ruta.get("Pct_Ut_Bruta"))
    color    = "#10b981" if ut_bruta >= 0 else "#dc2626"

    with st.container(border=True):
        h1, h2 = st.columns([3, 1])
        with h1:
            st.markdown(f"**{titulo}** {badge}")
            st.caption(
                f"{ruta.get('ID_Ruta', '')} · "
                f"{ruta.get('Tipo_Viaje', '')} · "
                f"{ruta.get('Cliente', '—')} · "
                f"{ruta.get('Ruta_USA', '')}"
            )
        with h2:
            st.markdown(
                f'<div style="text-align:right;color:{color};">'
                f'<div style="font-size:1rem;font-weight:800;">${ut_bruta:,.2f}</div>'
                f'<div style="font-size:0.72rem;">{pct_ub:.1f}% Ut. Bruta</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Ingreso",      f"${safe(ruta.get('Ingreso_Global')):,.2f}")
        m2.metric("Costo Dir.",   f"${safe(ruta.get('Costo_Directo')):,.2f}")
        m3.metric("Ut. Neta",     f"${safe(ruta.get('Utilidad_Neta')):,.2f}")
        m4.metric("Miles Load",   f"{safe(ruta.get('Miles_Load')):.0f} mi")


# ─────────────────────────────────────────────
# RESUMEN COMBINADO
# ─────────────────────────────────────────────
def _resumen_combinado(ruta_p: pd.Series, ruta_e: pd.Series | None) -> None:
    divider()
    section_header("🏁", "Resultado Vuelta Redonda")

    # Sumar valores de las rutas seleccionadas
    rutas = [ruta_p]
    if ruta_e is not None:
        rutas.append(ruta_e)

    def _sum(campo: str) -> float:
        return sum(safe(r.get(campo)) for r in rutas)

    ing_vr  = _sum("Ingreso_Global")
    cd_vr   = _sum("Costo_Directo")
    ci_vr   = _sum("Costo_Indirecto")
    ct_vr   = _sum("Costo_Total")
    ub_vr   = _sum("Utilidad_Bruta")
    un_vr   = _sum("Utilidad_Neta")
    mi_vr   = _sum("Miles_Load") + _sum("Short_Miles")

    pct_ub = (ub_vr / ing_vr * 100) if ing_vr else 0.0
    pct_un = (un_vr / ing_vr * 100) if ing_vr else 0.0
    pct_cd = (cd_vr / ing_vr * 100) if ing_vr else 0.0
    pct_ci = (ci_vr / ing_vr * 100) if ing_vr else 0.0

    color_ub = "#10b981" if ub_vr >= 0 else "#dc2626"
    color_un = "#10b981" if un_vr >= 0 else "#dc2626"

    kpi_row([
        {"icono": "💵", "label": "Ingreso VR",      "valor": f"${ing_vr:,.2f}",  "color": "#1B2266"},
        {"icono": "📦", "label": "Costo Directo",   "valor": f"${cd_vr:,.2f}",   "color": "#6B7280"},
        {"icono": "🔁", "label": "Costo Indirecto", "valor": f"${ci_vr:,.2f}",   "color": "#F59E0B"},
        {"icono": "📈", "label": "Ut. Bruta",        "valor": f"${ub_vr:,.2f}",   "color": color_ub},
        {"icono": "🏆", "label": "Ut. Neta",         "valor": f"${un_vr:,.2f}",   "color": color_un},
    ])

    # Porcentajes
    p1, p2, p3, p4, p5 = st.columns(5)
    p1.metric("% C. Directo",   f"{pct_cd:.1f}%")
    p2.metric("% C. Indirecto", f"{pct_ci:.1f}%")
    p3.metric("% Ut. Bruta",    f"{pct_ub:.1f}%")
    p4.metric("% Ut. Neta",     f"{pct_un:.1f}%")
    p5.metric("Ingreso/Milla",  f"${(ing_vr / mi_vr):,.3f}" if mi_vr > 0 else "—")

    # Semáforos
    divider()
    semaforos_ruta({
        "Pct_Costo_Directo":   pct_cd,
        "Pct_Ut_Bruta":        pct_ub,
        "Pct_Costo_Indirecto": pct_ci,
        "Pct_Ut_Neta":         pct_un,
    })

    # Ruta visual
    divider()
    section_header("🗺️", "Secuencia de la Ruta Completa")
    _mostrar_ruta_visual(ruta_p, ruta_e)


# ─────────────────────────────────────────────
# RENDER PRINCIPAL
# ─────────────────────────────────────────────
def render() -> None:
    sb = get_supabase_client()
    if sb is None:
        alert("error", "Supabase no configurado.")
        return

    # Recargar
    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("🔄 Recargar", key="sl_sim_reload"):
            _cargar_rutas.clear()
            st.rerun()
    with c2:
        st.caption("Carga cacheada 2 min.")

    df = _cargar_rutas(TABLE_RUTAS)
    if df.empty:
        alert("warn", "No hay rutas guardadas todavía.")
        alert("info", "Captura rutas primero desde la pestaña Captura de Rutas.")
        return

    # Separar por tipo
    df_principal = df[df["Tipo_Viaje"].isin(TIPOS_PRINCIPAL)].copy() if "Tipo_Viaje" in df.columns else pd.DataFrame()
    df_empty     = df[df["Tipo_Viaje"] == TIPO_EMPTY].copy()          if "Tipo_Viaje" in df.columns else pd.DataFrame()

    if df_principal.empty:
        alert("warn", "No hay rutas principales (NB/SB/D2DNB/D2DSB) guardadas.")
        return

    df_principal = df_principal.set_index("ID_Ruta", drop=False)

    # ── 1. RUTA PRINCIPAL ─────────────────────────────────────────────────────
    divider()
    section_header("🚛", "Ruta Principal")

    fp1, fp2, fp3 = st.columns(3)
    tipos_disp = sorted(df_principal["Tipo_Viaje"].dropna().unique().tolist())
    f_tipo     = fp1.selectbox("Filtrar por tipo", ["Todos"] + tipos_disp, key="sl_sim_ftipo")
    clientes_p = sorted(df_principal["Cliente"].dropna().astype(str).unique().tolist())
    f_cli      = fp2.selectbox("Filtrar por cliente", ["Todos"] + clientes_p, key="sl_sim_fcli")

    df_pf = df_principal.copy()
    if f_tipo != "Todos":
        df_pf = df_pf[df_pf["Tipo_Viaje"] == f_tipo]
    if f_cli != "Todos":
        df_pf = df_pf[df_pf["Cliente"].astype(str) == f_cli]

    if df_pf.empty:
        alert("info", "No hay rutas con esos filtros.")
        return

    idx_p = st.selectbox(
        f"Selecciona ruta principal ({len(df_pf)} disponibles)",
        options=df_pf.index.tolist(),
        format_func=lambda i: _label_ruta(df_pf.loc[i], mostrar_pct=True),
        key="sl_sim_ruta_p",
    )

    ruta_p = df_pf.loc[idx_p]
    _tarjeta_ruta("Ruta Principal", ruta_p)

    tipo_p    = str(ruta_p.get("Tipo_Viaje", ""))
    es_subida = tipo_p in TIPOS_SUBIDA

    # ── 2. TRAMO EMPTY (sugerencias) ─────────────────────────────────────────
    divider()
    section_header("⬜", "Tramo Vacío (opcional)")

    if df_empty.empty:
        alert("info", "No hay rutas tipo Empty guardadas. Puedes continuar sin tramo vacío.")
        ruta_e     = None
        idx_e      = None
    else:
        df_empty_idx = df_empty.set_index("ID_Ruta", drop=False)
        df_sug       = _sugerir_empty(df_empty_idx, ruta_p)

        destino_ref = _destino_usa(ruta_p) if es_subida else _origen_usa(ruta_p)
        hay_coincidencia = not df_sug.empty and _coincide(
            _origen_usa(df_sug.iloc[0]) if es_subida else _destino_usa(df_sug.iloc[0]),
            destino_ref,
        )

        if hay_coincidencia:
            st.caption(
                f"✅ Se encontraron rutas Empty cuyo "
                f"{'origen' if es_subida else 'destino'} coincide con "
                f"**{destino_ref}** — ordenadas por % Ut. Bruta."
            )
        else:
            st.caption(
                f"ℹ️ No se encontró coincidencia exacta con **{destino_ref}**. "
                f"Se muestran todas las rutas Empty disponibles ordenadas por % Ut. Bruta."
            )

        idx_e = st.selectbox(
            "Selecciona tramo vacío (o deja en blanco para omitir)",
            options=[""] + df_sug.index.tolist(),
            format_func=lambda i: "— Sin tramo vacío —" if i == "" else _label_ruta(df_sug.loc[i]),
            key="sl_sim_ruta_e",
        )

        if idx_e:
            ruta_e = df_sug.loc[idx_e]
            _tarjeta_ruta("Tramo Vacío", ruta_e, badge="⬜")
        else:
            ruta_e = None
            st.caption("Sin tramo vacío seleccionado.")

    # ── 3. RESUMEN COMBINADO ──────────────────────────────────────────────────
    _resumen_combinado(ruta_p, ruta_e)
