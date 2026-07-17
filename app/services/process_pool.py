"""Harness del ProcessPool (fase 2 del plan de partición por activos):
creación del executor con contexto spawn. El initializer del hijo vive en
`process_child` (raíz del repo, fuera del paquete `app`) por razones de
timing de imports — ver ese módulo.

Separado de technical_service a propósito: el harness es reutilizable por
los otros candidatos ya anotados (verification_service, fundamental_service,
y señales paralelizadas por fechas si algún día compute_s pasara a dominar
sus timings).

Por qué SPAWN y no fork: el proceso padre (mod_wsgi en prod, el server de
Dash en dev) está lleno de threads (APScheduler, pools de callbacks,
SQLAlchemy) — fork heredaría locks tomados por otros threads (deadlock
clásico) y los sockets vivos del pool de conexiones (compartir un socket
MySQL/PG entre padre e hijo corrompe el protocolo). spawn arranca un
intérprete limpio que re-importa solo lo que necesita.

El executor es EFÍMERO (uno por corrida, cerrado al terminar): un pool
persistente sobreviviría a los reciclados de mod_wsgi como procesos
huérfanos escribiendo en la BD.

sys.executable bajo mod_wsgi puede apuntar a httpd (no a python), en cuyo
caso spawn lanzaría httpd como "intérprete" y el pool nacería roto — por
eso _use_process_pool (technical_service) degrada a threads cuando
spawn_executable_ok() es falso.
"""
import multiprocessing as _mp
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from process_child import child_initializer


def spawn_executable_ok() -> bool:
    """True si sys.executable parece un intérprete de Python. Bajo
    Apache+mod_wsgi embebido apunta a httpd: spawn no podría arrancar los
    hijos (lanzaría httpd -c '...') y el pool moriría entero. En ese caso
    el caller degrada a threads en vez de fallar la corrida en silencio."""
    try:
        name = Path(sys.executable).name.lower()
    except Exception:
        return False
    return name.startswith("python") or name.startswith("pypy")


def make_executor(n_procs: int, root: str, db_pool_size: int,
                  log_level: str) -> ProcessPoolExecutor:
    """Executor spawn efímero con el initializer de `process_child`. El
    caller lo usa como context manager y lo deja morir con la corrida."""
    return ProcessPoolExecutor(
        max_workers=n_procs,
        mp_context=_mp.get_context("spawn"),
        initializer=child_initializer,
        initargs=(root, db_pool_size, log_level),
    )
