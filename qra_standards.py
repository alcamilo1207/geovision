"""
================================================================================
MÓDULO DE ESTÁNDARES INTERNACIONALES QRA (Quantitative Risk Assessment)
- BEVI v4.2 (RIVM - Handleiding Risicoberekeningen Bevi versie 4.2)
- Purple Book (PGS 3 / CPR 18E - Guidelines for Quantitative Risk Assessment)
- Yellow Book (TNO CPR 14E - Methods for Calculation of Physical Effects)
- NIST Chemistry WebBook (National Institute of Standards and Technology)
================================================================================
"""

import math
import numpy as np

# ==============================================================================
# 1. NIST CHEMISTRY WEBBOOK: PROPIEDADES TERMODINÁMICAS PURAS
# ==============================================================================

NIST_SUSTANCIAS_PROPS = {
    "GLP / Propano": {
        "formula": "C3H8",
        "cas": "74-98-6",
        "mw": 44.096,               # g/mol
        "tb_k": 231.05,             # -42.1 °C
        "tc_k": 369.89,             # Temperatura crítica (K)
        "pc_bar": 42.51,            # Presión crítica (bar)
        "delta_hvap_kj_mol": 19.04, # Calor de vaporización a Tb
        "delta_hc_mj_kg": 46.35,    # Calor neto de combustión (MJ/kg)
        "lfl_pct": 2.1,             # % vol en aire
        "ufl_pct": 9.5,
        "rho_liq_kg_m3": 493.0,     # a 20 °C saturado
        "cp_gas_j_mol_k": 73.5,
        "reactividad_purple_book": "average", # Purple Book Tabla 4.7
        # Constantes de Antoine (NIST WebBook): log10(P [bar]) = A - (B / (T [K] + C))
        "antoine": {"A": 3.92828, "B": 803.997, "C": -26.11},
        # Yellow Book: Tasa de quema de charco m'' (kg/m2·s) y SEPmax (kW/m2)
        "yellow_book": {"m_inf": 0.099, "k_beta": 0.055, "sep_max": 140.0}
    },
    "Gas Natural / Metano": {
        "formula": "CH4",
        "cas": "74-82-8",
        "mw": 16.043,
        "tb_k": 111.66,             # -161.5 °C
        "tc_k": 190.56,
        "pc_bar": 45.99,
        "delta_hvap_kj_mol": 8.17,
        "delta_hc_mj_kg": 50.01,
        "lfl_pct": 5.0,
        "ufl_pct": 15.0,
        "rho_liq_kg_m3": 422.4,
        "cp_gas_j_mol_k": 35.69,
        "reactividad_purple_book": "low", # Purple Book Tabla 4.7
        "antoine": {"A": 3.98950, "B": 443.011, "C": -0.49},
        "yellow_book": {"m_inf": 0.078, "k_beta": 0.050, "sep_max": 125.0}
    },
    "Hidrógeno": {
        "formula": "H2",
        "cas": "1333-74-0",
        "mw": 2.016,
        "tb_k": 20.39,              # -252.8 °C
        "tc_k": 33.15,
        "pc_bar": 12.96,
        "delta_hvap_kj_mol": 0.90,
        "delta_hc_mj_kg": 120.00,
        "lfl_pct": 4.0,
        "ufl_pct": 75.0,
        "rho_liq_kg_m3": 70.85,
        "cp_gas_j_mol_k": 28.84,
        "reactividad_purple_book": "high",
        "antoine": {"A": 3.543, "B": 99.3, "C": 7.7},
        "yellow_book": {"m_inf": 0.040, "k_beta": 0.100, "sep_max": 220.0}
    },
    "Nafta Ligera": {
        "formula": "C5-C7 (Pentano-Hexano)",
        "cas": "64741-66-8",
        "mw": 86.18,
        "tb_k": 309.22,             # 36.1 °C
        "tc_k": 469.7,
        "pc_bar": 33.7,
        "delta_hvap_kj_mol": 25.77,
        "delta_hc_mj_kg": 44.80,
        "lfl_pct": 1.1,
        "ufl_pct": 7.5,
        "rho_liq_kg_m3": 660.0,
        "cp_gas_j_mol_k": 120.0,
        "reactividad_purple_book": "high", # Purple Book Tabla 4.7 (naphtha, solvent*)
        "antoine": {"A": 3.97786, "B": 1064.84, "C": -41.136},
        "yellow_book": {"m_inf": 0.072, "k_beta": 0.045, "sep_max": 130.0}
    },
    "Gasolina / Nafta": {
        "formula": "C7H16 (Heptano eq.)",
        "cas": "86290-81-5",
        "mw": 100.20,
        "tb_k": 371.58,             # 98.4 °C
        "tc_k": 540.2,
        "pc_bar": 27.4,
        "delta_hvap_kj_mol": 31.77,
        "delta_hc_mj_kg": 44.00,
        "lfl_pct": 1.05,
        "ufl_pct": 6.7,
        "rho_liq_kg_m3": 740.0,
        "cp_gas_j_mol_k": 166.0,
        "reactividad_purple_book": "k1_liquid",
        "antoine": {"A": 4.02832, "B": 1268.636, "C": -56.199},
        "yellow_book": {"m_inf": 0.055, "k_beta": 0.040, "sep_max": 120.0}
    },
    "Gasóleo / Diesel": {
        "formula": "C12-C15 (Gas Oil)",
        "cas": "68334-30-5",
        "mw": 170.30,
        "tb_k": 473.15,             # 200 °C
        "tc_k": 670.0,
        "pc_bar": 21.0,
        "delta_hvap_kj_mol": 52.00,
        "delta_hc_mj_kg": 42.50,
        "lfl_pct": 0.6,
        "ufl_pct": 6.0,
        "rho_liq_kg_m3": 840.0,
        "cp_gas_j_mol_k": 250.0,
        "reactividad_purple_book": "k1_liquid",
        "antoine": {"A": 4.12000, "B": 1650.000, "C": -70.000},
        "yellow_book": {"m_inf": 0.045, "k_beta": 0.035, "sep_max": 105.0}
    },
    "Crudo / Hidrocarburo Mezcla": {
        "formula": "Crude Oil Blend",
        "cas": "8002-05-9",
        "mw": 180.00,
        "tb_k": 353.15,
        "tc_k": 650.0,
        "pc_bar": 25.0,
        "delta_hvap_kj_mol": 45.00,
        "delta_hc_mj_kg": 42.00,
        "lfl_pct": 1.0,
        "ufl_pct": 7.0,
        "rho_liq_kg_m3": 850.0,
        "cp_gas_j_mol_k": 220.0,
        "reactividad_purple_book": "k1_liquid",
        "antoine": {"A": 4.05000, "B": 1400.000, "C": -60.000},
        "yellow_book": {"m_inf": 0.040, "k_beta": 0.035, "sep_max": 95.0}
    },
    "Etileno": {
        "formula": "C2H4",
        "cas": "74-85-1",
        "mw": 28.054,
        "tb_k": 169.42,             # -103.7 °C
        "tc_k": 282.35,
        "pc_bar": 50.41,
        "delta_hvap_kj_mol": 13.54,
        "delta_hc_mj_kg": 47.16,
        "lfl_pct": 2.7,
        "ufl_pct": 36.0,
        "rho_liq_kg_m3": 568.0,
        "cp_gas_j_mol_k": 42.9,
        "reactividad_purple_book": "average", # Purple Book Tabla 4.7
        "antoine": {"A": 3.91382, "B": 583.245, "C": -18.15},
        "yellow_book": {"m_inf": 0.085, "k_beta": 0.060, "sep_max": 155.0}
    }
}

