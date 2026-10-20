import sqlite3
import pandas as pd
import re
from pathlib import Path

# Ruta absoluta dinámica y portable en Windows y otros SO
DB_PATH = Path(__file__).resolve().parent / "geovision_u044.db"
EXCEL_DANO_PATH = Path(r"C:\backup 2026\daño de equipos vs tiempo de reparación vs psig y kw_m2.xlsx")

def get_connection():
    """Retorna una conexión activa a SQLite con soporte multihilo para Streamlit."""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Inicializa el esquema de base de datos sin alterar registros preexistentes."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS equipos (
        tag TEXT PRIMARY KEY,
        tipo_equipo TEXT DEFAULT 'Vessel / Drum',
        latitud REAL NOT NULL,
        longitud REAL NOT NULL,
        sustancia TEXT DEFAULT 'GLP / Propano',
        inventario_kg REAL DEFAULT 15000.0,
        presion_bar REAL DEFAULT 18.0,
        temperatura_c REAL DEFAULT 45.0,
        diametro_orificio_mm REAL DEFAULT 25.4,
        altura_fuga_m REAL DEFAULT 1.5,
        valor_reposicion_usd REAL DEFAULT 850000.0,
        lead_time_meses REAL DEFAULT 8.0,
        impacto_diario_usd REAL DEFAULT 40000.0,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    # Migración segura: agregar columnas si no existen
    for col_def in [
        ("altura_fuga_m", "REAL DEFAULT 1.5"),
        ("tipo_equipo", "TEXT DEFAULT 'Vessel / Drum'"),
        ("sustancia", "TEXT DEFAULT 'GLP / Propano'"),
        ("inventario_kg", "REAL DEFAULT 15000.0"),
        ("presion_bar", "REAL DEFAULT 18.0"),
        ("temperatura_c", "REAL DEFAULT 45.0"),
        ("diametro_orificio_mm", "REAL DEFAULT 25.4"),
        ("valor_reposicion_usd", "REAL DEFAULT 850000.0"),
        ("lead_time_meses", "REAL DEFAULT 8.0"),
        ("impacto_diario_usd", "REAL DEFAULT 40000.0")
    ]:
        try:
            cursor.execute(f"ALTER TABLE equipos ADD COLUMN {col_def[0]} {col_def[1]};")
        except sqlite3.OperationalError:
            pass  # La columna ya existe
        
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS condiciones_ambientales (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        temperatura_ambiente_c REAL DEFAULT 32.0,
        humedad_relativa_pct REAL DEFAULT 78.0,
        velocidad_viento_ms REAL DEFAULT 4.5,
        direccion_viento_deg REAL DEFAULT 45.0,
        clase_estabilidad TEXT DEFAULT 'D'
    );
    """)
    
    cursor.execute("""
    INSERT OR IGNORE INTO condiciones_ambientales (id, temperatura_ambiente_c, humedad_relativa_pct, velocidad_viento_ms, direccion_viento_deg, clase_estabilidad)
    VALUES (1, 32.0, 78.0, 4.5, 45.0, 'D');
    """)
    
    # Tabla persistente para la Matriz de % Daño y Tiempo de Reparación vs Psig y kW/m²
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS matriz_dano_reparacion (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        categoria_activo TEXT,
        tipo_equipo TEXT UNIQUE,
        ps_leve_min_kpa REAL,
        ps_leve_max_kpa REAL,
        q_leve_kw_m2 REAL,
        dano_leve_pct TEXT DEFAULT '5% – 25%',
        tiempo_leve_txt TEXT,
        dias_leve_min REAL DEFAULT 3.0,
        dias_leve_max REAL DEFAULT 7.0,
        accion_leve TEXT,
        ps_medio_min_kpa REAL,
        ps_medio_max_kpa REAL,
        q_medio_kw_m2 REAL,
        dano_medio_pct TEXT DEFAULT '30% – 60%',
        tiempo_medio_txt TEXT,
        dias_medio_min REAL DEFAULT 14.0,
        dias_medio_max REAL DEFAULT 30.0,
        accion_medio TEXT,
        ps_severo_min_kpa REAL,
        q_severo_kw_m2 REAL,
        dano_severo_pct TEXT DEFAULT '> 70% (80% – 100%)',
        lead_time_severo_txt TEXT,
        meses_severo_min REAL DEFAULT 12.0,
        meses_severo_max REAL DEFAULT 18.0,
        dias_severo_min REAL DEFAULT 360.0,
        dias_severo_max REAL DEFAULT 540.0,
        factores_variabilidad TEXT,
        raw_leve TEXT,
        raw_medio TEXT,
        raw_severo TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Verificar si está vacía para poblar desde Excel automáticamente
    cursor.execute("SELECT COUNT(*) FROM matriz_dano_reparacion;")
    count_mat = cursor.fetchone()[0]
    if count_mat == 0:
        seed_matriz_dano_reparacion(conn)

    conn.commit()
    conn.close()

def upsert_equipo_coords(tag, lat, lon):
    """Inserta o actualiza las coordenadas de un equipo."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO equipos (tag, latitud, longitud)
    VALUES (?, ?, ?)
    ON CONFLICT(tag) DO UPDATE SET
        latitud = excluded.latitud,
        longitud = excluded.longitud,
        updated_at = CURRENT_TIMESTAMP;
    """, (str(tag).strip(), float(lat), float(lon)))
    conn.commit()
    conn.close()

def get_equipos_df():
    """Retorna un DataFrame con todos los equipos registrados."""
    init_db()
    conn = get_connection()
    try:
        df = pd.read_sql_query("SELECT * FROM equipos ORDER BY tag ASC", conn)
    except Exception:
        df = pd.DataFrame()
    finally:
        conn.close()
    return df

def update_equipo_detalles(tag, tipo, sustancia, inventario, presion, temp, orificio, altura_fuga, valor_rep, lead_time, impacto_diario):
    """Actualiza las especificaciones de proceso y patrimoniales de un activo."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE equipos SET
        tipo_equipo = ?,
        sustancia = ?,
        inventario_kg = ?,
        presion_bar = ?,
        temperatura_c = ?,
        diametro_orificio_mm = ?,
        altura_fuga_m = ?,
        valor_reposicion_usd = ?,
        lead_time_meses = ?,
        impacto_diario_usd = ?,
        updated_at = CURRENT_TIMESTAMP
    WHERE tag = ?;
    """, (tipo, sustancia, float(inventario), float(presion), float(temp), float(orificio), float(altura_fuga), float(valor_rep), float(lead_time), float(impacto_diario), str(tag).strip()))
    conn.commit()
    conn.close()

def update_equipos_costos_df(df_costos):
    """
    Actualiza en lote los costos de reposición, lead time y lucro cesante
    diario de los equipos ingresados o editados por el usuario.
    """
    if df_costos is None or df_costos.empty:
        return False
    conn = get_connection()
    cur = conn.cursor()
    try:
        for _, row in df_costos.iterrows():
            tag = str(row['tag']).strip()
            val_rep = float(row.get('valor_reposicion_usd', 850000.0))
            lead = float(row.get('lead_time_meses', 12.0))
            imp = float(row.get('impacto_diario_usd', 40000.0))
            cur.execute("""
            UPDATE equipos SET
                valor_reposicion_usd = ?,
                lead_time_meses = ?,
                impacto_diario_usd = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE tag = ?;
            """, (val_rep, lead, imp, tag))
        conn.commit()
        return True
    finally:
        conn.close()

def insert_equipo_completo(tag, tipo, lat, lon, sustancia, inventario, presion, temp, orificio, altura_fuga, valor_rep, lead_time, impacto_diario):
    """Inserta un equipo con sus atributos completos."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO equipos (
        tag, tipo_equipo, latitud, longitud, sustancia,
        inventario_kg, presion_bar, temperatura_c, diametro_orificio_mm,
        altura_fuga_m, valor_reposicion_usd, lead_time_meses, impacto_diario_usd
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(tag) DO UPDATE SET
        tipo_equipo = excluded.tipo_equipo,
        latitud = excluded.latitud,
        longitud = excluded.longitud,
        sustancia = excluded.sustancia,
        inventario_kg = excluded.inventario_kg,
        presion_bar = excluded.presion_bar,
        temperatura_c = excluded.temperatura_c,
        diametro_orificio_mm = excluded.diametro_orificio_mm,
        altura_fuga_m = excluded.altura_fuga_m,
        valor_reposicion_usd = excluded.valor_reposicion_usd,
        lead_time_meses = excluded.lead_time_meses,
        impacto_diario_usd = excluded.impacto_diario_usd,
        updated_at = CURRENT_TIMESTAMP;
    """, (str(tag).strip(), tipo, float(lat), float(lon), sustancia, float(inventario), float(presion), float(temp), float(orificio), float(altura_fuga), float(valor_rep), float(lead_time), float(impacto_diario)))
    conn.commit()
    conn.close()

def delete_equipo(tag):
    """Elimina un equipo por su TAG."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM equipos WHERE tag = ?;", (str(tag).strip(),))
    conn.commit()
    conn.close()

