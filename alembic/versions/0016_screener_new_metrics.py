"""Screener: rsi_w, dist_sma_d/w/m

Revision ID: 0016
Revises: 0015
Create Date: 2026-04-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("screener_snapshot", sa.Column("rsi_w",     sa.Float(), nullable=True))
    op.add_column("screener_snapshot", sa.Column("dist_sma_d", sa.Float(), nullable=True))
    op.add_column("screener_snapshot", sa.Column("dist_sma_w", sa.Float(), nullable=True))
    op.add_column("screener_snapshot", sa.Column("dist_sma_m", sa.Float(), nullable=True))


def downgrade():
    op.drop_column("screener_snapshot", "dist_sma_m")
    op.drop_column("screener_snapshot", "dist_sma_w")
    op.drop_column("screener_snapshot", "dist_sma_d")
    op.drop_column("screener_snapshot", "rsi_w")
