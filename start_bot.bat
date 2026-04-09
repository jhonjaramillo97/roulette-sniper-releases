@echo off
title ROULETTE SNIPER BOT
cls
echo ===========================================
echo    ROULETTE SNIPER - BOT LAUNCHER
echo ===========================================
echo.

cd /d "%~dp0"
echo.

:: Verificar entorno virtual
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] No se encontro el entorno virtual ^(venv^).
    echo Por favor ejecuta primero "install.bat" para instalar las dependencias.
    pause
    exit /b 1
)

:: Verificar si el venv funciona (prevenir error 103 al cambiar de PC)
venv\Scripts\python.exe --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] El entorno virtual existente esta corrupto ^(probable copia de otro PC^).
    echo Por favor ejecuta "install.bat" para repararlo automaticamente.
    pause
    exit /b 1
)

set "PYTHON_EXE=venv\Scripts\python.exe"
echo [OK] Entorno virtual detectado y operativo.
echo.

:: Verificar run.py
if exist "bot_ruleta\run.py" (
    set "RUN_PY=bot_ruleta\run.py"
    goto :search_dashboard
)
echo [ERROR] No se encontro "bot_ruleta\run.py".
pause
exit /b 1

:search_dashboard
:: Verificar dashboard
set "APP_PY="
if exist "bot_ruleta\dashboard\app.py" (
    set "APP_PY=bot_ruleta\dashboard\app.py"
)

:start_bot
echo [OK] Bot principal: %RUN_PY%

:: Iniciar Dashboard si se encontro
if "%APP_PY%"=="" (
    echo [AVISO] Dashboard no encontrado, saltando paso.
    goto :launch_bot
)
echo [2/4] Iniciando Dashboard: %APP_PY%
start /MIN "Roulette Dashboard Server" "%PYTHON_EXE%" "%APP_PY%"
echo [OK] Dashboard iniciado. Esperando 3 segundos...
timeout /t 3 /nobreak > NUL
echo [3/4] Abriendo panel de control local...
start http://127.0.0.1:5050
echo [4/4] Abriendo tunel de Cloudflare para acceso remoto...
start "Cloudflare Tunnel" cmd /k "echo Iniciando Cloudflare, por favor espera tu link... && cloudflared tunnel --url http://localhost:5050"

:launch_bot
echo.
echo [OK] Iniciando Bot (Modo Headless)...
echo ==========================================
"%PYTHON_EXE%" "%RUN_PY%"
set "EXIT_CODE=%errorlevel%"

echo.
echo ===========================================
if %EXIT_CODE% neq 0 (
    echo [ERROR] El bot termino con codigo de error: %EXIT_CODE%
) else (
    echo [OK] El bot finalizo correctamente.
)
echo ===========================================
pause
