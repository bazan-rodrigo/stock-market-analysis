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
import re
import threading

from sqlalchemy import (Column, Date, Float, Index, Integer, MetaData,
                        PrimaryKeyConstraint, Table)

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
        if _SIG_RE.match(name):
            return Table(
                name, _meta,
                Column("asset_id", Integer, nullable=False),
                Column("date",     Date,    nullable=False),
                Column("score",    Float,   nullable=False),
                PrimaryKeyConstraint("date", "asset_id"),
                Index(f"ix_{name}_asset_date", "asset_id", "date"),
            )
        if _STRAT_RE.match(name):
            return Table(
                name, _meta,
                Column("asset_id", Integer, nullable=False),
                Column("date",     Date,    nullable=False),
                Column("score",    Float),
                # Percentil 0..100 del score en la cross-section de la fecha
                # (ver strategy_service.percent_ranks / migración 0071)
                Column("pct",      Float),
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
    sig_tables, strat_tables = _list_dynamic_tables()
    sig_ids   = {i for (i,) in session.execute(sa.text("SELECT id FROM signal"))}
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
