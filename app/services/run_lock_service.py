"""Lock de corrida persistido con heartbeat (ver modelo RunLock).

Cierra tres agujeros de la exclusión mutua en memoria del Centro de Datos
(_any_running en data_center_callbacks):
  1. Doble corrida tras un reciclado del proceso WSGI: los flags en memoria
     renacen en False mientras hijos huérfanos del ProcessPool siguen
     escribiendo — dos corridas concurrentes contra las mismas tablas
     (deadlocks garantizados). Con el lock persistido, la segunda corrida ve
     el lock (heartbeat todavía fresco si el proceso vive; si murió de
     verdad, recién tras el umbral de obsolescencia se puede reclamar).
  2. La carrera check-then-act de _any_running (dos requests concurrentes):
     acá la toma del lock es atómica por la PK (INSERT que falla si existe).
  3. La UI distingue 'abortada por reciclado' (heartbeat viejo) de
     'corriendo' (heartbeat fresco) y puede destrabar el botón.

Atomicidad portable MySQL/PostgreSQL/sqlite sin SQL de motor: se limpia el
lock muerto con un DELETE condicional (heartbeat < cutoff) y se toma con un
INSERT — el INSERT es atómico por la PK, así que ante dos tomadores
concurrentes exactamente uno gana y el otro recibe IntegrityError.
"""
import logging
import os
import secrets
import socket
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from app.database import Session, get_session
from app.models.run_lock import RunLock

logger = logging.getLogger(__name__)

# Sentinel de fail-open: guarded_acquire lo devuelve cuando el subsistema del
# lock no está disponible (tabla ausente pre-migración, BD caída). El caller
# procede (fail-open) y beat/release con este token son no-ops (no matchea
# ninguna fila).
NO_LOCK = "__no_lock__"

# Cada cuánto late el heartbeat mientras corre una operación, y a partir de
# qué antigüedad del heartbeat un lock se considera MUERTO (proceso caído) y
# reclamable. 4 latidos perdidos: tolerante a pausas de GIL/GC sin dejar el
# botón trabado eternamente tras un reciclado.
HEARTBEAT_INTERVAL = 30
STALE_SECONDS = 120

# Op única del dominio de escritura masiva: el Centro de Datos, los botones
# de precios y la corrida nocturna del scheduler son mutuamente excluyentes
# (una sola corrida pesada a la vez), así que comparten este lock.
HEAVY_WRITE = "heavy_write"

# Latch: si la tabla run_lock NO existe (deploy sin correr la migración 0076),
# se desactiva el lock persistido para TODO el proceso en vez de reintentar en
# cada acquire/heartbeat (una corrida entera martillaría la BD con queries a
# una tabla inexistente, que PostgreSQL además loguea como ERROR una por una).
# Solo latchea ante "tabla ausente" (no ante errores transitorios de conexión,
# que sí conviene reintentar). Se resetea al reiniciar el proceso — el flujo
# normal de deploy corre la migración y reinicia, así que la tabla aparece con
# un proceso nuevo.
_unavailable = False

_MISSING_TABLE_MARKERS = (
    "does not exist", "doesn't exist", "no such table", "undefinedtable",
    "1146",  # MySQL: Table doesn't exist
)


