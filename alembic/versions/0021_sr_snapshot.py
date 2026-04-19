"""Add SR/VPVR columns to screener_snapshot

Revision ID: 0021
Revises: 0020
Create Date: 2026-04-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("screener_snapshot", sa.Column("pivot_resist_pct", sa.Float(), nullable=True))
    op.add_column("screener_snapshot", sa.Column("pivot_support_pct", sa.Float(), nullable=True))
    op.add_column("screener_snapshot", sa.Column("vpvr_resist_pct", sa.Float(), nullable=True))
    op.add_column("screener_snapshot", sa.Column("vpvr_support_pct", sa.Float(), nullable=True))


def downgrade():
    op.drop_column("screener_snapshot", "vpvr_support_pct")
    op.drop_column("screener_snapshot", "vpvr_resist_pct")
    op.drop_column("screener_snapshot", "pivot_support_pct")
    op.drop_column("screener_snapshot", "pivot_resist_pct")
