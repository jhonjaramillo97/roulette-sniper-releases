"""
Manejo de contexto iframe y cierre de modales/popups.
"""

import time
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from bot_ruleta.debug_logger import get_logger, capture_screenshot

log = get_logger("iframe")


def switch_to_game_iframe(driver, max_wait=15):
    """Intenta cambiar al iframe donde vive el lobby/juego (incluyendo anidados). Retorna True si tuvo éxito."""
    try:
        driver.switch_to.default_content()
        switched = False
        
        log.debug(f"   ⏳ Esperando iframe principal (max {max_wait}s)...")
        for _ in range(max_wait):
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            if iframes:
                for idx, iframe in enumerate(iframes):
                    src = iframe.get_attribute("src") or ""
                    cls = iframe.get_attribute("class") or ""
                    name = iframe.get_attribute("name") or ""
                    
                    if "game" in cls or "pragmatic" in src or "gs2c" in src:
                        driver.switch_to.frame(iframe)
                        log.info(f"   ✅ Cambio a iframe #{idx} (class='{cls}')")
                        switched = True
                        break
                
                if switched:
                    break
                
                # Fallback si no encontró el específico pero sí hay iframes (y han pasado unos segundos)
                if _ > 5 and len(iframes) > 0:
                    log.debug(f"   Usando fallback: iframe #0")
                    driver.switch_to.frame(iframes[0])
                    switched = True
                    break
            time.sleep(1)

        if switched:
            # Esperar activamente al iframe anidado o a los elementos del juego
            log.debug(f"   ⏳ Esperando iframe anidado o elementos del juego (max {max_wait}s)...")
            for _ in range(max_wait):
                # 1. Verificar si los elementos (tiles o curtain) ya están en el iframe actual
                # (Stake/Pragmatic a veces cambia la estructura y elimina el iframe anidado)
                try:
                    tiles = driver.find_elements(By.XPATH, "//*[@data-testid='tile-container'] | //*[@data-testid='curtain']")
                    if len(tiles) > 0:
                        log.info("   ✅ Elementos del juego encontrados en el iframe principal. No requiere anidado.")
                        return True
                except: pass
                
                # 2. Buscar iframe anidado clásico
                inner_iframes = driver.find_elements(By.TAG_NAME, "iframe")
                if inner_iframes:
                    for idx, inner in enumerate(inner_iframes):
                        name = inner.get_attribute("name") or ""
                        src = inner.get_attribute("src") or ""
                        
                        if "shell-app" in name or "lobby" in src:
                            driver.switch_to.frame(inner)
                            log.info(f"   ✅ Cambio a iframe anidado '{name}'")
                            return True
                time.sleep(1)
            
            log.warning("   ⚠️ Iframe anidado no encontrado. Continuaremos en el iframe principal.")
            return True
            
    except Exception as e:
        log.error(f"⚠️ Error cambiando iframe: {e}")
        capture_screenshot(driver, "ERROR_cambio_iframe")
    return False


def cerrar_modales(driver):
    """Intenta cerrar modales/popups que bloquean la vista (dentro del iframe)."""
    log.info("🛡️ Verificando modales bloquantes...")
    try:
        # 1. Intentar tecla ESC
        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        time.sleep(1)

        # 2. Buscar botones de cierre comunes
        cierre_selectors = [
            "//button[contains(@aria-label, 'Close')]",
            "//button[contains(@aria-label, 'Cerrar')]",
            "//div[@data-testid='modal-close-button']",
            "//button[contains(text(), 'Juega aquí')]",
            "//button[contains(text(), 'Entendido')]",
        ]

        for xpath in cierre_selectors:
            try:
                btn = driver.find_element(By.XPATH, xpath)
                if btn.is_displayed():
                    log.info(f"   Click en cerrar modal: {xpath}")
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(1)
            except:
                pass

    except Exception as e:
        log.warning(f"⚠️ Error al cerrar modales: {e}")
