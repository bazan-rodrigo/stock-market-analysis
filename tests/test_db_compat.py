"""
Paridad de dialecto de la capa db_compat (soporte dual MySQL/PostgreSQL,
ver docs/notes/design_postgresql_dual.md).

REGLA PRINCIPAL: la rama MySQL de db_compat debe emitir EXACTAMENTE el SQL
que emitía el código antes de la capa dual. Estos tests fijan esa paridad
byte a byte — contra la construcción legacy (dialects.mysql.insert +
on_duplicate_key_update) y contra los strings crudos históricos de los
caminos calientes. Si un cambio los rompe, está cambiando el SQL que corre
contra la base MySQL de producción.

La rama PostgreSQL se verifica por compilación offline (los dialectos de
SQLAlchemy no necesitan driver) y la rama sqlite EJECUTANDO upserts reales.
"""
from datetime import date
from types import SimpleNamespace

import sqlalchemy as sa
from sqlalchemy.dialects import mysql, postgresql, sqlite
from sqlalchemy.dialects.mysql import insert as mysql_insert

from app.models import Price
from app.models.indicator_store import CurrentIndicatorValue
from app.services import db_compat
from app.services.db_compat import INSERTED


class _Bind(SimpleNamespace):
    """Bind falso: a db_compat le alcanza con .dialect (nunca conecta)."""


MYSQL  = _Bind(dialect=mysql.dialect())
PG     = _Bind(dialect=postgresql.dialect())
SQLITE = _Bind(dialect=sqlite.dialect())

_meta = sa.MetaData()
IND = sa.Table(
    "ind_rsi_14", _meta,
    sa.Column("asset_id", sa.Integer, primary_key=True),
    sa.Column("date",     sa.Date,    primary_key=True),
    sa.Column("value",    sa.Float),
)


def _sql(stmt, dialect):
    return str(stmt.compile(dialect=dialect))


# ── upsert() ORM: rama MySQL byte-idéntica a la construcción legacy ──────────

def test_upsert_mysql_identico_a_legacy_con_inserted():
    vals = dict(asset_id=1, date=date(2026, 1, 2), value=3.5)
    legacy = mysql_insert(IND).values(vals)
    legacy = legacy.on_duplicate_key_update(value=legacy.inserted.value)
    nuevo = db_compat.upsert(MYSQL, IND, vals, {"value": INSERTED})
    assert _sql(nuevo, mysql.dialect()) == _sql(legacy, mysql.dialect())


def test_upsert_mysql_identico_a_legacy_con_literal():
    # forma de fundamental_service._upsert_fund_value / _upsert_current_ind
    vals = dict(asset_id=1, date=date(2026, 1, 2), value=3.14)
    legacy = mysql_insert(IND).values(vals).on_duplicate_key_update(value=3.14)
    nuevo = db_compat.upsert(MYSQL, IND, vals, {"value": 3.14})
    assert _sql(nuevo, mysql.dialect()) == _sql(legacy, mysql.dialect())


def test_upsert_mysql_identico_a_legacy_precios_multifila():
    # forma de price_service._upsert_prices (modelo ORM + batch multi-fila)
    chunk = [
        dict(asset_id=1, date=date(2026, 1, 2), open=1.0, high=2.0,
             low=0.5, close=1.5, volume=10),
        dict(asset_id=1, date=date(2026, 1, 3), open=1.5, high=2.5,
             low=1.0, close=2.0, volume=20),
    ]
    legacy = mysql_insert(Price).values(chunk)
    legacy = legacy.on_duplicate_key_update(
        open=legacy.inserted.open, high=legacy.inserted.high,
        low=legacy.inserted.low, close=legacy.inserted.close,
        volume=legacy.inserted.volume)
    nuevo = db_compat.upsert(MYSQL, Price, chunk, {
        "open": INSERTED, "high": INSERTED, "low": INSERTED,
        "close": INSERTED, "volume": INSERTED})
    assert _sql(nuevo, mysql.dialect()) == _sql(legacy, mysql.dialect())


