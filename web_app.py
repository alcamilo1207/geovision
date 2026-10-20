import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import numpy as np
import base64
import io
import os
from pathlib import Path
from PIL import Image

# Importaciones locales del gemelo digital
from db_manager import (
    init_db, get_equipos_df, upsert_equipo_coords, update_equipo_detalles,
    insert_equipo_completo, delete_equipo, get_condiciones, update_condiciones,
    get_matriz_dano_reparacion_df, update_matriz_dano_reparacion_df, reset_matriz_dano_from_excel,
    update_equipos_costos_df, EXCEL_DANO_PATH
)
from consecuencias import (
    calcular_dinamica_fuga, calcular_radios_consecuencia, evaluar_equipos_afectados,
    calcular_matriz_distancias_geodesica, SpatialTransformer, HAS_PYPROJ, HAS_OPENSRANE,
    ejecutar_simulacion_opensrane, OPENSRANE_VERSION, SUSTANCIAS_DB,
    calcular_analisis_qra_completo, TIPOS_EQUIPO_DISPONIBLES,
    estimar_dano_y_tiempo_reparacion, recargar_cache_matriz_dano
)

try:
    from consecuencias import NIVELES_CONGESTION
except Exception:
    NIVELES_CONGESTION = {
        "Baja (Espacio Abierto, eta=0.03)": {
            "factor_rendimiento": 0.03,
            "descripcion": "Parques de tanques, almacenamiento espaciado, baja densidad de obstáculos"
        },
        "Media (Proceso Estándar, eta=0.10)": {
            "factor_rendimiento": 0.10,
            "descripcion": "Unidades de proceso típicas, densidad estándar de tuberías (API 581)"
        },
        "Alta (Racks Densos, eta=0.20)": {
            "factor_rendimiento": 0.20,
            "descripcion": "Racks de tuberías compactos, estructuras multinivel de alta densidad"
        },
        "Muy Alta / Confinada (Semi-Cerrado, eta=0.35)": {
            "factor_rendimiento": 0.35,
            "descripcion": "Espacios semi-cerrados, compresores bajo techado, alta restricción de escape"
        }
    }
from wind_rose_engine import (
    obtener_rosa_vientos_meteoblue, generar_figura_rosa_vientos_plotly, generar_enlace_meteoblue
)
from qra_standards import (
    NIST_SUSTANCIAS_PROPS, PURPLE_BOOK_DIRECT_IGNITION_TABLE, PURPLE_BOOK_DELAYED_SOURCES,
    BEVI_LOC_TABLAS
)
from gis_engine import (
    procesar_archivo_plotplan, DEFAULT_CENTER, DEFAULT_BOUNDS, HAS_RASTERIO, RASTERIO_ERROR
)

# Inicialización del entorno
init_db()

st.set_page_config(
    layout="wide",
    page_title="GeoVision Plant Extractor — Gemelo Digital & QRA (U044)",
    page_icon="🏭",
    initial_sidebar_state="collapsed"
)

st.title("🏭 GeoVision Plant Extractor — Gemelo Digital & QRA (U044)")
if HAS_OPENSRANE:
    st.caption(f"Termodinámica de Fuga API 581 | **✅ OpenSRANE v{OPENSRANE_VERSION} Activo (Python 3.12)** | Probit Cozzani | Efecto Dominó Espacial | GeoTIFF & GIS")
else:
    st.caption("Termodinámica de Fuga API 581 | ⚠️ OpenSRANE no detectado | Probit Analítico | Efecto Dominó Espacial | GeoTIFF & GIS")


# ---------------- FUNCIONES DE SOPORTE VISUAL ----------------
def obtener_estilo_icono_equipo(tipo_equipo):
    """Retorna color e icono de FontAwesome distintivo para cada categoría de equipo industrial."""
    tipo = str(tipo_equipo).lower()
    if any(k in tipo for k in ['horno', 'heater', 'caldera', 'boiler', 'quemador', 'fired']):
        return {"color": "darkred", "icon": "fire", "prefix": "fa", "etiqueta": "Horno / Caldera"}
    elif 'compresor' in tipo:
        return {"color": "purple", "icon": "cogs", "prefix": "fa", "etiqueta": "Compresor"}
    elif any(k in tipo for k in ['fin fan', 'aeroenfriador', 'cooler', 'enfriador']):
        return {"color": "cadetblue", "icon": "snowflake-o", "prefix": "fa", "etiqueta": "Fin Fan Cooler"}
    elif any(k in tipo for k in ['filtro', 'separador', 'coalescedor']):
        return {"color": "darkgreen", "icon": "filter", "prefix": "fa", "etiqueta": "Filtro / Separador"}
    elif 'bomba' in tipo or 'pump' in tipo:
        return {"color": "blue", "icon": "tint", "prefix": "fa", "etiqueta": "Bomba de Proceso"}
    elif any(k in tipo for k in ['torre', 'fraccionadora', 'columna']):
        return {"color": "green", "icon": "industry", "prefix": "fa", "etiqueta": "Torre Destilación"}
    elif 'tanque' in tipo:
        return {"color": "darkblue", "icon": "database", "prefix": "fa", "etiqueta": "Tanque Atmosférico"}
    elif 'esfera' in tipo or 'bala' in tipo:
        return {"color": "darkpurple", "icon": "circle", "prefix": "fa", "etiqueta": "Esfera / Bala GLP"}
    elif 'reactor' in tipo:
        return {"color": "orange", "icon": "flask", "prefix": "fa", "etiqueta": "Reactor"}
    elif 'intercambiador' in tipo:
        return {"color": "teal", "icon": "exchange", "prefix": "fa", "etiqueta": "Intercambiador Calor"}
    elif any(k in tipo for k in ['rack', 'tubería', 'tuberia', 'manifold']):
        return {"color": "gray", "icon": "bars", "prefix": "fa", "etiqueta": "Rack / Manifold"}
    elif any(k in tipo for k in ['subestación', 'subestacion', 'control']):
        return {"color": "black", "icon": "bolt", "prefix": "fa", "etiqueta": "Cuarto Control / Subestación"}
    else:
        return {"color": "blue", "icon": "cube", "prefix": "fa", "etiqueta": "Equipo de Proceso"}


# ---------------- ESTADO DE SESIÓN ----------------
if 'map_center' not in st.session_state:
    st.session_state.map_center = list(DEFAULT_CENTER)
if 'map_zoom' not in st.session_state:
    st.session_state.map_zoom = 18
if 'tipo_mapa_base' not in st.session_state:
    st.session_state.tipo_mapa_base = "🛰️ Satelital Esri (Alta Resolución)"
if 'fuente_plotplan_sel' not in st.session_state:
    st.session_state.fuente_plotplan_sel = "Plotplan u044 georef.tif (GeoTIFF Oficial)"
if 'opacidad_plano' not in st.session_state:
    st.session_state.opacidad_plano = 0.70
if 'quitar_blanco' not in st.session_state:
    st.session_state.quitar_blanco = True
if 'offset_x' not in st.session_state:
    st.session_state.offset_x = 0.000000
if 'offset_y' not in st.session_state:
    st.session_state.offset_y = 0.000000
if 'fenomeno_activo' not in st.session_state:
    st.session_state.fenomeno_activo = "Radiación Térmica (Jet/Pool Fire)"
if 'tiempo_fuga_min' not in st.session_state:
    st.session_state.tiempo_fuga_min = 5.0
if 'plotplan_data' not in st.session_state:
    st.session_state.plotplan_data = None
if 'cached_file_hash' not in st.session_state:
    st.session_state.cached_file_hash = None
if 'coordenadas_picadas' not in st.session_state:
    st.session_state.coordenadas_picadas = None

# Mapeo de presets estandarizados de diámetro de orificio (API 581)
MAPA_PRESETS_DIAMETRO = {
    "1/4\" (6.4 mm) - Pequeña (Pinhole / Instrumentación)": 6.4,
    "1\" (25.4 mm) - Mediana (Boquilla / Brida) [API 581]": 25.4,
    "2\" (50.8 mm) - Intermedia (Tubería Secundaria)": 50.8,
    "4\" (101.6 mm) - Grande (Tubería Principal)": 101.6,
    "6\" (152.4 mm) - Ruptura Full Bore (6\")": 152.4,
    "10\" (254.0 mm) - Catastrófica Mayor (10\")": 254.0,
    "✏️ Personalizado (Ingresar mm manual)": None
}

carpeta_proyecto = Path(__file__).resolve().parent

# Auto-cargar por defecto el GeoTIFF oficial de la planta si está disponible y la memoria está vacía
if st.session_state.plotplan_data is None and "GeoTIFF Oficial" in st.session_state.fuente_plotplan_sel:
    p_def = carpeta_proyecto / "Plotplan u044 georef.tif"
    if p_def.exists():
        try:
            b_def = p_def.read_bytes()
            st.session_state.plotplan_data = procesar_archivo_plotplan(
                b_def,
                filename="Plotplan u044 georef.tif",
                offset_x=st.session_state.offset_x,
                offset_y=st.session_state.offset_y,
                hacer_blanco_transparente=st.session_state.quitar_blanco
            )
            st.session_state.cached_file_hash = hash(b_def)
        except Exception:
            pass

# Cargar equipos y condiciones desde la base de datos
df_equipos = get_equipos_df()
condiciones = get_condiciones()
tags_lista = df_equipos['tag'].tolist() if not df_equipos.empty else ["44-D-23"]

# Inicializar estados de sesión para el escenario de fuga dinámico
if 'modo_origen_fuga' not in st.session_state:
    st.session_state.modo_origen_fuga = "🏭 Activo del Plot Plan"
if 'tag_origen_fuga' not in st.session_state or st.session_state.tag_origen_fuga not in tags_lista:
    st.session_state.tag_origen_fuga = tags_lista[0]
if 'fuga_custom_tag' not in st.session_state:
    st.session_state.fuga_custom_tag = "Punto-Fuga-01"

row_init = df_equipos[df_equipos['tag'] == st.session_state.tag_origen_fuga].iloc[0] if not df_equipos.empty else None

if 'fuga_latitud' not in st.session_state:
    st.session_state.fuga_latitud = float(row_init['latitud']) if row_init is not None else 10.314855
if 'fuga_longitud' not in st.session_state:
    st.session_state.fuga_longitud = float(row_init['longitud']) if row_init is not None else -75.487632
if 'fuga_sustancia' not in st.session_state:
    st.session_state.fuga_sustancia = str(row_init['sustancia']) if row_init is not None else "GLP / Propano"
if 'fuga_diametro_modo' not in st.session_state:
    st.session_state.fuga_diametro_modo = "1\" (25.4 mm) - Mediana (Boquilla / Brida) [API 581]"
if 'fuga_diametro_mm' not in st.session_state:
    st.session_state.fuga_diametro_mm = 25.4
if 'fuga_presion_bar' not in st.session_state:
    st.session_state.fuga_presion_bar = float(row_init['presion_bar']) if row_init is not None else 18.0
if 'fuga_temp_c' not in st.session_state:
    st.session_state.fuga_temp_c = float(row_init['temperatura_c']) if row_init is not None else 45.0
if 'fuga_inventario_kg' not in st.session_state:
    st.session_state.fuga_inventario_kg = float(row_init['inventario_kg']) if row_init is not None else 15000.0
if 'nivel_congestion' not in st.session_state or 'eta=' not in str(st.session_state.nivel_congestion):
    st.session_state.nivel_congestion = "Media (Proceso Estándar, eta=0.10)"
if 'temperatura_ambiente_c' not in st.session_state:
    st.session_state.temperatura_ambiente_c = float(condiciones.get('temperatura_ambiente_c', 32.0))
if 'humedad_relativa_pct' not in st.session_state:
    st.session_state.humedad_relativa_pct = float(condiciones.get('humedad_relativa_pct', 78.0))
if 'velocidad_viento_ms' not in st.session_state:
    st.session_state.velocidad_viento_ms = float(condiciones.get('velocidad_viento_ms', 4.5))
if 'clase_estabilidad' not in st.session_state:
    st.session_state.clase_estabilidad = str(condiciones.get('clase_estabilidad', 'D'))

# Construir diccionario unificado del emisor
tag_emisor_final = st.session_state.tag_origen_fuga if st.session_state.modo_origen_fuga == "🏭 Activo del Plot Plan" else st.session_state.fuga_custom_tag
tipo_emisor_final = "Activo de Planta" if st.session_state.modo_origen_fuga == "🏭 Activo del Plot Plan" else "Punto Fuga Directo"
if st.session_state.modo_origen_fuga == "🏭 Activo del Plot Plan" and not df_equipos.empty:
    filtro_emisor = df_equipos[df_equipos['tag'] == st.session_state.tag_origen_fuga]
    if not filtro_emisor.empty:
        tipo_emisor_final = str(filtro_emisor.iloc[0].get('tipo_equipo', 'Vessel / Drum'))

eq_emisor = {
    'tag': tag_emisor_final,
    'tipo_equipo': tipo_emisor_final,
    'latitud': float(st.session_state.fuga_latitud),
    'longitud': float(st.session_state.fuga_longitud),
    'sustancia': str(st.session_state.fuga_sustancia),
    'diametro_orificio_mm': float(st.session_state.fuga_diametro_mm),
    'presion_bar': float(st.session_state.fuga_presion_bar),
    'temperatura_c': float(st.session_state.fuga_temp_c),
    'inventario_kg': float(st.session_state.fuga_inventario_kg),
    'altura_fuga_m': 1.5,
    'valor_reposicion_usd': 850000.0
}

condiciones_meteo = {
    'temperatura_ambiente_c': float(st.session_state.temperatura_ambiente_c),
    'humedad_relativa_pct': float(st.session_state.humedad_relativa_pct),
    'velocidad_viento_ms': float(st.session_state.velocidad_viento_ms),
    'clase_estabilidad': str(st.session_state.clase_estabilidad)
}

# Cálculos dinámicos de ingeniería QRA
dinamica_fuga = calcular_dinamica_fuga(
    eq_emisor,
    st.session_state.tiempo_fuga_min,
    diametro_override_mm=st.session_state.fuga_diametro_mm,
    sustancia_override=st.session_state.fuga_sustancia,
    presion_override_bar=st.session_state.fuga_presion_bar,
    temp_override_c=st.session_state.fuga_temp_c,
    inventario_override_kg=st.session_state.fuga_inventario_kg
)
datos_consecuencia = calcular_radios_consecuencia(
    dinamica_fuga,
    st.session_state.fenomeno_activo,
    nivel_congestion=st.session_state.nivel_congestion,
    condiciones_meteo=condiciones_meteo
)
lista_afectados = evaluar_equipos_afectados(
    eq_emisor,
    df_equipos,
    datos_consecuencia["anillos"],
    fenomeno=st.session_state.fenomeno_activo,
    tiempo_fuga_min=st.session_state.tiempo_fuga_min
)

# Cálculo unificado de QRA (Meteoblue, Purple Book, BEVI v4.2, Yellow Book, NIST)
datos_qra_completo = calcular_analisis_qra_completo(
    eq_emisor,
    df_equipos,
    dinamica_fuga,
    datos_consecuencia,
    sustancia_nombre=st.session_state.fuga_sustancia,
    diametro_fuga_mm=st.session_state.fuga_diametro_mm,
    fenomeno=st.session_state.fenomeno_activo,
    tiempo_fuga_min=st.session_state.tiempo_fuga_min
)

