"""
consulta_ruta.py — Cotizador Igloo
Consulta individual de ruta con simulación de diesel/rendimiento.
Diseño homologado con Lincoln y Set Logis:
  - Sin st.title()
  - Botón recargar en col [1,4]
  - Resultados con mostrar_resultados_utilidad() → kpi_row + semaforos_ruta
  - Desglose con st.markdown("### emoji Título") por sección
  - Generación de PDF sin cambios
"""

import os
import tempfile
from datetime import datetime

import pandas as pd
import streamlit as st

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable

from services.supabase_client import get_supabase_client
from ui.components import section_header, alert, divider

from .helpers import (
    cargar_datos_generales,
    safe_number,
    calcular_utilidades,
    mostrar_resultados_utilidad,
)


# ─────────────────────────────────────────────
# CACHE
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=120)
def _load_rutas_igloo_cached(table_name: str) -> pd.DataFrame:
    supabase = get_supabase_client()
    if supabase is None:
        return pd.DataFrame()
    try:
        resp = supabase.table(table_name).select("*").order("Fecha", desc=True).execute()
        return pd.DataFrame(resp.data) if resp.data else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


# ─────────────────────────────────────────────
# FILTROS Y LABEL
# ─────────────────────────────────────────────
def _filtrar_rutas(df: pd.DataFrame, prefix_key: str) -> pd.DataFrame:
    with st.expander("🔎 Filtros de búsqueda (opcional)", expanded=False):
        fc1, fc2, fc3, fc4, fc5 = st.columns(5)
        tipos_disp    = ["Todos"] + sorted(df["Tipo"].dropna().unique().tolist()) if "Tipo" in df.columns else ["Todos"]
        clientes_disp = ["Todos"] + sorted(df["Cliente"].dropna().astype(str).unique().tolist()) if "Cliente" in df.columns else ["Todos"]
        filtro_tipo    = fc1.selectbox("Tipo",              tipos_disp,    key=f"{prefix_key}_ftipo")
        filtro_cliente = fc2.selectbox("Cliente",           clientes_disp, key=f"{prefix_key}_fcliente")
        filtro_origen  = fc3.text_input("Origen contiene",                 key=f"{prefix_key}_forigen")
        filtro_destino = fc4.text_input("Destino contiene",                key=f"{prefix_key}_fdestino")
        filtro_id      = fc5.text_input("ID Ruta",          placeholder="IG000123", key=f"{prefix_key}_fid")

    resultado = df.copy()
    if filtro_tipo    != "Todos": resultado = resultado[resultado["Tipo"] == filtro_tipo]
    if filtro_cliente != "Todos": resultado = resultado[resultado["Cliente"].astype(str) == filtro_cliente]
    if filtro_origen.strip():     resultado = resultado[resultado["Origen"].astype(str).str.contains(filtro_origen.strip(), case=False, na=False)]
    if filtro_destino.strip():    resultado = resultado[resultado["Destino"].astype(str).str.contains(filtro_destino.strip(), case=False, na=False)]
    if filtro_id.strip():         resultado = resultado[resultado["ID_Ruta"].astype(str).str.contains(filtro_id.strip(), case=False, na=False)]
    return resultado


def _format_ruta_label(row) -> str:
    fecha = str(row.get("Fecha", ""))[:10]
    return (
        f"{row.get('ID_Ruta', '')} | {fecha} | "
        f"{row.get('Tipo', '')} | {row.get('Cliente', '')} | "
        f"{row.get('Origen', '')} → {row.get('Destino', '')}"
    )


