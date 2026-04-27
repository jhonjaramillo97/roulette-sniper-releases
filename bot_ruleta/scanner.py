"""
Loop principal del bot: escaneo de tiles, extracción y guardado de datos.
Incluye detección de sesión expirada y auto-reinicio.
"""

import os
import time
import random
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains

from bot_ruleta.config import (
    TABLES, DATA_DIR, LOBBY_MODE, REDS, load_credentials,
)
from bot_ruleta.driver import setup_driver, login_stake
from bot_ruleta.lobby import ir_al_lobby, map_tables_dynamic
from bot_ruleta.iframe import switch_to_game_iframe
from bot_ruleta.db import init_db, guardar_resultado, obtener_ultimo_numero, obtener_ultimos_numeros
import bot_ruleta.logic as bt_logic
from bot_ruleta.debug_logger import get_logger, capture_screenshot, generate_crash_report, run_diagnostics

log = get_logger("scanner")


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

def _run_single_session(email, password, headless=True, stop_event=None):
    """
    Ejecuta una sesión completa del bot.
    Si ocurre un error crítico, lanza una excepción para que el supervisor reinicie.
    """
    driver = None
    try:
        # 1. Setup Driver
        log.info("🚀 Iniciando nueva sesión del bot...")
        driver, wait = setup_driver(headless=headless)
        actions = ActionChains(driver)
        capture_screenshot(driver, "01_driver_iniciado")

        # 2. Login
        login_stake(driver, wait, email, password)
        # Screenshot de login lo maneja driver.py (solo ante error)

        # 3. Ir al Lobby
        ir_al_lobby(driver, wait)
        capture_screenshot(driver, "03_lobby_cargado")

        # 4. Configurar Modo Lobby
        if LOBBY_MODE:
            log.info("👀 MODO ESPÍA ACTIVADO: Escaneando miniaturas...")
            
            # Buscar iframe usando helper
            switch_to_game_iframe(driver)
            capture_screenshot(driver, "04_iframe_context")
            
            time.sleep(2)
            map_tables_dynamic(driver)
            capture_screenshot(driver, "05_mesas_mapeadas")

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
            log.debug("🔊 Audio keep-alive activado")
        except:
            log.debug("⚠️ Audio keep-alive no disponible (no crítico)")

        # 6. Loop de Escaneo
        log.info("📡 Comienza escaneo continuo...")
        
        # Contadores de errores para reinicio automático
        consecutive_zero_tiles = 0
        MAX_ZERO_TILES = 30  # ~15 segundos de fallos consecutivos
        scan_cycle = 0

        while True:
            if stop_event and stop_event.is_set():
                log.info("🛑 Bot detenido por usuario (GUI).")
                return
            scan_cycle += 1
            
            # Mouse Jitter
            try:
                body = driver.find_element(By.TAG_NAME, "body")
                actions.move_to_element_with_offset(body, random.randint(-50,50), random.randint(-50,50)).perform()
            except: pass

            # -----------------------------------------------------------
            # Detección proactiva de sesión expirada (cada 30 ciclos)
            # En lugar de Anti-AFK, dejamos que Stake cierre la sesión
            # y la detectamos rápidamente para hacer soft-restart.
            # -----------------------------------------------------------
            if scan_cycle % 30 == 0:
                try:
                    driver.switch_to.default_content()
                    inactivity_els = driver.find_elements(
                        By.XPATH,
                        "//*[contains(text(), 'sesión ha finalizado')] | "
                        "//*[contains(text(), 'falta de inactividad')] | "
                        "//*[contains(text(), 'session has expired')] | "
                        "//*[contains(text(), 'vuelve a iniciar sesión')]"
                    )
                    for el in inactivity_els:
                        if el.is_displayed():
                            log.warning("⏰ Sesión expirada por inactividad. Reiniciando sesión...")
                            raise Exception("SESIÓN EXPIRADA: Reinicio automático")
                    # Restaurar contexto
                    switch_to_game_iframe(driver)
                except Exception as e:
                    if "SESIÓN EXPIRADA" in str(e):
                        raise

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
                        
                        # --- Procesamiento de números (Lógica Robusta de Anclaje) ---
                        nums_int = [int(n) for n in numeros]
                        db_history = obtener_ultimos_numeros(nombre, limit=15)
                        db_nums = [d["numero"] for d in db_history] if db_history else []
                        
                        nuevos = []
                        MIN_CHAIN = 4  # Mínimo de números consecutivos para confirmar empalme
                        
                        if not db_nums:
                            # Primera vez: no hay datos previos, insertar todo lo visible
                            nuevos = list(reversed(nums_int))
                        else:
                            # ── BÚSQUEDA ROBUSTA DE CADENA ──
                            # Buscar en TODAS las posiciones del tile nuevo contra TODAS
                            # las posiciones del historial DB, exigiendo MIN_CHAIN coincidencias
                            # consecutivas para confirmar un empalme genuino.
                            anchor_idx = -1
                            
                            for i in range(len(nums_int)):
                                for j in range(len(db_nums)):
                                    if nums_int[i] == db_nums[j]:
                                        # Verificar longitud de la cadena
                                        chain_len = 0
                                        while (i + chain_len < len(nums_int) and
                                               j + chain_len < len(db_nums) and
                                               nums_int[i + chain_len] == db_nums[j + chain_len]):
                                            chain_len += 1
                                        
                                        if chain_len >= MIN_CHAIN:
                                            anchor_idx = i
                                            break
                                
                                if anchor_idx != -1:
                                    break
                            
                            if anchor_idx > 0:
                                # Empalme confirmado: solo insertar los números nuevos (antes del ancla)
                                nuevos = list(reversed(nums_int[:anchor_idx]))
                            elif anchor_idx == 0:
                                # El tile no cambió, no hay números nuevos
                                nuevos = []
                            else:
                                # ── CADENA ROTA ──
                                # No se encontró empalme de 4+ números.
                                # Insertar todo como sesión fresca, PERO precedido
                                # del marcador oficial de ruptura de cadena (-1).
                                log.warning(f"⚠️ {nombre}: CADENA ROTA - sin empalme de {MIN_CHAIN}+ números. Reinicio de sesión.")
                                nuevos = [-1] + list(reversed(nums_int))

                        if nuevos:
                            log.info(f"🔥 {nombre}: Nuevos -> {nuevos}")
                            ts_base = time.time()
                            for idx, num in enumerate(nuevos):
                                if num == -1:
                                    color = "Reset"
                                else:
                                    color = "Red" if str(num) in REDS else ("Green" if num == 0 else "Black")
                                
                                ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts_base - len(nuevos) + 1 + idx))
                                guardar_resultado(nombre, num, color, ts, int(ts_base)+idx)
                            
                            # Alertas Telegram
                            try:
                                history = obtener_ultimos_numeros(nombre, limit=100)
                                if history:
                                    delays = bt_logic.compute_delays(history)
                                    bt_logic.check_and_notify(nombre, delays, history)
                                    log.debug(f"TG check: {nombre} Delays={delays}")
                            except Exception as e:
                                log.error(f"Error TG: {e}")

                    else:
                        # No numeros encontrados en este tile
                        pass

                except Exception as e:
                    log.debug(f"Error escaneando tile '{nombre}': {e}")
            
            # Verificación GLOBAL de salud del escaneo
            if tables_scanned_successfully == 0:
                consecutive_zero_tiles += 1
                if consecutive_zero_tiles % 5 == 0:
                    log.warning(f"⚠️ Alerta: 0 tiles leídos por {consecutive_zero_tiles} ciclos...")
                
                # Verificar inactividad inmediatamente al primer bloque de zero tiles
                if consecutive_zero_tiles >= 3:
                    try:
                        driver.switch_to.default_content()
                        inactivity_elements = driver.find_elements(
                            By.XPATH,
                            "//*[contains(text(), 'sesión ha finalizado')] | "
                            "//*[contains(text(), 'falta de inactividad')] | "
                            "//*[contains(text(), 'session has expired')] | "
                            "//*[contains(text(), 'vuelve a iniciar sesión')]"
                        )
                        for el in inactivity_elements:
                            if el.is_displayed():
                                log.warning("⏰ Sesión expirada por inactividad. Reiniciando sesión...")
                                raise Exception("SESIÓN EXPIRADA: Reinicio automático")
                        # Restaurar contexto
                        switch_to_game_iframe(driver)
                    except Exception as e:
                        if "SESIÓN EXPIRADA" in str(e):
                            raise
                
                if consecutive_zero_tiles >= MAX_ZERO_TILES:
                    capture_screenshot(driver, "CRITICAL_max_zero_tiles")
                    raise Exception("MAX_ZERO_TILES alcanzado: El bot parece ciego o desconectado.")
            else:
                consecutive_zero_tiles = 0

            # Log de heartbeat cada 60 ciclos (~30 seg)
            if scan_cycle % 60 == 0:
                log.debug(f"💓 Heartbeat: ciclo {scan_cycle}, tiles OK en último escaneo: {tables_scanned_successfully}")

            print(f"📡 Escaneando... [{time.strftime('%H:%M:%S')}]", end="\r", flush=True)
            time.sleep(0.5)

    except KeyboardInterrupt:
        raise
    except Exception as e:
        error_msg = str(e)
        if "SESIÓN EXPIRADA" in error_msg:
            # Sesión expirada por inactividad - es esperado, reinicio rápido
            log.warning(f"⏰ {error_msg}")
            log.info("🔄 Preparando reinicio rápido de sesión (Cloudflare se mantiene activo)...")
        else:
            # Error real/inesperado - generar crash report
            log.critical(f"❌ Error crítico en sesión: {e}")
            log.critical(f"Traceback completo:\n{__import__('traceback').format_exc()}")
            generate_crash_report(driver=driver, error=e)
        raise # Re-lanzar para que el loop supervisor reinicie
    finally:
        if driver:
            log.info("🛑 Cerrando navegador...")
            try: driver.quit()
            except: pass


