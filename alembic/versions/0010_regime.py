"""Regime: tabla regime_config y zonas JSON en screener_snapshot

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "regime_config",
        sa.Column("id",              sa.Integer(),  primary_key=True),
        sa.Column("fast_period",     sa.Integer(),  nullable=False, server_default="50"),
        sa.Column("slow_period",     sa.Integer(),  nullable=False, server_default="200"),
        sa.Column("lateral_band_pct",sa.Float(),    nullable=False, server_default="2.0"),
        mysql_charset="utf8mb4",
    )
    op.execute("INSERT INTO regime_config (id, fast_period, slow_period, lateral_band_pct) VALUES (1, 50, 200, 2.0)")

    op.add_column("screener_snapshot", sa.Column("regime_zones_d", sa.Text(), nullable=True))
    op.add_column("screener_snapshot", sa.Column("regime_zones_w", sa.Text(), nullable=True))
    op.add_column("screener_snapshot", sa.Column("regime_zones_m", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("screener_snapshot", "regime_zones_m")
    op.drop_column("screener_snapshot", "regime_zones_w")
    op.drop_column("screener_snapshot", "regime_zones_d")
    op.drop_table("regime_config")
