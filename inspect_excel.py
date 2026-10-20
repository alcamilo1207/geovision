import sys
import io
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

for idx, r in df.iterrows():
    print(f"[{idx}] {r['Categoría de Activo']} -> {r['Tipo de Equipo Mayor']}")
    print(f"  LEVE: {r[col_leve][:100]}...")
    print(f"  MEDIO: {r[col_medio][:100]}...")
    print(f"  SEVERO: {r[col_severo][:100]}...")
    print("-" * 50)
