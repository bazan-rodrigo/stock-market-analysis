"""markets: country_id opcional

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("markets") as batch_op:
        batch_op.alter_column("country_id", existing_type=sa.Integer(), nullable=True)


def downgrade():
    with op.batch_alter_table("markets") as batch_op:
        batch_op.alter_column("country_id", existing_type=sa.Integer(), nullable=False)
