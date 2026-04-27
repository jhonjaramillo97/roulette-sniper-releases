"""
Navegación al lobby y mapeo dinámico de mesas.
"""

import time
from selenium.webdriver.common.by import By

from bot_ruleta.config import LOBBY_URL, TABLES
from bot_ruleta.iframe import switch_to_game_iframe, cerrar_modales
from bot_ruleta.debug_logger import get_logger, capture_screenshot

log = get_logger("lobby")


def check_session_alive(driver):
    """Verifica si la sesión de Stake sigue activa.
    Retorna True si el usuario está logueado, False si se cerró la sesión."""
    try:
        driver.switch_to.default_content()
        # Buscar indicadores de sesión cerrada
        login_buttons = driver.find_elements(
            By.XPATH,
            "//a[contains(., 'Iniciar sesión')] | //button[contains(., 'Iniciar sesión')]"
            " | //a[contains(., 'Sign in')] | //button[contains(., 'Sign in')]"
        )
        register_buttons = driver.find_elements(
            By.XPATH,
            "//a[contains(., 'Registro')] | //button[contains(., 'Registro')]"
            " | //a[contains(., 'Register')] | //button[contains(., 'Register')]"
        )
        
        # Si encontramos botones de login/registro visibles => sesión cerrada
        for btn in login_buttons:
            if btn.is_displayed():
                log.warning("🔴 SESIÓN CERRADA: Botón 'Iniciar sesión' visible")
                return False
        for btn in register_buttons:
            if btn.is_displayed():
                log.warning("🔴 SESIÓN CERRADA: Botón 'Registro' visible")
                return False
        
        # Buscar indicadores de sesión activa (billetera, menú usuario)
        session_indicators = driver.find_elements(
            By.XPATH,
            "//a[contains(@href, '/finance/wallet')] | //button[contains(., 'Billetera')]"
            " | //div[contains(@data-testid, 'user-dropdown')]"
        )
        for el in session_indicators:
            if el.is_displayed():
                log.debug("✅ Sesión activa confirmada")
                return True
        
        # No se encontró ningún indicador claro - asumir activa
        log.debug("⚠️ No se detectaron indicadores claros de sesión. Asumiendo activa.")
        return True
        
    except Exception as e:
        log.warning(f"⚠️ Error verificando sesión: {e}")
        return True  # En caso de error, asumimos activa


def _click_juego_real(driver):
    """Busca y hace clic en el botón 'Juego real' en cualquier nivel de la página.
    Retorna True si encontró y clickeó el botón."""
    selectors = [
        "//*[contains(text(), 'Juego real')]",
        "//*[contains(text(), 'Juego Real')]",
        "//*[contains(text(), 'Play for real')]",
        "//*[contains(text(), 'Real play')]",
        "//button[contains(text(), 'Play')]",
        "//a[contains(text(), 'Juego real')]",
        "//div[contains(@class, 'play-button')]",
    ]
    for xpath in selectors:
        try:
            elements = driver.find_elements(By.XPATH, xpath)
            for el in elements:
                if el.is_displayed():
                    log.info(f"   👉 Click en '{el.text.strip()}' ...")
                    driver.execute_script("arguments[0].click();", el)
                    return True
        except:
            pass
    return False


