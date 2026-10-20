import sys
import sqlite3
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
from consecuencias import TIPOS_EQUIPO_DISPONIBLES

conn = sqlite3.connect("geovision_u044.db")
df_matriz = pd.read_sql("SELECT id, categoria_activo, tipo_equipo FROM matriz_dano_reparacion", conn)
conn.close()

print("MATRIZ EQUIPOS (25):")
for _, r in df_matriz.iterrows():
    print(f"  [{r['id']}] {r['tipo_equipo']}")

print("\nTIPOS EN CATÁLOGO DISPONIBLES:")
for t in TIPOS_EQUIPO_DISPONIBLES:
    print(f"  - {t}")
