# -*- coding: utf-8 -*-
"""
Servicio de importación de activos desde archivos o fuentes externas.
Refactorizado para manejo de duplicados, logs y rollback seguro.
"""

from core.logging_config import get_logger
from services.db import get_session
from models.db_models import Asset, PriceSource
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

logger = get_logger(__name__)

def import_asset(asset_data: dict) -> dict:
    """
    Inserta o actualiza un activo en la base de datos.
    Retorna un dict con resultado detallado.
    """
    session = get_session()
    result = {"success": False, "action": None, "symbol": asset_data.get("symbol")}

    try:
        # Buscar fuente asociada por código
        src_code = asset_data.get("source_code")
        src = session.execute(
            select(PriceSource).where(PriceSource.code == src_code)
        ).scalar_one_or_none()

        if not src:
            logger.error(f"Fuente '{src_code}' no encontrada para {asset_data.get('symbol')}.")
            result["message"] = f"Fuente '{src_code}' no encontrada."
            return result

        # Verificar duplicado
        symbol = asset_data.get("symbol")
        existing = session.execute(
            select(Asset).where(Asset.symbol == symbol)
        ).scalar_one_or_none()

        if existing:
            # Actualizar si cambió algo
            changed = False
            for key, value in asset_data.items():
                if hasattr(existing, key) and getattr(existing, key) != value:
                    setattr(existing, key, value)
                    changed = True
            if changed:
                session.commit()
                result.update({"success": True, "action": "updated"})
                logger.info(f"Asset actualizado: {symbol}")
            else:
                result.update({"success": True, "action": "skipped"})
                logger.info(f"Asset sin cambios: {symbol}")
        else:
            # Crear nuevo activo
            new_asset = Asset(**asset_data)
            new_asset.source_id = src.id
            session.add(new_asset)
            session.commit()
            result.update({"success": True, "action": "created"})
            logger.info(f"Asset creado: {symbol}")

    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Error SQL al importar asset {asset_data.get('symbol')}: {e}")
        result["message"] = str(e)

    except Exception as e:
        session.rollback()
        logger.error(f"Error inesperado importando asset {asset_data.get('symbol')}: {e}")
        result["message"] = str(e)

    finally:
        session.close()

    return result