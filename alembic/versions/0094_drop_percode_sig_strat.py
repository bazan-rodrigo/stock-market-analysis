"""Fase 5: DROP de las tablas sig_{id}/strat_res_{id} (ya viven en las anchas).

Cierre del refactor a tablas anchas de señales/estrategias
(docs/notes/design_sig_wide_tables.md): los scores están en signal_values_wide /
strategy_results_wide (0091/0093) y el código los lee/escribe cuando
use_wide_signal_tables() está ON. Este DROP es el PUNTO DE NO RETORNO: libera el
espacio (las señales eran ~50% de la base). APLICAR SOLO tras validar el modo
ancho en Railway (flag ON, señales/rankings/backtests idénticos).

Las tablas son DINÁMICAS (una por señal/estrategia, ids desconocidos en tiempo de
render) → se descubren del catálogo, así que upgrade NO renderiza offline (guard
as_sql, como las migraciones de datos). El downgrade recrea el esquema per-entidad
(idéntico a signal_store._build) y lo repuebla desde las columnas anchas.

Revision ID: 0094
Revises: 0093
"""
import re

import sqlalchemy as sa
from alembic import op

revision = "0094"
down_revision = "0093"
branch_labels = None
depends_on = None

_SIG_RE          = re.compile(r"^sig_(\d+)$")
_STRAT_RE        = re.compile(r"^strat_res_(\d+)$")
_SIG_COL_RE      = re.compile(r"^sig_(\d+)$")
_STRAT_SCORE_RE  = re.compile(r"^strat_(\d+)_score$")

SIG_WIDE   = "signal_values_wide"
STRAT_WIDE = "strategy_results_wide"


def _q(bind, name: str) -> str:
    return f"`{name}`" if bind.dialect.name in ("mysql", "mariadb") else f'"{name}"'


def upgrade() -> None:
    if op.get_context().as_sql:
        return  # tablas dinámicas: descubiertas del catálogo, no offline
    bind = op.get_bind()
    for name in sorted(sa.inspect(bind).get_table_names()):
        if _SIG_RE.match(name) or _STRAT_RE.match(name):
            op.drop_table(name)


def _create_percode(name: str, *, with_pct: bool) -> None:
    """Esquema idéntico a signal_store._build: PK (date, asset_id), índice
    secundario (asset_id, date), score (y pct) float4, sin FK."""
    cols = [
        sa.Column("asset_id", sa.Integer, nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("score", sa.Float(precision=24),
                  nullable=not with_pct),
    ]
    if with_pct:
        cols.append(sa.Column("pct", sa.Float(precision=24)))
    op.create_table(name, *cols,
                    sa.PrimaryKeyConstraint("date", "asset_id"))
    op.create_index(f"ix_{name}_asset_date", name, ["asset_id", "date"])


def downgrade() -> None:
    if op.get_context().as_sql:
        return
    bind = op.get_bind()

    sig_cols = {c["name"] for c in sa.inspect(bind).get_columns(SIG_WIDE)}
    strat_cols = {c["name"] for c in sa.inspect(bind).get_columns(STRAT_WIDE)}
    sig_ids = sorted(int(m.group(1)) for c in sig_cols
                     if (m := _SIG_COL_RE.match(c)))
    strat_ids = sorted(int(m.group(1)) for c in strat_cols
                       if (m := _STRAT_SCORE_RE.match(c)))

    for i in sig_ids:
        name = f"sig_{i}"
        _create_percode(name, with_pct=False)
        bind.execute(sa.text(
            f"INSERT INTO {_q(bind, name)} (asset_id, date, score) "
            f"SELECT asset_id, date, {_q(bind, f'sig_{i}')} FROM {_q(bind, SIG_WIDE)} "
            f"WHERE {_q(bind, f'sig_{i}')} IS NOT NULL"))

    for i in strat_ids:
        name = f"strat_res_{i}"
        _create_percode(name, with_pct=True)
        bind.execute(sa.text(
            f"INSERT INTO {_q(bind, name)} (asset_id, date, score, pct) "
            f"SELECT asset_id, date, {_q(bind, f'strat_{i}_score')}, "
            f"{_q(bind, f'strat_{i}_pct')} FROM {_q(bind, STRAT_WIDE)} "
            f"WHERE {_q(bind, f'strat_{i}_score')} IS NOT NULL"))
