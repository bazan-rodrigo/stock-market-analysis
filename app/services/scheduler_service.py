"""
APScheduler para la actualización diaria de precios.
Configuración (enabled, hour, minute) persistida en la tabla scheduler_config.
"""
import logging
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
_scheduler_lock = threading.Lock()

# True mientras corre la actualización diaria programada (lo consulta el
# Centro de Datos para no lanzar operaciones ni COUNTs pesados en paralelo)
_daily_running = False


def is_daily_update_running() -> bool:
    return _daily_running


# ── Acceso a configuración en DB ──────────────────────────────────────────────

def _get_config():
    from app.database import get_session
    from app.models.scheduler_config import SchedulerConfig
    s = get_session()
    cfg = s.query(SchedulerConfig).filter(SchedulerConfig.id == 1).first()
    if cfg is None:
        cfg = SchedulerConfig(id=1, enabled=False, hour=18, minute=0)
        s.add(cfg)
        s.commit()
    return cfg


def _save_config(enabled: bool | None = None, hour: int | None = None, minute: int | None = None) -> None:
    from app.database import get_session
    from app.models.scheduler_config import SchedulerConfig
    s = get_session()
    cfg = s.query(SchedulerConfig).filter(SchedulerConfig.id == 1).first()
    if cfg is None:
        cfg = SchedulerConfig(id=1, enabled=False, hour=18, minute=0)
        s.add(cfg)
    if enabled is not None:
        cfg.enabled = enabled
    if hour is not None:
        cfg.hour = hour
    if minute is not None:
        cfg.minute = minute
    s.commit()


# ── Job ───────────────────────────────────────────────────────────────────────

def _daily_update_job() -> None:
    global _daily_running
    _daily_running = True
    logger.info("Iniciando actualización diaria de precios (scheduled)")
    try:
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
            return

        # ── Pipeline de señales/estrategias ─────────────────────────────────
        try:
            from app.services import indicator_service
            indicator_service.run_daily()
        except Exception as exc:
            logger.exception("Error en indicator_service.run_daily: %s", exc)

        try:
            from app.services import signal_service
            result = signal_service.run_daily()
            logger.info("signal_service: %s", result)
        except Exception as exc:
            logger.exception("Error en signal_service.run_daily: %s", exc)

        try:
            from app.services import strategy_service
            result = strategy_service.run_daily()
            logger.info("strategy_service: %s", result)
        except Exception as exc:
            logger.exception("Error en strategy_service.run_daily: %s", exc)
    finally:
        _daily_running = False
        # El thread del scheduler se reutiliza entre corridas: liberar la
        # sesión scoped para no retener conexión ni objetos entre días.
        from app.database import Session
        Session.remove()


def _weekly_verification_job() -> None:
    """Recalcula desde cero (en memoria, solo lectura sobre precios/
    trimestrales) todos los indicadores y ratios de TODOS los activos y
    guarda en asset_verification_flag los que difieren de lo guardado —
    fuente de los ⚠️ en los selectores de activo de Análisis de Activo,
    RRG, Evolución, Pares y Retornos (ver verification_service.
    get_flagged_asset_ids). Semanal porque a diferencia de la actualización
    diaria de precios, no hace falta que estas marcas estén al minuto:
    alcanza con no quedar desactualizadas por más de unos días."""
    logger.info("Iniciando verificación semanal de datos (scheduled)")
    try:
        from app.services.verification_service import run_full_verification_and_store
        result = run_full_verification_and_store()
        logger.info("Verificación semanal finalizada: %s", result)
    except Exception as exc:
        logger.exception("Error en la verificación semanal: %s", exc)
    finally:
        from app.database import Session
        Session.remove()


# ── Control del scheduler ─────────────────────────────────────────────────────

def start_scheduler() -> None:
    global _scheduler
    with _scheduler_lock:
        if _scheduler is not None and _scheduler.running:
            return
        cfg = _get_config()
        _scheduler = BackgroundScheduler(timezone="UTC")
        _scheduler.add_job(
            _daily_update_job,
            trigger=CronTrigger(hour=cfg.hour, minute=cfg.minute),
            id="daily_price_update",
            replace_existing=True,
        )
        # Mismo proceso único de APScheduler, un segundo job con su propio
        # horario fijo (domingo temprano, lejos de la actualización diaria)
        # — no tiene configuración propia en scheduler_config, se prende y
        # apaga junto con el scheduler general.
        _scheduler.add_job(
            _weekly_verification_job,
            trigger=CronTrigger(day_of_week="sun", hour=3, minute=0),
            id="weekly_verification",
            replace_existing=True,
        )
        _scheduler.start()
    _save_config(enabled=True)
    logger.info(
        "Scheduler iniciado. Actualización diaria a las %02d:%02d UTC, "
        "verificación semanal domingos 03:00 UTC",
        cfg.hour, cfg.minute,
    )


def shutdown_scheduler() -> None:
    global _scheduler
    with _scheduler_lock:
        if _scheduler and _scheduler.running:
            _scheduler.shutdown(wait=False)
            _scheduler = None
    _save_config(enabled=False)
    logger.info("Scheduler detenido")


def get_status() -> dict:
    cfg = _get_config()
    with _scheduler_lock:
        running = _scheduler is not None and _scheduler.running
        if not running:
            return {
                "running": False,
                "next_run": None,
                "hour": cfg.hour,
                "minute": cfg.minute,
            }
        job = _scheduler.get_job("daily_price_update")
        next_run = str(job.next_run_time)[:19] if job and job.next_run_time else "—"
    return {
        "running": True,
        "next_run": next_run,
        "hour": cfg.hour,
        "minute": cfg.minute,
    }


def update_schedule(hour: int, minute: int) -> None:
    _save_config(hour=hour, minute=minute)
    with _scheduler_lock:
        if _scheduler and _scheduler.running:
            _scheduler.reschedule_job(
                "daily_price_update",
                trigger=CronTrigger(hour=hour, minute=minute),
            )
    logger.info("Horario del scheduler actualizado: %02d:%02d UTC", hour, minute)


def run_now() -> None:
    if _scheduler is None or not _scheduler.running:
        raise RuntimeError("El scheduler no está corriendo.")
    import datetime
    _scheduler.get_job("daily_price_update").modify(
        next_run_time=datetime.datetime.utcnow()
    )


def start_if_enabled() -> None:
    """Llamado al arrancar la app: inicia el scheduler solo si estaba habilitado en DB."""
    try:
        cfg = _get_config()
        if cfg.enabled:
            start_scheduler()
        else:
            logger.info("Scheduler deshabilitado en DB, no se inicia automáticamente")
    except Exception as exc:
        logger.warning("No se pudo verificar estado del scheduler: %s", exc)
