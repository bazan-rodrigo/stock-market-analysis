# -*- coding: utf-8 -*-
"""
Servicio: failed_updates.py
Versión adaptada a tu modelo actual en db_models.py
"""

from datetime import datetime
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from services.db import get_session
from models.db_models import FailedUpdate, Asset, PriceSource
from core.logging_config import get_logger

logger = get_logger(__name__)


def register_failed_update(asset_id=None, source_id=None, error_message="", run_type="manual"):
    """Registra un nuevo error de actualización."""
    session = get_session()
    try:
        entry = FailedUpdate(
            asset_id=asset_id,
            source_id=source_id,
            error_message=error_message[:255],
            run_type=run_type,
            timestamp=datetime.now(),
            resolved=False
        )
        session.add(entry)
        session.commit()
        logger.warning(f"[FAILED UPDATE] asset_id={asset_id}, fuente={source_id}: {error_message}")
    except Exception as e:
        session.rollback()
        logger.error(f"Error registrando failed_update: {e}")
    finally:
        session.close()


def list_failed_updates():
    """Devuelve una lista de errores no resueltos."""
    session = get_session()
    try:
        query = (
            select(
                FailedUpdate.id,
                Asset.symbol,
                PriceSource.code.label("source"),
                FailedUpdate.error_message,
                FailedUpdate.run_type,
                FailedUpdate.timestamp
            )
            .join(Asset, FailedUpdate.asset_id == Asset.id, isouter=True)
            .join(PriceSource, FailedUpdate.source_id == PriceSource.id, isouter=True)
            .where(FailedUpdate.resolved == False)
            .order_by(FailedUpdate.timestamp.desc())
        )
        results = session.execute(query).mappings().all()
        return [dict(r) for r in results]
    except Exception as e:
        logger.error(f"Error listando failed_updates: {e}")
        return []
    finally:
        session.close()


def mark_failed_update_resolved(update_id: int):
    """Marca un error como resuelto."""
    session = get_session()
    try:
        session.execute(
            update(FailedUpdate)
            .where(FailedUpdate.id == update_id)
            .values(resolved=True)
        )
        session.commit()
        logger.info(f"Failed update {update_id} marcado como resuelto.")
    except Exception as e:
        session.rollback()
        logger.error(f"Error marcando failed_update como resuelto: {e}")
    finally:
        session.close()