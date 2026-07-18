"""Normalización del prefijo de la URL de PostgreSQL (deploy Railway/Heroku).

Railway/Heroku entregan `postgres://` o `postgresql://` sin driver; el
proyecto usa psycopg3, que en SQLAlchemy exige `postgresql+psycopg://`.
`_normalize_db_url` cierra ese hueco sin tocar URLs que ya traen driver.
"""
from app.config import _normalize_db_url


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
