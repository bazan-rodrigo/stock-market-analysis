"""Volatility regime: volatility_config table + snapshot columns

Revision ID: 0017
Revises: 0016
Create Date: 2026-04-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "volatility_config",
        sa.Column("id",            sa.Integer(), primary_key=True),
        sa.Column("atr_period",    sa.Integer(), nullable=False, server_default="14"),
        sa.Column("pct_low",       sa.Float(),   nullable=False, server_default="25.0"),
        sa.Column("pct_high",      sa.Float(),   nullable=False, server_default="75.0"),
        sa.Column("pct_extreme",   sa.Float(),   nullable=False, server_default="90.0"),
        sa.Column("confirm_bars",  sa.Integer(), nullable=False, server_default="3"),
        sa.Column("dur_short_pct", sa.Float(),   nullable=False, server_default="33.0"),
        sa.Column("dur_long_pct",  sa.Float(),   nullable=False, server_default="67.0"),
    )

    # Vol regime zones (JSON) and current regime per timeframe
    op.add_column("screener_snapshot", sa.Column("vol_zones_d", sa.Text(),    nullable=True))
    op.add_column("screener_snapshot", sa.Column("vol_zones_w", sa.Text(),    nullable=True))
    op.add_column("screener_snapshot", sa.Column("vol_zones_m", sa.Text(),    nullable=True))
    op.add_column("screener_snapshot", sa.Column("vol_d",       sa.String(20), nullable=True))
    op.add_column("screener_snapshot", sa.Column("vol_w",       sa.String(20), nullable=True))
    op.add_column("screener_snapshot", sa.Column("vol_m",       sa.String(20), nullable=True))
    op.add_column("screener_snapshot", sa.Column("atr_pct_d",   sa.Float(),   nullable=True))
    op.add_column("screener_snapshot", sa.Column("atr_pct_w",   sa.Float(),   nullable=True))
    op.add_column("screener_snapshot", sa.Column("atr_pct_m",   sa.Float(),   nullable=True))


def downgrade():
    op.drop_column("screener_snapshot", "atr_pct_m")
    op.drop_column("screener_snapshot", "atr_pct_w")
    op.drop_column("screener_snapshot", "atr_pct_d")
    op.drop_column("screener_snapshot", "vol_m")
    op.drop_column("screener_snapshot", "vol_w")
    op.drop_column("screener_snapshot", "vol_d")
    op.drop_column("screener_snapshot", "vol_zones_m")
    op.drop_column("screener_snapshot", "vol_zones_w")
    op.drop_column("screener_snapshot", "vol_zones_d")
    op.drop_table("volatility_config")
