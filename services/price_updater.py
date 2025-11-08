# services/price_updater.py
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy import select, func
from services.db import get_session
from models.db_models import Asset, UpdateRun
from core.logging_config import get_logger
from datetime import datetime
import time
import re

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