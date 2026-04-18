"""Screener: rsi_m (RSI mensual)

Revision ID: 0018
Revises: 0017
Create Date: 2026-04-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("screener_snapshot", sa.Column("rsi_m", sa.Float(), nullable=True))


def downgrade():
    op.drop_column("screener_snapshot", "rsi_m")
