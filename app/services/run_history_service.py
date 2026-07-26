"""Bitácora persistida de corridas pesadas (ver modelo RunHistory).

Best-effort y fail-open, MISMO patrón que run_lock_service: si la tabla no
existe todavía (deploy sin correr la migración 0096), se desactiva para todo
el proceso —latch `_unavailable`— en vez de reintentar en cada corrida
(martillaría la BD, y PostgreSQL loguea cada fallo como ERROR). El monitoreo
JAMÁS debe romper una corrida: toda función traga sus excepciones.
"""
import logging
import os
import socket
from datetime import datetime, timedelta

import sqlalchemy as sa

from app.database import get_session
from app.models.run_history import RunHistory

logger = logging.getLogger(__name__)

# Retención por antigüedad: prune_old() borra lo más viejo que esto. La tabla
# suma ~pocas filas por día, así que 180 días son unos cientos de filas.
RETENTION_DAYS = 180
_MAX_FIRST_ERROR = 500

_unavailable = False
_MISSING_TABLE_MARKERS = (
    "does not exist", "doesn't exist", "no such table", "undefinedtable",
)


def _looks_like_missing_table(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(m in msg for m in _MISSING_TABLE_MARKERS)


def _note_error(exc: Exception) -> None:
    """Latchea el servicio como no disponible SOLO ante 'tabla ausente'
    (pre-migración). Los errores transitorios no latchean: cada llamada
    reintenta. Loguea una única vez."""
    global _unavailable
    if not _unavailable and _looks_like_missing_table(exc):
        _unavailable = True
        logger.warning(
            "run_history: la tabla no existe (¿falta la migración 0096?). "
            "Bitácora de corridas DESACTIVADA en este proceso hasta reiniciar.")


def _utcnow() -> datetime:
    return datetime.utcnow()


def _host() -> str:
    try:
        return socket.gethostname()[:255]
    except Exception:
        return ""


def start_run(op: str, scope: str | None = None) -> int | None:
    """Abre una corrida (status='running') y devuelve su id, o None si la
    bitácora no está disponible. El id se pasa después a finish_run."""
    if _unavailable:
        return None
    s = get_session()
    try:
        row = RunHistory(
            op=(op or "")[:32], scope=(scope[:64] if scope else None),
            status="running", started_at=_utcnow(),
            pid=os.getpid(), host=_host())
        s.add(row)
        s.commit()
        return row.id
    except Exception as exc:
        s.rollback()
        _note_error(exc)
        return None


def finish_run(run_id: int | None, status: str, *, total: int | None = None,
               unit: str | None = None, ok: int | None = None,
               first_error: str | None = None) -> None:
    """Cierra la corrida `run_id` con su estado final. No-op si run_id es None
    (start_run no pudo abrirla) o la bitácora no está disponible."""
    if _unavailable or run_id is None:
        return
    s = get_session()
    try:
        s.execute(sa.update(RunHistory).where(RunHistory.id == run_id).values(
            status=status, finished_at=_utcnow(), total=total,
            unit=(unit[:16] if unit else None), ok=ok,
            first_error=(first_error[:_MAX_FIRST_ERROR] if first_error else None)))
        s.commit()
    except Exception as exc:
        s.rollback()
        _note_error(exc)


def abort_orphans() -> int:
    """Para el ARRANQUE: marca 'aborted' toda corrida que quedó 'running'.
    Un final limpio deja ok/error, así que un 'running' remanente es una
    corrida cuyo proceso murió a mitad. Supone 1 worker (mismo supuesto que
    run_lock). Devuelve cuántas marcó."""
    if _unavailable:
        return 0
    s = get_session()
    try:
        res = s.execute(sa.update(RunHistory)
                        .where(RunHistory.status == "running")
                        .values(status="aborted", finished_at=_utcnow()))
        s.commit()
        return res.rowcount or 0
    except Exception as exc:
        s.rollback()
        _note_error(exc)
        return 0


def prune_old(retention_days: int = RETENTION_DAYS) -> int:
    """Borra las corridas más viejas que `retention_days`. DELETE acotado
    sobre una tabla chica (no necesita el patrón de ventanas). Se llama al
    arranque, fuera del hot path. Devuelve cuántas borró."""
    if _unavailable:
        return 0
    s = get_session()
    cutoff = _utcnow() - timedelta(days=retention_days)
    try:
        res = s.execute(sa.delete(RunHistory).where(
            RunHistory.started_at < cutoff))
        s.commit()
        return res.rowcount or 0
    except Exception as exc:
        s.rollback()
        _note_error(exc)
        return 0


def get_recent(limit: int = 50) -> list[dict]:
    """Últimas corridas, más reciente primero — para la UI del Centro de
    Datos. Filas planas (sin objetos ORM) para no arrastrar la sesión."""
    if _unavailable:
        return []
    s = get_session()
    try:
        rows = s.execute(
            sa.select(RunHistory).order_by(RunHistory.started_at.desc())
            .limit(limit)).scalars().all()
        return [{
            "op": r.op, "scope": r.scope, "status": r.status,
            "started_at": r.started_at, "finished_at": r.finished_at,
            "total": r.total, "unit": r.unit, "ok": r.ok,
            "first_error": r.first_error, "host": r.host,
        } for r in rows]
    except Exception as exc:
        s.rollback()
        _note_error(exc)
        return []
