# portal_app/modules/facturacion/cargar_datos.py
# Carga de clientes y facturas desde Excel/CSV.
import streamlit as st
import pandas as pd

from modules.facturacion._shared import leer_json, guardar_json
from ui.components import page_banner, section_header, alert, divider


def render():
    page_banner("📤", "Cargar Datos — Facturación", "Importa clientes o facturas desde Excel/CSV")

    data                = leer_json()
    clientes_existentes = {c["id"]: c for c in data.get("clientes", [])}
    facturas_existentes = {f["folio"]: f for f in data.get("facturas", [])}

    tab_cli, tab_fact = st.tabs(["🏢 Clientes", "🧾 Facturas"])

    # ── Tab Clientes ──────────────────────────────────────────────────────────
    with tab_cli:
        section_header("🏢", "Importar Clientes")
        st.caption(
            "Columnas requeridas: `id`, `nombre`, `razon_social`, `limite_credito`, "
            "`condiciones_pago`, `banco`, `banco_empresa`, `cuenta_bancaria`, `swift`, `telefono`"
        )
        st.caption("Columnas opcionales: `email_contacto`, `notas_pago`")

        archivo_cli = st.file_uploader(
            "Sube Excel o CSV de clientes",
            type=["xlsx", "xls", "csv"],
            key="fact_upload_cli",
        )

        if archivo_cli:
            try:
                df_cli = pd.read_csv(archivo_cli) if archivo_cli.name.endswith(".csv") \
                         else pd.read_excel(archivo_cli)
                st.dataframe(df_cli, use_container_width=True, hide_index=True)

                col_req = {"id","nombre","razon_social","limite_credito","condiciones_pago",
                           "banco","banco_empresa","cuenta_bancaria","swift","telefono"}
                faltantes = col_req - set(df_cli.columns)

                if faltantes:
                    alert("error", f"❌ Faltan columnas: {', '.join(sorted(faltantes))}")
                else:
                    nuevos, actualizados = 0, 0
                    preview = []
                    for _, row in df_cli.iterrows():
                        cid    = str(row["id"]).strip()
                        accion = "✏️ Actualizar" if cid in clientes_existentes else "➕ Nuevo"
                        preview.append({"ID": cid, "Nombre": row["nombre"], "Acción": accion})
                        if cid in clientes_existentes: actualizados += 1
                        else: nuevos += 1

                    c1, c2 = st.columns(2)
                    c1.metric("Clientes nuevos", nuevos)
                    c2.metric("A actualizar", actualizados)
                    st.dataframe(pd.DataFrame(preview), use_container_width=True, hide_index=True)

                    if st.button("💾 Guardar clientes", type="primary", key="fact_save_cli"):
                        for _, row in df_cli.iterrows():
                            cid = str(row["id"]).strip()
                            clientes_existentes[cid] = {
                                "id":               cid,
                                "codigo":           cid,
                                "nombre":           str(row.get("nombre", "")),
                                "razon_social":     str(row.get("razon_social", "")),
                                "limite_credito":   float(row.get("limite_credito", 0)),
                                "condiciones_pago": str(row.get("condiciones_pago", "")),
                                "banco":            str(row.get("banco", "")),
                                "banco_empresa":    str(row.get("banco_empresa", "")),
                                "cuenta_bancaria":  str(row.get("cuenta_bancaria", "")),
                                "swift":            str(row.get("swift", "")),
                                "telefono":         str(row.get("telefono", "")),
                                "email_contacto":   str(row.get("email_contacto", "")),
                                "notas_pago":       str(row.get("notas_pago", "")),
                                "activo":           True,
                            }
                        data["clientes"] = list(clientes_existentes.values())
                        guardar_json(data)
                        alert("success", f"✅ {nuevos} nuevos y {actualizados} actualizados.")
                        st.rerun()

            except Exception as e:
                alert("error", f"❌ Error leyendo el archivo: {e}")

    # ── Tab Facturas ──────────────────────────────────────────────────────────
    with tab_fact:
        section_header("🧾", "Importar Facturas",
                       "Las facturas con estatus 'pagada' no se modifican aunque estén en el archivo.")
        st.caption(
            "Columnas requeridas: `folio`, `cliente_id`, `viaje_referencia`, "
            "`fecha_emision`, `fecha_vencimiento`, `importe`, `estatus`"
        )
        st.caption("Valores de estatus: `pendiente`, `vencida`, `pagada` | Opcional: `fecha_pago`")

        archivo_fact = st.file_uploader(
            "Sube Excel o CSV de facturas",
            type=["xlsx", "xls", "csv"],
            key="fact_upload_fact",
        )

        if archivo_fact:
            try:
                df_fact = pd.read_csv(archivo_fact) if archivo_fact.name.endswith(".csv") \
                          else pd.read_excel(archivo_fact)
                st.dataframe(df_fact, use_container_width=True, hide_index=True)

                col_req = {"folio","cliente_id","viaje_referencia","fecha_emision",
                           "fecha_vencimiento","importe","estatus"}
                faltantes = col_req - set(df_fact.columns)

                if faltantes:
                    alert("error", f"❌ Faltan columnas: {', '.join(sorted(faltantes))}")
                else:
                    nuevas, actualizadas, pagadas_skip = 0, 0, 0
                    preview = []
                    for _, row in df_fact.iterrows():
                        folio = str(row["folio"]).strip()
                        if folio in facturas_existentes:
                            if facturas_existentes[folio].get("estatus") == "pagada":
                                accion = "🔒 Pagada (sin cambios)"
                                pagadas_skip += 1
                            else:
                                accion = "✏️ Actualizar"
                                actualizadas += 1
                        else:
                            accion = "➕ Nueva"
                            nuevas += 1
                        preview.append({"Folio": folio, "Cliente": row["cliente_id"],
                                        "Importe": f"${float(row['importe']):,.0f}",
                                        "Estatus": row["estatus"], "Acción": accion})

                    c1, c2, c3 = st.columns(3)
                    c1.metric("Nuevas", nuevas)
                    c2.metric("A actualizar", actualizadas)
                    c3.metric("Pagadas (no se tocan)", pagadas_skip)
                    st.dataframe(pd.DataFrame(preview), use_container_width=True, hide_index=True)

                    if st.button("💾 Guardar facturas", type="primary", key="fact_save_fact"):
                        for _, row in df_fact.iterrows():
                            folio = str(row["folio"]).strip()
                            if folio in facturas_existentes and \
                               facturas_existentes[folio].get("estatus") == "pagada":
                                continue
                            facturas_existentes[folio] = {
                                "id":                folio,
                                "cliente_id":        str(row.get("cliente_id", "")),
                                "folio":             folio,
                                "viaje_referencia":  str(row.get("viaje_referencia", "")),
                                "fecha_emision":     str(row.get("fecha_emision", ""))[:10],
                                "fecha_vencimiento": str(row.get("fecha_vencimiento", ""))[:10],
                                "importe":           float(row.get("importe", 0)),
                                "estatus":           str(row.get("estatus", "pendiente")),
                                "fecha_pago":        str(row.get("fecha_pago", "")) or None,
                                "dias_vencido":      0,
                            }
                        data["facturas"] = list(facturas_existentes.values())
                        guardar_json(data)
                        alert("success",
                              f"✅ {nuevas} nuevas, {actualizadas} actualizadas. "
                              f"{pagadas_skip} pagadas sin cambios.")
                        st.rerun()

            except Exception as e:
                alert("error", f"❌ Error leyendo el archivo: {e}")

        divider()

        # Resumen actual
        section_header("📊", "Resumen actual del sistema")
        m1, m2 = st.columns(2)
        m1.metric("Clientes registrados", len(clientes_existentes))
        m2.metric("Facturas registradas", len(facturas_existentes))
        pagadas    = sum(1 for f in facturas_existentes.values() if f.get("estatus") == "pagada")
        m3, m4 = st.columns(2)
        m3.metric("Pagadas", pagadas)
        m4.metric("Activas/pendientes", len(facturas_existentes) - pagadas)
