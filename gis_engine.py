import io
import base64
import math
from PIL import Image

try:
    import rasterio
    from rasterio.io import MemoryFile
    from rasterio.warp import transform_bounds
    from rasterio.crs import CRS
    HAS_RASTERIO = True
    RASTERIO_ERROR = None
except Exception as _e:
    HAS_RASTERIO = False
    RASTERIO_ERROR = str(_e)

# Coordenadas y bounds de referencia exactos para la Planta U044 (Cartagena)
DEFAULT_CENTER = [10.314855, -75.487632]
DEFAULT_BOUNDS = [[10.313492, -75.488273], [10.316219, -75.486990]]

def calcular_zoom_desde_bounds(bounds):
    """Calcula el nivel de zoom óptimo de Folium basado en el span geográfico."""
    min_lat, min_lon = bounds[0]
    max_lat, max_lon = bounds[1]
    lat_span = max(abs(max_lat - min_lat), 0.0001)
    lon_span = max(abs(max_lon - min_lon), 0.0001)
    max_span = max(lat_span, lon_span)
    
    # Aproximación logarítmica para zoom de Web Mercator
    if max_span < 0.002:
        return 19
    elif max_span < 0.005:
        return 18
    elif max_span < 0.01:
        return 17
    elif max_span < 0.03:
        return 16
    elif max_span < 0.08:
        return 15
    elif max_span < 0.2:
        return 14
    else:
        return 13

def optimizar_imagen_para_folium(pil_img, max_dim=4000, hacer_blanco_transparente=False, tolerancia_blanco=235):
    """
    Optimiza la imagen para su visualización nítida y transparente en Folium.
    - Preserva formato PNG sin pérdida para planos y dibujos técnicos.
    - Soporta canal Alfa real o eliminación opcional de fondo blanco.
    - Permite resoluciones altas (hasta 4000px) sin pixelado ni artefactos JPEG.
    """
    w, h = pil_img.size
    if max(w, h) > max_dim:
        scale = max_dim / float(max(w, h))
        new_w = int(w * scale)
        new_h = int(h * scale)
        pil_img = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
    # Asegurar modo RGBA para soporte total de transparencia
    if pil_img.mode != 'RGBA':
        pil_img = pil_img.convert('RGBA')
        
    if hacer_blanco_transparente:
        # Convertir píxeles blancos/claros a transparentes
        import numpy as np
        data = np.array(pil_img)
        r, g, b, a = data[:, :, 0], data[:, :, 1], data[:, :, 2], data[:, :, 3]
        mascara_blanco = (r >= tolerancia_blanco) & (g >= tolerancia_blanco) & (b >= tolerancia_blanco)
        data[:, :, 3] = np.where(mascara_blanco, 0, a)
        pil_img = Image.fromarray(data, mode='RGBA')

    buf = io.BytesIO()
    # Guardar como PNG de alta fidelidad sin compresión destructiva
    pil_img.save(buf, format="PNG", optimize=True)
    b64_str = base64.b64encode(buf.getvalue()).decode('utf-8')
    data_url = f"data:image/png;base64,{b64_str}"
    return data_url, pil_img.size

