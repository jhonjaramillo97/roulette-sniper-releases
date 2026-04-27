import urllib.request
import threading
import os
import sys
import subprocess
import logging

log = logging.getLogger("bot")

CURRENT_VERSION = "2.0.6"
# Usamos la API de GitHub en lugar de raw.githubusercontent.com para mayor fiabilidad
VERSION_URL = "https://api.github.com/repos/jhonjaramillo97/roulette-sniper-releases/contents/version.txt"
DOWNLOAD_URL = "https://github.com/jhonjaramillo97/roulette-sniper-releases/releases/latest/download/RouletteSniperPro.exe"

def check_for_updates(callback):
    """
    Checks GitHub for updates in a background thread.
    Calls callback(new_version) if an update is found, otherwise callback(None).
    """
    def _check():
        try:
            import json
            import base64
            import time
            
            headers = {
                'Cache-Control': 'no-cache',
                'User-Agent': 'RouletteSniper-Updater',
                'Accept': 'application/vnd.github+json'
            }
            
            # La API de GitHub es más estable que el enlace raw en algunas redes
            req = urllib.request.Request(f"{VERSION_URL}?t={int(time.time())}", headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
                # El contenido viene en base64
                remote_version = base64.b64decode(data['content']).decode('utf-8').strip()
            
            log.info(f"Check Update: Local={CURRENT_VERSION}, Remote={remote_version}")
            
            if remote_version and remote_version != CURRENT_VERSION:
                # Extraer solo números de las partes (ej: 'v1' -> 1)
                import re
                def get_parts(v):
                    return [int(re.sub(r'\D', '', p)) for p in v.split('.') if re.sub(r'\D', '', p)]
                
                remote_parts = get_parts(remote_version)
                local_parts = get_parts(CURRENT_VERSION)
                
                if remote_parts > local_parts:
                    log.info(f"¡Nueva versión encontrada!: v{remote_version}")
                    callback(remote_version)
                    return
            
            callback(None)
        except Exception as e:
            log.warning(f"Error al verificar actualizaciones: {e}")
            callback(None)
            
    threading.Thread(target=_check, daemon=True).start()

def perform_update(new_version, progress_callback, completion_callback):
    """
    Downloads the new executable and spawns a bat file to replace the current one.
    """
    def _update():
        try:
            if not getattr(sys, 'frozen', False):
                log.warning("Ejecutando desde código fuente. La actualización automática solo funciona en el ejecutable compilado (.exe).")
                completion_callback(False, "Solo funciona en el .exe")
                return

            current_exe = sys.executable
            update_dir = os.path.dirname(current_exe)
            update_exe_final = os.path.join(update_dir, "RouletteSniperPro.update")
            
            log.info(f"Descargando versión {new_version}...")
            
            # Download with progress
            with urllib.request.urlopen(DOWNLOAD_URL) as response:
                total_size = int(response.getheader('Content-Length').strip())
                downloaded = 0
                chunk_size = 8192
                
                with open(update_exe_final, 'wb') as f:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = min(100, int((downloaded / total_size) * 100))
                            progress_callback(percent)
                            
            old_exe = os.path.join(update_dir, "RouletteSniperPro.old")
            
            bat_content = f"""@echo off
setlocal
:: Intentar cerrar cualquier proceso remanente
taskkill /F /IM "RouletteSniperPro.exe" >nul 2>&1
timeout /t 1 /nobreak >nul

:wait_exit
if exist "{old_exe}" del /f /q "{old_exe}" >nul 2>&1
ren "{current_exe}" "RouletteSniperPro.old"
if errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait_exit
)

ren "{update_exe_final}" "RouletteSniperPro.exe"
start "" "RouletteSniperPro.exe"
del "%~f0"
"""
            
            bat_path = os.path.join(update_dir, "restart_update.bat")
            with open(bat_path, "w", encoding="utf-8") as f:
                f.write(bat_content)
            
            log.info("Ejecutando restart script...")
            completion_callback(True, "Actualización descargada. Reiniciando...")
            
            subprocess.Popen(["cmd", "/c", bat_path], creationflags=subprocess.CREATE_NO_WINDOW)
            os._exit(0)
            
        except Exception as e:
            log.error(f"Error durante la actualización: {e}")
            completion_callback(False, str(e))
            
    threading.Thread(target=_update, daemon=True).start()
