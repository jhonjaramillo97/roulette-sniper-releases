import os
import sys
import json
import base64
import urllib.request
import urllib.error
import subprocess

GITHUB_TOKEN = "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"
REPO_OWNER = "jhonjaramillo97"
REPO_NAME = "roulette-sniper-releases"
EXE_PATH = os.path.join("dist", "RouletteSniperPro.exe")
UPDATER_FILE = os.path.join("bot_ruleta", "updater.py")

def api_request(url, method="GET", data=None, is_upload=False):
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Publish-Script"
    }
    
    if is_upload:
        headers["Content-Type"] = "application/octet-stream"
    elif data:
        headers["Content-Type"] = "application/json"
        data = json.dumps(data).encode("utf-8")
        
    # Para subidas grandes (el EXE ahora es mas pesado), necesitamos mucho mas tiempo
    timeout = 600 if is_upload else 60
    
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 204: # No content
                return {}
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        print(f"Error HTTP {e.code}: {e.read().decode()}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

def get_file_sha(path):
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{path}"
    try:
        res = api_request(url)
        return res.get("sha")
    except:
        return None

def update_github_version_file(new_version):
    print("-> Actualizando version.txt en GitHub...")
    path = "version.txt"
    sha = get_file_sha(path)
    
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{path}"
    content_b64 = base64.b64encode(new_version.encode("utf-8")).decode("utf-8")
    
    data = {
        "message": f"Update version to {new_version}",
        "content": content_b64
    }
    if sha:
        data["sha"] = sha
        
    api_request(url, method="PUT", data=data)
    print("OK: version.txt actualizado en GitHub.")

def update_local_updater(new_version):
    print("-> Actualizando updater.py localmente...")
    with open(UPDATER_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    for i, line in enumerate(lines):
        if line.startswith("CURRENT_VERSION = "):
            lines[i] = f'CURRENT_VERSION = "{new_version}"\n'
            break
            
    with open(UPDATER_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print("OK: updater.py actualizado.")

def build_executable():
    print("-> Compilando nuevo ejecutable. Esto tomara unos minutos...")
    try:
        subprocess.check_call([sys.executable, os.path.join("bot_ruleta", "build_exe.py")])
        print("OK: Ejecutable compilado con exito.")
    except Exception as e:
        print(f"Error al compilar: {e}")
        sys.exit(1)

def get_release_by_tag(tag):
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/tags/{tag}"
    try:
        return api_request(url)
    except:
        return None

def delete_release(release_id):
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/{release_id}"
    api_request(url, method="DELETE")

def delete_tag(tag):
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/git/refs/tags/{tag}"
    try:
        api_request(url, method="DELETE")
    except:
        pass

def create_release(new_version):
    tag = f"v{new_version}"
    print(f"-> Verificando si existe la Release {tag}...")
    
    existing = get_release_by_tag(tag)
    if existing:
        print(f"-> La Release {tag} ya existe. Eliminandola para subir el nuevo archivo...")
        delete_release(existing["id"])
        delete_tag(tag)
        print("OK: Release anterior eliminada.")

    print(f"-> Creando Release {tag} en GitHub...")
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases"
    data = {
        "tag_name": tag,
        "name": f"Version {new_version}",
        "body": "Actualizacion automatica de Roulette Sniper Pro.",
        "draft": False,
        "prerelease": False
    }
    
    res = api_request(url, method="POST", data=data)
    print(f"OK: Release {tag} creado.")
    return res["id"]

def upload_asset(release_id, file_path):
    print("-> Subiendo RouletteSniperPro.exe a GitHub (puede tardar unos minutos)...")
    url = f"https://uploads.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/{release_id}/assets?name=RouletteSniperPro.exe"
    
    with open(file_path, "rb") as f:
        file_data = f.read()
        
    api_request(url, method="POST", data=file_data, is_upload=True)
    print("OK: Archivo subido con exito.")

def main():
    print("="*50)
    print("ROULETTE SNIPER - PUBLICADOR AUTOMATICO")
    print("="*50)
    
    if len(sys.argv) > 1:
        new_version = sys.argv[1].strip()
    else:
        new_version = input("\nIngresa el nuevo numero de version (ej: 1.1.0): ").strip()
        
    if not new_version:
        print("Operacion cancelada.")
        return
        
    print(f"\nIniciando proceso de lanzamiento para la version {new_version}...\n")
    
    # 1. Actualizar código local
    update_local_updater(new_version)
    
    # 2. Compilar
    build_executable()
    
    # 3. Subir version.txt a GitHub
    update_github_version_file(new_version)
    
    # 4. Crear Release
    release_id = create_release(new_version)
    
    # 5. Subir .exe
    upload_asset(release_id, EXE_PATH)
    
    print("\n" + "="*50)
    print("LANZAMIENTO COMPLETADO EXITOSAMENTE!")
    print(f"Los clientes recibiran la actualizacion {new_version} al abrir su bot.")
    print("="*50)

if __name__ == "__main__":
    main()
