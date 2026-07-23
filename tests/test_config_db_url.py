"""Normalización del prefijo de la URL de PostgreSQL (deploy Railway/Heroku).

Railway/Heroku entregan `postgres://` o `postgresql://` sin driver; el
proyecto usa psycopg3, que en SQLAlchemy exige `postgresql+psycopg://`.
`_normalize_db_url` cierra ese hueco sin tocar URLs que ya traen driver.
"""
import pytest

from app.config import _normalize_db_url, _resolve_db, _validate_lock_timeout
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


# ── El motor como elección de INSTALACIÓN ────────────────────────────────────
#
# El motor no es una propiedad del entorno: se elige al instalar con db_engine
# y de ahí salen driver, puerto y usuario. database_url explícita gana (es lo
# que usa Railway); si contradice al motor elegido, la app NO arranca.

def _resolve(engine=None, url=None, **kw):
    kw.setdefault("host", "h")
    kw.setdefault("name", "db")
    for k in ("port_opt", "user_opt", "password_opt"):
        kw.setdefault(k, None)
    return _resolve_db(engine, url, **kw)


def test_solo_el_motor_deriva_driver_puerto_y_usuario():
    assert _resolve(engine="postgres") == (
        "postgres", "postgresql+psycopg://postgres:postgres@h:5432/db")
    assert _resolve(engine="mysql") == (
        "mysql", "mysql+mysqldb://root:@h:3306/db?charset=utf8mb4")


def test_sin_nada_usa_el_motor_por_defecto():
    engine, url = _resolve()
    assert engine == "postgres" and url.startswith("postgresql+psycopg://")


def test_solo_la_url_deduce_el_motor():
    """No romper instalaciones que nunca definieron db_engine — el Railway de
    hoy es exactamente ese caso: define DATABASE_URL y nada más."""
    assert _resolve(url="postgres://u:p@h:5432/db") == (
        "postgres", "postgresql+psycopg://u:p@h:5432/db")
    assert _resolve(url="mysql+mysqldb://u:p@h:3306/db")[0] == "mysql"


def test_la_url_explicita_gana_sobre_los_db_star():
    _, url = _resolve(engine="postgres", url="postgres://u:p@otro:6000/x",
                      port_opt="5432", user_opt="ignorado")
    assert url == "postgresql+psycopg://u:p@otro:6000/x"


def test_motor_y_url_contradictorios_no_arrancan():
    """El caso que antes pasaba callado: instalabas un motor y la app corría
    contra el otro, y el síntoma aparecía después como un error de driver."""
    with pytest.raises(RuntimeError, match="incoherente"):
        _resolve(engine="mysql", url="postgres://u:p@h/db")
    with pytest.raises(RuntimeError, match="incoherente"):
        _resolve(engine="postgres", url="mysql+mysqldb://u:p@h/db")


def test_los_alias_del_motor_se_aceptan():
    for alias in ("postgresql", "PG", " Postgres "):
        assert _resolve(engine=alias)[0] == "postgres"
    for alias in ("mariadb", "MySQL"):
        assert _resolve(engine=alias)[0] == "mysql"


def test_motor_desconocido_falla_nombrando_los_validos():
    with pytest.raises(RuntimeError, match="db_engine inválido"):
        _resolve(engine="oracle")


def test_sqlite_no_dispara_el_chequeo_de_coherencia():
    """El stub de la suite no es una instalación: convive con cualquier
    db_engine sin que la app se niegue a arrancar."""
    engine, url = _resolve(engine="mysql", url="sqlite:///.pytest-stub.db")
    assert url == "sqlite:///.pytest-stub.db" and engine == "mysql"


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


def test_no_pisa_el_options_que_venga_en_la_url():
    """SQLAlchemy mete la query de la URL en los parámetros de conexión, pero
    connect_args gana sobre ellos: sin conservarlo, un search_path puesto en la
    URL desaparecería en silencio. Con varios -c del mismo parámetro libpq
    aplica el último, así que el nuestro va al final y sigue mandando."""
    args = pg_connect_args(
        "postgresql+psycopg://u:p@h/db?options=-c%20search_path%3Dsma", "30s")
    assert args["options"] == "-c search_path=sma -c lock_timeout=30s"


# ── db_lock_timeout: la unidad implícita de PostgreSQL es el MILISEGUNDO ─────

def test_exige_unidad_explicita_porque_el_numero_pelado_son_milisegundos():
    # '30' al lado de 'db_pool_size = 30' parece 30 segundos y son 30 ms:
    # abortaría toda espera de lock al instante. Se rechaza, no se interpreta.
    for crudo in ("30", "0.5s", "30 s", "abc", "", "   "):
        with pytest.raises(RuntimeError, match="db_lock_timeout"):
            _validate_lock_timeout(crudo)


def test_acepta_las_unidades_de_postgres_y_recorta_espacios():
    for v in ("30s", "500ms", "2min", "1h"):
        assert _validate_lock_timeout(v) == v
    assert _validate_lock_timeout("  30s  ") == "30s"


def test_cero_desactiva_el_tope_sin_unidad():
    assert _validate_lock_timeout("0") == "0"