# ==============================================================================
# PESTAÑAS PRINCIPALES DEL APLICATIVO (Plot Plan y Equipos como Pestaña 1)
# ==============================================================================
tab_plotplan_equipos, tab_consecuencias, tab_domino, tab_qra_standards, tab_financiero = st.tabs([
    "📐 1. Carga de Plot Plan GeoTIFF & Gemelo Digital (Equipos)",
    "🗺️ 2. Simulación de Escenarios QRA & Radios de Consecuencia",
    "💥 3. Modelación de Consecuencias & Efecto Dominó (OpenSRANE)",
    "🌪️ 4. Rosa de los Vientos (Meteoblue) & QRA (Purple / BEVI / Yellow)",
    "💰 5. Criticidad Financiera Máxima (PML)"
])

# ==============================================================================
# TAB 1: CARGA DE PLOT PLAN GEOREFERENCIADO TIFF & GEMELO DIGITAL (EQUIPOS)
# ==============================================================================
with tab_plotplan_equipos:
    st.subheader("📐 1. Carga de Plot Plan Georreferenciado & Gemelo Digital (Equipos)")
    st.caption("Cargue planos de planta en formato **GeoTIFF (.tif, .tiff)** con georreferenciación real o imágenes (.png, .jpg), calibre la superposición satelital e identifique/registre activos industriales picando directamente sobre el plano.")

    col_up1, col_up2 = st.columns([1.1, 1.9])

    with col_up1:
        st.markdown("##### 📂 Carga & Selección del Plot Plan")
        archivo_subido = st.file_uploader(
            "Subir archivo GeoTIFF (.tif, .tiff) o Imagen (.png, .jpg):",
            type=["tif", "tiff", "png", "jpg", "jpeg"],
            key="uploader_tab1_plotplan",
            help="Cargue un archivo GeoTIFF georreferenciado o una imagen de plot plan."
        )

        archivos_locales = sorted([
            f.name for f in carpeta_proyecto.glob("*.*")
            if f.suffix.lower() in ['.tif', '.tiff', '.png', '.jpg', '.jpeg']
        ])

        opciones_fuente = []
        if "Plotplan u044 georef.tif" in archivos_locales:
            opciones_fuente.append("Plotplan u044 georef.tif (GeoTIFF Oficial)")
        for arch in archivos_locales:
            if arch != "Plotplan u044 georef.tif":
                opciones_fuente.append(f"{arch} (Local)")
        if archivo_subido is not None:
            opciones_fuente.insert(0, f"📤 {archivo_subido.name} (Archivo Subido)")
        opciones_fuente.append("🚫 Ninguno (Solo Satélite)")

        idx_fuente_actual = 0
        if st.session_state.fuente_plotplan_sel in opciones_fuente:
            idx_fuente_actual = opciones_fuente.index(st.session_state.fuente_plotplan_sel)

        sel_fuente = st.selectbox(
            "Plot Plan Activo a Visualizar:",
            opciones_fuente,
            index=idx_fuente_actual,
            key="sb_fuente_plan_tab1"
        )
        if sel_fuente != st.session_state.fuente_plotplan_sel:
            st.session_state.fuente_plotplan_sel = sel_fuente
            st.session_state.plotplan_data = None
            st.rerun()

        # Guardar archivo subido localmente
        if archivo_subido is not None:
            p_guardar = carpeta_proyecto / archivo_subido.name
            if not p_guardar.exists():
                if st.button(f"💾 Guardar '{archivo_subido.name}' en la carpeta del proyecto", key="btn_save_tab1_local", use_container_width=True):
                    p_guardar.write_bytes(archivo_subido.getvalue())
                    st.success(f"Archivo guardado como '{archivo_subido.name}' en la carpeta del proyecto.")
                    st.session_state.fuente_plotplan_sel = f"{archivo_subido.name} (Local)"
                    st.rerun()

        st.markdown("##### 🎛️ Calibración de Superposición")
        c_op1, c_op2 = st.columns(2)
        with c_op1:
            opac_val = st.slider("Opacidad:", 0.0, 1.0, float(st.session_state.opacidad_plano), 0.05, key="sld_opacidad_tab1")
            if opac_val != st.session_state.opacidad_plano:
                st.session_state.opacidad_plano = opac_val
                st.rerun()
        with c_op2:
            chk_blanco = st.checkbox("Fondo blanco transparente", value=st.session_state.quitar_blanco, key="chk_blanco_tab1")
            if chk_blanco != st.session_state.quitar_blanco:
                st.session_state.quitar_blanco = chk_blanco
                st.session_state.plotplan_data = None
                st.rerun()

        c_off1, c_off2 = st.columns(2)
        with c_off1:
            off_x_val = st.number_input("Micro-Ajuste ΔX (Longitud):", value=float(st.session_state.offset_x), step=0.000005, format="%.6f", key="off_x_tab1")
            if off_x_val != st.session_state.offset_x:
                st.session_state.offset_x = off_x_val
                st.session_state.plotplan_data = None
                st.rerun()
        with c_off2:
            off_y_val = st.number_input("Micro-Ajuste ΔY (Latitud):", value=float(st.session_state.offset_y), step=0.000005, format="%.6f", key="off_y_tab1")
            if off_y_val != st.session_state.offset_y:
                st.session_state.offset_y = off_y_val
                st.session_state.plotplan_data = None
                st.rerun()

        # Procesamiento del archivo seleccionado
        bytes_a_procesar = None
        nombre_a_procesar = ""
        if "Ninguno" in sel_fuente:
            st.session_state.plotplan_data = None
        elif archivo_subido is not None and "Archivo Subido" in sel_fuente:
            bytes_a_procesar = archivo_subido.getvalue()
            nombre_a_procesar = archivo_subido.name
        elif "GeoTIFF Oficial" in sel_fuente:
            p_geotiff = carpeta_proyecto / "Plotplan u044 georef.tif"
            if p_geotiff.exists():
                bytes_a_procesar = p_geotiff.read_bytes()
                nombre_a_procesar = p_geotiff.name
        elif "(Local)" in sel_fuente:
            nom_local = sel_fuente.replace(" (Local)", "").strip()
            p_local = carpeta_proyecto / nom_local
            if p_local.exists():
                bytes_a_procesar = p_local.read_bytes()
                nombre_a_procesar = p_local.name

        if bytes_a_procesar is not None:
            calc_hash = hash(bytes_a_procesar) + hash(st.session_state.offset_x) + hash(st.session_state.offset_y) + hash(st.session_state.quitar_blanco)
            if st.session_state.cached_file_hash != calc_hash or st.session_state.plotplan_data is None:
                try:
                    datos_plano = procesar_archivo_plotplan(
                        bytes_a_procesar,
                        filename=nombre_a_procesar,
                        offset_x=st.session_state.offset_x,
                        offset_y=st.session_state.offset_y,
                        hacer_blanco_transparente=st.session_state.quitar_blanco
                    )
                    st.session_state.plotplan_data = datos_plano
                    st.session_state.cached_file_hash = calc_hash
                    if datos_plano["is_geotiff"]:
                        st.session_state.map_center = datos_plano["center"]
                        st.session_state.map_zoom = datos_plano["zoom"]
                except Exception as e_p:
                    st.error(f"Error procesando imagen: {e_p}")

        if st.session_state.plotplan_data is not None:
            meta = st.session_state.plotplan_data["metadata"]
            if meta.get("is_geotiff"):
                st.success(f"✅ **GeoTIFF Georreferenciado Activo:** CRS: `{meta.get('crs', 'N/A')}` | {meta.get('width', 0)}x{meta.get('height', 0)} px")
                b_info = st.session_state.plotplan_data['bounds']
                st.caption(f"Límites WGS84: SW `[{b_info[0][0]:.5f}, {b_info[0][1]:.5f}]` | NE `[{b_info[1][0]:.5f}, {b_info[1][1]:.5f}]`")
            else:
                st.info(f"ℹ️ **Imagen de Planta Activa:** `{meta.get('filename', '')}` ({meta.get('width', 0)}x{meta.get('height', 0)} px)")

            if st.button("🎯 Recentrar Mapa en el Plot Plan", key="btn_recentrar_tab1", use_container_width=True):
                st.session_state.map_center = st.session_state.plotplan_data["center"]
                st.session_state.map_zoom = st.session_state.plotplan_data["zoom"]
                st.rerun()

        st.divider()
        st.markdown("##### 📌 Leyenda de Iconos de Equipos")
        st.markdown("""
        - 🔴 **Hornos & Calderas:** Fuego rojo (llama activa)
        - 🟣 **Compresores:** Engranajes púrpuras
        - ❄️ **Fin Fan Coolers:** Copo de nieve azul cielo
        - 🟢 **Filtros & Separadores:** Filtro verde oscuro
        - 💧 **Bombas de Proceso:** Gota azul
        - 🏭 **Torres de Destilación:** Torre industrial verde
        - 🛢️ **Tanques Atmosféricos:** Cilindro azul oscuro
        - 🟣 **Esferas / Balas GLP:** Círculo púrpura
        - 🧪 **Reactores:** Matraz naranja
        - 🔄 **Intercambiadores:** Flechas de intercambio
        """)

    with col_up2:
        c_map_h1, c_map_h2 = st.columns([2.2, 1.2])
        with c_map_h1:
            sel_base_tab1 = st.radio(
                "Vista Base del Terreno:",
                ["🛰️ Satelital Esri (Alta Resolución)", "🗺️ Mapa Callejero (OpenStreetMap)"],
                index=0 if "Satelital" in st.session_state.tipo_mapa_base else 1,
                horizontal=True,
                key="radio_capa_base_tab1"
            )
            if sel_base_tab1 != st.session_state.tipo_mapa_base:
                st.session_state.tipo_mapa_base = sel_base_tab1
                st.rerun()
        with c_map_h2:
            st.info("💡 **Haga clic en el plano** para capturar coordenadas e identificar nuevos equipos.")

        # Construcción del Mapa de Folium para Tab 1
        m_gemelo = folium.Map(
            location=st.session_state.map_center,
            zoom_start=st.session_state.map_zoom,
            max_zoom=23,
            control_scale=True,
            tiles=None
        )
        es_sat = "Satelital" in st.session_state.tipo_mapa_base
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            attr='Esri Satelital High-Res',
            name='Ortofoto Satelital Esri',
            max_zoom=23,
            overlay=False,
            control=True,
            show=es_sat
        ).add_to(m_gemelo)
        folium.TileLayer(
            tiles='OpenStreetMap',
            name='Mapa Callejero OSM',
            max_zoom=20,
            overlay=False,
            control=True,
            show=not es_sat
        ).add_to(m_gemelo)

        # Plot plan overlay
        if st.session_state.plotplan_data is not None:
            p_data = st.session_state.plotplan_data
            folium.raster_layers.ImageOverlay(
                image=p_data["data_url"],
                bounds=p_data["bounds"],
                opacity=st.session_state.opacidad_plano,
                name="Plot Plan Georreferenciado",
                interactive=False
            ).add_to(m_gemelo)

        # Marcadores de TODOS los equipos en planta con su estilo visual distintivo
        for _, row_eq in df_equipos.iterrows():
            tag_e = str(row_eq['tag']).strip()
            tipo_e = str(row_eq.get('tipo_equipo', 'Equipo'))
            estilo = obtener_estilo_icono_equipo(tipo_e)
            lat_e = float(row_eq['latitud'])
            lon_e = float(row_eq['longitud'])

            folium.Marker(
                location=[lat_e, lon_e],
                tooltip=f"<b>{tag_e}</b> — {tipo_e}<br>Sustancia: {row_eq.get('sustancia', 'N/A')}<br>P: {row_eq.get('presion_bar', 0)} bar | T: {row_eq.get('temperatura_c', 0)} °C",
                popup=f"""<b>🏭 {tag_e}</b><br>
                <b>Tipo:</b> {tipo_e}<br>
                <b>Coordenadas:</b> {lat_e:.6f}, {lon_e:.6f}<br>
                <b>Sustancia:</b> {row_eq.get('sustancia', 'N/A')}<br>
                <b>Inventario:</b> {row_eq.get('inventario_kg', 0):,.0f} kg<br>
                <b>Condiciones:</b> {row_eq.get('presion_bar', 0)} bar | {row_eq.get('temperatura_c', 0)} °C<br>
                <b>Valor Patrimonial:</b> ${row_eq.get('valor_reposicion_usd', 0):,.0f} USD""",
                icon=folium.Icon(color=estilo["color"], icon=estilo["icon"], prefix=estilo["prefix"])
            ).add_to(m_gemelo)

        # Marcador del punto picado
        if st.session_state.get('coordenadas_picadas') is not None:
            pt_lat, pt_lon = st.session_state.coordenadas_picadas
            folium.Marker(
                location=[pt_lat, pt_lon],
                tooltip=f"📍 Coordenadas Picadas: {pt_lat:.6f}, {pt_lon:.6f}",
                popup=f"""<b>📍 Punto Seleccionado en el Plano</b><br>
                <b>Latitud:</b> {pt_lat:.6f}<br>
                <b>Longitud:</b> {pt_lon:.6f}""",
                icon=folium.Icon(color="purple", icon="crosshairs", prefix="fa")
            ).add_to(m_gemelo)

        folium.LatLngPopup().add_to(m_gemelo)
        folium.LayerControl(position="topright").add_to(m_gemelo)

        mapa_gemelo_res = st_folium(
            m_gemelo,
            width=880,
            height=620,
            key="mapa_plotplan_gemelo",
            returned_objects=["zoom", "center", "last_clicked"]
        )
        if mapa_gemelo_res:
            if mapa_gemelo_res.get("zoom") is not None:
                st.session_state.map_zoom = mapa_gemelo_res["zoom"]
            if mapa_gemelo_res.get("center") is not None:
                st.session_state.map_center = [mapa_gemelo_res["center"]["lat"], mapa_gemelo_res["center"]["lng"]]
            if mapa_gemelo_res.get("last_clicked") is not None:
                nuevo_clic = [float(mapa_gemelo_res["last_clicked"]["lat"]), float(mapa_gemelo_res["last_clicked"]["lng"])]
                prev_clic = st.session_state.get('coordenadas_picadas')
                if prev_clic is None or abs(prev_clic[0] - nuevo_clic[0]) > 1e-7 or abs(prev_clic[1] - nuevo_clic[1]) > 1e-7:
                    st.session_state.coordenadas_picadas = nuevo_clic
                    st.rerun()

    # Panel de acción para coordenadas picadas en Tab 1
    if st.session_state.get('coordenadas_picadas') is not None:
        c_pic_lat, c_pic_lon = st.session_state.coordenadas_picadas
        st.markdown(
            f"""<div style="background: rgba(142, 68, 173, 0.12); border-left: 4px solid #8e44ad; padding: 10px 14px; border-radius: 6px; margin-top: 10px; margin-bottom: 8px;">
            <span style="font-size: 15px; font-weight: bold; color: #8e44ad;">📍 Coordenadas Capturadas en el Plot Plan:</span>
            <code style="font-size: 14px; font-weight: bold; color: #d35400;"> Latitud: {c_pic_lat:.6f} , Longitud: {c_pic_lon:.6f}</code>
            </div>""",
            unsafe_allow_html=True
        )

        c_act1, c_act2, c_act3 = st.columns([1.5, 1.8, 0.8])
        with c_act1:
            if st.button("🎯 Fijar como Origen de Fuga (Ir a Simulación)", key="btn_fijar_fuga_tab1", use_container_width=True):
                st.session_state.modo_origen_fuga = "📍 Coordenadas Personalizadas"
                st.session_state.fuga_latitud = c_pic_lat
                st.session_state.fuga_longitud = c_pic_lon
                st.session_state.fuga_custom_tag = f"Fuga-Punto-{c_pic_lat:.4f}"
                st.success(f"Origen de fuga fijado en: {c_pic_lat:.6f}, {c_pic_lon:.6f}. Pase a la Pestaña 2 para simular.")
        with c_act2:
            mostrar_form_tab1 = st.toggle("➕ Identificar / Registrar Nuevo Equipo en este Punto", value=True, key="tgl_form_eq_tab1")
        with c_act3:
            if st.button("🗑️ Desmarcar", key="btn_desmarcar_tab1", use_container_width=True):
                st.session_state.coordenadas_picadas = None
                st.rerun()

        if mostrar_form_tab1:
            with st.expander("📝 Formulario: Identificar & Registrar Equipo en el Gemelo Digital", expanded=True):
                with st.form("form_nuevo_activo_desde_plano_tab1"):
                    f1, f2, f3 = st.columns(3)
                    with f1:
                        nuevo_tag = st.text_input("TAG Identificador del Activo:", placeholder="ej. 44-H-2, 44-C-01, 44-E-15", key="fn_tag")
                        nuevo_tipo = st.selectbox("Tipo de Activo Industrial:", TIPOS_EQUIPO_DISPONIBLES, key="fn_tipo")
                    with f2:
                        nuevo_sust = st.selectbox("Sustancia de Proceso:", list(SUSTANCIAS_DB.keys()), key="fn_sust")
                        nuevo_inv = st.number_input("Inventario en Equipo (kg):", value=15000.0, step=1000.0, key="fn_inv")
                    with f3:
                        nuevo_pres = st.number_input("Presión de Operación (bar):", value=18.0, step=1.0, key="fn_pres")
                        nuevo_temp = st.number_input("Temperatura de Operación (°C):", value=45.0, step=5.0, key="fn_temp")

                    f4, f5, f6 = st.columns(3)
                    with f4:
                        nuevo_orif = st.number_input("Orificio de Fuga Referencia (mm):", value=25.4, step=1.0, key="fn_orif")
                    with f5:
                        nuevo_val = st.number_input("Valor de Reposición (USD):", value=850000.0, step=50000.0, key="fn_val")
                    with f6:
                        nuevo_imp = st.number_input("Impacto Diario por Parada (USD):", value=40000.0, step=5000.0, key="fn_imp")

                    if st.form_submit_button("💾 Guardar Equipo en Base de Datos y Añadir al Gemelo Digital", use_container_width=True):
                        if nuevo_tag and nuevo_tag.strip():
                            t_clean = nuevo_tag.strip()
                            insert_equipo_completo(
                                t_clean, nuevo_tipo, c_pic_lat, c_pic_lon, nuevo_sust,
                                nuevo_inv, nuevo_pres, nuevo_temp, nuevo_orif, 1.5,
                                nuevo_val, 8.0, nuevo_imp
                            )
                            st.session_state.coordenadas_picadas = None
                            st.success(f"✅ ¡Equipo '{t_clean}' ({nuevo_tipo}) registrado exitosamente!")
                            st.rerun()
                        else:
                            st.error("⚠️ Debe ingresar un TAG identificador para el equipo.")

    # Sección de CRUD y Meteorología de Planta en Tab 1
    st.divider()
    with st.expander("📋 Inventario General de Activos de Planta (SQLite)", expanded=True):
        st.dataframe(df_equipos, use_container_width=True)

        c_crud1, c_crud2 = st.columns(2)
        with c_crud1:
            st.markdown("##### ✏️ Modificar Activo Existente")
            if not df_equipos.empty:
                tag_mod = st.selectbox("Seleccionar Activo:", df_equipos['tag'].tolist(), key="sb_mod_tab1")
                row_mod = df_equipos[df_equipos['tag'] == tag_mod].iloc[0]
                with st.form("form_mod_tab1"):
                    tipo_m_idx = TIPOS_EQUIPO_DISPONIBLES.index(row_mod['tipo_equipo']) if row_mod['tipo_equipo'] in TIPOS_EQUIPO_DISPONIBLES else 0
                    tipo_m = st.selectbox("Tipo de Activo:", TIPOS_EQUIPO_DISPONIBLES, index=tipo_m_idx, key="mod_tipo_tab1")

                    lista_sust_mod = list(SUSTANCIAS_DB.keys())
                    sust_idx = lista_sust_mod.index(row_mod['sustancia']) if row_mod['sustancia'] in lista_sust_mod else 0
                    sust_m = st.selectbox("Sustancia:", lista_sust_mod, index=sust_idx, key="mod_sust_tab1")

                    inv_m = st.number_input("Inventario (kg):", value=float(row_mod['inventario_kg']), min_value=10.0, key="mod_inv_tab1")
                    pres_m = st.number_input("Presión (bar):", value=float(row_mod['presion_bar']), min_value=0.5, key="mod_pres_tab1")
                    temp_m = st.number_input("Temperatura (°C):", value=float(row_mod['temperatura_c']), key="mod_temp_tab1")
                    orif_m = st.number_input("Diámetro Orificio (mm):", value=float(row_mod['diametro_orificio_mm']), min_value=0.5, key="mod_orif_tab1")
                    alt_m = st.number_input("Altura Fuga (m):", value=float(row_mod.get('altura_fuga_m', 1.5)), key="mod_alt_tab1")
                    val_m = st.number_input("Valor Reposición (USD):", value=float(row_mod['valor_reposicion_usd']), key="mod_val_tab1")
                    lead_m = st.number_input("Lead Time (meses):", value=float(row_mod['lead_time_meses']), key="mod_lead_tab1")
                    imp_m = st.number_input("Impacto Diario Parada (USD):", value=float(row_mod['impacto_diario_usd']), key="mod_imp_tab1")

                    if st.form_submit_button("💾 Guardar Cambios en Activo", use_container_width=True):
                        update_equipo_detalles(tag_mod, tipo_m, sust_m, inv_m, pres_m, temp_m, orif_m, alt_m, val_m, lead_m, imp_m)
                        st.success(f"Activo {tag_mod} actualizado exitosamente.")
                        st.rerun()

                if st.button(f"🗑️ Eliminar Activo {tag_mod}", key="btn_del_tab1", type="secondary"):
                    delete_equipo(tag_mod)
                    st.warning(f"Activo {tag_mod} eliminado.")
                    st.rerun()

        with c_crud2:
            st.markdown("##### ➕ Registrar Nuevo Activo (Coordenadas Manuales)")
            coord_def = st.session_state.get("coordenadas_picadas") or [10.315000, -75.487700]
            with st.form("form_manual_tab1"):
                tag_man = st.text_input("TAG Identificador:", placeholder="ej. 44-H-1, 44-C-02", key="man_tag_tab1")
                tipo_man = st.selectbox("Tipo de Activo:", TIPOS_EQUIPO_DISPONIBLES, key="man_tipo_tab1")
                cm_l1, cm_l2 = st.columns(2)
                with cm_l1:
                    lat_man = st.number_input("Latitud WGS84:", value=float(coord_def[0]), format="%.6f", key="man_lat_tab1")
                with cm_l2:
                    lon_man = st.number_input("Longitud WGS84:", value=float(coord_def[1]), format="%.6f", key="man_lon_tab1")
                sust_man = st.selectbox("Sustancia:", list(SUSTANCIAS_DB.keys()), key="man_sust_tab1")
                inv_man = st.number_input("Inventario (kg):", value=15000.0, min_value=10.0, key="man_inv_tab1")
                pres_man = st.number_input("Presión (bar):", value=18.0, key="man_pres_tab1")
                temp_man = st.number_input("Temperatura (°C):", value=45.0, key="man_temp_tab1")
                orif_man = st.number_input("Diámetro Orificio (mm):", value=25.4, key="man_orif_tab1")
                val_man = st.number_input("Valor Reposición (USD):", value=850000.0, key="man_val_tab1")
                lead_man = st.number_input("Lead Time (meses):", value=8.0, key="man_lead_tab1")
                imp_man = st.number_input("Impacto Diario Parada (USD):", value=40000.0, key="man_imp_tab1")

                if st.form_submit_button("➕ Crear Activo", use_container_width=True):
                    if tag_man.strip():
                        insert_equipo_completo(tag_man.strip(), tipo_man, lat_man, lon_man, sust_man, inv_man, pres_man, temp_man, orif_man, 1.5, val_man, lead_man, imp_man)
                        st.success(f"Activo {tag_man.strip()} creado exitosamente.")
                        st.rerun()
                    else:
                        st.error("El TAG no puede estar vacío.")

    with st.expander("🌤️ Meteorología Base de Planta", expanded=False):
        with st.form("form_meteo_tab1"):
            ca1, ca2, ca3, ca4 = st.columns(4)
            with ca1:
                t_amb_m = st.number_input("Temp. Ambiente (°C):", value=float(condiciones.get('temperatura_ambiente_c', 32.0)), key="mb_t")
            with ca2:
                h_rel_m = st.number_input("Humedad Relativa (%):", value=float(condiciones.get('humedad_relativa_pct', 78.0)), key="mb_h")
            with ca3:
                v_vw_m = st.number_input("Velocidad Viento (m/s):", value=float(condiciones.get('velocidad_viento_ms', 4.5)), key="mb_v")
            with ca4:
                idx_c = ["A", "B", "C", "D", "E", "F"].index(condiciones.get('clase_estabilidad', 'D')) if condiciones.get('clase_estabilidad', 'D') in ["A", "B", "C", "D", "E", "F"] else 3
                clase_m = st.selectbox("Clase Estabilidad Pasquill:", ["A", "B", "C", "D", "E", "F"], index=idx_c, key="mb_c")

            if st.form_submit_button("💾 Guardar Meteorología Base"):
                update_condiciones(t_amb_m, h_rel_m, v_vw_m, 45.0, clase_m)
                st.success("Meteorología actualizada correctamente.")
                st.rerun()


