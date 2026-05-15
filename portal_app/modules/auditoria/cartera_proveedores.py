# portal_app/modules/auditoria/cartera_proveedores.py
import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO
from supabase import create_client


# =====================================================
# --- CONFIGURACIÓN ---
# =====================================================

EMPRESAS = {
    'PICUS': {'nombre': 'Picus Carrier'},
    'IGLOO': {'nombre': 'Igloo Carrier'},
    'LINCOLN': {'nombre': 'Lincoln Freight'},
    'SET_LOGIS': {'nombre': 'Set Logis Plus'},
    'SET_FREIGHT': {'nombre': 'Set Freight'}
}

# Tipos válidos
TIPOS_VALIDOS = [
    'TRANSPORTE', 'TALLER', 'SEGURO', 'COMBUSTIBLE',
    'DIRECCIÓN', 'ADMINISTRATIVO', 'CASETAS', 'REFACCIONES',
    'LLANTAS', 'MANTENIMIENTO', 'SERVICIOS', 'ARRENDAMIENTO', 'OTRO'
]

# Mapeo de tipos no estándar
MAPEO_TIPOS = {
    'ADMINISTRACION': 'ADMINISTRATIVO',
    'ADMINISTRACIÓN': 'ADMINISTRATIVO',
    'DIESEL': 'COMBUSTIBLE',
    'DISPENSARIO': 'COMBUSTIBLE',
    'GASTO COMUN': 'ADMINISTRATIVO',
    'GASTO COMÚN': 'ADMINISTRATIVO',
    'SISTEMA': 'SERVICIOS',
    'GPS': 'SERVICIOS',
    'VIGILANCIA': 'SERVICIOS',
    'PERMISIONARIO': 'SERVICIOS',
    'INSPECCIONES': 'SERVICIOS',
    'FUMIGACION TERMOS': 'SERVICIOS',
    'VERIFICACIONES': 'SERVICIOS',
    'LAVADO TERMOS': 'SERVICIOS',
    'RENTA TERMOS': 'ARRENDAMIENTO',
    'SEGURO LOGISTICA': 'SEGURO',
    'SEGURIDAD': 'SERVICIOS',
    'PATIO CALAMANDA': 'SERVICIOS',
    'DONACIÓN': 'OTRO',
    'PERSONAL TRAFICO': 'ADMINISTRATIVO',
    'VALES PARA OP': 'ADMINISTRATIVO',
    'SEGURO MERCANCIA': 'SEGURO',
    'UNIDADES': 'ARRENDAMIENTO',
    'EXAMEN MEDICO': 'SERVICIOS',
    'PREPASS': 'CASETAS',
    'BANCO': 'SERVICIOS',
    'PLACAS': 'ADMINISTRATIVO'
}

def _normalizar_tipo(tipo):
    """Normaliza el tipo al catálogo válido"""
    tipo_limpio = str(tipo).strip().upper()
    if tipo_limpio in TIPOS_VALIDOS:
        return tipo_limpio
    return MAPEO_TIPOS.get(tipo_limpio, 'OTRO')


# =====================================================
# --- FUNCIONES DE DETECCIÓN DE FORMATO ---
# =====================================================

def _es_archivo_html(archivo_bytes):
    """
    Detecta si el archivo es HTML disfrazado de .xls
    Los sistemas antiguos de PICUS/IGLOO exportan HTML con extensión .xls
    """
    try:
        # Leer primeros bytes y buscar etiquetas HTML
        inicio = archivo_bytes[:500].decode('utf-8', errors='ignore')
        return '<html' in inicio.lower() or '<table' in inicio.lower() or '<!DOCTYPE' in inicio.lower()
    except:
        return False


def _detectar_formato_sac(archivo_bytes):
    """
    Detecta automáticamente si el archivo es SAC Anterior o SAC Nuevo.
    
    Retorna:
    - 'anterior' si detecta formato antiguo (o es HTML)
    - 'nuevo' si detecta formato nuevo
    - None si no puede determinar
    """
    try:
        # Si es HTML, es SAC Anterior (PICUS/IGLOO)
        if _es_archivo_html(archivo_bytes):
            return 'anterior'
        
        # Intentar leer primeras filas como Excel
        df_raw = pd.read_excel(BytesIO(archivo_bytes), sheet_name=0, header=None, nrows=10)
        
        # Convertir todo a string y buscar patrones
        contenido = ' '.join([
            ' '.join([str(v) for v in row if pd.notna(v)]) 
            for row in df_raw.values
        ])
        
        # SAC Nuevo tiene "Proveedor" y "Dias Credito" (con minúsculas)
        if 'Proveedor' in contenido and 'Dias Credito' in contenido:
            return 'nuevo'
        
        # SAC Anterior tiene "PROVEEDOR" y "ID" (todo mayúsculas)
        if 'PROVEEDOR' in contenido and 'ID' in contenido:
            return 'anterior'
        
        return None
    except:
        return None


# =====================================================
# --- FUNCIONES DE LECTURA DE ARCHIVOS ---
# =====================================================

