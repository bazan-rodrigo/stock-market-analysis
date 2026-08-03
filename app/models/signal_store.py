"""
Almacenamiento de señales y estrategias.

HOY, y por default: **tablas anchas** — `signal_values_wide` con una columna
`sig_{id}` por señal y `strategy_results_wide` con dos por estrategia. El
cutover se hizo en la 0093/0094, que además DROPEÓ las tablas per-entidad de
las bases existentes. Para leer se usa `read_sig_table` / `read_strat_table`,
que despachan según el flag; ver la sección de tablas anchas más abajo.

El modelo PER-ENTIDAD que describe el resto de este módulo —una tabla
`sig_{id}` por señal y una `strat_res_{id}` por estrategia— sigue vivo detrás
de `USE_WIDE_SIGNAL_TABLES=0` y es el que ejercita la suite. Su ventaja era
que recalcular una unidad es TRUNCATE de su tabla + insertar en vacío, sin
borrar-e-insertar dentro de tablas pobladas (medido 3-5× más caro) y sin
contención entre unidades.

Las tablas se nombran por ID INMUTABLE, nunca por key: la key de una señal
es editable desde el ABM y el DDL de MySQL no es transaccional (commit
implícito), así que "renombrar tabla + actualizar definición" jamás podría
ser atómico. Con el id, renombrar es metadata puro.

PK (date, asset_id) — date primero: las inserciones del backfill son
cronológicas (append-only sobre el índice clustered) y las operaciones por
ventanas de fechas necesitan el prefijo (lección medida del staging: con
date al final, cada ventana hacía full scan). El índice secundario
(asset_id, date) cubre las lecturas por activo (gráfico, historial,
optimizador, backtest). Sin FK a assets: purge_assets descubre y limpia
estas tablas explícitamente (igual que ind_%), y el chequeo de FK
encarecería cada insert masivo.

Ciclo de vida: la tabla vive y muere en el mismo servicio que la
definición (save_signal/delete_signal, save_strategy/delete_strategy).
El orden de operaciones ante crash siempre deja el lado benigno:
- alta: primero la definición (commit), después CREATE — si crashea en el
  medio queda una definición sin tabla, que cualquier escritor/lector
  repara con ensure_* (checkfirst).
- baja: primero borrar definición (commit), después DROP — si crashea
  queda una tabla huérfana inofensiva, que reconcile_dynamic_tables()
  detecta y dropea.
"""
import os
import re
import threading

import sqlalchemy as sa
from sqlalchemy import (Column, Date, Float, Index, Integer, MetaData,
                        PrimaryKeyConstraint, Table)
from sqlalchemy.engine import Engine

from app.database import engine

_meta      = MetaData()
_meta_lock = threading.Lock()

_SIG_RE   = re.compile(r"^sig_(\d+)$")
_STRAT_RE = re.compile(r"^strat_res_(\d+)$")


def sig_table_name(signal_id: int) -> str:
    return f"sig_{int(signal_id)}"


def strat_table_name(strategy_id: int) -> str:
    return f"strat_res_{int(strategy_id)}"


def _build(name: str) -> Table:
    """Define la tabla en el MetaData propio (el esquema es fijo y conocido:
    no hace falta autoload como en ind_{code})."""
    if name in _meta.tables:
        return _meta.tables[name]
    with _meta_lock:
        if name in _meta.tables:
            return _meta.tables[name]
        # Float(precision=24) = precisión simple (REAL/4 B en PostgreSQL, FLOAT
        # en MySQL — neutral al motor, ver signal_store en 0088). score vive en
        # -100..100 y pct en 0..100: float4 (~7 dígitos) los cubre de sobra.
        if _SIG_RE.match(name):
            return Table(
                name, _meta,
                Column("asset_id", Integer, nullable=False),
                Column("date",     Date,    nullable=False),
                Column("score",    Float(precision=24), nullable=False),
                PrimaryKeyConstraint("date", "asset_id"),
                Index(f"ix_{name}_asset_date", "asset_id", "date"),
            )
        if _STRAT_RE.match(name):
            return Table(
                name, _meta,
                Column("asset_id", Integer, nullable=False),
                Column("date",     Date,    nullable=False),
                Column("score",    Float(precision=24)),
                # Percentil 0..100 del score en la cross-section de la fecha
                # (ver strategy_service.percent_ranks / migración 0071)
                Column("pct",      Float(precision=24)),
                PrimaryKeyConstraint("date", "asset_id"),
                Index(f"ix_{name}_asset_date", "asset_id", "date"),
            )
        raise ValueError(f"Nombre de tabla dinámica inválido: {name!r}")


