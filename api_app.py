import os
import io
import math
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import pandas as pd
import numpy as np

# Importaciones locales del gemelo digital y motores QRA
import db_manager
from db_manager import (
    init_db, get_equipos_df, upsert_equipo_coords, update_equipo_detalles,
    insert_equipo_completo, delete_equipo, get_condiciones, update_condiciones,
    get_matriz_dano_reparacion_df, update_matriz_dano_reparacion_df, reset_matriz_dano_from_excel
)
from consecuencias import (
    calcular_dinamica_fuga, calcular_radios_consecuencia, evaluar_equipos_afectados,
    calcular_matriz_distancias_geodesica, SpatialTransformer, HAS_PYPROJ, HAS_OPENSRANE,
    ejecutar_simulacion_opensrane, OPENSRANE_VERSION, SUSTANCIAS_DB,
    calcular_analisis_qra_completo, TIPOS_EQUIPO_DISPONIBLES,
    estimar_dano_y_tiempo_reparacion, recargar_cache_matriz_dano, NIVELES_CONGESTION
)
from wind_rose_engine import (
    obtener_rosa_vientos_meteoblue, generar_enlace_meteoblue, generar_figura_rosa_vientos_plotly
)
from qra_standards import (
    NIST_SUSTANCIAS_PROPS, PURPLE_BOOK_DIRECT_IGNITION_TABLE, PURPLE_BOOK_DELAYED_SOURCES,
    BEVI_LOC_TABLAS
)
from gis_engine import (
    procesar_archivo_plotplan, DEFAULT_CENTER, DEFAULT_BOUNDS, HAS_RASTERIO, RASTERIO_ERROR
)

# Inicializar DB
init_db()

app = FastAPI(
    title="GeoVision Plant Extractor — API REST Gemelo Digital & QRA (U044)",
    version="2.0.0",
    description="Backend API REST para cálculo de termodinámica API 581, OpenSRANE, GIS GeoTIFF, y QRA Standards"
)

# Habilitar CORS para permitir desarrollo con Vite / React en cualquier puerto
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DIR_PROYECTO = Path(__file__).resolve().parent

# Estado global en memoria para plotplan activo y caché de imagen
plotplan_state = {
    "fuente_sel": "Plotplan u044 georef.tif (GeoTIFF Oficial)",
    "opacidad": 0.70,
    "quitar_blanco": True,
    "offset_x": 0.0,
    "offset_y": 0.0,
    "data": None,
    "image_bytes": None,
    "file_hash": None
}

def sanitizar_para_json(obj):
    """Convierte NaNs, Infs y tipos NumPy a tipos nativos serializables en JSON."""
    if isinstance(obj, dict):
        return {k: sanitizar_para_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitizar_para_json(v) for v in obj]
    elif isinstance(obj, (np.floating, float)):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return float(obj)
    elif isinstance(obj, (np.integer, int)):
        return int(obj)
    elif isinstance(obj, np.ndarray):
        return sanitizar_para_json(obj.tolist())
    elif isinstance(obj, pd.DataFrame):
        return sanitizar_para_json(obj.to_dict(orient="records"))
    return obj