def _leer_archivo_sac_anterior(archivo_bytes):
    """
    Lee archivo SAC Anterior manejando MultiIndex del HTML
    
    SOLUCION: El HTML de PICUS tiene 2 filas de header que crean MultiIndex.
    Pandas lee correctamente los datos, solo necesitamos aplanar las columnas.
    """
    if _es_archivo_html(archivo_bytes):
        alert("info", "🔍 Detectado: Archivo HTML (PICUS/IGLOO)")
        
        try:
            # Leer HTML normalmente - pandas detectara el MultiIndex
            tables = pd.read_html(BytesIO(archivo_bytes))
            
            if not tables:
                alert("error", "❌ No se encontraron tablas")
                return pd.DataFrame()
            
            # Tabla mas grande
            df = max(tables, key=lambda x: len(x))
            st.write(f"✓ Tabla HTML: {len(df)} filas x {len(df.columns)} cols")
            
            # SOLUCION: Si tiene MultiIndex, tomar solo el primer nivel (los nombres reales)
            if isinstance(df.columns, pd.MultiIndex):
                alert("info", "ℹ️ MultiIndex detectado - usando primer nivel de columnas")
                # Tomar solo el nivel 0 (ID, PROVEEDOR, FACTURA, etc.)
                df.columns = df.columns.get_level_values(0)
            
            # Normalizar nombres de columnas
            df.columns = [str(col).strip().upper() for col in df.columns]
            
            st.write(f"✓ Columnas: {df.columns.tolist()[:6]}")
            
            # FILTRAR "SUBTOTAL" - estas son las filas azules combinadas
            if 'PROVEEDOR' in df.columns:
                col_prov = 'PROVEEDOR'
            elif len(df.columns) > 1:
                col_prov = df.columns[1]
            else:
                alert("error", "❌ No se puede identificar columna de proveedor")
                return pd.DataFrame()
            
            antes = len(df)
            df = df[~df[col_prov].astype(str).str.upper().str.contains('SUBTOTAL', na=False)]
            df = df[~df[col_prov].astype(str).str.upper().str.contains('PROVEEDORES PROPIOS', na=False)]
            despues = len(df)
            
            if antes != despues:
                st.success(f"✓ Filtradas {antes - despues} filas de subtotales/agrupacion")
            
            # Eliminar filas vacias
            df = df.dropna(how='all')
            
            # Eliminar filas donde FACTURA esta vacia
            if 'FACTURA' in df.columns:
                df = df[df['FACTURA'].notna()]
                df = df[df['FACTURA'].astype(str).str.strip() != '']
            
            # Reset index
            df.reset_index(drop=True, inplace=True)
            
            st.write(f"✓ DataFrame final: {len(df)} filas")
            return df
            
        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
            st.exception(e)
            return pd.DataFrame()
    
    else:
        # Excel real
        alert("info", "🔍 Detectado: Excel real")
        try:
            df_raw = pd.read_excel(BytesIO(archivo_bytes), sheet_name=0, header=None)
            
            # Buscar header
            header_idx = None
            for idx in range(min(10, len(df_raw))):
                row_text = ' '.join([str(v) for v in df_raw.iloc[idx] if pd.notna(v)]).upper()
                if 'PROVEEDOR' in row_text and 'FACTURA' in row_text:
                    if row_text.count('PROVEEDOR') <= 2:
                        header_idx = idx
                        st.success(f"✓ Header en fila {idx + 1}")
                        break
            
            if header_idx is None:
                header_idx = 0
            
            headers = [str(h).strip().upper() if pd.notna(h) else f"COL_{i}" 
                      for i, h in enumerate(df_raw.iloc[header_idx])]
            
            df = df_raw.iloc[header_idx + 1:].copy()
            df.columns = headers
            df.reset_index(drop=True, inplace=True)
            
            # Filtrar
            if 'PROVEEDOR' in df.columns:
                col_prov = 'PROVEEDOR'
            elif len(df.columns) > 1:
                col_prov = df.columns[1]
            else:
                return df
            
            antes = len(df)
            df = df[~df[col_prov].astype(str).str.upper().str.contains('PROVEEDORES PROPIOS', na=False)]
            df = df[~df[col_prov].astype(str).str.upper().str.contains('SUBTOTAL', na=False)]
            if antes != len(df):
                st.success(f"✓ Filtradas {antes - len(df)} filas")
            
            return df
            
        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
            return pd.DataFrame()

# =====================================================
# --- FUNCIONES DE PROCESAMIENTO SAC ---
# =====================================================

def _cargar_catalogo(empresa):
    """Carga catálogo de Supabase"""
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
    """Extrae lista de proveedores únicos del archivo SAC"""
    try:
        if formato == 'anterior':
            return _extraer_proveedores_sac_anterior(archivo_bytes)
        else:
            return _extraer_proveedores_sac_nuevo(archivo_bytes)
    except Exception as e:
        st.error(f"Error extrayendo proveedores: {e}")
        return []


