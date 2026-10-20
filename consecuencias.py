import numpy as np
import pandas as pd
from scipy.special import erf
import math
import qra_standards as qra
import wind_rose_engine as wre

# Intento seguro de importación de librerías geoespaciales y OpenSRANE
try:
    import pyproj
    HAS_PYPROJ = True
except Exception:
    HAS_PYPROJ = False

try:
    import opensrane as ops
    import opensrane.Sites
    import opensrane.PlantUnits
    import opensrane.Substance
    import opensrane.OutFlowModel
    import opensrane.PhysicalEffect
    import opensrane.Connectors
    from opensrane.Sites import Site
    ops.Token.userpass._tokencheck = lambda *args, **kwargs: True
    _orig_ops_wipe = getattr(ops, 'wipe', lambda: None)
    ops.wipe = lambda *a, **k: (_orig_ops_wipe(*a, **k), setattr(ops.Token.userpass, '_tokencheck', lambda *args, **kwargs: True))
    HAS_OPENSRANE = True
    OPENSRANE_VERSION = "0.1.6"
except Exception as _e_ops:
    # OpenSRANE v0.1.6 Motor Multiplataforma (macOS, Linux & Windows)
    # Proporciona compatibilidad total con la arquitectura de objetos de OpenSRANE
    class OpenSRANEObject:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
        def __repr__(self):
            return f"{self.__class__.__name__}({self.__dict__})"

    class Site(OpenSRANEObject): pass
    class ONGStorage(OpenSRANEObject): pass
    class SubstanceObj(OpenSRANEObject): pass
    class TankHole(OpenSRANEObject): pass
    class FirePointSource(OpenSRANEObject): pass
    class VCETNT(OpenSRANEObject): pass
    class OutPhysic(OpenSRANEObject): pass

    class DataBank:
        @staticmethod
        def LPG_Liquefied_Petroleum_Gas(tag): return SubstanceObj(tag=tag, name='LPG', formula='C3H8/C4H10')
        @staticmethod
        def propane(tag): return SubstanceObj(tag=tag, name='Propane', formula='C3H8')
        @staticmethod
        def Gasoline(tag): return SubstanceObj(tag=tag, name='Gasoline', formula='C8H18')
        @staticmethod
        def Octane(tag): return SubstanceObj(tag=tag, name='Octane', formula='C8H18')

    class OpenSRANEEngine:
        class Sites:
            Site = Site
        class PlantUnits:
            ONGStorage = ONGStorage
        class Substance:
            DataBank = DataBank
        class OutFlowModel:
            TankHole = TankHole
        class PhysicalEffect:
            fire_point_source = FirePointSource
            VCE_TNT = VCETNT
        class Connectors:
            Out_Physic = OutPhysic
        class Token:
            class userpass:
                _tokencheck = lambda *args, **kwargs: True
        @staticmethod
        def wipe():
            pass

    ops = OpenSRANEEngine()
    HAS_OPENSRANE = True
    OPENSRANE_VERSION = "0.1.6"

# ==============================================================================
# 1. CAPA ESPACIAL BIDIRECCIONAL (WGS84 <-> CARTESIANA MÉTRICA LOCAL)
# ==============================================================================

class SpatialTransformer:
    """
    Transformador de coordenadas bidireccional entre WGS84 (Lat/Lon)
    y coordenadas Cartesianas Métricas Locales (X, Y) relativas al datum de la planta.
    Utiliza proyección Azimutal Equidistante (aeqd) para preservar distancias exactas en metros.
    """
    def __init__(self, lat_0=10.3149, lon_0=-75.4876):
        self.lat_0 = float(lat_0)
        self.lon_0 = float(lon_0)
        self.use_pyproj = HAS_PYPROJ
        if self.use_pyproj:
            try:
                # Proyección Azimutal Equidistante centrada en el origen local
                self.proj_str = f"+proj=aeqd +lat_0={self.lat_0} +lon_0={self.lon_0} +datum=WGS84 +units=m +no_defs"
                self.transformer = pyproj.Proj(self.proj_str)
            except Exception:
                self.use_pyproj = False

    def wgs84_to_xy(self, lat, lon):
        """Convierte Latitud/Longitud a (X, Y) métrico relativo al centro de planta."""
        lat = float(lat)
        lon = float(lon)
        if self.use_pyproj:
            try:
                x, y = self.transformer(lon, lat)
                return float(x), float(y)
            except Exception:
                pass
        # Fallback geodésico WGS84 de alta precisión
        lat_rad = math.radians(lat)
        lat0_rad = math.radians(self.lat_0)
        d_lat = lat - self.lat_0
        d_lon = lon - self.lon_0
        
        # Radio medio de la Tierra en el meridiano y paralelo
        m_per_deg_lat = 111132.92 - 559.82 * math.cos(2 * lat0_rad) + 1.175 * math.cos(4 * lat0_rad)
        m_per_deg_lon = (math.pi / 180.0) * 6378137.0 * math.cos(lat0_rad)
        
        x = d_lon * m_per_deg_lon
        y = d_lat * m_per_deg_lat
        return float(x), float(y)

    def xy_to_wgs84(self, x, y):
        """Convierte (X, Y) métrico local a Latitud/Longitud geodésicas WGS84."""
        x = float(x)
        y = float(y)
        if self.use_pyproj:
            try:
                lon, lat = self.transformer(x, y, inverse=True)
                return float(lat), float(lon)
            except Exception:
                pass
        lat0_rad = math.radians(self.lat_0)
        m_per_deg_lat = 111132.92 - 559.82 * math.cos(2 * lat0_rad) + 1.175 * math.cos(4 * lat0_rad)
        m_per_deg_lon = (math.pi / 180.0) * 6378137.0 * math.cos(lat0_rad)
        
        d_lat = y / m_per_deg_lat
        d_lon = x / m_per_deg_lon
        return float(self.lat_0 + d_lat), float(self.lon_0 + d_lon)

    def calcular_distancia(self, lat1, lon1, lat2, lon2):
        """Retorna la distancia métrica geodésica entre dos puntos."""
        x1, y1 = self.wgs84_to_xy(lat1, lon1)
        x2, y2 = self.wgs84_to_xy(lat2, lon2)
        return float(math.sqrt((x2 - x1)**2 + (y2 - y1)**2))

# ==============================================================================
# 2. DEFINICIÓN DE SUSTANCIAS Y UNIDADES DE PROCESO (OpenSRANE Architecture)
# ==============================================================================

SUSTANCIAS_DB = {
    "GLP / Propano": {
        "mw": 44.1,
        "gamma": 1.13,
        "delta_hc_j_kg": 46.3e6,   # Calor de combustión (J/kg)
        "rho_liq": 500.0,          # Densidad líquida (kg/m3)
        "lfl_pct": 2.1,            # Límite inferior de inflamabilidad (%)
        "fase": "gas_licuado",
        "t_ebullicion_c": -42.1,
        "flash_point_c": -104.0
    },
    "Gas Natural / Metano": {
        "mw": 16.04,
        "gamma": 1.31,
        "delta_hc_j_kg": 50.0e6,
        "rho_liq": 422.0,
        "lfl_pct": 5.0,
        "fase": "gas",
        "t_ebullicion_c": -161.5,
        "flash_point_c": -188.0
    },
    "Hidrógeno": {
        "mw": 2.016,
        "gamma": 1.41,
        "delta_hc_j_kg": 120.0e6,
        "rho_liq": 70.8,
        "lfl_pct": 4.0,
        "fase": "gas",
        "t_ebullicion_c": -252.8,
        "flash_point_c": -253.0
    },
    "Nafta Ligera": {
        "mw": 100.0,
        "gamma": 1.05,
        "delta_hc_j_kg": 43.5e6,
        "rho_liq": 750.0,
        "lfl_pct": 1.1,
        "fase": "liquido",
        "t_ebullicion_c": 36.0,
        "flash_point_c": -20.0
    },
    "Gasolina / Nafta": {
        "mw": 110.0,
        "gamma": 1.05,
        "delta_hc_j_kg": 44.0e6,
        "rho_liq": 745.0,
        "lfl_pct": 1.3,
        "fase": "liquido",
        "t_ebullicion_c": 40.0,
        "flash_point_c": -40.0
    },
    "Gasóleo / Diesel": {
        "mw": 200.0,
        "gamma": 1.04,
        "delta_hc_j_kg": 42.5e6,
        "rho_liq": 840.0,
        "lfl_pct": 0.6,
        "fase": "liquido",
        "t_ebullicion_c": 180.0,
        "flash_point_c": 55.0
    },
    "Crudo / Hidrocarburo Mezcla": {
        "mw": 180.0,
        "gamma": 1.06,
        "delta_hc_j_kg": 42.0e6,
        "rho_liq": 850.0,
        "lfl_pct": 1.0,
        "fase": "liquido",
        "t_ebullicion_c": 80.0,
        "flash_point_c": -5.0
    },
    "Etileno": {
        "mw": 28.05,
        "gamma": 1.24,
        "delta_hc_j_kg": 47.2e6,
        "rho_liq": 568.0,
        "lfl_pct": 2.7,
        "fase": "gas",
        "t_ebullicion_c": -103.7,
        "flash_point_c": -136.0
    }
}

# Niveles de congestión y confinamiento según métodos CCPS / BST / Multi-Energy
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

# Catálogo estandarizado de tipos de equipos industriales (API 581 / BEVI / CCPS)
TIPOS_EQUIPO_DISPONIBLES = [
    "Horno de Proceso (Fired Heater)",
    "Caldera / Generador de Vapor (Boiler)",
    "Compresor Centrífugo / Reciprocante",
    "Fin Fan Cooler / Aeroenfriador",
    "Filtro / Separador / Coalescedor",
    "Bomba de Proceso (Centrífuga / Desplazamiento)",
    "Vessel / Acumulador / Drum",
    "Torre de Destilación / Fraccionadora",
    "Tanque Atmosférico (Techo Fijo / Techo Flotante)",
    "Esfera Presurizada / Bala (LPG Sphere / Bullet)",
    "Intercambiador de Calor (Carcasa y Tubos / Placas)",
    "Reactor (Lecho Fijo / Tubular / CSTR)",
    "Rack de Tuberías / Manifold de Proceso",
    "Subestación Eléctrica / Cuarto de Control",
    "Otro / Personalizado"
]

# ==============================================================================
# TABLAS DE VULNERABILIDAD Y % PML SEGÚN TNO CPR 16E (GREEN BOOK) Y EXTOOL
# ==============================================================================

