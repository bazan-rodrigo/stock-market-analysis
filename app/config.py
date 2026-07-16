import os
import configparser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

_conf = configparser.ConfigParser()
_conf_file = BASE_DIR / "conf.properties"
if _conf_file.exists():
    _conf.read(_conf_file, encoding="utf-8")

_SECTION = "settings"


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
    DATABASE_URL: str = _get(
        "database_url",
        f"mysql+mysqldb://{DB_USER}:{DB_PASSWORD}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4",
    )

    # Pool de conexiones de SQLAlchemy. Con MySQL los defaults sobran
    # (threads baratos, max_connections=151); en PostgreSQL cada conexión
    # es un PROCESO del servidor (max_connections=100 default) — bajar
    # estos valores si corren varios procesos contra la misma base.
    DB_POOL_SIZE: int = int(_get("db_pool_size", "30"))
    DB_MAX_OVERFLOW: int = int(_get("db_max_overflow", "20"))

    LOG_LEVEL: str = _get("log_level", "INFO")
    LOG_FILE: str = _get("log_file", str(BASE_DIR / "logs" / "app.log"))

    # Credenciales del admin inicial (se cambian en el primer login)
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"
