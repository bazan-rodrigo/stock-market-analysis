# -*- coding: utf-8 -*-
"""
Configuracion del sistema de logs usando Loguru.
Crea logs rotativos diarios, tanto en consola como en archivo.
"""

from loguru import logger
import sys, os
from datetime import datetime
from config.config import get_config

# Se crea la carpeta de logs si no existe
_cfg = get_config()
os.makedirs(_cfg["LOG_DIR"], exist_ok=True)
_log_file = os.path.join(_cfg["LOG_DIR"], f"stock_app_{datetime.now().strftime('%Y%m%d')}.log")

# Configuracion del formato de los logs
logger.remove()
logger.add(sys.stdout,
           level="INFO",
           colorize=True,
           format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | {name}:{function}:{line} - <level>{message}</level>")
logger.add(_log_file, level="DEBUG", rotation="20 MB", retention="15 days", compression="zip")

def get_logger():
    """Retorna el logger configurado para usar en cualquier modulo."""
    return logger