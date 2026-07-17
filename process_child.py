"""Initializer del proceso hijo del ProcessPool de indicadores.

Vive en la RAÍZ del repo, FUERA del paquete `app`, a propósito: el
bootstrap de un proceso spawn des-picklea la referencia al initializer
ANTES de ejecutarlo, y ese unpickle importa el módulo que lo contiene. Si
estuviera en `app.*`, el import arrastraría `app/__init__.py` →
`app.config`, evaluando la clase `Config` (que lee os.environ) ANTES de que
el initializer alcance a setear DB_POOL_SIZE/DB_MAX_OVERFLOW — y el hijo
nacería con el pool del padre (30+20) en vez del pool chico configurado.
Al estar acá, su unpickle no importa nada de `app`: el initializer setea el
entorno y recién la PRIMERA TAREA importa `app.database` con Config leyendo
el entorno ya correcto.

(El import de dash/pandas vía app igual ocurre al importar la primera tarea
—app.services.technical_service—; es inevitable y se amortiza porque el
executor reusa cada hijo entre lotes. Lo que este módulo garantiza es solo
el timing del entorno del pool de BD.)
"""
import os
import sys


def child_initializer(root: str, db_pool_size: int, log_level: str) -> None:
    """Corre UNA vez por proceso hijo, antes de la primera tarea."""
    # 'app' no está instalado como paquete: asegurar la raíz del repo en
    # sys.path (bajo mod_wsgi el cwd del padre puede ser '/').
    if root and root not in sys.path:
        sys.path.insert(0, root)

    # Pool de BD chico para el hijo (N hijos × pool del padre agotarían
    # max_connections). Mínimo 2: la tarea del hijo necesita dos conexiones
    # a la vez — la sesión scoped retiene una mientras se refleja
    # ind_{code} (get_ind_table, autoload_with=engine) y se leen los
    # precios del lote. Con pool=1 la reflexión/lectura se autodeadlockea.
    os.environ["DB_POOL_SIZE"] = str(max(2, db_pool_size))
    os.environ["DB_MAX_OVERFLOW"] = "0"

    import logging
    logging.basicConfig(
        level=getattr(logging, (log_level or "INFO").upper(), logging.INFO),
        format=(f"%(asctime)s [pid {os.getpid()}] %(levelname)s "
                "%(name)s: %(message)s"),
    )