def calcular_presion_vapor_antoine(sustancia_nombre, temp_c=25.0, t_c=None, **kwargs):
    """
    Calcula la presión de vapor saturada Pv (bar) usando la ecuación de Antoine de NIST:
    log10(P [bar]) = A - (B / (T [K] + C))
    """
    if t_c is not None:
        temp_c = float(t_c)
    else:
        temp_c = float(temp_c)

    props = NIST_SUSTANCIAS_PROPS.get("GLP / Propano")
    for k, v in NIST_SUSTANCIAS_PROPS.items():
        if k in sustancia_nombre or any(part in sustancia_nombre for part in k.split('/')):
            props = v
            break
            
    t_k = float(temp_c) + 273.15
    ant = props.get("antoine", {"A": 3.92828, "B": 803.997, "C": -26.11})
    log10_p = ant["A"] - (ant["B"] / (t_k + ant["C"]))
    p_bar = 10.0 ** log10_p
    return max(float(p_bar), 1e-4)


# ==============================================================================
# 2. PURPLE BOOK (PGS 3 / CPR 18E): PROBABILIDADES DE IGNICIÓN & ÁRBOL DE EVENTOS
# ==============================================================================

# Tabla 4.5 Purple Book: Probabilidad de ignición directa para instalaciones estacionarias
# Filas: rangos de flujo de descarga continua (<10 kg/s, 10-100 kg/s, >100 kg/s)
# o masa instantánea (<1000 kg, 1000-10000 kg, >10000 kg)
PURPLE_BOOK_DIRECT_IGNITION_TABLE = {
    "pequeno": { # < 10 kg/s o < 1000 kg
        "k1_liquid": 0.065,
        "low_reactive": 0.020,
        "average_high_reactive": 0.200
    },
    "mediano": { # 10 - 100 kg/s o 1000 - 10,000 kg
        "k1_liquid": 0.065,
        "low_reactive": 0.040,
        "average_high_reactive": 0.500
    },
    "grande": { # > 100 kg/s o > 10,000 kg
        "k1_liquid": 0.065,
        "low_reactive": 0.090,
        "average_high_reactive": 0.700
    }
}

