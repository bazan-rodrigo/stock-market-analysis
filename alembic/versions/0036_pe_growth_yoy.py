"""add pe_growth_yoy to fundamental_snapshot

Revision ID: 0036
Revises: 0035
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "fundamental_snapshot",
        sa.Column("pe_growth_yoy", sa.Float(), nullable=True),
    )


def downgrade():
    op.drop_column("fundamental_snapshot", "pe_growth_yoy")
