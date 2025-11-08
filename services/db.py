# services/db.py
# -*- coding: utf-8 -*-
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from dotenv import load_dotenv

load_dotenv()
DB_URI = os.getenv("DB_URI")

engine = create_engine(DB_URI, echo=False, pool_pre_ping=True)
SessionLocal = scoped_session(sessionmaker(bind=engine, autocommit=False, autoflush=False))

def get_session():
    """Retorna una sesión SQLAlchemy segura."""
    return SessionLocal()

def close_session():
    """Cierra la sesión actual."""
    SessionLocal.remove()
