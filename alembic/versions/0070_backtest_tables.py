"""Tablas del módulo de backtesting (nivel A: análisis por deciles).

backtest_run = snapshot reproducible (config JSON + resultados persistidos);
backtest_quantile_stat = resumen por horizonte×cuantil;
backtest_ic_point = serie temporal de IC/spread por fecha×horizonte.

Revision ID: 0070
Revises: 0069
"""
import sqlalchemy as sa
from alembic import op

revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "backtest_run",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("strategy_id", sa.Integer(),
                  sa.ForeignKey("strategy.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("owner_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("config", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default="running"),
        sa.Column("error", sa.Text()),
        sa.Column("date_from", sa.Date()),
        sa.Column("date_to", sa.Date()),
        sa.Column("n_dates", sa.Integer()),
        sa.Column("duration_seconds", sa.Float()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "backtest_quantile_stat",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(),
                  sa.ForeignKey("backtest_run.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("horizon", sa.Integer(), nullable=False),
        sa.Column("quantile", sa.Integer(), nullable=False),
        sa.Column("n_dates", sa.Integer(), nullable=False),
        sa.Column("mean_ret", sa.Float()),
        sa.Column("median_ret", sa.Float()),
        sa.Column("pct_pos", sa.Float()),
    )
    op.create_table(
        "backtest_ic_point",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(),
                  sa.ForeignKey("backtest_run.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("horizon", sa.Integer(), nullable=False),
        sa.Column("ic", sa.Float()),
        sa.Column("spread", sa.Float()),
        sa.Column("n_assets", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("backtest_ic_point")
    op.drop_table("backtest_quantile_stat")
    op.drop_table("backtest_run")