def cargar_plotplan_actual():
    """Recalcula o devuelve los datos del plotplan activo según la configuración."""
    fuente = plotplan_state["fuente_sel"]
    p_archivo = None

    if "GeoTIFF Oficial" in fuente:
        p_archivo = DIR_PROYECTO / "Plotplan u044 georef.tif"
    elif "(Local)" in fuente:
        nombre = fuente.replace(" (Local)", "").strip()
        p_archivo = DIR_PROYECTO / nombre
    elif fuente != "🚫 Ninguno (Solo Satélite)":
        p_archivo = DIR_PROYECTO / fuente

    if p_archivo and p_archivo.exists():
        raw_bytes = p_archivo.read_bytes()
        cur_hash = hash(raw_bytes) + hash(plotplan_state["offset_x"]) + hash(plotplan_state["offset_y"]) + hash(plotplan_state["quitar_blanco"])
        if plotplan_state["file_hash"] != cur_hash or plotplan_state["data"] is None:
            try:
                datos = procesar_archivo_plotplan(
                    raw_bytes,
                    filename=p_archivo.name,
                    offset_x=plotplan_state["offset_x"],
                    offset_y=plotplan_state["offset_y"],
                    hacer_blanco_transparente=plotplan_state["quitar_blanco"]
                )
                plotplan_state["data"] = datos
                plotplan_state["file_hash"] = cur_hash
                if "data_url" in datos and datos["data_url"].startswith("data:image/png;base64,"):
                    import base64
                    plotplan_state["image_bytes"] = base64.b64decode(datos["data_url"].split(",")[1])
            except Exception as e:
                print(f"Error procesando plotplan: {e}")
                plotplan_state["data"] = None
                plotplan_state["image_bytes"] = None
    else:
        plotplan_state["data"] = None
        plotplan_state["image_bytes"] = None

    return plotplan_state["data"]

# Carga inicial al arrancar
cargar_plotplan_actual()


# ==============================================================================
# MODELOS PYDANTIC
# ==============================================================================

class EquipoCreate(BaseModel):
    tag: str
    tipo_equipo: str = "Vessel / Drum"
    latitud: float
    longitud: float
    sustancia: str = "GLP / Propano"
    inventario_kg: float = 15000.0
    presion_bar: float = 18.0
    temperatura_c: float = 45.0
    diametro_orificio_mm: float = 25.4
    altura_fuga_m: float = 1.5
    valor_reposicion_usd: float = 850000.0
    lead_time_meses: float = 8.0
    impacto_diario_usd: float = 40000.0

class EquipoUpdateCoords(BaseModel):
    latitud: float
    longitud: float

class CondicionesUpdate(BaseModel):
    temperatura_ambiente_c: float = 32.0
    humedad_relativa_pct: float = 78.0
    velocidad_viento_ms: float = 4.5
    direccion_viento_deg: float = 45.0
    clase_estabilidad: str = "D"

class PlotplanConfig(BaseModel):
    fuente_sel: Optional[str] = None
    opacidad: Optional[float] = None
    quitar_blanco: Optional[bool] = None
    offset_x: Optional[float] = None
    offset_y: Optional[float] = None

class SimulacionRequest(BaseModel):
    tag_emisor: Optional[str] = None
    modo_origen_fuga: str = "🏭 Activo del Plot Plan"
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    tipo_equipo: Optional[str] = "Vessel / Drum"
    sustancia: str = "GLP / Propano"
    diametro_orificio_mm: float = 25.4
    presion_bar: float = 18.0
    temperatura_c: float = 45.0
    inventario_kg: float = 15000.0
    tiempo_fuga_min: float = 5.0
    fenomeno: str = "Radiación Térmica (Jet/Pool Fire)"
    nivel_congestion: str = "Media (Proceso Estándar, eta=0.10)"
    temperatura_ambiente_c: Optional[float] = 32.0
    humedad_relativa_pct: Optional[float] = 78.0
    velocidad_viento_ms: Optional[float] = 4.5
    clase_estabilidad: Optional[str] = "D"


# ==============================================================================
# ENDPOINTS REST: ESTADO DEL SISTEMA & METADATOS
# ==============================================================================

@app.get("/api/status")
def get_system_status():
    return {
        "status": "online",
        "app_title": "GeoVision Plant Extractor — Gemelo Digital & QRA (U044)",
        "opensrane_activo": HAS_OPENSRANE,
        "opensrane_version": OPENSRANE_VERSION,
        "rasterio_activo": HAS_RASTERIO,
        "pyproj_activo": HAS_PYPROJ,
        "tipos_equipo": TIPOS_EQUIPO_DISPONIBLES,
        "sustancias": list(SUSTANCIAS_DB.keys()),
        "niveles_congestion": NIVELES_CONGESTION,
        "default_center": DEFAULT_CENTER,
        "default_bounds": DEFAULT_BOUNDS
    }