def _extraer_proveedores_sac_anterior(archivo_bytes):
    """Extrae proveedores de SAC Anterior (HTML o Excel)"""
    try:
        df_raw = _leer_archivo_sac_anterior(archivo_bytes)
        
        if df_raw.empty:
            alert("warn", "⚠️ El DataFrame está vacío después de leer el archivo")
            return []
        
        # Debug: mostrar info del DataFrame
        st.write(f"**Debug:** DataFrame tiene {len(df_raw)} filas y {len(df_raw.columns)} columnas")
        st.write(f"**Debug:** Columnas: {df_raw.columns.tolist()[:5]}...")  # Primeras 5 columnas
        
        # Buscar columna de proveedor (puede ser index 0 o 1)
        col_proveedor = None
        for col in df_raw.columns:
            # Manejar columnas multi-index (tuplas) y columnas simples
            if isinstance(col, tuple):
                col_name = str(col[0]).upper()  # Primer elemento de la tupla
            else:
                col_name = str(col).upper()
            
            if 'PROVEEDOR' in col_name and 'ID' not in col_name:
                col_proveedor = col
                st.write(f"**Debug:** Columna PROVEEDOR encontrada: {col}")
                break
        
        # Si no encontró por nombre, intentar por posición (columna 1 suele ser proveedor)
        if col_proveedor is None and len(df_raw.columns) > 1:
            col_proveedor = df_raw.columns[1]
            st.write(f"**Debug:** Usando columna por posición [1]: {col_proveedor}")
        
        if col_proveedor is None:
            alert("error", "❌ No se pudo identificar la columna de proveedor")
            st.write("**Primeras 5 filas:**")
            st.dataframe(df_raw.head())
            return []
        
        # Limpiar y extraer únicos
        df = df_raw.copy()
        
        st.write(f"**Debug:** Total filas inicial: {len(df)}")
        
        # PASO 1: Detectar y eliminar filas con celdas combinadas puras
        # (Solo "PROVEEDORES PROPIOS MXP", "PROVEEDORES TERCEROS USD", etc.)
        def valores_unicos_por_fila(row):
            valores = [str(v).strip().upper() for v in row if pd.notna(v) and str(v).strip() != '']
            if not valores:
                return 0
            return len(set(valores))
        
        df['_num_valores_unicos'] = df.apply(valores_unicos_por_fila, axis=1)
        filas_antes = len(df)
        df = df[df['_num_valores_unicos'] > 1]
        st.write(f"**Debug:** Celdas combinadas eliminadas: {filas_antes - len(df)}")
        df = df.drop('_num_valores_unicos', axis=1)
        
        # PASO 2: Eliminar filas de SUBTOTAL
        # En el HTML aparecen como "SUBTOTAL DEL PROVEEDORXXXX" (concatenado)
        antes = len(df)
        df = df[~df[col_proveedor].astype(str).str.contains('SUBTOTAL', case=False, na=False)]
        st.write(f"**Debug:** SUBTOTALs eliminados: {antes - len(df)}")
        
        # PASO 3: Filtrar por FACTURA válida (no vacía)
        col_factura = None
        for col in df.columns:
            # Manejar columnas multi-index (tuplas) y columnas simples
            if isinstance(col, tuple):
                col_name = str(col[0]).upper()
            else:
                col_name = str(col).upper()
            
            if 'FACTURA' in col_name:
                col_factura = col
                break
        
        if col_factura is not None:
            antes = len(df)
            df = df[df[col_factura].notna()]
            df = df[df[col_factura].astype(str).str.strip() != '']
            st.write(f"**Debug:** Después de filtrar por FACTURA: {len(df)} filas (eliminadas: {antes - len(df)})")
        
        # PASO 4: Filtrar PROVEEDOR no vacío
        df = df[df[col_proveedor].notna()]
        df = df[df[col_proveedor].astype(str).str.strip() != '']
        
        st.write(f"**Debug:** Filas finales: {len(df)}")
        
        if df.empty:
            alert("warn", "⚠️ No quedaron filas después de aplicar filtros")
            return []
        
        # Extraer proveedores únicos
        proveedores = df[col_proveedor].str.strip().str.upper().unique().tolist()
        proveedores = [p for p in proveedores if p and str(p).upper() != 'NAN' and len(str(p)) > 2]
        
        st.write(f"**Debug:** Se extrajeron {len(proveedores)} proveedores únicos")
        if proveedores:
            st.write(f"**Debug:** Primeros 5 proveedores: {proveedores[:5]}")
        
        return proveedores
        
    except Exception as e:
        st.error(f"❌ Error en _extraer_proveedores_sac_anterior: {str(e)}")
        st.exception(e)
        return []


def _extraer_proveedores_sac_nuevo(archivo_bytes):
    """Extrae proveedores de SAC Nuevo"""
    df_raw = pd.read_excel(BytesIO(archivo_bytes), sheet_name=0, header=None)
    
    # Buscar header
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
    
    # Limpiar
    df = df[~df['Proveedor'].astype(str).str.contains('SUBTOTAL', case=False, na=False)]
    df = df[~df['Proveedor'].astype(str).str.contains('TOTAL DE PROVEEDORES', case=False, na=False)]
    df = df[~df['Proveedor'].astype(str).str.contains('ID:', case=False, na=False)]
    df = df[~df['Proveedor'].astype(str).str.contains(':', case=False, na=False)]
    df = df[df['Proveedor'].notna()]
    
    proveedores = df['Proveedor'].str.strip().str.upper().unique().tolist()
    return [p for p in proveedores if p and p != 'NAN']


