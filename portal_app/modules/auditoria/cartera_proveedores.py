# portal_app/modules/auditoria/cartera_proveedores.py
from __future__ import annotations

import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO
from supabase import create_client

from ui.components import page_banner, section_header, alert, divider, kpi_row


# =====================================================
# --- CONFIGURACIÓN ---
# =====================================================

EMPRESAS = {
    'PICUS':       {'nombre': 'Picus Carrier'},
    'IGLOO':       {'nombre': 'Igloo Carrier'},
    'LINCOLN':     {'nombre': 'Lincoln Freight'},
    'SET_LOGIS':   {'nombre': 'Set Logis Plus'},
    'SET_FREIGHT': {'nombre': 'Set Freight'},
}

TIPOS_VALIDOS = [
    'TRANSPORTE', 'TALLER', 'SEGURO', 'COMBUSTIBLE',
    'DIRECCIÓN', 'ADMINISTRATIVO', 'CASETAS', 'REFACCIONES',
    'LLANTAS', 'MANTENIMIENTO', 'SERVICIOS', 'ARRENDAMIENTO', 'OTRO',
]

MAPEO_TIPOS = {
    'ADMINISTRACION':    'ADMINISTRATIVO',
    'ADMINISTRACIÓN':    'ADMINISTRATIVO',
    'DIESEL':            'COMBUSTIBLE',
    'DISPENSARIO':       'COMBUSTIBLE',
    'GASTO COMUN':       'ADMINISTRATIVO',
    'GASTO COMÚN':       'ADMINISTRATIVO',
    'SISTEMA':           'SERVICIOS',
    'GPS':               'SERVICIOS',
    'VIGILANCIA':        'SERVICIOS',
    'PERMISIONARIO':     'SERVICIOS',
    'INSPECCIONES':      'SERVICIOS',
    'FUMIGACION TERMOS': 'SERVICIOS',
    'VERIFICACIONES':    'SERVICIOS',
    'LAVADO TERMOS':     'SERVICIOS',
    'RENTA TERMOS':      'ARRENDAMIENTO',
    'SEGURO LOGISTICA':  'SEGURO',
    'SEGURIDAD':         'SERVICIOS',
    'PATIO CALAMANDA':   'SERVICIOS',
    'DONACIÓN':          'OTRO',
    'PERSONAL TRAFICO':  'ADMINISTRATIVO',
    'VALES PARA OP':     'ADMINISTRATIVO',
    'SEGURO MERCANCIA':  'SEGURO',
    'UNIDADES':          'ARRENDAMIENTO',
    'EXAMEN MEDICO':     'SERVICIOS',
    'PREPASS':           'CASETAS',
    'BANCO':             'SERVICIOS',
    'PLACAS':            'ADMINISTRATIVO',
}


def _normalizar_tipo(tipo):
    tipo_limpio = str(tipo).strip().upper()
    if tipo_limpio in TIPOS_VALIDOS:
        return tipo_limpio
    return MAPEO_TIPOS.get(tipo_limpio, 'OTRO')


# =====================================================
# --- DETECCIÓN DE FORMATO ---
# =====================================================

def _es_archivo_html(archivo_bytes):
    try:
        inicio = archivo_bytes[:500].decode('utf-8', errors='ignore')
        return '<html' in inicio.lower() or '<table' in inicio.lower() or '<!DOCTYPE' in inicio.lower()
    except:
        return False


def _detectar_formato_sac(archivo_bytes):
    try:
        if _es_archivo_html(archivo_bytes):
            return 'anterior'
        df_raw = pd.read_excel(BytesIO(archivo_bytes), sheet_name=0, header=None, nrows=10)
        contenido = ' '.join([
            ' '.join([str(v) for v in row if pd.notna(v)])
            for row in df_raw.values
        ])
        if 'Proveedor' in contenido and 'Dias Credito' in contenido:
            return 'nuevo'
        if 'PROVEEDOR' in contenido and 'ID' in contenido:
            return 'anterior'
        return None
    except:
        return None


# =====================================================
# --- LECTURA DE ARCHIVOS ---
# =====================================================

