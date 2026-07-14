"""Columna pct en strategy_result: percentil del score en la cross-section.

Lo escriben ambos caminos del pipeline (compute_strategy_results y el modo
rango de signal_backfill_range) con strategy_service.percent_ranks — la
cross-section ya está en memoria al insertar. Reemplaza la ventana
PERCENT_RANK al leer (60s+ con historia densa). La historia existente queda
NULL: correr "Recalcular completo" de Señales y Estrategias para poblarla.

Revision ID: 0071
Revises: 0070
"""
import sqlalchemy as sa
from alembic import op

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("strategy_result", sa.Column("pct", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("strategy_result", "pct")
