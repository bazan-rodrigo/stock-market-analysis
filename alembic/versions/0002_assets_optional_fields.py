"""assets: country, market, instrument_type, currency opcionales

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("assets") as batch_op:
        batch_op.alter_column("country_id",   existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column("market_id",    existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column("instrument_type_id", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column("currency_id",  existing_type=sa.Integer(), nullable=True)


def downgrade():
    with op.batch_alter_table("assets") as batch_op:
        batch_op.alter_column("country_id",   existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("market_id",    existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("instrument_type_id", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("currency_id",  existing_type=sa.Integer(), nullable=False)
