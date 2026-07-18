"""Poblar ind_daily/ind_weekly/ind_monthly desde las ind_{code} per-código.

Cutover a tablas anchas (docs/notes/design_ind_wide_tables.md, fase 4): copia
byte a byte cada ind_{code}.value en la columna del código en la tabla ancha de
su cadencia. NO borra las ind_{code} viejas — quedan como red de rollback y se
dropean en una migración posterior (fase 5), tras validar.

MERGE EN PYTHON, sin bloat: arma la fila completa por (asset_id, date) juntando
todos los códigos de la cadencia y la INSERTA UNA sola vez. Se evita el
INSERT ... ON CONFLICT DO UPDATE por código (que actualizaba cada fila N veces
→ N-1 tuplas muertas por fila en Postgres → bloat de ~Nx que exigía VACUUM
FULL). Chunked por activo para acotar memoria/locks a escala. Portable
MySQL/PostgreSQL (sin FULL OUTER JOIN, que MySQL no tiene).

Migración de DATOS (usa op.get_bind()): NO se renderiza offline. El guard de
as_sql la salta en el render del meta-test de portabilidad
(tests/test_bootstrap_portability); se verifica contra ambos motores en real.

Revision ID: 0078
Revises: 0077
"""
import sqlalchemy as sa
from alembic import op

revision = "0078"
down_revision = "0077"
branch_labels = None
depends_on = None

# Autocontenido (snapshot): mismas listas que la 0077 / indicator_store._WIDE_*.
_DAILY = [
    "trend_daily", "volatility_daily", "atr_percentile_daily", "rsi_daily",
    "dist_sma20", "dist_sma50", "dist_sma200", "dist_optimal_sma_daily",
    "return_daily", "return_monthly", "return_quarterly", "return_yearly",
    "return_52w", "relative_strength_52w",
]
_WEEKLY = [
    "trend_weekly", "volatility_weekly", "atr_percentile_weekly",
    "rsi_weekly", "dist_optimal_sma_weekly",
]
_MONTHLY = [
    "trend_monthly", "volatility_monthly", "atr_percentile_monthly",
    "rsi_monthly", "dist_optimal_sma_monthly",
]
_WIDE = (("ind_daily", _DAILY), ("ind_weekly", _WEEKLY), ("ind_monthly", _MONTHLY))

_ASSET_BATCH = 100      # activos por lote (acota memoria del merge y el lock)
_INSERT_BATCH = 5000    # filas por executemany


def _q(bind, name: str) -> str:
    return f"`{name}`" if bind.dialect.name in ("mysql", "mariadb") else f'"{name}"'


def _asset_ids(bind, codes: list) -> list:
    ids = set()
    for code in codes:
        for (aid,) in bind.execute(sa.text(
                f"SELECT DISTINCT asset_id FROM {_q(bind, 'ind_' + code)}")):
            ids.add(aid)
    return sorted(ids)


def upgrade() -> None:
    if op.get_context().as_sql:
        return  # datos: no se renderiza offline (ver test_bootstrap_portability)
    bind = op.get_bind()
    ph = "?" if bind.dialect.paramstyle == "qmark" else "%s"

    for wide, codes in _WIDE:
        # DELETE defensivo: primer run vacío (no-op); re-run tras fallo parcial
        # arranca limpio (evita choque de PK en el INSERT).
        bind.execute(sa.text(f"DELETE FROM {_q(bind, wide)}"))
        present = [c for c in codes if sa.inspect(bind).has_table(f"ind_{c}")]
        if not present:
            continue

        cols = ["asset_id", "date"] + present
        col_sql = ", ".join(_q(bind, c) for c in cols)
        insert_sql = (f"INSERT INTO {_q(bind, wide)} ({col_sql}) "
                      f"VALUES ({', '.join([ph] * len(cols))})")

        ids = _asset_ids(bind, present)
        for i in range(0, len(ids), _ASSET_BATCH):
            batch = ids[i:i + _ASSET_BATCH]
            merged: dict = {}   # (asset_id, date) -> [None] * len(present)
            for j, code in enumerate(present):
                sel = sa.text(
                    f"SELECT asset_id, date, value FROM {_q(bind, 'ind_' + code)} "
                    "WHERE asset_id IN :ids"
                ).bindparams(sa.bindparam("ids", expanding=True))
                for aid, d, v in bind.execute(sel, {"ids": batch}):
                    row = merged.get((aid, d))
                    if row is None:
                        row = [None] * len(present)
                        merged[(aid, d)] = row
                    row[j] = v
            rows = [(aid, d, *vals) for (aid, d), vals in merged.items()]
            for k in range(0, len(rows), _INSERT_BATCH):
                bind.exec_driver_sql(insert_sql, rows[k:k + _INSERT_BATCH])


def downgrade() -> None:
    if op.get_context().as_sql:
        return
    bind = op.get_bind()
    # Las ind_{code} viejas siguen intactas → basta vaciar las anchas.
    for wide, _codes in _WIDE:
        bind.execute(sa.text(f"DELETE FROM {_q(bind, wide)}"))