# ─────────────────────────────────────────────
# PDF (sin cambios en lógica)
# ─────────────────────────────────────────────
def generar_pdf_profesional(ruta, ingreso_total, costo_total,
                             utilidad_bruta, costos_indirectos,
                             utilidad_neta, pct_bruta, pct_neta,
                             simulando=False, rend_sim=None, diesel_sim=None):
    tmp  = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    doc  = SimpleDocTemplate(tmp.name, pagesize=letter,
                              leftMargin=0.5*inch, rightMargin=0.5*inch,
                              topMargin=0.5*inch,  bottomMargin=0.5*inch)
    styles       = getSampleStyleSheet()
    title_style  = ParagraphStyle("Title",  parent=styles["Normal"], fontSize=14, fontName="Helvetica-Bold", textColor=colors.HexColor("#1B2266"), spaceAfter=6)
    subtitle_style = ParagraphStyle("Sub",  parent=styles["Normal"], fontSize=10, fontName="Helvetica-Bold", textColor=colors.HexColor("#1B2266"), spaceBefore=8, spaceAfter=4)
    normal_style = ParagraphStyle("Normal2", parent=styles["Normal"], fontSize=8)
    story = []

    # Encabezado
    empresa_nombre = "Igloo Transport"
    story.append(Paragraph(f"{empresa_nombre} — Reporte de Ruta", title_style))
    if simulando:
        story.append(Paragraph(f"⚠️ MODO SIMULACIÓN — Rendimiento: {rend_sim:.2f} km/L · Diesel: ${diesel_sim:.2f}/L", normal_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1B2266")))
    story.append(Spacer(1, 8))

    # Datos generales
    story.append(Paragraph("Datos Generales", subtitle_style))
    gen_data = [
        ["ID Ruta", ruta.get("ID_Ruta", ""), "Fecha", str(ruta.get("Fecha", ""))],
        ["Tipo", ruta.get("Tipo", ""), "Modo de Viaje", ruta.get("Modo de Viaje", "")],
        ["Cliente", ruta.get("Cliente", ""), "Origen → Destino", f"{ruta.get('Origen','')} → {ruta.get('Destino','')}"],
        ["KM", f"{safe_number(ruta.get('KM',0)):,.2f}", "Horas Termo", f"{safe_number(ruta.get('Horas_Termo',0)):,.2f}"],
    ]
    gen_table = Table(gen_data, colWidths=[1.5*inch, 2*inch, 1.5*inch, 2*inch])
    gen_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#EEF0F8")),
        ("BACKGROUND", (2,0), (2,-1), colors.HexColor("#EEF0F8")),
        ("FONTNAME",   (0,0), (-1,-1), "Helvetica"),
        ("FONTSIZE",   (0,0), (-1,-1), 7),
        ("GRID",       (0,0), (-1,-1), 0.5, colors.HexColor("#dee2e6")),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0), (-1,-1), 2),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2),
    ]))
    story.append(gen_table)
    story.append(Spacer(1, 8))

    # Ingresos
    story.append(Paragraph("Ingresos", subtitle_style))
    ing_data = [["Concepto", "Monto"]]
    ing_data.append(["Ingreso Flete",       f"${safe_number(ruta.get('Ingreso Flete', 0)):,.2f}"])
    ing_data.append(["Ingreso Cruce",       f"${safe_number(ruta.get('Ingreso Cruce', 0)):,.2f}"])
    ing_data.append(["Costo Cruce",         f"-${safe_number(ruta.get('Costo Cruce Convertido', 0)):,.2f}"])
    ing_data.append(["INGRESO TOTAL",       f"${ingreso_total:,.2f}"])
    ing_table = Table(ing_data, colWidths=[3.5*inch, 3.5*inch])
    ing_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1B2266")),
        ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,-1), 7),
        ("GRID",       (0,0), (-1,-1), 0.5, colors.HexColor("#dee2e6")),
        ("ALIGN",      (1,1), (-1,-1), "RIGHT"),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0), (-1,-1), 1),
        ("BOTTOMPADDING", (0,0), (-1,-1), 1),
    ]))
    story.append(ing_table)
    story.append(Spacer(1, 8))

    # Costos Operativos
    story.append(Paragraph("Costos Operativos", subtitle_style))
    costos_op_data = [["Concepto", "Monto"]]
    costos_op_data.append(["Diesel Camión ({:.2f} km/L)".format(safe_number(ruta.get("Rendimiento Camion", rend_sim or 2.5))), f"${safe_number(ruta.get('Costo_Diesel_Camion',0)):,.2f}"])
    costos_op_data.append(["Diesel Termo ({:.2f} hrs·L)".format(safe_number(ruta.get("Rendimiento Termo", 3.0))),              f"${safe_number(ruta.get('Costo_Diesel_Termo',0)):,.2f}"])
    costos_op_data.append(["Sueldo Operador",   f"${safe_number(ruta.get('Sueldo_Operador',0)):,.2f}"])
    costos_op_data.append(["Bono ISR/IMSS",     f"${safe_number(ruta.get('Bono',0)):,.2f}"])
    costos_op_data.append(["Casetas",            f"${safe_number(ruta.get('Casetas',0)):,.2f}"])
    costos_op_data.append(["Costo Cruce",        f"${safe_number(ruta.get('Costo Cruce Convertido',0)):,.2f}"])
    costos_table = Table(costos_op_data, colWidths=[3.5*inch, 3.5*inch])
    costos_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1B2266")),
        ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,-1), 7),
        ("GRID",       (0,0), (-1,-1), 0.5, colors.HexColor("#dee2e6")),
        ("ALIGN",      (1,1), (-1,-1), "RIGHT"),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0), (-1,-1), 1),
        ("BOTTOMPADDING", (0,0), (-1,-1), 1),
    ]))
    story.append(costos_table)
    story.append(Spacer(1, 8))

    # Otros costos
    story.append(Paragraph("Otros Costos", subtitle_style))
    otros_items = [
        ("Puntualidad",    safe_number(ruta.get("Puntualidad",      0))),
        ("Fianza Termo",   safe_number(ruta.get("Fianza_Termo",     0))),
        ("Lavado Termo",   safe_number(ruta.get("Lavado_Termo",     0))),
        ("Movimiento Local", safe_number(ruta.get("Movimiento_Local",0))),
        ("Pensión",        safe_number(ruta.get("Pension",          0))),
        ("Estancia",       safe_number(ruta.get("Estancia",         0))),
        ("Renta Termo",    safe_number(ruta.get("Renta_Termo",      0))),
        ("Pistas Extra",   safe_number(ruta.get("Pistas_Extra",     0))),
        ("Stop",           safe_number(ruta.get("Stop",             0))),
        ("Falso",          safe_number(ruta.get("Falso",            0))),
        ("Gatas",          safe_number(ruta.get("Gatas",            0))),
        ("Accesorios",     safe_number(ruta.get("Accesorios",       0))),
        ("Guías",          safe_number(ruta.get("Guias",            0))),
    ]
    otros_data = [["Concepto", "Monto"]]
    for concepto, monto in otros_items:
        if monto > 0:
            otros_data.append([concepto, f"${monto:,.2f}"])
    if len(otros_data) == 1:
        otros_data.append(["(Sin costos extras en esta ruta)", ""])
    otros_table = Table(otros_data, colWidths=[3.5*inch, 3.5*inch])
    otros_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1B2266")),
        ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,-1), 7),
        ("GRID",       (0,0), (-1,-1), 0.5, colors.HexColor("#dee2e6")),
        ("ALIGN",      (1,1), (-1,-1), "RIGHT"),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0), (-1,-1), 1),
        ("BOTTOMPADDING", (0,0), (-1,-1), 1),
    ]))
    story.append(otros_table)
    story.append(Spacer(1, 12))

    # Footer
    footer_style = ParagraphStyle("Footer", parent=styles["Normal"], fontSize=7,
                                   textColor=colors.HexColor("#6c757d"), alignment=TA_CENTER)
    story.append(Paragraph(
        f"Reporte generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} — Igloo Transport",
        footer_style,
    ))
    doc.build(story)
    return tmp.name


