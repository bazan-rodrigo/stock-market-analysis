# -*- coding: utf-8 -*-
"""
Configuración del sistema de logs usando Loguru.
Crea logs rotativos diarios, tanto en consola como en archivo.
Provee get_logger(__name__) para obtener un logger contextual.
"""

from loguru import logger
import sys, os
from datetime import datetime
from config.config import get_config

_cfg = get_config()
os.makedirs(_cfg["LOG_DIR"], exist_ok=True)

_log_file = os.path.join(
    _cfg["LOG_DIR"],
    f"stock_app_{datetime.now().strftime('%Y%m%d')}.log"
)

# Configuración base del logger global
logger.remove()
logger.add(sys.stdout,
           level="INFO",
           colorize=True,
           format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
                  "<cyan>{extra[module]}</cyan> - {message}")

logger.add(_log_file,
           level="DEBUG",
           rotation="20 MB",
           retention="1 week",
           format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {extra[module]} | {message}")


def get_logger(module_name: str):
    """
    Devuelve una instancia del logger con contexto de módulo.
    Ejemplo:
        logger = get_logger(__name__)
    """
    return logger.bind(module=module_name)
