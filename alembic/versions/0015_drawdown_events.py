"""Drawdown events: tabla drawdown_config + columna dd_events en screener_snapshot

Revision ID: 0015
Revises: 0014
Create Date: 2026-04-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "drawdown_config",
        sa.Column("id",            sa.Integer(), primary_key=True),
        sa.Column("min_depth_pct", sa.Float(),   nullable=False, server_default="20.0"),
    )
    op.execute("INSERT INTO drawdown_config (id, min_depth_pct) VALUES (1, 20.0)")
    op.add_column("screener_snapshot", sa.Column("dd_events", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("screener_snapshot", "dd_events")
    op.drop_table("drawdown_config")