def _looks_like_missing_table(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(m in msg for m in _MISSING_TABLE_MARKERS)


def _note_error(exc: Exception) -> None:
    """Latchea el lock como no disponible SOLO si el error es 'tabla ausente'
    (pre-migración). Loguea una única vez. Los errores transitorios (conexión,
    lock timeout) no latchean: cada llamada los reintenta."""
    global _unavailable
    if not _unavailable and _looks_like_missing_table(exc):
        _unavailable = True
        logger.warning(
            "run_lock: la tabla no existe (¿falta correr la migración 0076?). "
            "Lock persistido DESACTIVADO en este proceso hasta reiniciar; el "
            "Centro de Datos usa el guard en memoria de siempre.")


def _utcnow() -> datetime:
    return datetime.utcnow()


def _host() -> str:
    try:
        return socket.gethostname()[:255]
    except Exception:
        return ""


def acquire(op: str, stale_seconds: int = STALE_SECONDS) -> str | None:
    """Intenta tomar el lock de `op`. Devuelve un TOKEN de propiedad único
    si lo tomó, o None si ya hay una corrida VIVA (heartbeat fresco). Limpia
    primero un lock muerto (heartbeat viejo) para poder reclamarlo. El token
    identifica ESTA adquisición: beat/release solo operan si coincide, así un
    stale-reclaim (mismo pid, otro token) no deja que una corrida vieja pise
    el lock de la que reclamó."""
    s = get_session()
    now = _utcnow()
    cutoff = now - timedelta(seconds=stale_seconds)
    token = secrets.token_hex(8)
    # 1. Limpiar un lock muerto (proceso caído): DELETE condicional atómico.
    s.execute(sa.delete(RunLock).where(
        RunLock.op == op, RunLock.heartbeat < cutoff))
    s.commit()
    # 2. Tomarlo: el INSERT es atómico por la PK — si otro tomador ganó (o
    #    hay una corrida viva), este falla con IntegrityError.
    s.add(RunLock(op=op, token=token, pid=os.getpid(), host=_host(),
                  started_at=now, heartbeat=now))
    try:
        s.commit()
        return token
    except IntegrityError:
        s.rollback()
        return None


def guarded_acquire(op: str, stale_seconds: int = STALE_SECONDS) -> str | None:
    """acquire() a prueba de fallas del subsistema. Devuelve el TOKEN si se
    tomó, el sentinel NO_LOCK si el lock no está disponible (tabla ausente
    antes de la migración 0076, BD caída → fail-open, se procede sin lock
    real), o None SOLO cuando otro tiene un lock VIVO (el caller debe
    rechazar). Fail-open mantiene la feature puramente aditiva: sin la tabla,
    el Centro de Datos funciona igual que antes."""
    if _unavailable:
        return NO_LOCK
    try:
        return acquire(op, stale_seconds)
    except Exception as exc:
        _note_error(exc)
        if not _unavailable:  # error transitorio (no 'tabla ausente')
            logger.warning("run_lock no disponible; sigo con el guard en "
                           "memoria", exc_info=True)
        # dejar la sesión del thread limpia (el DELETE/INSERT fallido pudo
        # envenenar la transacción) para no arrastrar el error al caller
        try:
            get_session().rollback()
        except Exception:
            pass
        return NO_LOCK


def beat(op: str, token: str) -> bool:
    """Actualiza el heartbeat del lock de `op` SOLO si el token coincide
    (sigue siendo NUESTRA adquisición). False si lo perdimos (otro lo
    reclamó por muerte aparente). Cualquier error de BD se trata como
    transitorio (incluye tabla ausente pre-migración): no marca perdido ni
    escapa a spamear el log del beat thread."""
    if _unavailable:
        return True
    s = get_session()
    try:
        res = s.execute(sa.update(RunLock)
                        .where(RunLock.op == op, RunLock.token == token)
                        .values(heartbeat=_utcnow()))
        s.commit()
        return res.rowcount == 1
    except Exception as exc:
        s.rollback()
        _note_error(exc)
        return True


def release(op: str, token: str) -> None:
    """Libera el lock de `op` si es NUESTRA adquisición (token). Descarta
    primero la sesión del thread —que pudo quedar envenenada por la corrida
    que acaba de fallar— para que el DELETE opere sobre una sesión limpia:
    de lo contrario un PendingRollbackError abortaría el DELETE y el lock
    quedaría trabado hasta el stale-reclaim."""
    if _unavailable:
        return
    Session.remove()
    s = get_session()
    try:
        s.execute(sa.delete(RunLock).where(
            RunLock.op == op, RunLock.token == token))
        s.commit()
    except Exception as exc:
        s.rollback()
        _note_error(exc)
        if not _unavailable:
            logger.warning("No se pudo liberar el lock de corrida %s", op,
                           exc_info=True)


def status(op: str, stale_seconds: int = STALE_SECONDS) -> dict | None:
    """Estado del lock de `op` para la UI, o None si no hay corrida
    registrada. `stale` = el heartbeat quedó viejo (corrida abortada por
    reciclado): el botón puede destrabarse aunque la fila siga."""
    if _unavailable:
        return None
    s = get_session()
    try:
        row = s.get(RunLock, op)
    except Exception as exc:
        s.rollback()
        _note_error(exc)
        return None
    if row is None:
        return None
    age = (_utcnow() - row.heartbeat).total_seconds()
    return {
        "op": op,
        "pid": row.pid,
        "host": row.host,
        "started_at": row.started_at,
        "heartbeat": row.heartbeat,
        "age_seconds": age,
        "stale": age > stale_seconds,
    }


def is_running(op: str, stale_seconds: int = STALE_SECONDS) -> bool:
    """True si hay una corrida VIVA de `op` (lock con heartbeat fresco).
    Un lock muerto (heartbeat viejo) NO cuenta como corriendo."""
    st = status(op, stale_seconds)
    return st is not None and not st["stale"]


def clear_stale(stale_seconds: int = STALE_SECONDS) -> int:
    """Borra todos los locks muertos (heartbeat viejo). Para el arranque de
    la app: limpia lo que dejó un proceso anterior que murió a mitad de
    corrida. Devuelve cuántos borró."""
    if _unavailable:
        return 0
    s = get_session()
    cutoff = _utcnow() - timedelta(seconds=stale_seconds)
    try:
        res = s.execute(sa.delete(RunLock).where(RunLock.heartbeat < cutoff))
        s.commit()
        return res.rowcount or 0
    except Exception as exc:
        s.rollback()
        _note_error(exc)
        return 0


@contextmanager
def heartbeating(op: str, token: str, interval: int = HEARTBEAT_INTERVAL):
    """Context manager para envolver una corrida: late el heartbeat de ESTA
    adquisición (token) en un thread daemon mientras dura y LIBERA el lock al
    salir (éxito o excepción). Asume que el caller YA tomó el lock con
    acquire()/guarded_acquire() y pasa su token. El thread cierra su propia
    sesión scoped en cada latido (no comparte sesión con la corrida).

    th.start() va DENTRO del try/finally: si falla (agotamiento de threads),
    el finally igual libera el lock en vez de filtrarlo hasta el
    stale-reclaim."""
    stop = threading.Event()

    def _loop():
        while not stop.wait(interval):
            try:
                beat(op, token)
            except Exception:
                logger.warning("Heartbeat de %s falló", op, exc_info=True)
            finally:
                Session.remove()

    th = threading.Thread(target=_loop, name=f"run-lock-beat-{op}", daemon=True)
    try:
        th.start()
        yield
    finally:
        stop.set()
        try:
            th.join(timeout=interval + 5)
        except Exception:
            pass
        release(op, token)