def _leer_archivo_sac_anterior(archivo_bytes):
    if _es_archivo_html(archivo_bytes):
        try:
            tables = pd.read_html(BytesIO(archivo_bytes))
            if not tables:
                return pd.DataFrame()
            df = max(tables, key=lambda x: len(x))
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.columns = [str(col).strip().upper() for col in df.columns]
            df.rename(columns={'1-15': '1-15 DIAS', '16-30': '16-30 DIAS', '31-60': '31-60 DIAS'}, inplace=True)
            col_prov = 'PROVEEDOR' if 'PROVEEDOR' in df.columns else (df.columns[1] if len(df.columns) > 1 else None)
            if col_prov is None:
                return pd.DataFrame()
            df = df[~df[col_prov].astype(str).str.upper().str.contains('SUBTOTAL', na=False)]
            df = df[~df[col_prov].astype(str).str.upper().str.contains('PROVEEDORES PROPIOS', na=False)]
            df = df.dropna(how='all')
            if 'FACTURA' in df.columns:
                df = df[df['FACTURA'].notna()]
                df = df[df['FACTURA'].astype(str).str.strip() != '']
            df.reset_index(drop=True, inplace=True)
            return df
        except Exception as e:
            st.error(f"❌ Error leyendo HTML: {str(e)}")
            return pd.DataFrame()
    else:
        try:
            df_raw = pd.read_excel(BytesIO(archivo_bytes), sheet_name=0, header=None)
            header_idx = None
            for idx in range(min(10, len(df_raw))):
                row_text = ' '.join([str(v) for v in df_raw.iloc[idx] if pd.notna(v)]).upper()
                if 'PROVEEDOR' in row_text and 'FACTURA' in row_text:
                    if row_text.count('PROVEEDOR') <= 2:
                        header_idx = idx
                        break
            if header_idx is None:
                header_idx = 0
            headers = [str(h).strip().upper() if pd.notna(h) else f"COL_{i}"
                       for i, h in enumerate(df_raw.iloc[header_idx])]
            df = df_raw.iloc[header_idx + 1:].copy()
            df.columns = headers
            df.reset_index(drop=True, inplace=True)
            col_prov = 'PROVEEDOR' if 'PROVEEDOR' in df.columns else (df.columns[1] if len(df.columns) > 1 else None)
            if col_prov:
                df = df[~df[col_prov].astype(str).str.upper().str.contains('PROVEEDORES PROPIOS', na=False)]
                df = df[~df[col_prov].astype(str).str.upper().str.contains('SUBTOTAL', na=False)]
            return df
        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
            return pd.DataFrame()


# =====================================================
# --- FUNCIONES DE PROCESAMIENTO SAC ---
# =====================================================

def _cargar_catalogo(empresa):
    try:
        supabase = st.session_state.supabase
        response = supabase.table('catalogo_proveedores')\
            .select('proveedor, tipo')\
            .eq('empresa', empresa)\
            .execute()
        if response.data:
            df = pd.DataFrame(response.data)
            df.columns = ['PROVEEDOR', 'TIPO']
            df['PROVEEDOR'] = df['PROVEEDOR'].str.strip().str.upper()
            return df
        return pd.DataFrame(columns=['PROVEEDOR', 'TIPO'])
    except:
        return pd.DataFrame(columns=['PROVEEDOR', 'TIPO'])


def _extraer_proveedores_del_archivo(archivo_bytes, formato):
    try:
        if formato == 'anterior':
            return _extraer_proveedores_sac_anterior(archivo_bytes)
        else:
            return _extraer_proveedores_sac_nuevo(archivo_bytes)
    except Exception as e:
        st.error(f"Error extrayendo proveedores: {e}")
        return []


def _extraer_proveedores_sac_anterior(archivo_bytes):
    try:
        df_raw = _leer_archivo_sac_anterior(archivo_bytes)
        if df_raw.empty:
            return []
        col_proveedor = None
        for col in df_raw.columns:
            col_name = str(col[0]).upper() if isinstance(col, tuple) else str(col).upper()
            if 'PROVEEDOR' in col_name and 'ID' not in col_name:
                col_proveedor = col
                break
        if col_proveedor is None and len(df_raw.columns) > 1:
            col_proveedor = df_raw.columns[1]
        if col_proveedor is None:
            return []
        df = df_raw.copy()

        def valores_unicos_por_fila(row):
            valores = [str(v).strip().upper() for v in row if pd.notna(v) and str(v).strip() != '']
            return len(set(valores)) if valores else 0

        df['_nuv'] = df.apply(valores_unicos_por_fila, axis=1)
        df = df[df['_nuv'] > 1].drop('_nuv', axis=1)
        df = df[~df[col_proveedor].astype(str).str.contains('SUBTOTAL', case=False, na=False)]
        col_factura = next((c for c in df.columns if 'FACTURA' in (str(c[0]).upper() if isinstance(c, tuple) else str(c).upper())), None)
        if col_factura is not None:
            df = df[df[col_factura].notna()]
            df = df[df[col_factura].astype(str).str.strip() != '']
        df = df[df[col_proveedor].notna()]
        df = df[df[col_proveedor].astype(str).str.strip() != '']
        if df.empty:
            return []
        proveedores = df[col_proveedor].str.strip().str.upper().unique().tolist()
        return [p for p in proveedores if p and str(p).upper() != 'NAN' and len(str(p)) > 2]
    except Exception as e:
        st.error(f"❌ Error extrayendo proveedores SAC Anterior: {str(e)}")
        return []


