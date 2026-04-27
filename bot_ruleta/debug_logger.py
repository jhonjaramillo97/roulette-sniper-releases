"""
Sistema de Diagnóstico Forense para el Bot de Ruleta.
Centraliza logging, capturas de pantalla, diagnóstico de entorno y crash reports.
"""

import os
import sys
import time
import logging
import logging.handlers
import platform
import shutil
import zipfile
import traceback
import glob
from datetime import datetime

# ---------------------------------------------------------------------------
# Directorios Permanentes (Compatibles con PyInstaller)
# ---------------------------------------------------------------------------
if getattr(sys, 'frozen', False):
    # Si es el .exe, guarda en la carpeta data/logs junto al ejecutable
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    # En desarrollo, guarda en la carpeta data/logs en la raíz del proyecto
    _BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LOGS_DIR = os.path.join(_BASE_DIR, "data", "logs")
SCREENSHOTS_DIR = os.path.join(LOGS_DIR, "screenshots")
CRASH_REPORTS_DIR = os.path.join(LOGS_DIR, "crash_reports")

for _d in [LOGS_DIR, SCREENSHOTS_DIR, CRASH_REPORTS_DIR]:
    os.makedirs(_d, exist_ok=True)

# ---------------------------------------------------------------------------
# Logger Centralizado con Rotación
# ---------------------------------------------------------------------------
_LOG_FORMAT = "[%(asctime)s.%(msecs)03d] [%(levelname)-8s] [%(name)s] %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Logger raíz del bot
_root_logger = logging.getLogger("bot")
_root_logger.setLevel(logging.DEBUG)

# Evitar duplicar handlers si el módulo se importa más de una vez
if not _root_logger.handlers:
    # Handler 1: Archivo rotativo (10MB por archivo, máximo 5 archivos)
    _log_file = os.path.join(LOGS_DIR, f"bot_debug_{datetime.now().strftime('%Y-%m-%d')}.log")
    _file_handler = logging.handlers.RotatingFileHandler(
        _log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    _file_handler.setLevel(logging.DEBUG)
    _file_handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATE_FORMAT))
    _root_logger.addHandler(_file_handler)

    # Handler 2: Consola (solo INFO y superior para no saturar)
    # Usar un stream seguro para evitar UnicodeEncodeError en consolas Windows cp1252
    import io
    try:
        _safe_stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
        )
    except (AttributeError, TypeError):
        _safe_stdout = sys.stdout
    _console_handler = logging.StreamHandler(_safe_stdout)
    _console_handler.setLevel(logging.INFO)
    _console_handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATE_FORMAT))
    _root_logger.addHandler(_console_handler)


def get_logger(module_name: str) -> logging.Logger:
    """Obtiene un logger hijo con el nombre del módulo.
    Uso: log = get_logger('scanner')
    """
    return logging.getLogger(f"bot.{module_name}")


# ---------------------------------------------------------------------------
# Queue Handler para la GUI
# ---------------------------------------------------------------------------

class _GUIQueueHandler(logging.Handler):
    """Handler que envía logs a una Queue para que la GUI los lea."""
    def __init__(self, queue):
        super().__init__()
        self.queue = queue

    def emit(self, record):
        try:
            msg = self.format(record)
            self.queue.put(("log", record.levelname, msg))
        except Exception:
            pass


def attach_gui_queue(queue):
    """Conecta una Queue al logger para que la GUI reciba los logs.
    Llamar una sola vez al iniciar la GUI."""
    handler = _GUIQueueHandler(queue)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATE_FORMAT))
    _root_logger.addHandler(handler)


# ---------------------------------------------------------------------------
# Capturas de Pantalla Automáticas
# ---------------------------------------------------------------------------
_screenshot_counter = 0
_DIAGNOSTICS_ENABLED = False

def set_diagnostics(enabled: bool):
    """Activa o desactiva las capturas de pantalla de diagnóstico rutinarias."""
    global _DIAGNOSTICS_ENABLED
    _DIAGNOSTICS_ENABLED = enabled

