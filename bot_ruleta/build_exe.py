"""
Script para empaquetar Roulette Sniper Pro en un solo .exe
Requiere: pip install pyinstaller
"""

import os
import subprocess
import sys

def build():
    # Rutas base
    base_dir = os.path.dirname(os.path.abspath(__file__))
    main_script = os.path.join(base_dir, "gui_app.py")
    icon_path = os.path.join(base_dir, "icon.ico")

    # Asegurarse de que las dependencias están instaladas
    print("Verificando dependencias...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", os.path.join(base_dir, "requirements.txt")])
    except Exception as e:
        print(f"WARN: Error instalando requerimientos: {e}")

    # Asegurarse de que pyinstaller está instalado
    try:
        import PyInstaller
    except ImportError:
        print("Instalando PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    # Construir comando de PyInstaller
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name=RouletteSniperPro",
        "--onefile",
        "--windowed",  # Sin consola negra
        "--clean",
        "--noconfirm",
    ]

    # Incluir ícono si existe
    if os.path.exists(icon_path):
        cmd.append(f"--icon={icon_path}")
        # Asegurar que el icono se incluya en el paquete en tiempo de ejecución
        separator = ";" if os.name == 'nt' else ":"
        cmd.append(f"--add-data={icon_path}{separator}.")

    # Incluir datos estáticos del dashboard (Flask)
    dashboard_static = os.path.join(base_dir, "dashboard", "static")
    if os.path.exists(dashboard_static):
        cmd.append(f"--add-data={dashboard_static};dashboard/static")

    # Intentar obtener la ruta de customtkinter para incluirla explícitamente
    try:
        import customtkinter
        ctk_path = os.path.dirname(customtkinter.__file__)
        cmd.append(f"--add-data={ctk_path};customtkinter")
        print(f"-> Incluyendo customtkinter desde: {ctk_path}")
    except ImportError:
        print("WARN: No se pudo encontrar customtkinter para inclusion explicita.")

    # Incluir dependencias y asegurar que se recolecte todo
    cmd.append("--collect-all=customtkinter")
    cmd.append("--collect-all=PIL")
    cmd.append("--collect-all=selenium")
    cmd.append("--collect-all=undetected_chromedriver")
    
    # Forzar inclusion de metadatos y datos especificos que fallan en --onefile
    cmd.append("--copy-metadata=selenium")
    cmd.append("--copy-metadata=undetected-chromedriver")
    cmd.append("--collect-data=selenium")
    cmd.append("--collect-data=customtkinter")
    
    cmd.append("--collect-submodules=customtkinter")
    cmd.append("--hidden-import=undetected_chromedriver")
    cmd.append("--hidden-import=selenium")
    cmd.append("--hidden-import=PIL")
    cmd.append("--hidden-import=urllib")
    cmd.append("--hidden-import=tkinter")
    cmd.append("--hidden-import=waitress")  # Dashboard production server
    cmd.append("--exclude-module=pytest")
    cmd.append("--exclude-module=IPython")

    cmd.append(main_script)

    print("="*50)
    print(">>> Construyendo Roulette Sniper Pro.exe...")
    print("="*50)
    
    # Ejecutar PyInstaller
    subprocess.check_call(cmd)
    
    print("="*50)
    print("[OK] Build completado exitosamente.")
    print("El ejecutable está en la carpeta 'dist'")
    print("="*50)

if __name__ == "__main__":
    build()