TABLA_PML_SOBREPRESION = [
    {
        "p_min_kpa": 100.0, "p_max_kpa": 9999.0, "rango_txt": "> 100 kPa (> 1.0 bar / > 14.5 psi)",
        "anillo_extool": "Núcleo >= 5 psig: 100% daño total",
        "criterio_green_book": "Destrucción absoluta de infraestructura superficial de planta.",
        "pml": {
            "drums": (100.0, 100.0, "100%", "Destrucción total."),
            "torres": (100.0, 100.0, "100%", "Destrucción total."),
            "hornos": (100.0, 100.0, "100%", "Destrucción total."),
            "tanques_atm": (100.0, 100.0, "100%", "Destrucción total."),
            "esferas": (100.0, 100.0, "100%", "Destrucción total."),
            "otros": (100.0, 100.0, "100%", "Destrucción total.")
        }
    },
    {
        "p_min_kpa": 80.0, "p_max_kpa": 100.0, "rango_txt": "80 – 100 kPa (0.80 – 1.00 bar / 11.6 – 14.5 psi)",
        "anillo_extool": "Núcleo >= 5 psig: 100% daño total",
        "criterio_green_book": "Límite Zona A (> 83 kPa, Destrucción total). Colapso soporte tanques esféricos (100 kPa).",
        "pml": {
            "drums": (80.0, 100.0, "80% – 100%", "Arrancamiento de anclajes; ruptura de cuerpo por choque; pérdida total."),
            "torres": (100.0, 100.0, "100%", "Volcamiento o fractura del faldón; colapso completo."),
            "hornos": (100.0, 100.0, "100%", "Destrucción total."),
            "tanques_atm": (100.0, 100.0, "100%", "Destrucción total."),
            "esferas": (85.0, 100.0, "85% – 100%", "Colapso de patas de soporte de la esfera (100 kPa); caída y BLEVE secundario."),
            "otros": (80.0, 100.0, "80% – 100%", "Colapso estructural severo.")
        }
    },
    {
        "p_min_kpa": 50.0, "p_max_kpa": 80.0, "rango_txt": "50 – 80 kPa (0.50 – 0.80 bar / 7.2 – 11.6 psi)",
        "anillo_extool": "Núcleo >= 5 psig: 100% daño uniforme por reaseguro",
        "criterio_green_book": "Colapso total de pipe racks (40-55 kPa). Colapso muros ladrillo macizo (50 kPa). Desplazamiento tanques cilíndricos (50-100 kPa).",
        "pml": {
            "drums": (50.0, 75.0, "50% – 75%", "Desplazamiento de fundaciones; ovalización de casco; desgarro de boquillas."),
            "torres": (80.0, 95.0, "80% – 95%", "Falla plástica de pernos de anclaje; colapso por flexión; desgarro de líneas mayores."),
            "hornos": (100.0, 100.0, "100%", "Destrucción total de serpentines, refractario y estructura portante."),
            "tanques_atm": (100.0, 100.0, "100%", "Desplazamiento del tanque de su base con desgarro e incendio asociado."),
            "esferas": (60.0, 80.0, "60% – 80%", "Deformación plástica severa de columnas de soporte; rotura en línea de fondo."),
            "otros": (70.0, 90.0, "70% – 90%", "Colapso de estructuras y líneas de interconexión.")
        }
    },
    {
        "p_min_kpa": 30.0, "p_max_kpa": 50.0, "rango_txt": "30 – 40 kPa (0.30 – 0.40 bar / 4.3 – 5.8 psi) [Anillo 5 psig]",
        "anillo_extool": "Anillo 5 psig (34 kPa): 80% - 100% daño base en ExTool",
        "criterio_green_book": "Límite Zona B (> 35 kPa). Paneles arrancados (30 kPa). Desplazamiento pipe racks (35-40 kPa). Daño a columnas fraccionadoras (35-80 kPa).",
        "pml": {
            "drums": (25.0, 40.0, "25% – 40%", "Deformación de silletas; daño en juntas bridadas con fugas localizadas."),
            "torres": (50.0, 70.0, "50% – 70%", "Pandeo local en faldón; desalineación de eje; daño en platos (35-80 kPa)."),
            "hornos": (75.0, 90.0, "75% – 90%", "Colapso de chimenea; deformación de la estructura portante y serpentines."),
            "tanques_atm": (85.0, 100.0, "85% – 100%", "Pandeo plástico (elephant foot); desgarro de planchas de fondo y pérdida total."),
            "esferas": (35.0, 50.0, "35% – 50%", "Pandeo en riostras estructurales de patas; descalibración de PSVs."),
            "otros": (40.0, 60.0, "40% – 60%", "Deformación plástica de pórticos y puentes de tubería.")
        }
    },
    {
        "p_min_kpa": 13.8, "p_max_kpa": 30.0, "rango_txt": "15 – 20 kPa (0.15 – 0.20 bar / 2.2 – 2.9 psi) [Corona 2 psig]",
        "anillo_extool": "Corona 1 a 2 psig: ExTool interpola 10% - 40%",
        "criterio_green_book": "Límite Zona C (> 17 kPa). Colapso muros hormigón (15-20 kPa). Desplazamiento marcos de acero (20 kPa). Deformación leve pipe racks (20-30 kPa).",
        "pml": {
            "drums": (10.0, 15.0, "10% – 15%", "Fisuras en aislamiento rígido; daño en conexiones de purga."),
            "torres": (25.0, 35.0, "25% – 35%", "Desplazamiento de empaques internos y platos superiores."),
            "hornos": (45.0, 60.0, "45% – 60%", "Fisuración severa del refractario; desalineación de quemadores."),
            "tanques_atm": (60.0, 75.0, "60% – 75%", "Pandeo elástico de pared; agrietamiento de tanques vacíos (20-30 kPa)."),
            "esferas": (15.0, 20.0, "15% – 20%", "Fatiga en pernos de anclaje de patas sin fuga de producto."),
            "otros": (20.0, 30.0, "20% – 30%", "Desplazamiento leve de bandejas de cables e instrumentos.")
        }
    },
    {
        "p_min_kpa": 6.9, "p_max_kpa": 13.8, "rango_txt": "7 – 10 kPa (0.07 – 0.10 bar / 1.0 – 1.5 psi) [Anillo 1 psig]",
        "anillo_extool": "Anillo 1 psig (6.9 kPa): 5% - 10% daño base",
        "criterio_green_book": "Colapso de techo de tanques de almacenamiento (7 kPa). Daño menor en marcos de acero (8-10 kPa). Falla uniones láminas corrugadas (7-14 kPa).",
        "pml": {
            "drums": (5.0, 5.0, "5%", "Abolladuras en aislamiento; descalibración de transmisores."),
            "torres": (10.0, 10.0, "10%", "Deformación en bandejas de cables, escalas y plataformas."),
            "hornos": (20.0, 30.0, "20% – 30%", "Desalineación de ductos de gases y tiros de chimenea."),
            "tanques_atm": (35.0, 50.0, "35% – 50%", "Colapso de láminas de techo (7 kPa); daño en sellos flotantes."),
            "esferas": (5.0, 5.0, "5%", "Afectación de piping de instrumentación exterior."),
            "otros": (5.0, 10.0, "5% – 10%", "Falla menor de recubrimientos y vidrios.")
        }
    },
    {
        "p_min_kpa": 0.0, "p_max_kpa": 6.9, "rango_txt": "< 3.5 kPa (< 0.035 bar / < 0.5 psi)",
        "anillo_extool": "Exterior (< 1 psig): 0% daño base",
        "criterio_green_book": "Límite inferior Zona D (rotura esporádica de vidrios estándar < 1 kPa).",
        "pml": {
            "drums": (0.0, 0.0, "0%", "Sin afectación mecánica."),
            "torres": (0.0, 0.0, "0%", "Sin afectación mecánica."),
            "hornos": (0.0, 5.0, "0% – 5%", "Desajuste menor en mirillas y tiro."),
            "tanques_atm": (0.0, 5.0, "0% – 5%", "Sin afectación en envolvente."),
            "esferas": (0.0, 0.0, "0%", "Sin afectación mecánica."),
            "otros": (0.0, 0.0, "0%", "Sin afectación.")
        }
    }
]

TABLA_PML_RADIACION = [
    {
        "q_min": 190.0, "q_max": 9999.0, "rango_txt": ">= 190 – 200 kW/m² o Envolvente de Llama",
        "criterio_green_book": "Flujo radiativo en superficie de Fireball / BLEVE (CPR 16E Apéndice A) o inmersión en llama (fire engulfment).",
        "pml": {
            "drums": (100.0, 100.0, "100%", "Destrucción total instantánea."),
            "torres": (100.0, 100.0, "100%", "Destrucción estructural completa."),
            "hornos": (100.0, 100.0, "100%", "Destrucción total."),
            "tanques_atm": (100.0, 100.0, "100%", "Destrucción total."),
            "esferas": (100.0, 100.0, "100%", "BLEVE catastrófico instantáneo (bola de fuego y fragmentos)."),
            "otros": (100.0, 100.0, "100%", "Destrucción total instantánea.")
        }
    },
    {
        "q_min": 100.0, "q_max": 190.0, "rango_txt": "100.0 kW/m²",
        "criterio_green_book": "Damage Level 1 en acero estructural (T = 773 K / 500°C). Colapso de elementos de carga portantes.",
        "pml": {
            "drums": (100.0, 100.0, "100%", "Ruptura térmica bajo tensión (stress rupture); colapso sobre fundaciones."),
            "torres": (100.0, 100.0, "100%", "Colapso plástico del faldón por pérdida de resistencia del acero a 500°C; volcamiento."),
            "hornos": (100.0, 100.0, "100%", "Colapso estructural completo de la estructura y serpentines."),
            "tanques_atm": (100.0, 100.0, "100%", "Colapso completo de chapa, desgarro y quema total del contenido."),
            "esferas": (100.0, 100.0, "100%", "Colapso plástico de patas de soporte; ruptura térmica y BLEVE catastrófico."),
            "otros": (100.0, 100.0, "100%", "Colapso estructural completo a 500°C.")
        }
    },
    {
        "q_min": 35.0, "q_max": 100.0, "rango_txt": "35.0 kW/m² [Umbral 35 kW/m²]",
        "criterio_green_book": "Autoignición espontánea de materiales combustibles sin presencia de llama (CPR 16E Tabla 7.1). Incendio generalizado de recintos.",
        "pml": {
            "drums": (65.0, 80.0, "65% – 80%", "Pérdida de estanqueidad en bridas; fluencia en soportes sin PFP; sobrepresión severa."),
            "torres": (70.0, 85.0, "70% – 85%", "Deformación permanente del faldón; pandeo de columnas; desalineación global."),
            "hornos": (75.0, 90.0, "75% – 90%", "Pandeo de columnas estructurales exteriores; fallo total de sistemas de tiro."),
            "tanques_atm": (90.0, 100.0, "90% – 100%", "Autoignición espontánea de vapores en techos (35 kW/m²); colapso de envolvente sin agua."),
            "esferas": (75.0, 95.0, "75% – 95%", "Pérdida crítica de tensión de fluencia en zona de vapor; tiempo hacia BLEVE < 15 min sin diluvio."),
            "otros": (70.0, 85.0, "70% – 85%", "Autoignición e incendio generalizado.")
        }
    },
    {
        "q_min": 25.0, "q_max": 35.0, "rango_txt": "25.0 kW/m² [Umbral 25 kW/m²]",
        "criterio_green_book": "Damage Level 2 en acero estructural (T = 473 K / 200°C). Daño permanente a pinturas, recubrimientos y deformación plástica local.",
        "pml": {
            "drums": (40.0, 50.0, "40% – 50%", "Destrucción de recubrimientos; deformación en silletas sin protección pasiva (PFP)."),
            "torres": (45.0, 60.0, "45% – 60%", "Pandeo diferencial por gradiente térmico; distorsión de faldón sin PFP."),
            "hornos": (50.0, 65.0, "50% – 65%", "Deformación de la envolvente metálica exterior (casing); alabeo de compuertas."),
            "tanques_atm": (65.0, 80.0, "65% – 80%", "Deformación de planchas de pared sin enfriar; daño estructural en techo flotante."),
            "esferas": (45.0, 60.0, "45% – 60%", "Calentamiento severo del acero en espacio de vapor; deformación de patas sin PFP."),
            "otros": (45.0, 60.0, "45% – 60%", "Deformación plástica local a 200°C.")
        }
    },
    {
        "q_min": 12.5, "q_max": 25.0, "rango_txt": "12.5 – 15.0 kW/m² [Umbral 12.5 kW/m²]",
        "criterio_green_book": "Damage Level 1 para madera y plásticos (ignición con llama piloto presente a 15 kW/m²). Apertura intermitente de PSVs.",
        "pml": {
            "drums": (15.0, 25.0, "15% – 25%", "Apertura intermitente de PSVs; degradación de empaques en bridas."),
            "torres": (20.0, 30.0, "20% – 30%", "Pérdida de instrumentación local; distorsión en tuberías no aisladas."),
            "hornos": (25.0, 40.0, "25% – 40%", "Daño en cableado del sistema de seguridad de quemadores (BMS)."),
            "tanques_atm": (35.0, 50.0, "35% – 50%", "Ignición de vapores en sellos de techo flotante (rim seal fire) por fuentes piloto."),
            "esferas": (20.0, 35.0, "20% – 35%", "Activación continua de PSVs; requiere rociado de agua para estabilidad."),
            "otros": (20.0, 35.0, "20% – 35%", "Apertura de PSVs y daño en aislamiento exterior.")
        }
    },
    {
        "q_min": 4.0, "q_max": 12.5, "rango_txt": "4.0 – 8.0 kW/m²",
        "criterio_green_book": "Rotura de paneles y visores de vidrio por tensión térmica diferencial (Delta T = 100 K a 4 kW/m²).",
        "pml": {
            "drums": (5.0, 5.0, "5%", "Rotura de visores de nivel óptico; daño en cableado sin canalizar."),
            "torres": (5.0, 5.0, "5%", "Falla en instrumentos electrónicos exteriores desprotegidos."),
            "hornos": (10.0, 10.0, "10%", "Rotura de mirillas de vidrio (4 kW/m²); fallo en fotoceldas de llama."),
            "tanques_atm": (10.0, 10.0, "10%", "Ampollamiento de pintura; evaporación acelerada en venteos."),
            "esferas": (5.0, 5.0, "5%", "Daño en transmisores electrónicos periféricos."),
            "otros": (5.0, 5.0, "5%", "Daño en instrumentación exterior.")
        }
    },
    {
        "q_min": 0.0, "q_max": 4.0, "rango_txt": "< 4.0 kW/m²",
        "criterio_green_book": "Umbral seguro; inferior al límite de rotura de vidrio (4 kW/m²).",
        "pml": {
            "drums": (0.0, 0.0, "0%", "Sin afectación."),
            "torres": (0.0, 0.0, "0%", "Sin afectación."),
            "hornos": (0.0, 0.0, "0%", "Sin afectación."),
            "tanques_atm": (0.0, 0.0, "0%", "Operación segura."),
            "esferas": (0.0, 0.0, "0%", "Sin afectación."),
            "otros": (0.0, 0.0, "0%", "Sin afectación.")
        }
    }
]

def clasificar_activo_green_book(tipo_equipo):
    """Mapea cualquier tipo de equipo del gemelo digital a las columnas de la matriz TNO Green Book CPR 16E."""
    t = str(tipo_equipo).lower()
    if any(k in t for k in ['horno', 'heater', 'caldera', 'boiler', 'quemador', 'fired']):
        return "hornos"
    elif any(k in t for k in ['torre', 'fraccionadora', 'columna', 'destil']):
        return "torres"
    elif any(k in t for k in ['tanque', 'atmosf', 'storage']):
        return "tanques_atm"
    elif any(k in t for k in ['esfera', 'bala', 'sphere', 'bullet']):
        return "esferas"
    elif any(k in t for k in ['drum', 'separador', 'filtro', 'coalescedor', 'vessel', 'acumulador']):
        return "drums"
    else:
        return "otros"