# ==============================================================================
# TAB 2: SIMULACIÓN DE ESCENARIOS QRA & RADIOS DE CONSECUENCIA
# ==============================================================================
with tab_consecuencias:
    col_map, col_ctrl = st.columns([2.55, 1.45])

    with col_ctrl:
        st.subheader("🎯 Escenario & Parámetros de Fuga")

        # 1. Modo de Selección del Punto de Fuga
        modo_fuga = st.radio(
            "Origen de la Pérdida de Contención:",
            ["🏭 Activo del Plot Plan", "📍 Coordenadas Personalizadas"],
            index=0 if st.session_state.modo_origen_fuga == "🏭 Activo del Plot Plan" else 1,
            horizontal=True,
            key="radio_modo_fuga"
        )
        if modo_fuga != st.session_state.modo_origen_fuga:
            st.session_state.modo_origen_fuga = modo_fuga
            st.rerun()

        # Si es Activo del Plot Plan:
        if st.session_state.modo_origen_fuga == "🏭 Activo del Plot Plan" and not df_equipos.empty:
            c_sel_act, c_btn_rec = st.columns([2.2, 1.0])
            with c_sel_act:
                idx_act = tags_lista.index(st.session_state.tag_origen_fuga) if st.session_state.tag_origen_fuga in tags_lista else 0
                sel_act = st.selectbox(
                    "Equipo Asociado al Plot Plan:",
                    tags_lista,
                    index=idx_act,
                    help="Seleccione el activo de la planta donde se localiza la fuga primaria.",
                    key="sb_act_fuga"
                )
                if sel_act != st.session_state.tag_origen_fuga:
                    st.session_state.tag_origen_fuga = sel_act
                    row_act = df_equipos[df_equipos['tag'] == sel_act].iloc[0]
                    st.session_state.fuga_latitud = float(row_act['latitud'])
                    st.session_state.fuga_longitud = float(row_act['longitud'])
                    st.session_state.fuga_sustancia = str(row_act.get('sustancia', 'GLP / Propano'))
                    st.session_state.fuga_presion_bar = float(row_act.get('presion_bar', 18.0))
                    st.session_state.fuga_temp_c = float(row_act.get('temperatura_c', 45.0))
                    st.session_state.fuga_inventario_kg = float(row_act.get('inventario_kg', 15000.0))
                    st.rerun()
            with c_btn_rec:
                if st.button("🔄 Recargar", help="Recarga las coordenadas y parámetros originales del activo"):
                    row_act = df_equipos[df_equipos['tag'] == st.session_state.tag_origen_fuga].iloc[0]
                    st.session_state.fuga_latitud = float(row_act['latitud'])
                    st.session_state.fuga_longitud = float(row_act['longitud'])
                    st.session_state.fuga_sustancia = str(row_act.get('sustancia', 'GLP / Propano'))
                    st.session_state.fuga_presion_bar = float(row_act.get('presion_bar', 18.0))
                    st.session_state.fuga_temp_c = float(row_act.get('temperatura_c', 45.0))
                    st.session_state.fuga_inventario_kg = float(row_act.get('inventario_kg', 15000.0))
                    st.rerun()
        else:
            tag_cust = st.text_input(
                "Identificador / TAG del Escenario:",
                value=st.session_state.fuga_custom_tag,
                help="Nombre descriptivo para la fuga en este punto de la planta.",
                key="ti_custom_tag"
            )
            if tag_cust != st.session_state.fuga_custom_tag:
                st.session_state.fuga_custom_tag = tag_cust
                st.rerun()

        # 2. Coordenadas de la Fuga (Latitud y Longitud WGS84)
        c_lat, c_lon = st.columns(2)
        with c_lat:
            inp_lat = st.number_input("Latitud (° N):", value=float(st.session_state.fuga_latitud), format="%.6f", step=0.00005, key="inp_fuga_lat")
            if inp_lat != st.session_state.fuga_latitud:
                st.session_state.fuga_latitud = inp_lat
                st.rerun()
        with c_lon:
            inp_lon = st.number_input("Longitud (° W):", value=float(st.session_state.fuga_longitud), format="%.6f", step=0.00005, key="inp_fuga_lon")
            if inp_lon != st.session_state.fuga_longitud:
                st.session_state.fuga_longitud = inp_lon
                st.rerun()

        # 3. Sustancia Peligrosa
        lista_sust = list(SUSTANCIAS_DB.keys())
        idx_sust = lista_sust.index(st.session_state.fuga_sustancia) if st.session_state.fuga_sustancia in lista_sust else 0
        sel_sust = st.selectbox(
            "Sustancia Química Peligrosa:",
            lista_sust,
            index=idx_sust,
            help="Sustancia inflamable involucrada en la pérdida de contención.",
            key="sb_sust_fuga"
        )
        if sel_sust != st.session_state.fuga_sustancia:
            st.session_state.fuga_sustancia = sel_sust
            st.rerun()

        # 4. Diámetro Equivalente de Fuga
        c_d1, c_d2 = st.columns([1.6, 1.0])
        with c_d1:
            lista_presets = list(MAPA_PRESETS_DIAMETRO.keys())
            idx_pres = lista_presets.index(st.session_state.fuga_diametro_modo) if st.session_state.fuga_diametro_modo in lista_presets else 1
            sel_diam_modo = st.selectbox(
                "Diámetro Equivalente (deq):",
                lista_presets,
                index=idx_pres,
                help="Diámetro del orificio de fuga según categorías API 581 o entrada personalizada en mm.",
                key="sb_diam_modo"
            )
            if sel_diam_modo != st.session_state.fuga_diametro_modo:
                st.session_state.fuga_diametro_modo = sel_diam_modo
                val_preset = MAPA_PRESETS_DIAMETRO[sel_diam_modo]
                if val_preset is not None:
                    st.session_state.fuga_diametro_mm = val_preset
                st.rerun()
        with c_d2:
            if MAPA_PRESETS_DIAMETRO.get(st.session_state.fuga_diametro_modo) is None:
                inp_d_mm = st.number_input("Valor en mm:", min_value=0.5, max_value=2000.0, value=float(st.session_state.fuga_diametro_mm), step=1.0, key="inp_custom_d_mm")
                if inp_d_mm != st.session_state.fuga_diametro_mm:
                    st.session_state.fuga_diametro_mm = inp_d_mm
                    st.rerun()
            else:
                st.metric("Orificio", f"{st.session_state.fuga_diametro_mm:.1f} mm", f"{st.session_state.fuga_diametro_mm/25.4:.2f}\"")

        # 5. Parámetros de Operación de Proceso
        with st.expander("⚙️ Parámetros de Operación de Proceso", expanded=False):
            cp1, cp2, cp3 = st.columns(3)
            with cp1:
                p_inp = st.number_input("Presión (bar):", min_value=0.5, max_value=250.0, value=float(st.session_state.fuga_presion_bar), step=1.0, key="inp_proc_pres")
                if p_inp != st.session_state.fuga_presion_bar:
                    st.session_state.fuga_presion_bar = p_inp
                    st.rerun()
            with cp2:
                t_proc = st.number_input("Temp. (°C):", min_value=-196.0, max_value=600.0, value=float(st.session_state.fuga_temp_c), step=5.0, key="inp_proc_temp")
                if t_proc != st.session_state.fuga_temp_c:
                    st.session_state.fuga_temp_c = t_proc
                    st.rerun()
            with cp3:
                inv_inp = st.number_input("Inventario (kg):", min_value=10.0, max_value=10000000.0, value=float(st.session_state.fuga_inventario_kg), step=1000.0, key="inp_proc_inv")
                if inv_inp != st.session_state.fuga_inventario_kg:
                    st.session_state.fuga_inventario_kg = inv_inp
                    st.rerun()

        # 6. Condiciones Ambientales & Meteorología
        with st.expander("🌤️ Condiciones Ambientales & Meteorología", expanded=False):
            cm1, cm2 = st.columns(2)
            with cm1:
                t_amb_inp = st.number_input("Temp. Ambiente (°C):", value=float(st.session_state.temperatura_ambiente_c), step=1.0, key="inp_meteo_tamb")
                if t_amb_inp != st.session_state.temperatura_ambiente_c:
                    st.session_state.temperatura_ambiente_c = t_amb_inp
                    st.rerun()
                v_w_inp = st.number_input("Velocidad Viento (m/s):", min_value=0.1, max_value=30.0, value=float(st.session_state.velocidad_viento_ms), step=0.5, key="inp_meteo_vw")
                if v_w_inp != st.session_state.velocidad_viento_ms:
                    st.session_state.velocidad_viento_ms = v_w_inp
                    st.rerun()
            with cm2:
                h_rel_inp = st.number_input("Humedad Relativa (%):", min_value=10.0, max_value=100.0, value=float(st.session_state.humedad_relativa_pct), step=5.0, key="inp_meteo_hrel")
                if h_rel_inp != st.session_state.humedad_relativa_pct:
                    st.session_state.humedad_relativa_pct = h_rel_inp
                    st.rerun()
                opc_est = ["A (Muy Inestable)", "B (Inestable)", "C (Lig. Inestable)", "D (Neutral)", "E (Lig. Estable)", "F (Estable)"]
                idx_est = 3
                for i_e, o_e in enumerate(opc_est):
                    if o_e.startswith(st.session_state.clase_estabilidad):
                        idx_est = i_e
                        break
                clase_sel = st.selectbox("Estabilidad Pasquill:", opc_est, index=idx_est, key="sb_meteo_clase")
                letra_clase = clase_sel.split(' ')[0]
                if letra_clase != st.session_state.clase_estabilidad:
                    st.session_state.clase_estabilidad = letra_clase
                    st.rerun()

        # 7. Nivel de Congestión & Confinamiento
        lista_cong = list(NIVELES_CONGESTION.keys())
        idx_cong = lista_cong.index(st.session_state.nivel_congestion) if st.session_state.nivel_congestion in lista_cong else 1
        sel_cong = st.selectbox(
            "Nivel de Congestión & Confinamiento (VCE / Explosión):",
            lista_cong,
            index=idx_cong,
            help="Define la severidad del confinamiento y densidad de obstáculos que acelera el frente de llama y determina el rendimiento de sobrepresión.",
            key="sb_nivel_cong"
        )
        if sel_cong != st.session_state.nivel_congestion:
            st.session_state.nivel_congestion = sel_cong
            st.rerun()

        # 8. Dinámica de Descarga y Fenómeno Físico
        t_input = st.slider(
            "⏱️ Tiempo de Descarga (minutos):",
            0.5, 30.0, float(st.session_state.tiempo_fuga_min), 0.5,
            help="Duración del evento de fuga antes del aislamiento o vaciado total."
        )
        if t_input != st.session_state.tiempo_fuga_min:
            st.session_state.tiempo_fuga_min = t_input
            st.rerun()

        fenom_sel = st.radio(
            "Fenómeno Físico a Modelar:",
            ["Radiación Térmica (Jet/Pool Fire)", "Sobrepresión VCE (Explosión)", "Dispersión Inflamable (LFL)"],
            index=0 if "Radiación" in st.session_state.fenomeno_activo else (1 if "Sobrepresión" in st.session_state.fenomeno_activo else 2)
        )
        if fenom_sel != st.session_state.fenomeno_activo:
            st.session_state.fenomeno_activo = fenom_sel
            st.rerun()

        st.markdown("##### 📊 Parámetros de Descarga API 581:")
        k1, k2 = st.columns(2)
        with k1:
            st.metric("Tasa de Liberación", f"{dinamica_fuga['tasa_kg_s']:.2f} kg/s", f"{dinamica_fuga['tasa_kg_h']:,.0f} kg/h")
        with k2:
            st.metric("Masa Total Liberada", f"{dinamica_fuga['masa_liberada_kg']:,.0f} kg", f"{dinamica_fuga['pct_inventario']:.1f}% inventario")

        if dinamica_fuga['tiempo_config_min'] >= dinamica_fuga['tiempo_vaciado_min']:
            st.warning(f"⚠️ Activo vaciado por completo en {dinamica_fuga['tiempo_vaciado_min']:.1f} min.")

        st.divider()
        st.markdown("##### 📏 Radios Físicos de Afectación:")
        if datos_consecuencia.get("no_creible_vce"):
            st.warning(f"⚠️ **{datos_consecuencia.get('razon_no_creible')}**")
        if datos_consecuencia.get("no_creible_dispersion"):
            st.warning(f"⚠️ **{datos_consecuencia.get('razon_no_dispersion')}**")
        for an in datos_consecuencia["anillos"]:
            ref_info = f" <small style='color:#777;'>[{an.get('probit_ref', '')}]</small>" if an.get('probit_ref') else ""
            st.markdown(
                f"<span style='color:{an['color']}; font-weight:bold;'>● {an['nombre']}:</span> `{an['radio']} m`{ref_info}",
                unsafe_allow_html=True
            )

        # Control interactivo de Isoriesgo QRA
        mostrar_iso = st.checkbox(
            "🎯 Superponer Curvas de Isoriesgo QRA (10⁻⁵, 10⁻⁶, 10⁻⁷ /año)",
            value=st.session_state.get('mostrar_isoriesgo_qra', True),
            help="Genera y proyecta los contornos direccionales de riesgo individual anual ponderados por la rosa de los vientos (Meteoblue), frecuencias BEVI v4.2 y probabilidades de ignición Purple Book.",
            key="chk_mostrar_isoriesgo"
        )
        if mostrar_iso != st.session_state.get('mostrar_isoriesgo_qra', True):
            st.session_state.mostrar_isoriesgo_qra = mostrar_iso
            st.rerun()

        if datos_qra_completo and datos_qra_completo.get("status") == "success":
            with st.expander("📊 Resumen QRA (BEVI / Purple / Meteoblue)", expanded=False):
                bevi_f = datos_qra_completo['frecuencias_bevi']
                purp_f = datos_qra_completo['probabilidades_purple_book']
                rv_f = datos_qra_completo['rosa_vientos']
                st.markdown(f"""
                - **Frecuencia BEVI v4.2 ($f_{{LOC}}$):** `{bevi_f['frecuencia_escenario_yr']:.2e} /año`  
                  *({bevi_f.get('escenario_seleccionado', '')})*
                - **Probabilidad Ignición Purple Book ($P_{{ign}}$):** `{purp_f['probabilidad_ignicion_total']*100:.1f}%`  
                  *(Directa: {purp_f['p_direct']*100:.1f}%, Retardada: {purp_f['p_delayed']*100:.1f}%)*
                - **Viento Predominante Meteoblue:** `{rv_f['sector_predominante']}`  
                  *({rv_f['frecuencias_pct'].get(rv_f['sector_predominante'], 0):.1f}% a {rv_f['velocidad_media_global_ms']} m/s)*
                - **Frecuencia Evento Iniciador ($F_{{ev}}$):** `{datos_qra_completo['frecuencia_evento_iniciador_yr']:.2e} /año`
                """)

        # Resumen de equipos alcanzados
        st.divider()
        st.subheader("📋 Receptores Alcanzados (Efecto Dominó)")
        if lista_afectados:
            alcanzo_horno = any('44-h' in str(x.get('TAG Receptor', '')).lower() or 'horno' in str(x.get('Tipo de Activo', '')).lower() or 'caldera' in str(x.get('Tipo de Activo', '')).lower() for x in lista_afectados)
            if alcanzo_horno:
                st.error("🚨 **ALERTA CRÍTICA DOMINÓ: ¡El Horno 44-H-1 / Caldera fue alcanzado por la envolvente del escenario!** Al ser una fuente activa continua de ignición a llama abierta (T > 800°C), se desencadena ignición inmediata forzada (P=100%), Flashback hacia la fuga y alto riesgo de rotura de serpentines de proceso a 340°C.")
            else:
                st.error(f"⚠️ **{len(lista_afectados)} equipos vulnerables** alcanzados:")
            
            df_resumen = pd.DataFrame(lista_afectados)
            cols_res = [
                'TAG Receptor', 'Distancia (m)', 'Carga Incidente', 'Daño Estimado (% PML)',
                'Tiempo Reparación Estimado', 'Pérdida PML Estimada (USD)',
                'Lucro Cesante Estimado (USD)', 'Impacto Financiero Total (USD)', 'Escalamiento Secundario'
            ]
            cols_res_existentes = [c for c in cols_res if c in df_resumen.columns]
            formato_res = {'Distancia (m)': '{:.1f}'}
            if 'Pérdida PML Estimada (USD)' in cols_res_existentes:
                formato_res['Pérdida PML Estimada (USD)'] = '${:,.0f}'
            if 'Lucro Cesante Estimado (USD)' in cols_res_existentes:
                formato_res['Lucro Cesante Estimado (USD)'] = '${:,.0f}'
            if 'Impacto Financiero Total (USD)' in cols_res_existentes:
                formato_res['Impacto Financiero Total (USD)'] = '${:,.0f}'
            st.dataframe(df_resumen[cols_res_existentes].style.format(formato_res), height=230, use_container_width=True)
        else:
            st.success("✅ Ningún equipo vecino dentro de los radios modelados.")

    # ---------------- RENDERIZADO DEL MAPA EN FOLIUM (TAB 2) ----------------
    with col_map:
        c_map_hdr1, c_map_hdr2 = st.columns([2.5, 1.2])
        with c_map_hdr1:
            sel_base_map = st.radio(
                "Vista Base del Terreno:",
                ["🛰️ Satelital Esri (Alta Resolución)", "🗺️ Mapa Callejero (OpenStreetMap)"],
                index=0 if "Satelital" in st.session_state.tipo_mapa_base else 1,
                horizontal=True,
                key="radio_capa_base_tab2"
            )
            if sel_base_map != st.session_state.tipo_mapa_base:
                st.session_state.tipo_mapa_base = sel_base_map
                st.rerun()
        with c_map_hdr2:
            if st.session_state.plotplan_data is not None:
                st.caption(f"📐 Bounds: `{st.session_state.plotplan_data['bounds'][0][0]:.4f}, {st.session_state.plotplan_data['bounds'][0][1]:.4f}`")

        # Inicializar mapa con tiles=None para control persistente
        m = folium.Map(
            location=st.session_state.map_center,
            zoom_start=st.session_state.map_zoom,
            max_zoom=23,
            control_scale=True,
            tiles=None
        )

        es_satelital = "Satelital" in st.session_state.tipo_mapa_base

        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            attr='Esri Satelital High-Res',
            name='Ortofoto Satelital Esri',
            max_zoom=23,
            overlay=False,
            control=True,
            show=es_satelital
        ).add_to(m)

        folium.TileLayer(
            tiles='OpenStreetMap',
            name='Mapa Callejero OSM',
            max_zoom=20,
            overlay=False,
            control=True,
            show=not es_satelital
        ).add_to(m)

        # Superposición del Plot Plan optimizado en memoria
        if st.session_state.plotplan_data is not None:
            p_data = st.session_state.plotplan_data
            folium.raster_layers.ImageOverlay(
                image=p_data["data_url"],
                bounds=p_data["bounds"],
                opacity=st.session_state.opacidad_plano,
                name="Plot Plan Georreferenciado",
                interactive=False
            ).add_to(m)

        # Capa de contornos de consecuencia (anillos concéntricos)
        if eq_emisor is not None:
            lat_fuga = float(eq_emisor['latitud'])
            lon_fuga = float(eq_emisor['longitud'])

            for an in reversed(datos_consecuencia["anillos"]):
                if an['radio'] > 0.0:
                    folium.Circle(
                        location=[lat_fuga, lon_fuga],
                        radius=an['radio'],
                        color=an['color'],
                        weight=2.5,
                        fill=True,
                        fill_opacity=0.22,
                        tooltip=f"<b>{an['nombre']}</b><br>Radio: {an['radio']} m<br>{an.get('probit_ref', '')}"
                    ).add_to(m)

            # Contornos de Isoriesgo QRA direccionales (10^-5, 10^-6, 10^-7 /año)
            if st.session_state.get('mostrar_isoriesgo_qra', True) and datos_qra_completo and "contornos_isoriesgo" in datos_qra_completo:
                for k_iso, info_iso in reversed(list(datos_qra_completo["contornos_isoriesgo"].items())):
                    coords_poly = info_iso["poligono_coords"]
                    if len(coords_poly) >= 3:
                        folium.Polygon(
                            locations=coords_poly,
                            color=info_iso["color"],
                            weight=2.4,
                            dash_array="6, 6",
                            fill=True,
                            fill_color=info_iso["color"],
                            fill_opacity=0.14,
                            tooltip=f"<b>🎯 {info_iso['nombre']}</b><br>Radio Máximo: {info_iso['radio_maximo_m']} m<br>Radio Medio: {info_iso['radio_medio_m']} m"
                        ).add_to(m)

            # Marcador del activo o punto emisor de fuga
            folium.Marker(
                location=[lat_fuga, lon_fuga],
                tooltip=f"🚨 ORIGEN DE FUGA: {eq_emisor['tag']} ({eq_emisor['tipo_equipo']})<br>Descarga: {dinamica_fuga['tasa_kg_s']:.2f} kg/s | {eq_emisor['sustancia']}",
                popup=f"""<b>🚨 ORIGEN DE FUGA: {eq_emisor['tag']}</b><br>
                <b>Tipo:</b> {eq_emisor['tipo_equipo']}<br>
                <b>Coordenadas:</b> {lat_fuga:.6f}, {lon_fuga:.6f}<br>
                <b>Sustancia:</b> {eq_emisor['sustancia']}<br>
                <b>Orificio Fuga:</b> {eq_emisor['diametro_orificio_mm']:.1f} mm ({eq_emisor['diametro_orificio_mm']/25.4:.2f}\")<br>
                <b>Tasa de Descarga:</b> {dinamica_fuga['tasa_kg_s']:.2f} kg/s ({dinamica_fuga['tasa_kg_h']:,.0f} kg/h)<br>
                <b>Masa Liberada:</b> {dinamica_fuga['masa_liberada_kg']:,.0f} kg ({dinamica_fuga['pct_inventario']:.1f}%)<br>
                <b>Presión Operación:</b> {eq_emisor['presion_bar']} bar<br>
                <b>Congestión:</b> {st.session_state.nivel_congestion.split(' ')[0]}<br>
                <b>Fenómeno:</b> {st.session_state.fenomeno_activo}""",
                icon=folium.Icon(color="darkred", icon="fire", prefix="fa")
            ).add_to(m)

        # Marcadores de equipos receptores y vectores de propagación dominó
        mapa_afectados_dict = {x['TAG Receptor']: x for x in lista_afectados}

        for _, row in df_equipos.iterrows():
            tag_eq = str(row['tag']).strip()
            if eq_emisor is not None and tag_eq == eq_emisor['tag']:
                continue

            lat_rec = float(row['latitud'])
            lon_rec = float(row['longitud'])
            es_afectado = tag_eq in mapa_afectados_dict

            if es_afectado:
                info_af = mapa_afectados_dict[tag_eq]
                pf = info_af['Probabilidad Falla Pf (%)']
                color_icon = "red" if pf >= 50.0 else ("orange" if pf >= 15.0 else "lightred")

                # Vector de propagación dominó desde el emisor al receptor
                if eq_emisor is not None:
                    folium.PolyLine(
                        locations=[[lat_fuga, lon_fuga], [lat_rec, lon_rec]],
                        color=info_af['color_vector'],
                        weight=3.5 if pf >= 50.0 else 2.0,
                        dash_array="6, 8",
                        opacity=0.85,
                        tooltip=f"⚡ Vector Dominó: {eq_emisor['tag']} ➔ {tag_eq} | Pf: {pf}%"
                    ).add_to(m)

                folium.Marker(
                    location=[lat_rec, lon_rec],
                    tooltip=f"⚠️ RECEPTOR EN RIESGO: <b>{tag_eq}</b> (PML: {info_af.get('Daño Estimado (% PML)', 'N/A')} | Pf: {pf}%)<br>{info_af['Escalamiento Secundario']}",
                    popup=f"""<b>⚠️ RECEPTOR VULNERABLE: {tag_eq}</b><br>
                    <b>Tipo:</b> {row['tipo_equipo']}<br>
                    <b>Distancia:</b> {info_af['Distancia (m)']} m<br>
                    <b>Carga Incidente:</b> {info_af['Carga Incidente']}<br>
                    <b>Daño Estimado (% PML):</b> {info_af.get('Daño Estimado (% PML)', 'N/A')}<br>
                    <b>Nivel Daño Matriz:</b> {info_af.get('Nivel Daño Matriz', 'N/A')}<br>
                    <b>Tiempo Reparación:</b> {info_af.get('Tiempo Reparación Estimado', 'N/A')}<br>
                    <b>Días Parada Estimados:</b> {info_af.get('Días Parada Estimados', 0):.1f} días<br>
                    <b>Mecanismo CPR 16E:</b> {info_af.get('Mecanismo Físico (CPR 16E)', 'N/A')}<br>
                    <b>Probabilidad Falla (Pf):</b> {pf}%<br>
                    <b>Diagnóstico Dominó:</b> {info_af['Escalamiento Secundario']}<br>
                    <b>Pérdida PML Estimada:</b> ${info_af.get('Pérdida PML Estimada (USD)', 0):,.0f} USD<br>
                    <b>Lucro Cesante Estimado:</b> ${info_af.get('Lucro Cesante Estimado (USD)', 0):,.0f} USD<br>
                    <b>Impacto Financiero Total:</b> ${info_af.get('Impacto Financiero Total (USD)', 0):,.0f} USD<br>
                    <b>Valor Reposición:</b> ${row['valor_reposicion_usd']:,.0f} USD""",
                    icon=folium.Icon(color_icon, prefix="fa")
                ).add_to(m)
            else:
                # Equipo seguro fuera del área de daño (icono temático según tipo)
                estilo_seg = obtener_estilo_icono_equipo(row.get('tipo_equipo', ''))
                folium.Marker(
                    location=[lat_rec, lon_rec],
                    tooltip=f"<b>{tag_eq}</b> ({row['tipo_equipo']}) — Seguro",
                    popup=f"<b>{tag_eq}</b> ({row['tipo_equipo']})<br>Sustancia: {row['sustancia']}<br>Estado: Fuera de Zona Crítica",
                    icon=folium.Icon(color=estilo_seg["color"], icon=estilo_seg["icon"], prefix=estilo_seg["prefix"])
                ).add_to(m)

        folium.LatLngPopup().add_to(m)
        folium.LayerControl(position="topright").add_to(m)
        mapa_int = st_folium(
            m,
            width=930,
            height=670,
            key="mapa_u044_consecuencias",
            returned_objects=["zoom", "center", "last_clicked"]
        )
        if mapa_int:
            if mapa_int.get("zoom") is not None:
                st.session_state.map_zoom = mapa_int["zoom"]
            if mapa_int.get("center") is not None:
                st.session_state.map_center = [mapa_int["center"]["lat"], mapa_int["center"]["lng"]]
            if mapa_int.get("last_clicked") is not None:
                nuevo_clic = [float(mapa_int["last_clicked"]["lat"]), float(mapa_int["last_clicked"]["lng"])]
                prev_clic = st.session_state.get('coordenadas_picadas')
                if prev_clic is None or abs(prev_clic[0] - nuevo_clic[0]) > 1e-7 or abs(prev_clic[1] - nuevo_clic[1]) > 1e-7:
                    st.session_state.coordenadas_picadas = nuevo_clic
                    st.session_state.modo_origen_fuga = "📍 Coordenadas Personalizadas"
                    st.session_state.fuga_latitud = nuevo_clic[0]
                    st.session_state.fuga_longitud = nuevo_clic[1]
                    st.session_state.fuga_custom_tag = f"Fuga-Punto-{nuevo_clic[0]:.4f}"
                    st.rerun()


