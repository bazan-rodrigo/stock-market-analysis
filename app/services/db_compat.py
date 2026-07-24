"""
Capa de compatibilidad de dialecto: MySQL/MariaDB ↔ PostgreSQL (↔ sqlite).

REGLA DEL MÓDULO (soporte dual, ver docs/notes/design_postgresql_dual.md):
la app corre contra MySQL/MariaDB (producción actual) o PostgreSQL según
DATABASE_URL. Todo SQL con sabor a motor se construye acá — los servicios
no llevan ramas por dialecto propias. La rama MySQL debe emitir EXACTAMENTE
el SQL que emitía el código antes de esta capa: tests/test_db_compat.py
fija esa paridad byte a byte, romperla es cambiar lo que corre producción.

sqlite existe solo para la suite de tests (conftest apunta DATABASE_URL a
un stub sqlite); su rama replica la semántica, no la performance. PG nunca
debe caer al camino de sqlite: es un motor de producción, con rama propia.
"""
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import insert as _mysql_insert
from sqlalchemy.dialects.postgresql import insert as _pg_insert
from sqlalchemy.dialects.sqlite import insert as _sqlite_insert

# Sentinel para upsert(): "usar el valor entrante de esta columna en ESTA
# fila" — VALUES(col) en MySQL, EXCLUDED.col en PostgreSQL/sqlite.
INSERTED = object()


def _bind(obj):
    """Acepta engine/connection/bind o Session y devuelve algo con .dialect."""
    get_bind = getattr(obj, "get_bind", None)
    return get_bind() if get_bind is not None else obj


def is_mysql(bind) -> bool:
    return _bind(bind).dialect.name in ("mysql", "mariadb")


def is_postgres(bind) -> bool:
    return _bind(bind).dialect.name == "postgresql"


def quote_ident(bind, name: str) -> str:
    """Quoting INCONDICIONAL de un identificador según el dialecto
    (backticks en MySQL, comillas dobles en PostgreSQL/sqlite)."""
    return _bind(bind).dialect.identifier_preparer.quote_identifier(name)


def placeholder(bind) -> str:
    """Placeholder posicional del DBAPI para exec_driver_sql: MySQLdb y
    psycopg usan %s, sqlite3 usa ? (mismo criterio que el INSERT masivo de
    signal_backfill_range)."""
    return "?" if _bind(bind).dialect.paramstyle == "qmark" else "%s"


def _table_of(target) -> sa.Table:
    insp = sa.inspect(target)
    return insp if isinstance(insp, sa.Table) else insp.local_table


def _conflict_cols(table: sa.Table, sample: dict) -> list[str]:
    """Columnas del ON CONFLICT (PG/sqlite): la PK si la fila insertada la
    trae completa; si no (PK autoincremental ausente de values, como el `id`
    sustituto de fundamental_quarterly/group_scores), la primera
    UniqueConstraint cubierta por los valores. Es el equivalente al
    comportamiento de MySQL, donde ON DUPLICATE KEY UPDATE dispara con
    CUALQUIER clave única (PK o UNIQUE).

    (prices ya NO es ejemplo de esto: su PK pasó a (asset_id, date) en la
    0089 y ahora la trae completa en cada insert — el fallback se queda por
    las otras tablas con id sustituto.)"""
    pk = [c.name for c in table.primary_key]
    if pk and all(c in sample for c in pk):
        return pk
    for cons in table.constraints:
        if isinstance(cons, sa.UniqueConstraint):
            cols = [c.name for c in cons.columns]
            if cols and all(c in sample for c in cols):
                return cols
    return pk


def _dedupe_last(values: list, keys: list[str]) -> list:
    """Colapsa filas con la misma clave de conflicto quedándose con la ÚLTIMA
    (semántica de MySQL ON DUPLICATE KEY: dentro de un mismo statement, la
    última fila de cada clave gana). PostgreSQL y sqlite, en cambio, ABORTAN
    con CardinalityViolation ("ON CONFLICT DO UPDATE command cannot affect row
    a second time") si un INSERT propone dos filas con la misma clave única —
    así que su rama tiene que deduplicar para replicar lo observable en MySQL.
    Preserva el orden de primera aparición de cada clave (dict conserva la
    posición al reasignar). Sin cambios si no hay duplicados."""
    if not keys:
        return values
    seen: dict = {}
    for row in values:
        seen[tuple(row[k] for k in keys)] = row
    return list(seen.values()) if len(seen) < len(values) else values


