"""Elimina la columna rank de strategy_result.

El rank persistido era el orden por score desc (redundante para ordenar) y su
único valor extra era el movimiento entre fechas (delta_rank); se decidió
sacarlo. El orden por score sigue dando el ranking al vuelo.

Revision ID: 0069
Revises: 0068
"""
import sqlalchemy as sa
from alembic import op

revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("strategy_result", "rank")


def downgrade() -> None:
    op.add_column("strategy_result", sa.Column("rank", sa.Integer(), nullable=True))
