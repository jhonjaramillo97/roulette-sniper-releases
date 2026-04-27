"""
Almacenamiento seguro de credenciales para la GUI.
Guarda las credenciales en un archivo JSON ofuscado con base64.
"""

import os
import json
import base64
import hashlib
import platform

import sys

if getattr(sys, 'frozen', False):
    DATA_DIR = os.path.join(os.path.dirname(sys.executable), "data")
else:
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

_CRED_FILE = os.path.join(DATA_DIR, "credentials.dat")


def _get_key():
    """Genera una clave de ofuscación basada en el nombre de la máquina."""
    machine = platform.node() or "default_machine"
    return hashlib.sha256(machine.encode()).digest()


def _xor_bytes(data: bytes, key: bytes) -> bytes:
    """XOR simple para ofuscación."""
    return bytes(d ^ key[i % len(key)] for i, d in enumerate(data))


def save_credentials(email, password, tg_token, tg_chat_id, threshold, headless, diagnostics=False):
    """Guarda credenciales ofuscadas en disco."""
    os.makedirs(os.path.dirname(_CRED_FILE), exist_ok=True)
    data = json.dumps({
        "email": email,
        "password": password,
        "tg_token": tg_token,
        "tg_chat_id": tg_chat_id,
        "threshold": threshold,
        "headless": headless,
        "diagnostics": diagnostics,
    }).encode("utf-8")
    encrypted = _xor_bytes(data, _get_key())
    with open(_CRED_FILE, "wb") as f:
        f.write(base64.b64encode(encrypted))


def load_saved_credentials():
    """Carga credenciales guardadas. Retorna dict o None."""
    if not os.path.exists(_CRED_FILE):
        return None
    try:
        with open(_CRED_FILE, "rb") as f:
            encrypted = base64.b64decode(f.read())
        data = _xor_bytes(encrypted, _get_key())
        return json.loads(data.decode("utf-8"))
    except Exception:
        return None


def has_saved_credentials():
    """Retorna True si hay credenciales guardadas."""
    return os.path.exists(_CRED_FILE)


def delete_saved_credentials():
    """Elimina las credenciales guardadas."""
    if os.path.exists(_CRED_FILE):
        os.remove(_CRED_FILE)