def _procesar_sac_anterior(archivo_bytes, catalogo_df):
    """
    Procesa SAC Anterior (Picus, Igloo)
    Maneja tanto HTML como Excel
    Incluye columna UUID para empresas mexicanas
    """
    df_raw = _leer_archivo_sac_anterior(archivo_bytes)
    
    if df_raw.empty:
        raise ValueError("No se pudieron leer datos del archivo")
    
    # Normalizar nombres de columnas
    # El HTML puede tener columnas multi-index (tuplas)
    df = df_raw.copy()
    
    # Si las columnas son tuplas (multi-index), aplanar usando el primer elemento
    if isinstance(df.columns[0], tuple):
        nuevos_nombres = {}
        for col in df.columns:
            nuevos_nombres[col] = col[0]  # Usar primer elemento de la tupla
        df.rename(columns=nuevos_nombres, inplace=True)
    
    # Mapear columnas por posición si no son reconocibles
    columnas_esperadas = {
        0: 'ID',
        1: 'PROVEEDOR',
        2: 'DIAS CRED',
        3: 'FACTURA',
        4: 'TRAFICO',
        5: 'NUM CR',
        6: 'FECHA REP FACT/CR',
        7: 'FECHA VENC',
        8: 'SALDO',
        9: 'POR VENCER',
        10: '1-15 DIAS',
        11: '16-30 DIAS',
        12: '31-60 DIAS',
        13: '+60',
        14: 'MONEDA',
        15: 'UUID'
    }
    
    # Si las columnas actuales no coinciden con lo esperado, renombrar por posición
    columnas_actuales_upper = [str(c).upper() for c in df.columns]
    if 'PROVEEDOR' not in columnas_actuales_upper or 'FACTURA' not in columnas_actuales_upper:
        if len(df.columns) >= 14:
            nuevos_nombres = {}
            for idx, col in enumerate(df.columns):
                if idx in columnas_esperadas:
                    nuevos_nombres[col] = columnas_esperadas[idx]
            df.rename(columns=nuevos_nombres, inplace=True)
    
    # Limpiar filas que no son proveedores reales
    # Buscar columna PROVEEDOR (puede ser string o tupla)
    col_proveedor = None
    col_factura = None
    
    for col in df.columns:
        if isinstance(col, tuple):
            col_name = str(col[0]).upper()
        else:
            col_name = str(col).upper()
        
        if 'PROVEEDOR' in col_name and 'ID' not in col_name and col_proveedor is None:
            col_proveedor = col
        if 'FACTURA' in col_name and col_factura is None:
            col_factura = col
    
    if col_proveedor is not None:
        # FILTRAR FILAS DE AGRUPACION "PROVEEDORES PROPIOS"
        filas_antes = len(df)
        df = df[~df[col_proveedor].astype(str).str.upper().str.contains('PROVEEDORES PROPIOS', na=False)]
        filas_despues = len(df)
        if filas_antes != filas_despues:
            st.info(f"ℹ️ Filtradas {filas_antes - filas_despues} filas de agrupacion en procesamiento")
    
    if col_proveedor is not None and col_factura is not None:
        # PASO 1: Detectar y eliminar celdas combinadas puras
        def valores_unicos_por_fila(row):
            valores = [str(v).strip().upper() for v in row if pd.notna(v) and str(v).strip() != '']
            if not valores:
                return 0
            return len(set(valores))
        
        df['_num_valores_unicos'] = df.apply(valores_unicos_por_fila, axis=1)
        df = df[df['_num_valores_unicos'] > 1]
        df = df.drop('_num_valores_unicos', axis=1)
        
        # PASO 2: Eliminar SUBTOTAL (concatenado en el HTML)
        df = df[~df[col_proveedor].astype(str).str.contains('SUBTOTAL', case=False, na=False)]
        
        # PASO 3: Filtrar por FACTURA válida
        df = df[df[col_factura].notna()]
        df = df[df[col_factura].astype(str).str.strip() != '']
        
        # PASO 4: Filtrar PROVEEDOR no vacío
        df = df[df[col_proveedor].notna()]
        df = df[df[col_proveedor].astype(str).str.strip() != '']
    
    # Normalizar columna de antigüedad >60 días
    if '+60' not in df.columns and 'MAS DE 60' in df.columns:
        df.rename(columns={'MAS DE 60': '+60'}, inplace=True)
    elif '+60' not in df.columns and len(df.columns) > 13:
        df.rename(columns={df.columns[13]: '+60'}, inplace=True)
    
    # Asignar tipos desde catalogo
    # Buscar columna PROVEEDOR (puede tener nombre diferente)
    col_prov_final = None
    for col in df.columns:
        if 'PROVEEDOR' in str(col).upper():
            col_prov_final = col
            break
    
    if col_prov_final is not None:
        if not catalogo_df.empty:
            # AGREGAR ESTAS LINEAS DE DEBUG:
            st.write(f"**Debug Clasificacion:**")
            st.write(f"  - Proveedores en archivo: {len(df)}")
            st.write(f"  - Proveedores en catalogo: {len(catalogo_df)}")
            st.write(f"  - Catalogo primeros 3: {catalogo_df['PROVEEDOR'].head(3).tolist()}")
            st.write(f"  - Archivo primeros 3: {df[col_prov_final].head(3).tolist()}")
            
            catalogo_dict = dict(zip(
                catalogo_df['PROVEEDOR'].str.strip().str.upper(),
                catalogo_df['TIPO']
            ))
            df['TIPO'] = df[col_prov_final].astype(str).str.strip().str.upper().map(catalogo_dict)
            
            # AGREGAR ESTADISTICAS:
            clasificados = df['TIPO'].notna().sum()
            st.info(f"📊 Clasificados: {clasificados}/{len(df)} ({clasificados/len(df)*100:.1f}%)")
            
            # Mostrar algunos que NO se clasificaron
            sin_clasificar = df[df['TIPO'].isna()][[col_prov_final]].head(5)
            if not sin_clasificar.empty:
                st.warning(f"⚠️ Ejemplos sin clasificar:")
                st.dataframe(sin_clasificar)
        else:
            alert("warn", "⚠️ Catalogo vacio - TIPO quedara vacio")
            df['TIPO'] = None
    else:
        alert("error", "❌ No se encontro columna PROVEEDOR para clasificar")
        df['TIPO'] = None
    
    # Columnas finales (incluyendo UUID si existe)
    columnas_finales = [
        'ID', 'PROVEEDOR', 'DIAS CRED', 'FACTURA', 'TRAFICO',
        'NUM CR', 'FECHA REP FACT/CR', 'FECHA VENC', 'SALDO',
        'POR VENCER', '1-15 DIAS', '16-30 DIAS', '31-60 DIAS', '+60',
        'MONEDA', 'UUID', 'TIPO'
    ]
    
    # Crear columnas faltantes
    for col in columnas_finales:
        if col not in df.columns:
            df[col] = None
    
    return df[columnas_finales]


