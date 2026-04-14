"""
APScheduler para la actualización diaria de precios.
Se ejecuta en el proceso principal de la app (Opción A acordada).
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import Config

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _daily_update_job() -> None:
    logger.info("Iniciando actualización diaria de precios (scheduled)")
    try:
        from app.services.price_service import update_all_active_assets
        summary = update_all_active_assets()
        logger.info(
            "Actualización diaria finalizada: %d/%d exitosos, %d errores",
            summary["success"],
            summary["total"],
            len(summary["errors"]),
        )
    except Exception as exc:
        logger.exception("Error crítico en la actualización diaria: %s", exc)


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return  # Ya iniciado

    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _daily_update_job,
        trigger=CronTrigger(
            hour=Config.SCHEDULER_HOUR,
            minute=Config.SCHEDULER_MINUTE,
        ),
        id="daily_price_update",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(
        "Scheduler iniciado. Actualización diaria a las %02d:%02d UTC",
        Config.SCHEDULER_HOUR,
        Config.SCHEDULER_MINUTE,
    )


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler detenido")