def get_sig_table(signal_id: int) -> Table:
    return _build(sig_table_name(signal_id))


def get_strat_table(strategy_id: int) -> Table:
    return _build(strat_table_name(strategy_id))


def ensure_sig_table(signal_id: int, bind=None) -> Table:
    """Crea sig_{id} si no existe (checkfirst: solo consulta el catálogo si
    ya existe — no emite DDL ni commit implícito en el camino común)."""
    t = get_sig_table(signal_id)
    t.create(bind or engine, checkfirst=True)
    return t


def ensure_strat_table(strategy_id: int, bind=None) -> Table:
    t = get_strat_table(strategy_id)
    t.create(bind or engine, checkfirst=True)
    return t


def drop_sig_table(signal_id: int, bind=None) -> None:
    _drop(sig_table_name(signal_id), bind)


def drop_strat_table(strategy_id: int, bind=None) -> None:
    _drop(strat_table_name(strategy_id), bind)


def _drop(name: str, bind=None) -> None:
    t = _build(name)
    t.drop(bind or engine, checkfirst=True)
    # Sacarla del MetaData: si se recrea una definición con el mismo id
    # (import, tests), _build debe partir de cero
    with _meta_lock:
        _meta.remove(t)


def _list_dynamic_tables(bind=None) -> tuple[dict[int, str], dict[int, str]]:
    """{id: nombre} de las tablas sig_%/strat_res_% que EXISTEN en la base
    (regex estricto sobre el catálogo — no confundir con signal/strategy)."""
    from sqlalchemy import inspect
    sig, strat = {}, {}
    for name in inspect(bind or engine).get_table_names():
        m = _SIG_RE.match(name)
        if m:
            sig[int(m.group(1))] = name
        m = _STRAT_RE.match(name)
        if m:
            strat[int(m.group(1))] = name
    return sig, strat


def drop_all_percode_tables() -> list[str]:
    """Dropea todas las tablas per-entidad sig_{id}/strat_res_{id} que existan.
    En modo ancho la data vive en signal_values_wide/strategy_results_wide, así
    que las per-entidad no deben existir — pero reconcile_dynamic_tables las
    recrearía en cada arranque; el arranque en modo ancho llama a esta en su
    lugar (ver startup_service). Devuelve los nombres dropeados."""
    sig_tables, strat_tables = _list_dynamic_tables()
    dropped: list[str] = []
    for name in sorted(list(sig_tables.values()) + list(strat_tables.values())):
        _drop(name)
        dropped.append(name)
    return dropped


def reconcile_dynamic_tables(session) -> dict:
    """Red de seguridad bidireccional (el DDL de MySQL no es transaccional,
    un crash entre commit y CREATE/DROP puede dejar mitades):
    - tabla sin definición → huérfana: se dropea.
    - definición sin tabla → se crea vacía (el próximo recálculo la llena,
      igual que un activo nuevo en ind_{code}).
    Devuelve {"dropped": [nombres], "created": [nombres]}."""
    import sqlalchemy as sa
    from app.services.db_compat import quote_ident
    sig_tables, strat_tables = _list_dynamic_tables()
    # quoting por dialecto: `signal` es palabra reservada en MariaDB
    # (backticks); en PostgreSQL/sqlite el quoting es con comillas dobles
    qsig = quote_ident(session, "signal")
    sig_ids   = {i for (i,) in session.execute(sa.text(f"SELECT id FROM {qsig}"))}
    strat_ids = {i for (i,) in session.execute(sa.text("SELECT id FROM strategy"))}

    dropped, created = [], []
    for sid, name in sorted(sig_tables.items()):
        if sid not in sig_ids:
            _drop(name)
            dropped.append(name)
    for sid, name in sorted(strat_tables.items()):
        if sid not in strat_ids:
            _drop(name)
            dropped.append(name)
    for sid in sorted(sig_ids - set(sig_tables)):
        created.append(ensure_sig_table(sid).name)
    for sid in sorted(strat_ids - set(strat_tables)):
        created.append(ensure_strat_table(sid).name)
    return {"dropped": dropped, "created": created}