# ==============================================================================
# ENDPOINTS REST: GESTIÓN DE EQUIPOS (GEMELO DIGITAL)
# ==============================================================================

@app.get("/api/equipos")
def get_all_equipos():
    df = get_equipos_df()
    return sanitizar_para_json(df.to_dict(orient="records"))

@app.post("/api/equipos")
def create_equipo(eq: EquipoCreate):
    ok = insert_equipo_completo(
        tag=eq.tag,
        tipo_equipo=eq.tipo_equipo,
        latitud=eq.latitud,
        longitud=eq.longitud,
        sustancia=eq.sustancia,
        inventario_kg=eq.inventario_kg,
        presion_bar=eq.presion_bar,
        temperatura_c=eq.temperatura_c,
        diametro_orificio_mm=eq.diametro_orificio_mm,
        altura_fuga_m=eq.altura_fuga_m,
        valor_reposicion_usd=eq.valor_reposicion_usd,
        lead_time_meses=eq.lead_time_meses,
        impacto_diario_usd=eq.impacto_diario_usd
    )
    if not ok:
        raise HTTPException(status_code=400, detail="Error al crear el equipo o Tag duplicado")
    return {"message": f"Equipo '{eq.tag}' registrado con éxito", "tag": eq.tag}

@app.put("/api/equipos/{tag}")
def update_equipo(tag: str, eq: EquipoCreate):
    ok = update_equipo_detalles(
        tag=tag,
        tipo_equipo=eq.tipo_equipo,
        sustancia=eq.sustancia,
        inventario_kg=eq.inventario_kg,
        presion_bar=eq.presion_bar,
        temperatura_c=eq.temperatura_c,
        diametro_orificio_mm=eq.diametro_orificio_mm,
        altura_fuga_m=eq.altura_fuga_m,
        valor_reposicion_usd=eq.valor_reposicion_usd,
        lead_time_meses=eq.lead_time_meses,
        impacto_diario_usd=eq.impacto_diario_usd
    )
    upsert_equipo_coords(tag, eq.latitud, eq.longitud)
    return {"message": f"Equipo '{tag}' actualizado con éxito"}

@app.patch("/api/equipos/{tag}/coords")
def update_equipo_coords(tag: str, coords: EquipoUpdateCoords):
    upsert_equipo_coords(tag, coords.latitud, coords.longitud)
    return {"message": f"Coordenadas de '{tag}' actualizadas", "lat": coords.latitud, "lon": coords.longitud}

@app.delete("/api/equipos/{tag}")
def remove_equipo(tag: str):
    delete_equipo(tag)
    return {"message": f"Equipo '{tag}' eliminado"}


# ==============================================================================
# ENDPOINTS REST: CONDICIONES AMBIENTALES
# ==============================================================================

@app.get("/api/condiciones")
def get_ambient_conditions():
    cond = get_condiciones()
    return sanitizar_para_json(cond)

@app.put("/api/condiciones")
def set_ambient_conditions(c: CondicionesUpdate):
    update_condiciones(
        temp_c=c.temperatura_ambiente_c,
        humedad_pct=c.humedad_relativa_pct,
        vel_viento_ms=c.velocidad_viento_ms,
        dir_viento_deg=c.direccion_viento_deg,
        clase_estabilidad=c.clase_estabilidad
    )
    return {"message": "Condiciones ambientales actualizadas correctamente"}


# ==============================================================================
# ENDPOINTS REST: PLOT PLAN & GIS
# ==============================================================================

@app.get("/api/plotplan/files")
def get_plotplan_files():
    archivos_locales = sorted([
        f.name for f in DIR_PROYECTO.glob("*.*")
        if f.suffix.lower() in ['.tif', '.tiff', '.png', '.jpg', '.jpeg']
    ])
    opciones = []
    if "Plotplan u044 georef.tif" in archivos_locales:
        opciones.append("Plotplan u044 georef.tif (GeoTIFF Oficial)")
    for arch in archivos_locales:
        if arch != "Plotplan u044 georef.tif":
            opciones.append(f"{arch} (Local)")
    opciones.append("🚫 Ninguno (Solo Satélite)")

    return {
        "files": opciones,
        "selected": plotplan_state["fuente_sel"],
        "opacidad": plotplan_state["opacidad"],
        "quitar_blanco": plotplan_state["quitar_blanco"],
        "offset_x": plotplan_state["offset_x"],
        "offset_y": plotplan_state["offset_y"]
    }

