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


def get_status() -> dict:
    if _scheduler is None or not _scheduler.running:
        return {"running": False, "next_run": None, "hour": None, "minute": None}
    job = _scheduler.get_job("daily_price_update")
    next_run = str(job.next_run_time)[:19] if job and job.next_run_time else "—"
    trigger = job.trigger if job else None
    hour = minute = None
    if trigger:
        for field in trigger.fields:
            if field.name == "hour":
                hour = str(field)
            if field.name == "minute":
                minute = str(field)
    return {"running": True, "next_run": next_run, "hour": hour, "minute": minute}


def update_schedule(hour: int, minute: int) -> None:
    global _scheduler
    if _scheduler is None or not _scheduler.running:
        raise RuntimeError("El scheduler no está corriendo.")
    _scheduler.reschedule_job(
        "daily_price_update",
        trigger=CronTrigger(hour=hour, minute=minute),
    )
    logger.info("Horario del scheduler actualizado: %02d:%02d UTC", hour, minute)


def run_now() -> None:
    if _scheduler is None or not _scheduler.running:
        raise RuntimeError("El scheduler no está corriendo.")
    _scheduler.get_job("daily_price_update").modify(next_run_time=__import__("datetime").datetime.utcnow())
