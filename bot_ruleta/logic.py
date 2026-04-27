import requests
import time
from bot_ruleta.config import load_credentials

# Cache para evitar spam de notificaciones
# Key: f"{table_name}_{zone}" -> Value: timestamp de última notificación
ALERT_COOLDOWN = 60 * 5  # 5 minutos entre alertas de la misma zona
_alert_cache = {}

def compute_delays(numeros):
    """
    Calcula los delays de docenas y columnas dado una lista de números o diccionarios.
    numeros[0] es el más reciente.
    """
    from datetime import datetime
    
    delays = {
        "docena_1": 0, "docena_2": 0, "docena_3": 0,
        "columna_1": 0, "columna_2": 0, "columna_3": 0
    }
    found = {k: False for k in delays}
    
    prev_time = None

    for item in numeros:
        # Extraer el número y timestamp si es un dict/Row
        timestamp_str = None
        if hasattr(item, '__getitem__') and not isinstance(item, (str, bytes, int)):
            try:
                n = item['numero']
                timestamp_str = item.get('timestamp')
            except:
                n = item
        else:
            n = item
            
        # Validación rigurosa de continuidad (Marcador oficial de cadena rota)
        if n == -1:
            break # Topamos con un agujero ciego comprobado. Hasta aquí llega el delay actual.
            
        if n == 0:
            for k in delays:
                if not found[k]:
                    delays[k] += 1
            continue

        zones = {
            "docena_1": (1 <= n <= 12),
            "docena_2": (13 <= n <= 24),
            "docena_3": (25 <= n <= 36),
            "columna_1": (n % 3 == 1),
            "columna_2": (n % 3 == 2),
            "columna_3": (n % 3 == 0),
        }

        for k, hits in zones.items():
            if hits:
                found[k] = True
            elif not found[k]:
                delays[k] += 1

        if all(found.values()):
            break
            
    return delays

def check_and_notify(table_name, delays, history=None):
    """
    Verifica si hay delays que superen el umbral y envía notificación a Telegram.
    Maneja cooldown para no spamear.
    La notificación incluye una previsualización visual de los últimos giros.
    """
    global _alert_cache
    
    # Cargar credenciales y configuración
    _, _, token, chat_id, alert_threshold, _ = load_credentials()
    
    # DEBUG LOGGING EXTREMO
    try:
        with open("bot_ruleta/logs/debug_tg.txt", "a") as f:
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{ts}] CHECKING {table_name}: Threshold={alert_threshold} Delays={delays}\n")
    except:
        pass
    
    if not token or not chat_id:
        return

    # Usar SOLO el umbral del .env
    threshold = alert_threshold

    alerts = [k for k, v in delays.items() if v >= threshold]
    
    for zone in alerts:
        cache_key = f"{table_name}_{zone}"
        last_time = _alert_cache.get(cache_key, 0)
        
        if time.time() - last_time > ALERT_COOLDOWN:
            # Formatear el historial de los ultimos 10 números con emojis keycap
            hist_str = ""
            if history:
                recent_10 = history[:10]
                emojis = []
                keycap_map = {
                    "0": "0️⃣", "1": "1️⃣", "2": "2️⃣", "3": "3️⃣", "4": "4️⃣",
                    "5": "5️⃣", "6": "6️⃣", "7": "7️⃣", "8": "8️⃣", "9": "9️⃣"
                }
                for item in reversed(recent_10):
                    n = item["numero"] if isinstance(item, dict) else item
                    if n == 10:
                        emojis.append("🔟")
                    else:
                        emojis.append("".join(keycap_map[c] for c in str(n)))
                
                hist_str = " ".join(emojis)

            # Enviar alerta (Diseño sofisticado solicitado por usario)
            friendly_zone = zone.replace("_", " ").title()
            msg = f"🎰 *{table_name}*\n\n⚠️ Zona: *{friendly_zone}*"
            if hist_str:
                msg += f"\n\n📊 *Últimos 10 giros:*\n{hist_str}"
            
            if send_telegram_msg(token, chat_id, msg):
                print(f"✅ Notificación Telegram enviada: {table_name} - {zone}")
                
                try:
                    with open("bot_ruleta/logs/debug_tg.txt", "a") as f:
                         f.write(f"   >>> SENT ALERT for {zone} (Delay {delays[zone]})\n")
                except: pass
                
                _alert_cache[cache_key] = time.time()
        else:
            try:
                with open("bot_ruleta/logs/debug_tg.txt", "a") as f:
                     f.write(f"   >>> SKIPPED {zone} (Cooldown)\n")
            except: pass

