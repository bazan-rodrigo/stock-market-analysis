"""synthetic formula + components (reemplaza synthetic_asset_config)

Revision ID: 0023
Revises: 0022
"""
from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("synthetic_asset_config")

    op.create_table(
        "synthetic_formula",
        sa.Column("id",           sa.Integer(),     nullable=False),
        sa.Column("asset_id",     sa.Integer(),     nullable=False),
        sa.Column("formula_type", sa.String(20),    nullable=False),
        sa.Column("base_value",   sa.Float(),       nullable=True),
        sa.Column("base_date",    sa.Date(),        nullable=True),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id"),
    )

    op.create_table(
        "synthetic_component",
        sa.Column("id",         sa.Integer(), nullable=False),
        sa.Column("formula_id", sa.Integer(), nullable=False),
        sa.Column("asset_id",   sa.Integer(), nullable=False),
        sa.Column("role",       sa.String(20), nullable=False),
        sa.Column("weight",     sa.Float(),   nullable=False, server_default="1.0"),
        sa.ForeignKeyConstraint(["formula_id"], ["synthetic_formula.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"],   ["assets.id"],           ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("synthetic_component")
    op.drop_table("synthetic_formula")
    op.create_table(
        "synthetic_asset_config",
        sa.Column("id",                   sa.Integer(), nullable=False),
        sa.Column("asset_id",             sa.Integer(), nullable=False),
        sa.Column("numerator_asset_id",   sa.Integer(), nullable=False),
        sa.Column("denominator_asset_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id"),
    )
