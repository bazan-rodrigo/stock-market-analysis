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


def _get_opt(key: str) -> str | None:
    """Como _get, pero distingue "no lo definió nadie" de "lo definió vacío".

    Necesario para resolver el motor: la regla depende de si `db_engine` y
    `database_url` fueron provistos EXPLÍCITAMENTE, no de su valor."""
    env_val = os.environ.get(key.upper())
    if env_val is not None:
        return env_val
    if _conf.has_option(_SECTION, key):
        return _conf.get(_SECTION, key)
    return None


# ── Motor de base de datos: una elección de INSTALACIÓN ──────────────────────
# El motor NO es una propiedad del entorno (que corra en Railway no implica
# PostgreSQL, ni un Codespace implica MySQL): se elige al instalar, con
# `db_engine`, y de ahí se derivan el driver, el puerto y el usuario por
# defecto. `database_url` sigue siendo el contrato con la app y gana cuando
# viene dada — es lo que usa Railway.

_DEFAULT_ENGINE = "postgres"          # el motor desplegado hoy

_ENGINE_ALIASES = {
    "postgres": "postgres", "postgresql": "postgres", "pg": "postgres",
    "mysql": "mysql", "mariadb": "mysql",
}

_ENGINE_DEFAULTS = {
    "postgres": {"driver": "postgresql+psycopg", "port": "5432",
                 "user": "postgres", "password": "postgres", "query": ""},
    "mysql": {"driver": "mysql+mysqldb", "port": "3306",
              "user": "root", "password": "", "query": "?charset=utf8mb4"},
}


def _normalize_engine(value: str) -> str:
    """Nombre canónico del motor ('postgres' | 'mysql'), o RuntimeError."""
    engine = _ENGINE_ALIASES.get((value or "").strip().lower())
    if engine is None:
        raise RuntimeError(
            f"db_engine inválido: {value!r}. Valores admitidos: "
            f"'postgres' (o 'postgresql'/'pg') y 'mysql' (o 'mariadb')."
        )
    return engine


def _engine_of_url(url: str) -> str | None:
    """Motor que nombra una URL de conexión, o None si no es uno de los dos
    soportados. sqlite cae acá: es el stub de la suite de tests, no una
    instalación — por eso NO participa del chequeo de coherencia."""
    scheme = (url or "").split("://", 1)[0].split("+", 1)[0].lower()
    return _ENGINE_ALIASES.get(scheme)


def _resolve_db(engine_opt: str | None, url_opt: str | None, *, host: str,
                name: str, port_opt: str | None, user_opt: str | None,
                password_opt: str | None) -> tuple[str, str]:
    """Resuelve (motor, DATABASE_URL) a partir de la config cruda.

    - Las dos definidas y contradiciéndose → **RuntimeError**. Es el caso que
      antes pasaba callado: instalabas un motor y la app arrancaba contra el
      otro, y el síntoma aparecía después como un error de driver.
    - Solo la URL → el motor se DEDUCE de ella (no rompe instalaciones que
      nunca definieron `db_engine`, como el Railway de hoy).
    - Solo el motor → la URL se deriva de él y de los `db_*`.
    - Ninguna → motor por defecto + URL derivada.
    """
    url = _normalize_db_url(url_opt) if url_opt else None
    url_engine = _engine_of_url(url) if url else None

    if engine_opt is not None:
        engine = _normalize_engine(engine_opt)
        if url_engine is not None and url_engine != engine:
            raise RuntimeError(
                f"Config incoherente: db_engine dice '{engine}' pero "
                f"database_url apunta a '{url_engine}'. El motor es una "
                f"elección de instalación: corregí uno de los dos. "
                f"(Si la URL es la buena, borrá db_engine y se deduce sola.)"
            )
    else:
        engine = url_engine or _DEFAULT_ENGINE

    if url:
        return engine, url

    d = _ENGINE_DEFAULTS[engine]
    port = port_opt or d["port"]
    user = user_opt if user_opt is not None else d["user"]
    password = password_opt if password_opt is not None else d["password"]
    return engine, (f"{d['driver']}://{user}:{password}"
                    f"@{host}:{port}/{name}{d['query']}")


class Config:
    SECRET_KEY: str = _get("secret_key", "dev-secret-change-me")

    DB_HOST: str = _get("db_host", "localhost")
    DB_NAME: str = _get("db_name", "stock_analysis")

    # El motor elegido al instalar y la URL que sale de él. Los defaults de
    # puerto/usuario/password los pone el motor (5432/postgres vs 3306/root),
    # así que solo hace falta declararlos si se apartan de lo habitual.
    # `database_url` explícita gana y es lo que usa Railway; si contradice a
    # `db_engine`, la app NO arranca (ver _resolve_db).
    DB_ENGINE, DATABASE_URL = _resolve_db(
        _get_opt("db_engine"), _get_opt("database_url"),
        host=DB_HOST, name=DB_NAME, port_opt=_get_opt("db_port"),
        user_opt=_get_opt("db_user"), password_opt=_get_opt("db_password"),
    )

    DB_PORT: int = int(_get_opt("db_port")
                       or _ENGINE_DEFAULTS[DB_ENGINE]["port"])
    DB_USER: str = _get_opt("db_user") or _ENGINE_DEFAULTS[DB_ENGINE]["user"]
    DB_PASSWORD: str = (_get_opt("db_password")
                        if _get_opt("db_password") is not None
                        else _ENGINE_DEFAULTS[DB_ENGINE]["password"])

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
