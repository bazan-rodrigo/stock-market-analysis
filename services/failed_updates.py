# -*- coding: utf-8 -*-
"""
Servicio: failed_updates.py
Gestiona los registros de actualizaciones fallidas.
"""

from sqlalchemy import select, update
from services.db import get_session
from models.db_models import FailedUpdate, Asset
from core.logging_config import get_logger

logger = get_logger()

def list_failed_updates(limit=100):
    """
    Devuelve los ultimos errores registrados.
    """
    session = get_session()
    try:
        fails = session.execute(
            select(FailedUpdate).order_by(FailedUpdate.run_timestamp.desc()).limit(limit)
        ).scalars().all()

        return [
            {
                "asset": f.asset.symbol if f.asset else None,
                "source": f.source.name if f.source else None,
                "timestamp": f.run_timestamp,
                "error": f.error_message,
                "resolved": f.resolved
            }
            for f in fails
        ]
    finally:
        session.close()


def mark_failed_update_resolved(fail_id: int):
    """
    Marca un registro de fallo como resuelto.
    """
    session = get_session()
    try:
        stmt = (
            update(FailedUpdate)
            .where(FailedUpdate.id == fail_id)
            .values(resolved=True)
        )
        session.execute(stmt)
        session.commit()
        logger.info(f"Fallo {fail_id} marcado como resuelto.")
    except Exception as e:
        session.rollback()
        logger.error(f"Error marcando fallo {fail_id}: {e}")
    finally:
        session.close()