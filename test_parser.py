import sys
import re
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
excel_path = r"C:\backup 2026\daño de equipos vs tiempo de reparación vs psig y kw_m2.xlsx"
df = pd.read_excel(excel_path, sheet_name="Hoja3")
df['Categoría de Activo'] = df['Categoría de Activo'].ffill()

col_leve = [c for c in df.columns if "Leve" in c][0]
col_medio = [c for c in df.columns if "Medio" in c][0]
col_severo = [c for c in df.columns if "Severo" in c][0]
col_factores = [c for c in df.columns if "Factores" in c][0]

def parse_cell(txt):
    if not isinstance(txt, str):
        return {}
    # Ps regex: Ps: 10 - 20 kPa or Ps: > 80 kPa or Ps: 3.5 - 10 kPa
    ps_range = re.search(r'Ps:\s*([\d\.]+)\s*-\s*([\d\.]+)\s*kPa', txt)
    ps_gt = re.search(r'Ps:\s*>\s*([\d\.]+)\s*kPa', txt)
    q_val = re.search(r'q:\s*(?:≥|>=)?\s*([\d\.]+)\s*kW/m2', txt)
    
    ps_min = float(ps_range.group(1)) if ps_range else (float(ps_gt.group(1)) if ps_gt else None)
    ps_max = float(ps_range.group(2)) if ps_range else (9999.0 if ps_gt else None)
    q_num = float(q_val.group(1)) if q_val else None
    
    # Days / weeks / months
    days_match = re.search(r'(\d+)\s*–\s*(\d+)\s*días', txt)
    weeks_match = re.search(r'(\d+(?:\.\d+)?)\s*–\s*(\d+(?:\.\d+)?)\s*semanas', txt)
    months_match = re.search(r'(\d+(?:\.\d+)?)\s*–\s*(\d+(?:\.\d+)?)\s*meses', txt)
    
    dias_min, dias_max = 0, 0
    if days_match:
        dias_min = float(days_match.group(1))
        dias_max = float(days_match.group(2))
    elif weeks_match:
        dias_min = float(weeks_match.group(1)) * 7.0
        dias_max = float(weeks_match.group(2)) * 7.0
    elif months_match:
        dias_min = float(months_match.group(1)) * 30.0
        dias_max = float(months_match.group(2)) * 30.0
        
    return {
        'ps_min': ps_min, 'ps_max': ps_max, 'q': q_num,
        'dias_min': dias_min, 'dias_max': dias_max
    }

for idx, r in df.iterrows():
    p_l = parse_cell(r[col_leve])
    p_m = parse_cell(r[col_medio])
    p_s = parse_cell(r[col_severo])
    print(f"[{idx}] {r['Tipo de Equipo Mayor']}:")
    print(f"   LEVE: Ps [{p_l['ps_min']}-{p_l['ps_max']}] kPa | q: {p_l['q']} kW/m2 | Días: {p_l['dias_min']}-{p_l['dias_max']}")
    print(f"   MEDIO: Ps [{p_m['ps_min']}-{p_m['ps_max']}] kPa | q: {p_m['q']} kW/m2 | Días: {p_m['dias_min']}-{p_m['dias_max']}")
    print(f"   SEVERO: Ps > {p_s['ps_min']} kPa | q: {p_s['q']} kW/m2 | Días: {p_s['dias_min']}-{p_s['dias_max']}")
