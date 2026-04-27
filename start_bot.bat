@echo off
chcp 65001 >nul
title ROULETTE SNIPER BOT - DASHBOARD
cls
echo ===========================================
echo    ROULETTE SNIPER - BOT LAUNCHER
echo ===========================================
echo.

cd /d "%~dp0"

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
set "LAUNCHER_PY=bot_ruleta\launcher.py"

if not exist "%LAUNCHER_PY%" (
    echo [ERROR] No se encontro la arquitectura principal en "%LAUNCHER_PY%".
    pause
    exit /b 1
)

:: Iniciar Orquestador Minimalista con Cloudflare Integrado
"%PYTHON_EXE%" "%LAUNCHER_PY%"

pause
