"""
Configuración y creación del WebDriver + flujo de login.
"""

import os
import time
import random
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from bot_ruleta.config import LOBBY_URL
from bot_ruleta.helpers import human_type
from bot_ruleta.debug_logger import get_logger, capture_screenshot

log = get_logger("driver")


def get_chrome_major_version():
    """Detecta la versión principal de Chrome instalada para evitar mismatch."""
    import platform
    try:
        if platform.system() == "Windows":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
            version, _ = winreg.QueryValueEx(key, "version")
            log.info(f"🌐 Chrome detectado: v{version}")
            return int(version.split('.')[0])
    except Exception as e:
        log.warning(f"⚠️ No se pudo detectar versión de Chrome: {e}")
    return None

def setup_driver(headless=True):
    """Configura y retorna (driver, wait)."""
    log.info(f"⚙️ Configurando WebDriver (headless={headless})...")
    options = uc.ChromeOptions()
    # options.add_argument("--mute-audio")  <-- REMOVIDO para evitar throttling extremo
    
    # -------------------------------------------------------------------------
    # Evitar Congelamiento en Segundo Plano (IMPORTANTE para Lobby)
    # -------------------------------------------------------------------------
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-backgrounding-occluded-windows")
    options.add_argument("--disable-renderer-backgrounding")
    options.add_argument("--disable-features=CalculateNativeWinOcclusion")  # <--- CLAVE PARA MINIMIZAR

    if headless:
        log.info("👻 Modo Headless (ventana fuera de pantalla)...")
        # ---------------------------------------------------------------
        # NOTA: Pragmatic Play detecta --headless=new y bloquea la carga
        # del lobby indefinidamente. Usamos Chrome real pero con la ventana
        # fuera de la pantalla visible. Para el servidor es Chrome normal,
        # para el usuario es invisible.
        # ---------------------------------------------------------------
        options.add_argument("--window-position=-2400,-2400")
    else:
        log.info("🖥️ Modo Visible (con ventana)...")
        
    options.add_argument("--window-size=1920,1080") 
    options.add_argument("--no-first-run")
    options.add_argument("--no-service-autorun")
    options.add_argument("--password-store=basic")

    log.info("🚀 Iniciando Chrome con undetected_chromedriver...")
    
    # Prevenir crash de PyInstaller por driver corrupto de UC
    try:
        import shutil
        uc_path = os.path.join(os.environ.get('APPDATA', ''), 'undetected_chromedriver')
        if os.path.exists(uc_path):
            shutil.rmtree(uc_path, ignore_errors=True)
    except Exception:
        pass
    
    # Obtener versión dinámica para que no falle al actualizar Chrome
    chrome_version = get_chrome_major_version()
    try:
        if chrome_version:
            log.info(f"   Usando version_main={chrome_version}")
            driver = uc.Chrome(options=options, version_main=chrome_version)
        else:
            log.info("   Usando detección automática de versión")
            driver = uc.Chrome(options=options)
        
        # --- ANTI DETECCIÓN (CDP) AVANZADA ---
        driver.execute_cdp_cmd("Network.setUserAgentOverride", {
            "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "acceptLanguage": "es-ES,es;q=0.9,en;q=0.8,en-US;q=0.7",
            "platform": "Win32"
        })
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                // 1. Ocultar webdriver
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                
                // 2. Mock de window.chrome
                window.chrome = {
                    runtime: {}
                };
                
                // 3. Mock de plugins y languages
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['es-ES', 'es', 'en', 'en-US']});
                
                // 4. Bypass de navigator.permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
                
                // 5. Eliminar variables CDC de Selenium
                for (let key in window) {
                    if (key.startsWith('cdc_')) {
                        delete window[key];
                    }
                }
            """
        })
        log.info("🛡️ Parches Anti-Detección Avanzados (CDP) aplicados.")
        
        log.info("✅ Chrome iniciado correctamente")
    except Exception as e:
        log.critical(f"❌ FALLO AL INICIAR CHROME: {e}")
        log.critical(f"   Esto puede indicar: Chrome no instalado, versión incompatible, o permisos insuficientes")
        raise

    if headless:
        _hide_chrome_window(driver)
        
    wait = WebDriverWait(driver, 30)
    return driver, wait


# ---------------------------------------------------------------------------
# Ocultar ventana de Chrome de la barra de tareas + protección anti-minimize
# ---------------------------------------------------------------------------

def _hide_chrome_window(driver):
    """Oculta la ventana de Chrome de la barra de tareas y la mueve fuera de la pantalla.
    Busca la ventana por PID del proceso Chrome (determinístico, no depende del título).
    Lanza un hilo vigilante que la restaura si alguien la minimiza accidentalmente."""
    import platform
    if platform.system() != "Windows":
        return

    import ctypes
    import ctypes.wintypes
    import threading

    user32 = ctypes.windll.user32

    # Constantes Win32
    GWL_EXSTYLE       = -20
    WS_EX_APPWINDOW   = 0x00040000  # Aparece en barra de tareas
    WS_EX_TOOLWINDOW  = 0x00000080  # NO aparece en barra de tareas
    SW_HIDE           = 0
    SW_SHOWNOACTIVATE = 4
    SW_RESTORE        = 9
    SWP_NOMOVE        = 0x0002
    SWP_NOSIZE        = 0x0001
    SWP_NOACTIVATE    = 0x0010
    SWP_FRAMECHANGED  = 0x0020

    # Obtener el PID del proceso Chrome desde el driver
    chrome_pid = None
    try:
        chrome_pid = driver.service.process.pid
    except Exception:
        pass
    if not chrome_pid:
        try:
            chrome_pid = driver.browser_pid
        except Exception:
            pass
    
    if not chrome_pid:
        log.warning("⚠️ No se pudo obtener PID de Chrome, fallback a búsqueda por título")
    
    def _find_hwnd_by_pid(target_pid):
        """Busca ventanas de nivel superior pertenecientes al proceso Chrome o sus hijos."""
        results = []
        
        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        def enum_callback(h, _lparam):
            if user32.IsWindowVisible(h):
                # Obtener PID de la ventana
                pid = ctypes.wintypes.DWORD()
                user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
                window_pid = pid.value
                
                # Chrome puede lanzar procesos hijos; verificar si es el proceso padre
                # o un hijo directo (el renderer). Aceptamos ambos.
                if window_pid == target_pid:
                    # Verificar que sea una ventana principal (tiene tamaño razonable)
                    rect = ctypes.wintypes.RECT()
                    user32.GetWindowRect(h, ctypes.byref(rect))
                    width = rect.right - rect.left
                    height = rect.bottom - rect.top
                    if width > 200 and height > 200:
                        results.append(h)
            return True
        
        user32.EnumWindows(enum_callback, 0)
        return results
    
    def _find_hwnd_by_title():
        """Fallback: busca por título de ventana."""
        results = []
        
        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        def enum_callback(h, _lparam):
            if user32.IsWindowVisible(h):
                length = user32.GetWindowTextLengthW(h)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(h, buf, length + 1)
                    title = buf.value
                    if title and ("Chrome" in title or "Stake" in title or "stake" in title or "data:," in title):
                        results.append(h)
            return True
        
        user32.EnumWindows(enum_callback, 0)
        return results

    # Intentar encontrar la ventana con reintentos
    hwnd = None
    for attempt in range(5):
        time.sleep(2)
        
        if chrome_pid:
            found = _find_hwnd_by_pid(chrome_pid)
            if found:
                hwnd = found[0]
                log.debug(f"🛡️ HWND encontrado por PID {chrome_pid} en intento {attempt+1}")
                break
        
        # Fallback a búsqueda por título
        found = _find_hwnd_by_title()
        if found:
            hwnd = found[0]
            log.debug(f"🛡️ HWND encontrado por título en intento {attempt+1}")
            break
        
        log.debug(f"⏳ Esperando ventana Chrome (intento {attempt+1}/5)...")

    if not hwnd:
        log.warning("⚠️ HWND no encontrado tras 5 intentos, Chrome seguirá visible en taskbar")
        return

    def _apply_hide(target_hwnd):
        """Aplica el ocultamiento completo a un HWND."""
        try:
            user32.ShowWindow(target_hwnd, SW_HIDE)
            style = user32.GetWindowLongW(target_hwnd, GWL_EXSTYLE)
            style = (style & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW
            user32.SetWindowLongW(target_hwnd, GWL_EXSTYLE, style)
            user32.SetWindowPos(
                target_hwnd, None, -2400, -2400, 0, 0,
                SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED
            )
            user32.ShowWindow(target_hwnd, SW_SHOWNOACTIVATE)
            return True
        except Exception:
            return False

    if _apply_hide(hwnd):
        log.info("🛡️ Chrome oculto de la barra de tareas y movido fuera de pantalla")
    else:
        log.warning("⚠️ Error ocultando ventana")
        return

    # Hilo vigilante: verifica que Chrome siga oculto y busca ventanas nuevas
    def _watchdog():
        current_hwnd = hwnd
        while True:
            try:
                # Verificar si el HWND actual sigue siendo válido
                if not user32.IsWindow(current_hwnd):
                    # La ventana fue cerrada (reinicio del bot), buscar nueva
                    if chrome_pid:
                        found = _find_hwnd_by_pid(chrome_pid)
                    else:
                        found = _find_hwnd_by_title()
                    
                    if found:
                        current_hwnd = found[0]
                        _apply_hide(current_hwnd)
                        log.debug("🛡️ Nueva ventana Chrome detectada y ocultada")
                    time.sleep(2)
                    continue
                
                # Si está minimizada, restaurar fuera de pantalla
                if user32.IsIconic(current_hwnd):
                    user32.ShowWindow(current_hwnd, SW_RESTORE)
                    user32.SetWindowPos(
                        current_hwnd, None, -2400, -2400, 0, 0,
                        SWP_NOSIZE | SWP_NOACTIVATE
                    )
                
                # Verificar que siga siendo TOOLWINDOW (no APPWINDOW)
                current_style = user32.GetWindowLongW(current_hwnd, GWL_EXSTYLE)
                if current_style & WS_EX_APPWINDOW:
                    current_style = (current_style & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW
                    user32.SetWindowLongW(current_hwnd, GWL_EXSTYLE, current_style)
                    user32.SetWindowPos(
                        current_hwnd, None, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED
                    )
            except Exception:
                break  # La ventana fue cerrada, terminar el hilo
            time.sleep(2)

    t = threading.Thread(target=_watchdog, daemon=True)
    t.start()
    log.info("🛡️ Watchdog anti-minimización activo")


def login_stake(driver, wait, email, password):
    """Navega al lobby y ejecuta el flujo de login."""
    log.info("🔗 Navegando a Stake...")
    driver.get(LOBBY_URL)
    time.sleep(random.uniform(3, 5))

    # LIMPIEZA EXPLICITA (Sugerido por usuario: reiniciar estado)
    try:
        log.info("🧹 Limpiando cookies y almacenamiento local...")
        driver.delete_all_cookies()
        driver.execute_script("window.localStorage.clear(); window.sessionStorage.clear();")
    except:
        pass

    try:
        log.info("🔑 Iniciando sesión...")
        # Click Login
        btn_login = wait.until(EC.element_to_be_clickable(
            (By.XPATH,
             "//a[contains(., 'Iniciar sesión')] | //button[contains(., 'Iniciar sesión')]")
        ))
        driver.execute_script("arguments[0].click();", btn_login)
        log.debug("   Botón 'Iniciar sesión' clickeado")

        # User
        user_field = wait.until(EC.presence_of_element_located((By.ID, "username")))
        driver.execute_script("arguments[0].focus(); arguments[0].click();", user_field)
        human_type(user_field, email)
        log.debug("   Email ingresado")

        # Pass
        pass_field = driver.find_element(By.ID, "password")
        driver.execute_script("arguments[0].focus(); arguments[0].click();", pass_field)
        human_type(pass_field, password)
        log.debug("   Password ingresado")

        # Submit
        submit_btn = driver.find_element(By.XPATH, "//button[@type='submit']")
        driver.execute_script("arguments[0].click();", submit_btn)

        log.info("✅ Login enviado. Esperando confirmación de inicio de sesión...")
        # Screenshot solo ante errores de login
        
        # Esperar hasta 60s a que aparezca la Billetera o Menú de usuario
        try:
            wait_login = WebDriverWait(driver, 60)
            wait_login.until(EC.presence_of_element_located(
                (By.XPATH, "//a[contains(@href, '/finance/wallet')] | //button[contains(., 'Billetera')] | //div[contains(@data-testid, 'user-dropdown')]")
            ))
            log.info("🎉 Login exitoso confirmado!")
            # Login OK - sin screenshot
            time.sleep(3) # Pequeña pausa de asentamiento
        except Exception as e:
            log.warning(f"⚠️ Tiempo de espera de login agotado (60s). Verificando si estamos dentro... Error: {e}")
            capture_screenshot(driver, "WARN_login_timeout")
            
    except Exception as e:
        log.warning(f"ℹ️ Login saltado/error: {e}")
        capture_screenshot(driver, "WARN_login_error")
