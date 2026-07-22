from sqlalchemy import create_engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker, scoped_session

from app.config import Config

# Parámetros de sesión de PostgreSQL, por la opción -c de libpq y NO por un
# `SET`: un SET corriente es transaccional y el rollback que el pool emite al
# devolver la conexión lo desharía.
#
# lock_timeout es lo que hace FUNCIONAR la red de reintentos de
# db_compat.is_retryable_lock_error: con READ COMMITTED (el default de PG) el
# SQLSTATE 40001 no se emite nunca y el 55P03 solo aparece si hay lock_timeout
# configurado. Sin esto, un escritor bloqueado no falla, no reintenta y espera
# indefinidamente — y como el heartbeat de run_lock_service sigue latiendo, la
# corrida colgada parece viva. MySQL daba el errno 1205 gratis por su
# innodb_lock_wait_timeout (50s); PostgreSQL no trae equivalente activo.
def pg_connect_args(url: str, lock_timeout: str) -> dict:
    """connect_args de create_engine: vacío fuera de PostgreSQL."""
    if make_url(url).get_backend_name() != "postgresql":
        return {}
    return {"options": f"-c lock_timeout={lock_timeout}"}


_connect_args = pg_connect_args(Config.DATABASE_URL, Config.DB_LOCK_TIMEOUT)

engine = create_engine(
    Config.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_size=Config.DB_POOL_SIZE,
    max_overflow=Config.DB_MAX_OVERFLOW,
    connect_args=_connect_args,
    echo=False,
)

_SessionFactory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Session = scoped_session(_SessionFactory)


class Base(DeclarativeBase):
    pass


def get_session():
    return Session()


def teardown_session(exception=None):
    """Llamar al final de cada request Flask para liberar la sesión."""
    Session.remove()
