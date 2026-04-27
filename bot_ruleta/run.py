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

from bot_ruleta.debug_logger import get_logger, run_diagnostics

log = get_logger("run")

if __name__ == "__main__":
    log.info("=" * 60)
    log.info("🚀 Bot de Ruleta iniciando...")
    log.info("=" * 60)
    
    # Diagnóstico de entorno al inicio directo
    run_diagnostics()
    
    from bot_ruleta.scanner import run_bot
    run_bot()
