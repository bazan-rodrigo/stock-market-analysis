"""drop active from assets and price_sources

Revision ID: 0026
Revises: 0025
Create Date: 2026-04-19
"""
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column("assets", "active")
    op.drop_column("price_sources", "active")


def downgrade():
    import sqlalchemy as sa
    op.add_column("assets",
        sa.Column("active", sa.Boolean(), nullable=False, server_default="1"))
    op.add_column("price_sources",
        sa.Column("active", sa.Boolean(), nullable=False, server_default="1"))