def test_upsert_mysql_identico_a_legacy_current_batch():
    # forma de technical_service._upsert_current_ind_batch
    rows = [{"asset_id": 1, "code": "rsi_14", "value_num": 55.0, "value_str": None},
            {"asset_id": 1, "code": "adx_14", "value_num": 20.0, "value_str": None}]
    legacy = mysql_insert(CurrentIndicatorValue.__table__).values(rows)
    legacy = legacy.on_duplicate_key_update(
        value_num=legacy.inserted.value_num, value_str=legacy.inserted.value_str)
    nuevo = db_compat.upsert(MYSQL, CurrentIndicatorValue.__table__, rows,
                             {"value_num": INSERTED, "value_str": INSERTED})
    assert _sql(nuevo, mysql.dialect()) == _sql(legacy, mysql.dialect())


def test_upsert_mysql_no_dedup_lote_clave_repetida():
    # Paridad byte-idéntica: la rama MySQL hace early-return con on_duplicate_
    # key_update ANTES de _dedupe_last (que solo corre en PG/sqlite). Un lote
    # con (asset_id, date) repetido NO se colapsa: MySQL tolera la clave
    # duplicada dentro del statement (última gana), así que las N filas
    # originales deben llegar íntegras al VALUES — igual que el SQL histórico.
    d = date(2026, 1, 2)
    chunk = [
        dict(asset_id=1, date=d,                value=1.0),
        dict(asset_id=2, date=date(2026, 1, 3), value=2.0),
        dict(asset_id=1, date=d,                value=9.0),  # clave repetida
    ]
    legacy = mysql_insert(IND).values(chunk)
    legacy = legacy.on_duplicate_key_update(value=legacy.inserted.value)
    nuevo = db_compat.upsert(MYSQL, IND, chunk, {"value": INSERTED})
    # byte-idéntico al build legacy con las 3 filas (dedup NO corrió)
    assert _sql(nuevo, mysql.dialect()) == _sql(legacy, mysql.dialect())
    # y las 3 filas siguen en el VALUES (si _dedupe_last hubiera corrido, 2)
    assert _sql(nuevo, mysql.dialect()).count("(%s, %s, %s)") == 3


# ── upsert() ORM: rama PostgreSQL ─────────────────────────────────────────────

def test_upsert_pg_on_conflict_sobre_pk():
    vals = dict(asset_id=1, date=date(2026, 1, 2), value=3.5)
    s = _sql(db_compat.upsert(PG, IND, vals, {"value": INSERTED}),
             postgresql.dialect())
    assert "ON CONFLICT (asset_id, date) DO UPDATE SET value = excluded.value" in s


def test_upsert_pg_prices_usa_unique_no_la_pk_autoincremental():
    # prices tiene PK id (ausente de values) + UNIQUE(asset_id, date): el
    # ON CONFLICT debe apuntar al UNIQUE — el equivalente de MySQL, donde
    # ON DUPLICATE KEY dispara con cualquier clave única.
    chunk = [dict(asset_id=1, date=date(2026, 1, 2), open=1.0, high=2.0,
                  low=0.5, close=1.5, volume=10)]
    s = _sql(db_compat.upsert(PG, Price, chunk, {"close": INSERTED}),
             postgresql.dialect())
    assert "ON CONFLICT (asset_id, date)" in s
    assert "close = excluded.close" in s


# ── upsert_sql(): strings crudos byte-idénticos a los históricos ─────────────

def test_upsert_sql_mysql_ind_series_byte_identico():
    sql = db_compat.upsert_sql(
        MYSQL, "ind_rsi_14", ("asset_id", "date", "value"),
        update_cols=("value",), pk_cols=("asset_id", "date"),
        quote_table=True)
    assert sql == ("INSERT INTO `ind_rsi_14` (asset_id, date, value)"
                   " VALUES (%s, %s, %s)"
                   " ON DUPLICATE KEY UPDATE value = VALUES(value)")


def test_upsert_sql_mysql_asset_meta_byte_identico():
    sql = db_compat.upsert_sql(
        MYSQL, "ind_asset_meta", ("asset_id", "code", "benchmark_id"),
        update_cols=("benchmark_id",), pk_cols=("asset_id", "code"))
    assert sql == ("INSERT INTO ind_asset_meta (asset_id, code, benchmark_id)"
                   " VALUES (%s, %s, %s)"
                   " ON DUPLICATE KEY UPDATE benchmark_id = VALUES(benchmark_id)")


