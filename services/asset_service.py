# -*- coding: utf-8 -*-
"""
Servicio de gestión de activos (Assets).
Permite crear, eliminar, listar y obtener fuentes de datos.
"""

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from core.logging_config import get_logger
from services.db import get_session
from models.db_models import Asset, Source

logger = get_logger(__name__)


# ==========================================================
# Crear nuevo asset
# ==========================================================
def create_asset(symbol: str, name: str, source_id: int, source_symbol: str):
    """
    Crea un nuevo activo si no existe.
    Retorna (mensaje, ok)
    """
    session = get_session()
    try:
        # Verificar duplicado por símbolo
        existing = session.execute(
            select(Asset).where(Asset.symbol == symbol)
        ).scalar_one_or_none()

        if existing:
            msg = f"El activo '{symbol}' ya existe."
            logger.warning(msg)
            return msg, False

        new_asset = Asset(
            symbol=symbol.strip().upper(),
            name=name.strip(),
            source_id=source_id,
            source_symbol=source_symbol.strip(),
        )
        session.add(new_asset)
        session.commit()
        msg = f"Activo '{symbol}' creado exitosamente."
        logger.info(msg)
        return msg, True

    except SQLAlchemyError as e:
        session.rollback()
        msg = f"Error SQL al crear asset '{symbol}': {e}"
        logger.error(msg)
        return msg, False

    except Exception as e:
        session.rollback()
        msg = f"Error inesperado al crear asset '{symbol}': {e}"
        logger.error(msg)
        return msg, False

    finally:
        session.close()


# ==========================================================
# Eliminar asset
# ==========================================================
def delete_asset(asset_id: int):
    """
    Elimina un activo por su ID.
    Retorna (mensaje, ok)
    """
    session = get_session()
    try:
        asset = session.get(Asset, asset_id)
        if not asset:
            msg = f"Activo ID {asset_id} no encontrado."
            logger.warning(msg)
            return msg, False

        session.delete(asset)
        session.commit()
        msg = f"Activo '{asset.symbol}' eliminado correctamente."
        logger.info(msg)
        return msg, True

    except SQLAlchemyError as e:
        session.rollback()
        msg = f"Error SQL al eliminar asset {asset_id}: {e}"
        logger.error(msg)
        return msg, False

    except Exception as e:
        session.rollback()
        msg = f"Error inesperado al eliminar asset {asset_id}: {e}"
        logger.error(msg)
        return msg, False

    finally:
        session.close()


# ==========================================================
# Listar todos los assets
# ==========================================================
def list_assets():
    """
    Devuelve una lista de assets como lista de diccionarios.
    """
    session = get_session()
    try:
        result = session.execute(
            select(
                Asset.id,
                Asset.symbol,
                Asset.name,
                Asset.source_symbol,
                Asset.country,
                Asset.currency,
                Source.code.label("source")
            ).join(Source, Source.id == Asset.source_id)
        ).mappings().all()

        assets = [dict(row) for row in result]
        return assets

    except SQLAlchemyError as e:
        logger.error(f"Error SQL al listar assets: {e}")
        return []

    except Exception as e:
        logger.error(f"Error inesperado al listar assets: {e}")
        return []

    finally:
        session.close()


# ==========================================================
# Listar fuentes disponibles
# ==========================================================
def list_sources():
    """
    Devuelve las fuentes disponibles como lista de opciones para Dropdown.
    """
    session = get_session()
    try:
        result = session.execute(
            select(Source.id, Source.name)
        ).all()
        options = [{"label": name, "value": id_} for id_, name in result]
        return options

    except SQLAlchemyError as e:
        logger.error(f"Error SQL al listar fuentes: {e}")
        return []

    except Exception as e:
        logger.error(f"Error inesperado al listar fuentes: {e}")
        return []

    finally:
        session.close()


# ==========================================================
# Obtener ID de fuente por código
# ==========================================================
def get_source_id_by_code(code: str):
    """
    Retorna el ID de una fuente a partir de su código.
    """
    session = get_session()
    try:
        src = session.execute(
            select(Source.id).where(Source.code == code)
        ).scalar_one_or_none()
        return src

    except Exception as e:
        logger.error(f"Error buscando fuente '{code}': {e}")
        return None

    finally:
        session.close()