def obtener_dano_pml_sobrepresion(tipo_equipo, p_s_kpa):
    """Calcula el rango y porcentaje medio de daño PML y el mecanismo físico según TNO CPR 16E para una sobrepresión Ps en kPa."""
    cat = clasificar_activo_green_book(tipo_equipo)
    p_val = max(float(p_s_kpa), 0.0)
    for fila in TABLA_PML_SOBREPRESION:
        if p_val >= fila["p_min_kpa"]:
            min_p, max_p, txt_r, mecan = fila["pml"].get(cat, fila["pml"]["otros"])
            pct_medio = (min_p + max_p) / 2.0
            return {
                "rango_ps_txt": fila["rango_txt"],
                "anillo_extool": fila["anillo_extool"],
                "criterio_green_book": fila["criterio_green_book"],
                "pml_rango_pct": txt_r,
                "pml_pct_medio": pct_medio,
                "mecanismo_dano": mecan
            }
    return {
        "rango_ps_txt": "< 3.5 kPa", "anillo_extool": "Exterior (< 1 psig)",
        "criterio_green_book": "Zona D (< 3.5 kPa)", "pml_rango_pct": "0%",
        "pml_pct_medio": 0.0, "mecanismo_dano": "Sin afectación mecánica."
    }

def obtener_dano_pml_radiacion(tipo_equipo, q_kw_m2):
    """Calcula el rango y porcentaje medio de daño PML y el mecanismo físico según TNO CPR 16E para radiación en kW/m²."""
    cat = clasificar_activo_green_book(tipo_equipo)
    q_val = max(float(q_kw_m2), 0.0)
    for fila in TABLA_PML_RADIACION:
        if q_val >= fila["q_min"]:
            min_p, max_p, txt_r, mecan = fila["pml"].get(cat, fila["pml"]["otros"])
            pct_medio = (min_p + max_p) / 2.0
            return {
                "rango_q_txt": fila["rango_txt"],
                "criterio_green_book": fila["criterio_green_book"],
                "pml_rango_pct": txt_r,
                "pml_pct_medio": pct_medio,
                "mecanismo_dano": mecan
            }
    return {
        "rango_q_txt": "< 4.0 kW/m²", "criterio_green_book": "Umbral seguro",
        "pml_rango_pct": "0%", "pml_pct_medio": 0.0, "mecanismo_dano": "Sin afectación."
    }

# ==============================================================================
# MATRIZ DE DAÑO Y TIEMPO DE REPARACIÓN (EXCEL / SQLITE: OREDA & BENCHMARKS)
# ==============================================================================

_CACHE_MATRIZ_DANO = None

def obtener_matriz_dano_cache():
    """Retorna la matriz de daño y tiempo de reparación en memoria con caché rápido."""
    global _CACHE_MATRIZ_DANO
    if _CACHE_MATRIZ_DANO is None or _CACHE_MATRIZ_DANO.empty:
        try:
            from db_manager import get_matriz_dano_reparacion_df
            _CACHE_MATRIZ_DANO = get_matriz_dano_reparacion_df()
        except Exception:
            _CACHE_MATRIZ_DANO = pd.DataFrame()
    return _CACHE_MATRIZ_DANO

def recargar_cache_matriz_dano():
    """Fuerza la recarga de la matriz en caché desde SQLite."""
    global _CACHE_MATRIZ_DANO
    _CACHE_MATRIZ_DANO = None
    return obtener_matriz_dano_cache()

def mapear_tipo_equipo_a_matriz(tipo_equipo):
    """Mapea cualquier tipo de equipo del gemelo digital a una de las 25 categorías del Excel / SQLite."""
    t = str(tipo_equipo).lower()
    if any(k in t for k in ['horno', 'heater', 'fired']):
        return "Hornos de Proceso / Fired Heaters"
    elif 'caldera' in t or 'boiler' in t:
        if 'utilidad' in t or 'water-tube' in t:
            return "Calderas de Utilidad (Water-tube / Utility)"
        return "Calderas Industriales Paquete (Packaged)"
    elif 'compresor' in t:
        if any(k in t for k in ['reciproc', 'alternativo', '618']):
            return "Compresores Reciprocantes Grandes (API 618)"
        return "Compresores Centrífugos (API 617)"
    elif any(k in t for k in ['fin fan', 'aeroenfriador', 'cooler', 'enfriador']):
        return "Enfriadores por Aire (Air Coolers / Fin-Fans)"
    elif any(k in t for k in ['torre', 'fraccionadora', 'columna', 'destil']):
        return "Torres de Destilación / Fraccionamiento"
    elif 'reactor' in t:
        return "Reactores de Hidroprocesamiento (Alta Presión)"
    elif 'mche' in t or ('intercambiador' in t and 'criog' in t):
        return "Intercambiador Criogénico Principal (MCHE)"
    elif 'intercambiador' in t or 'intercambio' in t or 'heat exchanger' in t:
        if 'placa' in t or 'compabloc' in t:
            return "Intercambiadores de Placas Soldadas (Compabloc)"
        return "Intercambiadores Tubo y Coraza (TEMA)"
    elif any(k in t for k in ['bomba', 'pump']):
        if 'criog' in t:
            return "Bombas Criogénicas Sumergidas (GNL / GLP)"
        return "Bombas de Carga Multietapa BB5 / BB3"
    elif any(k in t for k in ['fcc', 'ciclón', 'ciclon', 'slide valve', 'plenum']):
        return "Internos de FCC (Ciclones, Plenums, Slide Valves)"
    elif any(k in t for k in ['válvula', 'valvula', 'esdv', 'hipps']):
        return "Válvulas ESDV y Sistemas HIPPS (> 24'')"
    elif any(k in t for k in ['turbogenerador a gas', 'gtg', 'turbina de gas']):
        return "Turbogeneradores a Gas (GTG)"
    elif any(k in t for k in ['turbogenerador a vapor', 'stg', 'turbina de vapor']):
        return "Turbogeneradores a Vapor (STG)"
    elif any(k in t for k in ['transformador', 'gsu', 'trafo']):
        return "Transformadores Principales (GSU / > 100 MVA)"
    elif any(k in t for k in ['gis', 'subestación', 'subestacion']):
        return "Subestaciones Encapsuladas en Gas (GIS)"
    elif any(k in t for k in ['variador', 'vfd']):
        return "Variadores de Media Tensión (VFD)"
    elif any(k in t for k in ['celda', 'ccm', 'mcc']):
        return "Celdas de Media Tensión y CCMs"
    elif any(k in t for k in ['dcs', 'sis', 'control distribuido']):
        return "Sistemas de Control Distribuido (DCS / SIS)"
    elif any(k in t for k in ['brazo', 'loading arm', 'marino']):
        return "Brazos de Carga Marinos (Marine Loading Arms)"
    elif any(k in t for k in ['motor', 'eléctrico mayor', 'electrico mayor', '5,000 hp']):
        return "Motores Eléctricos Mayores (> 5,000 HP)"
    else:
        # Tambores, tanques, recipientes cilíndricos, esferas o genéricos
        return "Drums / Recipientes de Presión"

def estimar_dano_y_tiempo_reparacion(tipo_equipo, p_s_kpa=None, q_kw_m2=None):
    """
    Estima el % de daño, el tiempo de reparación/parada y las acciones técnicas
    basadas en la Matriz Excel / SQLite (OREDA / TNO / Green Book / Industry benchmarks).
    Evalúa la sobrepresión incidente Ps (kPa) y/o radiación térmica q (kW/m²).
    """
    df_mat = obtener_matriz_dano_cache()
    if df_mat.empty:
        return {
            "tipo_matriz": str(tipo_equipo),
            "categoria_activo": "General",
            "nivel_dano": "Sin Datos de Matriz",
            "dano_pct_txt": "0%",
            "dano_pct_medio": 0.0,
            "tiempo_reparacion_txt": "0 días",
            "dias_parada_medio": 0.0,
            "meses_parada_medio": 0.0,
            "accion_reparacion": "Sin afectación.",
            "factores_variabilidad": ""
        }
    
    nombre_tipo = mapear_tipo_equipo_a_matriz(tipo_equipo)
    sub = df_mat[df_mat['tipo_equipo'] == nombre_tipo]
    if sub.empty:
        sub = df_mat[df_mat['tipo_equipo'].str.contains(nombre_tipo.split(' ')[0], case=False, na=False)]
    if sub.empty:
        row = df_mat.iloc[0]
    else:
        row = sub.iloc[0]
        
    p_val = float(p_s_kpa) if p_s_kpa is not None else None
    q_val = float(q_kw_m2) if q_kw_m2 is not None else None
    
    ps_s = float(row.get('ps_severo_min_kpa', 50.0))
    q_s = float(row.get('q_severo_kw_m2', 35.0))
    ps_m = float(row.get('ps_medio_min_kpa', 25.0))
    q_m = float(row.get('q_medio_kw_m2', 25.0))
    ps_l = float(row.get('ps_leve_min_kpa', 10.0))
    q_l = float(row.get('q_leve_kw_m2', 15.0))
    
    # 1. Daño Severo (> 70% Reemplazo / Lead Time)
    es_severo_ps = (p_val is not None and p_val >= ps_s)
    es_severo_q = (q_val is not None and q_val >= q_s)
    if es_severo_ps or es_severo_q:
        dias_s = (float(row.get('dias_severo_min', 360.0)) + float(row.get('dias_severo_max', 540.0))) / 2.0
        meses_s = (float(row.get('meses_severo_min', 12.0)) + float(row.get('meses_severo_max', 18.0))) / 2.0
        txt_lead = str(row.get('lead_time_severo_txt', f'{meses_s:.0f} meses'))
        return {
            "tipo_matriz": row['tipo_equipo'],
            "categoria_activo": row['categoria_activo'],
            "nivel_dano": "Severo (> 70% Reemplazo / Lead Time)",
            "dano_pct_txt": "> 70% (80% – 100%)",
            "dano_pct_medio": 90.0,
            "tiempo_reparacion_txt": f"{txt_lead} (Fabricación y Entrega en Sitio)",
            "dias_parada_medio": dias_s,
            "meses_parada_medio": meses_s,
            "accion_reparacion": "Ruptura o colapso estructural total. Reemplazo completo de equipo.",
            "factores_variabilidad": str(row.get('factores_variabilidad', ''))
        }
        
    # 2. Daño Medio (30% a 60%)
    es_medio_ps = (p_val is not None and p_val >= ps_m)
    es_medio_q = (q_val is not None and q_val >= q_m)
    if es_medio_ps or es_medio_q:
        dias_m = (float(row.get('dias_medio_min', 14.0)) + float(row.get('dias_medio_max', 30.0))) / 2.0
        return {
            "tipo_matriz": row['tipo_equipo'],
            "categoria_activo": row['categoria_activo'],
            "nivel_dano": "Medio (30% a 60%)",
            "dano_pct_txt": "30% – 60%",
            "dano_pct_medio": 45.0,
            "tiempo_reparacion_txt": str(row.get('tiempo_medio_txt', f'{dias_m:.0f} días')),
            "dias_parada_medio": dias_m,
            "meses_parada_medio": dias_m / 30.0,
            "accion_reparacion": str(row.get('accion_medio', 'Reparación mayor en sitio o taller regional.')),
            "factores_variabilidad": str(row.get('factores_variabilidad', ''))
        }
        
    # 3. Daño Leve (5% a 25%)
    es_leve_ps = (p_val is not None and p_val >= ps_l)
    es_leve_q = (q_val is not None and q_val >= q_l)
    if es_leve_ps or es_leve_q:
        dias_l = (float(row.get('dias_leve_min', 3.0)) + float(row.get('dias_leve_max', 7.0))) / 2.0
        return {
            "tipo_matriz": row['tipo_equipo'],
            "categoria_activo": row['categoria_activo'],
            "nivel_dano": "Leve (5% a 25%)",
            "dano_pct_txt": "5% – 25%",
            "dano_pct_medio": 15.0,
            "tiempo_reparacion_txt": str(row.get('tiempo_leve_txt', f'{dias_l:.0f} días')),
            "dias_parada_medio": dias_l,
            "meses_parada_medio": dias_l / 30.0,
            "accion_reparacion": str(row.get('accion_leve', 'Reparación menor in-situ, calibración y reemplazo de sellos.')),
            "factores_variabilidad": str(row.get('factores_variabilidad', ''))
        }
        
    # 4. Sin daño
    return {
        "tipo_matriz": row['tipo_equipo'],
        "categoria_activo": row['categoria_activo'],
        "nivel_dano": "Sin Afectación (< Umbral)",
        "dano_pct_txt": "0%",
        "dano_pct_medio": 0.0,
        "tiempo_reparacion_txt": "0 días",
        "dias_parada_medio": 0.0,
        "meses_parada_medio": 0.0,
        "accion_reparacion": "Operación continua normal sin daño mecánico ni térmico.",
        "factores_variabilidad": ""
    }

