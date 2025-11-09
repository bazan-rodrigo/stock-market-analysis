# services/price_updater.py
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy import select, func
from services import price_fetchers, failed_updates
from services.db import get_session
from models.db_models import Asset, UpdateRun, PriceSource, HistoricalPrice
from core.logging_config import get_logger
from datetime import datetime, timedelta
import pandas as pd
import time
import re

logger = get_logger(__name__)


logger = get_logger(__name__)

def update_all_assets(run_type="manual", max_workers=6, min_workers=2, backoff_time=15):
    """
    Actualiza los precios de todos los activos registrados, 
    ajustando dinámicamente el número de hilos según errores de red.

    Args:
        run_type (str): tipo de ejecución ("manual" o "scheduled")
        max_workers (int): cantidad máxima de threads simultáneos
        min_workers (int): cantidad mínima de threads permitidos
        backoff_time (int): segundos de espera al reducir la concurrencia
    Returns:
        int: cantidad de activos actualizados exitosamente
    """
    session = get_session()
    assets = session.query(Asset).all()
    session.close()

    total = len(assets)
    updated = 0
    start_time = datetime.now()
    current_workers = max_workers

    logger.info(f"🚀 Iniciando actualización de {total} activos ({run_type}) con {current_workers} hilos...")

    # Lista de símbolos pendientes
    pending_assets = [a.symbol for a in assets]

    while pending_assets and current_workers >= min_workers:
        logger.info(f"➡️ Ejecutando batch con {len(pending_assets)} activos ({current_workers} hilos)")
        failed_assets = []
        errors_429 = 0

        with ThreadPoolExecutor(max_workers=current_workers) as executor:
            futures = {executor.submit(update_single_asset, symbol, run_type): symbol for symbol in pending_assets}
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    result = future.result()
                    if result:
                        updated += 1
                        logger.info(f"✅ {symbol} actualizado correctamente.")
                    else:
                        logger.warning(f"⚠️ {symbol} no devolvió datos válidos.")
                except Exception as e:
                    msg = str(e)
                    failed_assets.append(symbol)
                    logger.error(f"❌ Error en {symbol}: {msg}")

                    # Detectar throttling o demasiadas peticiones
                    if re.search(r"429|Too Many Requests|timeout|temporarily unavailable", msg, re.I):
                        errors_429 += 1

        # Si hay muchos errores 429 → reducir concurrencia
        if errors_429 > len(pending_assets) * 0.1:  # más del 10% con limitaciones
            new_workers = max(current_workers - 2, min_workers)
            if new_workers < current_workers:
                logger.warning(
                    f"⚠️ Detectado throttling (HTTP 429). Reduciendo concurrencia de {current_workers} → {new_workers} y esperando {backoff_time}s..."
                )
                current_workers = new_workers
                time.sleep(backoff_time)
        else:
            # Si no hubo throttling, se puede terminar
            break

        # Reintentar los fallidos con menos hilos
        pending_assets = failed_assets

    duration = (datetime.now() - start_time).total_seconds()
    logger.info(f"🏁 Finalizada actualización: {updated}/{total} activos en {duration:.1f}s (concurrencia final {current_workers})")

    _register_update_run(start_time, datetime.now(), total, updated, run_type)
    return updated


# ==========================================================
# REGISTRAR EJECUCIÓN
# ==========================================================
def _register_update_run(start_time, end_time, total, updated, run_type):
    """Guarda registro de la ejecución en la tabla UpdateRun."""
    session = get_session()
    try:
        run = UpdateRun(
            start_time=start_time,
            end_time=end_time,
            total_assets=total,
            updated_assets=updated,
            run_type=run_type
        )
        session.add(run)
        session.commit()
    except Exception as e:
        logger.error(f"Error guardando registro de actualización: {e}")
        session.rollback()
    finally:
        session.close()


