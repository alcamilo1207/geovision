import sys
import sqlite3
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
from db_manager import get_matriz_dano_reparacion_df

df_matriz = get_matriz_dano_reparacion_df()

def test_estimacion(tipo_eq, ps_kpa, q_kw):
    # Mapping
    t = tipo_eq.lower()
    if 'horno' in t:
        nombre_m = "Hornos de Proceso / Fired Heaters"
    elif 'torre' in t:
        nombre_m = "Torres de Destilación / Fraccionamiento"
    else:
        nombre_m = "Drums / Recipientes de Presión"
        
    row = df_matriz[df_matriz['tipo_equipo'] == nombre_m].iloc[0]
    
    # Check
    ps_s = row['ps_severo_min_kpa']
    q_s = row['q_severo_kw_m2']
    ps_m = row['ps_medio_min_kpa']
    q_m = row['q_medio_kw_m2']
    ps_l = row['ps_leve_min_kpa']
    q_l = row['q_leve_kw_m2']
    
    if (ps_kpa is not None and ps_kpa >= ps_s) or (q_kw is not None and q_kw >= q_s):
        nivel = "Daño Severo (> 70%)"
        pct_medio = 90.0
        dias = (row['dias_severo_min'] + row['dias_severo_max']) / 2.0
        t_txt = f"{row['lead_time_severo_txt']}"
    elif (ps_kpa is not None and ps_kpa >= ps_m) or (q_kw is not None and q_kw >= q_m):
        nivel = "Daño Medio (30% a 60%)"
        pct_medio = 45.0
        dias = (row['dias_medio_min'] + row['dias_medio_max']) / 2.0
        t_txt = f"{row['tiempo_medio_txt']}"
    elif (ps_kpa is not None and ps_kpa >= ps_l) or (q_kw is not None and q_kw >= q_l):
        nivel = "Daño Leve (5% a 25%)"
        pct_medio = 15.0
        dias = (row['dias_leve_min'] + row['dias_leve_max']) / 2.0
        t_txt = f"{row['tiempo_leve_txt']}"
    else:
        nivel = "Sin Afectación (< Umbral)"
        pct_medio = 0.0
        dias = 0.0
        t_txt = "0 días"
        
    print(f"Tipo: {tipo_eq} | Carga Ps={ps_kpa} kPa, q={q_kw} kW/m2 -> {nivel} ({pct_medio}%) | Parada: {t_txt} ({dias:.1f} días)")

test_estimacion("Torre de Destilación", 35.0, 0.0) # 35 kPa en Torre -> Medio (Ps 20-40)
test_estimacion("Horno de Proceso", 40.0, 0.0)    # 40 kPa en Horno -> Severo (Ps > 35)
test_estimacion("Horno de Proceso", 0.0, 25.0)    # 25 kW/m2 en Horno -> Medio (q=25)
test_estimacion("Horno de Proceso", 0.0, 35.0)    # 35 kW/m2 en Horno -> Severo (q >= 35)
test_estimacion("Vessel / Drum", 15.0, 0.0)       # 15 kPa en Drum -> Leve (Ps 10-20)
test_estimacion("Vessel / Drum", 2.0, 0.0)        # 2 kPa en Drum -> Sin daño (< 10)
