"""Add sr_config table

Revision ID: 0020
Revises: 0019
Create Date: 2026-04-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sr_config",
        sa.Column("id",            sa.Integer(), primary_key=True),
        sa.Column("lookback_days", sa.Integer(), nullable=False, server_default="252"),
        sa.Column("pivot_window",  sa.Integer(), nullable=False, server_default="5"),
        sa.Column("cluster_pct",   sa.Float(),   nullable=False, server_default="0.5"),
        sa.Column("min_touches",   sa.Integer(), nullable=False, server_default="2"),
        sa.Column("vpvr_buckets",  sa.Integer(), nullable=False, server_default="100"),
        sa.Column("hvn_factor",    sa.Float(),   nullable=False, server_default="1.0"),
    )


def downgrade():
    op.drop_table("sr_config")
