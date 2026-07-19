"""Persistencia de corridas de backtest de cartera (nivel D — comparar).

portfolio_run = snapshot de una corrida (config + KPIs por sub-modo);
portfolio_run_point = serie de equity por sub-modo (gated/ranking/benchmark).
Sólo DDL portable, renderizable offline contra MySQL y PostgreSQL.

Revision ID: 0084
Revises: 0083
"""
import sqlalchemy as sa
from alembic import op

revision = "0084"
down_revision = "0083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_run",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("strategy_id", sa.Integer()),
        sa.Column("name", sa.String(120)),
        sa.Column("config", sa.Text()),
        sa.Column("summary", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "portfolio_run_point",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(),
                  sa.ForeignKey("portfolio_run.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("submode", sa.String(12)),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("value", sa.Float()),
    )


def downgrade() -> None:
    op.drop_table("portfolio_run_point")
    op.drop_table("portfolio_run")