# Apéndice 4.A Tabla 4.A.1 Purple Book: Efectividad de fuentes de ignición en 1 minuto
PURPLE_BOOK_DELAYED_SOURCES = {
    "antorcha_flare": {"prob_1min": 1.00, "desc": "Antorcha / Flare de planta"},
    "refineria_planta_quimica": {"prob_1min": 0.90, "desc": "Refinería de petróleo / Complejo químico"},
    "horno_exterior": {"prob_1min": 0.90, "desc": "Horno de proceso o craqueo exterior"},
    "industria_pesada": {"prob_1min": 0.70, "desc": "Área de calderas e industria pesada"},
    "horno_interior": {"prob_1min": 0.45, "desc": "Horno en sala cerrada"},
    "caldera_exterior": {"prob_1min": 0.45, "desc": "Caldera exterior de vapor"},
    "vehiculos_motores": {"prob_1min": 0.40, "desc": "Tráfico vehicular y motores de combustión interna"},
    "caldera_interior": {"prob_1min": 0.23, "desc": "Caldera interior"},
    "linea_transmision": {"prob_1min": 0.20, "desc": "Línea eléctrica de alta tensión (por 100m)"},
    "personal_operadores": {"prob_1min": 0.01, "desc": "Presencia humana / personal de planta (por persona)"}
}

def calcular_probabilidad_ignicion_purple_book(tasa_kg_s=15.0, masa_total_kg=5000.0, sustancia_nombre="GLP / Propano", sustancia=None, caudal_kg_s=None, fuentes_activas=None, tiempo_nube_s=60.0, **kwargs):
    """
    Computa las probabilidades de ignición según el Purple Book (PGS 3 / CPR 18E):
    - P_direct: Ignición inmediata (Tabla 4.5)
    - P_delayed: Ignición retardada por fuentes en la planta (Apéndice 4.A)
    - P_bleve: Probabilidad de BLEVE para gas licuado instantáneo (0.70)
    - P_vce vs P_flashfire: 40% Explosión VCE vs 60% Flash Fire (Sección 4.8)
    """
    if caudal_kg_s is not None:
        tasa_kg_s = float(caudal_kg_s)
    if sustancia is not None:
        sustancia_nombre = str(sustancia)

    props = NIST_SUSTANCIAS_PROPS.get("GLP / Propano")
    for k, v in NIST_SUSTANCIAS_PROPS.items():
        if k in sustancia_nombre or any(part in sustancia_nombre for part in k.split('/')):
            props = v
            break
            
    react = props.get("reactividad_purple_book", "average")
    
    # Determinar categoría de tamaño según Tabla 4.5
    if tasa_kg_s < 10.0 or masa_total_kg < 1000.0:
        cat_tam = "pequeno"
    elif tasa_kg_s <= 100.0 or masa_total_kg <= 10000.0:
        cat_tam = "mediano"
    else:
        cat_tam = "grande"
        
    # Obtener P_direct
    if react == "k1_liquid":
        p_direct = PURPLE_BOOK_DIRECT_IGNITION_TABLE[cat_tam]["k1_liquid"]
    elif react == "low":
        p_direct = PURPLE_BOOK_DIRECT_IGNITION_TABLE[cat_tam]["low_reactive"]
    else:
        p_direct = PURPLE_BOOK_DIRECT_IGNITION_TABLE[cat_tam]["average_high_reactive"]
        
    # Calcular Ignición Retardada (Apéndice 4.A, Ec. 4.A.1: P(t) = 1 - exp(-omega * t))
    if fuentes_activas is None:
        # Fuentes estándar de una refinería / planta de proceso
        fuentes_activas = ["refineria_planta_quimica", "vehiculos_motores", "personal_operadores"]
        
    omega_total = 0.0
    for f in fuentes_activas:
        if f in PURPLE_BOOK_DELAYED_SOURCES:
            p_1m = PURPLE_BOOK_DELAYED_SOURCES[f]["prob_1min"]
            # omega = -ln(1 - P_1m) / 60
            om = -math.log(max(1.0 - p_1m, 0.001)) / 60.0
            omega_total += om
            
    t_s = max(float(tiempo_nube_s), 10.0)
    p_delayed = 1.0 - math.exp(-omega_total * t_s)
    p_delayed = max(min(p_delayed, 0.99), 0.05)
    
    # Probabilidad total de que la nube inflamable se encienda (directa o retardada)
    p_ign_total = p_direct + (1.0 - p_direct) * p_delayed
    
    # Bifurcación de consecuencias según Purple Book Sección 4.7 y 4.8
    # - Instantáneo de gas licuado: BLEVE = 0.70
    # - Nube de vapor retardada: Flash Fire = 0.60, Explosión VCE = 0.40
    p_bleve = 0.70 if props["tb_k"] < 273.15 else 0.0
    p_vce = 0.40
    p_flash_fire = 0.60
    
    return {
        "p_direct": round(p_direct, 4),
        "p_delayed": round(p_delayed, 4),
        "p_ignicion_total": round(p_ign_total, 4),
        "probabilidad_ignicion_total": round(p_ign_total, 4),
        "p_bleve": p_bleve,
        "p_vce": p_vce,
        "p_flash_fire": p_flash_fire,
        "categoria_tamanio": cat_tam,
        "reactividad": react,
        "fuentes_consideradas": fuentes_activas
    }