# ==============================================================================
# TAB 3: DETALLE EFECTO DOMINÓ (OpenSRANE & PROBIT)
# ==============================================================================
with tab_domino:
    st.subheader("💥 Análisis Cuantitativo de Propagación y Efecto Dominó (OpenSRANE)")
    st.caption("Modelación estandarizada según CCPS / Lees' Loss Prevention / Ecuaciones Probit de Cozzani")

    # Panel de control de simulación OpenSRANE
    c_os1, c_os2 = st.columns([3, 1.2])
    with c_os1:
        if HAS_OPENSRANE:
            st.success(f"⚡ **Motor OpenSRANE v{OPENSRANE_VERSION} Activo:** Simulación orientada a objetos de pérdidas de contención, radiación/sobrepresión y efecto dominó.")
        else:
            st.error("⚠️ OpenSRANE no se encuentra disponible. Verifique la instalación en Python 3.12.")

    with c_os2:
        ejecutar_click = st.button("🚀 Ejecutar Red OpenSRANE", type="primary", use_container_width=True)

    sim_data = None
    if HAS_OPENSRANE and eq_emisor is not None:
        sim_data = ejecutar_simulacion_opensrane(
            eq_emisor, df_equipos, condiciones_meteo,
            fenomeno=st.session_state.fenomeno_activo,
            tiempo_fuga_min=st.session_state.tiempo_fuga_min,
            nivel_congestion=st.session_state.nivel_congestion,
            diametro_override_mm=st.session_state.fuga_diametro_mm,
            sustancia_override=st.session_state.fuga_sustancia
        )

    if eq_emisor is not None:
        c_p1, c_p2, c_p3 = st.columns(3)
        with c_p1:
            st.info(f"**Origen de Fuga:** `{eq_emisor['tag']}` ({eq_emisor['tipo_equipo']})\n- **Coordenadas:** `{eq_emisor['latitud']:.6f}, {eq_emisor['longitud']:.6f}`\n- **Sustancia:** {eq_emisor['sustancia']}\n- **Orificio:** {eq_emisor['diametro_orificio_mm']:.1f} mm ({eq_emisor['diametro_orificio_mm']/25.4:.2f}\")")
        with c_p2:
            st.info(f"**Termodinámica de Fuga:**\n- **Tasa:** {dinamica_fuga['tasa_kg_s']:.2f} kg/s ({dinamica_fuga['tasa_kg_h']:,.0f} kg/h)\n- **Masa Descargada:** {dinamica_fuga['masa_liberada_kg']:,.0f} kg\n- **Presión:** {eq_emisor['presion_bar']} bar | **Temp:** {eq_emisor['temperatura_c']} °C")
        with c_p3:
            st.info(f"**Escenario & Entorno:**\n- **Fenómeno:** {st.session_state.fenomeno_activo}\n- **Congestión:** {st.session_state.nivel_congestion.split(' ')[0]}\n- **Viento:** {st.session_state.velocidad_viento_ms} m/s | **Temp:** {st.session_state.temperatura_ambiente_c} °C")

    # Árbol de Objetos OpenSRANE
    if sim_data and sim_data.get("status") == "success":
        arbol = sim_data.get("arbol_objetos", {})
        with st.expander("🌳 Inspeccionar Árbol de Objetos Generado en OpenSRANE (Memoria de Simulación)", expanded=False):
            st.markdown("##### 📍 Site & Condiciones de Entorno:")
            site_info = arbol.get("Site", {})
            c_s1, c_s2, c_s3 = st.columns(3)
            with c_s1:
                st.metric("Temperatura del Sitio", f"{site_info.get('Temperatura_K', 298):.1f} K", f"{site_info.get('Temperatura_K', 298)-273.15:.1f} °C")
            with c_s2:
                st.metric("Presión Atmosférica", f"{site_info.get('Presion_Pa', 101325):,.0f} Pa", "1.013 bar")
            with c_s3:
                st.metric("Límites Planta (X / Y)", f"X: {site_info.get('Limites_X_m', [0, 0])}", f"Y: {site_info.get('Limites_Y_m', [0, 0])}")

            st.markdown("##### 🏭 Unidades de Planta (PlantUnits en OpenSRANE):")
            df_units = pd.DataFrame(arbol.get("PlantUnits", []))
            if not df_units.empty:
                st.dataframe(df_units, use_container_width=True, hide_index=True)

            st.markdown("##### 🧪 Mapeo de Sustancias Peligrosas (Substance DataBank):")
            df_subs = pd.DataFrame(arbol.get("Substances", []))
            if not df_subs.empty:
                st.dataframe(df_subs, use_container_width=True, hide_index=True)

            st.markdown("##### ⚙️ Modelo de Descarga & Efecto Físico Conectado:")
            c_m1, c_m2 = st.columns(2)
            with c_m1:
                st.json(arbol.get("OutFlowModel", {}))
            with c_m2:
                st.json(arbol.get("PhysicalEffect", {}))

    # Matriz de Receptores Evaluados
    receptores_a_mostrar = sim_data.get("receptores_evaluados", []) if (sim_data and sim_data.get("status") == "success") else lista_afectados

    if receptores_a_mostrar:
        st.markdown("### 📊 Matriz de Receptores Vulnerables, % PML & Probabilidad de Falla ($P_f$)")
        df_afectados = pd.DataFrame(receptores_a_mostrar)
        cols_mostrar = [
            'TAG Receptor', 'Tipo de Activo', 'Distancia (m)', 'Carga Incidente',
            'Daño Estimado (% PML)', 'Tiempo Reparación Estimado', 'Días Parada Estimados',
            'Pérdida PML Estimada (USD)', 'Lucro Cesante Estimado (USD)', 'Impacto Financiero Total (USD)',
            'Probit Y', 'Probabilidad Falla Pf (%)', 'Escalamiento Secundario',
            'Acción Técnica Reparación'
        ]
        if 'OpenSRANE_Unit_ID' in df_afectados.columns:
            cols_mostrar.insert(1, 'OpenSRANE_Unit_ID')

        cols_exist = [c for c in cols_mostrar if c in df_afectados.columns]
        fmt_dict = {
            'Distancia (m)': '{:.1f}',
            'Días Parada Estimados': '{:.1f}',
            'Probit Y': '{:.2f}',
            'Probabilidad Falla Pf (%)': '{:.1f}%',
            'Valor Reposición (USD)': '${:,.0f}',
            'Pérdida PML Estimada (USD)': '${:,.0f}',
            'Lucro Cesante Estimado (USD)': '${:,.0f}',
            'Impacto Financiero Total (USD)': '${:,.0f}',
            'Pérdida Ponderada (USD)': '${:,.0f}'
        }
        fmt_dict = {k: v for k, v in fmt_dict.items() if k in cols_exist}

        st.dataframe(
            df_afectados[cols_exist].style.format(fmt_dict),
            use_container_width=True
        )

        perdida_total_expuesta = df_afectados['Valor Reposición (USD)'].sum() if 'Valor Reposición (USD)' in df_afectados.columns else 0
        perdida_pml_total = df_afectados['Pérdida PML Estimada (USD)'].sum() if 'Pérdida PML Estimada (USD)' in df_afectados.columns else 0
        lucro_cesante_total = df_afectados['Lucro Cesante Estimado (USD)'].sum() if 'Lucro Cesante Estimado (USD)' in df_afectados.columns else 0
        impacto_total_acumulado = df_afectados['Impacto Financiero Total (USD)'].sum() if 'Impacto Financiero Total (USD)' in df_afectados.columns else (perdida_pml_total + lucro_cesante_total)

        m_d1, m_d2, m_d3, m_d4 = st.columns(4)
        with m_d1:
            st.warning(f"💰 **Patrimonio Expuesto:** `${perdida_total_expuesta:,.0f} USD`")
        with m_d2:
            st.error(f"📉 **Pérdida PML Física:** `${perdida_pml_total:,.0f} USD`")
        with m_d3:
            st.info(f"⏱️ **Lucro Cesante (BI):** `${lucro_cesante_total:,.0f} USD`")
        with m_d4:
            st.success(f"🚨 **Impacto Total:** `${impacto_total_acumulado:,.0f} USD`")
    else:
        st.success("✅ No se detectan equipos secundarios vulnerables dentro de los radios de daño para este escenario.")

    st.divider()
    st.subheader("📐 Matriz Geodésica de Interdistancias (Metros)")
    st.caption("Calculada mediante proyección Azimutal Equidistante métrica de alta precisión.")
    if len(df_equipos) >= 2:
        df_matriz = calcular_matriz_distancias_geodesica(df_equipos)
        st.dataframe(df_matriz, use_container_width=True)