@app.post("/api/plotplan/config")
def update_plotplan_config(cfg: PlotplanConfig):
    if cfg.fuente_sel is not None:
        plotplan_state["fuente_sel"] = cfg.fuente_sel
        plotplan_state["file_hash"] = None
    if cfg.opacidad is not None:
        plotplan_state["opacidad"] = cfg.opacidad
    if cfg.quitar_blanco is not None:
        plotplan_state["quitar_blanco"] = cfg.quitar_blanco
        plotplan_state["file_hash"] = None
    if cfg.offset_x is not None:
        plotplan_state["offset_x"] = cfg.offset_x
        plotplan_state["file_hash"] = None
    if cfg.offset_y is not None:
        plotplan_state["offset_y"] = cfg.offset_y
        plotplan_state["file_hash"] = None

    cargar_plotplan_actual()
    return get_plotplan_info()

@app.get("/api/plotplan/current")
def get_plotplan_info():
    data = cargar_plotplan_actual()
    if data is None:
        return {
            "has_plotplan": False,
            "fuente_sel": plotplan_state["fuente_sel"],
            "bounds": DEFAULT_BOUNDS,
            "center": DEFAULT_CENTER,
            "zoom": 18,
            "opacidad": plotplan_state["opacidad"],
            "metadata": {}
        }

    return {
        "has_plotplan": True,
        "fuente_sel": plotplan_state["fuente_sel"],
        "bounds": data["bounds"],
        "center": data["center"],
        "zoom": data["zoom"],
        "opacidad": plotplan_state["opacidad"],
        "quitar_blanco": plotplan_state["quitar_blanco"],
        "offset_x": plotplan_state["offset_x"],
        "offset_y": plotplan_state["offset_y"],
        "metadata": data.get("metadata", {}),
        "image_url": f"/api/plotplan/image?v={plotplan_state['file_hash']}"
    }

@app.get("/api/plotplan/image")
def get_plotplan_image():
    cargar_plotplan_actual()
    if plotplan_state["image_bytes"] is None:
        raise HTTPException(status_code=404, detail="No hay imagen de plot plan disponible")
    return Response(content=plotplan_state["image_bytes"], media_type="image/png")