def update_single_asset(symbol: str, run_type="manual") -> bool:
    """
    Actualiza los precios de un activo específico.
    
    Args:
        symbol (str): símbolo del activo (ej: "AAPL").
        run_type (str): tipo de ejecución ("manual" o "scheduled").
    Returns:
        bool: True si se actualizó correctamente, False si hubo error.
    """
    session = get_session()
    try:
        # Buscar activo
        asset = session.execute(select(Asset).where(Asset.symbol == symbol)).scalar_one_or_none()
        if not asset:
            raise ValueError(f"Activo '{symbol}' no encontrado en base de datos.")

        source = session.get(PriceSource, asset.source_id)
        if not source or not source.is_active:
            raise ValueError(f"Fuente inactiva o no encontrada para {symbol}.")

        # Determinar fecha de inicio
        last_price = session.execute(
            select(HistoricalPrice.date)
            .where(HistoricalPrice.asset_id == asset.id)
            .order_by(HistoricalPrice.date.desc())
        ).scalars().first()

        start_date = last_price + timedelta(days=1) if last_price else datetime.utcnow() - timedelta(days=180)
        start_date = start_date.date()

        logger.info(f"Actualizando precios de {symbol} desde {start_date} (fuente: {source.code})")

        # Descargar precios
        df = price_fetchers.yahoo_fetch_prices(asset.source_symbol or symbol, start_date)
        if df.empty:
            logger.warning(f"Sin nuevos datos para {symbol}")
            return True  # no error, pero nada que actualizar

        # Normalizar columnas
        df.rename(columns={"Adj Close": "Adj_Close"}, inplace=True)
        expected_cols = {"Date", "Open", "High", "Low", "Close", "Adj_Close", "Volume"}
        if not expected_cols.issubset(df.columns):
            raise ValueError(f"Datos incompletos para {symbol}. Columnas: {df.columns}")

        inserted = 0
        for _, row in df.iterrows():
            # Evitar duplicados
            exists = session.execute(
                select(HistoricalPrice.id).where(
                    (HistoricalPrice.asset_id == asset.id)
                    & (HistoricalPrice.date == row["Date"])
                )
            ).first()
            if exists:
                continue

            hp = HistoricalPrice(
                asset_id=asset.id,
                source_id=source.id,
                date=row["Date"],
                open=row["Open"],
                high=row["High"],
                low=row["Low"],
                close=row["Close"],
                adj_close=row.get("Adj_Close"),
                volume=int(row["Volume"]) if not pd.isna(row["Volume"]) else None,
                recorded_at=datetime.utcnow(),
            )
            session.add(hp)
            inserted += 1

        session.commit()
        logger.info(f"{symbol}: {inserted} precios agregados correctamente.")
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Error actualizando {symbol}: {e}")
        # Registrar fallo
        try:
            failed_updates.log_failed_update(
                asset_id=asset.id if "asset" in locals() and asset else None,
                source_id=source.id if "source" in locals() and source else None,
                msg=str(e),
                run_type=run_type
            )
        except Exception as log_err:
            logger.error(f"No se pudo registrar el fallo para {symbol}: {log_err}")
        return False

    finally:
        session.close()


# ==========================================================
# OBTENER FECHA DE ÚLTIMA ACTUALIZACIÓN
# ==========================================================

def get_last_update_date() -> datetime | None:
    """
    Retorna la fecha/hora de la última actualización registrada.
    Prioriza el campo 'end_time' de la tabla UpdateRun.
    Si no existen registros, busca la última fecha de HistoricalPrice.
    """
    session = get_session()
    try:
        # Primero buscar la última ejecución completada
        last_run = session.execute(
            select(UpdateRun.end_time)
            .where(UpdateRun.end_time.isnot(None))
            .order_by(UpdateRun.end_time.desc())
        ).scalars().first()

        if last_run:
            return last_run

        # Si no hay registros en UpdateRun, usar el último precio cargado
        last_price = session.execute(
            select(func.max(HistoricalPrice.recorded_at))
        ).scalar()

        return last_price

    except Exception as e:
        logger.error(f"Error obteniendo fecha de última actualización: {e}")
        return None

    finally:
        session.close()
