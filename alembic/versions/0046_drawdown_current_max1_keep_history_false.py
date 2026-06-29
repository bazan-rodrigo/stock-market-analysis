"""drawdown_current y drawdown_max1 pasan a keep_history=False

Revision ID: 0046
Revises: 0045
Create Date: 2026-06-29
"""
from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DROP TABLE IF EXISTS ind_drawdown_current")
    op.execute("DROP TABLE IF EXISTS ind_drawdown_max1")
    op.execute(
        "UPDATE indicator_definitions SET keep_history = 0 "
        "WHERE code IN ('drawdown_current', 'drawdown_max1')"
    )


def downgrade():
    import sqlalchemy as sa
    op.create_table(
        "ind_drawdown_current",
        sa.Column("asset_id", sa.Integer, sa.ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("date",     sa.Date,    primary_key=True),
        sa.Column("value",    sa.Float),
    )
    op.create_table(
        "ind_drawdown_max1",
        sa.Column("asset_id", sa.Integer, sa.ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("date",     sa.Date,    primary_key=True),
        sa.Column("value",    sa.Float),
    )
    op.execute(
        "UPDATE indicator_definitions SET keep_history = 1 "
        "WHERE code IN ('drawdown_current', 'drawdown_max1')"
    )
