# -*- coding: utf-8 -*-
"""
Servicio de autenticacion.
Encapsula la logica de login y validacion de usuarios.
No debe ser llamado directamente desde Flask/Dash, sino a traves de la UI.
"""

from sqlalchemy import select
from werkzeug.security import check_password_hash
from services.db import get_session
from models.db_models import User
from core.logging_config import get_logger

logger = get_logger()

def authenticate_user(username: str, password: str):
    """
    Autentica un usuario.
    Retorna el objeto User si las credenciales son correctas, None en caso contrario.
    """
    session = get_session()
    try:
        user = session.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if user and check_password_hash(user.password_hash, password):
            return user
        return None
    except Exception as e:
        logger.error(f"Error autenticando usuario {username}: {e}")
        return None
    finally:
        session.close()

def get_user_by_id(user_id: int):
    """
    Retorna un usuario por ID.
    """
    session = get_session()
    try:
        return session.get(User, user_id)
    finally:
        session.close()