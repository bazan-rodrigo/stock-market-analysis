"""Poblar signal_values_wide / strategy_results_wide desde sig_{id}/strat_res_{id}.

Cutover a tablas anchas de señales/estrategias (docs/notes/design_sig_wide_tables.md,
fase 4): agrega una columna por señal (sig_{id}) y dos por estrategia
(strat_{id}_score, strat_{id}_pct) a las tablas base (creadas vacías en la 0091)
y copia byte a byte los scores. NO borra las sig_{id}/strat_res_{id} viejas —
quedan como red de rollback y se dropean en la 0094 (fase 5), tras validar.

MERGE EN PYTHON, sin bloat (igual que la 0078 de indicadores): arma la fila
completa por (asset_id, date) juntando todas las señales/estrategias y la INSERTA
una sola vez, en vez de INSERT ... ON CONFLICT por entidad (que bloatearía ~Nx
en Postgres). Chunked por activo. Descubre las tablas dinámicas del catálogo
(las columnas anchas dependen de qué señales/estrategias existen). Portable
MySQL/PostgreSQL.

Migración de DATOS (usa op.get_bind()): NO se renderiza offline. El guard de
as_sql la salta en el meta-test de portabilidad; se verifica en real.

Revision ID: 0093
Revises: 0092
"""
import re

import sqlalchemy as sa
from alembic import op

revision = "0093"
down_revision = "0092"
branch_labels = None
depends_on = None

_SIG_RE   = re.compile(r"^sig_(\d+)$")
_STRAT_RE = re.compile(r"^strat_res_(\d+)$")

_ASSET_BATCH  = 100      # activos por lote (acota memoria del merge y el lock)
_INSERT_BATCH = 5000     # filas por executemany

SIG_WIDE   = "signal_values_wide"
STRAT_WIDE = "strategy_results_wide"


def _q(bind, name: str) -> str:
    return f"`{name}`" if bind.dialect.name in ("mysql", "mariadb") else f'"{name}"'


def _dynamic_tables(bind):
    sig, strat = {}, {}
    for name in sa.inspect(bind).get_table_names():
        m = _SIG_RE.match(name)
        if m:
            sig[int(m.group(1))] = name
        m = _STRAT_RE.match(name)
        if m:
            strat[int(m.group(1))] = name
    return sig, strat


def _existing_cols(bind, table: str) -> set:
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def _add_columns(bind, table: str, cols: list) -> None:
    # Float(precision=24) = REAL (4 B) en PG, FLOAT en MySQL — idéntico a
    # signal_store.ensure_sig_column/ensure_strat_columns.
    ftype = sa.Float(precision=24).compile(dialect=bind.dialect)
    existing = _existing_cols(bind, table)
    for c in cols:
        if c not in existing:
            bind.execute(sa.text(
                f"ALTER TABLE {_q(bind, table)} ADD COLUMN {_q(bind, c)} {ftype}"))


def _pivot(bind, ph: str, wide: str, sources: list) -> None:
    """sources: [(src_table, [(src_col, dest_col), ...])]. Junta las columnas de
    cada tabla per-entidad en la fila ancha por (asset_id, date) y la inserta una
    sola vez (sin bloat)."""
    dest_cols = [dc for _src, pairs in sources for _sc, dc in pairs]
    if not dest_cols:
        return
    all_cols = ["asset_id", "date"] + dest_cols
    col_sql = ", ".join(_q(bind, c) for c in all_cols)
    insert_sql = (f"INSERT INTO {_q(bind, wide)} ({col_sql}) "
                  f"VALUES ({', '.join([ph] * len(all_cols))})")

    # offset de cada fuente dentro de la fila mergeada
    offsets, off = [], 0
    for _src, pairs in sources:
        offsets.append(off)
        off += len(pairs)

    ids = set()
    for src, _pairs in sources:
        for (aid,) in bind.execute(sa.text(
                f"SELECT DISTINCT asset_id FROM {_q(bind, src)}")):
            ids.add(aid)
    ids = sorted(ids)

    for i in range(0, len(ids), _ASSET_BATCH):
        batch = ids[i:i + _ASSET_BATCH]
        merged: dict = {}   # (asset_id, date) -> [None] * len(dest_cols)
        for (src, pairs), base in zip(sources, offsets):
            src_cols = [sc for sc, _dc in pairs]
            sel = sa.text(
                f"SELECT asset_id, date, "
                f"{', '.join(_q(bind, c) for c in src_cols)} "
                f"FROM {_q(bind, src)} WHERE asset_id IN :ids"
            ).bindparams(sa.bindparam("ids", expanding=True))
            for r in bind.execute(sel, {"ids": batch}):
                aid, d = r[0], r[1]
                row = merged.get((aid, d))
                if row is None:
                    row = [None] * len(dest_cols)
                    merged[(aid, d)] = row
                for k, v in enumerate(r[2:]):
                    row[base + k] = v
        rows = [(aid, d, *vals) for (aid, d), vals in merged.items()]
        for k in range(0, len(rows), _INSERT_BATCH):
            bind.exec_driver_sql(insert_sql, rows[k:k + _INSERT_BATCH])


def upgrade() -> None:
    if op.get_context().as_sql:
        return  # datos: no se renderiza offline
    bind = op.get_bind()
    ph = "?" if bind.dialect.paramstyle == "qmark" else "%s"
    sig_tables, strat_tables = _dynamic_tables(bind)

    # ── Señales: una columna sig_{id} por tabla ──────────────────────────────
    sig_ids = sorted(sig_tables)
    if sig_ids:
        _add_columns(bind, SIG_WIDE, [f"sig_{i}" for i in sig_ids])
        bind.execute(sa.text(f"DELETE FROM {_q(bind, SIG_WIDE)}"))  # re-run limpio
        _pivot(bind, ph, SIG_WIDE,
               [(sig_tables[i], [("score", f"sig_{i}")]) for i in sig_ids])

    # ── Estrategias: dos columnas (score, pct) por tabla ─────────────────────
    strat_ids = sorted(strat_tables)
    if strat_ids:
        cols = []
        for i in strat_ids:
            cols += [f"strat_{i}_score", f"strat_{i}_pct"]
        _add_columns(bind, STRAT_WIDE, cols)
        bind.execute(sa.text(f"DELETE FROM {_q(bind, STRAT_WIDE)}"))
        _pivot(bind, ph, STRAT_WIDE,
               [(strat_tables[i],
                 [("score", f"strat_{i}_score"), ("pct", f"strat_{i}_pct")])
                for i in strat_ids])


def downgrade() -> None:
    if op.get_context().as_sql:
        return
    bind = op.get_bind()
    # Las sig_{id}/strat_res_{id} siguen intactas → vaciar las anchas y devolver
    # las tablas base a su estado de la 0091 (solo asset_id, date).
    for wide in (SIG_WIDE, STRAT_WIDE):
        bind.execute(sa.text(f"DELETE FROM {_q(bind, wide)}"))
        for c in sorted(_existing_cols(bind, wide) - {"asset_id", "date"}):
            bind.execute(sa.text(
                f"ALTER TABLE {_q(bind, wide)} DROP COLUMN {_q(bind, c)}"))
