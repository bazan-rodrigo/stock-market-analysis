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

    DATABASE_URL: str = (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    )

    LOG_LEVEL: str = _get("log_level", "INFO")
    LOG_FILE: str = _get("log_file", str(BASE_DIR / "logs" / "app.log"))

    # Credenciales del admin inicial (se cambian en el primer login)
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"
