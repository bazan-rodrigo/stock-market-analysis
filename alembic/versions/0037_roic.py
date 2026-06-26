"""add roic to fundamental_snapshot

Revision ID: 0037
Revises: 0036
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "fundamental_snapshot",
        sa.Column("roic", sa.Float(), nullable=True),
    )


def downgrade():
    op.drop_column("fundamental_snapshot", "roic")
