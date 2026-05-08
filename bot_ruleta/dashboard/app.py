import sys
import os
import sqlite3
from flask import Flask, jsonify, request, send_from_directory

# Añadir directorio raíz del proyecto al path para importar bot_ruleta
# __file__ = bot_ruleta/dashboard/app.py
# dirname = bot_ruleta/dashboard
# dirname(dirname) = bot_ruleta
# dirname(dirname(dirname)) = PROYECTO ROOT
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from bot_ruleta.config import TABLES, REDS, load_credentials, get_color_streak_threshold
from bot_ruleta.gui_credentials import load_saved_credentials
import bot_ruleta.logic as bt_logic

def get_dashboard_threshold():
    """Lee el threshold de los datos guardados por la GUI. Fallback al .env"""
    saved = load_saved_credentials()
    if saved and "threshold" in saved:
        return saved["threshold"]
    _, _, _, _, threshold, _ = load_credentials()
    return threshold

# Determinar rutas correctas para PyInstaller o desarrollo
if getattr(sys, 'frozen', False):
    # Archivos estáticos están empaquetados en MEIPASS
    static_dir = os.path.join(sys._MEIPASS, 'dashboard', 'static')
    # Datos persistentes van junto al ejecutable
    DATA_DIR = os.path.join(os.path.dirname(sys.executable), "data")
else:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    DATA_DIR = os.path.join(base_dir, "data")

app = Flask(__name__, static_url_path='', static_folder=static_dir)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # Sin caché para archivos estáticos

os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "ruleta.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def calcular_delays(table_name, limit=500):
    """Calcula los delays de docenas y columnas para una tabla dada (USANDO LOGIC COMPARTIDA)."""
    try:
        conn = get_db_connection()
        cursor = conn.execute(
            f"SELECT numero, color, timestamp FROM {table_name} ORDER BY id DESC LIMIT ?", (limit,)
        )
        rows = cursor.fetchall()
        conn.close()
    except Exception:
        return None, []

    numeros = [dict(row) for row in rows]
    
    # Usar lógica centralizada
    delays = bt_logic.compute_delays(numeros)

    return delays, numeros


# ─── RUTAS ────────────────────────────────────────────────────────────

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/mesa')
def serve_mesa():
    return send_from_directory(app.static_folder, 'mesa.html')

@app.route('/analisis')
def serve_analisis():
    return send_from_directory(app.static_folder, 'analisis.html')


@app.route('/api/mesas')
def get_mesas():
    return jsonify([{"name": t["name"], "value": t["table_name"]} for t in TABLES])


@app.route('/api/overview')
def get_overview():
    """Retorna un resumen rápido de TODAS las mesas: delay máximo y alertas."""
    from datetime import datetime
    
    # Cargar threshold dinámico
    threshold = get_dashboard_threshold()
    
    result = []
    for t in TABLES:
        tn = t["table_name"]
        delays, nums = calcular_delays(tn, limit=100)
        if delays is None:
            continue

        max_delay = max(delays.values())
        alertas = [k for k, v in delays.items() if v >= threshold]

        # Nombre bonito de la zona con mayor delay
        max_zone = max(delays, key=delays.get)
        zone_labels = {
            "docena_1": "1ª Docena", "docena_2": "2ª Docena", "docena_3": "3ª Docena",
            "columna_1": "Col. 1", "columna_2": "Col. 2", "columna_3": "Col. 3"
        }
        
        # Calcular tiempo desde la última actualización
        last_update_seconds = 999999
        if nums and "timestamp" in nums[0]:
            try:
                import time
                from datetime import datetime
                last_ts = datetime.strptime(nums[0]["timestamp"], "%Y-%m-%d %H:%M:%S")
                last_ts_seconds = time.mktime(last_ts.timetuple())
                last_update_seconds = time.time() - last_ts_seconds
            except Exception as e:
                pass

        # Calcular racha de color
        color_streak = bt_logic.compute_color_streak(
            [{"numero": n["numero"], "color": n.get("color", "Green")} for n in nums]
        ) if nums else {"color": None, "streak": 0}

        result.append({
            "name": t["name"],
            "table_name": tn,
            "max_delay": max_delay,
            "max_zone": zone_labels.get(max_zone, max_zone),
            "delays": delays,
            "alertas": alertas,
            "ultimo": nums[0]["numero"] if nums else None,
            "ultimo_color": nums[0].get("color", "Green") if nums else None,
            "last_10": [{"val": n["numero"], "col": n.get("color", "Green")} for n in nums[:10]] if nums else [],
            "last_update_seconds": last_update_seconds,
            "color_streak": color_streak
        })

    color_thresh = get_color_streak_threshold()
    return jsonify({
        "threshold": threshold,
        "color_streak_threshold": color_thresh,
        "tables": result
    })