def ir_al_lobby(driver, wait, from_anti_afk=False):
    """Navega al lobby de Ruleta, entra al iframe y cierra modales.
    
    Args:
        from_anti_afk: Si True, usa browser.back() y verifica sesión.
                       Si False, navega directamente con driver.get().
    """
    log.info(f"🔄 Navegando al Lobby... (from_anti_afk={from_anti_afk})")
    try:
        if from_anti_afk:
            # -----------------------------------------------------------
            # MODO ANTI-AFK: Usar back() para preservar la sesión
            # -----------------------------------------------------------
            log.info("   ↩️ Usando browser.back() para volver al lobby...")
            capture_screenshot(driver, "AFK_01_antes_back")
            driver.back()
            time.sleep(3)
            capture_screenshot(driver, "AFK_02_despues_back")
            
            # Verificar si seguimos en la URL correcta
            current_url = driver.current_url
            log.info(f"   📍 URL actual: {current_url}")
            
            # Si back() no nos llevó al lobby, navegar directamente
            if "roulette-lobby" not in current_url and "lobby" not in current_url:
                log.warning("   ⚠️ back() no llevó al lobby, navegando directamente...")
                driver.get(LOBBY_URL)
                time.sleep(5)
                capture_screenshot(driver, "AFK_03_navegacion_directa")
            
            # VERIFICAR SESIÓN - Paso crítico
            driver.switch_to.default_content()
            capture_screenshot(driver, "AFK_04_verificando_sesion")
            
            if not check_session_alive(driver):
                log.critical("🔴 SESIÓN PERDIDA TRAS ANTI-AFK!")
                capture_screenshot(driver, "CRITICAL_sesion_perdida_anti_afk")
                # Guardar HTML para diagnóstico
                try:
                    html_path = "debug_session_lost.html"
                    with open(html_path, "w", encoding="utf-8") as f:
                        f.write(driver.page_source)
                    log.critical(f"   📄 HTML guardado: {html_path}")
                except:
                    pass
                raise Exception("SESIÓN PERDIDA: Se requiere re-login completo")
            
            log.info("   ✅ Sesión sigue activa tras Anti-AFK")
        else:
            # MODO NORMAL: Navegación directa al lobby
            driver.get(LOBBY_URL)
            time.sleep(5)

        # -----------------------------------------------------------
        # Paso 1: Buscar botón "Juego real" 
        # -----------------------------------------------------------
        driver.switch_to.default_content()
        
        # Buscar y clickear "Juego real"
        clicked = _click_juego_real(driver)

        if not clicked:
            # Buscar en iframes por si acaso (solo si no lo encontró arriba)
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            for iframe in iframes:
                try:
                    driver.switch_to.default_content()
                    driver.switch_to.frame(iframe)
                    clicked = _click_juego_real(driver)
                    if clicked:
                        break
                except:
                    pass
            driver.switch_to.default_content()

        if clicked:
            log.info("   ⏳ Esperando recarga del iframe tras 'Juego real'...")
            time.sleep(12)
            
            if from_anti_afk:
                # Si tuvimos que clickear "Juego real" en Anti-AFK, verificar sesión otra vez
                driver.switch_to.default_content()
                if not check_session_alive(driver):
                    log.critical("🔴 SESIÓN PERDIDA TRAS CLICK EN 'JUEGO REAL'!")
                    capture_screenshot(driver, "CRITICAL_sesion_perdida_juego_real", save_html=True)
                    raise Exception("SESIÓN PERDIDA tras 'Juego real': Se requiere re-login")
        else:
            if from_anti_afk:
                log.info("   ✅ Sesión activa en modo real (no requirió botón 'Juego real')")

        # -----------------------------------------------------------
        # Paso 2: Entrar al iframe del juego real
        # -----------------------------------------------------------
        if switch_to_game_iframe(driver):
            log.info("✅ Contexto cambiado al iframe del juego.")

            # Esperar activamente a que el lobby cargue los tiles
            log.info("   ⏳ Esperando a que el lobby termine de cargar...")
            max_wait = 60  # segundos máximos de espera
            poll_interval = 3
            elapsed = 0
            tiles_found = False
            while elapsed < max_wait:
                time.sleep(poll_interval)
                elapsed += poll_interval
                try:
                    tiles = driver.find_elements(
                        By.XPATH, "//div[@data-testid='tile-container']"
                    )
                    if len(tiles) > 0:
                        log.info(f"   ✅ Lobby cargado! {len(tiles)} tiles encontrados ({elapsed}s)")
                        tiles_found = True
                        break
                    curtain_visible = driver.execute_script("""
                        var c = document.querySelector('[data-testid="curtain"]');
                        if (!c) return false;
                        return !c.classList.contains('curtain_dead');
                    """)
                    if curtain_visible:
                        log.debug(f"   ⏳ Pantalla de carga activa... ({elapsed}s)")
                    else:
                        log.debug(f"   ⏳ Curtain cerrado, esperando tiles... ({elapsed}s)")
                except:
                    pass

            if not tiles_found:
                log.warning(f"⚠️ Timeout esperando tiles ({max_wait}s)")
                capture_screenshot(driver, "WARN_lobby_timeout_tiles")

            cerrar_modales(driver)
        else:
            log.error("❌ No se pudo cambiar al iframe del juego.")
            capture_screenshot(driver, "ERROR_lobby_sin_iframe")

    except Exception as e:
        log.error(f"⚠️ Error navegando al lobby: {e}")
        capture_screenshot(driver, "ERROR_lobby_navegacion")
        raise  # Re-lanzar para que el scanner maneje el reinicio