def _extraer_proveedores_sac_nuevo(archivo_bytes):
    df_raw = pd.read_excel(BytesIO(archivo_bytes), sheet_name=0, header=None)
    header_row = None
    for idx in range(min(20, len(df_raw))):
        row_str = ' '.join(str(v) for v in df_raw.iloc[idx].values if pd.notna(v))
        if 'Proveedor' in row_str and ('Dias Credito' in row_str or 'Días Crédito' in row_str):
            header_row = idx
            break
    if header_row is None:
        return []
    df = pd.read_excel(BytesIO(archivo_bytes), sheet_name=0, header=header_row)
    if 'Proveedor' not in df.columns:
        return []
    for pat in ['SUBTOTAL', 'TOTAL DE PROVEEDORES', 'ID:', ':']:
        df = df[~df['Proveedor'].astype(str).str.contains(pat, case=False, na=False)]
    df = df[df['Proveedor'].notna()]
    proveedores = df['Proveedor'].str.strip().str.upper().unique().tolist()
    return [p for p in proveedores if p and p != 'NAN']


def _procesar_sac_anterior(archivo_bytes, catalogo_df):
    df_raw = _leer_archivo_sac_anterior(archivo_bytes)
    if df_raw.empty:
        raise ValueError("No se pudieron leer datos del archivo")
    df = df_raw.copy()
    if isinstance(df.columns[0], tuple):
        df.rename(columns={col: col[0] for col in df.columns}, inplace=True)
    columnas_esperadas = {
        0: 'ID', 1: 'PROVEEDOR', 2: 'DIAS CRED', 3: 'FACTURA', 4: 'TRAFICO',
        5: 'NUM CR', 6: 'FECHA REP FACT/CR', 7: 'FECHA VENC', 8: 'SALDO',
        9: 'POR VENCER', 10: '1-15 DIAS', 11: '16-30 DIAS', 12: '31-60 DIAS',
        13: '+60', 14: 'MONEDA', 15: 'UUID',
    }
    columnas_actuales_upper = [str(c).upper() for c in df.columns]
    if 'PROVEEDOR' not in columnas_actuales_upper or 'FACTURA' not in columnas_actuales_upper:
        if len(df.columns) >= 14:
            df.rename(columns={col: columnas_esperadas[idx] for idx, col in enumerate(df.columns) if idx in columnas_esperadas}, inplace=True)
    col_proveedor = next((c for c in df.columns if 'PROVEEDOR' in (str(c[0]).upper() if isinstance(c, tuple) else str(c).upper()) and 'ID' not in (str(c[0]).upper() if isinstance(c, tuple) else str(c).upper())), None)
    col_factura   = next((c for c in df.columns if 'FACTURA'   in (str(c[0]).upper() if isinstance(c, tuple) else str(c).upper())), None)
    if col_proveedor is not None:
        df = df[~df[col_proveedor].astype(str).str.upper().str.contains('PROVEEDORES PROPIOS', na=False)]
    if col_proveedor is not None and col_factura is not None:
        def valores_unicos_por_fila(row):
            valores = [str(v).strip().upper() for v in row if pd.notna(v) and str(v).strip() != '']
            return len(set(valores)) if valores else 0
        df['_nuv'] = df.apply(valores_unicos_por_fila, axis=1)
        df = df[df['_nuv'] > 1].drop('_nuv', axis=1)
        df = df[~df[col_proveedor].astype(str).str.contains('SUBTOTAL', case=False, na=False)]
        df = df[df[col_factura].notna()]
        df = df[df[col_factura].astype(str).str.strip() != '']
        df = df[df[col_proveedor].notna()]
        df = df[df[col_proveedor].astype(str).str.strip() != '']
    if '+60' not in df.columns and 'MAS DE 60' in df.columns:
        df.rename(columns={'MAS DE 60': '+60'}, inplace=True)
    elif '+60' not in df.columns and len(df.columns) > 13:
        df.rename(columns={df.columns[13]: '+60'}, inplace=True)
    col_prov_final = next((c for c in df.columns if 'PROVEEDOR' in str(c).upper()), None)
    if col_prov_final is not None and not catalogo_df.empty:
        catalogo_dict = dict(zip(catalogo_df['PROVEEDOR'].str.strip().str.upper(), catalogo_df['TIPO']))
        df['TIPO'] = df[col_prov_final].astype(str).str.strip().str.upper().map(catalogo_dict)
    else:
        df['TIPO'] = None
    columnas_finales = [
        'ID', 'PROVEEDOR', 'DIAS CRED', 'FACTURA', 'TRAFICO',
        'NUM CR', 'FECHA REP FACT/CR', 'FECHA VENC', 'SALDO',
        'POR VENCER', '1-15 DIAS', '16-30 DIAS', '31-60 DIAS', '+60',
        'MONEDA', 'UUID', 'TIPO',
    ]
    for col in columnas_finales:
        if col not in df.columns:
            df[col] = None
    return df[columnas_finales]