# ── Tablas ANCHAS de señales/estrategias (footprint) ──────────────────────────
# Optimización de footprint (docs/notes/design_sig_wide_tables.md): las señales
# son ~50% de la base (medido en Railway), ~80% overhead de fila+índice pagado N
# veces (una tabla por señal). El modelo ancho —una fila por (asset_id, date),
# una COLUMNA por señal (`sig_{id}`) / dos por estrategia (`strat_{id}_score`,
# `strat_{id}_pct`)— paga ese overhead UNA vez por fecha y hace que float4 por
# fin rinda (varias columnas float empacadas, sin el padding MAXALIGN que anula
# el ahorro en una tabla de un solo score). Mismo modelo que los indicadores
# (indicator_store._WIDE), con una diferencia: acá las columnas son DINÁMICAS
# (una por señal/estrategia, que se crean/borran en runtime) → ADD/DROP COLUMN
# en vez de CREATE/DROP TABLE.
#
# FASE 1 (fundaciones): las tablas base y las primitivas de columna existen pero
# NADA las lee/escribe todavía (use_wide_signal_tables default OFF). El cutover
# de lectura/escritura es fase 2-4 del diseño. La migración 0091 crea las tablas
# base en Railway; ensure_wide_signal_tables las materializa en bases create_all.
SIG_WIDE_TABLE   = "signal_values_wide"
STRAT_WIDE_TABLE = "strategy_results_wide"


def use_wide_signal_tables() -> bool:
    """Ruteo a las tablas anchas de señales/estrategias
    (docs/notes/design_sig_wide_tables.md). Default ON desde el cutover (fase 5):
    las sig_{id}/strat_res_{id} se dropearon (migración 0094) y el camino vivo es
    ancho. Se puede forzar per-entidad con USE_WIDE_SIGNAL_TABLES=0 (debug, o
    bases aún sin migrar/poblar). La suite lo pone en 0 en conftest (usa sqlite y
    tablas per-entidad); los tests de paridad ancha lo vuelven a 1."""
    return os.environ.get("USE_WIDE_SIGNAL_TABLES", "1").strip().lower() in (
        "1", "true", "yes", "on")


def sig_column_name(signal_id: int) -> str:
    """Columna de una señal en signal_values_wide — el mismo `sig_{id}` que hoy
    nombra su tabla per-señal (identidad por ID inmutable, ver _build)."""
    return f"sig_{int(signal_id)}"


def strat_score_column(strategy_id: int) -> str:
    return f"strat_{int(strategy_id)}_score"


def strat_pct_column(strategy_id: int) -> str:
    return f"strat_{int(strategy_id)}_pct"


def ensure_wide_signal_tables(bind=None) -> None:
    """Crea signal_values_wide / strategy_results_wide (base: solo asset_id +
    date, sin columnas de valor — se agregan por señal/estrategia con
    ensure_*_column). Idempotente (inspección por tabla). Mismo esquema que la
    migración 0091 y que las sig_{id} per-entidad: PK (date, asset_id) — date
    primero para el append cronológico del backfill —, índice secundario
    (asset_id, date) para las lecturas por activo, sin FK a assets (purge_assets
    limpia estas tablas explícitamente, igual que las per-entidad)."""
    b = bind or engine
    insp = sa.inspect(b)
    for name in (SIG_WIDE_TABLE, STRAT_WIDE_TABLE):
        if insp.has_table(name):
            continue
        tmp = MetaData()
        t = Table(
            name, tmp,
            Column("asset_id", Integer, nullable=False),
            Column("date",     Date,    nullable=False),
            PrimaryKeyConstraint("date", "asset_id"),
            Index(f"ix_{name}_asset_date", "asset_id", "date"),
        )
        tmp.create_all(b, tables=[t])


def _wide_columns(bind, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(bind or engine).get_columns(table)}


def _run_ddl(bind, statements: list[str]) -> None:
    """Ejecuta ALTER TABLE (DDL) sobre un Engine o Connection. Con Engine abre
    una transacción propia (begin) — en Connection/Session el llamador controla
    el commit (patrón de ensure_sig_table(bind=s.connection()))."""
    if not statements:
        return
    b = bind or engine
    if isinstance(b, Engine):
        with b.begin() as conn:
            for st in statements:
                conn.execute(sa.text(st))
    else:
        for st in statements:
            b.execute(sa.text(st))


