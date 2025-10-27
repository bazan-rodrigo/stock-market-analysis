# -*- coding: utf-8 -*-
"""
Servicio: asset_service.py
Lógica de negocio para manejo de activos (Assets).
Esta capa se comunica con la DB, y es utilizada por la UI (Dash).
"""

from sqlalchemy import select
from services.db import get_session
from models.db_models import Asset, PriceSource
from core.logging_config import get_logger

logger = get_logger()

# ==========================================================
# FUNCIONES PRINCIPALES
# ==========================================================

def list_assets():
    """Devuelve todos los activos como lista de diccionarios."""
    session = get_session()
    try:
        assets = session.execute(select(Asset)).scalars().all()
        data = []
        for a in assets:
            data.append({
                "id": a.id,
                "symbol": a.symbol,
                "name": a.name,
                "source": a.source.name if a.source else "",
                "source_symbol": a.source_symbol,
                "country": a.country,
                "currency": a.currency,
            })
        return data
    finally:
        session.close()


def list_sources():
    """Devuelve las fuentes activas disponibles para asociar a un asset."""
    session = get_session()
    try:
        sources = session.execute(select(PriceSource).where(PriceSource.is_active == True)).scalars().all()
        return [{"label": f"{s.name} ({s.code})", "value": s.id} for s in sources]
    finally:
        session.close()


def create_asset(symbol: str, name: str, source_id: int, source_symbol: str,
                 country: str = "US", currency: str = "USD"):
    """
    Crea un nuevo activo en la base de datos.
    Devuelve un mensaje de resultado y True/False según éxito.
    """
    session = get_session()
    try:
        existing = session.execute(select(Asset).where(Asset.symbol == symbol.upper())).scalar_one_or_none()
        if existing:
            return f"El activo '{symbol}' ya existe.", False

        asset = Asset(
            symbol=symbol.upper().strip(),
            name=name.strip(),
            source_id=source_id,
            source_symbol=source_symbol.strip(),
            country=country,
            currency=currency
        )
        session.add(asset)
        session.commit()
        logger.info(f"Activo agregado: {symbol}")
        return f"Activo '{symbol}' agregado correctamente.", True
    except Exception as e:
        session.rollback()
        logger.error(f"Error creando activo {symbol}: {e}")
        return f"Error creando activo: {e}", False
    finally:
        session.close()


def delete_asset(asset_id: int):
    """Elimina un activo por ID."""
    session = get_session()
    try:
        asset = session.get(Asset, asset_id)
        if not asset:
            return f"Activo {asset_id} no encontrado.", False

        session.delete(asset)
        session.commit()
        logger.info(f"Activo eliminado: {asset.symbol}")
        return f"Activo {asset.symbol} eliminado correctamente.", True
    except Exception as e:
        session.rollback()
        logger.error(f"Error eliminando activo {asset_id}: {e}")
        return f"Error eliminando activo: {e}", False
    finally:
        session.close()

def get_source_id_by_code(source_code: str):
    """Devuelve el ID de la fuente segun su code (por ejemplo 'YF' para Yahoo Finance)."""
    session = get_session()
    try:
        src = session.execute(select(PriceSource).where(PriceSource.code == source_code)).scalar_one_or_none()
        if not src:
            raise ValueError(f"Fuente de precios no encontrada: {source_code}")
        return src.id
    finally:
        session.close()