"""Dropear la tabla group_scores.

El Mapa de Tendencia de Mercado dejó de leer group_scores: ahora calcula los
scores por grupo AL VUELO desde ind_trend_* (group_score_service.group_scores_for).
Con las señales de grupo ya removidas (0090), la tabla no tiene ningún consumidor,
así que se deja de persistir y se elimina.

Portable dual MySQL/PG (DDL puro, sin lectura de datos: se renderiza offline en
test_bootstrap_portability). El downgrade recrea la tabla VACÍA con el mismo
esquema que dejó la cadena 0033 (group_indicator_snapshot) + 0050 (rename): los
nombres de índice conservan el prefijo histórico ix_group_indicator_snapshot_*.

Revision ID: 0092
Revises: 0091
"""
import sqlalchemy as sa
from alembic import op

revision = "0092"
down_revision = "0091"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Sin FKs entrantes (group_id es un int suelto, no una FK): DROP directo.
    op.drop_table("group_scores")


def downgrade() -> None:
    op.create_table(
        "group_scores",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("group_type", sa.String(length=30), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("regime_score_d", sa.Float(), nullable=True),
        sa.Column("regime_score_w", sa.Float(), nullable=True),
        sa.Column("regime_score_m", sa.Float(), nullable=True),
        sa.Column("n_assets", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_type", "group_id", "date"),
    )
    op.create_index("ix_group_indicator_snapshot_group", "group_scores",
                    ["group_type", "group_id"])
    op.create_index("ix_group_indicator_snapshot_date", "group_scores", ["date"])
