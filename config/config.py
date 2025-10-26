# -*- coding: utf-8 -*-
"""
Archivo de configuracion seguro.
Carga variables desde el archivo .env o desde el entorno del sistema.
"""

import os
from dotenv import load_dotenv

# Cargar variables desde el archivo .env si existe
load_dotenv()

def get_config():
    return {
        "DB_URI": os.getenv("DB_URI"),
        "SECRET_KEY": os.getenv("SECRET_KEY"),
        "LOG_DIR": os.getenv("LOG_DIR", "logs"),
        "DEFAULT_SOURCE_CODE": os.getenv("DEFAULT_SOURCE_CODE", "YAHOO"),
        "SCHEDULER_ENABLED": os.getenv("SCHEDULER_ENABLED", "0") == "1",
    }