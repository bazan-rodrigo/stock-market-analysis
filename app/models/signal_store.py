"""
Almacenamiento de señales y estrategias por tabla separada.

Cada señal tiene su tabla `sig_{id}` (asset_id, date, score) y cada
estrategia su `strat_res_{id}` (asset_id, date, score, pct) — mismo patrón
que los indicadores (`ind_{code}`): recalcular una unidad es TRUNCATE de su
tabla + insertar en vacío, sin borrar-e-insertar dentro de tablas pobladas
(medido 3-5× más caro) y sin contención entre unidades.

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
    (docs/notes/design_sig_wide_tables.md). Default OFF: en fase 1 nada lee/
    escribe las anchas — el camino vivo sigue siendo sig_{id}/strat_res_{id}.
    En el cutover (fase 5) pasa a default ON, como use_wide_ind_tables."""
    return os.environ.get("USE_WIDE_SIGNAL_TABLES", "0").strip().lower() in (
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