def capture_screenshot(driver, label: str, save_html: bool = True) -> str | None:
    """Toma un screenshot del navegador y opcionalmente guarda el HTML source.

    Args:
        driver: Instancia de WebDriver (puede ser None).
        label: Etiqueta descriptiva (ej: 'login_ok', 'ERROR_timeout').
        save_html: Si True, también guarda el page_source como HTML.

    Returns:
        Ruta absoluta del screenshot guardado, o None si falló.
    """
    global _screenshot_counter
    if driver is None:
        return None

    # Si los diagnósticos están desactivados, solo capturar errores graves
    global _DIAGNOSTICS_ENABLED
    if not _DIAGNOSTICS_ENABLED:
        if "CRITICAL" not in label.upper() and "ERROR" not in label.upper():
            return None

    log = get_logger("screenshot")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    _screenshot_counter += 1
    counter_str = f"{_screenshot_counter:03d}"

    # Sanitizar label para nombre de archivo
    safe_label = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in label)
    base_name = f"{counter_str}_{timestamp}_{safe_label}"

    png_path = os.path.join(SCREENSHOTS_DIR, f"{base_name}.png")
    html_path = os.path.join(SCREENSHOTS_DIR, f"{base_name}.html")

    try:
        driver.save_screenshot(png_path)
        log.info(f"📸 Screenshot guardado: {png_path}")

        if save_html:
            try:
                # Guardar HTML del contexto actual (puede ser iframe)
                page_src = driver.page_source
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(page_src)
                log.debug(f"📄 HTML source guardado: {html_path}")
            except Exception as e:
                log.warning(f"No se pudo guardar HTML source: {e}")

        return png_path
    except Exception as e:
        log.error(f"Error tomando screenshot '{label}': {e}")
        return None


def _cleanup_old_screenshots(max_files: int = 50):
    """Mantiene solo los últimos N screenshots para no llenar el disco."""
    try:
        files = sorted(
            glob.glob(os.path.join(SCREENSHOTS_DIR, "*.png")),
            key=os.path.getmtime,
        )
        if len(files) > max_files:
            for old_file in files[: len(files) - max_files]:
                os.remove(old_file)
                # También eliminar el HTML acompañante si existe
                html_companion = old_file.replace(".png", ".html")
                if os.path.exists(html_companion):
                    os.remove(html_companion)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Diagnóstico de Entorno
# ---------------------------------------------------------------------------

