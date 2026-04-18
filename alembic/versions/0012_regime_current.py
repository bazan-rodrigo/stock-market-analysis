"""Regime current: agrega columnas regime_d/w/m a screener_snapshot

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("screener_snapshot", sa.Column("regime_d", sa.String(10), nullable=True))
    op.add_column("screener_snapshot", sa.Column("regime_w", sa.String(10), nullable=True))
    op.add_column("screener_snapshot", sa.Column("regime_m", sa.String(10), nullable=True))


def downgrade():
    op.drop_column("screener_snapshot", "regime_d")
    op.drop_column("screener_snapshot", "regime_w")
    op.drop_column("screener_snapshot", "regime_m")
