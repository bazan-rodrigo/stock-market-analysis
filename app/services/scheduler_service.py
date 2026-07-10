"""
APScheduler para la actualización diaria de precios y la verificación
semanal de datos (asset_verification_flag). Un único proceso de
BackgroundScheduler con dos jobs independientes: el diario se habilita
junto con "Iniciar" (como siempre), el semanal tiene su propio toggle
en scheduler_config (weekly_verify_enabled) y nace deshabilitado.
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

_WEEKLY_JOB_ID = "weekly_verification"


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


def _save_config(**fields) -> None:
    from app.database import get_session
    from app.models.scheduler_config import SchedulerConfig
    s = get_session()
    cfg = s.query(SchedulerConfig).filter(SchedulerConfig.id == 1).first()
    if cfg is None:
        cfg = SchedulerConfig(id=1, enabled=False, hour=18, minute=0)
        s.add(cfg)
    for key, value in fields.items():
        if value is not None:
            setattr(cfg, key, value)
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
        logger.info(
            "Verificación semanal finalizada: %d activos verificados, "
            "%d marcados, %d limpiados, %.1fs",
            result["checked_assets"], result["flagged_assets"],
            result["cleared_assets"], result["seconds"],
        )
    except Exception as exc:
        logger.exception("Error en la verificación semanal: %s", exc)
    finally:
        from app.database import Session
        Session.remove()


# ── Control del scheduler (job diario) ────────────────────────────────────────

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
        if cfg.weekly_verify_enabled:
            _scheduler.add_job(
                _weekly_verification_job,
                trigger=CronTrigger(day_of_week=cfg.weekly_verify_day,
                                    hour=cfg.weekly_verify_hour,
                                    minute=cfg.weekly_verify_minute),
                id=_WEEKLY_JOB_ID,
                replace_existing=True,
            )
        _scheduler.start()
    _save_config(enabled=True)
    logger.info("Scheduler iniciado. Actualización diaria a las %02d:%02d UTC",
               cfg.hour, cfg.minute)


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


# ── Control de la verificación semanal (job independiente) ───────────────────
# No comparte el habilitado/deshabilitado del job diario: "Iniciar"/"Detener"
# arriba prende/apaga el proceso de APScheduler en sí (infraestructura
# compartida), pero este job además necesita su PROPIO toggle — nace
# deshabilitado (weekly_verify_enabled=False por default) y el usuario lo
# habilita explícitamente cuando quiere.

def enable_weekly_verification() -> None:
    cfg = _get_config()
    _save_config(weekly_verify_enabled=True)
    with _scheduler_lock:
        if _scheduler and _scheduler.running:
            _scheduler.add_job(
                _weekly_verification_job,
                trigger=CronTrigger(day_of_week=cfg.weekly_verify_day,
                                    hour=cfg.weekly_verify_hour,
                                    minute=cfg.weekly_verify_minute),
                id=_WEEKLY_JOB_ID,
                replace_existing=True,
            )
    logger.info("Verificación semanal habilitada")


def disable_weekly_verification() -> None:
    _save_config(weekly_verify_enabled=False)
    with _scheduler_lock:
        if _scheduler and _scheduler.running and _scheduler.get_job(_WEEKLY_JOB_ID):
            _scheduler.remove_job(_WEEKLY_JOB_ID)
    logger.info("Verificación semanal deshabilitada")


def update_weekly_verification_schedule(day: str, hour: int, minute: int) -> None:
    _save_config(weekly_verify_day=day, weekly_verify_hour=hour, weekly_verify_minute=minute)
    with _scheduler_lock:
        if _scheduler and _scheduler.running and _scheduler.get_job(_WEEKLY_JOB_ID):
            _scheduler.reschedule_job(
                _WEEKLY_JOB_ID,
                trigger=CronTrigger(day_of_week=day, hour=hour, minute=minute),
            )
    logger.info("Horario de verificación semanal actualizado: %s %02d:%02d UTC",
               day, hour, minute)


def run_weekly_verification_now() -> None:
    with _scheduler_lock:
        job = _scheduler.get_job(_WEEKLY_JOB_ID) if _scheduler and _scheduler.running else None
    if job is None:
        raise RuntimeError("La verificación semanal no está habilitada/corriendo.")
    import datetime
    job.modify(next_run_time=datetime.datetime.utcnow())


def get_weekly_verification_status() -> dict:
    cfg = _get_config()
    with _scheduler_lock:
        job = _scheduler.get_job(_WEEKLY_JOB_ID) if _scheduler and _scheduler.running else None
        next_run = str(job.next_run_time)[:19] if job and job.next_run_time else "—"
    return {
        "enabled": cfg.weekly_verify_enabled,
        "running": job is not None,
        "next_run": next_run,
        "day": cfg.weekly_verify_day,
        "hour": cfg.weekly_verify_hour,
        "minute": cfg.weekly_verify_minute,
    }


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
