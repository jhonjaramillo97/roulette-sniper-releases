import urllib.request
import threading
import os
import sys
import subprocess
import glob
import logging

log = logging.getLogger("bot")

CURRENT_VERSION = "2.0.18"
# Usamos la API de GitHub en lugar de raw.githubusercontent.com para mayor fiabilidad
VERSION_URL = "https://api.github.com/repos/jhonjaramillo97/roulette-sniper-releases/contents/version.txt"

# La URL de descarga ahora apunta al asset versionado (latest release)
def _get_download_url(version):
    """Genera la URL de descarga para una versión específica."""
    return f"https://github.com/jhonjaramillo97/roulette-sniper-releases/releases/download/v{version}/RouletteSniperPro_v{version}.exe"

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

def _cleanup_old_versions(update_dir, keep_exe=None):
    """Limpia archivos de actualizaciones anteriores (.old, .update, versiones viejas)."""
    patterns = [
        os.path.join(update_dir, "*.old"),
        os.path.join(update_dir, "*.update"),
        os.path.join(update_dir, "restart_update.bat"),
    ]
    
    for pattern in patterns:
        for f in glob.glob(pattern):
            try:
                os.remove(f)
                log.debug(f"Limpieza: eliminado {os.path.basename(f)}")
            except Exception:
                pass
    
    # Limpiar versiones viejas versionadas (RouletteSniperPro_v*.exe) excepto la que vamos a usar
    for f in glob.glob(os.path.join(update_dir, "RouletteSniperPro_v*.exe")):
        if keep_exe and os.path.abspath(f) == os.path.abspath(keep_exe):
            continue
        try:
            os.remove(f)
            log.debug(f"Limpieza: eliminado versión vieja {os.path.basename(f)}")
        except Exception:
            pass

def perform_update(new_version, progress_callback, completion_callback):
    """
    Downloads the new versioned executable and spawns a bat file to replace the current one.
    The new exe is named RouletteSniperPro_v{version}.exe for clear identification.
    """
    def _update():
        try:
            if not getattr(sys, 'frozen', False):
                log.warning("Ejecutando desde código fuente. La actualización automática solo funciona en el ejecutable compilado (.exe).")
                completion_callback(False, "Solo funciona en el .exe")
                return

            current_exe = sys.executable
            current_exe_name = os.path.basename(current_exe)
            update_dir = os.path.dirname(current_exe)
            
            # Nombre versionado del nuevo ejecutable
            new_exe_name = f"RouletteSniperPro_v{new_version}.exe"
            new_exe_path = os.path.join(update_dir, new_exe_name)
            
            # 1. Limpieza previa de archivos de actualizaciones anteriores
            log.info("🧹 Limpiando archivos de actualizaciones anteriores...")
            _cleanup_old_versions(update_dir, keep_exe=current_exe)
            
            # 2. Descargar nueva versión con nombre versionado
            download_url = _get_download_url(new_version)
            log.info(f"📥 Descargando v{new_version} desde {download_url}...")
            
            with urllib.request.urlopen(download_url) as response:
                total_size = int(response.getheader('Content-Length').strip())
                downloaded = 0
                chunk_size = 8192
                
                with open(new_exe_path, 'wb') as f:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = min(100, int((downloaded / total_size) * 100))
                            progress_callback(percent)
            
            # Verificar que se descargó correctamente
            if not os.path.exists(new_exe_path) or os.path.getsize(new_exe_path) < 1000000:
                raise Exception(f"Archivo descargado inválido ({os.path.getsize(new_exe_path)} bytes)")
            
            log.info(f"✅ Descarga completa: {new_exe_name} ({os.path.getsize(new_exe_path) / 1024 / 1024:.1f} MB)")
            
            # 3. Generar script .bat robusto con reintentos limitados
            old_exe_path = os.path.join(update_dir, f"{current_exe_name}.old")
            
            bat_content = f"""@echo off
setlocal
echo ============================================
echo   Actualizando Roulette Sniper Pro v{new_version}
echo ============================================
echo.

:: Paso 1: Cerrar procesos del bot (con árbol completo)
echo Cerrando procesos anteriores...
taskkill /F /T /IM "{current_exe_name}" >nul 2>&1
timeout /t 2 /nobreak >nul

:: Paso 2: Renombrar el exe actual a .old (con reintentos limitados)
set RETRIES=0
:retry_rename
if %RETRIES% GEQ 10 (
    echo ERROR: No se pudo renombrar el exe actual tras 10 intentos.
    echo El archivo puede estar en uso por otro proceso.
    pause
    exit /b 1
)

if exist "{old_exe_path}" del /f /q "{old_exe_path}" >nul 2>&1
ren "{current_exe}" "{current_exe_name}.old" >nul 2>&1
if errorlevel 1 (
    set /a RETRIES+=1
    echo Reintentando renombrar... (intento %RETRIES%/10)
    timeout /t 2 /nobreak >nul
    goto retry_rename
)

echo Exe anterior renombrado correctamente.

:: Paso 3: Copiar el nuevo exe versionado con el nombre original
copy /y "{new_exe_path}" "{current_exe}" >nul 2>&1
if errorlevel 1 (
    echo ERROR: No se pudo copiar la nueva version.
    :: Restaurar el exe original
    ren "{old_exe_path}" "{current_exe_name}" >nul 2>&1
    pause
    exit /b 1
)

echo Nueva version instalada correctamente.

:: Paso 4: Limpiar archivos temporales
del /f /q "{old_exe_path}" >nul 2>&1
del /f /q "{new_exe_path}" >nul 2>&1

:: Paso 5: Ejecutar la nueva version
echo Iniciando Roulette Sniper Pro v{new_version}...
start "" "{current_exe}"

:: Paso 6: Auto-eliminar este script
(goto) 2>nul & del "%~f0"
"""
            
            import tempfile
            bat_path = os.path.join(tempfile.gettempdir(), "restart_update.bat")
            with open(bat_path, "w", encoding="utf-8") as f:
                f.write(bat_content)
            
            log.info("🔄 Ejecutando script de actualización...")
            completion_callback(True, "Actualización descargada. Reiniciando...")
            
            subprocess.Popen(
                ["cmd", "/c", bat_path],
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            os._exit(0)
            
        except Exception as e:
            log.error(f"Error durante la actualización: {e}")
            completion_callback(False, str(e))
            
    threading.Thread(target=_update, daemon=True).start()
