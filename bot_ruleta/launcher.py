import subprocess
import threading
import re
import os
import sys
import time

# Permitir cargar módulos del proyecto compartidos
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot_ruleta.config import load_credentials
from bot_ruleta.logic import send_telegram_msg
from bot_ruleta.debug_logger import run_diagnostics, get_logger

log = get_logger("launcher")

# Forzar codificación UTF-8 para la salida de la consola (Evitar crasheos de emojis en Windows)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import sys

if getattr(sys, 'frozen', False):
    DATA_DIR = os.path.join(os.path.dirname(sys.executable), "data")
else:
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)
    
TUNNEL_FILE = os.path.join(DATA_DIR, "tunnel.txt")

# Variables globales para la UI de consola
public_url = "Generando..."
last_log_line = "Iniciando sistema..."
tables_found_status = "Mesas: Esperando mapeo (Anti-AFK)..."
lock = threading.Lock()

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def render_ui():
    """Dibuja la consola limpia y minimalista"""
    global public_url, last_log_line, tables_found_status
    
    with lock:
        clear_screen()
        print("=========================================================")
        print("              🎰 ROULETTE SNIPER BOT 🎰")
        print("=========================================================")
        print(f" 🏠 Dashboard Local: http://127.0.0.1:5050")
        print(f" 🌍 Acceso Remoto:   {public_url}")
        print("=========================================================")
        print(f" 🗂️  {tables_found_status}")
        print("=========================================================")
        print("\n ⚡ [ ESTADO ACTUAL DEL BOT ] ⚡\n")
        print(f" > {last_log_line}")
        print("\n=========================================================")
        print(" (Presiona Ctrl+C para apagar todo)")