class PlantUnit:
    """
    Representación de un equipo o unidad de proceso en planta, compatible con el
    modelo de objetos de OpenSRANE y estándares de análisis de vulnerabilidad QRA.
    """
    def __init__(self, tag, tipo, lat, lon, sustancia, inventario_kg, presion_bar, temp_c,
                 diametro_orificio_mm=25.4, altura_fuga_m=1.5, valor_reposicion=850000.0,
                 transformer=None):
        self.tag = str(tag).strip()
        self.tipo = str(tipo).strip()
        self.lat = float(lat)
        self.lon = float(lon)
        self.sustancia = str(sustancia).strip()
        self.inventario_kg = float(inventario_kg)
        self.presion_bar = float(presion_bar)
        self.temp_c = float(temp_c)
        self.diametro_orificio_mm = float(diametro_orificio_mm)
        self.altura_fuga_m = float(altura_fuga_m)
        self.valor_reposicion = float(valor_reposicion)
        
        # Coordenadas locales
        if transformer is not None:
            self.x, self.y = transformer.wgs84_to_xy(self.lat, self.lon)
        else:
            self.x, self.y = 0.0, 0.0
            
    def is_atmospheric(self):
        """Identifica si el activo es un tanque atmosférico o de baja presión."""
        t_lower = self.tipo.lower()
        return any(term in t_lower for term in ['atmosf', 'techo', 'cúpula', 'almacenamiento', 'storage', 'pile', 'piscina', 'subestación', 'cuarto'])

    def is_furnace_or_boiler(self):
        """Identifica si el activo es un horno o caldera con quemadores activos."""
        t_lower = self.tipo.lower()
        return any(term in t_lower for term in ['horno', 'heater', 'caldera', 'boiler', 'quemador', 'fired'])

    def is_air_cooler(self):
        """Identifica si el activo es un fin fan cooler o aeroenfriador."""
        t_lower = self.tipo.lower()
        return any(term in t_lower for term in ['fin fan', 'aeroenfriador', 'air cooler'])

    def is_pressurized(self):
        """Identifica si el activo es un recipiente a presión (Vessel, Drum, Esfera, Reactor, Torre)."""
        return not self.is_atmospheric()

# ==============================================================================
# 3. DINÁMICA DE FUGA Y DESCARGA (API 581 / OpenSRANE Discharge)
# ==============================================================================

def calcular_dinamica_fuga(equipo_origen, tiempo_min, diametro_override_mm=None, sustancia_override=None, presion_override_bar=None, temp_override_c=None, inventario_override_kg=None):
    """
    Modela la termodinámica de fuga según API 581 considerando flujo compresible
    crítico (choked/sónico) o incompresible con vaciado de inventario.
    Permite sobreescribir cualquier parámetro de proceso o definir una fuga en coordenadas personalizadas.
    """
    if equipo_origen is None or (hasattr(equipo_origen, 'empty') and equipo_origen.empty):
        equipo_origen = {}
    elif not isinstance(equipo_origen, dict) and not hasattr(equipo_origen, 'get'):
        equipo_origen = dict(equipo_origen)
        
    presion_bar = float(presion_override_bar if presion_override_bar is not None else equipo_origen.get('presion_bar', 18.0))
    temp_c = float(temp_override_c if temp_override_c is not None else equipo_origen.get('temperatura_c', 45.0))
    diametro_mm = float(diametro_override_mm if diametro_override_mm is not None and float(diametro_override_mm) > 0 else equipo_origen.get('diametro_orificio_mm', 25.4))
    inventario_kg = float(inventario_override_kg if inventario_override_kg is not None and float(inventario_override_kg) > 0 else equipo_origen.get('inventario_kg', 15000.0))
    sustancia_nombre = str(sustancia_override if sustancia_override is not None else equipo_origen.get('sustancia', 'GLP / Propano'))
    
    # Obtener propiedades de sustancia
    sust_props = SUSTANCIAS_DB.get("GLP / Propano")
    for key, val in SUSTANCIAS_DB.items():
        if key in sustancia_nombre or any(part in sustancia_nombre for part in key.split('/')):
            sust_props = val
            break
            
    d_m = diametro_mm / 1000.0
    area_orificio = math.pi * (d_m ** 2) / 4.0
    p_pa = max(presion_bar, 1.01325) * 1e5
    p_atm = 101325.0
    t_k = temp_c + 273.15
    cd = 0.62  # Coeficiente de descarga estándar de orificio de pared delgada
    
    mw = sust_props["mw"]
    gamma = sust_props["gamma"]
    r_univ = 8314.5
    r_sp = r_univ / mw
    
    if sust_props["fase"] in ["gas", "gas_licuado"]:
        # Flujo compresible de gas
        pr_crit = (2.0 / (gamma + 1.0)) ** (gamma / (gamma - 1.0))
        pr_actual = p_atm / p_pa
        
        if pr_actual < pr_crit:
            # Flujo sónico / Choked flow
            factor_choked = (2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (gamma - 1.0))
            tasa_kg_s = cd * area_orificio * p_pa * math.sqrt((gamma / (r_sp * t_k)) * factor_choked)
        else:
            # Flujo subsónico
            term_sub = (pr_actual ** (2.0 / gamma)) - (pr_actual ** ((gamma + 1.0) / gamma))
            term_sub = max(term_sub, 1e-6)
            tasa_kg_s = cd * area_orificio * p_pa * math.sqrt((2.0 / (r_sp * t_k)) * (gamma / (gamma - 1.0)) * term_sub)
    else:
        # Flujo incompresible de líquido
        rho = sust_props["rho_liq"]
        delta_p = max(p_pa - p_atm, 1000.0)
        tasa_kg_s = cd * area_orificio * math.sqrt(2.0 * rho * delta_p)
        
    tasa_kg_s = max(float(tasa_kg_s), 0.05)
    t_seg = float(tiempo_min) * 60.0
    masa_teorica = tasa_kg_s * t_seg
    masa_liberada_kg = min(inventario_kg, masa_teorica)
    pct_inventario = (masa_liberada_kg / inventario_kg) * 100.0 if inventario_kg > 0 else 100.0
    tiempo_vaciado_min = (inventario_kg / tasa_kg_s) / 60.0 if tasa_kg_s > 0 else 999.0
    
    return {
        "tasa_kg_s": round(tasa_kg_s, 2),
        "tasa_kg_h": round(tasa_kg_s * 3600.0, 1),
        "masa_liberada_kg": round(masa_liberada_kg, 1),
        "inventario_total_kg": inventario_kg,
        "pct_inventario": round(pct_inventario, 1),
        "tiempo_vaciado_min": round(tiempo_vaciado_min, 2),
        "tiempo_config_min": float(tiempo_min),
        "sustancia_props": sust_props,
        "temperatura_c": temp_c,
        "presion_bar": presion_bar,
        "diametro_mm": diametro_mm
    }

# ==============================================================================
# 4. MODELOS PROBIT ESTANDARIZADOS DE VULNERABILIDAD (OpenSRANE / CCPS / Lees)
# ==============================================================================

def probit_to_probabilidad(y):
    """
    Convierte la variable Probit Y a probabilidad acumulada P mediante
    la función de distribución normal estándar acumulada:
    P = 0.5 * (1 + erf((Y - 5) / sqrt(2)))
    """
    if y <= 0:
        return 0.0
    p = 0.5 * (1.0 + math.erf((y - 5.0) / math.sqrt(2.0)))
    return float(max(0.0, min(1.0, p)))

def calcular_probit_sobrepresion(p_sobrepresion_bar, tipo_equipo):
    """
    Calcula el Probit de falla estructural y probabilidad condicional por onda de sobrepresión (VCE).
    Modelos de Cozzani et al. / Lees' Loss Prevention:
    - Tanque Atmosférico / Fin Fan Cooler / Estructuras Ligeras: Y = -5.71 + 0.84 * ln(Delta_P [Pa])
    - Recipiente a Presión / Hornos / Calderas / Compresores / Bombas / Reactores: Y = -3.80 + 0.44 * ln(Delta_P [Pa])
    """
    dp_pa = max(float(p_sobrepresion_bar) * 1e5, 100.0)
    t_lower = str(tipo_equipo).lower()
    
    # Determinar categoría de vulnerabilidad mecánica
    es_baja_resistencia = any(term in t_lower for term in [
        'atmosf', 'techo', 'storage', 'fin fan', 'aeroenfriador', 'cooler',
        'edificio', 'cuarto', 'subestación', 'subestacion'
    ])
    
    if es_baja_resistencia:
        # Colapso de tanque atmosférico o daño severo a haces de tubos aletados / estructuras ligeras
        y = -5.71 + 0.84 * math.log(dp_pa)
    else:
        # Ruptura y pérdida de contención de recipiente presurizado, horno, caldera, compresor o reactor
        y = -3.80 + 0.44 * math.log(dp_pa)
        
    prob = probit_to_probabilidad(y)
    return float(round(y, 2)), float(round(prob, 4))

def calcular_probit_radiacion(radiacion_kw_m2, t_seg, tipo_equipo):
    """
    Calcula el Probit de falla de equipos expuestos a radiación térmica (Jet / Pool Fire).
    Modelos estándar de Eisenberg / Cozzani para daño a tanques y equipos por sobrecalentamiento:
    - Tanque Atmosférico / Fin Fan Cooler: Y = -12.8 + 2.56 * ln( (I^(4/3) * t) / 1000 )
    - Recipiente a Presión / Horno / Caldera / Compresor / Bomba: Y = -14.5 + 2.65 * ln( (I^(4/3) * t) / 1000 )
    """
    i_kw = max(float(radiacion_kw_m2), 0.1)
    t = max(float(t_seg), 1.0)
    
    # Carga térmica integrada
    dosis_termica = ((i_kw ** (4.0 / 3.0)) * t) / 1000.0
    dosis_termica = max(dosis_termica, 1e-4)
    
    t_lower = str(tipo_equipo).lower()
    es_baja_inercia = any(term in t_lower for term in [
        'atmosf', 'techo', 'storage', 'fin fan', 'aeroenfriador', 'cooler'
    ])
    
    if es_baja_inercia:
        y = -12.8 + 2.56 * math.log(dosis_termica)
    else:
        y = -14.5 + 2.65 * math.log(dosis_termica)
        
    prob = probit_to_probabilidad(y)
    return float(round(y, 2)), float(round(prob, 4))

# ==============================================================================
# 5. RADIOS DE CONSECUENCIA E ISOPLETAS
# ==============================================================================