def _procesar_sac_nuevo(archivo_bytes, catalogo_df):
    """Procesa SAC Nuevo (Lincoln, Set Logis, Set Freight)"""
    
    df_raw = pd.read_excel(BytesIO(archivo_bytes), sheet_name=0, header=None)
    
    # Buscar header
    header_row = None
    for idx in range(min(20, len(df_raw))):
        row_str = ' '.join(str(v) for v in df_raw.iloc[idx].values if pd.notna(v))
        if 'Proveedor' in row_str and ('Dias Credito' in row_str or 'Días Crédito' in row_str):
            header_row = idx
            break
    
    if header_row is None:
        alert("error", "❌ No se encontraron encabezados válidos")
        st.write("**Primeras 10 filas del archivo:**")
        st.dataframe(df_raw.head(10))
        raise ValueError("No se encontraron encabezados con 'Proveedor' y 'Dias Credito'")
    
    df = pd.read_excel(BytesIO(archivo_bytes), sheet_name=0, header=header_row)
    
    if 'Proveedor' not in df.columns:
        st.error(f"❌ Columna 'Proveedor' no encontrada")
        st.write(f"**Columnas:** {df.columns.tolist()}")
        raise ValueError(f"Columna 'Proveedor' no encontrada")
    
    # Limpiar
    df = df[~df['Proveedor'].astype(str).str.contains('SUBTOTAL', case=False, na=False)]
    df = df[~df['Proveedor'].astype(str).str.contains('TOTAL DE PROVEEDORES', case=False, na=False)]
    df = df[~df['Proveedor'].astype(str).str.contains('ID:', case=False, na=False)]
    df = df[~df['Proveedor'].astype(str).str.contains(':', case=False, na=False)]
    df = df[df['Proveedor'].notna()]
    
    if 'Num CR' in df.columns:
        df = df[df['Num CR'].notna()]
    
    # Extraer IDs
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
    
    # Merge para IDs
    if 'Factura' in df.columns and 'Num CR' in df.columns:
        df = df.merge(
            df_full[['Proveedor', 'Factura', 'Num CR', 'ID_EXTRAIDO']],
            on=['Proveedor', 'Factura', 'Num CR'],
            how='left'
        )
    else:
        df['ID_EXTRAIDO'] = None
    
    # Renombrar
    df.rename(columns={
        'Proveedor': 'PROVEEDOR',
        'Dias Credito': 'DIAS CRED',
        'Factura': 'FACTURA',
        'Referencia': 'TRAFICO',
        'Ejecutivo': 'EJECUTIVO',
        'Num CR': 'NUM CR',
        'Fecha Rep Fac/Cr': 'FECHA REP FACT/CR',
        'Fecha Venc': 'FECHA VENC',
        'Saldo': 'SALDO',
        'Por Vencer': 'POR VENCER',
        '1-15 dias': '1-15 DIAS',
        '16-30 dias': '16-30 DIAS',
        '31-60 dias': '31-60 DIAS',
        '+60': '+60',
        'Moneda': 'MONEDA',
        'ID_EXTRAIDO': 'ID'
    }, inplace=True)
    
    # Asignar tipos
    if not catalogo_df.empty:
        catalogo_dict = dict(zip(
            catalogo_df['PROVEEDOR'].str.strip().str.upper(),
            catalogo_df['TIPO']
        ))
        df['TIPO'] = df['PROVEEDOR'].str.strip().str.upper().map(catalogo_dict)
    else:
        df['TIPO'] = None
    
    # Columnas finales (SIN UUID para empresas americanas)
    columnas_finales = [
        'ID', 'PROVEEDOR', 'DIAS CRED', 'FACTURA', 'TRAFICO',
        'NUM CR', 'FECHA REP FACT/CR', 'FECHA VENC', 'SALDO',
        'POR VENCER', '1-15 DIAS', '16-30 DIAS', '31-60 DIAS', '+60',
        'MONEDA', 'TIPO'
    ]
    
    for col in columnas_finales:
        if col not in df.columns:
            df[col] = None
    
    return df[columnas_finales]


def _procesar_sac(archivo_bytes, formato, catalogo_df):
    """Router que procesa según formato detectado"""
    if formato == 'anterior':
        return _procesar_sac_anterior(archivo_bytes, catalogo_df)
    else:
        return _procesar_sac_nuevo(archivo_bytes, catalogo_df)