def _start_cloudflared():
    """Inicia un proceso cloudflared y retorna el proceso."""
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    return subprocess.Popen(
        ["cloudflared", "tunnel", "--url", "http://localhost:5055"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        creationflags=creationflags
    )

def _update_tunnel_url(found_url):
    """Actualiza el URL del túnel en todas partes: variable global, archivo, Telegram."""
    global public_url
    
    with lock:
        old_url = public_url
        public_url = found_url
        
        # Guardar link para que el dashboard web lo lea
        try:
            with open(TUNNEL_FILE, "w") as f:
                f.write(found_url)
        except Exception:
            pass
        
        # Enviar notificación por Telegram (solo si el URL cambió)
        if found_url != old_url:
            try:
                _, _, token, chat_id, _, _ = load_credentials()
                if token and chat_id and token.strip() != "":
                    if old_url and "trycloudflare" in str(old_url):
                        tg_msg = (
                            f"🔄 *Enlace del Dashboard Actualizado*\n\n"
                            f"El túnel se renovó automáticamente. Nuevo enlace:\n\n{found_url}"
                        )
                    else:
                        tg_msg = (
                            f"🌐 *Nuevo Enlace del Dashboard*\n\n"
                            f"El bot acaba de encenderse. Puedes acceder al escáner en tiempo real desde cualquier lugar aquí:\n\n{found_url}"
                        )
                    send_telegram_msg(token, chat_id, tg_msg)
            except Exception:
                pass

    render_ui()

def cloudflared_watchdog():
    """Hilo permanente que mantiene cloudflared vivo y captura URLs nuevos.
    Si cloudflared muere, lo reinicia automáticamente.
    Si cloudflare rota el túnel (nuevo URL), lo detecta y actualiza todo."""
    global public_url
    url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
    
    while True:
        try:
            log.info("🌐 Iniciando túnel Cloudflare...")
            cf_proc = _start_cloudflared()
            
            # Leer stderr continuamente (NO hacer break al primer URL)
            for line in iter(cf_proc.stderr.readline, b''):
                line_str = line.decode('utf-8', errors='ignore').strip()
                match = url_pattern.search(line_str)
                if match:
                    found_url = match.group(0)
                    _update_tunnel_url(found_url)
                    log.info(f"🌐 Túnel activo: {found_url}")
            
            # Si llegamos aquí, cloudflared cerró su stderr → el proceso murió
            cf_proc.wait()
            log.warning("⚠️ Cloudflared se cayó. Reiniciando en 10 segundos...")
            with lock:
                public_url = "⏳ Reconectando túnel..."
            render_ui()
            time.sleep(10)
            
        except FileNotFoundError:
            log.error("❌ cloudflared no está instalado")
            with lock:
                public_url = "ERROR: No está instalado cloudflared"
            render_ui()
            break  # No tiene sentido reintentar si no está instalado
        except Exception as e:
            log.warning(f"⚠️ Error en túnel Cloudflare: {e}. Reintentando en 10s...")
            time.sleep(10)
            
def track_bot(process):
    """Lee la salida del bot y actualiza la consola minimalista"""
    global last_log_line, tables_found_status
    for line in iter(process.stdout.readline, b''):
        # Ya no eliminamos los emojis, solo limpiamos los saltos de línea
        cleaned_line = line.decode('utf-8', errors='ignore').replace('\r', '').replace('\n', '').strip()
        
        if cleaned_line: # No mostrar lineas vacias
            with lock:
                if "tiles totales" in cleaned_line or "Mesas mapeadas:" in cleaned_line:
                    tables_found_status = cleaned_line

                last_log_line = cleaned_line[-150:] # Mostrar un poco más de texto si hay emojis largos
            render_ui()

def cleanup():
    # Eliminar archivo tunnel.txt si queda
    if os.path.exists(TUNNEL_FILE):
        try: os.remove(TUNNEL_FILE)
        except: pass
        
    # Eliminar ejecutables viejos si venimos de una actualización
    import glob
    exe_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    for old_file in glob.glob(os.path.join(exe_dir, "*.old")):
        try: os.remove(old_file)
        except: pass

if __name__ == "__main__":
    # Limpiar archivo viejo
    cleanup()
    
    # =====================================================
    # PASO 0: Diagnóstico de Entorno (ANTES de lanzar nada)
    # =====================================================
    print("=" * 60)
    print("  🔍 EJECUTANDO DIAGNÓSTICO DE ENTORNO...")
    print("=" * 60)
    diag_report = run_diagnostics()
    print(diag_report)
    print("\n  ✅ Diagnóstico completado. Guardado en logs/diagnostico_inicio.txt")
    print("=" * 60)
    time.sleep(3)  # Dar tiempo a leer el diagnóstico
    
    # 1. Iniciar Dashboard
    base_dir = os.path.dirname(os.path.abspath(__file__))
    app_py_path = os.path.join(base_dir, "dashboard", "app.py")
    dashboard_proc = subprocess.Popen([sys.executable, app_py_path], 
                                      stdout=subprocess.DEVNULL, 
                                      stderr=subprocess.DEVNULL)
    
    # 2. Iniciar Cloudflared (con watchdog que auto-reinicia)
    threading.Thread(target=cloudflared_watchdog, daemon=True).start()
    
    render_ui()
    time.sleep(2) # Esperar que levante web
    
    # 3. Iniciar Bot Principal con flag -u (unbuffered) y env UTF-8
    run_py_path = os.path.join(base_dir, "run.py")
    
    bot_env = os.environ.copy()
    bot_env["PYTHONIOENCODING"] = "utf-8"
    
    bot_proc = subprocess.Popen([sys.executable, "-u", run_py_path],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                env=bot_env)
    
    # Hilo para leer bot
    threading.Thread(target=track_bot, args=(bot_proc,), daemon=True).start()
    
    try:
        # Mantener vivo el programa principal mientras el bot esté corriendo
        bot_proc.wait()
    except KeyboardInterrupt:
        with lock:
            last_log_line = "APAGANDO SISTEMA..."
        render_ui()
    finally:
        # Cerrar todo ordenadamente
        try: bot_proc.terminate()
        except: pass
        try: dashboard_proc.terminate()
        except: pass
        # cloudflared se cierra solo porque el hilo watchdog es daemon
        cleanup()