def obtener_constantes_antoine_nist(sustancia_nombre):
    """Retorna las constantes A, B, C de Antoine según NIST Chemistry WebBook."""
    props = NIST_SUSTANCIAS_PROPS.get("GLP / Propano")
    for k, v in NIST_SUSTANCIAS_PROPS.items():
        if k in sustancia_nombre or any(part in sustancia_nombre for part in k.split('/')):
            props = v
            break
    return props.get("antoine", {"A": 3.92828, "B": 803.997, "C": -26.11})



# ==============================================================================
# 3. BEVI v4.2 (RIVM): FRECUENCIAS OFICIALES DE PÉRDIDA DE CONTENCIÓN (LOC)
# ==============================================================================

BEVI_LOC_TABLAS = {
    "recipiente_presion": {
        "nombre": "Bovengronds opslagtank onder druk (Vessel / Drum / Esfera Presurizada)",
        "referencia": "BEVI Module C, Tabel 13",
        "scenarios": {
            "ruptura_catastrofica": {
                "frecuencia_anual": 5.0e-7,
                "desc": "Instantaan vrijkomen van de gehele inhoud (Ruptura Catastrófica)"
            },
            "liberacion_10min": {
                "frecuencia_anual": 5.0e-7,
                "desc": "Vrijkomen van gehele inhoud in 10 min constante stroom"
            },
            "fuga_continua_10mm": {
                "frecuencia_anual": 1.0e-5,
                "desc": "Continu vrijkomen uit gat met effectieve diameter 10 mm"
            }
        }
    },
    "reactor_proceso": {
        "nombre": "Reactorvaten en procesvaten (Reactores, Columnas, Procesos Químicos)",
        "referencia": "BEVI Module C, Tabel 30",
        "scenarios": {
            "ruptura_catastrofica": {
                "frecuencia_anual": 5.0e-6,
                "desc": "Instantaan vrijkomen van de gehele inhoud (Ruptura Catastrófica)"
            },
            "liberacion_10min": {
                "frecuencia_anual": 5.0e-6,
                "desc": "Vrijkomen van gehele inhoud in 10 min constante stroom"
            },
            "fuga_continua_10mm": {
                "frecuencia_anual": 1.0e-4,
                "desc": "Continu vrijkomen uit gat met effectieve diameter 10 mm"
            }
        }
    },
    "tanque_atmosferico_single": {
        "nombre": "Atmosferische opslagtank - Single Containment (Pared Simple)",
        "referencia": "BEVI Module C, Tabel 17",
        "scenarios": {
            "ruptura_catastrofica": {
                "frecuencia_anual": 1.0e-5,
                "desc": "Instantaan falen van de opslagtank (Ruptura Total)"
            },
            "liberacion_10min": {
                "frecuencia_anual": 1.0e-5,
                "desc": "Vrijkomen van gehele inhoud in 10 min"
            },
            "fuga_continua_10mm": {
                "frecuencia_anual": 1.0e-4,
                "desc": "Continu vrijkomen uit gat met effectieve diameter 10 mm"
            }
        }
    },
    "tanque_atmosferico_double": {
        "nombre": "Atmosferische opslagtank - Double Containment (Pared Doble)",
        "referencia": "BEVI Module C, Tabel 19",
        "scenarios": {
            "ruptura_catastrofica": {
                "frecuencia_anual": 1.0e-6,
                "desc": "Instantaan falen binnentank en buitentank"
            },
            "liberacion_10min": {
                "frecuencia_anual": 1.0e-6,
                "desc": "Vrijkomen gehele inhoud in 10 min"
            },
            "fuga_continua_10mm": {
                "frecuencia_anual": 1.0e-4,
                "desc": "Continu vrijkomen uit 10 mm gat"
            }
        }
    },
    "tuberias_bovengronds": {
        "nombre": "Bovengrondse leidingen (Tuberías de Proceso / Racks)",
        "referencia": "BEVI Module C, Tabel 27",
        "clases_dn": {
            "dn_menor_75": {
                "rango": "Nominale diameter < 75 mm (< 3\")",
                "ruptura_m_ano": 1.0e-6,
                "fuga_10pct_dn_m_ano": 5.0e-6
            },
            "dn_75_150": {
                "rango": "75 mm <= Nominale diameter <= 150 mm (3\" a 6\")",
                "ruptura_m_ano": 3.0e-7,
                "fuga_10pct_dn_m_ano": 2.0e-6
            },
            "dn_mayor_150": {
                "rango": "Nominale diameter > 150 mm (> 6\")",
                "ruptura_m_ano": 1.0e-7,
                "fuga_10pct_dn_m_ano": 5.0e-7
            }
        }
    },
    "bombas_compresores": {
        "nombre": "Pompen en compressoren (Bombas centrífugas y compresores)",
        "referencia": "BEVI Module C, Tabel 32",
        "scenarios": {
            "ruptura_catastrofica": {
                "frecuencia_anual": 1.0e-4,
                "desc": "Catastrofaal falen pomphuis"
            },
            "fuga_continua_10mm": {
                "frecuencia_anual": 5.0e-4,
                "desc": "Lekkage mechanische afdichting (10 mm eq.)"
            }
        }
    },
    "intercambiadores_calor": {
        "nombre": "Warmtewisselaars en condensors (Intercambiadores de calor)",
        "referencia": "BEVI Module C, Tabel 33",
        "scenarios": {
            "ruptura_carcasa": {
                "frecuencia_anual": 1.0e-6,
                "desc": "Breuk van de mantel (ruptura externa)"
            },
            "ruptura_tubos": {
                "frecuencia_anual": 1.0e-5,
                "desc": "Pijpbreuk in de bundel (fuga interna)"
            },
            "fuga_10mm": {
                "frecuencia_anual": 1.0e-4,
                "desc": "Lek uit aansluiting of flens (10 mm eq.)"
            }
        }
    }
}

