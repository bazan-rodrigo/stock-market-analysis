"""Regime detail: agrega nascent_bars y strong_slope_multiplier a regime_config

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("regime_config", sa.Column("nascent_bars",            sa.Integer(), nullable=False, server_default="20"))
    op.add_column("regime_config", sa.Column("strong_slope_multiplier", sa.Float(),   nullable=False, server_default="2.0"))


def downgrade():
    op.drop_column("regime_config", "nascent_bars")
    op.drop_column("regime_config", "strong_slope_multiplier")