def _exportar_excel(cartera_df, catalogo_df):
    """Exporta a Excel con dos hojas: CARTERA y CATALOGO"""
    output = BytesIO()
    
    # Hacer copia para no modificar el original
    df_export = cartera_df.copy()
    
    # CORRECCION: Aplanar columnas MultiIndex
    if isinstance(df_export.columns, pd.MultiIndex):
        alert("info", "ℹ️ Columnas MultiIndex detectadas - aplanando")
        df_export.columns = [
            '_'.join(map(str, col)).strip('_') 
            if isinstance(col, tuple) 
            else str(col) 
            for col in df_export.columns
        ]
    
    # Resetear index MultiIndex
    if isinstance(df_export.index, pd.MultiIndex):
        alert("info", "ℹ️ Index MultiIndex detectado - reseteando")
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
    from ui.components import section_header, alert, divider
    """Renderiza el módulo con diseño mejorado Streamlit 2026"""
    
    # CSS personalizado
    st.markdown("""
        <style>
        .banner-cartera {
            background: linear-gradient(135deg, #1B2266 0%, #252D80 100%);
            color: white;
            padding: 1.5rem 2rem;
            border-radius: 16px;
            margin-bottom: 2rem;
            display: flex;
            align-items: center;
            gap: 1.5rem;
            border-left: 6px solid #CC1E1E;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }
        
        .banner-icon { font-size: 2.5rem; }
        
        .banner-content h2 {
            margin: 0;
            color: white !important;
            font-weight: 700;
            font-size: 1.8rem;
        }
        
        .banner-content p {
            margin: 0.5rem 0 0 0;
            opacity: 0.9;
            font-size: 0.95rem;
        }
        
        .stTabs [data-baseweb="tab-list"] {
            gap: 12px;
            background: transparent;
        }
        
        .stTabs [data-baseweb="tab"] {
            border-radius: 10px 10px 0 0;
            padding: 14px 28px;
            font-weight: 600;
            background: rgba(102, 126, 234, 0.1);
        }
        
        .stTabs [aria-selected="true"] {
            background: linear-gradient(135deg, #1B2266 0%, #252D80 100%);
            color: white !important;
        }
        
        .stButton>button {
            border-radius: 10px;
            font-weight: 600;
            transition: all 0.3s ease;
            box-shadow: 0 2px 6px rgba(0,0,0,0.12);
        }
        
        .stButton>button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 16px rgba(102, 126, 234, 0.4);
        }
        
        .stButton>button[kind="primary"] {
            background: linear-gradient(135deg, #1B2266 0%, #252D80 100%);
        }
        
        [data-testid="stMetricValue"] {
            font-size: 2rem;
            font-weight: 700;
            background: linear-gradient(135deg, #1B2266 0%, #252D80 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        [data-testid="stFileUploader"] {
            border-radius: 14px;
            border: 2px dashed #667eea;
            background: rgba(102, 126, 234, 0.05);
            padding: 1.5rem;
        }
        
        .dataframe {
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0,0,0,0.08);
        }
        </style>
    """, unsafe_allow_html=True)
    
    # Banner
    st.markdown("""
    <div class="banner-cartera">
        <div class="banner-icon">📊</div>
        <div class="banner-content">
            <h2>Cartera de Proveedores</h2>
            <p>Convierte archivos SAC a formato Cartera con clasificación automática</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Inicializar Supabase
    if 'supabase' not in st.session_state:
        try:
            st.session_state.supabase = create_client(
                st.secrets["SUPABASE_URL"],
                st.secrets.get("SUPABASE_SERVICE_KEY", st.secrets["SUPABASE_KEY"])
            )
        except Exception as e:
            st.error(f"❌ Error conectando a Supabase: {str(e)}")
            st.stop()
    
    # Tabs
    tab1, tab2 = st.tabs(["📤 Procesar SAC", "📋 Catálogos"])
    
    # TAB 1: PROCESAR SAC
    with tab1:
        st.markdown("### 📂 Paso 1: Cargar Archivo SAC")
        
        empresa = st.selectbox(
            "🏢 Empresa",
            options=list(EMPRESAS.keys()),
            format_func=lambda x: EMPRESAS[x]['nombre'],
            help="Selecciona la empresa para procesar"
        )
        
        archivo = st.file_uploader(
            "📎 Sube tu archivo SAC (.xls o .xlsx)",
            type=['xls', 'xlsx'],
            help="El formato se detectará automáticamente (Excel o HTML)"
        )
        
        if archivo:
            archivo_bytes = archivo.read()
            
            # Detectar formato
            formato_detectado = _detectar_formato_sac(archivo_bytes)
            
            if formato_detectado is None:
                alert("error", "❌ No se pudo detectar el formato del archivo")
                alert("info", "Verifica que sea un archivo SAC válido")
                st.stop()
            
            # Mostrar formato
            es_html = _es_archivo_html(archivo_bytes)
            formato_nombre = "SAC Anterior (Picus/Igloo)" if formato_detectado == 'anterior' else "SAC Nuevo (Lincoln/Set Logis/Set Freight)"
            formato_emoji = "🟦" if formato_detectado == 'anterior' else "🟩"
            tipo_archivo = "HTML" if es_html else "Excel"
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.success(f"✅ Formato: **{formato_nombre}**")
            with col2:
                st.info(f"{formato_emoji} Tipo: **{tipo_archivo}**")
            with col3:
                st.info(f"📄 Archivo: **{archivo.name}**")
            
            st.markdown("---")
            
            # PASO 2: VERIFICAR CATÁLOGO
            st.markdown("### 📋 Paso 2: Verificar Catálogo de Proveedores")
            
            catalogo_existente = _cargar_catalogo(empresa)
            proveedores_archivo = _extraer_proveedores_del_archivo(archivo_bytes, formato_detectado)
            
            if not proveedores_archivo:
                alert("error", "❌ No se pudieron extraer proveedores del archivo")
                st.stop()
            
            proveedores_en_catalogo = set(catalogo_existente['PROVEEDOR'].tolist()) if not catalogo_existente.empty else set()
            proveedores_faltantes = [p for p in proveedores_archivo if p not in proveedores_en_catalogo]
            
            # Métricas
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("📄 En Archivo", len(proveedores_archivo), delta="proveedores únicos")
            with col2:
                st.metric("✅ En Catálogo", len(proveedores_archivo) - len(proveedores_faltantes),
                         delta=f"{((len(proveedores_archivo) - len(proveedores_faltantes))/len(proveedores_archivo)*100):.0f}%" if proveedores_archivo else "0%")
            with col3:
                st.metric("⚠️ Faltantes", len(proveedores_faltantes), delta="sin clasificar", delta_color="inverse")
            
            st.markdown("---")
            
            # Si hay faltantes, capturarlos
            if proveedores_faltantes:
                st.warning(f"⚠️ **Hay {len(proveedores_faltantes)} proveedores sin catalogar**")
                alert("info", "👇 Completa el catálogo antes de continuar")
                
                df_faltantes = pd.DataFrame({
                    'PROVEEDOR': proveedores_faltantes,
                    'TIPO': [None] * len(proveedores_faltantes)
                })
                df_faltantes = df_faltantes.sort_values('PROVEEDOR').reset_index(drop=True)
                
                st.markdown("#### ✏️ Clasificar Proveedores Faltantes")
                
                proveedores_editados = st.data_editor(
                    df_faltantes,
                    num_rows="fixed",
                    use_container_width=True,
                    column_config={
                        "PROVEEDOR": st.column_config.TextColumn("Proveedor", disabled=True),
                        "TIPO": st.column_config.SelectboxColumn("Tipo", options=TIPOS_VALIDOS, required=True)
                    },
                    key="proveedores_faltantes_editor"
                )
                
                proveedores_sin_tipo = proveedores_editados[proveedores_editados['TIPO'].isna()]
                
                if not proveedores_sin_tipo.empty:
                    st.warning(f"⚠️ Faltan {len(proveedores_sin_tipo)} proveedores por clasificar")
                else:
                    alert("success", "✅ Todos los proveedores tienen tipo asignado")
                
                col1, col2 = st.columns([1, 3])
                with col1:
                    if st.button("💾 Guardar en Catálogo", type="primary", use_container_width=True,
                                disabled=not proveedores_sin_tipo.empty):
                        try:
                            supabase = st.session_state.supabase
                            exito = 0
                            
                            for _, row in proveedores_editados.iterrows():
                                if pd.notna(row['TIPO']):
                                    try:
                                        supabase.table('catalogo_proveedores').insert({
                                            'empresa': empresa,
                                            'proveedor': row['PROVEEDOR'],
                                            'tipo': row['TIPO']
                                        }).execute()
                                        exito += 1
                                    except Exception as e:
                                        if 'duplicate' not in str(e).lower():
                                            pass
                            
                            st.success(f"✅ {exito} proveedores guardados")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Error: {str(e)}")
                
                st.stop()
            else:
                alert("success", "✅ **Todos los proveedores están en el catálogo**")
            
            st.markdown("---")
            
            # PASO 3: PROCESAR
            st.markdown("### 🔄 Paso 3: Procesar Archivo")
            
            catalogo_actualizado = _cargar_catalogo(empresa)
            
            col1, col2 = st.columns([1, 3])
            with col1:
                if st.button("🚀 Procesar Archivo", type="primary", use_container_width=True):
                    with st.spinner("⏳ Procesando..."):
                        try:
                            cartera_df = _procesar_sac(archivo_bytes, formato_detectado, catalogo_actualizado)
                            
                            st.session_state['cartera_procesada'] = cartera_df
                            st.session_state['catalogo_usado'] = catalogo_actualizado
                            st.session_state['empresa_procesada'] = empresa
                            
                            st.success(f"✅ **¡Procesado!** {len(cartera_df):,} registros")
                        
                        except Exception as e:
                            st.error(f"❌ Error: {str(e)}")
                            with st.expander("🔍 Ver detalles"):
                                st.exception(e)
            
            # Mostrar resultados
            if 'cartera_procesada' in st.session_state:
                cartera_df = st.session_state['cartera_procesada']
                
                st.markdown("---")
                st.markdown("#### 📈 Resumen")
                
                col1, col2, col3, col4 = st.columns(4)
                
                # Buscar columnas de forma flexible (pueden ser tuplas o strings)
                col_proveedor_name = None
                col_saldo_name = None
                col_tipo_name = None
                
                for col in cartera_df.columns:
                    col_str = str(col).upper()
                    if isinstance(col, tuple):
                        col_first = str(col[0]).upper()
                    else:
                        col_first = col_str
                    
                    if 'PROVEEDOR' in col_first and 'ID' not in col_first and col_proveedor_name is None:
                        col_proveedor_name = col
                    if 'SALDO' in col_first and 'VENCER' not in col_first and col_saldo_name is None:
                        col_saldo_name = col
                    if 'TIPO' in col_first and col_tipo_name is None:
                        col_tipo_name = col
                
                with col1:
                    st.metric("📝 Registros", f"{len(cartera_df):,}", delta="procesados")
                
                with col2:
                    if col_proveedor_name is not None:
                        st.metric("👥 Proveedores", cartera_df[col_proveedor_name].nunique(), delta="únicos")
                    else:
                        st.metric("👥 Proveedores", "N/A")
                
                with col3:
                    if col_saldo_name is not None:
                        try:
                            saldo_total = pd.to_numeric(cartera_df[col_saldo_name], errors='coerce').sum()
                            st.metric("💰 Saldo Total", f"${saldo_total:,.2f}", delta="MXN")
                        except:
                            st.metric("💰 Saldo Total", "N/A")
                    else:
                        st.metric("💰 Saldo Total", "N/A")
                
                with col4:
                    if col_tipo_name is not None:
                        con_tipo = cartera_df[col_tipo_name].notna().sum()
                        st.metric("✓ Clasificados", f"{con_tipo:,}", delta=f"{(con_tipo/len(cartera_df)*100):.1f}%")
                    else:
                        st.metric("✓ Clasificados", "N/A")
                
                st.markdown("---")
                
                st.markdown("#### 👁️ Vista Previa")
                
                # Filtrar filas de agrupacion para la vista previa
                df_vista = cartera_df.copy()
                if len(df_vista.columns) > 0:
                    primera_col = df_vista.columns[0]
                    df_vista = df_vista[~df_vista[primera_col].astype(str).str.upper().str.contains('PROVEEDORES PROPIOS', na=False)]
                
                st.dataframe(df_vista, use_container_width=True, height=400)
                
                st.markdown("#### 📥 Descargar")
                catalogo_usado = st.session_state.get('catalogo_usado', catalogo_actualizado)
                excel_bytes = _exportar_excel(cartera_df, catalogo_usado)
                
                st.download_button(
                    label="⬇️ Descargar Excel (CARTERA + CATÁLOGO)",
                    data=excel_bytes,
                    file_name=f"CARTERA_{empresa}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    type="primary"
                )
    
    # TAB 2: CATÁLOGOS
    with tab2:
        st.markdown("### 📋 Gestión de Catálogos")
        
        empresa_cat = st.selectbox(
            "🏢 Empresa",
            options=list(EMPRESAS.keys()),
            format_func=lambda x: EMPRESAS[x]['nombre'],
            key='empresa_cat'
        )
        
        catalogo_df = _cargar_catalogo(empresa_cat)
        
        col1, col2 = st.columns([1, 2])
        with col1:
            st.metric("📊 Proveedores catalogados", len(catalogo_df), delta="registros")
        
        accion = st.selectbox("⚙️ Acción", ["Ver Catálogo", "Agregar Proveedor", "Importar desde Excel"])
        
        st.markdown("---")
        
        if accion == "Ver Catálogo":
            if not catalogo_df.empty:
                busqueda = st.text_input("🔍 Buscar proveedor", placeholder="Escribe el nombre...")
                
                if busqueda:
                    catalogo_filtrado = catalogo_df[catalogo_df['PROVEEDOR'].str.contains(busqueda, case=False, na=False)]
                    st.info(f"📍 Encontrados: **{len(catalogo_filtrado)}** registros")
                else:
                    catalogo_filtrado = catalogo_df
                
                st.dataframe(catalogo_filtrado, use_container_width=True, height=500)
            else:
                alert("info", "📭 No hay proveedores catalogados")
        
        elif accion == "Agregar Proveedor":
            with st.form("agregar_proveedor"):
                st.markdown("##### ➕ Nuevo Proveedor")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    proveedor = st.text_input("Nombre del Proveedor *", placeholder="Ej: ACME CORP")
                
                with col2:
                    tipo = st.selectbox("Tipo de Proveedor *", TIPOS_VALIDOS)
                
                st.markdown("---")
                
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    if st.form_submit_button("✅ Agregar", use_container_width=True, type="primary"):
                        if proveedor.strip():
                            try:
                                supabase = st.session_state.supabase
                                supabase.table('catalogo_proveedores').insert({
                                    'empresa': empresa_cat,
                                    'proveedor': proveedor.strip(),
                                    'tipo': tipo
                                }).execute()
                                st.success(f"✅ **'{proveedor}'** agregado")
                                st.rerun()
                            except Exception as e:
                                if 'duplicate' in str(e).lower():
                                    st.warning(f"⚠️ El proveedor ya existe")
                                else:
                                    st.error(f"❌ Error: {str(e)}")
                        else:
                            alert("warn", "⚠️ El nombre es obligatorio")
                
                with col2:
                    if st.form_submit_button("❌ Cancelar", use_container_width=True):
                        st.rerun()
        
        elif accion == "Importar desde Excel":
            alert("info", "📄 Sube un Excel con hoja **CATALOGO** (o **T** para Lincoln)")
            st.markdown("""
            **Formato:**
            - Hoja: `CATALOGO` (o `T` para Lincoln)
            - Columnas: `PROVEEDOR` y `TIPO`
            """)
            
            archivo_cat = st.file_uploader("📎 Selecciona archivo", type=['xlsx', 'xls'], key='import_cat')
            
            if archivo_cat:
                if st.button("🚀 Importar", use_container_width=True, type="primary"):
                    try:
                        hoja = 'T' if empresa_cat == 'LINCOLN' else 'CATALOGO'
                        df_import = pd.read_excel(archivo_cat, sheet_name=hoja)
                        
                        col_proveedor = None
                        col_tipo = None
                        
                        for col in df_import.columns:
                            col_upper = str(col).upper()
                            if 'PROVEEDOR' in col_upper and col_proveedor is None:
                                col_proveedor = col
                            if 'TIPO' in col_upper and col_tipo is None:
                                col_tipo = col
                        
                        if col_proveedor is None or col_tipo is None:
                            alert("error", "❌ No se encontraron las columnas PROVEEDOR y TIPO")
                            st.write("Columnas:", df_import.columns.tolist())
                            st.stop()
                        
                        supabase = st.session_state.supabase
                        exito = 0
                        duplicados = 0
                        
                        progress = st.progress(0)
                        status = st.empty()
                        
                        for i, row in df_import.iterrows():
                            if pd.notna(row[col_proveedor]) and pd.notna(row[col_tipo]):
                                proveedor = str(row[col_proveedor]).strip()
                                tipo_norm = _normalizar_tipo(row[col_tipo])
                                
                                try:
                                    supabase.table('catalogo_proveedores').insert({
                                        'empresa': empresa_cat,
                                        'proveedor': proveedor,
                                        'tipo': tipo_norm
                                    }).execute()
                                    exito += 1
                                    status.text(f"✅ {proveedor[:50]}")
                                except Exception as e:
                                    if 'duplicate' in str(e).lower():
                                        duplicados += 1
                            
                            progress.progress((i + 1) / len(df_import))
                        
                        progress.empty()
                        status.empty()
                        
                        st.success(f"✅ **Importación completada**")
                        col1, col2 = st.columns(2)
                        with col1:
                            st.metric("✅ Exitosos", exito)
                        with col2:
                            st.metric("⚠️ Duplicados", duplicados)
                        
                        st.rerun()
                    
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
                        with st.expander("Ver detalles"):
                            st.exception(e)