@app.route('/api/data')
def get_data():
    from datetime import datetime
    table_name = request.args.get('mesa', 'ruleta_latina')

    # Validar tabla
    if not any(t["table_name"] == table_name for t in TABLES):
        return jsonify({"error": "Tabla no válida"}), 400

    delays, numeros = calcular_delays(table_name, limit=100)
    if delays is None:
        return jsonify({"error": "Error leyendo BD"}), 500

    # Cargar threshold dinámico
    threshold = get_dashboard_threshold()

    alertas = [k for k, v in delays.items() if v >= threshold]
    
    # Calcular edad de los datos
    last_update_seconds = 999999
    if numeros and "timestamp" in numeros[0]:
        try:
            from datetime import datetime
            import time
            last_ts = datetime.strptime(numeros[0]["timestamp"], "%Y-%m-%d %H:%M:%S")
            last_ts_seconds = time.mktime(last_ts.timetuple())
            last_update_seconds = time.time() - last_ts_seconds
        except Exception as e:
            print(f"Error parsing date {numeros[0]['timestamp']}: {e}")

    # Calcular racha de color
    color_streak = bt_logic.compute_color_streak(
        [{"numero": n["numero"], "color": n.get("color", "Green")} for n in numeros]
    ) if numeros else {"color": None, "streak": 0}

    return jsonify({
        "mesa": table_name,
        "ultimos": numeros[:20],
        "delays": delays,
        "alertas": alertas,
        "threshold": threshold,
        "color_streak": color_streak,
        "color_streak_threshold": get_color_streak_threshold(),
        "last_update_seconds": last_update_seconds
    })


@app.route('/api/backtest')
def get_backtest():
    table_name = request.args.get('mesa', 'ruleta_latina')
    if not any(t["table_name"] == table_name for t in TABLES):
        return jsonify({"error": "Tabla no válida"}), 400

    threshold = get_dashboard_threshold()
    
    # 1. Sincronizar (procesar giros nuevos)
    try:
        bt_logic.sync_backtest(table_name, threshold)
    except Exception as e:
        print(f"Error en sync_backtest: {e}")
        
    # 2. Leer historial
    try:
        conn = get_db_connection()
        cursor = conn.execute(
            "SELECT zone_name, start_time, end_time, max_delay FROM backtest_history WHERE table_name = ? ORDER BY id DESC LIMIT 100",
            (table_name,)
        )
        rows = cursor.fetchall()
        conn.close()
        
        history = [dict(row) for row in rows]
        return jsonify({"mesa": table_name, "history": history})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/backtest_color')
def get_backtest_color():
    """Historial de rachas de color completadas para una mesa."""
    table_name = request.args.get('mesa', 'ruleta_latina')
    if not any(t["table_name"] == table_name for t in TABLES):
        return jsonify({"error": "Tabla no válida"}), 400

    color_threshold = get_color_streak_threshold()
    
    # 1. Sincronizar
    try:
        bt_logic.sync_color_backtest(table_name, color_threshold)
    except Exception as e:
        print(f"Error en sync_color_backtest: {e}")
        
    # 2. Leer historial
    try:
        conn = get_db_connection()
        cursor = conn.execute(
            "SELECT streak_color, streak_count, start_time, end_time FROM color_streak_history WHERE table_name = ? ORDER BY id DESC LIMIT 100",
            (table_name,)
        )
        rows = cursor.fetchall()
        conn.close()
        
        history = [dict(row) for row in rows]
        return jsonify({"mesa": table_name, "history": history})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/analisis_global')