def _procesar_sac_nuevo(archivo_bytes, catalogo_df):
    df_raw = pd.read_excel(BytesIO(archivo_bytes), sheet_name=0, header=None)
    header_row = None
    for idx in range(min(20, len(df_raw))):
        row_str = ' '.join(str(v) for v in df_raw.iloc[idx].values if pd.notna(v))
        if 'Proveedor' in row_str and ('Dias Credito' in row_str or 'Días Crédito' in row_str):
            header_row = idx
            break
    if header_row is None:
        raise ValueError("No se encontraron encabezados con 'Proveedor' y 'Dias Credito'")
    df = pd.read_excel(BytesIO(archivo_bytes), sheet_name=0, header=header_row)
    if 'Proveedor' not in df.columns:
        raise ValueError(f"Columna 'Proveedor' no encontrada. Columnas: {df.columns.tolist()}")
    for pat in ['SUBTOTAL', 'TOTAL DE PROVEEDORES', 'ID:', ':']:
        df = df[~df['Proveedor'].astype(str).str.contains(pat, case=False, na=False)]
    df = df[df['Proveedor'].notna()]
    if 'Num CR' in df.columns:
        df = df[df['Num CR'].notna()]
    df_full = pd.read_excel(BytesIO(archivo_bytes), sheet_name=0, header=header_row)
    current_id = None
    ids_list = []
    for _, row in df_full.iterrows():
        proveedor_str = str(row['Proveedor']) if 'Proveedor' in row else ''
        if 'ID:' in proveedor_str:
            try:
                id_match = proveedor_str.split('ID:')[1].split('(')[0].strip()
                current_id = int(id_match) if id_match.isdigit() else None
            except:
                current_id = None
        ids_list.append(current_id)
    df_full['ID_EXTRAIDO'] = ids_list
    if 'Factura' in df.columns and 'Num CR' in df.columns:
        df = df.merge(df_full[['Proveedor', 'Factura', 'Num CR', 'ID_EXTRAIDO']], on=['Proveedor', 'Factura', 'Num CR'], how='left')
    else:
        df['ID_EXTRAIDO'] = None
    df.rename(columns={
        'Proveedor': 'PROVEEDOR', 'Dias Credito': 'DIAS CRED', 'Factura': 'FACTURA',
        'Referencia': 'TRAFICO', 'Ejecutivo': 'EJECUTIVO', 'Num CR': 'NUM CR',
        'Fecha Rep Fac/Cr': 'FECHA REP FACT/CR', 'Fecha Venc': 'FECHA VENC',
        'Saldo': 'SALDO', 'Por Vencer': 'POR VENCER', '1-15 dias': '1-15 DIAS',
        '16-30 dias': '16-30 DIAS', '31-60 dias': '31-60 DIAS', '+60': '+60',
        'Moneda': 'MONEDA', 'ID_EXTRAIDO': 'ID',
    }, inplace=True)
    if not catalogo_df.empty:
        catalogo_dict = dict(zip(catalogo_df['PROVEEDOR'].str.strip().str.upper(), catalogo_df['TIPO']))
        df['TIPO'] = df['PROVEEDOR'].str.strip().str.upper().map(catalogo_dict)
    else:
        df['TIPO'] = None
    columnas_finales = [
        'ID', 'PROVEEDOR', 'DIAS CRED', 'FACTURA', 'TRAFICO',
        'NUM CR', 'FECHA REP FACT/CR', 'FECHA VENC', 'SALDO',
        'POR VENCER', '1-15 DIAS', '16-30 DIAS', '31-60 DIAS', '+60',
        'MONEDA', 'TIPO',
    ]
    for col in columnas_finales:
        if col not in df.columns:
            df[col] = None
    return df[columnas_finales]


