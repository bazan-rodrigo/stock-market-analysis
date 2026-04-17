"""screener_snapshot: agregar best_sma/ema por timeframe

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("screener_snapshot", sa.Column("best_sma_d", sa.Integer(), nullable=True))
    op.add_column("screener_snapshot", sa.Column("best_ema_d", sa.Integer(), nullable=True))
    op.add_column("screener_snapshot", sa.Column("best_sma_w", sa.Integer(), nullable=True))
    op.add_column("screener_snapshot", sa.Column("best_ema_w", sa.Integer(), nullable=True))
    op.add_column("screener_snapshot", sa.Column("best_sma_m", sa.Integer(), nullable=True))
    op.add_column("screener_snapshot", sa.Column("best_ema_m", sa.Integer(), nullable=True))


def downgrade():
    for col in ("best_sma_d", "best_ema_d", "best_sma_w", "best_ema_w", "best_sma_m", "best_ema_m"):
        op.drop_column("screener_snapshot", col)
