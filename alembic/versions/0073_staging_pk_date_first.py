"""Recrea las tablas staging con la PK arrancando en DATE.

La PK original (signal_id/strategy_id primero) no servía al merge por
ventanas de fechas: `WHERE st.date BETWEEN ...` sin prefijo de índice hacía
FULL SCAN de staging en CADA ventana (~265 ventanas × 13M filas — medido
20min+ solo de merge). Con date primero: cada ventana lee su tajada, y los
INSERT del productor (cronológicos) quedan append-only en el B-tree.

Las staging son transitorias (se vacían por corrida): drop + create.

Revision ID: 0073
Revises: 0072
"""
import sqlalchemy as sa
from alembic import op

revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("signal_value_staging")
    op.drop_table("group_signal_value_staging")
    op.drop_table("group_scores_staging")
    op.drop_table("strategy_result_staging")

    op.create_table(
        "signal_value_staging",
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("signal_id", sa.Integer(), primary_key=True,
                  autoincrement=False),
        sa.Column("asset_id", sa.Integer(), primary_key=True,
                  autoincrement=False),
        sa.Column("score", sa.Float()),
    )
    op.create_table(
        "group_signal_value_staging",
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("signal_id", sa.Integer(), primary_key=True,
                  autoincrement=False),
        sa.Column("group_type", sa.String(30), primary_key=True),
        sa.Column("group_id", sa.Integer(), primary_key=True,
                  autoincrement=False),
        sa.Column("score", sa.Float()),
    )
    op.create_table(
        "group_scores_staging",
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("group_type", sa.String(30), primary_key=True),
        sa.Column("group_id", sa.Integer(), primary_key=True,
                  autoincrement=False),
        sa.Column("regime_score_d", sa.Float()),
        sa.Column("regime_score_w", sa.Float()),
        sa.Column("regime_score_m", sa.Float()),
        sa.Column("n_assets", sa.Integer()),
    )
    op.create_table(
        "strategy_result_staging",
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("strategy_id", sa.Integer(), primary_key=True,
                  autoincrement=False),
        sa.Column("asset_id", sa.Integer(), primary_key=True,
                  autoincrement=False),
        sa.Column("score", sa.Float()),
        sa.Column("pct", sa.Float()),
    )


def downgrade() -> None:
    # Volver a la PK vieja no tiene sentido (era el bug); no-op destructivo
    # deliberadamente omitido.
    pass