def send_telegram_msg(token, chat_id, text):
    """Envía mensaje raw a Telegram."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        r = requests.post(url, json=payload, timeout=5)
        return r.status_code == 200
    except Exception as e:
        print(f"❌ Error enviando Telegram: {e}")
        return False

from datetime import datetime
from bot_ruleta.db import get_connection

def sync_backtest(table_name, threshold):
    """
    Sincroniza el historial de backtesting para una mesa.
    Solo procesa los giros nuevos usando un buffer de 'warmup' para mantener precisión.
    
    Robusto: guarda eventos activos antes de resetear por gaps y al final del procesamiento.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Obtener último estado
    cursor.execute("SELECT last_game_id FROM sync_state WHERE table_name = ?", (table_name,))
    row = cursor.fetchone()
    last_game_id = row[0] if row else 0
    
    # 2. Leer giros nuevos + buffer de 100 para inicializar delays
    warmup = 100
    cursor.execute(f"SELECT id, numero, timestamp FROM {table_name} WHERE id > ? ORDER BY id ASC", (max(0, last_game_id - warmup),))
    rows = cursor.fetchall()
    
    if not rows:
        conn.close()
        return

    delays = {
        "docena_1": 0, "docena_2": 0, "docena_3": 0,
        "columna_1": 0, "columna_2": 0, "columna_3": 0
    }
    
    active_events = {}
    max_id_procesado = last_game_id
    last_ts_obj = None
    last_ts_str = None
    
    def _flush_active_events(end_timestamp, force_save_warmup=False):
        """Guarda todos los eventos activos que superaron el threshold."""
        flushed = []
        for k in list(active_events.keys()):
            evt = active_events[k]
            if delays[k] >= threshold:
                evt["max_delay"] = max(evt["max_delay"], delays[k])
                # Siempre guarda si se fuerza (ej. por Cadena Rota -1), o si el evento se generó en esta nueva tanda
                if force_save_warmup or evt.get("is_new", False):
                    cursor.execute("""
                        INSERT INTO backtest_history 
                        (table_name, zone_name, start_time, end_time, max_delay, threshold_used)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (table_name, k, evt["start_time"], end_timestamp, evt["max_delay"], threshold))
                flushed.append(k)
        for k in flushed:
            active_events.pop(k, None)
    
    for row in rows:
        db_id, n, ts = row
        max_id_procesado = max(max_id_procesado, db_id)
        is_new_row = db_id > last_game_id
        
        try:
            current_ts_obj = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            last_ts_str = ts
        except:
            pass
            
        if n == -1:
            # MARCADOR OFICIAL DE CADENA ROTA
            # El escáner dictaminó que hubo giros perdidos. 
            # Guardamos lo acumulado y reseteamos.
            # force_save_warmup = is_new_row fuerza a guardar incluso los eventos que empezaron en el warmup
            _flush_active_events(last_ts_str, force_save_warmup=is_new_row)
            for k in delays: delays[k] = 0
            active_events.clear()
            continue
        
        if n == 0:
            for k in delays: delays[k] += 1
            # Actualizar max_delay si están activos
            for k in active_events:
                if delays[k] >= threshold:
                    active_events[k]["max_delay"] = max(active_events[k]["max_delay"], delays[k])
        else:
            zones = {
                "docena_1": (1 <= n <= 12),
                "docena_2": (13 <= n <= 24),
                "docena_3": (25 <= n <= 36),
                "columna_1": (n % 3 == 1),
                "columna_2": (n % 3 == 2),
                "columna_3": (n % 3 == 0),
            }
            
            for k, hits in zones.items():
                if hits:
                    if delays[k] >= threshold:
                        if k in active_events:
                            evt = active_events.pop(k)
                            if is_new_row or evt.get("is_new", False):
                                # Guardar evento completado
                                cursor.execute("""
                                    INSERT INTO backtest_history 
                                    (table_name, zone_name, start_time, end_time, max_delay, threshold_used)
                                    VALUES (?, ?, ?, ?, ?, ?)
                                """, (table_name, k, evt["start_time"], ts, evt["max_delay"], threshold))
                    else:
                        if k in active_events: active_events.pop(k) # Cleanup
                            
                    delays[k] = 0
                else:
                    delays[k] += 1
                    if delays[k] >= threshold:
                        if k not in active_events:
                            active_events[k] = {"start_time": ts, "max_delay": delays[k], "is_new": is_new_row}
                        else:
                            active_events[k]["max_delay"] = max(active_events[k]["max_delay"], delays[k])

    # 3. Guardar estado incremental
    cursor.execute("""
        REPLACE INTO sync_state (table_name, last_game_id) 
        VALUES (?, ?)
    """, (table_name, max_id_procesado))
    
    conn.commit()
    conn.close()
