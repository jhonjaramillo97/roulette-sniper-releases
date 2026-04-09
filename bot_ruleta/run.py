#!/usr/bin/env python3
"""
Entrypoint del bot de ruleta.
Uso: python run.py
"""

import sys
import os

# Añadir directorio raíz del proyecto al path para importar bot_ruleta como paquete
# __file__ = bot_ruleta/run.py
# dirname = bot_ruleta
# dirname(dirname) = PROYECTO ROOT
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot_ruleta.scanner import run_bot

if __name__ == "__main__":
    run_bot()