def run_diagnostics() -> str:
    """Ejecuta un diagnóstico completo del entorno y retorna el reporte como string.
    También lo guarda en logs/diagnostico_inicio.txt.
    """
    log = get_logger("diagnostics")
    lines = []

    def _add(key, value):
        lines.append(f"  {key:<22} {value}")

    lines.append("=" * 60)
    lines.append("  🔍 DIAGNÓSTICO DE ENTORNO")
    lines.append(f"  Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 60)

    # --- OS ---
    try:
        os_info = f"{platform.system()} {platform.release()} ({platform.version()})"
    except Exception:
        os_info = "No disponible"
    _add("OS:", os_info)

    # --- Python ---
    _add("Python:", f"{sys.version.split()[0]} ({sys.executable})")

    # --- Chrome ---
    chrome_version = "No detectado"
    try:
        if platform.system() == "Windows":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
            version, _ = winreg.QueryValueEx(key, "version")
            chrome_version = version
        else:
            import subprocess
            result = subprocess.run(["google-chrome", "--version"], capture_output=True, text=True, timeout=5)
            chrome_version = result.stdout.strip()
    except Exception as e:
        chrome_version = f"Error: {e}"
    _add("Chrome:", chrome_version)

    # --- RAM ---
    try:
        import psutil
        mem = psutil.virtual_memory()
        _add("RAM Total:", f"{mem.total / (1024**3):.1f} GB")
        _add("RAM Disponible:", f"{mem.available / (1024**3):.1f} GB ({mem.percent}% en uso)")
    except ImportError:
        _add("RAM:", "psutil no instalado (instalar para más info)")
    except Exception as e:
        _add("RAM:", f"Error: {e}")

    # --- Disco ---
    try:
        disk = shutil.disk_usage(_BASE_DIR)
        _add("Disco Libre:", f"{disk.free / (1024**3):.1f} GB de {disk.total / (1024**3):.1f} GB")
    except Exception as e:
        _add("Disco:", f"Error: {e}")

    # --- .env ---
    env_path = os.path.join(os.path.dirname(_BASE_DIR), ".env")
    if os.path.exists(env_path):
        try:
            from bot_ruleta.config import load_credentials
            email, password, tg_token, tg_chat_id, threshold, headless = load_credentials()
            email_masked = email[:3] + "***" + email[email.index("@"):] if "@" in email else "???"
            _add(".env:", f"✅ Encontrado")
            _add("  Email:", email_masked)
            _add("  Password:", "✅ Presente" if password else "❌ VACÍO")
            _add("  TG Token:", "✅ Presente" if tg_token else "❌ VACÍO")
            _add("  TG Chat ID:", "✅ Presente" if tg_chat_id else "❌ VACÍO")
            _add("  Threshold:", str(threshold))
            _add("  Headless:", str(headless))
        except Exception as e:
            _add(".env:", f"⚠️ Error leyendo: {e}")
    else:
        _add(".env:", "❌ NO ENCONTRADO")

    # --- Permisos de escritura ---
    for d_name, d_path in [("data/", os.path.join(_BASE_DIR, "data")), ("logs/", LOGS_DIR)]:
        try:
            test_file = os.path.join(d_path, ".write_test")
            os.makedirs(d_path, exist_ok=True)
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
            _add(f"Permisos {d_name}:", "✅ Escritura OK")
        except Exception as e:
            _add(f"Permisos {d_name}:", f"❌ SIN ESCRITURA: {e}")

    # --- Red ---
    try:
        import urllib.request
        start_t = time.time()
        urllib.request.urlopen("https://stake.com.co", timeout=10)
        latency = (time.time() - start_t) * 1000
        _add("Red (stake.com.co):", f"✅ Accesible ({latency:.0f}ms)")
    except Exception as e:
        _add("Red (stake.com.co):", f"❌ NO ACCESIBLE: {e}")

    # --- undetected_chromedriver ---
    try:
        import undetected_chromedriver as uc
        _add("UC Driver:", f"✅ v{uc.__version__}" if hasattr(uc, "__version__") else "✅ Instalado")
    except ImportError:
        _add("UC Driver:", "❌ NO INSTALADO")

    # --- selenium ---
    try:
        import selenium
        _add("Selenium:", f"✅ v{selenium.__version__}")
    except ImportError:
        _add("Selenium:", "❌ NO INSTALADO")

    lines.append("=" * 60)

    report = "\n".join(lines)

    # Guardar en archivo
    diag_path = os.path.join(LOGS_DIR, "diagnostico_inicio.txt")
    try:
        with open(diag_path, "w", encoding="utf-8") as f:
            f.write(report)
    except Exception:
        pass

    # Log cada línea
    for line in lines:
        log.info(line)

    return report


# ---------------------------------------------------------------------------
# Crash Report con envío por Telegram
# ---------------------------------------------------------------------------

def generate_crash_report(driver=None, error: Exception = None) -> str | None:
    """Genera un ZIP con toda la información de diagnóstico y lo envía por Telegram.

    Returns:
        Ruta del ZIP generado, o None si falló.
    """
    log = get_logger("crash_report")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    zip_name = f"debug_report_{timestamp}.zip"
    zip_path = os.path.join(CRASH_REPORTS_DIR, zip_name)

    log.critical(f"🚨 Generando crash report: {zip_name}")

    try:
        # Tomar screenshot final si hay driver
        if driver:
            try:
                capture_screenshot(driver, f"CRITICAL_crash_{timestamp}", save_html=True)
            except Exception:
                pass

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # 1. Diagnóstico de inicio
            diag_file = os.path.join(LOGS_DIR, "diagnostico_inicio.txt")
            if os.path.exists(diag_file):
                zf.write(diag_file, "diagnostico_inicio.txt")

            # 2. Logs del día (últimas 500 líneas del más reciente)
            log_files = sorted(glob.glob(os.path.join(LOGS_DIR, "bot_debug_*.log")), key=os.path.getmtime)
            if log_files:
                latest_log = log_files[-1]
                try:
                    with open(latest_log, "r", encoding="utf-8", errors="ignore") as f:
                        all_lines = f.readlines()
                        last_500 = all_lines[-500:] if len(all_lines) > 500 else all_lines
                    zf.writestr("bot_debug_recent.log", "".join(last_500))
                except Exception:
                    pass

            # 3. Últimas 10 screenshots
            screenshots = sorted(
                glob.glob(os.path.join(SCREENSHOTS_DIR, "*.png")),
                key=os.path.getmtime,
            )
            for ss in screenshots[-10:]:
                zf.write(ss, f"screenshots/{os.path.basename(ss)}")
                # HTML acompañante
                html_comp = ss.replace(".png", ".html")
                if os.path.exists(html_comp):
                    zf.write(html_comp, f"screenshots/{os.path.basename(html_comp)}")

            # 4. .env sanitizado (sin contraseñas)
            env_path = os.path.join(os.path.dirname(_BASE_DIR), ".env")
            if os.path.exists(env_path):
                try:
                    with open(env_path, "r", encoding="utf-8") as f:
                        env_lines = f.readlines()
                    sanitized = []
                    for line in env_lines:
                        stripped = line.strip()
                        if "=" in stripped and not stripped.startswith("#"):
                            key = stripped.split("=", 1)[0].strip()
                            if "PASSWORD" in key.upper() or "TOKEN" in key.upper():
                                sanitized.append(f"{key}=********\n")
                            else:
                                sanitized.append(line)
                        else:
                            sanitized.append(line)
                    zf.writestr("env_sanitized.txt", "".join(sanitized))
                except Exception:
                    pass

            # 5. Traceback del error
            if error:
                tb_str = "".join(traceback.format_exception(type(error), error, error.__traceback__))
                zf.writestr("traceback.txt", tb_str)

            # 6. Page source si hay driver
            if driver:
                try:
                    zf.writestr("page_source_error.html", driver.page_source)
                except Exception:
                    pass

        log.critical(f"📦 Crash report generado: {zip_path}")

        # Enviar por Telegram
        _send_crash_report_telegram(zip_path, error)

        # Limpiar crash reports viejos (mantener últimos 10)
        _cleanup_old_crash_reports()

        return zip_path

    except Exception as e:
        log.error(f"Error generando crash report: {e}")
        return None


def _send_crash_report_telegram(zip_path: str, error: Exception = None):
    """Envía el crash report como documento por Telegram."""
    log = get_logger("crash_report")
    try:
        from bot_ruleta.config import load_credentials
        _, _, token, chat_id, _, _ = load_credentials()

        if not token or not chat_id:
            log.warning("No hay credenciales de Telegram configuradas. Crash report no enviado.")
            return

        import requests

        # Mensaje de texto con resumen del error
        error_summary = str(error)[:200] if error else "Error desconocido"
        caption = (
            f"🚨 *CRASH REPORT*\n\n"
            f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"❌ {error_summary}\n\n"
            f"📎 Revisa el ZIP adjunto para diagnóstico completo."
        )

        # Enviar documento
        url = f"https://api.telegram.org/bot{token}/sendDocument"
        with open(zip_path, "rb") as f:
            files = {"document": (os.path.basename(zip_path), f)}
            data = {"chat_id": chat_id, "caption": caption, "parse_mode": "Markdown"}
            response = requests.post(url, files=files, data=data, timeout=30)

        if response.status_code == 200:
            log.info("✅ Crash report enviado por Telegram")
        else:
            log.warning(f"⚠️ Telegram respondió {response.status_code}: {response.text[:200]}")

    except Exception as e:
        log.error(f"Error enviando crash report por Telegram: {e}")


def _cleanup_old_crash_reports(max_reports: int = 10):
    """Mantiene solo los últimos N crash reports."""
    try:
        zips = sorted(
            glob.glob(os.path.join(CRASH_REPORTS_DIR, "debug_report_*.zip")),
            key=os.path.getmtime,
        )
        if len(zips) > max_reports:
            for old_zip in zips[: len(zips) - max_reports]:
                os.remove(old_zip)
    except Exception:
        pass