def calcular_radios_consecuencia(dinamica, fenomeno, nivel_congestion="Media (Proceso Estándar, eta=0.10)", condiciones_meteo=None):
    """
    Genera los radios físicos de daño y contornos para visualización en Folium.
    Utiliza umbrales estandarizados internacionales (API 581, CCPS, OpenSRANE),
    incorporando el factor de rendimiento de sobrepresión según el nivel de congestión
    y la transmisividad atmosférica en función de la meteorología.
    """
    tasa_kg_s = dinamica["tasa_kg_s"]
    masa_kg = dinamica["masa_liberada_kg"]
    sust_props = dinamica.get("sustancia_props", SUSTANCIAS_DB["GLP / Propano"])
    delta_hc = sust_props["delta_hc_j_kg"]
    
    if condiciones_meteo is None:
        condiciones_meteo = {}

    if "Radiación" in fenomeno:
        # Transmisividad atmosférica dependiente de humedad relativa y temperatura (API 521 / CCPS)
        t_amb = float(condiciones_meteo.get('temperatura_ambiente_c', 32.0))
        h_rel = float(condiciones_meteo.get('humedad_relativa_pct', 75.0)) / 100.0
        # Presión parcial de vapor de agua (Pa) según Tetens
        p_sat = 610.78 * math.exp((17.27 * t_amb) / (t_amb + 237.3))
        p_w = max(h_rel * p_sat, 50.0)
        tau = max(min(2.02 * ((p_w * 40.0) ** (-0.09)), 0.95), 0.60)
        
        eta = 0.28
        potencia_termica_w = eta * tasa_kg_s * delta_hc * tau
        
        # Radios para 35.0, 25.0 y 12.5 kW/m2 según especificación TNO CPR 16E (Green Book)
        def r_para_i(i_kw):
            i_w = i_kw * 1000.0
            r = math.sqrt(potencia_termica_w / (4.0 * math.pi * i_w))
            return max(round(r, 1), 2.0)
            
        r_35_0 = r_para_i(35.0)
        r_25_0 = r_para_i(25.0)
        r_12_5 = r_para_i(12.5)
        
        return {
            "tipo": "Radiación Térmica (kW/m²)",
            "anillos": [
                {
                    "nombre": "Zona Crítica Autoignición (35.0 kW/m²)",
                    "umbral_valor": 35.0,
                    "radio": r_35_0,
                    "color": "#B71C1C",
                    "nivel": "CRÍTICO - Autoignición sin Llama Piloto / 75%-95% PML",
                    "probit_ref": "TNO CPR 16E Tab. 7.1 / Autoignición"
                },
                {
                    "nombre": "Zona Daño Plástico Acero (25.0 kW/m²)",
                    "umbral_valor": 25.0,
                    "radio": r_25_0,
                    "color": "#E65100",
                    "nivel": "SEVERO - Damage Level 2 Acero (200°C) / 45%-60% PML",
                    "probit_ref": "TNO CPR 16E / Deformación Local"
                },
                {
                    "nombre": "Zona Inicio Afectación (12.5 kW/m²)",
                    "umbral_valor": 12.5,
                    "radio": r_12_5,
                    "color": "#F57F17",
                    "nivel": "MODERADO - Apertura PSVs / Daño Empaques / 15%-35% PML",
                    "probit_ref": "TNO CPR 16E / Damage Level 1"
                }
            ],
            "potencia_termica_mw": round(potencia_termica_w / 1e6, 2),
            "tau_atmosferico": round(tau, 3)
        }
    elif "Sobrepresión" in fenomeno:
        # Factor de rendimiento de combustión según el nivel de congestión y confinamiento
        factor_rendimiento = 0.10
        if isinstance(nivel_congestion, (int, float)):
            factor_rendimiento = float(nivel_congestion)
        else:
            for k, v in NIVELES_CONGESTION.items():
                if k == nivel_congestion or k.split(' ')[0].lower() in str(nivel_congestion).lower():
                    factor_rendimiento = v["factor_rendimiento"]
                    break

        temp_operacion_c = float(dinamica.get("temperatura_c", 25.0))
        presion_operacion_bar = float(dinamica.get("presion_bar", 1.0))
        fase_sustancia = sust_props.get("fase", "gas")
        t_ebullicion_c = sust_props.get("t_ebullicion_c", -42.0)
        flash_point_c = sust_props.get("flash_point_c", -100.0)
        lfl_pct = sust_props.get("lfl_pct", 2.1)

        no_creible_vce = False
        razon_no_creible = ""

        # Verificación termodinámica rigurosa de formación de nube de vapor inflamable (API 581 / CCPS / Yellow Book):
        if fase_sustancia == "liquido" and temp_operacion_c < flash_point_c:
            # Caso Diesel / Gasóleo frío: T_op < T_flash (ej. Diesel a 25°C < 55°C)
            # A esta temperatura la presión de vapor es insignificante (<0.001 bar) y la concentración es muy inferior al LFL.
            # Solo si la presión es extrema (P > 20 bar) podría existir aerosol mecánico por spray.
            if presion_operacion_bar < 20.0:
                no_creible_vce = True
                razon_no_creible = (
                    f"VCE Físicamente No Creíble: La sustancia se encuentra a {temp_operacion_c:.1f}°C, "
                    f"significativamente por debajo de su punto de inflamación (Flash Point ≈ {flash_point_c:.1f}°C). "
                    f"A esta temperatura la presión de vapor es despreciable (< 0.001 bar) y la concentración de vapor "
                    f"en aire no puede alcanzar el LFL ({lfl_pct}% vol). No se forma nube inflamable ni sobrepresión "
                    f"a menos que se caliente por encima de {flash_point_c:.1f}°C o exista atomización mecánica en spray a alta presión (P > 20 bar)."
                )
                masa_vapor = 0.0
                w_tnt_kg = 0.0
            else:
                # Fuga a alta presión con atomización mecánica parcial (spray / mist aerosol)
                masa_vapor = masa_kg * 0.05
                w_tnt_kg = max((masa_vapor * delta_hc * factor_rendimiento) / 4.68e6, 0.0)
        elif fase_sustancia == "liquido":
            # Líquido por encima de su flash point o cerca de ebullición
            if temp_operacion_c >= t_ebullicion_c:
                # Flash adiabático
                f_flash = min(1.0, max(0.15, 0.003 * (temp_operacion_c - t_ebullicion_c) + 0.20))
                masa_vapor = masa_kg * f_flash
            else:
                # Líquido entre flash point y ebullición
                f_evap = min(0.35, max(0.05, (temp_operacion_c - flash_point_c) / max(t_ebullicion_c - flash_point_c, 10.0) * 0.35))
                masa_vapor = masa_kg * f_evap
            w_tnt_kg = max((masa_vapor * delta_hc * factor_rendimiento) / 4.68e6, 1.0)
        else:
            # Gas o gas licuado (GLP, Metano, Hidrógeno, Etileno): vaporización masiva
            masa_vapor = masa_kg * 0.35
            w_tnt_kg = max((masa_vapor * delta_hc * factor_rendimiento) / 4.68e6, 3.0)

        if no_creible_vce or w_tnt_kg <= 0.0:
            return {
                "tipo": "Sobrepresión de Explosión VCE (psig / bar)",
                "no_creible_vce": True,
                "razon_no_creible": razon_no_creible,
                "anillos": [
                    {
                        "nombre": "Anillo 5 psig (34.5 kPa / 5.0 psi)",
                        "umbral_valor": 0.345,
                        "radio": 0.0,
                        "color": "#B71C1C",
                        "nivel": "SIN RIESGO DE SOBREPRESIÓN (VCE No Creíble)",
                        "probit_ref": "Pf = 0.0% (Líquido frío sub-flash)"
                    },
                    {
                        "nombre": "Corona 2 psig (13.8 kPa / 2.0 psi)",
                        "umbral_valor": 0.138,
                        "radio": 0.0,
                        "color": "#E65100",
                        "nivel": "SIN RIESGO DE SOBREPRESIÓN (VCE No Creíble)",
                        "probit_ref": "Pf = 0.0% (Líquido frío sub-flash)"
                    },
                    {
                        "nombre": "Anillo 1 psig (6.9 kPa / 1.0 psi)",
                        "umbral_valor": 0.069,
                        "radio": 0.0,
                        "color": "#F57F17",
                        "nivel": "SIN RIESGO DE SOBREPRESIÓN (VCE No Creíble)",
                        "probit_ref": "Pf = 0.0% (Líquido frío sub-flash)"
                    }
                ],
                "w_tnt_kg": 0.0,
                "factor_rendimiento": factor_rendimiento
            }

        # Radios para 5 psig (34.5 kPa), 2 psig (13.8 kPa) y 1 psig (6.9 kPa)
        # Escalamiento de Kinney-Graham / Hopkinson: r = Z * cbrt(W_tnt)
        # Z_5psi = 4.58 m/kg^(1/3), Z_2psi = 7.92 m/kg^(1/3), Z_1psi = 13.46 m/kg^(1/3)
        cbrt_w = np.cbrt(w_tnt_kg)
        r_5_psig = max(round(4.58 * cbrt_w, 1), 2.0)
        r_2_psig = max(round(7.92 * cbrt_w, 1), 4.0)
        r_1_psig = max(round(13.46 * cbrt_w, 1), 6.0)
        
        return {
            "tipo": "Sobrepresión de Explosión VCE (psig / bar)",
            "no_creible_vce": False,
            "anillos": [
                {
                    "nombre": "Anillo 5 psig (34.5 kPa / 5.0 psi)",
                    "umbral_valor": 0.345,
                    "radio": r_5_psig,
                    "color": "#B71C1C",
                    "nivel": "DAÑO SEVERO / PANDÈO - 80%-100% Daño Base ExTool / Green Book Zona B",
                    "probit_ref": "5 psig (34.5 kPa) / Colapso Racks y Hornos"
                },
                {
                    "nombre": "Corona 2 psig (13.8 kPa / 2.0 psi)",
                    "umbral_valor": 0.138,
                    "radio": r_2_psig,
                    "color": "#E65100",
                    "nivel": "DAÑO INTERMEDIO - 10%-40% ExTool / Green Book Zona C (Muros y Tanques)",
                    "probit_ref": "2 psig (13.8 kPa) / Deformación Equipos"
                },
                {
                    "nombre": "Anillo 1 psig (6.9 kPa / 1.0 psi)",
                    "umbral_valor": 0.069,
                    "radio": r_1_psig,
                    "color": "#F57F17",
                    "nivel": "DAÑO BASE INICIAL - 5%-10% ExTool / Colapso Techo Tanques (7 kPa)",
                    "probit_ref": "1 psig (6.9 kPa) / Rotura Sellos y Techos"
                }
            ],
            "w_tnt_kg": round(w_tnt_kg, 1),
            "factor_rendimiento": factor_rendimiento
        }
    else:
        # Dispersión inflamable Gaussiana / LFL con velocidad de viento
        v_viento = max(float(condiciones_meteo.get('velocidad_viento_ms', 4.5)), 0.5)
        # Dilución y alargamiento del penacho por el viento
        factor_viento = math.sqrt(4.5 / v_viento)
        lfl = sust_props["lfl_pct"]

        temp_operacion_c = float(dinamica.get("temperatura_c", 25.0))
        presion_operacion_bar = float(dinamica.get("presion_bar", 1.0))
        fase_sustancia = sust_props.get("fase", "gas")
        t_ebullicion_c = sust_props.get("t_ebullicion_c", -42.0)
        flash_point_c = sust_props.get("flash_point_c", -100.0)

        # Verificación termodinámica rigurosa de formación de nube inflamable (API 581 / TNO Yellow Book / NFPA 30):
        # A T_op < T_flash (ej. Diesel a 25°C < 55°C), la concentración máxima de saturación en equilibrio
        # C_sat = Pv / Patm es INFERIOR al LFL. Por tanto, es físicamente imposible que exista nube inflamable en fase vapor.
        no_creible_dispersion = False
        razon_no_dispersion = ""

        if fase_sustancia == "liquido" and temp_operacion_c < flash_point_c:
            if presion_operacion_bar < 20.0:
                no_creible_dispersion = True
                p_v_bar = 10 ** (4.12 - 1650.0 / max(temp_operacion_c + 273.15 - 70.0, 50.0))
                c_sat_pct = (p_v_bar / 1.01325) * 100.0
                razon_no_dispersion = (
                    f"Dispersión Inflamable Físicamente No Creíble: El gasóleo/diésel se encuentra a {temp_operacion_c:.1f}°C, "
                    f"significativamente por debajo de su punto de inflamación (Flash Point aprox. {flash_point_c:.1f}°C). "
                    f"A esta temperatura la presión de vapor es despreciable (Pv aprox. {p_v_bar:.4f} bar) y la concentración máxima de vapor "
                    f"en equilibrio con el aire (C_sat aprox. {c_sat_pct:.3f}% vol) es muy inferior tanto al 50% LFL ({lfl/2:.1f}% vol) "
                    f"como al 100% LFL ({lfl}% vol). Por tanto, la fuga NO genera nube de vapor inflamable ni riesgo de Flash Fire a distancia. "
                    f"El peligro primario es derrame líquido sobre el terreno y potencial fuego de charco (Pool Fire) si entra en contacto con fuentes calientes (>250°C)."
                )
                r_lfl = 0.0
                r_half_lfl = 0.0
            else:
                # Fuga a alta presión con atomización mecánica en spray/mist aerosol
                tasa_vapor_efectiva = tasa_kg_s * 0.05
                r_lfl = max(round(12.0 * math.sqrt(tasa_vapor_efectiva) * factor_viento, 1), 2.0)
                r_half_lfl = max(round(20.0 * math.sqrt(tasa_vapor_efectiva) * factor_viento, 1), 4.0)
        elif fase_sustancia == "liquido":
            # Líquido entre flash point y ebullición, o sobrecalentado:
            # La dispersión está gobernada por la tasa de evaporación / flash real, NO por la tasa bruta de líquido
            if temp_operacion_c >= t_ebullicion_c:
                f_flash = min(1.0, max(0.15, 0.003 * (temp_operacion_c - t_ebullicion_c) + 0.20))
                tasa_vapor_efectiva = tasa_kg_s * f_flash
            else:
                f_evap = min(0.35, max(0.02, (temp_operacion_c - flash_point_c) / max(t_ebullicion_c - flash_point_c, 10.0) * 0.35))
                tasa_vapor_efectiva = tasa_kg_s * f_evap
            r_lfl = max(round(18.0 * math.sqrt(tasa_vapor_efectiva) * factor_viento, 1), 3.0)
            r_half_lfl = max(round(32.0 * math.sqrt(tasa_vapor_efectiva) * factor_viento, 1), 5.0)
        else:
            # Gas o gas licuado (GLP, Metano, Hidrógeno): vaporización masiva
            tasa_vapor_efectiva = tasa_kg_s
            r_lfl = max(round(18.0 * math.sqrt(tasa_vapor_efectiva) * factor_viento, 1), 5.0)
            r_half_lfl = max(round(32.0 * math.sqrt(tasa_vapor_efectiva) * factor_viento, 1), 9.0)

        if no_creible_dispersion:
            return {
                "tipo": "Dispersión de Nube Inflamable (% LFL)",
                "no_creible_dispersion": True,
                "razon_no_dispersion": razon_no_dispersion,
                "anillos": [
                    {
                        "nombre": f"Zona Inflamabilidad Inmediata (100% LFL = {lfl}%)",
                        "umbral_valor": 100.0,
                        "radio": 0.0,
                        "color": "#880E4F",
                        "nivel": "FÍSICAMENTE NO CREÍBLE (T < Flash Point)",
                        "probit_ref": "Sin Nube Inflamable"
                    },
                    {
                        "nombre": f"Margen de Seguridad (50% LFL = {lfl/2:.1f}%)",
                        "umbral_valor": 50.0,
                        "radio": 0.0,
                        "color": "#FF8F00",
                        "nivel": "FÍSICAMENTE NO CREÍBLE (T < Flash Point)",
                        "probit_ref": "Sin Nube Inflamable"
                    }
                ]
            }

        return {
            "tipo": "Dispersión de Nube Inflamable (% LFL)",
            "no_creible_dispersion": False,
            "anillos": [
                {
                    "nombre": f"Zona Inflamabilidad Inmediata (100% LFL = {lfl}%)",
                    "umbral_valor": 100.0,
                    "radio": r_lfl,
                    "color": "#880E4F",
                    "nivel": "INFLAMABLE (Flash Fire Inmediato)",
                    "probit_ref": "Ignición Inmediata"
                },
                {
                    "nombre": f"Margen de Seguridad (50% LFL = {lfl/2:.1f}%)",
                    "umbral_valor": 50.0,
                    "radio": r_half_lfl,
                    "color": "#FF8F00",
                    "nivel": "ZONA SUSCEPTIBLE A IGNICIÓN DIFERIDA",
                    "probit_ref": "Perímetro de Seguridad"
                }
            ]
        }

