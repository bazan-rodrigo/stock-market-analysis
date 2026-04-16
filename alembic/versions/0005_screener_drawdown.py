"""Agrega columnas de drawdown al screener_snapshot.

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-15
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("screener_snapshot", sa.Column("dd_current", sa.Float(), nullable=True))
    op.add_column("screener_snapshot", sa.Column("dd_max1",    sa.Float(), nullable=True))
    op.add_column("screener_snapshot", sa.Column("dd_max2",    sa.Float(), nullable=True))
    op.add_column("screener_snapshot", sa.Column("dd_max3",    sa.Float(), nullable=True))


def downgrade():
    op.drop_column("screener_snapshot", "dd_max3")
    op.drop_column("screener_snapshot", "dd_max2")
    op.drop_column("screener_snapshot", "dd_max1")
    op.drop_column("screener_snapshot", "dd_current")
