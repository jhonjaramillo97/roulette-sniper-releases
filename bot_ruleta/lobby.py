"""
Navegación al lobby y mapeo dinámico de mesas.
"""

import time
from selenium.webdriver.common.by import By

from bot_ruleta.config import LOBBY_URL, TABLES
from bot_ruleta.iframe import switch_to_game_iframe, cerrar_modales


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
                    print(f"   👉 Click en '{el.text.strip()}' ...")
                    driver.execute_script("arguments[0].click();", el)
                    return True
        except:
            pass
    return False


def ir_al_lobby(driver, wait):
    """Navega al lobby de Ruleta, entra al iframe y cierra modales."""
    print("🔄 Navegando al Lobby...")
    try:
        driver.get(LOBBY_URL)
        time.sleep(5)

        # -----------------------------------------------------------
        # Paso 1: Buscar botón "Juego real" en la PAGINA PRINCIPAL
        # -----------------------------------------------------------
        driver.switch_to.default_content()
        clicked = _click_juego_real(driver)

        if not clicked:
            # Paso 1b: El botón puede estar DENTRO del iframe demo
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
            print("   ⏳ Esperando recarga del iframe tras 'Juego real'...")
            time.sleep(12)

         # -----------------------------------------------------------
        # Paso 2: Entrar al iframe del juego real
        # -----------------------------------------------------------
        if switch_to_game_iframe(driver):
            print("✅ Contexto cambiado al iframe del juego.")

            # Esperar activamente a que el lobby cargue los tiles
            # En headless la pantalla de carga ("curtain") tarda mucho más
            print("   ⏳ Esperando a que el lobby termine de cargar...")
            max_wait = 60  # segundos máximos de espera
            poll_interval = 3
            elapsed = 0
            tiles_found = False
            while elapsed < max_wait:
                time.sleep(poll_interval)
                elapsed += poll_interval
                # Verificar si ya hay tiles visibles
                try:
                    tiles = driver.find_elements(
                        By.XPATH, "//div[@data-testid='tile-container']"
                    )
                    if len(tiles) > 0:
                        print(f"   ✅ Lobby cargado! {len(tiles)} tiles encontrados ({elapsed}s)")
                        tiles_found = True
                        break
                    # Verificar si el curtain aún está visible
                    curtain_visible = driver.execute_script("""
                        var c = document.querySelector('[data-testid="curtain"]');
                        if (!c) return false;
                        return !c.classList.contains('curtain_dead');
                    """)
                    if curtain_visible:
                        print(f"   ⏳ Pantalla de carga activa... ({elapsed}s)", end="\r", flush=True)
                    else:
                        print(f"   ⏳ Curtain cerrado, esperando tiles... ({elapsed}s)", end="\r", flush=True)
                except:
                    pass

            if not tiles_found:
                print(f"\n   ⚠️ Timeout esperando tiles ({max_wait}s)")

            cerrar_modales(driver)
        else:
            print("⚠️ No se pudo cambiar al iframe del juego.")

    except Exception as e:
        print(f"⚠️ Error navegando al lobby: {e}")


def map_tables_dynamic(driver):
    """Escanea el lobby tile por tile, extrae el título visible de cada uno,
    y actualiza dinámicamente los IDs en TABLES.  Esto hace al bot
    resiliente a cambios de IDs entre sesiones."""

    print("🗺️  Escaneando IDs de mesas dinámicamente (modo robusto)...")
    try:
        # Asegurar contexto iframe
        switch_to_game_iframe(driver)

        # 1. Scroll inicial para cargar la mayor cantidad de tiles posible
        print("   Bajando scroll en contenedor interno...")
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
            print(f"⚠️  Error scroll dinámico: {e}")

        # 2. Recorrer CADA tile individualmente (scroll + esperar render)
        tiles = driver.find_elements(By.XPATH, "//div[@data-testid='tile-container']")
        print(f"   Encontrados {len(tiles)} tiles totales. Escaneando uno por uno...")

        if len(tiles) == 0:
            try:
                with open("debug_afk_failure.html", "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
                print("❌ 0 TILES! DUMP HTML GUARDADO: 'debug_afk_failure.html'")
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
        print(f"\n   {'ID':<30} | TÍTULO")
        print(f"   {'-'*60}")
        for tid, title in lobby_tiles:
            print(f"   {tid:<30} | {title or '???'}")
        print(f"   {'-'*60}")

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
                    print(f"   ⚠️  CAMBIO DE ID para '{mesa['name']}':")
                    print(f"       Antiguo: {mesa['id']}")
                    print(f"       Nuevo:   {best_match_id}")
                    mesa["id"] = best_match_id
                else:
                    print(f"   ✅ {mesa['name']}: ID confirmado ({mesa['id']})")
                matched_table_names.add(mesa["name"])
            else:
                print(f"   ❌ ALERTA: '{mesa['name']}' NO ENCONTRADA en el lobby")

        print(f"\n✅ Mapeo completado. {len(matched_table_names)}/{len(TABLES)} mesas emparejadas.")

    except Exception as e:
        print(f"❌ Error en mapeo dinámico: {e}")
