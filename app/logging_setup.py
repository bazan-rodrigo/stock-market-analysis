import logging
import logging.handlers
from pathlib import Path

from app.config import Config


def configure_logging() -> None:
    log_file = Path(Config.LOG_FILE)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler rotativo: máx 10 MB, guarda 5 backups
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Silenciar loggers muy verbosos de librerías externas — se fijan a
    # WARNING SIN importar LOG_LEVEL, así ni con LOG_LEVEL=DEBUG (debug de la
    # app) inundan. urllib3/requests son los que más pesan: cada request a
    # Yahoo emitía varias líneas DEBUG (reventaron el rate limit de logs de
    # Railway, 500/seg, durante un backfill de precios).
    for _noisy in ("apscheduler", "yfinance", "peewee",
                   "urllib3", "requests", "asyncio", "hpack", "httpx"):
        logging.getLogger(_noisy).setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.INFO)   # ver requests HTTP