def map_tables_dynamic(driver):
    """Escanea el lobby tile por tile, extrae el título visible de cada uno,
    y actualiza dinámicamente los IDs en TABLES.  Esto hace al bot
    resiliente a cambios de IDs entre sesiones."""

    log.info("🗺️  Escaneando IDs de mesas dinámicamente (modo robusto)...")
    try:
        # Asegurar contexto iframe
        switch_to_game_iframe(driver)

        # 1. Scroll inicial para cargar la mayor cantidad de tiles posible
        log.debug("   Bajando scroll en contenedor interno...")
        try:
            scroll_script = """
                var tile = document.querySelector("[data-testid='tile-container']");
                if(tile) {
                    var p = tile.parentElement;
                    while(p) {
                        var s = getComputedStyle(p);
                        if((s.overflowY === 'scroll' || s.overflowY === 'auto')
                            && p.scrollHeight > p.clientHeight) return p;
                        p = p.parentElement;
                        if(p === document.body) break;
                    }
                }
                return null;
            """
            scroll_container = driver.execute_script(scroll_script)
            if scroll_container:
                for _ in range(5):
                    driver.execute_script(
                        "arguments[0].scrollTop += 500;", scroll_container
                    )
                    time.sleep(0.8)
                # Volver arriba
                driver.execute_script("arguments[0].scrollTop = 0;", scroll_container)
                time.sleep(0.5)
        except Exception as e:
            log.warning(f"⚠️  Error scroll dinámico: {e}")

        # 2. Recorrer CADA tile individualmente (scroll + esperar render)
        tiles = driver.find_elements(By.XPATH, "//div[@data-testid='tile-container']")
        log.info(f"   Encontrados {len(tiles)} tiles totales. Escaneando uno por uno...")

        if len(tiles) == 0:
            log.error("❌ 0 TILES ENCONTRADOS EN EL LOBBY!")
            capture_screenshot(driver, "ERROR_cero_tiles_lobby")
            try:
                with open("debug_afk_failure.html", "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
                log.error("   HTML dump guardado: 'debug_afk_failure.html'")
            except:
                pass
            return

        # Recopilar (tile_id, titulo) de todos los tiles
        lobby_tiles = []
        for i in range(len(tiles)):
            try:
                # Re-obtener tiles para evitar StaleElementReference
                current_tiles = driver.find_elements(
                    By.XPATH, "//div[@data-testid='tile-container']"
                )
                if i >= len(current_tiles):
                    break
                t = current_tiles[i]

                # Scrollear al tile → fuerza lazy-render del título
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", t
                )
                time.sleep(0.8)

                tile_id = t.get_attribute("id") or ""

                # Extraer título visible
                titulo = ""
                for sel in [
                    ".//*[@data-testid='tile-container-title']",
                    ".//div[contains(@class, 'title')]",
                    ".//span[contains(@class, 'title')]",
                ]:
                    try:
                        el = t.find_element(By.XPATH, sel)
                        txt = el.text.strip()
                        if txt and not txt.isdigit():
                            titulo = txt
                            break
                    except:
                        pass

                lobby_tiles.append((tile_id, titulo))
            except:
                pass

        # 3. Mostrar tabla de resumen
        log.info(f"\n   {'ID':<30} | TÍTULO")
        log.info(f"   {'-'*60}")
        for tid, title in lobby_tiles:
            log.info(f"   {tid:<30} | {title or '???'}")
        log.info(f"   {'-'*60}")

        # 4. Emparejar: buscar cada TABLES[].name en los títulos del lobby
        matched_table_names = set()
        for mesa in TABLES:
            config_name = mesa["name"].lower()

            best_match_id = None
            for tid, titulo in lobby_tiles:
                if not titulo:
                    continue
                lobby_name = titulo.lower()

                # Match exacto o contenido ("Mega Roulette" in "Mega Roulette")
                # pero NO match parcial falso ("Mega Roulette" != "Auto Mega Roulette")
                if lobby_name == config_name:
                    best_match_id = tid
                    break  # Match perfecto

            # Si no hubo match exacto, intentar match por contenido
            if not best_match_id:
                for tid, titulo in lobby_tiles:
                    if not titulo:
                        continue
                    lobby_name = titulo.lower()

                    # Verificar que config_name esté EN lobby_name
                    # y que no sea un match falso (ej: "Mega Roulette" vs "Auto Mega Roulette")
                    if config_name in lobby_name and len(lobby_name) - len(config_name) <= 3:
                        best_match_id = tid
                        break

            # Fallback: match por ID hardcodeado (si no se encontró por nombre)
            if not best_match_id:
                old_id = mesa["id"]
                for tid, titulo in lobby_tiles:
                    if tid.startswith(old_id) or old_id in tid:
                        best_match_id = tid
                        break

            if best_match_id:
                if mesa["id"] != best_match_id:
                    log.warning(f"   ⚠️  CAMBIO DE ID para '{mesa['name']}':")
                    log.warning(f"       Antiguo: {mesa['id']}")
                    log.warning(f"       Nuevo:   {best_match_id}")
                    mesa["id"] = best_match_id
                else:
                    log.info(f"   ✅ {mesa['name']}: ID confirmado ({mesa['id']})")
                matched_table_names.add(mesa["name"])
            else:
                log.warning(f"   ❌ ALERTA: '{mesa['name']}' NO ENCONTRADA en el lobby")

        log.info(f"\n✅ Mapeo completado. {len(matched_table_names)}/{len(TABLES)} mesas emparejadas.")
        # Flujo normal - sin screenshot

    except Exception as e:
        log.error(f"❌ Error en mapeo dinámico: {e}")
        capture_screenshot(driver, "ERROR_mapeo_dinamico")
