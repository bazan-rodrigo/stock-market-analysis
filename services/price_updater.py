# -*- coding: utf-8 -*-
"""
Servicio: price_updater.py
--------------------------------------------
Actualiza los precios históricos de los activos usando los adaptadores de fuentes.
Cada activo tiene una única fuente de precios asociada (ej. YAHOO, ALPHAVANTAGE).
Los errores se registran en la tabla failed_updates a través del servicio correspondiente.
"""

from datetime import date, timedelta
from sqlalchemy import select
from services.db import get_session
from models.db_models import Asset, HistoricalPrice
from services.failed_updates import register_failed_update
from core.logging_config import get_logger
from services.sources.factory import get_source_adapter

logger = get_logger(__name__)


# ==========================================================
# FUNCIÓN PRINCIPAL: Actualizar todos los activos
# ==========================================================
def update_all_assets(run_type: str = "manual"):
    """
    Recorre todos los activos y actualiza sus precios desde la fuente correspondiente.
    Cada error se registra en failed_updates sin detener el proceso completo.
    """
    session = get_session()
    assets = session.execute(select(Asset)).scalars().all()
    session.close()

    success, failures = 0, 0
    logger.info(f"=== INICIO actualización de precios ({len(assets)} activos, modo={run_type}) ===")

    for asset in assets:
        try:
            update_asset_prices(asset, run_type=run_type)
            success += 1
        except Exception as e:
            failures += 1
            logger.error(f"❌ Fallo actualizando {asset.symbol}: {e}")
            register_failed_update(
                asset_id=asset.id,
                source_id=asset.source_id,
                error_message=str(e),
                run_type=run_type
            )

    logger.info(f"=== FIN actualización: {success} éxitos, {failures} fallos ===")
    return {"success": success, "failures": failures}


# ==========================================================
# FUNCIÓN: Actualizar precios de un activo
# ==========================================================
def update_asset_prices(asset, run_type: str = "manual"):
    """
    Actualiza los precios históricos de un activo determinado.
    Si no hay precios previos, descarga el historial completo.
    Si hay precios previos, descarga desde el último día almacenado -1.
    """
    session = get_session()
    try:
        # Último registro en la base
        last_price = session.execute(
            select(HistoricalPrice)
            .where(HistoricalPrice.asset_id == asset.id)
            .order_by(HistoricalPrice.trade_date.desc())
        ).scalars().first()

    # Si ya existe data previa, traer solo desde la última fecha; si no, pedir TODO el histórico
    if last_price:
        start_date = last_price.trade_date - timedelta(days=1)
        end_date = date.today()
        logger.info(f"🔄 Actualizando {asset.symbol} ({asset.source.code}) desde {start_date} hasta {end_date}...")
        df = adapter.download_daily_prices(asset.source_symbol, start=start_date, end=end_date)
    else:
        logger.info(f"🔄 Descargando histórico completo de {asset.symbol} ({asset.source.code})...")
        df = adapter.download_daily_prices(asset.source_symbol)  # sin fechas → todo el histórico

        if df.empty:
            raise ValueError(f"No se obtuvieron precios para {asset.symbol}")

        # Insertar precios nuevos o actualizar existentes
        batch = []
        for _, row in df.iterrows():
            batch.append(HistoricalPrice(
                asset_id=asset.id,
                source_id=asset.source_id,
                trade_date=row["trade_date"],
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                adj_close=row.get("adj_close", row["close"]),
                volume=row.get("volume", 0),
            ))

        session.bulk_save_objects(batch)
        session.commit()
        logger.info(f"✅ {asset.symbol}: {len(batch)} precios guardados correctamente.")

    except Exception as e:
        session.rollback()
        logger.error(f"Error actualizando precios de {asset.symbol}: {e}")
        register_failed_update(
            asset_id=asset.id,
            source_id=asset.source_id,
            error_message=str(e),
            run_type=run_type
        )
        raise
    finally:
        session.close()


# ==========================================================
# FUNCIÓN: Actualización manual por símbolo
# ==========================================================
def update_single_asset(symbol: str, run_type: str = "manual"):
    """
    Permite actualizar manualmente un activo por su símbolo.
    """
    session = get_session()
    try:
        asset = session.execute(select(Asset).where(Asset.symbol == symbol)).scalar_one_or_none()
        if not asset:
            raise ValueError(f"Activo '{symbol}' no encontrado en la base de datos")

        update_asset_prices(asset, run_type=run_type)
        logger.info(f"Actualización manual finalizada para {symbol}.")
        return True

    except Exception as e:
        logger.error(f"Error actualizando