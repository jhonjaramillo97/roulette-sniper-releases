import time
from selenium.webdriver.common.by import By
from bot_ruleta.driver import setup_driver, login_stake
from bot_ruleta.lobby import ir_al_lobby
from bot_ruleta.config import load_credentials

def main():
    email, password = load_credentials()
    driver, wait = setup_driver()
    
    try:
        login_stake(driver, wait, email, password)
        ir_al_lobby(driver, wait)
        
        print("\n🕵️  ESCANEANDO TODOS LOS TILES DEL LOBBY...")
        
        # 1. Scroll progresivo para cargar todo
        try:
            scroll_script = """
                var tile = document.querySelector("[data-testid='tile-container']");
                if(tile) {
                    var p = tile.parentElement;
                    while(p) {
                        if(p.scrollHeight > p.clientHeight && (getComputedStyle(p).overflowY === 'scroll' || getComputedStyle(p).overflowY === 'auto')) return p;
                        p = p.parentElement;
                    }
                }
                return null;
            """
            scroll_container = driver.execute_script(scroll_script)
            if scroll_container:
                for _ in range(5):
                    driver.execute_script("arguments[0].scrollTop += 500;", scroll_container)
                    time.sleep(1)
        except:
            pass

        # 2. Extraer info iterando y scrolleando a cada uno
        tiles = driver.find_elements(By.XPATH, "//div[@data-testid='tile-container']")
        print(f"\n✅ Se encontraron {len(tiles)} tiles. Escaneando uno por uno...\n")
        print(f"{'ID':<25} | {'TÍTULO DE LA MESA'}")
        print("-" * 60)
        
        found_mega = False
        for i in range(len(tiles)):
            try:
                # Re-obtener tiles para evitar StaleElementReference
                current_tiles = driver.find_elements(By.XPATH, "//div[@data-testid='tile-container']")
                if i >= len(current_tiles): break
                t = current_tiles[i]
                
                # Scrollear al tile para que se renderice el contenido
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", t)
                time.sleep(1.0) # Esperar a que el contenido cargue
                
                tid = t.get_attribute("id")
                
                # Intentar sacar titulo con varios selectores
                title = "???"
                selectors = [
                    ".//*[@data-testid='tile-container-title']",
                    ".//span[not(re:test(text(), '^\\d+$'))]", # Experimental: span que no sea solo números
                    ".//div[contains(@class, 'title')]",
                    ".//span[contains(@class, 'title')]"
                ]
                
                for sel in selectors:
                    try:
                        el = t.find_element(By.XPATH, sel)
                        txt = el.text.strip()
                        if txt and not txt.isdigit(): # El título no debería ser solo un número
                            title = txt
                            break
                    except:
                        pass
                
                print(f"{tid:<25} | {title}")
                if title and "Mega Roulette" in title:
                    found_mega = True
            except Exception as e:
                # print(f"Error en tile {i}: {e}")
                pass
        
        print("-" * 60)
        if not found_mega:
            print("⚠️ No vi 'Mega Roulette'. Tal vez falta scrollear más o de plano no está en esta sección.")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        print("\nCierra la ventana cuando termines de copiar el ID correct.")
        # driver.quit() # Dejar abierto para debug

if __name__ == "__main__":
    main()
