# -*- coding: utf-8 -*-
"""
Servicio: price_updater.py
--------------------------------------------
Actualiza los precios historicos de los activos.
Cada activo tiene una unica fuente de precios asociada (por ejemplo, YAHOO).
Registra los errores de actualizacion en la tabla failed_updates a traves
del servicio services/failed_updates.py
"""

from datetime import date, timedelta
from sqlalchemy import select
from services.db import get_session
from models.db_models import Asset, HistoricalPrice, PriceSource
from services.failed_updates import register_failed_update
from core.logging_config import get_logger
from services.price_fetchers import yahoo_fetch_prices  # ejemplo de fetcher de precios

logger = get_logger()

# ==========================================================
# FUNCION PRINCIPAL
# ==========================================================
def update_all_assets(run_type: str = "manual"):
    """
    Recorre todos los activos y actualiza sus precios desde la fuente correspondiente.
    Cada error se registra en failed_updates sin detener el proceso completo.
    """
    session = get_session()
    assets = session.execute(select(Asset).join(PriceSource)).scalars().all()
    session.close()

    success = 0
    failures = 0

    for asset in assets:
        try:
            update_asset_prices(asset, run_type=run_type)
            success += 1
        except Exception as e:
            failures += 1
            logger.error(f"Fallo actualizando {asset.symbol}: {e}")
            register_failed_update(
                asset_id=asset.id,
                source_id=asset.source_id,
                error_message=str(e),
                run_type=run_type
            )

    logger.info(f"Actualizacion finalizada: {success} exitos, {failures} fallos.")
    return {"success": success, "failures": failures}

# ==========================================================
# FUNCION DE ACTUALIZACION INDIVIDUAL
# ==========================================================
def update_asset_prices(asset, run_type: str = "manual"):
    """
    Actualiza los precios historicos de un activo determinado.
    Si no hay precios previos, descarga el historial completo.
    Si hay precios previos, descarga desde el ultimo dia almacenado -1.
    """
    session = get_session()
    try:
        # Obtener el ultimo registro de precios
        last_price = session.execute(
            select(HistoricalPrice)
            .where(HistoricalPrice.asset_id == asset.id)
            .order_by(HistoricalPrice.trade_date.desc())
        ).scalars().first()

        if last_price:
            start_date = last_price.trade_date - timedelta(days=1)
        else:
            start_date = date(2000, 1, 1)

        logger.info(f"Actualizando {asset.symbol} ({asset.source.code}) desde {start_date}...")

        # Seleccion de fetcher segun la fuente
        if asset.source.code == "YAHOO":
            df = yahoo_fetch_prices(asset.source_symbol, start_date)
        else:
            raise ValueError(f"Fuente de precios '{asset.source.code}' no implementada")

        # Guardar o actualizar registros
        for _, row in df.iterrows():
            price = HistoricalPrice(
                asset_id=asset.id,
                source_id=asset.source_id,
                trade_date=row["Date"],
                open=row["Open"],
                high=row["High"],
                low=row["Low"],
                close=row["Close"],
                adj_close=row.get("Adj Close", row["Close"]),
                volume=row["Volume"]
            )
            # merge() permite upsert (update o insert)
            session.merge(price)

        session.commit()
        logger.info(f"Precios de {asset.symbol} actualizados correctamente.")

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
# FUNCION DE ACTUALIZACION MANUAL
# ==========================================================
def update_single_asset(symbol: str, run_type: str = "manual"):
    """
    Permite actualizar manualmente un activo por su simbolo.
    """
    session = get_session()
    try:
        asset = session.execute(select(Asset).where(Asset.symbol == symbol)).scalar_one_or_none()
        if not asset:
            raise ValueError(f"Activo '{symbol}' no encontrado en la base de datos")

        update_asset_prices(asset, run_type=run_type)
        logger.info(f"Actualizacion manual finalizada para {symbol}.")
        return True

    except Exception as e:
        logger.error(f"Error actualizando manualmente {symbol}: {e}")
        register_failed_update(
            asset_id=asset.id if asset else None,
            source_id=asset.source_id if asset else None,
            error_message=str(e),
            run_type=run_type
        )
        return False
    finally:
        session.close()