# ---------------------------------------------------------------------------
# Loop Supervisor (Entry Point)
# ---------------------------------------------------------------------------

def run_bot(stop_event=None):
    """Loop supervisor que asegura que el bot se reinicie si falla.
    
    Args:
        stop_event: threading.Event opcional para detener el bot desde la GUI.
    """
    
    # Cargar config inicial
    email, password, _, _, _, headless = load_credentials()
    init_db()

    # Ejecutar diagnóstico de entorno
    log.info("=" * 60)
    log.info("🔧 Ejecutando diagnóstico de entorno...")
    run_diagnostics()
    log.info("=" * 60)

    log.info(f"🤖 Bot Supervisor Iniciado - Headless: {headless}")

    session_count = 0
    while True:
        if stop_event and stop_event.is_set():
            log.info("👋 Bot detenido por GUI.")
            break
        session_count += 1
        log.info(f"🔄 Iniciando sesión #{session_count}...")
        try:
            _run_single_session(email, password, headless=headless, stop_event=stop_event)
        except KeyboardInterrupt:
            log.info("👋 Deteniendo bot por usuario.")
            break
        except Exception as e:
            if stop_event and stop_event.is_set():
                break
            error_msg = str(e)
            if "SESIÓN EXPIRADA" in error_msg:
                log.info("🔄 Reiniciando sesión en 5 segundos... (el link del dashboard sigue activo)")
                time.sleep(5)
            else:
                log.critical(f"🔄 REINICIANDO BOT EN 15 SEGUNDOS POR ERROR: {e}")
                time.sleep(15)
