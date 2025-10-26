# -*- coding: utf-8 -*-
"""
Servicio de administracion de usuarios.
Contiene toda la logica de creacion, actualizacion y consulta de usuarios.
La capa de UI (Dash) solo debe llamar a estas funciones.
"""

from sqlalchemy import select
from werkzeug.security import generate_password_hash
from services.db import get_session
from models.db_models import User
from core.logging_config import get_logger

logger = get_logger()

def create_user(username: str, password: str, role: str = "analyst") -> str:
    """
    Crea un nuevo usuario si no existe.
    Retorna un mensaje con el resultado.
    """
    session = get_session()
    try:
        if not username or not password:
            return "Usuario o clave vacios."

        existing = session.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if existing:
            return f"El usuario '{username}' ya existe."

        hashed_pw = generate_password_hash(password)
        user = User(username=username, password_hash=hashed_pw, role=role, is_active=True)
        session.add(user)
        session.commit()
        logger.info(f"Usuario '{username}' creado correctamente.")
        return f"Usuario '{username}' creado correctamente."
    except Exception as e:
        session.rollback()
        logger.error(f"Error creando usuario {username}: {e}")
        return f"Error: {e}"
    finally:
        session.close()

def get_all_users() -> list:
    """
    Devuelve una lista de todos los usuarios activos.
    """
    session = get_session()
    try:
        users = session.execute(select(User)).scalars().all()
        return [{"username": u.username, "role": u.role, "is_active": u.is_active} for u in users]
    finally:
        session.close()