def obtener_frecuencias_bevi(tipo_equipo, diametro_orificio_mm=25.4, longitud_tuberia_m=20.0, diametro_fuga_mm=None, **kwargs):
    """
    Determina la frecuencia base de falla anual f_LOC según la clasificación oficial de BEVI v4.2.
    """
    if diametro_fuga_mm is not None:
        diametro_orificio_mm = float(diametro_fuga_mm)
    else:
        diametro_orificio_mm = float(diametro_orificio_mm)

    t_low = str(tipo_equipo).lower()
    
    if any(k in t_low for k in ['tub', 'pipe', 'línea', 'line', 'ducto', 'rack']):
        cat = BEVI_LOC_TABLAS["tuberias_bovengronds"]
        l_m = max(float(longitud_tuberia_m), 1.0)
        d_mm = float(diametro_orificio_mm)
        if d_mm < 75.0:
            dn_clase = cat["clases_dn"]["dn_menor_75"]
        elif d_mm <= 150.0:
            dn_clase = cat["clases_dn"]["dn_75_150"]
        else:
            dn_clase = cat["clases_dn"]["dn_mayor_150"]
            
        freq_rup = dn_clase["ruptura_m_ano"] * l_m
        freq_lek = dn_clase["fuga_10pct_dn_m_ano"] * l_m
        f_ap = freq_rup if d_mm >= 75.0 else freq_lek
        return {
            "categoria_bevi": cat["nombre"],
            "referencia": cat["referencia"],
            "subclase": dn_clase["rango"],
            "frecuencia_ruptura_anual": freq_rup,
            "frecuencia_fuga_anual": freq_lek,
            "frecuencia_total_loc_anual": freq_rup + freq_lek,
            "escenario_seleccionado": "Ruptura de Tubería" if d_mm >= 75.0 else "Fuga en Tubería (10% DN)",
            "frecuencia_aplicada": f_ap,
            "frecuencia_escenario_yr": f_ap
        }
    elif any(k in t_low for k in ['atmosf', 'techo', 'cúpula', 'almacenamiento', 'storage', 'pile']):
        cat = BEVI_LOC_TABLAS["tanque_atmosferico_single"]
        sc = cat["scenarios"]
        d_mm = float(diametro_orificio_mm)
        if d_mm >= 100.0:
            f_ap = sc["ruptura_catastrofica"]["frecuencia_anual"]
            esc = "Ruptura Catastrófica (Instantaan)"
        elif d_mm >= 25.0:
            f_ap = sc["liberacion_10min"]["frecuencia_anual"]
            esc = "Vaciado Total en 10 min"
        else:
            f_ap = sc["fuga_continua_10mm"]["frecuencia_anual"]
            esc = "Fuga Continua 10 mm"
            
        return {
            "categoria_bevi": cat["nombre"],
            "referencia": cat["referencia"],
            "subclase": "Single Containment Tank",
            "frecuencia_ruptura_anual": sc["ruptura_catastrofica"]["frecuencia_anual"],
            "frecuencia_fuga_anual": sc["fuga_continua_10mm"]["frecuencia_anual"],
            "frecuencia_total_loc_anual": sc["ruptura_catastrofica"]["frecuencia_anual"] + sc["fuga_continua_10mm"]["frecuencia_anual"],
            "escenario_seleccionado": esc,
            "frecuencia_aplicada": f_ap,
            "frecuencia_escenario_yr": f_ap
        }
    elif any(k in t_low for k in ['reactor', 'torre', 'destil', 'columna', 'flash']):
        cat = BEVI_LOC_TABLAS["reactor_proceso"]
        sc = cat["scenarios"]
        d_mm = float(diametro_orificio_mm)
        if d_mm >= 75.0:
            f_ap = sc["ruptura_catastrofica"]["frecuencia_anual"]
            esc = "Ruptura Catastrófica del Reactor"
        elif d_mm >= 25.0:
            f_ap = sc["liberacion_10min"]["frecuencia_anual"]
            esc = "Vaciado en 10 min"
        else:
            f_ap = sc["fuga_continua_10mm"]["frecuencia_anual"]
            esc = "Fuga Continua 10 mm"
            
        return {
            "categoria_bevi": cat["nombre"],
            "referencia": cat["referencia"],
            "subclase": "Reactor / Columna de Destilación",
            "frecuencia_ruptura_anual": sc["ruptura_catastrofica"]["frecuencia_anual"],
            "frecuencia_fuga_anual": sc["fuga_continua_10mm"]["frecuencia_anual"],
            "frecuencia_total_loc_anual": sc["ruptura_catastrofica"]["frecuencia_anual"] + sc["fuga_continua_10mm"]["frecuencia_anual"],
            "escenario_seleccionado": esc,
            "frecuencia_aplicada": f_ap,
            "frecuencia_escenario_yr": f_ap
        }
    elif any(k in t_low for k in ['bomba', 'pump', 'compres']):
        cat = BEVI_LOC_TABLAS["bombas_compresores"]
        sc = cat["scenarios"]
        f_ap = sc["fuga_continua_10mm"]["frecuencia_anual"] if diametro_orificio_mm < 50.0 else sc["ruptura_catastrofica"]["frecuencia_anual"]
        return {
            "categoria_bevi": cat["nombre"],
            "referencia": cat["referencia"],
            "subclase": "Bomba / Compresor de Proceso",
            "frecuencia_ruptura_anual": sc["ruptura_catastrofica"]["frecuencia_anual"],
            "frecuencia_fuga_anual": sc["fuga_continua_10mm"]["frecuencia_anual"],
            "frecuencia_total_loc_anual": sc["ruptura_catastrofica"]["frecuencia_anual"] + sc["fuga_continua_10mm"]["frecuencia_anual"],
            "escenario_seleccionado": "Falla de Sello Mecánico (10 mm)" if diametro_orificio_mm < 50.0 else "Ruptura de Carcasa",
            "frecuencia_aplicada": f_ap,
            "frecuencia_escenario_yr": f_ap
        }
    elif any(k in t_low for k in ['intercambiador', 'cooler', 'enfriador', 'fin fan', 'aeroenfriador', 'condens']):
        cat = BEVI_LOC_TABLAS["intercambiadores_calor"]
        sc = cat["scenarios"]
        f_ap = sc["fuga_10mm"]["frecuencia_anual"] if diametro_orificio_mm < 50.0 else sc["ruptura_carcasa"]["frecuencia_anual"]
        return {
            "categoria_bevi": cat["nombre"],
            "referencia": cat["referencia"],
            "subclase": "Intercambiador de Calor / Fin Fan Cooler",
            "frecuencia_ruptura_anual": sc["ruptura_carcasa"]["frecuencia_anual"],
            "frecuencia_fuga_anual": sc["fuga_10mm"]["frecuencia_anual"],
            "frecuencia_total_loc_anual": sc["ruptura_carcasa"]["frecuencia_anual"] + sc["fuga_10mm"]["frecuencia_anual"],
            "escenario_seleccionado": "Fuga en Conexión / Boquilla (10 mm)" if diametro_orificio_mm < 50.0 else "Ruptura de Tubos / Carcasa",
            "frecuencia_aplicada": f_ap,
            "frecuencia_escenario_yr": f_ap
        }
    elif any(k in t_low for k in ['horno', 'heater', 'caldera', 'boiler', 'fired']):
        cat = BEVI_LOC_TABLAS["recipiente_presion"]
        sc = cat["scenarios"]
        f_ap = sc["fuga_continua_10mm"]["frecuencia_anual"] if diametro_orificio_mm < 50.0 else sc["ruptura_catastrofica"]["frecuencia_anual"]
        return {
            "categoria_bevi": "Horno de Proceso / Caldera (Tubos a Presión)",
            "referencia": "BEVI Module C, Tabel 13 / Tabel 30",
            "subclase": "Serpentín de Fuego Directo (Horno / Caldera)",
            "frecuencia_ruptura_anual": sc["ruptura_catastrofica"]["frecuencia_anual"],
            "frecuencia_fuga_anual": sc["fuga_continua_10mm"]["frecuencia_anual"],
            "frecuencia_total_loc_anual": sc["ruptura_catastrofica"]["frecuencia_anual"] + sc["fuga_continua_10mm"]["frecuencia_anual"],
            "escenario_seleccionado": "Fuga en Tubo / Boquilla (10 mm)" if diametro_orificio_mm < 50.0 else "Ruptura de Serpentín de Proceso",
            "frecuencia_aplicada": f_ap,
            "frecuencia_escenario_yr": f_ap
        }
    else:
        # Default: Recipiente a Presión (Vessel, Drum, Esfera, Bullet) - Tabla 13
        cat = BEVI_LOC_TABLAS["recipiente_presion"]
        sc = cat["scenarios"]
        d_mm = float(diametro_orificio_mm)
        if d_mm >= 75.0:
            f_ap = sc["ruptura_catastrofica"]["frecuencia_anual"]
            esc = "Ruptura Catastrófica (Instantaan)"
        elif d_mm >= 25.0:
            f_ap = sc["liberacion_10min"]["frecuencia_anual"]
            esc = "Vaciado Total en 10 min"
        else:
            f_ap = sc["fuga_continua_10mm"]["frecuencia_anual"]
            esc = "Fuga Continua 10 mm"
            
        return {
            "categoria_bevi": cat["nombre"],
            "referencia": cat["referencia"],
            "subclase": "Bovengronds drukvat (Recipiente Presurizado)",
            "frecuencia_ruptura_anual": sc["ruptura_catastrofica"]["frecuencia_anual"],
            "frecuencia_fuga_anual": sc["fuga_continua_10mm"]["frecuencia_anual"],
            "frecuencia_total_loc_anual": sc["ruptura_catastrofica"]["frecuencia_anual"] + sc["fuga_continua_10mm"]["frecuencia_anual"],
            "escenario_seleccionado": esc,
            "frecuencia_aplicada": f_ap,
            "frecuencia_escenario_yr": f_ap
        }