def test_upsert_sql_mysql_stats_meta_byte_identico():
    sql = db_compat.upsert_sql(
        MYSQL, "ind_asset_meta",
        ("asset_id", "code", "min_date", "max_date", "row_count"),
        update_cols=("min_date", "max_date", "row_count"),
        pk_cols=("asset_id", "code"))
    assert sql == (
        "INSERT INTO ind_asset_meta (asset_id, code, min_date, max_date, row_count)"
        " VALUES (%s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE"
        " min_date = VALUES(min_date), max_date = VALUES(max_date),"
        " row_count = VALUES(row_count)")


def test_upsert_sql_pg_on_conflict():
    sql = db_compat.upsert_sql(
        PG, "ind_rsi_14", ("asset_id", "date", "value"),
        update_cols=("value",), pk_cols=("asset_id", "date"),
        quote_table=True)
    assert sql == ('INSERT INTO "ind_rsi_14" (asset_id, date, value)'
                   " VALUES (%s, %s, %s)"
                   " ON CONFLICT (asset_id, date) DO UPDATE SET"
                   " value = EXCLUDED.value")


def test_upsert_sql_sqlite_placeholders_qmark():
    sql = db_compat.upsert_sql(
        SQLITE, "ind_rsi_14", ("asset_id", "date", "value"),
        update_cols=("value",), pk_cols=("asset_id", "date"),
        quote_table=True)
    assert "VALUES (?, ?, ?)" in sql and "ON CONFLICT (asset_id, date)" in sql


# ── quoting / placeholder / capacidades ──────────────────────────────────────

def test_quote_ident_por_dialecto():
    assert db_compat.quote_ident(MYSQL, "signal") == "`signal`"
    assert db_compat.quote_ident(PG, "signal") == '"signal"'
    assert db_compat.quote_ident(SQLITE, "signal") == '"signal"'


def test_placeholder_por_driver():
    assert db_compat.placeholder(MYSQL) == "%s"
    assert db_compat.placeholder(PG) == "%s"
    assert db_compat.placeholder(SQLITE) == "?"


def test_supports_truncate():
    assert db_compat.supports_truncate(MYSQL)
    assert db_compat.supports_truncate(PG)      # en PG además es transaccional
    assert not db_compat.supports_truncate(SQLITE)


def test_is_mysql_is_postgres():
    assert db_compat.is_mysql(MYSQL) and not db_compat.is_postgres(MYSQL)
    assert db_compat.is_postgres(PG) and not db_compat.is_mysql(PG)
    assert not db_compat.is_mysql(SQLITE) and not db_compat.is_postgres(SQLITE)


# ── is_retryable_lock_error: las tres formas de excepción ────────────────────

def _exc(**orig_attrs):
    return SimpleNamespace(orig=SimpleNamespace(**orig_attrs))


def test_retry_errnos_mysql():
    assert db_compat.is_retryable_lock_error(_exc(args=(1205, "Lock wait timeout")))
    assert db_compat.is_retryable_lock_error(_exc(args=(1213, "Deadlock found")))
    assert not db_compat.is_retryable_lock_error(_exc(args=(1062, "Duplicate entry")))


def test_retry_sqlstates_psycopg2():
    # psycopg2: SQLSTATE en .pgcode, args[0] es el mensaje
    assert db_compat.is_retryable_lock_error(
        _exc(args=("deadlock detected",), pgcode="40P01"))
    assert db_compat.is_retryable_lock_error(
        _exc(args=("lock timeout",), pgcode="55P03"))
    assert db_compat.is_retryable_lock_error(
        _exc(args=("serialization",), pgcode="40001"))
    assert not db_compat.is_retryable_lock_error(
        _exc(args=("unique violation",), pgcode="23505"))


def test_retry_sqlstates_psycopg3():
    # psycopg (v3): SQLSTATE en .sqlstate
    assert db_compat.is_retryable_lock_error(
        _exc(args=("deadlock detected",), sqlstate="40P01"))
    assert not db_compat.is_retryable_lock_error(
        _exc(args=("not null violation",), sqlstate="23502"))