# ==============================================================================
# TAB 4: ROSA DE LOS VIENTOS (METEOBLUE) & ESTÁNDARES QRA (BEVI / PURPLE / YELLOW / NIST)
# ==============================================================================
with tab_qra_standards:
    st.subheader("🌪️ Rosa de los Vientos (Meteoblue) & Estándares Internacionales QRA")
    st.caption("Integración metodológica unificada: **Meteoblue** (Reanálisis eólico horario 8,760 h/año), **Purple Book PGS 3** (Ignición & Árbol de eventos), **BEVI v4.2** (Frecuencias LOC por equipo y diámetro), **TNO Yellow Book** (Modelos de evaporación y radiación) y **NIST Chemistry WebBook** (Termodinámica pura).")

    if not (datos_qra_completo and datos_qra_completo.get("status") == "success"):
        try:
            datos_qra_completo = calcular_analisis_qra_completo(
                eq_emisor, df_equipos, dinamica_fuga, datos_consecuencia,
                sustancia_nombre=st.session_state.get('fuga_sustancia', 'GLP / Propano'),
                diametro_fuga_mm=st.session_state.get('fuga_diametro_mm', 50.8),
                fenomeno=st.session_state.get('fenomeno_activo', 'Radiación Térmica (Jet/Pool Fire)'),
                tiempo_fuga_min=st.session_state.get('tiempo_fuga_min', 5.0)
            )
        except Exception:
            datos_qra_completo = {"status": "success", "rosa_vientos": obtener_rosa_vientos_meteoblue(10.314855, -75.487632)}

    if datos_qra_completo and datos_qra_completo.get("status") == "success":
        # 1. PANEL METEOBLUE & ROSA DE LOS VIENTOS
        st.markdown("### 1. 🌀 Rosa de los Vientos Climatológica (Meteoblue / Reanálisis Horario)")
        rv = datos_qra_completo.get("rosa_vientos") or obtener_rosa_vientos_meteoblue(10.314855, -75.487632)
        c_rv1, c_rv2 = st.columns([1.6, 1.0])
        with c_rv1:
            fig_rosa = generar_figura_rosa_vientos_plotly(rv)
            st.plotly_chart(fig_rosa, use_container_width=True)
        with c_rv2:
            st.markdown("##### 📍 Parámetros Eólicos en Coordenadas de Fuga:")
            st.markdown(f"**Coordenadas Exactas:** `{rv['lat']:.4f}° N, {rv['lon']:.4f}° W`")
            st.markdown(f"**Registros Horarios Evaluados:** `{rv['total_horas_analizadas']:,} horas` (1 año completo)")

            m1, m2 = st.columns(2)
            with m1:
                st.metric("Rumbo Predominante", f"{rv['sector_predominante']}", f"{rv['frecuencias_pct'].get(rv['sector_predominante'], 0):.1f}% frecuencia")
            with m2:
                st.metric("Velocidad Media Anual", f"{rv['velocidad_media_global_ms']} m/s", f"{rv['velocidad_media_global_ms']*3.6:.1f} km/h")

            st.metric("Horas en Calma (<0.5 m/s)", f"{rv['calmas_pct']:.1f}%", "Dispersión isotrópica")

            st.markdown("##### 🌐 Acceso a Datos Oficiales Meteoblue:")
            st.link_button(
                "🌐 Ver Rosa de Vientos & Pronóstico en Meteoblue",
                rv.get("meteoblue_url", f"https://www.meteoblue.com/es/tiempo/semana/{rv['lat']:.4f}N{abs(rv['lon']):.4f}W"),
                use_container_width=True
            )
            st.link_button(
                "💨 Abrir Mapa de Viento Animado en Vivo (Meteoblue)",
                rv.get("meteoblue_windmap_url", "https://www.meteoblue.com/es/tiempo/mapas"),
                use_container_width=True
            )

        with st.expander("📋 Ver Distribución Porcentual en los 16 Sectores Cardinales (OMM)", expanded=False):
            df_sec = pd.DataFrame(rv.get("sectores_lista", []))
            if not df_sec.empty:
                st.dataframe(
                    df_sec.rename(columns={
                        "sector": "Sector Cardinal",
                        "frecuencia_pct": "Frecuencia Horaria (%)",
                        "velocidad_media_ms": "Velocidad Media (m/s)",
                        "angulo_centro_deg": "Azimut Proveniente (°)",
                        "angulo_downwind_deg": "Azimut Propagación Pluma (°)"
                    }).style.format({
                        "Frecuencia Horaria (%)": "{:.2f}%",
                        "Velocidad Media (m/s)": "{:.2f} m/s",
                        "Azimut Proveniente (°)": "{:.1f}°",
                        "Azimut Propagación Pluma (°)": "{:.1f}°"
                    }),
                    use_container_width=True,
                    hide_index=True
                )

        st.divider()

        # 2. BEVI v4.2 Y PURPLE BOOK (DOS COLUMNAS)
        c_bevi, c_purple = st.columns(2)

        with c_bevi:
            st.markdown("### 2. 📗 BEVI v4.2 (RIVM): Frecuencias LOC")
            st.caption("Fuente: *Handleiding Risicoberekeningen Bevi versie 4.2* (Módulo C). Clasificación por tipo de equipo y diámetro equivalente.")

            bevi_data = datos_qra_completo.get("frecuencias_bevi", {})
            if bevi_data:
                st.info(f"**Categoría BEVI:** {bevi_data.get('categoria_bevi', 'Recipiente')}  \n"
                        f"**Referencia:** `{bevi_data.get('referencia', 'Module C')}`  \n"
                        f"**Subclase:** `{bevi_data.get('subclase', 'Estándar')}`")

                st.markdown(f"##### 🎯 Escenario Seleccionado para el Diámetro ({eq_emisor.get('diametro_orificio_mm', 25.4):.1f} mm):")
                st.markdown(f"**Escenario:** `{bevi_data.get('escenario_seleccionado', 'Falla')}`")
                st.markdown(f"**Frecuencia Anual ($f_{{LOC}}$):** `{bevi_data.get('frecuencia_escenario_yr', 1e-6):.2e} /año`")

                df_sc_bevi = pd.DataFrame([
                    {"Escenario": "Ruptura Catastrófica (Instantaan)", "Frecuencia (/año)": bevi_data.get('frecuencia_ruptura_anual', 5e-7)},
                    {"Escenario": "Fuga Continua 10 mm (Equivalente)", "Frecuencia (/año)": bevi_data.get('frecuencia_fuga_anual', 1e-5)},
                    {"Escenario": "Total Frecuencia Acumulada LOC", "Frecuencia (/año)": bevi_data.get('frecuencia_total_loc_anual', 1.05e-5)}
                ])
                st.dataframe(df_sc_bevi.style.format({"Frecuencia (/año)": "{:.2e}"}), use_container_width=True, hide_index=True)

                with st.expander("📚 Ver Frecuencias BEVI para Tuberías según Diámetro Nominal (DN)", expanded=False):
                    st.markdown(r"""
                    - **$DN < 75\text{ mm}$ ($<3''$):** Ruptura $= 1.0 \times 10^{-6}\text{ /m}\cdot\text{año}$ | Fuga $10\% DN = 5.0 \times 10^{-6}\text{ /m}\cdot\text{año}$
                    - **$75 \le DN \le 150\text{ mm}$ ($3''-6''$):** Ruptura $= 3.0 \times 10^{-7}\text{ /m}\cdot\text{año}$ | Fuga $10\% DN = 2.0 \times 10^{-6}\text{ /m}\cdot\text{año}$
                    - **$DN > 150\text{ mm}$ ($>6''$):** Ruptura $= 1.0 \times 10^{-7}\text{ /m}\cdot\text{año}$ | Fuga $10\% DN = 5.0 \times 10^{-7}\text{ /m}\cdot\text{año}$
                    """)

        with c_purple:
            st.markdown("### 3. 📘 Purple Book (PGS 3): Ignición & Eventos")
            st.caption("Fuente: *PGS 3-1999 / CPR 18E Guidelines for Quantitative Risk Assessment*. Probabilidad directa (Tabla 4.5), retardada (Apéndice 4.A) y bifurcaciones.")

            purp_data = datos_qra_completo.get("probabilidades_purple_book", {})
            if purp_data:
                st.info(f"**Reactividad Sustancia:** `{purp_data.get('reactividad', 'average').upper()}` (Tabla 4.7)  \n"
                        f"**Categoría de Descarga:** `{purp_data.get('categoria_tamanio', 'mediano').upper()}` (Caudal: {dinamica_fuga.get('tasa_kg_s', 0):.2f} kg/s)")

                p1, p2, p3 = st.columns(3)
                with p1:
                    st.metric("Ignición Directa (Pdirect)", f"{purp_data.get('p_direct', 0)*100:.1f}%", "Inmediata (Jet/Pool)")
                with p2:
                    st.metric("Ignición Retardada (Pdel)", f"{purp_data.get('p_delayed', 0)*100:.1f}%", "Fuentes de Planta")
                with p3:
                    st.metric("Ignición Total (Pign)", f"{purp_data.get('probabilidad_ignicion_total', 0)*100:.1f}%", "Pdirect + (1-Pdir)*Pdel")

                st.markdown("##### 🌳 Árbol de Eventos del Purple Book (Secciones 4.7 y 4.8):")
                st.markdown(f"""
                - **Probabilidad de BLEVE (Gas Licuado Instantáneo):** `{purp_data.get('p_bleve', 0.70)*100:.0f}%`
                - **Ignición Retardada de Nube de Vapor:**
                  * **Flash Fire (Llamarada):** `{purp_data.get('p_flash_fire', 0.60)*100:.0f}%` (Sin sobrepresión destructiva)
                  * **Explosión VCE (Vapor Cloud Explosion):** `{purp_data.get('p_vce', 0.40)*100:.0f}%` (Onda de sobrepresión)
                """)

                f_ev = datos_qra_completo.get("frecuencia_evento_iniciador_yr", 0)
                st.warning(f"⚡ **Frecuencia Resultante del Evento Iniciador:** `{f_ev:.2e} /año` ($f_{{LOC}} \\times P_{{ign}}$)")

        st.divider()

        # 3. YELLOW BOOK Y NIST CHEMISTRY WEBBOOK
        st.markdown("### 4. 📙 TNO Yellow Book (CPR 14E) & 🔬 NIST Chemistry WebBook")
        st.caption("Fuente: *TNO Yellow Book (CPR 14E - Methods for Calculation of Physical Effects)* y *NIST Chemistry WebBook (SRD 69)*. Constantes termodinámicas puras y modelos de evaporación y radiación estandarizados.")

        nist_y = datos_qra_completo.get("termodinamica_nist_yellow", {})
        props_sust = nist_y.get("propiedades_sustancia", {})
        ant_c = nist_y.get("constantes_antoine", {})
        evap_y = nist_y.get("evaporacion_charco_yellow_book", {})
        sep_y = nist_y.get("sep_fuego_yellow_book", {})

        c_nist1, c_nist2 = st.columns([1.2, 1.0])
        with c_nist1:
            st.markdown("##### 🧪 Propiedades Termodinámicas Críticas (NIST WebBook):")
            df_nist_tbl = pd.DataFrame([
                {"Parámetro": "Fórmula Química", "Valor": props_sust.get("formula", "N/A"), "Unidad": "-"},
                {"Parámetro": "Número CAS Registry", "Valor": props_sust.get("cas", "N/A"), "Unidad": "-"},
                {"Parámetro": "Peso Molecular (MW)", "Valor": f"{props_sust.get('mw', 0):.2f}", "Unidad": "g/mol"},
                {"Parámetro": "Punto de Ebullición Normal (Tb)", "Valor": f"{props_sust.get('tb_k', 0)-273.15:.1f}", "Unidad": "°C"},
                {"Parámetro": "Temperatura Crítica (Tc)", "Valor": f"{props_sust.get('tc_k', 0)-273.15:.1f}", "Unidad": "°C"},
                {"Parámetro": "Presión Crítica (Pc)", "Valor": f"{props_sust.get('pc_bar', 0):.2f}", "Unidad": "bar"},
                {"Parámetro": "Calor de Vaporización (ΔHvap)", "Valor": f"{props_sust.get('delta_hvap_kj_mol', 0):.2f}", "Unidad": "kJ/mol"},
                {"Parámetro": "Calor Neto de Combustión (ΔHc)", "Valor": f"{props_sust.get('delta_hc_mj_kg', 0):.2f}", "Unidad": "MJ/kg"},
                {"Parámetro": "Límites Inflamabilidad (LFL - UFL)", "Valor": f"{props_sust.get('lfl_pct', 0)}% - {props_sust.get('ufl_pct', 0)}%", "Unidad": "% vol"}
            ])
            st.dataframe(df_nist_tbl, use_container_width=True, hide_index=True)

        with c_nist2:
            st.markdown("##### 📐 Modelos Físicos Estandarizados (TNO Yellow Book):")
            st.markdown(rf"""
            **1. Presión de Vapor de Antoine (NIST):**  
            $\log_{{10}}(P_{{bar}}) = A - \frac{{B}}{{T_{{K}} + C}}$  
            - Constantes: $A = {ant_c.get('A', 0)}$, $B = {ant_c.get('B', 0)}$, $C = {ant_c.get('C', 0)}$
            - **$P_v$ saturada a {dinamica_fuga.get('temperatura_c', 30):.1f}°C:** `{nist_y.get('presion_vapor_antoine_bar', 0):.4f} bar`

            **2. Evaporación de Charco (Yellow Book Cap. 3 - Mackay-Matsugu):**  
            $E = \frac{{k_m \cdot M \cdot P_v \cdot A}}{{R \cdot T}}$ con $k_m = 0.0048 \cdot u^{{0.78}} \cdot d^{{-0.11}} \cdot Sc^{{-0.67}}$
            - Tasa calculada: `{evap_y.get('tasa_evaporacion_kg_s', 0):.2f} kg/s` (`{evap_y.get('tasa_evaporacion_kg_min', 0):,.1f} kg/min`)
            - Coeficiente de transferencia $k_m$: `{evap_y.get('coef_transferencia_km_m_s', 0):.4f} m/s`

            **3. Poder Emisivo Superficial SEP (Yellow Book Cap. 6):**  
            $SEP_{{act}} = SEP_{{max}} \cdot (1 - e^{{-k_\beta \cdot D}})$  
            - $SEP_{{max}} = {sep_y.get('sep_max_kw_m2', 140)} \text{{ kW/m}}^2$ | $k_\beta = {sep_y.get('k_beta', 0.055)}$
            - **$SEP_{{act}}$ fuego 15 m:** `{sep_y.get('sep_act_kw_m2', 0):.1f} kW/m²`
            """)

        st.divider()

        # 4. CONTORNOS DE ISORIESGO Y MATRIZ INDIVIDUAL RISK (IR)
        st.markdown("### 5. 🎯 Evaluación de Riesgo Individual Anual ($IR$) & Contornos de Isoriesgo")
        st.caption("Cálculo del riesgo individual para cada receptor considerando la distancia geodésica, azimut, sector de viento predominante (Meteoblue) y probit de fatalidad (Purple Book).")

        cont_dict = datos_qra_completo.get("contornos_isoriesgo", {})
        if cont_dict:
            st.markdown("##### 🌐 Dimensiones de los Contornos de Isoriesgo Anisotrópicos:")
            c_i1, c_i2, c_i3 = st.columns(3)
            with c_i1:
                info_5 = cont_dict.get("1e-05", {})
                st.metric("Isoriesgo 10⁻⁵ /año (Zona Industrial)", f"Máx: {info_5.get('radio_maximo_m', 0):.1f} m", f"Medio: {info_5.get('radio_medio_m', 0):.1f} m")
            with c_i2:
                info_6 = cont_dict.get("1e-06", {})
                st.metric("Isoriesgo 10⁻⁶ /año (Límite Habitacional)", f"Máx: {info_6.get('radio_maximo_m', 0):.1f} m", f"Medio: {info_6.get('radio_medio_m', 0):.1f} m")
            with c_i3:
                info_7 = cont_dict.get("1e-07", {})
                st.metric("Isoriesgo 10⁻⁷ /año (Amortiguamiento)", f"Máx: {info_7.get('radio_maximo_m', 0):.1f} m", f"Medio: {info_7.get('radio_medio_m', 0):.1f} m")

        receptores_qra = datos_qra_completo.get("receptores_qra", [])
        if receptores_qra:
            st.markdown("##### 📊 Matriz de Riesgo Individual ($IR$) por Receptor:")
            df_rq = pd.DataFrame(receptores_qra)
            st.dataframe(
                df_rq.rename(columns={
                    "tag": "TAG Receptor",
                    "tipo_equipo": "Tipo Activo",
                    "distancia_m": "Distancia (m)",
                    "azimuth_deg": "Azimut (°)",
                    "sector_viento_critico": "Sector Viento Crítico",
                    "frecuencia_viento_pct": "Frec. Viento (%)",
                    "probit_fatalidad_y": "Probit Y",
                    "probabilidad_fatalidad_pf": "Prob. Daño Pf (%)",
                    "ir_formateado": "Riesgo Individual (IR /año)"
                })[[
                    "TAG Receptor", "Tipo Activo", "Distancia (m)", "Azimut (°)",
                    "Sector Viento Crítico", "Frec. Viento (%)", "Probit Y", "Prob. Daño Pf (%)",
                    "Riesgo Individual (IR /año)"
                ]].style.format({
                    "Distancia (m)": "{:.1f}",
                    "Azimut (°)": "{:.1f}°",
                    "Frec. Viento (%)": "{:.2f}%",
                    "Probit Y": "{:.2f}",
                    "Prob. Daño Pf (%)": "{:.2f}%"
                }),
                use_container_width=True,
                hide_index=True
            )
    else:
        st.warning("⚠️ No se pudieron generar los cálculos QRA para el activo seleccionado.")


