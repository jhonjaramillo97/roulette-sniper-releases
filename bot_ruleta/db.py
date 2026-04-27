"""
Manejo de base de datos SQLite con tablas separadas por juego.
"""

import sqlite3
import os
from bot_ruleta.config import TABLES

import sys

DB_NAME = "ruleta.db"
if getattr(sys, 'frozen', False):
    DATA_DIR = os.path.join(os.path.dirname(sys.executable), "data")
else:
    DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, DB_NAME)


def get_connection():
    """Retorna una conexión a la base de datos."""
    return sqlite3.connect(DB_PATH)


def init_db():
    """Inicializa la base de datos creando las tablas configuradas."""
    print(f"🗄️  Inicializando base de datos en: {DB_PATH}")
    conn = get_connection()
    cursor = conn.cursor()

    for mesa in TABLES:
        table_name = mesa.get("table_name")
        if not table_name:
            continue

        # Crear tabla específica para cada juego
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                numero      INTEGER NOT NULL,
                color       TEXT NOT NULL,
                timestamp   TEXT NOT NULL,
                game_id     INTEGER
            )
        """)
        # Índice básico por timestamp
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_ts 
            ON {table_name}(timestamp)
        """)

    # Tabla global para historial de backtesting (señales completadas)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS backtest_history (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name      TEXT NOT NULL,
            zone_name       TEXT NOT NULL,
            start_time      TEXT NOT NULL,
            end_time        TEXT,
            max_delay       INTEGER NOT NULL,
            threshold_used  INTEGER NOT NULL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_backtest_table ON backtest_history(table_name)")

    # Tabla para estado de sincronización incremental
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sync_state (
            table_name      TEXT PRIMARY KEY,
            last_game_id    INTEGER NOT NULL
        )
    """)

    conn.commit()
    conn.close()
    print("✅ Tablas verificadas/creadas.")


def guardar_resultado(mesa_nombre, numero, color, timestamp, game_id):
    """Guarda un resultado en la tabla específica del juego."""
    # Buscar el table_name correspondiente al nombre descriptivo o usar directo si ya viene
    table_name = None
    for t in TABLES:
        if t["name"] == mesa_nombre or t["table_name"] == mesa_nombre:
            table_name = t["table_name"]
            break
    
    if not table_name:
        print(f"⚠️ Error BD: No se encontró tabla para '{mesa_nombre}'")
        return

    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # INSERT directo a la tabla del juego
        cursor.execute(f"""
            INSERT INTO {table_name} (numero, color, timestamp, game_id)
            VALUES (?, ?, ?, ?)
        """, (numero, color, timestamp, game_id))
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ Error guardando en BD ({table_name}): {e}")


def obtener_ultimo_numero(mesa_nombre):
    """Obtiene el último número registrado en la tabla del juego."""
    table_name = _resolve_table_name(mesa_nombre)
    if not table_name:
        return None

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT numero FROM {table_name} ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        if row:
            return row[0]
    except:
        pass
    return None


def obtener_ultimos_numeros(mesa_nombre, limit=15):
    """Obtiene los últimos N registros (número y timestamp)."""
    table_name = _resolve_table_name(mesa_nombre)
    if not table_name:
        return []

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT numero, timestamp FROM {table_name} ORDER BY id DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [{"numero": r[0], "timestamp": r[1]} for r in rows]
    except Exception as e:
        print(f"Error obtener_ultimos_numeros: {e}")
        return []


def _resolve_table_name(mesa_nombre):
    """Resuelve el nombre de tabla SQLite a partir del nombre descriptivo."""
    for t in TABLES:
        if t["name"] == mesa_nombre or t["table_name"] == mesa_nombre:
            return t["table_name"]
    return None

def limpiar_mesa(mesa_nombre):
    """Elimina todos los registros de la tabla de una mesa específica. 
    Usado cuando se detecta que el bot estuvo apagado mucho tiempo y los datos en pantalla no empalman."""
    table_name = _resolve_table_name(mesa_nombre)
    if not table_name:
        return

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM {table_name}")
        conn.commit()
        conn.close()
        print(f"🧹 Historial limpiado para la mesa '{mesa_nombre}' (Sesión Stale detectada)")
    except Exception as e:
        print(f"⚠️ Error limpiando BD ({table_name}): {e}")
