"""remove vpvr columns from screener_snapshot and vpvr_buckets from sr_config

Revision ID: 0024
Revises: 0023
"""
from alembic import op

revision = "0024"
down_revision = "0023"


def upgrade():
    op.drop_column("screener_snapshot", "vpvr_resist_pct")
    op.drop_column("screener_snapshot", "vpvr_support_pct")
    op.drop_column("sr_config", "vpvr_buckets")
    op.drop_column("sr_config", "hvn_factor")


def downgrade():
    import sqlalchemy as sa
    op.add_column("sr_config", sa.Column("hvn_factor", sa.Float(), nullable=False, server_default="1.0"))
    op.add_column("sr_config", sa.Column("vpvr_buckets", sa.Integer(), nullable=False, server_default="100"))
    op.add_column("screener_snapshot", sa.Column("vpvr_support_pct", sa.Float(), nullable=True))
    op.add_column("screener_snapshot", sa.Column("vpvr_resist_pct", sa.Float(), nullable=True))
