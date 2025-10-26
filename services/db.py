# -*- coding: utf-8 -*-
"""
Modulo de conexion a base de datos.
Crea el motor SQLAlchemy y la sesion para consultas.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config.config import get_config

_cfg = get_config()

# Se define el motor de conexion, con parametros de pool
engine = create_engine(
    _cfg["DB_URI"],
    pool_pre_ping=True,
    pool_recycle=3600,
    future=True
)

# Crea la sesion de trabajo
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

def get_session():
    """Retorna una nueva sesion de base de datos."""
    return SessionLocal()