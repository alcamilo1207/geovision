import sys
import re
import sqlite3
from pathlib import Path
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
EXCEL_PATH = Path(r"C:\backup 2026\daño de equipos vs tiempo de reparación vs psig y kw_m2.xlsx")
DB_PATH = Path("geovision_u044.db")

def parse_cell(txt):
    if not isinstance(txt, str):
        return {
            'ps_min': 10.0, 'ps_max': 20.0, 'q': 15.0,
            'dias_min': 3.0, 'dias_max': 7.0, 'meses_min': 0.1, 'meses_max': 0.25,
            'horas_txt': '', 'tiempo_txt': '', 'accion': ''
        }
    lines = [l.strip() for l in txt.strip().split('\n') if l.strip()]
    cabeza = lines[0] if len(lines) > 0 else ""
    tiempo_txt = lines[1] if len(lines) > 1 else ""
    accion = "\n".join(lines[2:]) if len(lines) > 2 else ""

    ps_range = re.search(r'Ps:\s*([\d\.]+)\s*-\s*([\d\.]+)\s*kPa', cabeza)
    ps_gt = re.search(r'Ps:\s*>\s*([\d\.]+)\s*kPa', cabeza)
    q_val = re.search(r'q:\s*(?:≥|>=)?\s*([\d\.]+)\s*kW/m2', cabeza)

    ps_min = float(ps_range.group(1)) if ps_range else (float(ps_gt.group(1)) if ps_gt else 10.0)
    ps_max = float(ps_range.group(2)) if ps_range else (9999.0 if ps_gt else 20.0)
    q_num = float(q_val.group(1)) if q_val else 15.0

    days_match = re.search(r'(\d+(?:\.\d+)?)\s*–\s*(\d+(?:\.\d+)?)\s*días', txt)
    weeks_match = re.search(r'(\d+(?:\.\d+)?)\s*–\s*(\d+(?:\.\d+)?)\s*semanas', txt)
    months_match = re.search(r'(\d+(?:\.\d+)?)\s*–\s*(\d+(?:\.\d+)?)\s*meses', txt)

    dias_min, dias_max = 3.0, 7.0
    meses_min, meses_max = 0.1, 0.25
    if days_match:
        dias_min = float(days_match.group(1))
        dias_max = float(days_match.group(2))
        meses_min = dias_min / 30.0
        meses_max = dias_max / 30.0
    elif weeks_match:
        dias_min = float(weeks_match.group(1)) * 7.0
        dias_max = float(weeks_match.group(2)) * 7.0
        meses_min = dias_min / 30.0
        meses_max = dias_max / 30.0
    elif months_match:
        meses_min = float(months_match.group(1))
        meses_max = float(months_match.group(2))
        dias_min = meses_min * 30.0
        dias_max = meses_max * 30.0

    return {
        'ps_min': ps_min, 'ps_max': ps_max, 'q': q_num,
        'dias_min': dias_min, 'dias_max': dias_max,
        'meses_min': meses_min, 'meses_max': meses_max,
        'tiempo_txt': tiempo_txt, 'accion': accion
    }

