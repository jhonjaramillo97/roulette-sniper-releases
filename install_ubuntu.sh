#!/bin/bash
# ==============================================================================
# ⚙️ INSTALADOR AUTOMÁTICO PARA UBUNTU (AWS / VPS) - ROULETTE SNIPER
# ==============================================================================

echo "[1] Actualizando lista de paquetes del sistema operativo..."
sudo apt-get update -y && sudo apt-get upgrade -y

echo "[2] Instalando Python 3, pip y herramientas de entorno virtual..."
sudo apt-get install -y python3 python3-pip python3-venv

echo "[3] Instalando dependencias necesarias para Google Chrome y la Pantalla Fantasma (Xvfb)..."
sudo apt-get install -y wget curl unzip xvfb libxi6 libgconf-2-4 libnss3 libxss1 libasound2 libatk-bridge2.0-0 libgtk-3-0 dbus-x11

echo "[4] Descargando e instalando Google Chrome Estable..."
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo dpkg -i google-chrome-stable_current_amd64.deb
sudo apt --fix-broken install -y
rm google-chrome-stable_current_amd64.deb

echo "[5] Creando archivo de Memoria RAM Virtual (SWAP) de 2GB..."
# Google Chrome consume mucha RAM al estar corriendo días enteros.
# Esto previene que el servidor (especialmente los de 1GB o 2GB de RAM) muera por falta de memoria.
if [ ! -f /swapfile ]; then
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    echo "SWAP configurado exitosamente."
else
    echo "SWAP ya existe, saltando este paso."
fi

echo "[6] Creando y aislando Entorno Virtual de Python..."
python3 -m venv venv

echo "[7] Activando entorno e instalando librerías del Bot (requirements.txt)..."
source venv/bin/activate
pip install --upgrade pip
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    echo "⚠️ ADVERTENCIA: No se encontró requirements.txt en esta carpeta."
fi

echo "=============================================================================="
echo "✅ Instalación completada en el Servidor Ubuntu."
echo "Para arrancar el bot permanente, utiliza tmux o screen y luego:"
echo "source venv/bin/activate"
echo "xvfb-run -a python3 start_bot.py"
echo "=============================================================================="