def test_retry_sin_orig_no_reintenta():
    assert not db_compat.is_retryable_lock_error(SimpleNamespace(orig=None))
    assert not db_compat.is_retryable_lock_error(SimpleNamespace())


# ── wipe_table: SQL emitido por dialecto ─────────────────────────────────────

class _Sess:
    """Session falsa: registra los statements ejecutados."""
    def __init__(self, dialect):
        self._dialect = dialect
        self.executed = []

    def get_bind(self):
        return _Bind(dialect=self._dialect)

    def execute(self, stmt):
        self.executed.append(str(stmt))


def test_wipe_table_truncate_vs_delete():
    for d in (mysql.dialect(), postgresql.dialect()):
        s = _Sess(d)
        db_compat.wipe_table(s, "sig_7")
        assert s.executed == ["TRUNCATE TABLE sig_7"]
    s = _Sess(sqlite.dialect())
    db_compat.wipe_table(s, "sig_7")
    assert s.executed == ["DELETE FROM sig_7"]


# ── Semántica portable (fase 3): orden de NULLs y case-insensitive ───────────

def test_order_desc_nulls_last_pone_nulls_al_final():
    # sqlite es un motor donde el DESC puro ya pone NULLs al final (como
    # MySQL); el helper debe conservar ese orden Y generar la clave extra
    # (col IS NULL) que lo garantiza también en PostgreSQL
    eng, t = _mem_engine_con_tabla()
    d = date(2026, 1, 2)
    with eng.begin() as c:
        c.execute(t.insert(), [
            {"asset_id": 1, "date": d, "value": 1.0},
            {"asset_id": 2, "date": d, "value": None},
            {"asset_id": 3, "date": d, "value": 9.0},
        ])
        rows = c.execute(
            sa.select(t.c.asset_id)
            .order_by(*db_compat.order_desc_nulls_last(t.c.value))
        ).fetchall()
    assert [r[0] for r in rows] == [3, 1, 2]   # 9.0, 1.0, NULL

    # la clave (col IS NULL) tiene que estar en el SQL de ambos motores
    stmt = sa.select(t.c.asset_id).order_by(
        *db_compat.order_desc_nulls_last(t.c.value))
    for d_ in (mysql.dialect(), postgresql.dialect()):
        s = _sql(stmt, d_)
        assert "value IS NULL" in s and "value DESC" in s


def test_ci_equals_matchea_sin_distinguir_caso():
    # sqlite compara '=' con BINARY (case-sensitive, como PostgreSQL):
    # ci_equals debe encontrar la fila igual — es exactamente el contrato
    # que la collation de MySQL daba gratis
    eng = sa.create_engine("sqlite://")
    meta = sa.MetaData()
    t = sa.Table("u", meta,
                 sa.Column("id", sa.Integer, primary_key=True),
                 sa.Column("username", sa.String(80)))
    meta.create_all(eng)
    with eng.begin() as c:
        c.execute(t.insert(), [{"id": 1, "username": "admin"}])
        exacto = c.execute(sa.select(t.c.id).where(
            t.c.username == "ADMIN")).fetchall()
        ci = c.execute(sa.select(t.c.id).where(
            db_compat.ci_equals(t.c.username, "ADMIN"))).fetchall()
    assert exacto == []          # '=' puro no matchea en motores CS
    assert [r[0] for r in ci] == [1]
    # None no explota (form vacío)
    assert str(db_compat.ci_equals(sa.column("x"), None))


# ── Ejecución real sobre sqlite (la rama que corre en esta suite) ────────────

def _mem_engine_con_tabla():
    eng = sa.create_engine("sqlite://")
    meta = sa.MetaData()
    t = sa.Table(
        "t", meta,
        sa.Column("asset_id", sa.Integer, primary_key=True),
        sa.Column("date",     sa.Date,    primary_key=True),
        sa.Column("value",    sa.Float),
    )
    meta.create_all(eng)
    return eng, t