def seed_db():
    df = pd.read_excel(EXCEL_PATH, sheet_name="Hoja3")
    df['Categoría de Activo'] = df['Categoría de Activo'].ffill()

    col_leve = [c for c in df.columns if "Leve" in c][0]
    col_medio = [c for c in df.columns if "Medio" in c][0]
    col_severo = [c for c in df.columns if "Severo" in c][0]
    col_factores = [c for c in df.columns if "Factores" in c][0]

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS matriz_dano_reparacion (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        categoria_activo TEXT,
        tipo_equipo TEXT UNIQUE,
        ps_leve_min_kpa REAL,
        ps_leve_max_kpa REAL,
        q_leve_kw_m2 REAL,
        dano_leve_pct TEXT DEFAULT '5% – 25%',
        tiempo_leve_txt TEXT,
        dias_leve_min REAL,
        dias_leve_max REAL,
        accion_leve TEXT,
        ps_medio_min_kpa REAL,
        ps_medio_max_kpa REAL,
        q_medio_kw_m2 REAL,
        dano_medio_pct TEXT DEFAULT '30% – 60%',
        tiempo_medio_txt TEXT,
        dias_medio_min REAL,
        dias_medio_max REAL,
        accion_medio TEXT,
        ps_severo_min_kpa REAL,
        q_severo_kw_m2 REAL,
        dano_severo_pct TEXT DEFAULT '> 70% (80% – 100%)',
        lead_time_severo_txt TEXT,
        meses_severo_min REAL,
        meses_severo_max REAL,
        dias_severo_min REAL,
        dias_severo_max REAL,
        factores_variabilidad TEXT,
        raw_leve TEXT,
        raw_medio TEXT,
        raw_severo TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    for _, r in df.iterrows():
        cat = str(r['Categoría de Activo']).strip()
        tipo = str(r['Tipo de Equipo Mayor']).strip()
        r_l = str(r[col_leve])
        r_m = str(r[col_medio])
        r_s = str(r[col_severo])
        fac = str(r[col_factores]) if pd.notna(r[col_factores]) else ""

        p_l = parse_cell(r_l)
        p_m = parse_cell(r_m)
        p_s = parse_cell(r_s)

        cur.execute("""
        INSERT INTO matriz_dano_reparacion (
            categoria_activo, tipo_equipo,
            ps_leve_min_kpa, ps_leve_max_kpa, q_leve_kw_m2, dano_leve_pct, tiempo_leve_txt, dias_leve_min, dias_leve_max, accion_leve,
            ps_medio_min_kpa, ps_medio_max_kpa, q_medio_kw_m2, dano_medio_pct, tiempo_medio_txt, dias_medio_min, dias_medio_max, accion_medio,
            ps_severo_min_kpa, q_severo_kw_m2, dano_severo_pct, lead_time_severo_txt, meses_severo_min, meses_severo_max, dias_severo_min, dias_severo_max,
            factores_variabilidad, raw_leve, raw_medio, raw_severo
        ) VALUES (
            ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?
        )
        ON CONFLICT(tipo_equipo) DO UPDATE SET
            categoria_activo = excluded.categoria_activo,
            ps_leve_min_kpa = excluded.ps_leve_min_kpa,
            ps_leve_max_kpa = excluded.ps_leve_max_kpa,
            q_leve_kw_m2 = excluded.q_leve_kw_m2,
            tiempo_leve_txt = excluded.tiempo_leve_txt,
            dias_leve_min = excluded.dias_leve_min,
            dias_leve_max = excluded.dias_leve_max,
            accion_leve = excluded.accion_leve,
            ps_medio_min_kpa = excluded.ps_medio_min_kpa,
            ps_medio_max_kpa = excluded.ps_medio_max_kpa,
            q_medio_kw_m2 = excluded.q_medio_kw_m2,
            tiempo_medio_txt = excluded.tiempo_medio_txt,
            dias_medio_min = excluded.dias_medio_min,
            dias_medio_max = excluded.dias_medio_max,
            accion_medio = excluded.accion_medio,
            ps_severo_min_kpa = excluded.ps_severo_min_kpa,
            q_severo_kw_m2 = excluded.q_severo_kw_m2,
            lead_time_severo_txt = excluded.lead_time_severo_txt,
            meses_severo_min = excluded.meses_severo_min,
            meses_severo_max = excluded.meses_severo_max,
            dias_severo_min = excluded.dias_severo_min,
            dias_severo_max = excluded.dias_severo_max,
            factores_variabilidad = excluded.factores_variabilidad,
            raw_leve = excluded.raw_leve,
            raw_medio = excluded.raw_medio,
            raw_severo = excluded.raw_severo,
            updated_at = CURRENT_TIMESTAMP;
        """, (
            cat, tipo,
            p_l['ps_min'], p_l['ps_max'], p_l['q'], '5% – 25%', p_l['tiempo_txt'], p_l['dias_min'], p_l['dias_max'], p_l['accion'],
            p_m['ps_min'], p_m['ps_max'], p_m['q'], '30% – 60%', p_m['tiempo_txt'], p_m['dias_min'], p_m['dias_max'], p_m['accion'],
            p_s['ps_min'], p_s['q'], '> 70% (80% – 100%)', p_s['tiempo_txt'], p_s['meses_min'], p_s['meses_max'], p_s['dias_min'], p_s['dias_max'],
            fac, r_l, r_m, r_s
        ))

    conn.commit()
    count = cur.execute("SELECT count(*) FROM matriz_dano_reparacion;").fetchone()[0]
    conn.close()
    print(f"SUCCESS: Seeded {count} equipment rows into matriz_dano_reparacion!")

if __name__ == "__main__":
    seed_db()
