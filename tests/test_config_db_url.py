"""Normalización del prefijo de la URL de PostgreSQL (deploy Railway/Heroku).

Railway/Heroku entregan `postgres://` o `postgresql://` sin driver; el
proyecto usa psycopg3, que en SQLAlchemy exige `postgresql+psycopg://`.
`_normalize_db_url` cierra ese hueco sin tocar URLs que ya traen driver.
"""
from app.config import _normalize_db_url
from app.database import pg_connect_args


def test_postgres_scheme_sin_driver_recibe_psycopg():
    assert _normalize_db_url(
        "postgres://user:pass@host:5432/db"
    ) == "postgresql+psycopg://user:pass@host:5432/db"


def test_postgresql_scheme_sin_driver_recibe_psycopg():
    assert _normalize_db_url(
        "postgresql://user:pass@host:5432/db"
    ) == "postgresql+psycopg://user:pass@host:5432/db"


def test_url_con_driver_explicito_no_se_toca():
    url = "postgresql+psycopg://user:pass@host:5432/db"
    assert _normalize_db_url(url) == url


def test_mysql_no_se_toca():
    url = "mysql+mysqldb://root:@localhost:3306/stock_analysis?charset=utf8mb4"
    assert _normalize_db_url(url) == url


def test_sqlite_de_tests_no_se_toca():
    url = "sqlite:///.pytest-stub.db"
    assert _normalize_db_url(url) == url


# ── lock_timeout: la precondición de que el retry de locks funcione ──────────
#
# Con READ COMMITTED (default de PG) el SQLSTATE 40001 no se emite nunca y el
# 55P03 solo aparece si hay lock_timeout configurado. Sin él,
# is_retryable_lock_error() no ve nada y un escritor bloqueado se cuelga en vez
# de reintentar. Va por la opción -c de libpq y no por un `SET` porque un SET
# corriente es transaccional: el rollback del pool al devolver la conexión lo
# desharía.

def test_lock_timeout_viaja_como_opcion_de_libpq():
    assert pg_connect_args(
        "postgresql+psycopg://u:p@h:5432/db", "30s"
    ) == {"options": "-c lock_timeout=30s"}


def test_sin_driver_explicito_igual_se_reconoce_postgres():
    assert pg_connect_args("postgresql://u:p@h/db", "10s") == {
        "options": "-c lock_timeout=10s"}


def test_fuera_de_postgres_no_se_pasa_nada():
    # sqlite (la suite) y cualquier otro motor: connect_args vacío, o
    # create_engine rechazaría el parámetro desconocido
    assert pg_connect_args("sqlite:///.pytest-stub.db", "30s") == {}