def test_upsert_ejecuta_de_verdad_en_sqlite():
    eng, t = _mem_engine_con_tabla()
    d = date(2026, 1, 2)
    with eng.begin() as c:
        c.execute(db_compat.upsert(
            eng, t, dict(asset_id=1, date=d, value=1.0), {"value": INSERTED}))
        c.execute(db_compat.upsert(
            eng, t, dict(asset_id=1, date=d, value=9.0), {"value": INSERTED}))
        rows = c.execute(sa.select(t)).fetchall()
    assert [(r[0], r[2]) for r in rows] == [(1, 9.0)]


def test_upsert_dedup_lote_clave_repetida_ultima_gana_en_sqlite():
    # Regresión: la fuente Ámbito (riesgo país) devuelve fechas duplicadas.
    # Un lote con (asset_id, date) repetido dentro del mismo INSERT hacía que
    # PG/sqlite abortaran con CardinalityViolation ("ON CONFLICT DO UPDATE
    # command cannot affect row a second time"); MySQL lo toleraba (última
    # gana). La rama PG/sqlite ahora deduplica para replicar esa semántica.
    eng, t = _mem_engine_con_tabla()
    d = date(2026, 1, 2)
    chunk = [
        dict(asset_id=1, date=d,               value=1.0),
        dict(asset_id=2, date=date(2026, 1, 3), value=2.0),
        dict(asset_id=1, date=d,               value=9.0),  # pisa a la 1.ª
    ]
    with eng.begin() as c:
        c.execute(db_compat.upsert(eng, t, chunk, {"value": INSERTED}))
        rows = c.execute(sa.select(t).order_by(t.c.asset_id)).fetchall()
    assert [(r[0], r[2]) for r in rows] == [(1, 9.0), (2, 2.0)]  # última gana


def test_dedupe_last_sin_duplicados_devuelve_la_misma_lista():
    # Sin duplicados no toca nada (misma instancia, no una copia): el caso
    # común no paga la reconstrucción de la lista.
    rows = [{"asset_id": 1, "date": date(2026, 1, 2)},
            {"asset_id": 1, "date": date(2026, 1, 3)}]
    assert db_compat._dedupe_last(rows, ["asset_id", "date"]) is rows


def test_upsert_sql_crudo_ejecuta_de_verdad_en_sqlite():
    # el camino de _write_ind_series (exec_driver_sql + executemany)
    eng, t = _mem_engine_con_tabla()
    sql = db_compat.upsert_sql(
        eng, "t", ("asset_id", "date", "value"),
        update_cols=("value",), pk_cols=("asset_id", "date"),
        quote_table=True)
    with eng.begin() as c:
        c.exec_driver_sql(sql, [(1, "2026-01-02", 1.0), (2, "2026-01-02", 2.0)])
        c.exec_driver_sql(sql, [(1, "2026-01-02", 7.0)])
        rows = c.execute(sa.text(
            "SELECT asset_id, value FROM t ORDER BY asset_id")).fetchall()
    assert [tuple(r) for r in rows] == [(1, 7.0), (2, 2.0)]


def test_list_tables_by_prefix_y_approx_rows():
    eng = sa.create_engine("sqlite://")
    meta = sa.MetaData()
    for name in ("ind_rsi_14", "sig_3", "strat_res_2", "otros"):
        sa.Table(name, meta, sa.Column("asset_id", sa.Integer, primary_key=True))
    meta.create_all(eng)
    assert db_compat.list_tables_by_prefix(eng, "ind_", "sig_", "strat_res_") == [
        "ind_rsi_14", "sig_3", "strat_res_2"]

    from sqlalchemy.orm import Session as _S
    with _S(eng) as s:
        s.execute(sa.text("INSERT INTO sig_3 (asset_id) VALUES (1), (2)"))
        # commit: el inspector de list_tables_by_prefix abre otra conexión
        # (en el sqlite en memoria del test compartiría la única conexión y
        # el cierre rollbackearía el INSERT pendiente; en motores reales es
        # simplemente otra conexión que no ve lo no-committeado)
        s.commit()
        rows = db_compat.approx_table_rows(s, "sig_")
    assert rows == {"sig_3": 2}