def upsert(bind, target, values, update: dict):
    """INSERT ... upsert portable sobre la clave única de `target`.

    target: Table o modelo ORM. values: dict o lista de dicts (multi-fila).
    update: {columna: valor} a aplicar cuando la fila ya existe; el sentinel
    INSERTED significa "el valor entrante de esa columna" (VALUES(col) en
    MySQL, EXCLUDED.col en PG/sqlite). En MySQL compila al mismo SQL que el
    viejo on_duplicate_key_update (paridad fijada en test_db_compat).

    En la rama PG/sqlite un lote con la misma clave de conflicto repetida se
    deduplica (última gana, ver _dedupe_last) — MySQL lo tolera nativamente,
    PG/sqlite abortarían el statement entero."""
    name = _bind(bind).dialect.name
    if name in ("mysql", "mariadb"):
        stmt = _mysql_insert(target).values(values)
        return stmt.on_duplicate_key_update(**{
            c: (getattr(stmt.inserted, c) if v is INSERTED else v)
            for c, v in update.items()})
    ins = _pg_insert if name == "postgresql" else _sqlite_insert
    sample = values[0] if isinstance(values, (list, tuple)) else values
    conflict = _conflict_cols(_table_of(target), sample)
    if isinstance(values, (list, tuple)):
        values = _dedupe_last(values, conflict)
    stmt = ins(target).values(values)
    return stmt.on_conflict_do_update(
        index_elements=conflict,
        set_={c: (getattr(stmt.excluded, c) if v is INSERTED else v)
              for c, v in update.items()})


def upsert_sql(bind, table: str, columns: tuple, update_cols: tuple,
               pk_cols: tuple, quote_table: bool = False) -> str:
    """SQL crudo de upsert para exec_driver_sql (executemany en los caminos
    calientes, donde la compilación de SQLAlchemy por fila pesa — ver
    _write_ind_series). La variante MySQL es byte-idéntica a la histórica;
    quote_table replica si el call site original quoteaba el nombre.
    pk_cols: destino del ON CONFLICT en PG/sqlite (la PK de la tabla)."""
    b = _bind(bind)
    tbl = quote_ident(b, table) if quote_table or not is_mysql(b) else table
    cols = ", ".join(columns)
    ph = ", ".join([placeholder(b)] * len(columns))
    if is_mysql(b):
        sets = ", ".join(f"{c} = VALUES({c})" for c in update_cols)
        return (f"INSERT INTO {tbl} ({cols}) VALUES ({ph})"
                f" ON DUPLICATE KEY UPDATE {sets}")
    sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
    return (f"INSERT INTO {tbl} ({cols}) VALUES ({ph})"
            f" ON CONFLICT ({', '.join(pk_cols)}) DO UPDATE SET {sets}")


# Códigos que el motor espera que la APLICACIÓN resuelva reintentando la
# transacción completa (no son bugs: resultado esperado de escrituras
# concurrentes contra las mismas tablas). Patrón de uso en
# fundamental_service._fund_worker y signal_backfill_range._flush.
_MYSQL_RETRYABLE_ERRNOS = frozenset({
    1205,  # "Lock wait timeout exceeded"
    1213,  # "Deadlock found when trying to get lock"
})
_PG_RETRYABLE_SQLSTATES = frozenset({
    "40001",  # serialization_failure
    "40P01",  # deadlock_detected
    "55P03",  # lock_not_available (lock_timeout)
})


def is_retryable_lock_error(exc: BaseException) -> bool:
    """True si `exc` (envuelta por SQLAlchemy, con .orig del DBAPI) es un
    deadlock/lock-timeout que amerita reintentar la transacción. MySQLdb
    señala por errno en args[0]; psycopg2 por .pgcode y psycopg3 por
    .sqlstate (SQLSTATE de 5 caracteres)."""
    orig = getattr(exc, "orig", None)
    if orig is None:
        return False
    args = getattr(orig, "args", None)
    if args and args[0] in _MYSQL_RETRYABLE_ERRNOS:
        return True
    state = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)
    return state in _PG_RETRYABLE_SQLSTATES