def _alter_add(bind, table: str, cols: list[tuple[str, object]]) -> None:
    """ADD COLUMN de las columnas faltantes (checkfirst por introspección: no
    depende de ADD COLUMN IF NOT EXISTS, que MySQL 8 no tiene). El tipo se
    compila por dialecto (Float(precision=24) → REAL en PG, FLOAT en MySQL)."""
    from app.services.db_compat import quote_ident
    b = bind or engine
    existing = _wide_columns(b, table)
    stmts = []
    for name, ctype in cols:
        if name in existing:
            continue
        type_sql = ctype.compile(dialect=b.dialect)
        stmts.append(f"ALTER TABLE {quote_ident(b, table)} "
                     f"ADD COLUMN {quote_ident(b, name)} {type_sql}")
    _run_ddl(b, stmts)


def _alter_drop(bind, table: str, names: list[str]) -> None:
    """DROP COLUMN de las que existan (checkfirst). En PostgreSQL el espacio no
    se libera hasta reescribir la tabla (el rebuild completo la recrea con las
    columnas vivas — ver design_sig_wide_tables.md)."""
    from app.services.db_compat import quote_ident
    b = bind or engine
    existing = _wide_columns(b, table)
    stmts = [f"ALTER TABLE {quote_ident(b, table)} "
             f"DROP COLUMN {quote_ident(b, name)}"
             for name in names if name in existing]
    _run_ddl(b, stmts)


# Float(precision=24) = precisión simple: REAL (4 B) en PG, FLOAT en MySQL. score
# vive en -100..100 y pct en 0..100 → float4 (~7 dígitos) los cubre de sobra.
# En la ancha float4 SÍ rinde (varias columnas float empacadas), a diferencia de
# la tabla per-señal de un solo score (ver #4 en project_reduccion_footprint).
def ensure_sig_column(signal_id: int, bind=None) -> None:
    _alter_add(bind, SIG_WIDE_TABLE,
               [(sig_column_name(signal_id), Float(precision=24))])


def drop_sig_column(signal_id: int, bind=None) -> None:
    _alter_drop(bind, SIG_WIDE_TABLE, [sig_column_name(signal_id)])


def ensure_strat_columns(strategy_id: int, bind=None) -> None:
    _alter_add(bind, STRAT_WIDE_TABLE, [
        (strat_score_column(strategy_id), Float(precision=24)),
        (strat_pct_column(strategy_id),   Float(precision=24)),
    ])


def drop_strat_columns(strategy_id: int, bind=None) -> None:
    _alter_drop(bind, STRAT_WIDE_TABLE, [
        strat_score_column(strategy_id), strat_pct_column(strategy_id)])


def sig_columns(signal_ids) -> list[str]:
    return [sig_column_name(sid) for sid in signal_ids]


def strat_columns(strategy_ids) -> list[str]:
    """Columnas de valor de las estrategias, en orden score,pct por estrategia."""
    cols: list[str] = []
    for sid in strategy_ids:
        cols.append(strat_score_column(sid))
        cols.append(strat_pct_column(sid))
    return cols


# ── Escritura/lectura de las anchas (cutover, fases 2-4) ───────────────────────
# El cómputo NO cambia (los evaluadores son los mismos): solo cambia el blanco de
# persistencia. La semántica per-columna espeja la per-entidad:
#   - DELETE de fila (per-entidad) → NULL de columna (ancha): limpia un score que
#     dejó de puntuar sin tocar las columnas de otras señales/estrategias.
#   - INSERT/UPSERT per-tabla → UPSERT/INSERT de la fila ancha (una fila por
#     (activo,fecha), todas las columnas del alcance).
# Un rebuild TOTAL (todo el alcance) trunca la tabla y hace INSERT plano (sin
# conflicto → sin bloat, Opción B de indicadores); un alcance PARCIAL (una
# estrategia, una señal) o el delta hacen NULL de columnas + UPSERT (paga bloat
# de tuplas muertas que recupera autovacuum — ver design_sig_wide_tables.md).

def _q(bind, name: str) -> str:
    from app.services.db_compat import quote_ident
    return quote_ident(bind, name)


