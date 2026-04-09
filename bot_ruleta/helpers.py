"""
Funciones auxiliares puras: escritura simulada, persistencia CSV.
"""

import csv
import os
import random
import time


def human_type(element, text):
    """Escribe texto con retardos aleatorios para simular humano."""
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(0.05, 0.2))



