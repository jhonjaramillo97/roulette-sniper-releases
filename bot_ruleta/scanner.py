"""
Loop principal del bot: anti-AFK, escaneo de tiles, extracción y guardado de datos.
Incluye lógica de auto-reinicio ante fallos críticos.
"""

import os
import time
import random
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains

from bot_ruleta.config import (
    TABLES, DATA_DIR, LOBBY_MODE, AFK_INTERVAL, REDS, load_credentials,
)
from bot_ruleta.driver import setup_driver, login_stake
from bot_ruleta.lobby import ir_al_lobby, map_tables_dynamic
from bot_ruleta.iframe import switch_to_game_iframe
from bot_ruleta.db import init_db, guardar_resultado, obtener_ultimo_numero, obtener_ultimos_numeros
import bot_ruleta.logic as bt_logic


# ---------------------------------------------------------------------------
# Helpers internos del scanner
# ---------------------------------------------------------------------------

def extract_nums_js(driver, tile_element):
    """Extrae números visibles de un tile usando JavaScript (class-agnostic)."""
    js_script = """
        var tile = arguments[0];
        var nums = [];
        var allEls = tile.querySelectorAll('span, div');
        for (var i = 0; i < allEls.length; i++) {
            var el = allEls[i];
            var txt = el.textContent.trim();
            if (/^\\d{1,2}$/.test(txt)) {
                var num = parseInt(txt);
                if (num >= 0 && num <= 36) {
                    var childEls = el.querySelectorAll('span, div');
                    var isLeaf = true;
                    for (var j = 0; j < childEls.length; j++) {
                        if (childEls[j].textContent.trim().length > 0) {
                            isLeaf = false;
                            break;
                        }
                    }
                    if (isLeaf && el.offsetParent !== null) {
                        nums.push(txt);
                    }
                }
            }
        }
        return nums;
    """
    try:
        return driver.execute_script(js_script, tile_element)
    except:
        return []


# ---------------------------------------------------------------------------
# Sesión Unitaria (Driver Start -> Login -> Loop -> Error)
# ---------------------------------------------------------------------------