# ==============================================================================
# 4. YELLOW BOOK (TNO CPR 14E): MODELOS FÍSICOS ESTANDARIZADOS
# ==============================================================================

def calcular_evaporacion_charco_yellow_book(sustancia_nombre=None, sustancia=None, diametro_charco_m=10.0, radio_charco_m=None, temp_amb_c=32.0, t_ambiente_c=None, vel_viento_ms=4.5, v_viento_ms=None, **kwargs):
    """
    Calcula la tasa de evaporación de un charco de líquido según Yellow Book (TNO CPR 14E Cap. 3 / Mackay-Matsugu):
    E [kg/s] = k_m * M * P_v * A / (R * T)
    con k_m = 0.0048 * u^0.78 * d^-0.11 * Sc^-0.67
    """
    if sustancia is not None:
        sustancia_nombre = str(sustancia)
    if sustancia_nombre is None:
        sustancia_nombre = "GLP / Propano"

    if radio_charco_m is not None:
        diametro_charco_m = float(radio_charco_m) * 2.0
    if t_ambiente_c is not None:
        temp_amb_c = float(t_ambiente_c)
    if v_viento_ms is not None:
        vel_viento_ms = float(v_viento_ms)

    props = NIST_SUSTANCIAS_PROPS.get("Gasolina / Nafta")
    for k, v in NIST_SUSTANCIAS_PROPS.items():
        if k in sustancia_nombre or any(part in sustancia_nombre for part in k.split('/')):
            props = v
            break
            
    mw_kg_mol = props["mw"] / 1000.0 # kg/mol
    t_k = float(temp_amb_c) + 273.15
    u = max(float(vel_viento_ms), 0.5)
    d = max(float(diametro_charco_m), 1.0)
    area = math.pi * (d ** 2) / 4.0
    r_const = 8.314 # J/(mol·K)
    
    # Presión de vapor según Antoine (Pa)
    p_v_bar = calcular_presion_vapor_antoine(sustancia_nombre, temp_amb_c)
    p_v_pa = p_v_bar * 1e5
    
    # Coeficiente de transferencia de masa Mackay-Matsugu (m/s)
    sc = 1.8 # Número de Schmidt típico para vapor de hidrocarburo en aire
    km = 0.0048 * (u ** 0.78) * (d ** -0.11) * (sc ** -0.67)
    
    # Tasa de evaporación (kg/s)
    tasa_evap_kg_s = (km * mw_kg_mol * p_v_pa * area) / (r_const * t_k)
    tasa_evap_kg_s = max(float(tasa_evap_kg_s), 0.01)
    
    return {
        "tasa_evaporacion_kg_s": round(tasa_evap_kg_s, 3),
        "tasa_evaporacion_kg_min": round(tasa_evap_kg_s * 60.0, 2),
        "presion_vapor_bar": round(p_v_bar, 4),
        "area_charco_m2": round(area, 1),
        "coef_transferencia_km_m_s": round(km, 4)
    }