# ─────────────────────────────────────────────
# RENDER PRINCIPAL
# ─────────────────────────────────────────────
def render():
    supabase = get_supabase_client()
    if supabase is None:
        alert("warn", "⚠️ Supabase no configurado.")
        return

    TABLE_RUTAS = "Rutas"
    valores     = cargar_datos_generales()

    # ── Recargar ──────────────────────────────────────────────────
    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("🔄 Recargar", key="igloo_cons_reload"):
            _load_rutas_igloo_cached.clear()
            st.rerun()
    with c2:
        st.caption("Carga cacheada 2 min. Usa 'Recargar' si acabas de guardar algo.")

    df = _load_rutas_igloo_cached(TABLE_RUTAS)
    if df.empty:
        alert("warn", "⚠️ No hay rutas guardadas todavía.")
        return

    if "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.date
    if "ID_Ruta" in df.columns:
        df.set_index("ID_Ruta", inplace=True, drop=False)

    # ── Filtros y selector ────────────────────────────────────────
    df_filtrado = _filtrar_rutas(df, "igloo_cons")
    if df_filtrado.empty:
        alert("info", "No hay rutas que coincidan con los filtros.")
        return

    index_sel = st.selectbox(
        "Selecciona la ruta a consultar",
        df_filtrado.index.tolist(),
        format_func=lambda i: _format_ruta_label(df_filtrado.loc[i]),
        key="igloo_cons_select",
    )

    ruta      = df_filtrado.loc[index_sel]
    tipo_ruta = str(ruta.get("Tipo", "")).strip().upper()

    rend_reg = float(safe_number(
        ruta.get("Rendimiento_Camion", ruta.get("Rendimiento Camion", valores.get("Rendimiento Camion", 2.5)))
    ))

    # ── Ajustes para simulación ───────────────────────────────────
    divider()
    section_header("⚙️", "Ajustes para Simulación")
    costo_diesel_input = st.number_input(
        "Costo del Diesel ($/L)",
        value=float(valores.get("Costo Diesel", 24.0)),
        key="igloo_cons_diesel",
    )
    st.markdown(f"> Rendimiento Camión **registrado**: **{rend_reg:.2f} km/L** (solo referencia)")
    rendimiento_input = st.number_input(
        "Rendimiento Camión para Simulación (km/L)",
        value=float(rend_reg),
        key="igloo_cons_rend_sim",
    )
    if st.button("🔁 Simular", key="igloo_cons_sim"):
        st.session_state["igloo_simular"] = True

    # ── Resultados ────────────────────────────────────────────────
    if st.session_state.get("igloo_simular", False):
        ingreso_total = safe_number(ruta.get("Ingreso Total", 0))
        km            = safe_number(ruta.get("KM", 0))
        horas_termo   = safe_number(ruta.get("Horas_Termo", 0))
        rend_termo    = float(valores.get("Rendimiento Termo", 3.0))

        costo_diesel_camion = (km / rendimiento_input) * costo_diesel_input if rendimiento_input else 0
        costo_diesel_termo  = horas_termo * rend_termo * costo_diesel_input

        costo_total = (
            costo_diesel_camion
            + costo_diesel_termo
            + safe_number(ruta.get("Sueldo_Operador", 0))
            + safe_number(ruta.get("Bono", 0))
            + safe_number(ruta.get("Casetas", 0))
            + safe_number(ruta.get("Costo Cruce Convertido", 0))
            + safe_number(ruta.get("Costo_Extras", 0))
        )

        util = calcular_utilidades(ingreso_total, costo_total, tipo_ruta)

        alert("success", "🔧 Estás viendo una **simulación** con los valores de diesel/rendimiento ajustados.")

        mostrar_resultados_utilidad(
            st,
            ingreso_total, costo_total,
            util["utilidad_bruta"], util["costos_indirectos"],
            util["utilidad_neta"], util["porcentaje_bruta"], util["porcentaje_neta"],
            tipo=tipo_ruta,
            tc_usd=float(valores.get("Tipo de cambio USD", 19.5)),
        )

        # Conversión a USD si aplica
        tipo_cambio = safe_number(ruta.get("Tipo de cambio", 0))
        if tipo_cambio > 0 and str(ruta.get("Moneda", "")) == "USD":
            st.info(f"💵 **Utilidad Neta en USD:** ${util['utilidad_neta'] / tipo_cambio:,.2f}  _(TC: ${tipo_cambio:,.2f} MXP/USD)_")

        # ── Desglose detallado ────────────────────────────────────
        divider()
        st.markdown("### 📋 Información General")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.caption(f"**Fecha:** {ruta.get('Fecha', '')}")
            st.caption(f"**ID Ruta:** {ruta.get('ID_Ruta', '')}")
            st.caption(f"**Tipo:** {tipo_ruta}")
            st.caption(f"**Modo:** {ruta.get('Modo de Viaje', 'Sencillo')}")
            st.caption(f"**Cliente:** {ruta.get('Cliente', '')}")
            st.caption(f"**Origen → Destino:** {ruta.get('Origen', '')} → {ruta.get('Destino', '')}")
            st.caption(f"**KM:** {safe_number(ruta.get('KM', 0)):,.2f}")
            st.caption(f"**Horas Termo:** {horas_termo:,.2f} hrs")
            st.caption(f"**Rendimiento Camión:** {rend_reg:.2f} km/L")
            st.caption(f"**Precio Diesel:** ${safe_number(ruta.get('Costo Diesel', 0)):,.2f}/L")
            if tipo_ruta == "DOM MEX":
                modo_p = ruta.get("Modo_Pago_Dom", "km")
                st.caption(f"**Modo Pago DOM MEX:** {'Por km' if modo_p == 'km' else 'Fijo'}")

        with c2:
            st.markdown("### 💰 Ingresos")
            st.caption(f"**Moneda Flete:** {ruta.get('Moneda', '')}")
            st.caption(f"**Ingreso Flete Original:** ${safe_number(ruta.get('Ingreso_Original', 0)):,.2f}")
            st.caption(f"**TC Flete:** {safe_number(ruta.get('Tipo de cambio', 0)):,.2f}")
            st.caption(f"**Ingreso Flete Convertido:** ${safe_number(ruta.get('Ingreso Flete', 0)):,.2f}")
            st.caption(f"**Moneda Cruce:** {ruta.get('Moneda_Cruce', '')}")
            st.caption(f"**Ingreso Cruce Original:** ${safe_number(ruta.get('Cruce_Original', 0)):,.2f}")
            st.caption(f"**Ingreso Cruce Convertido:** ${safe_number(ruta.get('Ingreso Cruce', 0)):,.2f}")
            st.caption(f"**Costo Cruce Convertido:** ${safe_number(ruta.get('Costo Cruce Convertido', 0)):,.2f}")
            st.caption(f"**Ingreso Total:** ${ingreso_total:,.2f}")

        with c3:
            st.markdown("### 📉 Costos Directos")
            st.caption(f"**Diesel Camión:** ${costo_diesel_camion:,.2f}")
            st.caption(f"**Diesel Termo:** ${costo_diesel_termo:,.2f}")
            st.caption(f"**Sueldo Operador:** ${safe_number(ruta.get('Sueldo_Operador', 0)):,.2f}")
            st.caption(f"**Bono ISR/IMSS:** ${safe_number(ruta.get('Bono', 0)):,.2f}")
            st.caption(f"**Casetas:** ${safe_number(ruta.get('Casetas', 0)):,.2f}")

            # Otros costos fijos
            otros_fijos = {
                "Lavado Termo":    safe_number(ruta.get("Lavado_Termo", 0)),
                "Mov. Local":      safe_number(ruta.get("Movimiento_Local", 0)),
                "Puntualidad":     safe_number(ruta.get("Puntualidad", 0)),
                "Pensión":         safe_number(ruta.get("Pension", 0)),
                "Estancia":        safe_number(ruta.get("Estancia", 0)),
                "Fianza Termo":    safe_number(ruta.get("Fianza_Termo", 0)),
                "Renta Termo":     safe_number(ruta.get("Renta_Termo", 0)),
            }
            for nombre, val in otros_fijos.items():
                if val > 0:
                    st.caption(f"**{nombre}:** ${val:,.2f}")

            # Extras
            extras_items = {
                "Pistas Extra": safe_number(ruta.get("Pistas_Extra", 0)),
                "Stop":         safe_number(ruta.get("Stop", 0)),
                "Falso":        safe_number(ruta.get("Falso", 0)),
                "Gatas":        safe_number(ruta.get("Gatas", 0)),
                "Accesorios":   safe_number(ruta.get("Accesorios", 0)),
                "Guías":        safe_number(ruta.get("Guias", 0)),
            }
            hay_extras = any(v > 0 for v in extras_items.values())
            if hay_extras:
                st.caption("---")
                for nombre, val in extras_items.items():
                    if val > 0:
                        cobrado = bool(ruta.get(f"Cobra_{nombre.replace(' ','_').replace('í','i').replace('ó','o')}", False))
                        etiq    = "✅ cobrado" if cobrado else "costo interno"
                        st.caption(f"**{nombre}:** ${val:,.2f} _{etiq}_")

            st.caption(f"**Costo Total:** ${costo_total:,.2f}")

        # ── PDF ───────────────────────────────────────────────────
        divider()
        if st.button("📄 Generar PDF", key="igloo_cons_pdf"):
            with st.spinner("Generando PDF..."):
                try:
                    pdf_path = generar_pdf_profesional(
                        ruta.to_dict(), ingreso_total, costo_total,
                        util["utilidad_bruta"], util["costos_indirectos"],
                        util["utilidad_neta"], util["porcentaje_bruta"], util["porcentaje_neta"],
                        simulando=(rendimiento_input != rend_reg),
                        rend_sim=rendimiento_input,
                        diesel_sim=costo_diesel_input,
                    )
                    with open(pdf_path, "rb") as f:
                        st.download_button(
                            "📥 Descargar PDF",
                            data=f.read(),
                            file_name=f"ruta_{ruta.get('ID_Ruta', 'igloo')}.pdf",
                            mime="application/pdf",
                            key="igloo_cons_pdf_dl",
                        )
                except Exception as e:
                    alert("error", f"❌ Error al generar PDF: {e}")
