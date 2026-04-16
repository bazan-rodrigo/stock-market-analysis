"""Crea tabla market_event para eventos de mercado.

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "market_event",
        sa.Column("id",         sa.Integer(),     nullable=False, autoincrement=True),
        sa.Column("name",       sa.String(200),   nullable=False),
        sa.Column("start_date", sa.Date(),        nullable=False),
        sa.Column("end_date",   sa.Date(),        nullable=False),
        sa.Column("scope",      sa.String(10),    nullable=False, server_default="global"),
        sa.Column("country_id", sa.Integer(),     nullable=True),
        sa.Column("asset_id",   sa.Integer(),     nullable=True),
        sa.Column("color",      sa.String(20),    nullable=True, server_default="#ff9800"),
        sa.ForeignKeyConstraint(["country_id"], ["countries.id"]),
        sa.ForeignKeyConstraint(["asset_id"],   ["asset.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("market_event")
