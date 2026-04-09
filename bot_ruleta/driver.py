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


def get_chrome_major_version():
    """Detecta la versión principal de Chrome instalada para evitar mismatch."""
    import platform
    try:
        if platform.system() == "Windows":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
            version, _ = winreg.QueryValueEx(key, "version")
            return int(version.split('.')[0])
    except Exception:
        pass
    return None

def setup_driver(headless=True):
    """Configura y retorna (driver, wait)."""
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
        print("👻 Iniciando Driver en modo Headless (oculto)...")
        # ---------------------------------------------------------------
        # NOTA: Pragmatic Play detecta --headless=new y bloquea la carga
        # del lobby indefinidamente. Usamos Chrome real pero con la ventana
        # fuera de la pantalla visible. Para el servidor es Chrome normal,
        # para el usuario es invisible.
        # ---------------------------------------------------------------
        options.add_argument("--window-position=-2400,-2400")
    else:
        print("🖥️ Iniciando Driver en modo Visible (con ventana)...")
        
    options.add_argument("--window-size=1920,1080") 
    options.add_argument("--no-first-run")
    options.add_argument("--no-service-autorun")
    options.add_argument("--password-store=basic")

    print("🚀 Iniciando Bot de Ruleta (Modo Lobby)...")
    
    # Obtener versión dinámica para que no falle al actualizar Chrome
    chrome_version = get_chrome_major_version()
    if chrome_version:
        driver = uc.Chrome(options=options, version_main=chrome_version)
    else:
        driver = uc.Chrome(options=options)

    if headless:
        _hide_chrome_window(driver)
        
    wait = WebDriverWait(driver, 30)
    return driver, wait


# ---------------------------------------------------------------------------
# Ocultar ventana de Chrome de la barra de tareas + protección anti-minimize
# ---------------------------------------------------------------------------

def _hide_chrome_window(driver):
    """Oculta la ventana de Chrome de la barra de tareas y lanza un hilo
    vigilante que la restaura si alguien la minimiza accidentalmente."""
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

    time.sleep(2)  # Esperar a que Chrome cree su ventana

    # Buscar el HWND de la ventana principal de Chrome
    hwnd = None
    try:
        results = []
        
        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        def enum_windows_callback(h, _lparam):
            if user32.IsWindowVisible(h):
                length = user32.GetWindowTextLengthW(h)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(h, buf, length + 1)
                    title = buf.value
                    if title and ("Chrome" in title or "Stake" in title or "stake" in title):
                        results.append(h)
            return True

        user32.EnumWindows(enum_windows_callback, 0)
        
        if results:
            hwnd = results[0]
    except Exception as e:
        print(f"   ⚠️ No se pudo encontrar ventana Chrome: {e}")

    if not hwnd:
        print("   ⚠️ HWND no encontrado, Chrome seguirá visible en taskbar")
        return

    try:
        # 1. Ocultar temporalmente la ventana
        user32.ShowWindow(hwnd, SW_HIDE)

        # 2. Quitar estilo WS_EX_APPWINDOW y añadir WS_EX_TOOLWINDOW
        #    Esto la elimina de la barra de tareas y de Alt+Tab
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style = (style & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)

        # 3. Mover fuera de pantalla y mostrar sin activar
        user32.SetWindowPos(
            hwnd, None, -2400, -2400, 0, 0,
            SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED
        )
        user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)

        print("   🛡️ Chrome oculto de la barra de tareas")
    except Exception as e:
        print(f"   ⚠️ Error ocultando ventana: {e}")
        return

    # 4. Hilo vigilante: si alguien minimiza Chrome, restaurar inmediatamente
    def _watchdog():
        while True:
            try:
                # IsIconic = True si la ventana está minimizada
                if user32.IsIconic(hwnd):
                    user32.ShowWindow(hwnd, SW_RESTORE)
                    user32.SetWindowPos(
                        hwnd, None, -2400, -2400, 0, 0,
                        SWP_NOSIZE | SWP_NOACTIVATE
                    )
                # Verificar que siga siendo TOOLWINDOW
                current_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                if current_style & WS_EX_APPWINDOW:
                    current_style = (current_style & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW
                    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, current_style)
            except:
                break  # La ventana fue cerrada, terminar el hilo
            time.sleep(2)

    t = threading.Thread(target=_watchdog, daemon=True)
    t.start()
    print("   🛡️ Watchdog anti-minimización activo")


def login_stake(driver, wait, email, password):
    """Navega al lobby y ejecuta el flujo de login."""
    print("🔗 Navegando a Stake...")
    driver.get(LOBBY_URL)
    time.sleep(random.uniform(3, 5))

    # LIMPIEZA EXPLICITA (Sugerido por usuario: reiniciar estado)
    try:
        print("🧹 Limpiando cookies y almacenamiento local...")
        driver.delete_all_cookies()
        driver.execute_script("window.localStorage.clear(); window.sessionStorage.clear();")
    except:
        pass

    try:
        print("🔑 Iniciando sesión...")
        # Click Login
        btn_login = wait.until(EC.element_to_be_clickable(
            (By.XPATH,
             "//a[contains(., 'Iniciar sesión')] | //button[contains(., 'Iniciar sesión')]")
        ))
        driver.execute_script("arguments[0].click();", btn_login)

        # User
        user_field = wait.until(EC.presence_of_element_located((By.ID, "username")))
        driver.execute_script("arguments[0].focus(); arguments[0].click();", user_field)
        human_type(user_field, email)

        # Pass
        pass_field = driver.find_element(By.ID, "password")
        driver.execute_script("arguments[0].focus(); arguments[0].click();", pass_field)
        human_type(pass_field, password)

        # Submit
        submit_btn = driver.find_element(By.XPATH, "//button[@type='submit']")
        driver.execute_script("arguments[0].click();", submit_btn)

        print("✅ Login enviado. Esperando confirmación de inicio de sesión...")
        
        # Esperar hasta 60s a que aparezca la Billetera o Menú de usuario
        try:
            wait_login = WebDriverWait(driver, 60)
            wait_login.until(EC.presence_of_element_located(
                (By.XPATH, "//a[contains(@href, '/finance/wallet')] | //button[contains(., 'Billetera')] | //div[contains(@data-testid, 'user-dropdown')]")
            ))
            print("Mw🎉 Login exitoso confirmado!")
            time.sleep(3) # Pequeña pausa de asentamiento
        except:
            print("⚠️ Tiempo de espera de login agotado. Verificando si estamos dentro...")
            
    except Exception as e:
        print(f"ℹ️ (Login saltado/error): {e}")