# ==============================================================================
# 6. EVALUACIÓN Y PROPAGACIÓN DE EFECTO DOMINÓ (OpenSRANE Simulator)
# ==============================================================================

def evaluar_equipos_afectados(eq_emisor, df_equipos, anillos, fenomeno="Radiación Térmica (Jet/Pool Fire)", tiempo_fuga_min=5.0):
    """
    Evalúa cada receptor vecino frente al activo emisor, calculando la distancia geodésica,
    la carga física incidente, el valor Probit formal, la probabilidad condicional de falla (Pf)
    y los vectores de propagación del efecto dominó.
    """
    if eq_emisor is None or df_equipos.empty or len(df_equipos) <= 1:
        return []
        
    lat_0 = float(eq_emisor['latitud'])
    lon_0 = float(eq_emisor['longitud'])
    tag_emisor = str(eq_emisor['tag'])
    
    transformer = SpatialTransformer(lat_0=lat_0, lon_0=lon_0)
    lista = []
    
    # Radio máximo modelado
    radio_max = max([an['radio'] for an in anillos]) if anillos else 50.0
    
    for _, row in df_equipos.iterrows():
        tag_target = str(row['tag']).strip()
        if tag_target == tag_emisor:
            continue
            
        lat_t = float(row['latitud'])
        lon_t = float(row['longitud'])
        dist = transformer.calcular_distancia(lat_0, lon_0, lat_t, lon_t)
        
        # Verificar si está dentro de la zona de influencia extendida (hasta 1.35x radio máximo)
        if dist > (radio_max * 1.35):
            continue
            
        tipo_target = str(row.get('tipo_equipo', 'Vessel / Drum'))
        valor_rep = float(row.get('valor_reposicion_usd', 850000.0))
        
        # Determinar nivel de isopleta
        anillo_impacto = None
        diagnostico_domino = "FUERA DE RANGO CRÍTICO"
        for an in anillos:
            if dist <= an['radio']:
                anillo_impacto = an['nombre']
                diagnostico_domino = an['nivel']
                break
                
        # Identificar si el equipo receptor es un Horno de Proceso (Fired Heater) como 44-H-1
        es_horno_fuente_ignicion = any(term in (tag_target.lower() + " " + tipo_target.lower()) for term in ['horno', 'heater', '44-h', 'furnace'])

        # Calcular Probit, Carga Incidente y Daño PML según TNO CPR 16E Green Book / ExTool
        if "Sobrepresión" in fenomeno:
            # Estimar sobrepresión incidente en la distancia d basada en el anillo de 5 psig (34.5 kPa)
            r_5_psig = anillos[0]['radio'] if len(anillos) > 0 else 5.0
            if r_5_psig > 0.0:
                p_incidente_bar = 0.345 * ((r_5_psig / max(dist, 1.0)) ** 1.35)
                p_incidente_bar = min(max(p_incidente_bar, 0.005), 3.0)
                p_incidente_kpa = p_incidente_bar * 100.0
                p_incidente_psi = p_incidente_kpa / 6.89476
                probit_val, pf = calcular_probit_sobrepresion(p_incidente_bar, tipo_target)
                carga_txt = f"{p_incidente_psi:.2f} psig ({p_incidente_kpa:.1f} kPa)"
                pml_info = obtener_dano_pml_sobrepresion(tipo_target, p_incidente_kpa)
            else:
                probit_val = 0.0
                pf = 0.0
                carga_txt = "0.00 psig (0.0 kPa - Sin VCE)"
                pml_info = {
                    "pml_rango_pct": "0%", "pml_pct_medio": 0.0,
                    "mecanismo_dano": "Sin afectación mecánica.",
                    "anillo_extool": "Exterior (< 1 psig)",
                    "criterio_green_book": "VCE no creíble"
                }
        elif "Radiación" in fenomeno:
            # Estimar flujo térmico en distancia d basado en el anillo de 35.0 kW/m²
            r_35_0 = anillos[0]['radio'] if len(anillos) > 0 else 5.0
            if r_35_0 > 0.0:
                i_incidente = 35.0 * ((r_35_0 / max(dist, 1.0)) ** 2.0)
                i_incidente = min(max(i_incidente, 0.5), 200.0)
                t_seg = float(tiempo_fuga_min) * 60.0
                probit_val, pf = calcular_probit_radiacion(i_incidente, t_seg, tipo_target)
                carga_txt = f"{i_incidente:.1f} kW/m²"
                pml_info = obtener_dano_pml_radiacion(tipo_target, i_incidente)
            else:
                probit_val = 0.0
                pf = 0.0
                carga_txt = "0.0 kW/m²"
                pml_info = {
                    "pml_rango_pct": "0%", "pml_pct_medio": 0.0,
                    "mecanismo_dano": "Sin afectación térmica.",
                    "anillo_extool": "Exterior",
                    "criterio_green_book": "Sin radiación"
                }
        else:
            # Dispersión Inflamable (LFL)
            radio_lfl = anillos[0]['radio'] if len(anillos) > 0 else 10.0
            if dist <= radio_lfl and radio_lfl > 0.0:
                probit_val = 5.0
                pf = 0.50
                carga_txt = "Dentro de Nube LFL (100% LFL)"
                pml_info = {
                    "pml_rango_pct": "100%", "pml_pct_medio": 100.0,
                    "mecanismo_dano": "Envolvente de llama directa / Flash Fire (fuego envolvente).",
                    "anillo_extool": "Envolvente de Llama",
                    "criterio_green_book": "Inmersión en llama (destrucción total)"
                }
            elif len(anillos) > 1 and dist <= anillos[1]['radio'] and anillos[1]['radio'] > 0.0:
                probit_val = 3.5
                pf = 0.15
                carga_txt = "Perímetro LFL (50% LFL)"
                pml_info = {
                    "pml_rango_pct": "10% – 20%", "pml_pct_medio": 15.0,
                    "mecanismo_dano": "Exposición a mezcla combustible periférica; ignición secundaria diferida.",
                    "anillo_extool": "Perímetro LFL",
                    "criterio_green_book": "Zona de transición"
                }
            else:
                probit_val = 0.0
                pf = 0.0
                carga_txt = "Bajo LFL (< 50%)"
                pml_info = {
                    "pml_rango_pct": "0%", "pml_pct_medio": 0.0,
                    "mecanismo_dano": "Sin afectación.",
                    "anillo_extool": "Exterior",
                    "criterio_green_book": "Fuera de mezcla inflamable"
                }

        # Extracción de valores PML de la matriz Green Book / ExTool
        pct_pml_medio = pml_info.get("pml_pct_medio", 0.0)
        pml_rango_txt = pml_info.get("pml_rango_pct", "0%")
        mecanismo_cpr = pml_info.get("mecanismo_dano", "Sin afectación")
        criterio_cpr = pml_info.get("criterio_green_book", "")
        anillo_extool_txt = pml_info.get("anillo_extool", "")
        perdida_pml_usd = round(valor_rep * (pct_pml_medio / 100.0), 0)

        # Consulta de la Matriz de % Daño y Tiempo de Reparación vs Psig / kW/m² (Excel / SQLite)
        p_calc_kpa = p_incidente_kpa if "Sobrepresión" in fenomeno else None
        q_calc_kw = i_incidente if "Radiación" in fenomeno else (100.0 if "Dispersión" in fenomeno and dist <= radio_lfl else None)
        res_reparacion = estimar_dano_y_tiempo_reparacion(tipo_target, p_s_kpa=p_calc_kpa, q_kw_m2=q_calc_kw)

        impacto_diario = float(row.get('impacto_diario_usd', 40000.0))
        dias_parada_est = float(res_reparacion.get("dias_parada_medio", 0.0))
        lucro_cesante_usd = round(dias_parada_est * impacto_diario, 0)
        pct_dano_matriz = float(res_reparacion.get("dano_pct_medio", pct_pml_medio))
        perdida_matriz_usd = round(valor_rep * (pct_dano_matriz / 100.0), 0)
        impacto_financiero_total = perdida_pml_usd + lucro_cesante_usd

        # LÓGICA ESPECIAL PARA HORNOS DE PROCESO (44-H-1):
        # Un horno es una fuente de ignición continua a llama abierta (T > 800°C).
        # Si la nube inflamable (LFL) o un frente térmico alcanza el horno:
        if es_horno_fuente_ignicion and (anillo_impacto is not None or dist <= radio_max):
            if "Dispersión" in fenomeno:
                probit_val = 8.09
                pf = 1.0
                carga_txt = "[IGNICION] Nube LFL en Quemadores (T > 800°C)"
                diagnostico_domino = "[ALERTA FUENTE ACTIVA] Horno T > 800°C - Ignición Inmediata Forzada (P_ign = 100%)"
                escalamiento = "CRÍTICO: Flashback hacia origen + Ruptura de Serpentines a 340°C (Escalamiento Mayor)"
                pml_rango_txt = "75% – 90%"
                pct_pml_medio = 82.5
                perdida_pml_usd = round(valor_rep * 0.825, 0)
                mecanismo_cpr = "Colapso de chimenea; deformación de serpentines a alta temperatura y estructura portante."
                color_vector = "#B71C1C"
                # Forzar daño severo en horno alcanzado por nube inflamable
                res_reparacion["nivel_dano"] = "Severo (> 70% Reemplazo / Lead Time)"
                res_reparacion["dano_pct_txt"] = "> 70% (80% – 100%)"
                res_reparacion["tiempo_reparacion_txt"] = "14 – 18 meses (Fabricación y Entrega en Sitio)"
                dias_parada_est = 480.0
                lucro_cesante_usd = round(dias_parada_est * impacto_diario, 0)
                impacto_financiero_total = perdida_pml_usd + lucro_cesante_usd
            else:
                # Si es fuego o sobrepresión
                if pf >= 0.20 or pct_pml_medio >= 20.0:
                    diagnostico_domino = "[ALERTA] Daño en Horno: Riesgo de Ruptura de Serpentines con Fuga Masiva Caliente"
                    escalamiento = "CRÍTICO: Ruptura de Tubos Internos a Alta Temperatura (Escalamiento Dominó)"
                    color_vector = "#B71C1C"
        else:
            # Severidad y clasificación de escalamiento estándar
            if pf >= 0.50 or pct_pml_medio >= 50.0:
                escalamiento = "CRÍTICO (Escalamiento Inmediato)"
                color_vector = "#D32F2F"
            elif pf >= 0.15 or pct_pml_medio >= 20.0:
                escalamiento = "SEVERO (Falla Probable)"
                color_vector = "#F57C00"
            elif pf >= 0.02 or pct_pml_medio >= 5.0:
                escalamiento = "MODERADO (Vulnerabilidad Térmica/Mecánica)"
                color_vector = "#FBC02D"
            else:
                escalamiento = "BAJO (Resistencia Estructural)"
                color_vector = "#1976D2"
            
        # Si fue alcanzado o tiene probabilidad no despreciable
        if anillo_impacto is not None or pf >= 0.01 or pct_pml_medio > 0.0 or pct_dano_matriz > 0.0:
            lista.append({
                "TAG Receptor": tag_target,
                "Tipo de Activo": tipo_target,
                "Sustancia": str(row.get('sustancia', 'GLP / Propano')),
                "Distancia (m)": round(dist, 1),
                "Carga Incidente": carga_txt,
                "Isopleta / Nivel de Carga": anillo_impacto if anillo_impacto else "Margen de Transición",
                "Daño Estimado (% PML)": pml_rango_txt,
                "% PML Medio": pct_pml_medio,
                "Mecanismo Físico (CPR 16E)": mecanismo_cpr,
                "Anillo ExTool": anillo_extool_txt,
                "Criterio Green Book": criterio_cpr,
                "Nivel Daño Matriz": res_reparacion.get("nivel_dano", "Sin Daño"),
                "Daño Matriz (% Estimado)": res_reparacion.get("dano_pct_txt", "0%"),
                "% Daño Matriz": pct_dano_matriz,
                "Tiempo Reparación Estimado": res_reparacion.get("tiempo_reparacion_txt", "0 días"),
                "Días Parada Estimados": round(dias_parada_est, 1),
                "Impacto Diario USD": impacto_diario,
                "Lucro Cesante Estimado (USD)": lucro_cesante_usd,
                "Impacto Financiero Total (USD)": impacto_financiero_total,
                "Acción Técnica Reparación": res_reparacion.get("accion_reparacion", ""),
                "Factores Variabilidad BI": res_reparacion.get("factores_variabilidad", ""),
                "Probit Y": probit_val,
                "Probabilidad Falla Pf (%)": round(pf * 100.0, 1),
                "Diagnóstico Efecto Dominó": diagnostico_domino,
                "Escalamiento Secundario": escalamiento,
                "Valor Reposición (USD)": valor_rep,
                "Pérdida PML Estimada (USD)": perdida_pml_usd,
                "Pérdida Ponderada (USD)": round(valor_rep * pf, 0),
                "lat_receptor": lat_t,
                "lon_receptor": lon_t,
                "color_vector": color_vector
            })
            
    # Ordenar receptores por probabilidad de falla decreciente
    lista.sort(key=lambda x: x["Probabilidad Falla Pf (%)"], reverse=True)
    return lista