def get_condiciones():
    """Retorna las variables meteorológicas de la planta."""
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM condiciones_ambientales WHERE id = 1;")
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {
        'temperatura_ambiente_c': 32.0,
        'humedad_relativa_pct': 78.0,
        'velocidad_viento_ms': 4.5,
        'direccion_viento_deg': 45.0,
        'clase_estabilidad': 'D'
    }

def update_condiciones(temp_amb, hum, vel_viento, dir_viento, estabilidad):
    """Actualiza las variables meteorológicas de la planta."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE condiciones_ambientales SET
        temperatura_ambiente_c = ?,
        humedad_relativa_pct = ?,
        velocidad_viento_ms = ?,
        direccion_viento_deg = ?,
        clase_estabilidad = ?
    WHERE id = 1;
    """, (float(temp_amb), float(hum), float(vel_viento), float(dir_viento), str(estabilidad)))
    conn.commit()
    conn.close()

def parse_cell_dano(txt):
    """Parsea una celda de nivel de daño de la hoja Excel con umbrales Ps, q, tiempos y acciones."""
    if not isinstance(txt, str):
        return {
            'ps_min': 10.0, 'ps_max': 20.0, 'q': 15.0,
            'dias_min': 3.0, 'dias_max': 7.0, 'meses_min': 0.1, 'meses_max': 0.25,
            'tiempo_txt': '', 'accion': ''
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

def seed_matriz_dano_reparacion(conn=None, excel_path=None):
    """Puebla o actualiza la tabla matriz_dano_reparacion a partir del archivo Excel oficial."""
    path = Path(excel_path) if excel_path else EXCEL_DANO_PATH
    if not path.exists():
        return False
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True
    
    try:
        df = pd.read_excel(path, sheet_name="Hoja3")
        df['Categoría de Activo'] = df['Categoría de Activo'].ffill()

        col_leve = [c for c in df.columns if "Leve" in c][0]
        col_medio = [c for c in df.columns if "Medio" in c][0]
        col_severo = [c for c in df.columns if "Severo" in c][0]
        col_factores = [c for c in df.columns if "Factores" in c][0]

        cur = conn.cursor()
        for _, r in df.iterrows():
            cat = str(r['Categoría de Activo']).strip()
            tipo = str(r['Tipo de Equipo Mayor']).strip()
            r_l = str(r[col_leve])
            r_m = str(r[col_medio])
            r_s = str(r[col_severo])
            fac = str(r[col_factores]) if pd.notna(r[col_factores]) else ""

            p_l = parse_cell_dano(r_l)
            p_m = parse_cell_dano(r_m)
            p_s = parse_cell_dano(r_s)

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
        return True
    finally:
        if close_after:
            conn.close()

def get_matriz_dano_reparacion_df():
    """Retorna un DataFrame con todos los registros de la matriz de daño y tiempo de reparación."""
    init_db()
    conn = get_connection()
    try:
        df = pd.read_sql_query("SELECT * FROM matriz_dano_reparacion ORDER BY id ASC", conn)
    except Exception:
        df = pd.DataFrame()
    finally:
        conn.close()
    return df

def update_matriz_dano_reparacion_df(df_updated):
    """Guarda los cambios realizados en el DataFrame en la base de datos SQLite."""
    if df_updated is None or df_updated.empty:
        return False
    conn = get_connection()
    cur = conn.cursor()
    try:
        for _, row in df_updated.iterrows():
            tipo = str(row['tipo_equipo']).strip()
            cur.execute("""
            UPDATE matriz_dano_reparacion SET
                ps_leve_min_kpa = ?, ps_leve_max_kpa = ?, q_leve_kw_m2 = ?,
                dias_leve_min = ?, dias_leve_max = ?, tiempo_leve_txt = ?, accion_leve = ?,
                ps_medio_min_kpa = ?, ps_medio_max_kpa = ?, q_medio_kw_m2 = ?,
                dias_medio_min = ?, dias_medio_max = ?, tiempo_medio_txt = ?, accion_medio = ?,
                ps_severo_min_kpa = ?, q_severo_kw_m2 = ?,
                meses_severo_min = ?, meses_severo_max = ?, dias_severo_min = ?, dias_severo_max = ?,
                lead_time_severo_txt = ?, factores_variabilidad = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE tipo_equipo = ?;
            """, (
                float(row.get('ps_leve_min_kpa', 10.0)), float(row.get('ps_leve_max_kpa', 20.0)), float(row.get('q_leve_kw_m2', 15.0)),
                float(row.get('dias_leve_min', 3.0)), float(row.get('dias_leve_max', 7.0)), str(row.get('tiempo_leve_txt', '')), str(row.get('accion_leve', '')),
                float(row.get('ps_medio_min_kpa', 25.0)), float(row.get('ps_medio_max_kpa', 40.0)), float(row.get('q_medio_kw_m2', 25.0)),
                float(row.get('dias_medio_min', 14.0)), float(row.get('dias_medio_max', 30.0)), str(row.get('tiempo_medio_txt', '')), str(row.get('accion_medio', '')),
                float(row.get('ps_severo_min_kpa', 50.0)), float(row.get('q_severo_kw_m2', 35.0)),
                float(row.get('meses_severo_min', 12.0)), float(row.get('meses_severo_max', 18.0)),
                float(row.get('dias_severo_min', 360.0)), float(row.get('dias_severo_max', 540.0)),
                str(row.get('lead_time_severo_txt', '')), str(row.get('factores_variabilidad', '')),
                tipo
            ))
        conn.commit()
        return True
    finally:
        conn.close()

def reset_matriz_dano_from_excel(excel_path=None):
    """Fuerza la recarga de la matriz de daño desde el archivo Excel."""
    conn = get_connection()
    try:
        return seed_matriz_dano_reparacion(conn, excel_path)
    finally:
        conn.close()