def calcular_sep_fuego_yellow_book(sustancia_nombre=None, sustancia=None, diametro_fuego_m=8.0, **kwargs):
    """
    Calcula el Poder Emisivo Superficial (SEP_act en kW/m2) según Yellow Book (TNO CPR 14E Cap. 6):
    SEP_act = SEP_max * (1 - exp(-k_beta * D))
    """
    if sustancia is not None:
        sustancia_nombre = str(sustancia)
    if sustancia_nombre is None:
        sustancia_nombre = "GLP / Propano"

    props = NIST_SUSTANCIAS_PROPS.get("GLP / Propano")
    for k, v in NIST_SUSTANCIAS_PROPS.items():
        if k in sustancia_nombre or any(part in sustancia_nombre for part in k.split('/')):
            props = v
            break
            
    yb = props.get("yellow_book", {"m_inf": 0.099, "k_beta": 0.055, "sep_max": 140.0})
    sep_max = yb["sep_max"]
    k_beta = yb["k_beta"]
    d = max(float(diametro_fuego_m), 1.0)
    
    sep_act = sep_max * (1.0 - math.exp(-k_beta * d))
    return {
        "sep_act_kw_m2": round(sep_act, 1),
        "sep_max_kw_m2": sep_max,
        "k_beta": k_beta
    }
