"""currency iso_code optional

Revision ID: 0025
Revises: 0024
Create Date: 2026-04-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "currencies",
        "iso_code",
        existing_type=sa.String(10),
        nullable=True,
    )


def downgrade():
    op.alter_column(
        "currencies",
        "iso_code",
        existing_type=sa.String(10),
        nullable=False,
    )
