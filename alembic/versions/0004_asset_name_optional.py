"""assets: name opcional

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-15
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("assets") as batch_op:
        batch_op.alter_column("name", existing_type=sa.String(200), nullable=True)


def downgrade():
    with op.batch_alter_table("assets") as batch_op:
        batch_op.alter_column("name", existing_type=sa.String(200), nullable=False)
