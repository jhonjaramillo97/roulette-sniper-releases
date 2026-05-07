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


# ─── SEÑALES DE RACHAS DE COLOR (ROJOS/NEGROS) ───────────────────────

def compute_color_streak(numeros):
    """
    Calcula la racha actual de un color (Rojo o Negro) basándose en los números recientes.
    El verde (0) es un comodín: suma a la racha sin romperla.
    Retorna un dict: {"color": "Red"|"Black", "streak": int}
    """
    streak_color = None
    streak_count = 0
    greens_at_start = 0
    
    for item in numeros:
        # Extraer color del item
        if hasattr(item, '__getitem__') and not isinstance(item, (str, bytes, int)):
            try:
                color = item.get('color', item.get('col', ''))
                n = item.get('numero', item.get('val', -1))
            except:
                continue
        else:
            continue
        
        # Marcador de cadena rota — detener
        if n == -1:
            break
        
        # Verde (0) = comodín, suma a la racha
        if color == "Green" or n == 0:
            if streak_color is None:
                greens_at_start += 1
            else:
                streak_count += 1
            continue
        
        if color not in ("Red", "Black"):
            continue
        
        if streak_color is None:
            # Primer color real encontrado — inicia la racha
            streak_color = color
            streak_count = 1 + greens_at_start
        elif color == streak_color:
            # Mismo color — la racha sigue
            streak_count += 1
        else:
            # Color opuesto — la racha se rompe, ya no necesitamos seguir
            break
    
    return {"color": streak_color, "streak": streak_count}


def check_and_notify_color(table_name, streak_data, history=None):
    """
    Si la racha de color supera el umbral, envía notificación a Telegram.
    Usa cooldown independiente con cache key 'tablename_color_Red/Black'.
    """
    global _alert_cache
    
    from bot_ruleta.config import get_color_streak_threshold
    
    color = streak_data.get("color")
    streak = streak_data.get("streak", 0)
    threshold = get_color_streak_threshold()
    
    if not color or streak < threshold:
        return
    
    _, _, token, chat_id, _, _ = load_credentials()
    if not token or not chat_id:
        return
    
    cache_key = f"{table_name}_color_{color}"
    last_time = _alert_cache.get(cache_key, 0)
    
    if time.time() - last_time > ALERT_COOLDOWN:
        # Emoji según color
        color_emoji = "🔴" if color == "Red" else "⚫"
        color_name = "Rojos" if color == "Red" else "Negros"
        opposite = "Negro" if color == "Red" else "Rojo"
        
        # Historial visual
        hist_str = ""
        if history:
            recent_10 = history[:10]
            chips = []
            for item in reversed(recent_10):
                n = item.get("numero", item.get("val", "?"))
                c = item.get("color", item.get("col", ""))
                if c == "Red":
                    chips.append(f"🔴{n}")
                elif c == "Black":
                    chips.append(f"⚫{n}")
                else:
                    chips.append(f"🟢{n}")
            hist_str = " ".join(chips)
        
        msg = (
            f"🎰 *{table_name}*\n\n"
            f"{color_emoji} Racha: *{streak} {color_name}* consecutivos\n"
            f"💡 Señal para apostar al *{opposite}*"
        )
        if hist_str:
            msg += f"\n\n📊 *Últimos giros:*\n{hist_str}"
        
        if send_telegram_msg(token, chat_id, msg):
            print(f"✅ Alerta de color enviada: {table_name} - {streak} {color_name}")
            _alert_cache[cache_key] = time.time()


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


def sync_color_backtest(table_name, threshold):
    """
    Sincroniza el historial de rachas de color para una mesa.
    Detecta rachas de rojos/negros consecutivos (verde = comodín).
    Solo procesa giros nuevos usando un buffer de warmup.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Obtener último estado
    cursor.execute("SELECT last_game_id FROM color_sync_state WHERE table_name = ?", (table_name,))
    row = cursor.fetchone()
    last_game_id = row[0] if row else 0
    
    # 2. Leer giros nuevos + buffer
    warmup = 50
    cursor.execute(f"SELECT id, numero, color, timestamp FROM {table_name} WHERE id > ? ORDER BY id ASC", (max(0, last_game_id - warmup),))
    rows = cursor.fetchall()
    
    if not rows:
        conn.close()
        return

    # Estado de la racha actual
    current_color = None   # "Red" o "Black"
    current_count = 0
    current_start_ts = None
    active_is_new = False  # Si la racha empezó en datos nuevos
    max_id_procesado = last_game_id
    last_ts = None

    def _save_streak(end_timestamp, is_end_new):
        """Guarda la racha si supera el threshold."""
        nonlocal current_color, current_count, current_start_ts, active_is_new
        if current_color and current_count >= threshold and (active_is_new or is_end_new):
            cursor.execute("""
                INSERT INTO color_streak_history 
                (table_name, streak_color, streak_count, start_time, end_time, threshold_used)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (table_name, current_color, current_count, current_start_ts, end_timestamp, threshold))

    for row in rows:
        db_id, n, color, ts = row
        max_id_procesado = max(max_id_procesado, db_id)
        is_new_row = db_id > last_game_id
        last_ts = ts

        # Cadena rota
        if n == -1:
            _save_streak(ts, is_new_row)
            current_color = None
            current_count = 0
            current_start_ts = None
            active_is_new = False
            continue

        # Verde = comodín, suma a la racha
        if color == "Green" or n == 0:
            if current_color is not None:
                current_count += 1
                if is_new_row:
                    active_is_new = True
            continue

        if color not in ("Red", "Black"):
            continue

        if current_color is None:
            # Inicio de racha
            current_color = color
            current_count = 1
            current_start_ts = ts
            active_is_new = is_new_row
        elif color == current_color:
            # Racha sigue
            current_count += 1
            if is_new_row:
                active_is_new = True
        else:
            # Color opuesto: la racha anterior terminó
            _save_streak(ts, is_new_row)
            # Empezar nueva racha con el color actual
            current_color = color
            current_count = 1
            current_start_ts = ts
            active_is_new = is_new_row

    # No guardar la racha activa al final (aún está en progreso)

    # 3. Guardar estado incremental
    cursor.execute("""
        REPLACE INTO color_sync_state (table_name, last_game_id) 
        VALUES (?, ?)
    """, (table_name, max_id_procesado))
    
    conn.commit()
    conn.close()
