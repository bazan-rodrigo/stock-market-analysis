"""nullable fixes: instrument_types.default_currency_id y countries.iso_code

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "instrument_types", "default_currency_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.alter_column(
        "countries", "iso_code",
        existing_type=sa.String(3),
        nullable=True,
    )


def downgrade():
    op.alter_column(
        "countries", "iso_code",
        existing_type=sa.String(3),
        nullable=False,
    )
    op.alter_column(
        "instrument_types", "default_currency_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
