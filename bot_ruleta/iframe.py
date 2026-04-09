"""
Manejo de contexto iframe y cierre de modales/popups.
"""

import time
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys


def switch_to_game_iframe(driver):
    """Intenta cambiar al iframe donde vive el lobby/juego (incluyendo anidados). Retorna True si tuvo éxito."""
    try:
        driver.switch_to.default_content()
        switched = False
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for iframe in iframes:
            src = iframe.get_attribute("src") or ""
            cls = iframe.get_attribute("class") or ""
            if "game" in cls or "pragmatic" in src or "gs2c" in src:
                driver.switch_to.frame(iframe)
                switched = True
                break
                
        # Fallback: usar el primero disponible
        if not switched and len(iframes) > 0:
            driver.switch_to.frame(iframes[0])
            switched = True

        if switched:
            time.sleep(1) # Esperar al renderizado del DOM interno
            inner_iframes = driver.find_elements(By.TAG_NAME, "iframe")
            for inner in inner_iframes:
                name = inner.get_attribute("name") or ""
                src = inner.get_attribute("src") or ""
                if "shell-app" in name or "lobby" in src:
                    driver.switch_to.frame(inner)
                    break
            return True
            
    except Exception as e:
        print(f"⚠️ Error cambiando iframe: {e}")
        pass
    return False


def cerrar_modales(driver):
    """Intenta cerrar modales/popups que bloquean la vista (dentro del iframe)."""
    print("🛡️ Verificando modales bloquantes...")
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
                    print(f"   Click en cerrar modal: {xpath}")
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(1)
            except:
                pass

    except Exception as e:
        print(f"⚠️ Error al cerrar modales: {e}")
