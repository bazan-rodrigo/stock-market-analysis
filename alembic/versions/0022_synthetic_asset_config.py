"""synthetic asset config table

Revision ID: 0022
Revises: 0021
"""
from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "synthetic_asset_config",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("numerator_asset_id", sa.Integer(), nullable=False),
        sa.Column("denominator_asset_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"],           ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["numerator_asset_id"], ["assets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["denominator_asset_id"], ["assets.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id"),
    )


def downgrade():
    op.drop_table("synthetic_asset_config")
