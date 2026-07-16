"""Tablas staging del backfill acotado de señales/estrategias.

Los recálculos acotados insertan acá (tablas vacías, un solo índice) y un
merge por ventanas pasa a las oficiales solo las diferencias — reemplaza al
borrar-y-reescribir la historia completa en tablas pobladas, que hacía que
recalcular UNA estrategia costara más que recalcular todo.

Revision ID: 0072
Revises: 0071
"""
import sqlalchemy as sa
from alembic import op

revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "signal_value_staging",
        sa.Column("signal_id", sa.Integer(), primary_key=True,
                  autoincrement=False),
        sa.Column("asset_id", sa.Integer(), primary_key=True,
                  autoincrement=False),
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("score", sa.Float()),
    )
    op.create_table(
        "group_signal_value_staging",
        sa.Column("signal_id", sa.Integer(), primary_key=True,
                  autoincrement=False),
        sa.Column("group_type", sa.String(30), primary_key=True),
        sa.Column("group_id", sa.Integer(), primary_key=True,
                  autoincrement=False),
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("score", sa.Float()),
    )
    op.create_table(
        "group_scores_staging",
        sa.Column("group_type", sa.String(30), primary_key=True),
        sa.Column("group_id", sa.Integer(), primary_key=True,
                  autoincrement=False),
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("regime_score_d", sa.Float()),
        sa.Column("regime_score_w", sa.Float()),
        sa.Column("regime_score_m", sa.Float()),
        sa.Column("n_assets", sa.Integer()),
    )
    op.create_table(
        "strategy_result_staging",
        sa.Column("strategy_id", sa.Integer(), primary_key=True,
                  autoincrement=False),
        sa.Column("asset_id", sa.Integer(), primary_key=True,
                  autoincrement=False),
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("score", sa.Float()),
        sa.Column("pct", sa.Float()),
    )


def downgrade() -> None:
    op.drop_table("strategy_result_staging")
    op.drop_table("group_scores_staging")
    op.drop_table("group_signal_value_staging")
    op.drop_table("signal_value_staging")
