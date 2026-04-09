"""
Test rápido - verifica que el fix completo funciona en headless.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import time
from selenium.webdriver.common.by import By
from bot_ruleta.config import LOBBY_URL, load_credentials
from bot_ruleta.driver import setup_driver, login_stake
from bot_ruleta.lobby import ir_al_lobby
from bot_ruleta.iframe import switch_to_game_iframe

def test():
    print("\n" + "="*60)
    print("  TEST HEADLESS - CON ESPERA ACTIVA DE TILES")
    print("="*60 + "\n")
    
    email, password, _, _, _, _ = load_credentials()
    driver, wait = setup_driver(headless=True)
    
    try:
        login_stake(driver, wait, email, password)
        ir_al_lobby(driver, wait)
        
        # Verificar
        switch_to_game_iframe(driver)
        time.sleep(2)
        
        tiles = driver.find_elements(By.XPATH, "//div[@data-testid='tile-container']")
        print(f"\n{'='*40}")
        print(f"  TILES ENCONTRADOS: {len(tiles)}")
        
        if tiles:
            for i, t in enumerate(tiles[:5]):
                tid = t.get_attribute("id") or "?"
                # buscar titulo
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
                print(f"  [{i}] ID={tid[:30]} | {titulo}")
            print(f"  ... (primeros 5 de {len(tiles)})")
            print(f"\n  === TEST EXITOSO ===")
        else:
            print(f"  === TEST FALLIDO ===")
        print(f"{'='*40}")
        
        driver.save_screenshot("debug_screenshot_FINAL.png")
            
    except Exception as e:
        print(f"\n  ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        driver.quit()


if __name__ == "__main__":
    test()
