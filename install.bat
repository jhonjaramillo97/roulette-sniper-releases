@echo off
title INSTALADOR ROULETTE SNIPER
cls
echo ===========================================
echo    INSTALADOR DE DEPENDENCIAS - WINDOWS
echo ===========================================
echo.

cd /d "%~dp0"

:: 1. Verificar Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python no esta detectado en las variables de entorno.
    echo Por favor instala Python desde python.org
    echo y asegurate de marcar "Add Python to PATH".
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
echo [OK] %PY_VER% detectado.
echo.

:: 2. Verificar si el venv existente es valido (puede estar corrupto si se copio de otro PC)
echo [1/3] Verificando entorno virtual (venv)...
set "VENV_VALID=0"
if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe --version >nul 2>&1
    if %errorlevel% equ 0 (
        set "VENV_VALID=1"
    )
)

if "%VENV_VALID%"=="0" (
    if exist "venv" (
        echo [AVISO] El entorno virtual existente es invalido o fue copiado de otro PC.
        echo Eliminando venv y creando uno nuevo...
        rmdir /s /q venv
    ) else (
        echo Creando entorno virtual nuevo...
    )
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
    echo [OK] Entorno virtual creado.
) else (
    echo [OK] Entorno virtual valido encontrado.
)
echo.

:: 3. Actualizar PIP
echo [2/3] Actualizando PIP...
call venv\Scripts\python.exe -m pip install --upgrade pip --quiet

:: 4. Instalar librerias
echo [3/3] Buscando requirements.txt...
set "REQ_FILE=requirements.txt"

if not exist "%REQ_FILE%" (
    echo [INFO] requirements.txt no encontrado en la raiz, buscando en subcarpetas...
    for /r %%i in (requirements.txt) do (
        if exist "%%i" (
            set "REQ_FILE=%%i"
            goto :found
        )
    )
)

:found
if not exist "%REQ_FILE%" (
    echo [ERROR] No se pudo encontrar el archivo requirements.txt en ningun lugar.
    echo Asegurate de que el archivo existe en la carpeta del bot.
    pause
    exit /b 1
)

echo [OK] Instalando librerias desde: %REQ_FILE%
call venv\Scripts\pip.exe install -r "%REQ_FILE%"
if %errorlevel% neq 0 (
    echo [ERROR] Hubo un problema instalando las librerias.
    pause
    exit /b 1
)

echo.
echo ===========================================
echo    INSTALACION COMPLETADA CON EXITO
echo ===========================================
echo.
echo Ahora puedes usar "start_bot.bat" para iniciar el bot.
pause