def order_desc_nulls_last(col):
    """Claves de ORDER BY para "col DESC con NULLs al final" en todos los
    motores. MySQL ya pone los NULLs al final en DESC, pero PostgreSQL los
    pone PRIMERO (arruinaría el ranking) y MariaDB no soporta NULLS LAST —
    la clave extra (col IS NULL) ASC es portable: false/0 < true/1 en los
    tres motores, y en MySQL no cambia el resultado.

    Uso: .order_by(*order_desc_nulls_last(t.c.score))"""
    return col.is_(None).asc(), col.desc()


def ci_equals(col, value: str):
    """Igualdad case-insensitive portable: LOWER(col) = lower(valor).

    En MySQL la collation utf8mb4_*_ci ya comparaba sin distinguir
    mayúsculas (esto no cambia resultados); en PostgreSQL '=' es
    case-sensitive y sin esto los lookups de login/keys/aliases dejan de
    matchear filas escritas con otro caso. La insensibilidad a ACENTOS de
    la collation de MySQL NO se replica en PG (á != a) — asumido.
    Solo para lookups puntuales sobre tablas chicas: LOWER(col) impide
    usar el índice de la columna."""
    return sa.func.lower(col) == (value or "").lower()


def supports_truncate(bind) -> bool:
    """TRUNCATE TABLE existe en MySQL/MariaDB y PostgreSQL (en PG es además
    transaccional); sqlite no lo tiene."""
    return _bind(bind).dialect.name in ("mysql", "mariadb", "postgresql")


def wipe_table(session, table_name: str) -> None:
    """Vacía una tabla entera: TRUNCATE donde existe (instantáneo, sin filas
    muertas que purgar), DELETE FROM en sqlite (tests)."""
    if supports_truncate(session):
        session.execute(sa.text(f"TRUNCATE TABLE {table_name}"))
    else:
        session.execute(sa.text(f"DELETE FROM {table_name}"))


def list_tables_by_prefix(bind, *prefixes: str) -> list[str]:
    """Nombres de tablas existentes que empiezan con alguno de los prefijos,
    vía inspector de SQLAlchemy — portable, reemplaza los SELECT a
    information_schema con DATABASE() (MySQL-only)."""
    insp = sa.inspect(_bind(bind))
    return sorted(n for n in insp.get_table_names()
                  if any(n.startswith(p) for p in prefixes))


def approx_table_rows(session, prefix: str) -> dict[str, int]:
    """{tabla: filas estimadas} para las tablas cuyo nombre empieza con
    `prefix`. Estimación de catálogo (instantánea): un COUNT(*) exacto
    escanea millones de filas por tabla y bajo carga tarda minutos. En
    sqlite (tests, tablas chicas) sí es COUNT exacto."""
    b = _bind(session)
    if is_mysql(b):
        rows = session.execute(sa.text(
            "SELECT table_name, table_rows FROM information_schema.tables"
            " WHERE table_schema = DATABASE() AND table_name LIKE :pat"),
            {"pat": prefix + "%"}).fetchall()
        return {r[0]: int(r[1] or 0) for r in rows}
    if is_postgres(b):
        rows = session.execute(sa.text(
            "SELECT relname, GREATEST(reltuples, 0)::bigint"
            " FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
            " WHERE n.nspname = current_schema() AND c.relkind = 'r'"
            " AND c.relname LIKE :pat"),
            {"pat": prefix + "%"}).fetchall()
        return {r[0]: int(r[1] or 0) for r in rows}
    return {t: session.execute(sa.text(f"SELECT COUNT(*) FROM {t}")).scalar() or 0
            for t in list_tables_by_prefix(b, prefix)}


def table_write_stats(session) -> dict[str, tuple[int, int, int]] | None:
    """{tabla: (n_tup_ins, n_tup_upd, n_tup_del)} — contadores ACUMULADOS de
    escritura del motor, para el reporte de escrituras por corrida (Centro de
    Datos): un snapshot antes y otro después de una corrida, restados, dicen
    cuántas filas insertó/actualizó/borró en cada tabla.

    Solo PostgreSQL (pg_stat_user_tables). MySQL/MariaDB no expone contadores
    por tabla sin el plugin userstat, y sqlite no los tiene: devuelven None y
    el reporte muestra "no disponible en este motor" — preferible a un número
    inventado."""
    b = _bind(session)
    if not is_postgres(b):
        return None
    rows = session.execute(sa.text(
        "SELECT relname, n_tup_ins, n_tup_upd, n_tup_del"
        " FROM pg_stat_user_tables")).fetchall()
    return {r[0]: (int(r[1] or 0), int(r[2] or 0), int(r[3] or 0))
            for r in rows}