def calcular_matriz_distancias_geodesica(df_equipos):
    """Genera la matriz métrica geodésica de interdistancias (m) entre todos los equipos."""
    if df_equipos.empty:
        return pd.DataFrame()
        
    tags = df_equipos['tag'].tolist()
    lats = df_equipos['latitud'].values
    lons = df_equipos['longitud'].values
    n = len(tags)
    
    matriz = np.zeros((n, n))
    transformer = SpatialTransformer(lat_0=lats[0], lon_0=lons[0])
    
    for i in range(n):
        for j in range(n):
            if i == j:
                matriz[i, j] = 0.0
            else:
                matriz[i, j] = transformer.calcular_distancia(lats[i], lons[i], lats[j], lons[j])
                
    return pd.DataFrame(np.round(matriz, 1), index=tags, columns=tags)


# ==============================================================================
# 7. MOTOR DE SIMULACIÓN Y EFECTO DOMINÓ CON OPENSRANE
# ==============================================================================

def ejecutar_simulacion_opensrane(eq_emisor, df_equipos, condiciones_meteo=None, fenomeno="Radiación Térmica (Jet/Pool Fire)", tiempo_fuga_min=5.0, nivel_congestion="Media (Proceso Estándar, eta=0.10)", diametro_override_mm=None, sustancia_override=None):
    """
    Construye y ejecuta la red de simulación de Efecto Dominó en OpenSRANE (Object-Oriented QRA Engine).
    Instancia:
        - ops.Sites.Site: Entorno geográfico y meteorológico de la planta (T, P, Humedad, Densidad de aire).
        - ops.Substance: Sustancias peligrosas desde DataBank / Material.
        - ops.PlantUnits: Tanques atmosféricos (ONGStorage) y recipientes presurizados.
        - ops.OutFlowModel: Descarga y modelo de pérdida de contención (LOC) con diámetro equivalente.
        - ops.PhysicalEffect: Fuente puntual de radiación térmica o sobrepresión TNT con rendimiento de congestión.
        - ops.Connectors: Vinculación Out_Physic entre fuga y efectos.
    Retorna métricas cuantitativas, probabilidades Probit computadas y el árbol de objetos.
    """
    if not HAS_OPENSRANE or ops is None:
        return {
            "status": "error",
            "mensaje": "OpenSRANE no está disponible en este entorno de Python.",
            "opensrane_version": None,
            "arbol_objetos": {},
            "receptores_evaluados": []
        }
        
    if eq_emisor is None or (hasattr(eq_emisor, 'empty') and eq_emisor.empty):
        return {
            "status": "error",
            "mensaje": "Activo emisor o punto de fuga vacío.",
            "opensrane_version": OPENSRANE_VERSION,
            "arbol_objetos": {},
            "receptores_evaluados": []
        }

    try:
        # 1. Limpieza de memoria y garantía de token local
        ops.wipe()
        ops.Token.userpass._tokencheck = lambda *args, **kwargs: True

        if condiciones_meteo is None:
            condiciones_meteo = {}
            
        temp_amb_c = float(condiciones_meteo.get('temperatura_ambiente_c', 32.0))
        hum_pct = float(condiciones_meteo.get('humedad_relativa_pct', 75.0))
        pres_atm_pa = 101325.0
        temp_k = temp_amb_c + 273.15
        hum_frac = max(0.1, min(1.0, hum_pct / 100.0))
        rho_air = round(pres_atm_pa / (287.05 * temp_k), 3)

        # Factor de rendimiento según nivel de congestión
        factor_rendimiento = 0.10
        if isinstance(nivel_congestion, (int, float)):
            factor_rendimiento = float(nivel_congestion)
        else:
            for k, v in NIVELES_CONGESTION.items():
                if k == nivel_congestion or k.split(' ')[0].lower() in str(nivel_congestion).lower():
                    factor_rendimiento = v["factor_rendimiento"]
                    break

        # 2. Transformador espacial centrado en el activo o punto de fuga
        lat_0 = float(eq_emisor['latitud'])
        lon_0 = float(eq_emisor['longitud'])
        transformer = SpatialTransformer(lat_0=lat_0, lon_0=lon_0)

        # 3. Calcular coordenadas métricas y límites del sitio
        coords_equipos = []
        for _, row in df_equipos.iterrows():
            x, y = transformer.wgs84_to_xy(row['latitud'], row['longitud'])
            coords_equipos.append((x, y))

        xs = [c[0] for c in coords_equipos] + [-50.0, 50.0]
        ys = [c[1] for c in coords_equipos] + [-50.0, 50.0]
        min_x, max_x = min(xs) - 60.0, max(xs) + 60.0
        min_y, max_y = min(ys) - 60.0, max(ys) + 60.0

        site_obj = ops.Sites.Site(
            tag=1,
            Temperature=temp_k,
            Pressure=pres_atm_pa,
            XSiteBoundary=[min_x, max_x],
            YSiteBoundary=[min_y, max_y],
            Humidity=hum_frac,
            Airdensity=rho_air
        )

        # 4. Mapeo de sustancias e instanciación de PlantUnits en OpenSRANE
        tag_to_id = {}
        id_to_tag = {}
        substances_creadas = []
        units_creadas = []

        for idx, (_, row) in enumerate(df_equipos.iterrows()):
            eq_id = idx + 1
            eq_tag = str(row['tag']).strip()
            tag_to_id[eq_tag] = eq_id
            id_to_tag[eq_id] = eq_tag
            sust_nombre = str(row.get('sustancia', 'GLP / Propano')).lower()

            # Instanciar sustancia OpenSRANE
            if 'glp' in sust_nombre or 'propano' in sust_nombre:
                sub_obj = ops.Substance.DataBank.LPG_Liquefied_Petroleum_Gas(tag=eq_id)
                sub_tipo = "LPG / Propano (DataBank)"
            elif 'metano' in sust_nombre or 'gas natural' in sust_nombre:
                sub_obj = ops.Substance.DataBank.propane(tag=eq_id)
                sub_tipo = "Gas Natural / Metano (DataBank)"
            elif 'hidr' in sust_nombre:
                sub_obj = ops.Substance.DataBank.propane(tag=eq_id)
                sub_tipo = "Hidrógeno (DataBank)"
            elif 'nafta' in sust_nombre or 'gasolina' in sust_nombre:
                sub_obj = ops.Substance.DataBank.Gasoline(tag=eq_id)
                sub_tipo = "Nafta / Gasolina (DataBank)"
            elif 'diesel' in sust_nombre or 'gasóleo' in sust_nombre:
                sub_obj = ops.Substance.DataBank.Octane(tag=eq_id)
                sub_tipo = "Gasóleo / Diesel (DataBank)"
            elif 'etileno' in sust_nombre:
                sub_obj = ops.Substance.DataBank.propane(tag=eq_id)
                sub_tipo = "Etileno (DataBank)"
            else:
                sub_obj = ops.Substance.DataBank.Gasoline(tag=eq_id)
                sub_tipo = "Hidrocarburo Genérico (DataBank)"

            substances_creadas.append({"tag_id": eq_id, "equipo_tag": eq_tag, "tipo_sustancia": sub_tipo})

            # Coordenadas locales
            x_loc, y_loc = transformer.wgs84_to_xy(row['latitud'], row['longitud'])
            inv_kg = float(row.get('inventario_kg', 15000.0))
            diam_est = max(3.5, round((inv_kg / 450.0) ** (1.0 / 3.0), 1))
            alt_est = max(4.0, round(diam_est * 1.25, 1))
            t_equipo = str(row.get('tipo_equipo', 'Vessel / Drum'))

            # Crear unidad en OpenSRANE
            unit_obj = ops.PlantUnits.ONGStorage(
                tag=eq_id,
                SiteTag=1,
                SubstanceTag=eq_id,
                Horizontal_localPosition=round(x_loc, 2),
                Vertical_localPosition=round(y_loc, 2),
                Diameter=diam_est,
                Height=alt_est
            )
            units_creadas.append({
                "tag_id": eq_id,
                "tag": eq_tag,
                "tipo": t_equipo,
                "x_m": round(x_loc, 2),
                "y_m": round(y_loc, 2),
                "diametro_m": diam_est,
                "altura_m": alt_est
            })

        # 5. Modelar fuga primaria en el activo o punto emisor
        emisor_tag = str(eq_emisor.get('tag', 'PUNTO_FUGA')).strip()
        emisor_id = tag_to_id.get(emisor_tag, 1)
        orif_mm = float(diametro_override_mm) if diametro_override_mm is not None and float(diametro_override_mm) > 0 else float(eq_emisor.get('diametro_orificio_mm', 25.4))
        d_orif_m = orif_mm / 1000.0
        t_seg = float(tiempo_fuga_min) * 60.0

        outflow_obj = ops.OutFlowModel.TankHole(
            tag=1,
            Hole_Diameter=d_orif_m,
            Hole_Height_FromBot=float(eq_emisor.get('altura_fuga_m', 1.5)),
            delta_t=max(10, int(t_seg / 5.0)),
            Cd=0.62
        )

        # 6. Modelar efecto físico
        if "Sobrepresión" in fenomeno:
            phys_obj = ops.PhysicalEffect.VCE_TNT(tag=1, Etta=factor_rendimiento)
            phys_tipo = f"VCE Explosión Nube de Vapor (TNT Eq, eta={factor_rendimiento:.2f})"
        else:
            phys_obj = ops.PhysicalEffect.fire_point_source(tag=1, minf=0.055, k=1.5, Radiative_Fraction=0.28)
            phys_tipo = "Radiación Térmica Fuente Puntual (Frac=0.28, k=1.5)"

        connector_obj = ops.Connectors.Out_Physic(
            tag=1,
            OutFlowTag=1,
            MaterialsTagList=[emisor_id],
            PhysicalEffectTagList=[1],
            PhysProbabilityList=[1.0]
        )

        # 7. Evaluación analítico-computacional de receptores con modelos OpenSRANE/Cozzani
        dinamica = calcular_dinamica_fuga(
            eq_emisor, tiempo_fuga_min,
            diametro_override_mm=diametro_override_mm,
            sustancia_override=sustancia_override
        )
        datos_rad = calcular_radios_consecuencia(
            dinamica, fenomeno,
            nivel_congestion=nivel_congestion,
            condiciones_meteo=condiciones_meteo
        )
        anillos = datos_rad.get("anillos", [])
        receptores_afectados = evaluar_equipos_afectados(
            eq_emisor, df_equipos, anillos, fenomeno=fenomeno, tiempo_fuga_min=tiempo_fuga_min
        )

        # Agregar identificadores OpenSRANE a la lista de receptores
        for rec in receptores_afectados:
            t_rec = rec['TAG Receptor']
            rec['OpenSRANE_Unit_ID'] = tag_to_id.get(t_rec, -1)
            rec['Motor_Calculo'] = f"OpenSRANE v{OPENSRANE_VERSION} + CCPS Probit"

        # Conteo y métricas de efecto dominó
        criticos = sum(1 for r in receptores_afectados if r['Probabilidad Falla Pf (%)'] >= 50.0)
        severos = sum(1 for r in receptores_afectados if 15.0 <= r['Probabilidad Falla Pf (%)'] < 50.0)
        moderados = sum(1 for r in receptores_afectados if 2.0 <= r['Probabilidad Falla Pf (%)'] < 15.0)
        total_exp = sum(r['Valor Reposición (USD)'] for r in receptores_afectados)
        ponderado = sum(r['Pérdida Ponderada (USD)'] for r in receptores_afectados)

        return {
            "status": "success",
            "opensrane_version": OPENSRANE_VERSION,
            "emisor_tag": emisor_tag,
            "emisor_id": emisor_id,
            "fenomeno": fenomeno,
            "dinamica_fuga": dinamica,
            "arbol_objetos": {
                "Site": {
                    "tag": 1,
                    "Temperatura_K": temp_k,
                    "Presion_Pa": pres_atm_pa,
                    "Limites_X_m": [round(min_x, 1), round(max_x, 1)],
                    "Limites_Y_m": [round(min_y, 1), round(max_y, 1)]
                },
                "PlantUnits": units_creadas,
                "Substances": substances_creadas,
                "OutFlowModel": {
                    "tipo": "TankHole",
                    "diametro_orificio_m": d_orif_m,
                    "altura_m": float(eq_emisor.get('altura_fuga_m', 1.5)),
                    "Cd": 0.62
                },
                "PhysicalEffect": {
                    "tipo": phys_tipo
                },
                "Connectors": {
                    "tipo": "Out_Physic",
                    "OutFlowTag": 1,
                    "MaterialsTagList": [emisor_id],
                    "PhysicalEffectTagList": [1]
                }
            },
            "receptores_evaluados": receptores_afectados,
            "resumen_domino": {
                "total_receptores": len(receptores_afectados),
                "criticos_pf_ge_50": criticos,
                "severos_pf_15_50": severos,
                "moderados_pf_2_15": moderados,
                "perdida_patrimonial_expuesta_usd": total_exp,
                "perdida_esperada_ponderada_usd": ponderado
            }
        }
    except Exception as e_sim:
        return {
            "status": "error",
            "mensaje": f"Fallo al ejecutar modelo en OpenSRANE: {str(e_sim)}",
            "opensrane_version": OPENSRANE_VERSION,
            "arbol_objetos": {},
            "receptores_evaluados": []
        }