def get_analisis_global():
    threshold = get_dashboard_threshold()
    color_threshold = get_color_streak_threshold()
    
    # 1. Sincronizar TODAS las mesas para asegurar datos frescos
    try:
        for t in TABLES:
            bt_logic.sync_backtest(t["table_name"], threshold)
            bt_logic.sync_color_backtest(t["table_name"], color_threshold)
    except Exception as e:
        print(f"Error en sync global: {e}")
        
    # 2. Extraer historial de tercios
    try:
        conn = get_db_connection()
        cursor = conn.execute(
            "SELECT table_name, zone_name, start_time, end_time, max_delay FROM backtest_history ORDER BY id DESC"
        )
        rows = cursor.fetchall()
        history = [dict(row) for row in rows]
        
        # 3. Extraer historial de rachas de color
        cursor2 = conn.execute(
            "SELECT table_name, streak_color, streak_count, start_time, end_time FROM color_streak_history ORDER BY id DESC"
        )
        color_rows = cursor2.fetchall()
        color_history = [dict(row) for row in color_rows]
        
        conn.close()
        
        return jsonify({
            "history": history,
            "color_history": color_history,
            "threshold": threshold,
            "color_streak_threshold": color_threshold
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/signal_detail')
def get_signal_detail():
    """Devuelve las jugadas individuales que componen una señal específica."""
    table_name = request.args.get('mesa')
    start_time = request.args.get('start')
    end_time = request.args.get('end')
    pico = request.args.get('pico', type=int)
    
    if not table_name:
        return jsonify({"error": "Falta parámetro mesa"}), 400
    if not any(t["table_name"] == table_name for t in TABLES):
        return jsonify({"error": "Tabla no válida"}), 400
    
    try:
        conn = get_db_connection()
        
        if pico and pico > 0:
            if end_time:
                # La racha se rompió, así que traemos 'pico' jugadas + 1 (la que rompió la racha)
                limit = pico + 1
                cursor = conn.execute(
                    f"SELECT numero, color, timestamp FROM {table_name} "
                    f"WHERE timestamp <= ? ORDER BY id DESC LIMIT ?",
                    (end_time, limit)
                )
            else:
                # La racha está activa, así que la última jugada de la mesa pertenece a la racha
                limit = pico
                cursor = conn.execute(
                    f"SELECT numero, color, timestamp FROM {table_name} "
                    f"ORDER BY id DESC LIMIT ?",
                    (limit,)
                )
            rows = cursor.fetchall()
            rows.reverse()
        else:
            if not start_time:
                return jsonify({"error": "Se requiere start_time si no hay pico"}), 400
                
            if end_time:
                cursor = conn.execute(
                    f"SELECT numero, color, timestamp FROM {table_name} "
                    f"WHERE timestamp BETWEEN ? AND ? ORDER BY id ASC",
                    (start_time, end_time)
                )
            else:
                # Si no hay end_time (señal en progreso), traer desde start_time
                cursor = conn.execute(
                    f"SELECT numero, color, timestamp FROM {table_name} "
                    f"WHERE timestamp >= ? ORDER BY id ASC LIMIT 50",
                    (start_time,)
                )
            rows = cursor.fetchall()
        conn.close()
        
        plays = [{"numero": r["numero"], "color": r["color"], "timestamp": r["timestamp"]} for r in rows]
        return jsonify({"mesa": table_name, "plays": plays})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/tunnel')
def get_tunnel():
    """Retorna el link actual de Cloudflare si está disponible"""
    import os
    # El archivo se guarda en bot_ruleta/data/tunnel.txt por test_launcher.py
    tunnel_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "tunnel.txt")
    if os.path.exists(tunnel_file):
        try:
            with open(tunnel_file, "r") as f:
                url = f.read().strip()
                if url:
                    return jsonify({"url": url})
        except Exception:
            pass
            
    return jsonify({"url": None})


if __name__ == '__main__':
    print("Iniciando dashboard en puerto 5050...")
    app.run(port=5050, host='0.0.0.0', use_reloader=False)
