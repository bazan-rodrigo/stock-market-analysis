"""benchmark_field

Revision ID: 0019
Revises: 0018
Create Date: 2026-04-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("markets", sa.Column(
        "benchmark_id", sa.Integer(),
        sa.ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
    ))
    op.add_column("assets", sa.Column(
        "benchmark_id", sa.Integer(),
        sa.ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
    ))


def downgrade():
    op.drop_column("markets", "benchmark_id")
    op.drop_column("assets",  "benchmark_id")