def wide_null_columns(session, table: str, columns, dates) -> None:
    """UPDATE table SET col=NULL,... WHERE date IN (dates). Equivalente por
    columna al DELETE de fila del camino per-entidad en el delta."""
    columns = list(columns)
    if not columns or not dates:
        return
    sets = ", ".join(f"{_q(session, c)} = NULL" for c in columns)
    dates_in = ", ".join(f"'{d}'" for d in dates)
    session.execute(sa.text(
        f"UPDATE {_q(session, table)} SET {sets} WHERE date IN ({dates_in})"))


def wide_null_columns_ranges(session, table: str, columns, windows) -> None:
    """NULL de columnas por VENTANAS de fechas que avanzan (force con horizonte,
    convención delete_by_ranges). windows: [(d0, d1), ...] como strings."""
    columns = list(columns)
    if not columns or not windows:
        return
    sets = ", ".join(f"{_q(session, c)} = NULL" for c in columns)
    qtbl = _q(session, table)
    for d0, d1 in windows:
        session.execute(sa.text(
            f"UPDATE {qtbl} SET {sets} "
            f"WHERE date >= '{d0}' AND date <= '{d1}'"))


def wide_upsert(session, table: str, value_columns, rows) -> None:
    """UPSERT (asset_id, date, *value_columns) por executemany (exec_driver_sql):
    ON CONFLICT (date, asset_id) update de las value_columns. rows: tuplas
    posicionales (asset_id, date, *values)."""
    value_columns = list(value_columns)
    if not rows or not value_columns:
        return
    from app.services.db_compat import upsert_sql
    cols = ("asset_id", "date", *value_columns)
    stmt = upsert_sql(session, table, cols, tuple(value_columns),
                      ("date", "asset_id"), quote_table=True)
    session.connection().exec_driver_sql(stmt, rows)


def wide_insert(session, table: str, value_columns, rows) -> None:
    """INSERT plano (post-TRUNCATE: sin conflicto → sin tuplas muertas) por
    executemany. Para el rebuild total, donde cada (activo,fecha) se inserta una
    sola vez (los batches particionan las fechas)."""
    value_columns = list(value_columns)
    if not rows or not value_columns:
        return
    from app.services.db_compat import placeholder
    cols = ("asset_id", "date", *value_columns)
    colsql = ", ".join(_q(session, c) for c in cols)
    ph = ", ".join([placeholder(session)] * len(cols))
    session.connection().exec_driver_sql(
        f"INSERT INTO {_q(session, table)} ({colsql}) VALUES ({ph})", rows)


def sig_wide_rows(sv_by_sig: dict, signal_ids) -> list[tuple]:
    """Pivota {sig_id: [(aid, d_str, score), ...]} a filas anchas
    [(aid, d_str, score_a, score_b, ...)] en el orden de signal_ids — None donde
    una señal no puntuó ese (activo,fecha)."""
    by_key: dict = {}
    for sid, rows in sv_by_sig.items():
        for aid, d_str, score in rows:
            by_key.setdefault((aid, d_str), {})[sid] = score
    signal_ids = list(signal_ids)
    return [(aid, d_str, *(scores.get(sid) for sid in signal_ids))
            for (aid, d_str), scores in by_key.items()]


def strat_wide_rows(sr_by_strat: dict, strategy_ids) -> list[tuple]:
    """Pivota {strat_id: [(aid, d_str, score, pct), ...]} a filas anchas con
    (score, pct) por estrategia en el orden de strategy_ids."""
    by_key: dict = {}
    for sid, rows in sr_by_strat.items():
        for aid, d_str, score, pct in rows:
            by_key.setdefault((aid, d_str), {})[sid] = (score, pct)
    strategy_ids = list(strategy_ids)
    out: list[tuple] = []
    for (aid, d_str), vals in by_key.items():
        flat: list = []
        for sid in strategy_ids:
            sp = vals.get(sid)
            flat.extend(sp if sp is not None else (None, None))
        out.append((aid, d_str, *flat))
    return out