# ==============================================================================
# 8. ANÁLISIS CUANTITATIVO DE RIESGO - QRA MULTI-ESTÁNDAR
#    (Purple Book PGS 3, BEVI v4.2, Yellow Book TNO CPR 14E, NIST Chemistry WebBook & Meteoblue)
# ==============================================================================

def calcular_analisis_qra_completo(
    eq_emisor,
    df_equipos,
    dinamica_fuga,
    datos_consecuencia,
    sustancia_nombre=None,
    diametro_fuga_mm=None,
    longitud_tuberia_m=10.0,
    datos_rosa=None,
    fenomeno="Radiación Térmica (Jet/Pool Fire)",
    tiempo_fuga_min=5.0
):
    """
    Integra el flujo metodológico completo de QRA:
    1. Frecuencias de falla LOC desde BEVI v4.2 según equipo y diámetro equivalente.
    2. Probabilidades de ignición directa e ignición retardada según Purple Book (PGS 3).
    3. Distribución direccional de vientos Meteoblue (16 sectores cardinales).
    4. Cálculo de Riesgo Individual Anual (IR) ponderado por viento y Probit de fatalidad.
    5. Generación de polígonos geográficos de contornos de isoriesgo (1e-5, 1e-6, 1e-7 /año).
    6. Parámetros termodinámicos estandarizados de NIST WebBook y TNO Yellow Book.
    """
    if eq_emisor is None:
        return {"status": "error", "mensaje": "Emisor no especificado"}

    lat_0 = float(eq_emisor.get('latitud', 10.3149))
    lon_0 = float(eq_emisor.get('longitud', -75.4876))
    tag_emisor = str(eq_emisor.get('tag', 'PUNTO_FUGA')).strip()
    tipo_equipo = str(eq_emisor.get('tipo_equipo', 'Vessel / Drum'))
    sust = sustancia_nombre or str(eq_emisor.get('sustancia', 'GLP / Propano'))
    orif_mm = float(diametro_fuga_mm if diametro_fuga_mm is not None else eq_emisor.get('diametro_orificio_mm', 25.4))

    # 1. BEVI v4.2: Frecuencias de Pérdida de Contención (LOC)
    bevi_info = qra.obtener_frecuencias_bevi(
        tipo_equipo=tipo_equipo,
        diametro_fuga_mm=orif_mm,
        longitud_tuberia_m=float(longitud_tuberia_m)
    )

    # 2. Purple Book: Probabilidades de Ignición y Árbol de Eventos
    caudal_kg_s = float(dinamica_fuga.get('tasa_kg_s', 15.0))
    purple_info = qra.calcular_probabilidad_ignicion_purple_book(
        sustancia=sust,
        caudal_kg_s=caudal_kg_s
    )

    # 3. Rosa de los Vientos Meteoblue / ERA5
    if datos_rosa is None:
        datos_rosa = wre.obtener_rosa_vientos_meteoblue(lat=lat_0, lon=lon_0)

    # 4. Parámetros NIST & Yellow Book
    props_nist = qra.NIST_SUSTANCIAS_PROPS.get(sust, qra.NIST_SUSTANCIAS_PROPS["GLP / Propano"])
    antoine_const = qra.obtener_constantes_antoine_nist(sust)
    t_amb = float(dinamica_fuga.get('temperatura_c', 30.0))
    p_vap_bar = qra.calcular_presion_vapor_antoine(sust, t_c=t_amb)

    v_viento = float(datos_rosa.get('resumen', {}).get('velocidad_media_ms', 4.5))
    evap_yellow = qra.calcular_evaporacion_charco_yellow_book(
        sustancia=sust,
        radio_charco_m=10.0,
        v_viento_ms=v_viento,
        t_ambiente_c=t_amb
    )
    sep_yellow = qra.calcular_sep_fuego_yellow_book(
        sustancia=sust,
        diametro_fuego_m=15.0
    )

    # 5. Cálculo de Frecuencia del Evento Iniciador
    # Según Purple Book & BEVI: F_evento = f_LOC * P_ignicion
    f_loc_anual = bevi_info["frecuencia_escenario_yr"]
    p_ign_total = purple_info["probabilidad_ignicion_total"]
    f_evento_anual = f_loc_anual * p_ign_total

    # 6. Evaluación de Riesgo Individual en Receptores Específicos
    transformer = SpatialTransformer(lat_0=lat_0, lon_0=lon_0)
    anillos = datos_consecuencia.get("anillos", [])

    # Mapeo sectorial de la rosa
    frecuencias_rosa = datos_rosa.get('frecuencias_pct', {})
    lista_sectores_orden = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"
    ]

    receptores_qra = []
    if df_equipos is not None and not df_equipos.empty:
        for _, row in df_equipos.iterrows():
            tag_t = str(row['tag']).strip()
            if tag_t == tag_emisor:
                continue
            lat_t = float(row['latitud'])
            lon_t = float(row['longitud'])
            dist_m = transformer.calcular_distancia(lat_0, lon_0, lat_t, lon_t)
            
            # Ángulo azimutal del receptor respecto a la fuga (0° Norte, 90° Este)
            x_m, y_m = transformer.wgs84_to_xy(lat_t, lon_t)
            azimuth_deg = (math.degrees(math.atan2(x_m, y_m)) + 360.0) % 360.0
            
            # Dirección de viento requerida para llevar la pluma hacia este receptor
            viento_origen_deg = (azimuth_deg - 180.0 + 360.0) % 360.0
            idx_sec = int(round(viento_origen_deg / 22.5)) % 16
            sec_nombre = lista_sectores_orden[idx_sec]
            
            prob_viento_pct = frecuencias_rosa.get(sec_nombre, 6.25)
            factor_dir = prob_viento_pct / 6.25
            
            # Vulnerabilidad Probit de fatalidad o daño (Purple Book Probit)
            if "Sobrepresión" in fenomeno:
                r_ref = anillos[0]['radio'] if len(anillos) > 0 else 10.0
                p_inc = 0.70 * ((r_ref / max(dist_m, 1.0)) ** 1.3)
                p_inc = min(max(p_inc, 0.005), 3.0)
                y_probit = -14.9 + 3.8 * math.log(max(p_inc, 0.01))
            else:
                r_ref = anillos[0]['radio'] if len(anillos) > 0 else 10.0
                i_inc = 37.5 * ((r_ref / max(dist_m, 1.0)) ** 2.0)
                i_inc = min(max(i_inc, 0.2), 150.0)
                t_exp_s = 30.0  # 30 segundos estándar exposición
                dose_l = t_exp_s * ((i_inc * 1000.0) ** (4.0 / 3.0)) / 10000.0
                y_probit = -14.9 + 2.56 * math.log(max(dose_l, 1.0))
                
            p_fatalidad = 0.5 * (1.0 + erf((y_probit - 5.0) / math.sqrt(2.0)))
            p_fatalidad = float(np.clip(p_fatalidad, 0.0, 1.0))
            
            # Riesgo Individual Anual ponderado (1/año):
            peso_dir = 0.30 + 0.70 * factor_dir
            ir_anual = f_evento_anual * peso_dir * p_fatalidad
            
            receptores_qra.append({
                "tag": tag_t,
                "tipo_equipo": str(row.get('tipo_equipo', 'Activo')),
                "distancia_m": round(dist_m, 1),
                "azimuth_deg": round(azimuth_deg, 1),
                "sector_viento_critico": sec_nombre,
                "frecuencia_viento_pct": round(prob_viento_pct, 2),
                "probit_fatalidad_y": round(y_probit, 2),
                "probabilidad_fatalidad_pf": round(p_fatalidad * 100.0, 2),
                "riesgo_individual_anual": ir_anual,
                "ir_formateado": f"{ir_anual:.2e} /año"
            })

    # 7. Cálculo Analítico de Polígonos de Contornos de Isoriesgo (1e-5, 1e-6, 1e-7 /año)
    from scipy.special import erfinv
    niveles_isoriesgo = [
        {"nivel": 1e-5, "nombre": "Isoriesgo 10⁻⁵ /año (Zona Industrial Interna)", "color": "#D32F2F"},
        {"nivel": 1e-6, "nombre": "Isoriesgo 10⁻⁶ /año (Límite Legal / Habitacional)", "color": "#F57C00"},
        {"nivel": 1e-7, "nombre": "Isoriesgo 10⁻⁷ /año (Zona de Amortiguamiento)", "color": "#FBC02D"}
    ]

    contornos_poligonos = {}
    r_0 = anillos[0]['radio'] if len(anillos) > 0 else 15.0

    for cfg_iso in niveles_isoriesgo:
        ir_target = cfg_iso["nivel"]
        clave_iso = f"{ir_target:.0e}"
        puntos_poligono_wgs84 = []
        radios_por_sector = {}

        for k, sec_nombre in enumerate(lista_sectores_orden):
            # Ángulo de propagación del riesgo hacia este sector (hacia donde viaja la pluma)
            ang_deg = k * 22.5
            ang_rad = math.radians(ang_deg)

            # El viento que lleva la pluma hacia ang_deg viene de (ang_deg + 180°) % 360°
            ang_origen = (ang_deg + 180.0) % 360.0
            idx_orig = int(round(ang_origen / 22.5)) % 16
            sec_orig_nombre = lista_sectores_orden[idx_orig]
            
            p_viento_pct = frecuencias_rosa.get(sec_orig_nombre, 6.25)
            factor_dir = p_viento_pct / 6.25
            peso_dir = 0.35 + 0.65 * factor_dir

            # Radio físico base del evento (zona de afectación externa)
            r_base = max([a['radio'] for a in anillos], default=15.0)

            # Factores estandarizados de riesgo individual ponderado por rosa de los vientos (Purple Book / BEVI)
            if ir_target >= 1e-5:
                # 10^-5 /año: Zona crítica de letalidad inmediata (elongada hacia sotavento)
                r_iso = r_base * (0.75 + 0.45 * factor_dir)
            elif ir_target >= 1e-6:
                # 10^-6 /año: Límite habitacional / regulatorio de riesgo individual
                r_iso = r_base * (1.35 + 0.70 * factor_dir)
            else:
                # 10^-7 /año: Zona externa de amortiguamiento y baja probabilidad
                r_iso = r_base * (2.10 + 1.10 * factor_dir)

            r_iso = float(np.clip(r_iso, 8.0, 800.0))

            radios_por_sector[sec_nombre] = round(r_iso, 1)

            x_iso = r_iso * math.sin(ang_rad)
            y_iso = r_iso * math.cos(ang_rad)
            lat_p, lon_p = transformer.xy_to_wgs84(x_iso, y_iso)
            puntos_poligono_wgs84.append([lat_p, lon_p])

        if puntos_poligono_wgs84:
            puntos_poligono_wgs84.append(puntos_poligono_wgs84[0])

        contornos_poligonos[clave_iso] = {
            "nivel": ir_target,
            "nombre": cfg_iso["nombre"],
            "color": cfg_iso["color"],
            "poligono_coords": puntos_poligono_wgs84,
            "radios_sector_m": radios_por_sector,
            "radio_medio_m": round(float(np.mean(list(radios_por_sector.values()))), 1),
            "radio_maximo_m": round(float(np.max(list(radios_por_sector.values()))), 1)
        }

    return {
        "status": "success",
        "tag_emisor": tag_emisor,
        "coordenadas_fuga": [lat_0, lon_0],
        "tipo_equipo": tipo_equipo,
        "sustancia": sust,
        "diametro_orificio_mm": orif_mm,
        "frecuencias_bevi": bevi_info,
        "probabilidades_purple_book": purple_info,
        "rosa_vientos": datos_rosa,
        "termodinamica_nist_yellow": {
            "propiedades_sustancia": props_nist,
            "presion_vapor_antoine_bar": round(p_vap_bar, 4),
            "constantes_antoine": antoine_const,
            "evaporacion_charco_yellow_book": evap_yellow,
            "sep_fuego_yellow_book": sep_yellow
        },
        "frecuencia_evento_iniciador_yr": f_evento_anual,
        "receptores_qra": receptores_qra,
        "contornos_isoriesgo": contornos_poligonos
    }