def procesar_archivo_plotplan(file_bytes, filename="plotplan.tif", offset_x=0.0, offset_y=0.0, fallback_bounds=None, hacer_blanco_transparente=False):
    """
    Procesa un archivo de plot plan subido (.tif, .tiff, .png, .jpg).
    Extrae automáticamente metadatos geoespaciales si es GeoTIFF válido.
    Retorna:
        - data_url: Cadena base64 para ImageOverlay
        - bounds: [[min_lat, min_lon], [max_lat, max_lon]]
        - center: [center_lat, center_lon]
        - zoom: nivel de zoom óptimo
        - metadata: dict con información técnica de CRS y georreferenciación
    """
    if fallback_bounds is None:
        fallback_bounds = [list(DEFAULT_BOUNDS[0]), list(DEFAULT_BOUNDS[1])]

    is_tif = any(filename.lower().endswith(ext) for ext in ['.tif', '.tiff'])
    georeferenced = False
    meta_info = {
        "filename": filename,
        "is_geotiff": False,
        "crs": "No georreferenciado / Imagen plana",
        "rasterio_used": False,
        "width": 0,
        "height": 0
    }
    
    bounds = None
    pil_image = None
    
    if is_tif and HAS_RASTERIO:
        try:
            with MemoryFile(file_bytes) as memfile:
                with memfile.open() as src:
                    meta_info["rasterio_used"] = True
                    meta_info["width"] = src.width
                    meta_info["height"] = src.height
                    
                    if src.crs is not None:
                        meta_info["is_geotiff"] = True
                        meta_info["crs"] = str(src.crs)
                        
                        # Extraer límites espaciales del raster
                        raw_bounds = src.bounds # left, bottom, right, top
                        
                        try:
                            # Si no es EPSG:4326, reproyectar a latitud/longitud
                            if src.crs != CRS.from_epsg(4326):
                                min_lon, min_lat, max_lon, max_lat = transform_bounds(
                                    src.crs, 'EPSG:4326', raw_bounds.left, raw_bounds.bottom, raw_bounds.right, raw_bounds.top
                                )
                            else:
                                min_lon, min_lat, max_lon, max_lat = raw_bounds.left, raw_bounds.bottom, raw_bounds.right, raw_bounds.top
                                
                            bounds = [[min_lat, min_lon], [max_lat, max_lon]]
                            georeferenced = True
                        except Exception as e_reproj:
                            meta_info["reproject_error"] = str(e_reproj)
                            
                    # Extraer canales para convertir a PIL Image
                    num_bands = src.count
                    if num_bands >= 4:
                        data = src.read([1, 2, 3, 4])
                        # Transponer a (H, W, C)
                        import numpy as np
                        data = np.transpose(data, (1, 2, 0))
                        pil_image = Image.fromarray(data.astype('uint8'), mode='RGBA')
                    elif num_bands == 3:
                        data = src.read([1, 2, 3])
                        import numpy as np
                        data = np.transpose(data, (1, 2, 0))
                        pil_image = Image.fromarray(data.astype('uint8'), mode='RGB')
                    else:
                        data = src.read(1)
                        import numpy as np
                        pil_image = Image.fromarray(data.astype('uint8')).convert('L')
        except Exception as e_rio:
            meta_info["rasterio_error"] = str(e_rio)
            
    # Fallback con Pillow si no se pudo leer o no es GeoTIFF
    if pil_image is None:
        try:
            pil_image = Image.open(io.BytesIO(file_bytes))
            meta_info["width"] = pil_image.width
            meta_info["height"] = pil_image.height
        except Exception as e_pil:
            raise ValueError(f"No fue posible abrir el archivo de imagen: {e_pil}")
            
    if bounds is None or not georeferenced:
        bounds = [
            [fallback_bounds[0][0], fallback_bounds[0][1]],
            [fallback_bounds[1][0], fallback_bounds[1][1]]
        ]
        
    # Aplicar micro-desplazamientos de calibración
    final_bounds = [
        [bounds[0][0] + offset_y, bounds[0][1] + offset_x],
        [bounds[1][0] + offset_y, bounds[1][1] + offset_x]
    ]
    
    # Calcular centro y zoom
    center_lat = (final_bounds[0][0] + final_bounds[1][0]) / 2.0
    center_lon = (final_bounds[0][1] + final_bounds[1][1]) / 2.0
    center = [center_lat, center_lon]
    zoom = calcular_zoom_desde_bounds(final_bounds)
    
    # Optimizar imagen para el buffer de Folium
    data_url, final_size = optimizar_imagen_para_folium(pil_image, hacer_blanco_transparente=hacer_blanco_transparente)
    meta_info["render_size"] = final_size
    meta_info["bounds"] = final_bounds
    meta_info["center"] = center
    meta_info["zoom"] = zoom
    
    return {
        "data_url": data_url,
        "bounds": final_bounds,
        "center": center,
        "zoom": zoom,
        "metadata": meta_info,
        "is_geotiff": meta_info["is_geotiff"]
    }