def _run_single_session(email, password, headless=True):
    """
    Ejecuta una sesión completa del bot.
    Si ocurre un error crítico, lanza una excepción para que el supervisor reinicie.
    """
    driver = None
    try:
        # 1. Setup Driver
        driver, wait = setup_driver(headless=headless)
        actions = ActionChains(driver)

        # 2. Login
        login_stake(driver, wait, email, password)

        # 3. Ir al Lobby
        ir_al_lobby(driver, wait)

        # 4. Configurar Modo Lobby
        if LOBBY_MODE:
            print("\n👀 MODO ESPÍA ACTIVADO: Escaneando miniaturas...")
            
            # Buscar iframe usando helper
            switch_to_game_iframe(driver)
            
            time.sleep(2)
            map_tables_dynamic(driver)

        # 5. Audio Keep-Alive
        try:
            driver.execute_script("""
                window.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                var osc = window.audioCtx.createOscillator();
                var gain = window.audioCtx.createGain();
                osc.type = 'sine';
                osc.frequency.setValueAtTime(440, window.audioCtx.currentTime);
                gain.gain.setValueAtTime(0.0001, window.audioCtx.currentTime);
                osc.connect(gain);
                gain.connect(window.audioCtx.destination);
                osc.start();
                setInterval(() => {
                    if(window.audioCtx.state === 'suspended') window.audioCtx.resume();
                }, 1000);
            """)
        except:
            pass

        # 6. Loop de Escaneo
        print("\n📡 Comienza escaneo continuo...")
        start_scan_time = time.time()
        
        # Contadores de errores para reinicio automático
        consecutive_zero_tiles = 0
        MAX_ZERO_TILES = 30  # ~15 segundos de fallos consecutivos

        while True:
            # Mouse Jitter
            try:
                body = driver.find_element(By.TAG_NAME, "body")
                actions.move_to_element_with_offset(body, random.randint(-50,50), random.randint(-50,50)).perform()
            except: pass

            # Anti-AFK
            if time.time() - start_scan_time > AFK_INTERVAL:
                print("\n💤 ALERTA ANTI-AFK: Entrando a mesa aleatoria...")
                try:
                    target = random.choice(TABLES)
                    t_id = target["id"]
                    print(f"👉 Entrando a '{target['name']}'...")
                    
                    try:
                        tile = driver.find_element(By.ID, t_id)
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tile)
                        time.sleep(1)
                        tile.click()
                    except:
                        driver.execute_script(f"document.getElementById('{t_id}').click();")
                    
                    time.sleep(2)
                    ir_al_lobby(driver, wait)
                    print("🔄 Re-escaneando IDs...")
                    map_tables_dynamic(driver)
                    start_scan_time = time.time()
                    continue
                except Exception as e:
                    print(f"⚠️ Fallo parcial Anti-AFK: {e}")
                    start_scan_time = time.time() # Reset timer anyway

            # Escaneo de mesas
            tables_scanned_successfully = 0
            
            for mesa in TABLES:
                nombre = mesa["name"]
                iframe_id = mesa["id"]

                try:
                    tile = driver.find_element(By.ID, iframe_id)
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", tile)
                    time.sleep(0.5) # Leve pausa para render

                    numeros = extract_nums_js(driver, tile)
                    
                    if numeros:
                        consecutive_zero_tiles = 0 # Reset contador de errores
                        tables_scanned_successfully += 1
                        
                        # --- Procesamiento de números (Logica Original) ---
                        nums_int = [int(n) for n in numeros]
                        db_history = obtener_ultimos_numeros(nombre, limit=15)
                        db_nums = [d["numero"] for d in db_history] if db_history else []
                        
                        nuevos = []
                        stale_data = False
                        
                        if db_history:
                            try:
                                from datetime import datetime
                                last_ts = datetime.strptime(db_history[0]["timestamp"], "%Y-%m-%d %H:%M:%S")
                                if (datetime.now() - last_ts).total_seconds() > 300: # 5 minutos
                                    stale_data = True
                            except:
                                pass
                                
                        if not db_nums or stale_data:
                            if stale_data:
                                import bot_ruleta.db as bt_db
                                bt_db.limpiar_mesa(nombre)
                            nuevos = list(reversed(nums_int))
                        else:
                            anchor_idx = -1
                            for i, num in enumerate(nums_int):
                                if num == db_nums[0]:
                                    match = True
                                    for j in range(1, min(3, len(db_nums), len(nums_int) - i)):
                                        if nums_int[i+j] != db_nums[j]:
                                            match = False; break
                                    if match: anchor_idx = i; break
                            
                            if anchor_idx > 0: nuevos = list(reversed(nums_int[:anchor_idx]))
                            elif anchor_idx == -1 and nums_int[0] != db_nums[0]:
                                nuevos = [nums_int[0]]

                        if nuevos:
                            print(f"🔥 {nombre}: Nuevos -> {nuevos}")
                            ts_base = time.time()
                            for idx, num in enumerate(nuevos):
                                color = "Red" if str(num) in REDS else ("Green" if num == 0 else "Black")
                                ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts_base - len(nuevos) + 1 + idx))
                                guardar_resultado(nombre, num, color, ts, int(ts_base)+idx)
                            
                            # Alertas Telegram
                            try:
                                history = obtener_ultimos_numeros(nombre, limit=100)
                                if history:
                                    delays = bt_logic.compute_delays(history)
                                    bt_logic.check_and_notify(nombre, delays, history)
                                    # Debug Log
                                    with open("bot_ruleta/logs/debug_tg.txt", "a") as f:
                                        _, _, _, _, th, _ = bt_logic.load_credentials()
                                        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {nombre} Delays={delays} TH={th}\n")
                            except Exception as e:
                                print(f"Error TG: {e}")

                    else:
                        # No numeros encontrados en este tile
                        pass

                except Exception:
                    pass
            
            # Verificación GLOBAL de salud del escaneo
            if tables_scanned_successfully == 0:
                consecutive_zero_tiles += 1
                if consecutive_zero_tiles % 5 == 0:
                    print(f"⚠️ Alerta: 0 tiles leídos por {consecutive_zero_tiles} ciclos...")
                
                if consecutive_zero_tiles >= MAX_ZERO_TILES:
                    raise Exception("MAX_ZERO_TILES alcanzado: El bot parece ciego o desconectado.")
            else:
                consecutive_zero_tiles = 0

            print(f"📡 Escaneando... [{time.strftime('%H:%M:%S')}]", end="\r", flush=True)
            time.sleep(0.5)

    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"❌ Error en sesión: {e}")
        raise # Re-lanzar para que el loop principal reinicie
    finally:
        if driver:
            print("🛑 Cerrando navegador...")
            try: driver.quit()
            except: pass


# ---------------------------------------------------------------------------
# Loop Supervisor (Entry Point)
# ---------------------------------------------------------------------------

def run_bot():
    """Loop supervisor que asegura que el bot se reinicie si falla."""
    
    # Cargar config inicial
    email, password, _, _, _, headless = load_credentials()
    init_db()

    print(f"🤖 Bot Supervisor Iniciado - Headless: {headless}")

    while True:
        try:
            _run_single_session(email, password, headless=headless)
        except KeyboardInterrupt:
            print("\n👋 Deteniendo bot por usuario.")
            break
        except Exception as e:
            print(f"\n🔄 REINICIANDO BOT EN 10 SEGUNDOS POR ERROR: {e}")
            time.sleep(10)