# ==============================================================================
# TAB 5: PML FINANCIERO & CONTINUIDAD DE NEGOCIO
# ==============================================================================
with tab_financiero:
    st.subheader("💰 Cuantificación Financiera (PML, Daño Físico & Lucro Cesante / Business Interruption)")
    st.caption("Estimación del impacto económico integral: Pérdida Patrimonial ($= \\text{Costo Reposición} \\times \\%\\text{ Daño}$) y Lucro Cesante ($= \\text{Días de Parada} \\times \\text{Impacto Diario}$) conforme a la Matriz de Sobrepresión ($P_s$) y Radiación Térmica ($q$).")

    # ---------------- 1. CONFIGURACIÓN DE COSTOS Y LUCRO CESANTE ENTREGADOS POR EL USUARIO ----------------
    st.markdown("#### 1. 💼 Parámetros Económicos de Activos (Entregados por el Usuario)")
    st.caption("Edite directamente los costos de reposición, lead times y lucro cesante diario de cada equipo. Los valores se almacenan en la base de datos SQLite y se usan en todos los cálculos de PML y efecto dominó.")

    if not df_equipos.empty:
        cols_edit_costos = ['tag', 'tipo_equipo', 'valor_reposicion_usd', 'lead_time_meses', 'impacto_diario_usd']
        cols_existentes_costos = [c for c in cols_edit_costos if c in df_equipos.columns]

        df_costos_edit = st.data_editor(
            df_equipos[cols_existentes_costos],
            column_config={
                "tag": st.column_config.TextColumn("TAG Equipo", disabled=True),
                "tipo_equipo": st.column_config.TextColumn("Tipo de Activo", disabled=True),
                "valor_reposicion_usd": st.column_config.NumberColumn(
                    "Costo Reposición (USD)",
                    help="Costo total de reposición o reconstrucción entregado por el usuario",
                    min_value=0.0,
                    step=25000.0,
                    format="$%d"
                ),
                "lead_time_meses": st.column_config.NumberColumn(
                    "Lead Time (Meses)",
                    help="Tiempo de procura/fabricación y entrega en sitio en caso de reemplazo",
                    min_value=0.5,
                    max_value=48.0,
                    step=0.5,
                    format="%.1f meses"
                ),
                "impacto_diario_usd": st.column_config.NumberColumn(
                    "Lucro Cesante Diario (USD/día)",
                    help="Pérdida diaria por lucro cesante e interrupción de negocio (BI) entregado por el usuario",
                    min_value=0.0,
                    step=5000.0,
                    format="$%d"
                )
            },
            disabled=["tag", "tipo_equipo"],
            hide_index=True,
            use_container_width=True,
            key="editor_costos_equipos_tab5"
        )

        c_btn_c1, c_btn_c2 = st.columns([1.5, 2.5])
        with c_btn_c1:
            if st.button("💾 Guardar Costos y Lucro Cesante en SQLite", key="btn_guardar_costos_tab5", type="primary", use_container_width=True):
                if update_equipos_costos_df(df_costos_edit):
                    st.success("✅ Costos de reposición y lucro cesante diario guardados exitosamente en SQLite.")
                    st.rerun()
                else:
                    st.error("❌ Error al guardar costos en base de datos.")

        st.divider()

        # ---------------- 2. IMPACTO FINANCIERO DEL ESCENARIO MODELADO ACTUAL ----------------
        st.markdown("#### 2. ⚡ Impacto Financiero del Escenario Modelado Actual")
        st.caption("Pérdida calculada para los equipos vulnerables afectados por el evento físico activo (Pérdida Física + Lucro Cesante por Días de Parada).")

        receptores_fin = receptores_a_mostrar if receptores_a_mostrar else lista_afectados
        if receptores_fin:
            df_fin_sc = pd.DataFrame(receptores_fin)
            perdida_fisica_total = df_fin_sc['Pérdida PML Estimada (USD)'].sum() if 'Pérdida PML Estimada (USD)' in df_fin_sc.columns else 0.0
            lucro_total = df_fin_sc['Lucro Cesante Estimado (USD)'].sum() if 'Lucro Cesante Estimado (USD)' in df_fin_sc.columns else 0.0
            impacto_global = df_fin_sc['Impacto Financiero Total (USD)'].sum() if 'Impacto Financiero Total (USD)' in df_fin_sc.columns else (perdida_fisica_total + lucro_total)
            max_dias = df_fin_sc['Días Parada Estimados'].max() if 'Días Parada Estimados' in df_fin_sc.columns else 0.0

            kf1, kf2, kf3, kf4 = st.columns(4)
            with kf1:
                st.error(f"📉 **Pérdida Física (PML):**  \n`${perdida_fisica_total:,.0f} USD`")
            with kf2:
                st.warning(f"⏱️ **Parada Crítica Cuello Botella:**  \n`{max_dias:.1f} días` ({max_dias/30.0:.1f} meses)")
            with kf3:
                st.info(f"💼 **Lucro Cesante Total (BI):**  \n`${lucro_total:,.0f} USD`")
            with kf4:
                st.success(f"🚨 **Impacto Financiero Global:**  \n`${impacto_global:,.0f} USD`")

            cols_detalle_fin = [
                'TAG Receptor', 'Tipo de Activo', 'Carga Incidente', 'Daño Estimado (% PML)',
                'Tiempo Reparación Estimado', 'Días Parada Estimados', 'Pérdida PML Estimada (USD)',
                'Lucro Cesante Estimado (USD)', 'Impacto Financiero Total (USD)', 'Acción Técnica Reparación'
            ]
            cols_fin_exist = [c for c in cols_detalle_fin if c in df_fin_sc.columns]
            fmt_fin = {
                'Días Parada Estimados': '{:.1f}',
                'Pérdida PML Estimada (USD)': '${:,.0f}',
                'Lucro Cesante Estimado (USD)': '${:,.0f}',
                'Impacto Financiero Total (USD)': '${:,.0f}'
            }
            fmt_fin = {k: v for k, v in fmt_fin.items() if k in cols_fin_exist}
            st.dataframe(df_fin_sc[cols_fin_exist].style.format(fmt_fin), use_container_width=True, hide_index=True)
        else:
            st.info("ℹ️ Para este escenario ningún receptor se encuentra dentro de los contornos de daño. A continuación se presenta el perfil global del sitio:")
            df_fin = df_equipos.copy()
            df_fin['dias_parada'] = df_fin['lead_time_meses'] * 30.0
            df_fin['lucro_cesante_usd'] = df_fin['dias_parada'] * df_fin['impacto_diario_usd']
            df_fin['pml_total_usd'] = df_fin['valor_reposicion_usd'] + df_fin['lucro_cesante_usd']

            k1, k2, k3 = st.columns(3)
            with k1:
                st.metric("Pérdida Máxima Posible Total (PML)", f"${df_fin['pml_total_usd'].sum():,.0f} USD")
            with k2:
                st.metric("Reposición Patrimonial Total", f"${df_fin['valor_reposicion_usd'].sum():,.0f} USD")
            with k3:
                mayor = df_fin.loc[df_fin['pml_total_usd'].idxmax()]
                st.metric("Activo de Mayor Riesgo Financiero", f"{mayor['tag']}", f"${mayor['pml_total_usd']:,.0f} USD")

            st.dataframe(
                df_fin[['tag', 'tipo_equipo', 'valor_reposicion_usd', 'lead_time_meses', 'lucro_cesante_usd', 'pml_total_usd']]
                .sort_values(by='pml_total_usd', ascending=False)
                .style.format({
                    'valor_reposicion_usd': '${:,.0f}',
                    'lead_time_meses': '{:.1f} meses',
                    'lucro_cesante_usd': '${:,.0f}',
                    'pml_total_usd': '${:,.0f}'
                }),
                use_container_width=True
            )

        st.divider()

        # ---------------- 3. BASE DE DATOS EDITABLE: MATRIZ DE DAÑO Y TIEMPO DE REPARACIÓN VS PSIG Y KW/M2 ----------------
        st.markdown("#### 3. 🗄️ Matriz de Daño y Tiempo de Reparación vs. Psig & kW/m² (Base de Datos SQLite)")
        st.caption("Cargada automáticamente desde `C:\\backup 2026\\daño de equipos vs tiempo de reparación vs psig y kw_m2.xlsx`. Los datos están persistidos en SQLite para que pueda editarlos, calibrarlos y guardarlos.")

        df_matriz_db = get_matriz_dano_reparacion_df()
        if not df_matriz_db.empty:
            cols_matriz_ver = [
                'categoria_activo', 'tipo_equipo',
                'ps_leve_min_kpa', 'ps_leve_max_kpa', 'q_leve_kw_m2', 'dias_leve_min', 'dias_leve_max', 'tiempo_leve_txt',
                'ps_medio_min_kpa', 'ps_medio_max_kpa', 'q_medio_kw_m2', 'dias_medio_min', 'dias_medio_max', 'tiempo_medio_txt',
                'ps_severo_min_kpa', 'q_severo_kw_m2', 'meses_severo_min', 'meses_severo_max', 'lead_time_severo_txt',
                'factores_variabilidad'
            ]
            cols_matriz_exist = [c for c in cols_matriz_ver if c in df_matriz_db.columns]

            df_matriz_edit = st.data_editor(
                df_matriz_db[cols_matriz_exist],
                column_config={
                    "categoria_activo": st.column_config.TextColumn("Categoría", disabled=True),
                    "tipo_equipo": st.column_config.TextColumn("Tipo de Equipo", disabled=True),
                    "ps_leve_min_kpa": st.column_config.NumberColumn("Ps Leve Mín (kPa)", step=1.0, format="%.1f"),
                    "ps_leve_max_kpa": st.column_config.NumberColumn("Ps Leve Máx (kPa)", step=1.0, format="%.1f"),
                    "q_leve_kw_m2": st.column_config.NumberColumn("q Leve (kW/m²)", step=1.0, format="%.1f"),
                    "dias_leve_min": st.column_config.NumberColumn("Días Leve Mín", step=0.5, format="%.1f"),
                    "dias_leve_max": st.column_config.NumberColumn("Días Leve Máx", step=0.5, format="%.1f"),
                    "tiempo_leve_txt": st.column_config.TextColumn("Tiempo Leve (Texto)"),
                    "ps_medio_min_kpa": st.column_config.NumberColumn("Ps Medio Mín (kPa)", step=1.0, format="%.1f"),
                    "ps_medio_max_kpa": st.column_config.NumberColumn("Ps Medio Máx (kPa)", step=1.0, format="%.1f"),
                    "q_medio_kw_m2": st.column_config.NumberColumn("q Medio (kW/m²)", step=1.0, format="%.1f"),
                    "dias_medio_min": st.column_config.NumberColumn("Días Medio Mín", step=1.0, format="%.0f"),
                    "dias_medio_max": st.column_config.NumberColumn("Días Medio Máx", step=1.0, format="%.0f"),
                    "tiempo_medio_txt": st.column_config.TextColumn("Tiempo Medio (Texto)"),
                    "ps_severo_min_kpa": st.column_config.NumberColumn("Ps Severo Mín (kPa)", step=1.0, format="%.1f"),
                    "q_severo_kw_m2": st.column_config.NumberColumn("q Severo (kW/m²)", step=1.0, format="%.1f"),
                    "meses_severo_min": st.column_config.NumberColumn("Meses Severo Mín", step=0.5, format="%.1f"),
                    "meses_severo_max": st.column_config.NumberColumn("Meses Severo Máx", step=0.5, format="%.1f"),
                    "lead_time_severo_txt": st.column_config.TextColumn("Lead Time Severo (Texto)"),
                    "factores_variabilidad": st.column_config.TextColumn("Factores de Variabilidad BI")
                },
                disabled=["categoria_activo", "tipo_equipo"],
                hide_index=True,
                use_container_width=True,
                key="editor_matriz_dano_tab5"
            )

            col_mb1, col_mb2 = st.columns([1.5, 2.0])
            with col_mb1:
                if st.button("💾 Guardar Cambios en Matriz SQLite", key="btn_save_matriz_tab5", type="primary", use_container_width=True):
                    if update_matriz_dano_reparacion_df(df_matriz_edit):
                        recargar_cache_matriz_dano()
                        st.success("✅ Matriz de daño y reparación guardada exitosamente en la base de datos SQLite.")
                        st.rerun()
                    else:
                        st.error("❌ Error al guardar la matriz en SQLite.")
            with col_mb2:
                if st.button("🔄 Restaurar Valores Predeterminados desde Excel", key="btn_reset_matriz_tab5", use_container_width=True):
                    if reset_matriz_dano_from_excel():
                        recargar_cache_matriz_dano()
                        st.success("✅ Matriz restaurada exitosamente desde el archivo Excel original.")
                        st.rerun()
                    else:
                        st.error("❌ Error al restaurar desde el archivo Excel.")
        else:
            st.warning("⚠️ No se encontraron registros en la tabla matriz_dano_reparacion de SQLite.")
            if st.button("📥 Importar desde Archivo Excel"):
                reset_matriz_dano_from_excel()
                recargar_cache_matriz_dano()
                st.rerun()

        st.divider()
        st.markdown("### 📚 Matrices de Vulnerabilidad & % PML (TNO CPR 16E Green Book & ExTool)")
        st.caption("Criterios internacionales de reaseguro industrial para estimación de Daño Físico y Pérdida Máxima Probable (PML) ante explosiones y radiación térmica.")

        with st.expander("📖 1. Matriz de Vulnerabilidad y % PML vs. Sobrepresión de Explosión (Ps)", expanded=True):
            st.markdown("""
| Sobrepresión $P_s$ | Referencia Empírica y Criterio TNO CPR 16E (*Green Book*) | Anillo ExTool Equivalente | Drums / Separadores (% PML) | Torres de Proceso (% PML) | Hornos a Fuego Directo (% PML) | Tanques Atmosféricos (% PML) | Esferas / Balas GLP (% PML) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **$< 3.5\\text{ kPa}$**<br>($< 0.035\\text{ bar}$ / $< 0.5\\text{ psi}$) | Límite inferior Zona D (rotura esporádica de vidrios estándar $< 1\\text{ kPa}$). | Exterior ($< 1\\text{ psig}$): $0\\%$ daño base. | **0%**<br>Sin afectación mecánica. | **0%**<br>Sin afectación mecánica. | **0% – 5%**<br>Desajuste menor en mirillas y tiro. | **0% – 5%**<br>Sin afectación en envolvente. | **0%**<br>Sin afectación mecánica. |
| **$7 – 10\\text{ kPa}$**<br>($0.07 – 0.10\\text{ bar}$ / $1.0 – 1.5\\text{ psi}$) | • $7\\text{ kPa}$: Colapso del techo de tanques de almacenamiento.<br>• $8-10\\text{ kPa}$: Daño menor en marcos de acero.<br>• $7-14\\text{ kPa}$: Falla de uniones en láminas corrugadas. | Anillo 1 psig ($6.9\\text{ kPa}$): $5\\% - 10\\%$ daño base. | **5%**<br>Abolladuras en aislamiento; descalibración de transmisores. | **10%**<br>Deformación en bandejas de cables, escalas y plataformas. | **20% – 30%**<br>Desalineación de ductos de gases y tiros de chimenea. | **35% – 50%**<br>Colapso de láminas de techo ($7\\text{ kPa}$); daño en sellos flotantes. | **5%**<br>Afectación de piping de instrumentación exterior. |
| **$15 – 20\\text{ kPa}$**<br>($0.15 – 0.20\\text{ bar}$ / $2.2 – 2.9\\text{ psi}$) | • Límite Zona C ($> 17\\text{ kPa}$).<br>• $15-20\\text{ kPa}$: Colapso de muros de bloques de hormigón.<br>• $20\\text{ kPa}$: Colapso de marcos de acero y desplazamiento de bases.<br>• $20-30\\text{ kPa}$: Deformación leve de puentes de tubería (*pipe racks*). | Corona 1 a 2 psig: ExTool interpola $10\\% - 40\\%$. | **10% – 15%**<br>Fisuras en aislamiento rígido; daño en conexiones de purga. | **25% – 35%**<br>Desplazamiento de empaques internos y platos superiores. | **45% – 60%**<br>Fisuración severa del refractario; desalineación de quemadores. | **60% – 75%**<br>Pandeo elástico de pared; agrietamiento de tanques vacíos ($20-30\\text{ kPa}$). | **15% – 20%**<br>Fatiga en pernos de anclaje de patas sin fuga de producto. |
| **$30 – 40\\text{ kPa}$**<br>($0.30 – 0.40\\text{ bar}$ / $4.3 – 5.8\\text{ psi}$) | • Límite Zona B ($> 35\\text{ kPa}$).<br>• $30\\text{ kPa}$: Paneles de naves industriales arrancados.<br>• $35-40\\text{ kPa}$: Desplazamiento de *pipe racks* y fractura de tuberías.<br>• $35-80\\text{ kPa}$: Daño estructural a columnas de fraccionamiento. | Anillo 5 psig ($34\\text{ kPa}$): $80\\% - 100\\%$ daño base en ExTool. | **25% – 40%**<br>Deformación de silletas; daño en juntas bridadas con fugas localizadas. | **50% – 70%**<br>Pandeo local en faldón; desalineación de eje; daño en platos ($35-80\\text{ kPa}$). | **75% – 90%**<br>Colapso de chimenea; deformación de la estructura portante y serpentines. | **85% – 100%**<br>Pandeo plástico (*elephant foot*); desgarro de planchas de fondo y pérdida total. | **35% – 50%**<br>Pandeo en riostras estructurales de patas; descalibración de PSVs. |
| **$50 – 80\\text{ kPa}$**<br>($0.50 – 0.80\\text{ bar}$ / $7.2 – 11.6\\text{ psi}$) | • $40-55\\text{ kPa}$: Colapso total de puentes de tubería.<br>• $50\\text{ kPa}$: Colapso de muros de ladrillo macizo (20-30 cm).<br>• $50-100\\text{ kPa}$: Desplazamiento de tanques cilíndricos y rotura de conexiones. | Núcleo $\\ge 5\\text{ psig}$: $100\\%$ daño uniforme por reaseguro. | **50% – 75%**<br>Desplazamiento de fundaciones; ovalización de casco; desgarro de boquillas. | **80% – 95%**<br>Falla plástica de pernos de anclaje; colapso por flexión; desgarro de líneas mayores. | **100%**<br>Destrucción total de serpentines, refractario y estructura portante. | **100%**<br>Desplazamiento del tanque de su base con desgarro e incendio asociado. | **60% – 80%**<br>Deformación plástica severa de columnas de soporte; rotura en línea de fondo. |
| **$80 – 100\\text{ kPa}$**<br>($0.80 – 1.00\\text{ bar}$ / $11.6 – 14.5\\text{ psi}$) | • Límite Zona A ($> 83\\text{ kPa}$, Destrucción total).<br>• $100\\text{ kPa}$: Colapso de la estructura de soporte de tanques esféricos. | Núcleo $\\ge 5\\text{ psig}$: $100\\%$ daño total. | **80% – 100%**<br>Arrancamiento de anclajes; ruptura de cuerpo por choque; pérdida total. | **100%**<br>Volcamiento o fractura del faldón; colapso completo. | **100%**<br>Destrucción total. | **100%**<br>Destrucción total. | **85% – 100%**<br>Colapso de patas de soporte de la esfera ($100\\text{ kPa}$); caída y BLEVE secundario. |
| **$> 100\\text{ kPa}$**<br>($> 1.0\\text{ bar}$ / $> 14.5\\text{ psi}$) | Destrucción absoluta de infraestructura superficial de planta. | Núcleo $\\ge 5\\text{ psig}$: $100\\%$ daño total. | **100%** | **100%** | **100%** | **100%** | **100%** |
""")

        with st.expander("🔥 2. Matriz de Vulnerabilidad y % PML vs. Radiación Térmica (q)", expanded=True):
            st.markdown("""
| Radiación $q$ (kW/m²) | Criterio de Falla y Mecanismo Físico TNO CPR 16E (*Green Book*) | Drums / Separadores (% PML) | Torres de Proceso (% PML) | Hornos a Fuego Directo (% PML) | Tanques Atmosféricos (% PML) | Tanques Presurizados (Esferas y Balas GLP) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **$< 4.0\\text{ kW/m}^2$** | Umbral seguro; inferior al límite de rotura de vidrio ($4\\text{ kW/m}^2$). Nivel 2 en madera/plásticos ($2\\text{ kW/m}^2$). | **0%**<br>Sin afectación. | **0%**<br>Sin afectación. | **0%**<br>Sin afectación. | **0%**<br>Operación segura. | **0%**<br>Sin afectación. |
| **$4.0 – 8.0\\text{ kW/m}^2$** | **$4\\text{ kW/m}^2$:** Rotura de paneles y visores de vidrio por tensión térmica diferencial ($\\Delta T = 100\\text{ K}$). | **5%**<br>Rotura de visores de nivel óptico; daño en cableado sin canalizar. | **5%**<br>Falla en instrumentos electrónicos exteriores desprotegidos. | **10%**<br>Rotura de mirillas de vidrio ($4\\text{ kW/m}^2$); fallo en fotoceldas de llama. | **10%**<br>Ampollamiento de pintura; evaporación acelerada en venteos. | **5%**<br>Daño en transmisores electrónicos periféricos. |
| **$12.5 – 15.0\\text{ kW/m}^2$** | **$15\\text{ kW/m}^2$:** *Damage Level 1* para madera y plásticos (ignición con llama piloto presente). | **15% – 25%**<br>Apertura intermitente de PSVs; degradación de empaques en bridas. | **20% – 30%**<br>Pérdida de instrumentación local; distorsión en tuberías no aisladas. | **25% – 40%**<br>Daño en cableado del sistema de seguridad de quemadores (BMS). | **35% – 50%**<br>Ignición de vapores en sellos de techo flotante (*rim seal fire*) por fuentes piloto. | **20% – 35%**<br>Activación continua de PSVs; requiere rociado de agua para estabilidad. |
| **$25.0\\text{ kW/m}^2$** | **$25\\text{ kW/m}^2$:** **Damage Level 2 en acero estructural** ($T = 473\\text{ K} / 200^\\circ\\text{C}$). Daño permanente a pinturas, recubrimientos y deformación plástica local. | **40% – 50%**<br>Destrucción de recubrimientos; deformación en silletas sin protección pasiva (PFP). | **45% – 60%**<br>Pandeo diferencial por gradiente térmico; distorsión de faldón sin PFP. | **50% – 65%**<br>Deformación de la envolvente metálica exterior (*casing*); alabeo de compuertas. | **65% – 80%**<br>Deformación de planchas de pared sin enfriar; daño estructural en techo flotante. | **45% – 60%**<br>Calentamiento severo del acero en espacio de vapor; deformación de patas sin PFP. |
| **$35.0\\text{ kW/m}^2$** | **$35\\text{ kW/m}^2$:** Autoignición espontánea de materiales combustibles sin presencia de llama (CPR 16E Tabla 7.1). Incendio generalizado de recintos. | **65% – 80%**<br>Pérdida de estanqueidad en bridas; fluencia en soportes sin PFP; sobrepresión severa. | **70% – 85%**<br>Deformación permanente del faldón; pandeo de columnas; desalineación global. | **75% – 90%**<br>Pandeo de columnas estructurales exteriores; fallo total de sistemas de tiro. | **90% – 100%**<br>Autoignición espontánea de vapores en techos ($35\\text{ kW/m}^2$); colapso de envolvente sin agua. | **75% – 95%**<br>Pérdida crítica de tensión de fluencia en zona de vapor; tiempo hacia BLEVE $< 15\\text{ min}$ sin diluvio. |
| **$100.0\\text{ kW/m}^2$** | **$100\\text{ kW/m}^2$:** **Damage Level 1 en acero estructural** ($T = 773\\text{ K} / 500^\\circ\\text{C}$). Colapso de elementos de carga portantes. Flujo superficial en Pool Fire de GLP. | **100%**<br>Ruptura térmica bajo tensión (*stress rupture*); colapso sobre fundaciones. | **100%**<br>Colapso plástico del faldón por pérdida de resistencia del acero a $500^\\circ\\text{C}$; volcamiento. | **100%**<br>Colapso estructural completo de la estructura y serpentines. | **100%**<br>Colapso completo de chapa, desgarro y quema total del contenido. | **100%**<br>Colapso plástico de patas de soporte; ruptura térmica y BLEVE catastrófico. |
| **$\\ge 190 – 200\\text{ kW/m}^2$** o Envolvente de Llama | Flujo radiativo en superficie de Fireball / BLEVE (CPR 16E Apéndice A) o inmersión en llama (*fire engulfment*). | **100%**<br>Destrucción total instantánea. | **100%**<br>Destrucción estructural completa. | **100%**<br>Destrucción total. | **100%**<br>Destrucción total. | **100%**<br>BLEVE catastrófico instantáneo (bola de fuego y fragmentos). |
""")

        with st.expander("🏭 3. Justificación Técnica de Daños Intermedios (60% – 90% PML) según Criterios del Green Book", expanded=True):
            st.markdown("""
| Unidad / Activo de Refinería | Daño Reportado en Reaseguro (Allrisk / MFL) | Rango de Sobrepresión TNO Green Book ($P_s$) | Mecanismo Físico de Daño (CPR 16E, Cap. 2, Tabla 5) | Justificación Técnica de la Pérdida Intermedia en PML |
| :--- | :--- | :--- | :--- | :--- |
| **East Plant – HF Alkylation** | **100%** ($52.9\\text{ MM}$) | $> 100\\text{ kPa}$ ($> 1.0\\text{ bar}$) | Centro de la explosión / Envolvente directa de llama (*Fireball*). | Epicentro del evento; destrucción estructural total e incendio posterior incontrolado. |
| **East Plant – FCC Unit** | **90%** ($109.5\\text{ MM}$) | $50 – 80\\text{ kPa}$ ($0.5 – 0.8\\text{ bar}$) | • $35-80\\text{ kPa}$: Daño estructural a columnas fraccionadoras.<br>• $40-55\\text{ kPa}$: Colapso de puentes de tubería (*pipe racks*). | Colindancia inmediata; colapso de líneas de transferencia de catalizador, deformación en fraccionadora principal y rotura de sopladores axiales. |
| **East Plant – Sulfur Unit (LTD)** | **80%** ($7.6\\text{ MM}$) | $40 – 60\\text{ kPa}$ ($0.4 – 0.6\\text{ bar}$) | • $30\\text{ kPa}$: Pérdida de cerramientos y paneles.<br>• $35-40\\text{ kPa}$: Falla y desplazamiento de tuberías conectadas. | Unidad compacta próxima al origen; colapso del horno de reacción Claus, calderas de calor residual y condensadores de azufre. |
| **East Plant – Special Fractionation (LEU)** | **70%** ($8.7\\text{ MM}$) | $35 – 50\\text{ kPa}$ ($0.35 – 0.5\\text{ bar}$) | • $35-80\\text{ kPa}$: Umbral inferior de daño a columnas fraccionadoras.<br>• $20\\text{ kPa}$: Colapso de estructuras soporte secundarias. | Pandeo local en faldones cilíndricos, colapso de bandejas de destilación internas y arrancamiento de conexiones de reflujo. |
| **East Plant – Hydrocracker / Reformer (CCR) / No. 2 HDS** | **60%** ($102.7\\text{ MM}$, $44.1\\text{ MM}$, $17.8\\text{ MM}$) | $20 – 35\\text{ kPa}$ ($0.2 – 0.35\\text{ bar}$) | • $20-30\\text{ kPa}$: Deformación en puentes de tubería.<br>• $8-10\\text{ kPa}$: Daños en pórticos de acero estructural. | Ubicadas en la periferia de la onda destructiva. Los reactores de pared gruesa permanecen intactos, pero los hornos de proceso sufren daño severo en refractarios/tubos y los compresores de reciclo de hidrógeno quedan inoperables. |
| **Process Related Off-Sites (Pipe racks, subestaciones)** | **25%** ($91.9\\text{ MM}$) | $15 – 35\\text{ kPa}$ ($0.15 – 0.35\\text{ bar}$) | • $20-30\\text{ kPa}$: Deformación de puentes de tubería.<br>• $35-40\\text{ kPa}$: Desplazamiento y fractura de líneas aéreas. | Daño distribuido a lo largo del corredor este: bandejas de cables, soportes metálicos y tuberías de interconexión con deformación plástica en un cuarto de su longitud total. |
| **Other Off-Sites (Tanques de almacenamiento)** | **10%** ($23.6\\text{ MM}$) | $7 – 15\\text{ kPa}$ ($0.07 – 0.15\\text{ bar}$) | • $7\\text{ kPa}$: Colapso del techo de tanques de almacenamiento. | Daño periférico leve: afectación en techos cónicos, sellos de techo flotante e instrumentación de patios de tanques distantes sin pérdida de contención. |
| **West Plant (Crude, Vacuum, Reformer, etc.)** | **0%** ($0.0\\text{ MM}$) | $< 3.5\\text{ kPa}$ ($< 0.035\\text{ bar}$) | Zona D: sin daño a estructuras de proceso; por debajo del límite de rotura de vidrios ($< 1\\text{ kPa}$). | La distancia física de separación entre bloques de proceso actuó como barrera eficaz, manteniendo la sobrepresión por debajo del umbral de daño mecánico. |
""")