def load_wide_signal_scores(session, signal_ids, d0, d1) -> list[tuple]:
    """Filas (date, asset_id, sig_id, score) de signal_values_wide para las
    señales dadas en [d0, d1], solo columnas no-NULL (as-of fiel por columna).
    Reemplaza los N reads per-tabla de strategy_only por UN scan de la ancha."""
    signal_ids = list(signal_ids)
    if not signal_ids:
        return []
    cols = [sig_column_name(sid) for sid in signal_ids]
    colsql = ", ".join(_q(session, c) for c in cols)
    not_null = " OR ".join(f"{_q(session, c)} IS NOT NULL" for c in cols)
    rows = session.execute(sa.text(
        f"SELECT date, asset_id, {colsql} FROM {_q(session, SIG_WIDE_TABLE)} "
        f"WHERE date >= :d0 AND date <= :d1 AND ({not_null})"),
        # str: las fechas se guardan/comparan como strings ISO (mismo criterio
        # que el _bulk_insert per-entidad); un objeto date no matchea la columna
        # string en sqlite, y PG/MySQL coercionan el string a DATE igual.
        {"d0": str(d0), "d1": str(d1)}).fetchall()
    out: list[tuple] = []
    for r in rows:
        dt, aid = _as_date(r[0]), r[1]
        for sid, val in zip(signal_ids, r[2:]):
            if val is not None:
                out.append((dt, aid, sid, val))
    return out


def _as_date(v):
    """Normaliza la fecha a objeto date. El SQL crudo devuelve string en sqlite
    y objeto date en PostgreSQL; el consumidor (stored_sv_by_date del modo rango)
    la usa como key contra objetos date, así que hay que unificar — el select
    TIPADO del camino per-entidad ya coercionaba a date en todos los motores."""
    import datetime as _dt
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    return _dt.datetime.strptime(str(v)[:10], "%Y-%m-%d").date()


# ── Vistas de LECTURA sobre las anchas (drop-in de la tabla per-entidad) ───────
# Espejo del _CodeView de indicadores: un objeto liviano que expone `.c.score`/
# `.c.date`/`.c.asset_id` (y `.c.pct` para estrategias) mapeados a las columnas
# de la ancha, para que los lectores existentes (sa.select(t.c.date, t.c.score)
# .where(t.c.asset_id == ...)) compilen contra la ancha SIN cambiar su forma.
# Se arma con sa.table()/sa.column() TIPADOS (sin autoload): sin query al
# catálogo, sin caché que se desactualice cuando ALTER agrega/quita columnas, y
# con coerción de tipos (fecha, float) igual que el select per-entidad.
#
# OJO (lección de indicadores, "diferencias falsas"): en la ancha la fila de un
# (activo,fecha) EXISTE aunque ESTA señal no puntúe (la escribió otra) con la
# columna en NULL — los lectores DEBEN filtrar `.where(t.c.score.isnot(None))`.
# Es no-op en las tablas per-entidad (score nunca es NULL), así que se agrega
# incondicionalmente en cada lector.

def _sig_view(sig_id: int):
    """Subquery `SELECT asset_id, date, <sig_col> AS score FROM signal_values_wide
    WHERE <sig_col> IS NOT NULL`, nombrada como la tabla. El filtro NULL va
    HORNEADO (la fila existe aunque esta señal no puntúe — la escribió otra), así
    los lectores existentes (sa.select(rt.c.date, rt.c.score).where(...)) no
    tienen que agregarlo. sa.table()/sa.column() TIPADOS: sin autoload (la ancha
    tiene columnas dinámicas), con coerción de fecha/float igual que el select
    per-entidad. Es un drop-in de la tabla sig_{id}: soporta .c, .name, join_from."""
    col = sig_column_name(sig_id)
    t = sa.table(SIG_WIDE_TABLE,
                 sa.column("asset_id", Integer),
                 sa.column("date", Date),
                 sa.column(col, Float))
    return (sa.select(t.c.asset_id, t.c.date, t.c[col].label("score"))
            .where(t.c[col].isnot(None))
            .subquery(SIG_WIDE_TABLE))


def _strat_view(strategy_id: int):
    """Ídem para una estrategia: expone score y pct (filtra por score no-NULL)."""
    sc, pc = strat_score_column(strategy_id), strat_pct_column(strategy_id)
    t = sa.table(STRAT_WIDE_TABLE,
                 sa.column("asset_id", Integer),
                 sa.column("date", Date),
                 sa.column(sc, Float),
                 sa.column(pc, Float))
    return (sa.select(t.c.asset_id, t.c.date,
                      t.c[sc].label("score"), t.c[pc].label("pct"))
            .where(t.c[sc].isnot(None))
            .subquery(STRAT_WIDE_TABLE))