@app.post("/api/plotplan/upload")
async def upload_plotplan(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in ['.tif', '.tiff', '.png', '.jpg', '.jpeg']:
        raise HTTPException(status_code=400, detail="Formato no soportado (.tif, .png, .jpg)")
    
    contenido = await file.read()
    dest = DIR_PROYECTO / file.filename
    dest.write_bytes(contenido)

    plotplan_state["fuente_sel"] = f"{file.filename} (Local)"
    plotplan_state["file_hash"] = None
    cargar_plotplan_actual()

    return {"message": f"Archivo '{file.filename}' guardado y activado correctamente"}


# ==============================================================================
# ENDPOINTS REST: SIMULACIÓN DE ESCENARIOS (CONSECUENCIAS & QRA)
# ==============================================================================

@app.post("/api/simulacion/calcular")
def run_simulation(req: SimulacionRequest):
    df_equipos = get_equipos_df()
    
    tag_emisor = req.tag_emisor or "Punto-Fuga-01"
    lat = req.latitud
    lon = req.longitud
    tipo_eq = req.tipo_equipo or "Vessel / Drum"

    if req.modo_origen_fuga == "🏭 Activo del Plot Plan" and not df_equipos.empty:
        filtro = df_equipos[df_equipos['tag'] == req.tag_emisor]
        if not filtro.empty:
            r = filtro.iloc[0]
            lat = float(r['latitud']) if lat is None else lat
            lon = float(r['longitud']) if lon is None else lon
            tipo_eq = str(r['tipo_equipo'])

    if lat is None or lon is None:
        lat, lon = DEFAULT_CENTER[0], DEFAULT_CENTER[1]

    eq_emisor = {
        'tag': tag_emisor,
        'tipo_equipo': tipo_eq,
        'latitud': float(lat),
        'longitud': float(lon),
        'sustancia': req.sustancia,
        'diametro_orificio_mm': float(req.diametro_orificio_mm),
        'presion_bar': float(req.presion_bar),
        'temperatura_c': float(req.temperatura_c),
        'inventario_kg': float(req.inventario_kg),
        'altura_fuga_m': 1.5,
        'valor_reposicion_usd': 850000.0
    }

    cond_meteo = {
        'temperatura_ambiente_c': float(req.temperatura_ambiente_c or 32.0),
        'humedad_relativa_pct': float(req.humedad_relativa_pct or 78.0),
        'velocidad_viento_ms': float(req.velocidad_viento_ms or 4.5),
        'clase_estabilidad': str(req.clase_estabilidad or 'D')
    }

    dinamica = calcular_dinamica_fuga(
        eq_emisor,
        req.tiempo_fuga_min,
        diametro_override_mm=req.diametro_orificio_mm,
        sustancia_override=req.sustancia,
        presion_override_bar=req.presion_bar,
        temp_override_c=req.temperatura_c,
        inventario_override_kg=req.inventario_kg
    )

    consecuencia = calcular_radios_consecuencia(
        dinamica,
        req.fenomeno,
        nivel_congestion=req.nivel_congestion,
        condiciones_meteo=cond_meteo
    )

    afectados = evaluar_equipos_afectados(
        eq_emisor,
        df_equipos,
        consecuencia["anillos"],
        fenomeno=req.fenomeno,
        tiempo_fuga_min=req.tiempo_fuga_min
    )

    qra_full = calcular_analisis_qra_completo(
        eq_emisor,
        df_equipos,
        dinamica,
        consecuencia,
        sustancia_nombre=req.sustancia,
        diametro_fuga_mm=req.diametro_orificio_mm,
        fenomeno=req.fenomeno,
        tiempo_fuga_min=req.tiempo_fuga_min
    )

    return sanitizar_para_json({
        "eq_emisor": eq_emisor,
        "dinamica_fuga": dinamica,
        "consecuencia": consecuencia,
        "afectados": afectados,
        "qra_full": qra_full
    })


# ==============================================================================
# ENDPOINTS REST: MODELO DE EFECTO DOMINÓ (OPENSRANE & COZZANI)
# ==============================================================================

@app.get("/api/domino/matriz-distancias")
def get_distance_matrix():
    df = get_equipos_df()
    matriz = calcular_matriz_distancias_geodesica(df)
    return sanitizar_para_json(matriz.to_dict(orient="split"))

@app.post("/api/domino/simular")
def run_domino_simulation(req: SimulacionRequest):
    df_equipos = get_equipos_df()
    if df_equipos.empty:
        raise HTTPException(status_code=400, detail="No hay equipos registrados en la base de datos")

    lat = req.latitud or float(df_equipos.iloc[0]['latitud'])
    lon = req.longitud or float(df_equipos.iloc[0]['longitud'])
    tag = req.tag_emisor or str(df_equipos.iloc[0]['tag'])
    tipo = req.tipo_equipo or str(df_equipos.iloc[0]['tipo_equipo'])

    eq_emisor = {
        'tag': tag,
        'tipo_equipo': tipo,
        'latitud': float(lat),
        'longitud': float(lon),
        'sustancia': req.sustancia,
        'diametro_orificio_mm': float(req.diametro_orificio_mm),
        'presion_bar': float(req.presion_bar),
        'temperatura_c': float(req.temperatura_c),
        'inventario_kg': float(req.inventario_kg),
        'altura_fuga_m': 1.5,
        'valor_reposicion_usd': 850000.0
    }

    cond_meteo = {
        'temperatura_ambiente_c': float(req.temperatura_ambiente_c or 32.0),
        'humedad_relativa_pct': float(req.humedad_relativa_pct or 78.0),
        'velocidad_viento_ms': float(req.velocidad_viento_ms or 4.5),
        'clase_estabilidad': str(req.clase_estabilidad or 'D')
    }

    resultado_sim = ejecutar_simulacion_opensrane(
        eq_emisor, df_equipos, cond_meteo,
        fenomeno=req.fenomeno,
        tiempo_fuga_min=req.tiempo_fuga_min,
        nivel_congestion=req.nivel_congestion,
        diametro_override_mm=req.diametro_orificio_mm,
        sustancia_override=req.sustancia
    )

    matriz_dist = calcular_matriz_distancias_geodesica(df_equipos)

    return sanitizar_para_json({
        "status": "success",
        "opensrane_activo": HAS_OPENSRANE,
        "opensrane_version": OPENSRANE_VERSION,
        "sim_data": resultado_sim,
        "matriz_distancias": matriz_dist.to_dict(orient="split")
    })


# ==============================================================================
# ENDPOINTS REST: ROSA DE VIENTOS & ESTÁNDARES QRA
# ==============================================================================

@app.get("/api/qra/rosa-vientos")
def get_wind_rose(lat: float = Query(10.314855), lon: float = Query(-75.487632)):
    datos = obtener_rosa_vientos_meteoblue(lat, lon)
    enlace = generar_enlace_meteoblue(lat, lon)
    fig = generar_figura_rosa_vientos_plotly(datos)
    return sanitizar_para_json({
        "datos": datos,
        "meteoblue_url": enlace.get("url_pronostico", ""),
        "meteoblue_windmap_url": enlace.get("url_animacion_viento", ""),
        "plotly_fig": fig.to_dict()
    })

@app.get("/api/qra/bevi-frecuencias")
def get_bevi_tables():
    return sanitizar_para_json(BEVI_LOC_TABLAS)

@app.get("/api/qra/purple-book")
def get_purple_book_data():
    return sanitizar_para_json({
        "direct_ignition": PURPLE_BOOK_DIRECT_IGNITION_TABLE,
        "delayed_sources": PURPLE_BOOK_DELAYED_SOURCES
    })

@app.get("/api/qra/sustancias-nist")
def get_nist_properties():
    return sanitizar_para_json({
        "sustancias_db": SUSTANCIAS_DB,
        "nist_props": NIST_SUSTANCIAS_PROPS
    })


# ==============================================================================
# ENDPOINTS REST: CRITICIDAD FINANCIERA & MATRIZ DE DAÑO (PML)
# ==============================================================================

@app.get("/api/financiero/matriz-dano")
def get_damage_matrix():
    df = get_matriz_dano_reparacion_df()
    return sanitizar_para_json(df.to_dict(orient="records"))

@app.put("/api/financiero/matriz-dano")
def save_damage_matrix(records: List[Dict[str, Any]]):
    df = pd.DataFrame(records)
    ok = update_matriz_dano_reparacion_df(df)
    recargar_cache_matriz_dano()
    return {"message": "Matriz de daño y tiempo de reparación guardada con éxito", "ok": ok}

@app.post("/api/financiero/matriz-dano/reset")
def reset_damage_matrix():
    ok = reset_matriz_dano_from_excel()
    recargar_cache_matriz_dano()
    df = get_matriz_dano_reparacion_df()
    return {
        "message": "Matriz restablecida con éxito desde estándares de ingeniería",
        "data": sanitizar_para_json(df.to_dict(orient="records"))
    }


# ==============================================================================
# MONTAJE DE ARCHIVOS ESTÁTICOS DE REACT CON CABECERAS ANTI-CACHE
# ==============================================================================

@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    path = request.url.path.lower()
    if path.endswith((".js", ".html", ".css")) or path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

STATIC_DIR = DIR_PROYECTO / "static"
if not STATIC_DIR.exists():
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

# Montar static para servir frontend React
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

