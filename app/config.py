import os
import configparser
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

_conf = configparser.ConfigParser()
_conf_file = BASE_DIR / "conf.properties"
if _conf_file.exists():
    _conf.read(_conf_file, encoding="utf-8")

_SECTION = "settings"


def _normalize_db_url(url: str) -> str:
    """Normaliza el prefijo de PostgreSQL al driver que usa el proyecto.

    Railway/Heroku entregan la cadena de conexión como ``postgres://`` o
    ``postgresql://`` (sin driver). El proyecto usa **psycopg3**, que en
    SQLAlchemy exige el prefijo explícito ``postgresql+psycopg://`` — sin él,
    SQLAlchemy busca psycopg2 (no instalado) y falla. Normalizamos solo
    cuando falta el driver; no tocamos URLs que ya lo traen
    (``mysql+mysqldb://``, ``sqlite://`` de los tests, ``postgresql+psycopg://``).
    """
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


_LOCK_TIMEOUT_RE = re.compile(r"^\d+(us|ms|s|min|h|d)$")


def _validate_lock_timeout(value: str) -> str:
    """Valida db_lock_timeout y EXIGE unidad explícita.

    La unidad implícita de ``lock_timeout`` en PostgreSQL es el MILISEGUNDO,
    así que un ``db_lock_timeout = 30`` escrito al lado de ``db_pool_size = 30``
    no da 30 segundos sino 30 ms: toda espera de lock abortaría al instante y
    las corridas masivas fallarían por timeouts que nadie pidió. El error va en
    la dirección más dañina (1000x más corto) y PostgreSQL lo acepta sin
    chistar, así que el número pelado se rechaza en vez de interpretarse.

    Un valor inválido tumba TODAS las conexiones (el backend rechaza el startup
    packet) y con create_engine perezoso eso aparece recién en el primer
    request: por eso se valida acá, al importar la config, y no al conectar.
    """
    v = (value or "").strip()
    if v == "0":
        return v            # 0 = sin tope (la unidad es irrelevante)
    if not _LOCK_TIMEOUT_RE.match(v):
        raise RuntimeError(
            f"db_lock_timeout inválido: {value!r}. Poné la unidad explícita "
            f"(ej. '30s', '500ms', '2min') o '0' para desactivar el tope. "
            f"Sin unidad, PostgreSQL lo interpreta en MILISEGUNDOS."
        )
    return v


def _get(key: str, default: str | None = None) -> str:
    env_val = os.environ.get(key.upper())
    if env_val is not None:
        return env_val
    if _conf.has_option(_SECTION, key):
        return _conf.get(_SECTION, key)
    if default is not None:
        return default
    raise RuntimeError(
        f"Falta config obligatoria: variable de entorno {key.upper()} "
        f"o clave '{key}' bajo [{_SECTION}] en conf.properties"
    )


class Config:
    SECRET_KEY: str = _get("secret_key", "dev-secret-change-me")

    DB_HOST: str = _get("db_host", "localhost")
    DB_PORT: int = int(_get("db_port", "3306"))
    DB_NAME: str = _get("db_name", "stock_analysis")
    DB_USER: str = _get("db_user", "root")
    DB_PASSWORD: str = _get("db_password", "")

    # Overrideable completa via env DATABASE_URL (tests usan un stub
    # sqlite; para PostgreSQL: postgresql+psycopg://user:pass@host/db)
    DATABASE_URL: str = _normalize_db_url(_get(
        "database_url",
        f"mysql+mysqldb://{DB_USER}:{DB_PASSWORD}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4",
    ))

    # Pool de conexiones de SQLAlchemy. Con MySQL los defaults sobran
    # (threads baratos, max_connections=151); en PostgreSQL cada conexión
    # es un PROCESO del servidor (max_connections=100 default) — bajar
    # estos valores si corren varios procesos contra la misma base.
    DB_POOL_SIZE: int = int(_get("db_pool_size", "30"))
    DB_MAX_OVERFLOW: int = int(_get("db_max_overflow", "20"))

    # Espera máxima por un lock en PostgreSQL (app/database.py la pasa por la
    # opción -c de libpq). Es lo que convierte una espera indefinida en un
    # SQLSTATE 55P03 reintentable; con '0' el timeout se desactiva y una
    # escritura bloqueada vuelve a colgarse en silencio. Sin efecto fuera de PG.
    DB_LOCK_TIMEOUT: str = _validate_lock_timeout(_get("db_lock_timeout", "30s"))

    # Arranque de APScheduler EN ESTE PROCESO. Con gunicorn multi-worker o
    # réplicas, cada proceso arrancaría su propio scheduler y el job diario
    # se dispararía N veces (el lock persistido lo deduplica, pero es
    # desperdicio: N schedulers, N misfires). Patrón recomendado: RUN_SCHEDULER=0
    # en el/los proceso(s) web y correr el scheduler en un proceso worker
    # dedicado (worker.py, que lo fuerza a 1). Default 1 = no rompe el dev
    # local ni el Codespace, que corren en un solo proceso.
    RUN_SCHEDULER: bool = _get("run_scheduler", "1").strip().lower() \
        not in ("0", "false", "no", "off", "")

    LOG_LEVEL: str = _get("log_level", "INFO")
    LOG_FILE: str = _get("log_file", str(BASE_DIR / "logs" / "app.log"))

    # ── ProcessPool del backfill de indicadores (partición por activos) ──
    # Procesos hijos del pool; 0 = auto (cores - 1, dejando un core para el
    # padre: UI, drenaje de progreso, BD). 1 fuerza threads.
    IND_POOL_PROCS: int = int(_get("ind_pool_procs", "0"))
    # Techo del modo auto (0=auto): acota cores-1 para no reventar
    # max_connections en máquinas grandes — N procesos × ind_child_db_pool
    # + el pool del padre (30+20) deben entrar en 151 (MySQL) / 100 (PG).
    # 12×2 + 50 = 74 < 100: seguro contra el default de PostgreSQL. Subir
    # con IND_POOL_PROCS explícito si el hardware y max_connections lo dan.
    IND_POOL_MAX_PROCS: int = int(_get("ind_pool_max_procs", "12"))
    # Umbral de activos para activar procesos: por debajo, threads — a
    # escala chica el overhead de spawn+import supera al beneficio del
    # paralelismo real (medido: a ~560 activos el GIL-bound domina recién
    # en cómputo, no en el arranque).
    IND_POOL_MIN_ASSETS: int = int(_get("ind_pool_min_assets", "1500"))
    # Pool de conexiones de CADA proceso hijo (el padre conserva
    # db_pool_size): N hijos × pool grande agotaría max_connections
    # (151 MySQL / 100 PostgreSQL).
    IND_CHILD_DB_POOL: int = int(_get("ind_child_db_pool", "2"))

    # Credenciales del admin inicial (se cambian en el primer login)
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"
