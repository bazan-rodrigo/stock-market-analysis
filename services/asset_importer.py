# -*- coding: utf-8 -*-
"""
Servicio: asset_importer.py
Importa activos en forma individual o masiva.
Cada asset tiene una unica fuente asociada.
"""

from sqlalchemy import select
from services.db import get_session
from models.db_models import Asset, PriceSource
from core.logging_config import get_logger

logger = get_logger()

def import_asset(symbol: str, name: str, source_code: str, source_symbol: str, sector=None, industry=None, country=None, currency="USD"):
    """
    Crea un nuevo activo con su fuente asociada.
    Si ya existe el simbolo, no se inserta nuevamente.
    """
    session = get_session()
    try:
        # Buscar fuente por code
        source = session.execute(select(PriceSource).where(PriceSource.code == source_code)).scalar_one_or_none()
        if not source:
            raise ValueError(f"Fuente de precios {source_code} no encontrada")

        existing = session.execute(select(Asset).where(Asset.symbol == symbol)).scalar_one_or_none()
        if existing:
            return f"El activo {symbol} ya existe."

        asset = Asset(
            symbol=symbol,
            name=name,
            source_id=source.id,
            source_symbol=source_symbol,
            sector=sector,
            industry=industry,
            country=country,
            currency=currency
        )
        session.add(asset)
        session.commit()
        logger.info(f"Activo {symbol} creado con fuente {source_code}")
        return f"Activo {symbol} importado correctamente desde {source_code}."
    except Exception as e:
        session.rollback()
        logger.error(f"Error importando asset {symbol}: {e}")
        return f"Error importando asset {symbol}: {e}"
    finally:
        session.close()