"""
Configuración centralizada del bot de ruleta.
Constantes, configuración de mesas, URLs y lectura de credenciales.
"""

import os

# --- MODO DE OPERACIÓN ---
LOBBY_MODE = True  # False = modo clásico (desactivado)

# --- MESAS CONFIGURADAS ---
# Los IDs se actualizan dinámicamente al iniciar (map_tables_dynamic).
# Los valores aquí son fallback en caso de que el escaneo falle.
TABLES = [
    {"name": "Ruleta Latina", "id": "roulerw234rwl292-234", "op_id": "234", "table_name": "ruleta_latina"},
    {"name": "Mega Roulette", "id": "1hl65ce1lxuqdrkr-204", "op_id": "204", "table_name": "mega_roulette"},
    {"name": "Brazilian Roulette", "id": "rwbrzportrwa16rg-237", "op_id": "237", "table_name": "brazilian_roulette"},
    {"name": "Roulette 1", "id": "g03y1t9vvuhrfytl-227", "op_id": "227", "table_name": "roulette_1"},
    {"name": "Roulette 3", "id": "chroma229rwltr22-230", "op_id": "230", "table_name": "roulette_3"},
    {"name": "Roulette Macao", "id": "yqpz3ichst2xg439-206", "op_id": "206", "table_name": "roulette_macao"},
     
    # Nuevas mesas añadidas a petición del usuario
    {"name": "Roulette 2 Extra Time", "id": "5kvxlw4c1qm3xcyn-201", "op_id": "201", "table_name": "roulette_2_extra_time"},
    {"name": "Brazilian Mega Roulette", "id": "mrbras531mrbr532-287", "op_id": "287", "table_name": "brazilian_mega_roulette"},
    {"name": "Lucky 6 Roulette", "id": "lucky6roulettea3-211a1", "op_id": "211a1", "table_name": "lucky_6_roulette"},
    {"name": "Auto Roulette", "id": "5bzl2835s5ruvweg-225", "op_id": "225", "table_name": "auto_roulette"},

    # Lote de ruletas regionales
    {"name": "Stake Roulette", "id": "rw321stakerws321-236", "op_id": "236", "table_name": "stake_roulette"},
    {"name": "Turkish Roulette", "id": "p81lj84prrmxzyic-224", "op_id": "224", "table_name": "turkish_roulette"},
    {"name": "German Roulette", "id": "s2x6b4jdeqza2ge2-222", "op_id": "222", "table_name": "german_roulette"},
    {"name": "Romanian Roulette", "id": "romania233rw1291-233", "op_id": "233", "table_name": "romanian_roulette"},
    {"name": "Roulette Italia Tricolore", "id": "v1c52fgw7yy02upz-223", "op_id": "223", "table_name": "roulette_italia_tricolore"},
    {"name": "Russian Roulette", "id": "t4jzencinod6iqwi-221", "op_id": "221", "table_name": "russian_roulette"},
    {"name": "Dutch Roulette", "id": "dutchrw235rw1293-235", "op_id": "235", "table_name": "dutch_roulette"},
]

# --- URLs ---
LOBBY_URL = "https://stake.com.co/es/casino/juego/roulette-lobby-571"

# --- DIRECTORIOS ---
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# --- INTERVALOS ---
AFK_INTERVAL = 300  # segundos (120 = 2 min debug, 300 = 5 min producción)

# --- COLORES DE RULETA ---
REDS = ['1', '3', '5', '7', '9', '12', '14', '16', '18',
        '19', '21', '23', '25', '27', '30', '32', '34', '36']


def load_credentials():
    """Lee credenciales del archivo .env en la raíz del proyecto."""
    email = ""
    password = ""
    tg_token = ""
    tg_chat_id = ""
    alert_threshold = 12
    headless = True 

    # Buscar .env en la raíz del proyecto
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
            
            valid_lines = [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]
            creds = [line for line in valid_lines if "=" not in line]
            
            # Backwards compatibility con el archivo viejo (sin llaves)
            if len(creds) >= 1: email = creds[0]
            if len(creds) >= 2: password = creds[1]
            
            for line in valid_lines:
                if "=" in line:
                    parts = line.split("=", 1)
                    key = parts[0].strip()
                    val = parts[1].split("#")[0].strip()
                    
                    if key == "STAKE_EMAIL" or key == "CORREO":
                        email = val
                    elif key == "STAKE_PASSWORD" or key == "CONTRASEÑA" or key == "CONTRASENA":
                        password = val
                    elif key == "TELEGRAM_TOKEN":
                        tg_token = val
                    elif key == "TELEGRAM_CHAT_ID":
                        tg_chat_id = val
                    elif key == "ALERT_THRESHOLD":
                        try:
                            alert_threshold = int(val)
                        except:
                            alert_threshold = 12
                    elif key == "HEADLESS":
                        headless = (val.lower() == "true")

    except Exception as e:
        print(f"⚠️ No se pudo leer .env: {e}")
    
    return email, password, tg_token, tg_chat_id, alert_threshold, headless
