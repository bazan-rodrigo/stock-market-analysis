"""drop ind_last_close and remove last_close indicator definition

Revision ID: 0045
Revises: 0044
Create Date: 2026-06-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DROP TABLE IF EXISTS ind_last_close")
    op.execute("DELETE FROM indicator_definitions WHERE code = 'last_close'")


def downgrade():
    op.create_table(
        "ind_last_close",
        sa.Column("asset_id", sa.Integer, sa.ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("date",     sa.Date,    primary_key=True),
        sa.Column("value",    sa.Float),
    )
