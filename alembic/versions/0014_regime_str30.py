"""Amplía regime_d/w/m de String(10) a String(30)

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("screener_snapshot") as batch_op:
        batch_op.alter_column("regime_d", type_=sa.String(30), existing_nullable=True)
        batch_op.alter_column("regime_w", type_=sa.String(30), existing_nullable=True)
        batch_op.alter_column("regime_m", type_=sa.String(30), existing_nullable=True)


def downgrade():
    with op.batch_alter_table("screener_snapshot") as batch_op:
        batch_op.alter_column("regime_d", type_=sa.String(10), existing_nullable=True)
        batch_op.alter_column("regime_w", type_=sa.String(10), existing_nullable=True)
        batch_op.alter_column("regime_m", type_=sa.String(10), existing_nullable=True)