def _procesar_sac(archivo_bytes, formato, catalogo_df):
    if formato == 'anterior':
        return _procesar_sac_anterior(archivo_bytes, catalogo_df)
    else:
        return _procesar_sac_nuevo(archivo_bytes, catalogo_df)


def _exportar_excel(cartera_df, catalogo_df):
    output = BytesIO()
    df_export = cartera_df.copy()
    if isinstance(df_export.columns, pd.MultiIndex):
        df_export.columns = [
            '_'.join(map(str, col)).strip('_') if isinstance(col, tuple) else str(col)
            for col in df_export.columns
        ]
    if isinstance(df_export.index, pd.MultiIndex):
        df_export = df_export.reset_index()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_export.to_excel(writer, sheet_name='CARTERA', index=False)
        if not catalogo_df.empty:
            catalogo_df.to_excel(writer, sheet_name='CATALOGO', index=False)
    output.seek(0)
    return output.getvalue()


# =====================================================
# --- PUNTO DE ENTRADA DEL MÓDULO ---
# =====================================================

def render():
    from ui.components import page_banner, section_header, alert, divider, kpi_row

    page_banner("📊", "Cartera de Proveedores", "Convierte archivos SAC a formato Cartera con clasificación automática")

    # Inicializar Supabase
    if 'supabase' not in st.session_state:
        try:
            st.session_state.supabase = create_client(
                st.secrets["SUPABASE_URL"],
                st.secrets.get("SUPABASE_SERVICE_KEY", st.secrets["SUPABASE_KEY"])
            )
        except Exception as e:
            alert("error", f"❌ Error conectando a Supabase: {str(e)}")
            st.stop()

    tab1, tab2 = st.tabs(["📤 Procesar SAC", "📋 Catálogos"])

    # ─────────────────────────────────────────────
    # TAB 1: PROCESAR SAC
    # ─────────────────────────────────────────────
    with tab1:
        section_header("📂", "Paso 1: Cargar Archivo SAC")

        empresa = st.selectbox(
            "🏢 Empresa",
            options=list(EMPRESAS.keys()),
            format_func=lambda x: EMPRESAS[x]['nombre'],
        )

        archivo = st.file_uploader(
            "📎 Sube tu archivo SAC (.xls o .xlsx)",
            type=['xls', 'xlsx'],
        )

        if archivo:
            archivo_bytes = archivo.read()
            formato_detectado = _detectar_formato_sac(archivo_bytes)

            if formato_detectado is None:
                alert("error", "❌ No se pudo detectar el formato del archivo. Verifica que sea un archivo SAC válido.")
                st.stop()

            es_html = _es_archivo_html(archivo_bytes)
            formato_nombre = "SAC Anterior (Picus/Igloo)" if formato_detectado == 'anterior' else "SAC Nuevo (Lincoln/Set Logis/Set Freight)"
            tipo_archivo   = "HTML" if es_html else "Excel"

            col1, col2, col3 = st.columns(3)
            with col1:
                st.success(f"✅ Formato: **{formato_nombre}**")
            with col2:
                st.info(f"📄 Tipo: **{tipo_archivo}**")
            with col3:
                st.info(f"📎 Archivo: **{archivo.name}**")

            divider()

            # PASO 2: VERIFICAR CATÁLOGO
            section_header("📋", "Paso 2: Verificar Catálogo de Proveedores")

            catalogo_existente  = _cargar_catalogo(empresa)
            proveedores_archivo = _extraer_proveedores_del_archivo(archivo_bytes, formato_detectado)

            if not proveedores_archivo:
                alert("error", "❌ No se pudieron extraer proveedores del archivo")
                st.stop()

            proveedores_en_catalogo = set(catalogo_existente['PROVEEDOR'].tolist()) if not catalogo_existente.empty else set()
            proveedores_faltantes   = [p for p in proveedores_archivo if p not in proveedores_en_catalogo]
            n_en_catalogo           = len(proveedores_archivo) - len(proveedores_faltantes)
            pct_en_catalogo         = f"{(n_en_catalogo / len(proveedores_archivo) * 100):.0f}%" if proveedores_archivo else "0%"

            kpi_row([
                {"icono": "📄", "label": "En Archivo",   "valor": len(proveedores_archivo), "sub": "proveedores únicos",  "color": "#1B2266"},
                {"icono": "✅", "label": "En Catálogo",  "valor": n_en_catalogo,            "sub": pct_en_catalogo,       "color": "#16a34a"},
                {"icono": "⚠️", "label": "Sin clasificar","valor": len(proveedores_faltantes),"sub": "requieren tipo",    "color": "#dc2626"},
            ])

            divider()

            # Capturar faltantes
            if proveedores_faltantes:
                alert("warn", f"⚠️ Hay **{len(proveedores_faltantes)}** proveedores sin catalogar — completa el catálogo antes de continuar.")

                df_faltantes = pd.DataFrame({
                    'PROVEEDOR': sorted(proveedores_faltantes),
                    'TIPO':      [None] * len(proveedores_faltantes),
                })

                section_header("✏️", "Clasificar Proveedores Faltantes")

                proveedores_editados = st.data_editor(
                    df_faltantes,
                    num_rows="fixed",
                    use_container_width=True,
                    column_config={
                        "PROVEEDOR": st.column_config.TextColumn("Proveedor", disabled=True),
                        "TIPO":      st.column_config.SelectboxColumn("Tipo", options=TIPOS_VALIDOS, required=True),
                    },
                    key="proveedores_faltantes_editor",
                )

                # Streamlit 1.52.0: SelectboxColumn a veces devuelve el valor
                # envuelto en una lista (ej. ['TRANSPORTE'] en vez de 'TRANSPORTE').
                # Lo desempacamos aquí para que el resto del flujo trabaje con strings.
                proveedores_editados = proveedores_editados.copy()
                proveedores_editados['TIPO'] = proveedores_editados['TIPO'].apply(
                    lambda v: (v[0] if v else None) if isinstance(v, list) else v
                )

                proveedores_sin_tipo = proveedores_editados[proveedores_editados['TIPO'].isna()]

                if not proveedores_sin_tipo.empty:
                    alert("warn", f"⚠️ Faltan {len(proveedores_sin_tipo)} proveedores por clasificar")
                else:
                    alert("success", "✅ Todos los proveedores tienen tipo asignado — puedes guardar.")

                col1, col2 = st.columns([1, 3])
                with col1:
                    if st.button(
                        "💾 Guardar en Catálogo",
                        type="primary",
                        use_container_width=True,
                        disabled=not proveedores_sin_tipo.empty,
                    ):
                        try:
                            supabase = st.session_state.supabase
                            exito = 0
                            duplicados = 0
                            fallidos = []

                            for _, row in proveedores_editados.iterrows():
                                tipo_val = str(row['TIPO']).strip().upper() if pd.notna(row['TIPO']) else None

                                if tipo_val is None:
                                    continue

                                if tipo_val not in TIPOS_VALIDOS:
                                    fallidos.append((row['PROVEEDOR'], f"tipo inválido: '{tipo_val}'"))
                                    continue

                                try:
                                    supabase.table('catalogo_proveedores').insert({
                                        'empresa':   empresa,
                                        'proveedor': row['PROVEEDOR'],
                                        'tipo':      tipo_val,
                                    }).execute()
                                    exito += 1
                                except Exception as e:
                                    if 'duplicate' in str(e).lower():
                                        duplicados += 1
                                    else:
                                        fallidos.append((row['PROVEEDOR'], str(e)))

                            if exito:
                                alert("success", f"✅ {exito} proveedores guardados en el catálogo.")
                            if duplicados:
                                alert("warn", f"⚠️ {duplicados} ya existían en el catálogo.")
                            if fallidos:
                                alert("error", f"❌ {len(fallidos)} no se pudieron guardar.")
                                with st.expander("Ver detalle de errores"):
                                    for prov, err in fallidos:
                                        st.write(f"**{prov}**: {err}")

                            if not fallidos:
                                st.rerun()
                        except Exception as e:
                            alert("error", f"❌ Error: {str(e)}")

                st.stop()
            else:
                alert("success", "✅ Todos los proveedores están en el catálogo.")

            divider()

            # PASO 3: PROCESAR
            section_header("🔄", "Paso 3: Procesar Archivo")

            catalogo_actualizado = _cargar_catalogo(empresa)

            col1, col2 = st.columns([1, 3])
            with col1:
                if st.button("🚀 Procesar Archivo", type="primary", use_container_width=True):
                    with st.spinner("⏳ Procesando..."):
                        try:
                            cartera_df = _procesar_sac(archivo_bytes, formato_detectado, catalogo_actualizado)
                            st.session_state['cartera_procesada'] = cartera_df
                            st.session_state['catalogo_usado']    = catalogo_actualizado
                            st.session_state['empresa_procesada'] = empresa
                            alert("success", f"✅ ¡Procesado! **{len(cartera_df):,}** registros generados.")
                        except Exception as e:
                            alert("error", f"❌ Error: {str(e)}")
                            with st.expander("🔍 Ver detalles del error"):
                                st.exception(e)

            # Mostrar resultados
            if 'cartera_procesada' in st.session_state:
                cartera_df = st.session_state['cartera_procesada']
                divider()
                section_header("📈", "Resumen del Resultado")

                # Detectar columnas de forma flexible
                col_proveedor_name = next(
                    (c for c in cartera_df.columns if 'PROVEEDOR' in str(c).upper() and 'ID' not in str(c).upper()),
                    None,
                )
                col_saldo_name = next(
                    (c for c in cartera_df.columns if 'SALDO' in str(c).upper() and 'VENCER' not in str(c).upper()),
                    None,
                )
                col_tipo_name = next(
                    (c for c in cartera_df.columns if 'TIPO' in str(c).upper()),
                    None,
                )

                n_proveedores = cartera_df[col_proveedor_name].nunique() if col_proveedor_name else "N/A"
                saldo_total   = f"${pd.to_numeric(cartera_df[col_saldo_name], errors='coerce').sum():,.2f}" if col_saldo_name else "N/A"
                clasificados  = int(cartera_df[col_tipo_name].notna().sum()) if col_tipo_name else "N/A"
                pct_clas      = f"{(clasificados / len(cartera_df) * 100):.1f}%" if col_tipo_name and isinstance(clasificados, int) else ""

                kpi_row([
                    {"icono": "📝", "label": "Registros",    "valor": f"{len(cartera_df):,}", "sub": "procesados",          "color": "#1B2266"},
                    {"icono": "👥", "label": "Proveedores",  "valor": n_proveedores,          "sub": "únicos",              "color": "#1B2266"},
                    {"icono": "💰", "label": "Saldo Total",  "valor": saldo_total,            "sub": "MXN",                 "color": "#16a34a"},
                    {"icono": "✓",  "label": "Clasificados", "valor": clasificados,           "sub": pct_clas,              "color": "#0077B6"},
                ])

                divider()
                section_header("👁️", "Vista Previa")

                df_vista = cartera_df.copy()
                if len(df_vista.columns) > 0:
                    primera_col = df_vista.columns[0]
                    df_vista = df_vista[~df_vista[primera_col].astype(str).str.upper().str.contains('PROVEEDORES PROPIOS', na=False)]

                st.dataframe(df_vista, use_container_width=True, height=400)

                divider()
                section_header("📥", "Descargar")

                catalogo_usado = st.session_state.get('catalogo_usado', catalogo_actualizado)
                excel_bytes    = _exportar_excel(cartera_df, catalogo_usado)

                st.download_button(
                    label="⬇️ Descargar Excel (CARTERA + CATÁLOGO)",
                    data=excel_bytes,
                    file_name=f"CARTERA_{empresa}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    type="primary",
                )

    # ─────────────────────────────────────────────
    # TAB 2: CATÁLOGOS
    # ─────────────────────────────────────────────
    with tab2:
        section_header("📋", "Gestión de Catálogos")

        empresa_cat = st.selectbox(
            "🏢 Empresa",
            options=list(EMPRESAS.keys()),
            format_func=lambda x: EMPRESAS[x]['nombre'],
            key='empresa_cat',
        )

        catalogo_df = _cargar_catalogo(empresa_cat)

        kpi_row([
            {"icono": "📊", "label": "Proveedores catalogados", "valor": len(catalogo_df), "sub": "registros", "color": "#1B2266"},
        ])

        accion = st.selectbox("⚙️ Acción", ["Ver Catálogo", "Agregar Proveedor", "Importar desde Excel"])

        divider()

        if accion == "Ver Catálogo":
            if not catalogo_df.empty:
                busqueda = st.text_input("🔍 Buscar proveedor", placeholder="Escribe el nombre...")
                catalogo_filtrado = (
                    catalogo_df[catalogo_df['PROVEEDOR'].str.contains(busqueda, case=False, na=False)]
                    if busqueda else catalogo_df
                )
                if busqueda:
                    alert("info", f"📍 Encontrados: **{len(catalogo_filtrado)}** registros")
                st.dataframe(catalogo_filtrado, use_container_width=True, height=500)
            else:
                alert("info", "📭 No hay proveedores catalogados para esta empresa.")

        elif accion == "Agregar Proveedor":
            section_header("➕", "Nuevo Proveedor")
            with st.form("agregar_proveedor"):
                col1, col2 = st.columns(2)
                with col1:
                    proveedor = st.text_input("Nombre del Proveedor *", placeholder="Ej: ACME CORP")
                with col2:
                    tipo = st.selectbox("Tipo de Proveedor *", TIPOS_VALIDOS)

                divider()

                col1, col2 = st.columns(2)
                with col1:
                    if st.form_submit_button("✅ Agregar", use_container_width=True, type="primary"):
                        if proveedor.strip():
                            try:
                                st.session_state.supabase.table('catalogo_proveedores').insert({
                                    'empresa':   empresa_cat,
                                    'proveedor': proveedor.strip(),
                                    'tipo':      tipo,
                                }).execute()
                                alert("success", f"✅ **'{proveedor}'** agregado al catálogo.")
                                st.rerun()
                            except Exception as e:
                                if 'duplicate' in str(e).lower():
                                    alert("warn", "⚠️ El proveedor ya existe en el catálogo.")
                                else:
                                    alert("error", f"❌ Error: {str(e)}")
                        else:
                            alert("warn", "⚠️ El nombre del proveedor es obligatorio.")
                with col2:
                    if st.form_submit_button("❌ Cancelar", use_container_width=True):
                        st.rerun()

        elif accion == "Importar desde Excel":
            alert("info", "📄 Sube un Excel con hoja **CATALOGO** (o **T** para Lincoln) y columnas: **PROVEEDOR** y **TIPO**.")

            archivo_cat = st.file_uploader("📎 Selecciona archivo", type=['xlsx', 'xls'], key='import_cat')

            if archivo_cat:
                if st.button("🚀 Importar", use_container_width=True, type="primary"):
                    try:
                        hoja      = 'T' if empresa_cat == 'LINCOLN' else 'CATALOGO'
                        df_import = pd.read_excel(archivo_cat, sheet_name=hoja)

                        col_proveedor = next((c for c in df_import.columns if 'PROVEEDOR' in str(c).upper()), None)
                        col_tipo      = next((c for c in df_import.columns if 'TIPO'      in str(c).upper()), None)

                        if col_proveedor is None or col_tipo is None:
                            alert("error", f"❌ No se encontraron las columnas PROVEEDOR y TIPO. Columnas detectadas: {df_import.columns.tolist()}")
                            st.stop()

                        supabase  = st.session_state.supabase
                        exito     = 0
                        duplicados = 0
                        progress  = st.progress(0)
                        status    = st.empty()

                        for i, row in df_import.iterrows():
                            if pd.notna(row[col_proveedor]) and pd.notna(row[col_tipo]):
                                prov      = str(row[col_proveedor]).strip()
                                tipo_norm = _normalizar_tipo(row[col_tipo])
                                try:
                                    supabase.table('catalogo_proveedores').insert({
                                        'empresa':   empresa_cat,
                                        'proveedor': prov,
                                        'tipo':      tipo_norm,
                                    }).execute()
                                    exito += 1
                                    status.text(f"✅ {prov[:60]}")
                                except Exception as e:
                                    if 'duplicate' in str(e).lower():
                                        duplicados += 1
                            progress.progress((i + 1) / len(df_import))

                        progress.empty()
                        status.empty()

                        kpi_row([
                            {"icono": "✅", "label": "Importados",  "valor": exito,      "sub": "registros nuevos",  "color": "#16a34a"},
                            {"icono": "⚠️", "label": "Duplicados",  "valor": duplicados, "sub": "ya existían",       "color": "#F59E0B"},
                        ])

                        alert("success", "✅ Importación completada.")
                        st.rerun()

                    except Exception as e:
                        alert("error", f"❌ Error durante la importación: {str(e)}")
                        with st.expander("Ver detalles"):
                            st.exception(e)
