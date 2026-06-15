# ─────────────────────────────────────────────────────────────────────────────
# PATCH para cotizacion.py de Picus
# Reemplaza ÚNICAMENTE la función render() completa.
# Todo lo demás del archivo (imports, helpers, clase PDF, calcular_lineas,
# estimar_paginas) se queda exactamente igual.
# ─────────────────────────────────────────────────────────────────────────────

def render():
    supabase = get_supabase_client()
    if supabase is None:
        alert("warn", "⚠️ Supabase no configurado. No se pueden cargar rutas para cotizar.")
        return

    # ── Recargar ──────────────────────────────────────────────────────────────
    rc1, rc2 = st.columns([1, 4])
    with rc1:
        if st.button("🔄 Recargar rutas", key="pic_cot_reload"):
            st.cache_data.clear()
            st.rerun()
    with rc2:
        st.caption("Carga cacheada. Usa 'Recargar' si acabas de guardar rutas nuevas.")

    # ── Cargar rutas ──────────────────────────────────────────────────────────
    resp = supabase.table("Rutas_Picus").select("*").order("Fecha", desc=True).execute()
    df   = pd.DataFrame(resp.data) if resp.data else pd.DataFrame()

    if df.empty:
        alert("warn", "⚠️ No hay rutas guardadas. Captura rutas primero.")
        return

    if "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d")

    for col in ["Origen", "Destino", "Cliente", "Tipo"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.upper()

    if "ID_Ruta" in df.columns:
        df = df.set_index("ID_Ruta", drop=False)

    # ── Filtros ────────────────────────────────────────────────────────────────
    divider()
    section_header("🔎", "Filtrar Rutas")
    with st.expander("Filtros opcionales", expanded=False):
        fc1, fc2, fc3, fc4, fc5 = st.columns(5)
        tipos_disp    = ["Todos"] + sorted(df["Tipo"].dropna().unique().tolist())    if "Tipo"    in df.columns else ["Todos"]
        clientes_disp = ["Todos"] + sorted(df["Cliente"].dropna().astype(str).unique().tolist()) if "Cliente" in df.columns else ["Todos"]
        f_tipo    = fc1.selectbox("Tipo",              tipos_disp,    key="pic_cot_ftipo")
        f_cliente = fc2.selectbox("Cliente",           clientes_disp, key="pic_cot_fcli")
        f_origen  = fc3.text_input("Origen contiene",                 key="pic_cot_fori")
        f_destino = fc4.text_input("Destino contiene",                key="pic_cot_fdest")
        f_id      = fc5.text_input("ID contiene",                     key="pic_cot_fid")

    df_f = df.copy()
    if f_tipo    != "Todos": df_f = df_f[df_f["Tipo"].astype(str) == f_tipo]
    if f_cliente != "Todos": df_f = df_f[df_f["Cliente"].astype(str) == f_cliente]
    if f_origen.strip():  df_f = df_f[df_f["Origen"].astype(str).str.upper().str.contains(f_origen.upper(),  na=False)]
    if f_destino.strip(): df_f = df_f[df_f["Destino"].astype(str).str.upper().str.contains(f_destino.upper(), na=False)]
    if f_id.strip():      df_f = df_f[df_f["ID_Ruta"].astype(str).str.upper().str.contains(f_id.upper(),     na=False)]

    # ── Selección de rutas ────────────────────────────────────────────────────
    divider()
    section_header("🛣️", "Selección de Rutas")

    opciones = (
        df_f["ID_Ruta"].astype(str) + " | " +
        df_f["Tipo"].astype(str)    + " | " +
        df_f["Cliente"].astype(str) + " | " +
        df_f["Origen"].astype(str)  + " → " +
        df_f["Destino"].astype(str)
    ).tolist()

    ids_seleccionados = st.multiselect(
        f"🛣️ Elige las rutas a incluir ({len(df_f)} disponibles):",
        options=opciones,
        key="pic_cot_ids",
    )

    # ── Fecha y Datos del Cliente / Empresa ───────────────────────────────────
    divider()
    section_header("📅", "Fecha de Cotización")
    fecha = st.date_input("Fecha", value=date.today(), key="pic_cot_fecha")

    divider()
    section_header("🏢", "Datos del Cliente y Empresa")
    col_cli, col_emp = st.columns(2)

    with col_cli:
        st.markdown("#### 👤 Cliente")
        cliente_nombre    = st.text_input("Nombre del Cliente",    key="pic_cot_cli_nom",  placeholder="NOMBRE DE LA EMPRESA")
        cliente_direccion = st.text_input("Dirección del Cliente",  key="pic_cot_cli_dir",  placeholder="Calle, Ciudad, Estado")
        cliente_mail      = st.text_input("Email del Cliente",      key="pic_cot_cli_mail", placeholder="correo@empresa.com")
        cli_col1, cli_col2 = st.columns(2)
        cliente_telefono  = cli_col1.text_input("Teléfono Cliente", key="pic_cot_cli_tel",  placeholder="867 123 4567")
        cliente_ext       = cli_col2.text_input("Ext.",             key="pic_cot_cli_ext",  placeholder="1000")

    with col_emp:
        st.markdown("#### 🏢 Empresa")
        empresa_nombre    = st.text_input("Nombre de la Empresa",   key="pic_cot_emp_nom",  value="Picus")
        empresa_direccion = st.text_input("Dirección de la Empresa", key="pic_cot_emp_dir",  placeholder="Dirección completa")
        empresa_mail      = st.text_input("Email de la Empresa",     key="pic_cot_emp_mail", value="operaciones@picus.com")
        emp_col1, emp_col2 = st.columns(2)
        empresa_telefono  = emp_col1.text_input("Teléfono Empresa",  key="pic_cot_emp_tel",  placeholder="867 718 1823")
        empresa_ext       = emp_col2.text_input("Ext. Empresa",      key="pic_cot_emp_ext",  placeholder="1100")

    # ── Moneda y Tipo de Cambio ───────────────────────────────────────────────
    divider()
    section_header("💱", "Moneda y Tipo de Cambio")
    moneda_default = "MXP"
    if ids_seleccionados:
        id_0 = ids_seleccionados[0].split(" | ")[0].strip()
        if id_0 in df.index:
            moneda_default = str(df.loc[id_0].get("Moneda", "MXP") or "MXP")

    col_mon, col_tc = st.columns(2)
    moneda_cotizacion = col_mon.selectbox(
        "Moneda Principal",
        ["MXP", "USD"],
        index=0 if moneda_default == "MXP" else 1,
        key="pic_cot_moneda",
    )
    tipo_cambio = col_tc.number_input(
        "Tipo de Cambio USD/MXP",
        min_value=0.0, value=18.0, step=0.01,
        key="pic_cot_tc",
    )

    # ── Configuración de conceptos por ruta ───────────────────────────────────
    CONCEPTOS = [
        "Ingreso_Original", "Cruce_Original", "Movimiento_Local", "Puntualidad",
        "Pension", "Estancia", "Pistas_Extra", "Stop", "Falso", "Gatas",
        "Accesorios", "Casetas", "Fianza", "Guias", "Costo_Diesel_Camion",
    ]

    rutas_config = {}

    if ids_seleccionados:
        divider()
        section_header("⚙️", "Configuración de Conceptos por Ruta")
        for ruta_sel in ids_seleccionados:
            with st.expander(f"📋 Configurar: {ruta_sel}", expanded=False):
                default_sumar   = ["Ingreso_Original", "Cruce_Original"]
                default_visual  = ["Casetas", "Pension", "Estancia", "Movimiento_Local", "Puntualidad"]
                colS, colV = st.columns(2)
                with colS:
                    sumar = st.multiselect(
                        "➕ Sumar al total (Azul)",
                        options=CONCEPTOS,
                        default=[c for c in default_sumar if c in CONCEPTOS],
                        key=f"pic_cot_sumar_{ruta_sel}",
                    )
                with colV:
                    solo_visual = st.multiselect(
                        "👁️ Mostrar sin sumar (Gris)",
                        options=[c for c in CONCEPTOS if c not in sumar],
                        default=[c for c in default_visual if c not in sumar],
                        key=f"pic_cot_visual_{ruta_sel}",
                    )
                sumar       = [c for c in sumar       if c not in solo_visual]
                solo_visual = [c for c in solo_visual if c not in sumar]
                rutas_config[ruta_sel] = {"sumar": sumar, "visual": solo_visual}

    # ── Notas ─────────────────────────────────────────────────────────────────
    divider()
    section_header("📝", "Notas o Condiciones")
    texto_default = (
        "Esta cotización es válida por 15 días. "
        "No aplica IVA y Retenciones en el caso de las importaciones y exportaciones. "
        "Las exportaciones aplican tasa 0."
    )
    notas_cotizacion = st.text_area(
        "Puedes editar este texto si lo deseas:",
        value=texto_default, height=100,
        key="pic_cot_notas",
    )

    # ── Plantilla ─────────────────────────────────────────────────────────────
    plantilla_path = _find_template()
    if plantilla_path and plantilla_path.lower().endswith(".png"):
        try:
            if os.path.getsize(plantilla_path) > 900 * 1024:
                plantilla_path = _optimize_to_jpg(plantilla_path)
        except Exception:
            pass

    if plantilla_path:
        st.caption(f"Plantilla detectada: `{os.path.basename(plantilla_path)}`")
    else:
        alert("warn", "⚠️ No encontré plantilla en portal_app/img. Se usará encabezado básico.")

    # ── Estimación de páginas ─────────────────────────────────────────────────
    if ids_seleccionados:
        lineas           = calcular_lineas_necesarias(rutas_config, ids_seleccionados, df)
        paginas_estimadas = estimar_paginas_necesarias(lineas)
        st.info(f"📊 Estimación: ~{lineas} líneas de conceptos → ~{paginas_estimadas} página(s)")

    # ── Generar PDF ───────────────────────────────────────────────────────────
    divider()
    if st.button(
        "🎯 Generar Cotización PDF",
        disabled=(len(ids_seleccionados) == 0),
        type="primary",
        key="pic_cot_gen",
        use_container_width=True,
    ):
        # ─────────────────────────────────────────────────────────────────────
        # TODO EL BLOQUE DE GENERACIÓN DEL PDF (clase PDF, coordenadas, FPDF)
        # SE MANTIENE EXACTAMENTE IGUAL — NO SE MODIFICA NADA DE AQUÍ ABAJO
        # DENTRO DEL BOTÓN HASTA EL FINAL DEL ARCHIVO ORIGINAL.
        # ─────────────────────────────────────────────────────────────────────
        pass  # ← Este pass se elimina; el contenido original del if va aquí
