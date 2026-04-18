"""Regime v2: reemplaza esquema de config con algoritmo EMA+pendiente

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column("regime_config", "fast_period")
    op.drop_column("regime_config", "slow_period")
    op.drop_column("regime_config", "lateral_band_pct")

    op.add_column("regime_config", sa.Column("ema_period_d",       sa.Integer(), nullable=False, server_default="200"))
    op.add_column("regime_config", sa.Column("ema_period_w",       sa.Integer(), nullable=False, server_default="50"))
    op.add_column("regime_config", sa.Column("ema_period_m",       sa.Integer(), nullable=False, server_default="20"))
    op.add_column("regime_config", sa.Column("slope_lookback",     sa.Integer(), nullable=False, server_default="20"))
    op.add_column("regime_config", sa.Column("slope_threshold_pct",sa.Float(),   nullable=False, server_default="0.5"))
    op.add_column("regime_config", sa.Column("confirm_bars",       sa.Integer(), nullable=False, server_default="3"))


def downgrade():
    for col in ("ema_period_d", "ema_period_w", "ema_period_m",
                "slope_lookback", "slope_threshold_pct", "confirm_bars"):
        op.drop_column("regime_config", col)
    op.add_column("regime_config", sa.Column("fast_period",      sa.Integer(), nullable=False, server_default="50"))
    op.add_column("regime_config", sa.Column("slow_period",      sa.Integer(), nullable=False, server_default="200"))
    op.add_column("regime_config", sa.Column("lateral_band_pct", sa.Float(),   nullable=False, server_default="2.0"))
