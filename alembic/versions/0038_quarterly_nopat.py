"""add nopat and invested_capital_avg to fundamental_quarterly

Revision ID: 0038
Revises: 0037
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("fundamental_quarterly",
                  sa.Column("nopat", sa.Float(), nullable=True))
    op.add_column("fundamental_quarterly",
                  sa.Column("invested_capital_avg", sa.Float(), nullable=True))


def downgrade():
    op.drop_column("fundamental_quarterly", "invested_capital_avg")
    op.drop_column("fundamental_quarterly", "nopat")