def read_sig_table(session, sig_id: int):
    """Objeto para LEER una señal: subquery sobre signal_values_wide (flag ON, con
    el filtro NULL horneado) o la tabla per-entidad sig_{id} (flag OFF). Ambos
    soportan sa.select(rt.c.date, rt.c.score), .where, join_from, .name."""
    if use_wide_signal_tables():
        return _sig_view(sig_id)
    return ensure_sig_table(sig_id, bind=session.connection())


def read_strat_table(session, strategy_id: int):
    """Ídem para una estrategia (score+pct)."""
    if use_wide_signal_tables():
        return _strat_view(strategy_id)
    return ensure_strat_table(strategy_id, bind=session.connection())


# ── Ciclo de vida (alta/baja) — despacha per-entidad o ancha según el flag ─────
def ensure_signal_storage(sig_id: int, bind=None) -> None:
    """Alta de una señal: crea sig_{id} (flag OFF) o asegura la columna ancha
    (flag ON). Idempotente."""
    if use_wide_signal_tables():
        ensure_wide_signal_tables(bind=bind)
        ensure_sig_column(sig_id, bind=bind)
    else:
        ensure_sig_table(sig_id, bind=bind)


def drop_signal_storage(sig_id: int, bind=None) -> None:
    """Baja de una señal: dropea sig_{id} (checkfirst, no-op si ya no existe tras
    el cutover) y, en modo ancho, su columna."""
    drop_sig_table(sig_id, bind=bind)
    if use_wide_signal_tables():
        drop_sig_column(sig_id, bind=bind)


def ensure_strategy_storage(strategy_id: int, bind=None) -> None:
    if use_wide_signal_tables():
        ensure_wide_signal_tables(bind=bind)
        ensure_strat_columns(strategy_id, bind=bind)
    else:
        ensure_strat_table(strategy_id, bind=bind)


def drop_strategy_storage(strategy_id: int, bind=None) -> None:
    drop_strat_table(strategy_id, bind=bind)
    if use_wide_signal_tables():
        drop_strat_columns(strategy_id, bind=bind)


_STRAT_COL_RE = re.compile(r"^strat_(\d+)_(?:score|pct)$")


def reconcile_wide_columns(session) -> dict:
    """Red de seguridad de las columnas anchas (análogo de
    reconcile_dynamic_tables): asegura una columna por señal viva y dos por
    estrategia viva, y dropea las columnas de ids que ya no existen. Corre en el
    arranque en modo ancho. Devuelve {"added": [...], "dropped": [...]}."""
    from app.services.db_compat import quote_ident
    conn = session.connection()
    ensure_wide_signal_tables(bind=conn)

    qsig = quote_ident(session, "signal")
    sig_ids   = {i for (i,) in session.execute(sa.text(f"SELECT id FROM {qsig}"))}
    strat_ids = {i for (i,) in session.execute(sa.text("SELECT id FROM strategy"))}

    sig_cols   = _wide_columns(conn, SIG_WIDE_TABLE)
    strat_cols = _wide_columns(conn, STRAT_WIDE_TABLE)
    added, dropped = [], []

    for sid in sorted(sig_ids):
        if sig_column_name(sid) not in sig_cols:
            ensure_sig_column(sid, bind=conn)
            added.append(sig_column_name(sid))
    for sid in sorted(strat_ids):
        if strat_score_column(sid) not in strat_cols:
            ensure_strat_columns(sid, bind=conn)
            added.append(strat_score_column(sid))

    for col in sig_cols:
        m = _SIG_RE.match(col)
        if m and int(m.group(1)) not in sig_ids:
            _alter_drop(conn, SIG_WIDE_TABLE, [col])
            dropped.append(col)
    dead_strat = {int(m.group(1)) for col in strat_cols
                  if (m := _STRAT_COL_RE.match(col))
                  and int(m.group(1)) not in strat_ids}
    for sid in sorted(dead_strat):
        drop_strat_columns(sid, bind=conn)
        dropped.append(strat_score_column(sid))

    session.commit()
    return {"added": added, "dropped": dropped}
