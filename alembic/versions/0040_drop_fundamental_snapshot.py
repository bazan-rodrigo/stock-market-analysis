"""Drop fundamental_snapshot table (data migrated to indicator_values EAV).

Revision ID: 0040
Revises: 0039
Create Date: 2026-06-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade():
    from sqlalchemy import inspect as _inspect
    conn = op.get_bind()
    if "fundamental_snapshot" in set(_inspect(conn).get_table_names()):
        op.drop_table("fundamental_snapshot")


def downgrade():
    op.create_table(
        "fundamental_snapshot",
        sa.Column("id",                  sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("asset_id",            sa.Integer(), nullable=False),
        sa.Column("updated_at",          sa.DateTime(), nullable=False),
        sa.Column("pe_ttm",              sa.Float(), nullable=True),
        sa.Column("pb",                  sa.Float(), nullable=True),
        sa.Column("ps_ttm",              sa.Float(), nullable=True),
        sa.Column("ev_ebitda",           sa.Float(), nullable=True),
        sa.Column("net_margin",          sa.Float(), nullable=True),
        sa.Column("gross_margin",        sa.Float(), nullable=True),
        sa.Column("operating_margin",    sa.Float(), nullable=True),
        sa.Column("debt_to_equity",      sa.Float(), nullable=True),
        sa.Column("revenue_growth_yoy",  sa.Float(), nullable=True),
        sa.Column("eps_growth_yoy",      sa.Float(), nullable=True),
        sa.Column("pe_growth_yoy",       sa.Float(), nullable=True),
        sa.Column("roic",                sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
    )
