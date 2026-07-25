"""Remover las señales de grupo y el Alcance de grupo en estrategias.

Se droppea la tabla group_signal_value (scores de señales source=group) y las
columnas que materializaban la funcionalidad de grupo:
  - signal.source        (asset | group)  → todas las señales son de activo
  - signal.group_type    (solo si source=group)
  - strategy_component.scope / group_type / group_id  (Alcance own/specific_group)

group_scores NO se toca: la calcula group_score_service desde los indicadores de
tendencia y alimenta el Mapa de Mercado (independiente de las señales de grupo).

Portable dual MySQL/PG (DDL puro, sin lectura de datos: se renderiza offline en
test_bootstrap_portability). El downgrade recrea la tabla y las columnas VACÍAS
(los datos no se conservan).

Revision ID: 0090
Revises: 0089
"""
import sqlalchemy as sa
from alembic import op

revision = "0090"
down_revision = "0089"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # La tabla tiene una FK a signal (no hay FKs entrantes): DROP directo.
    op.drop_table("group_signal_value")

    op.drop_column("strategy_component", "scope")
    op.drop_column("strategy_component", "group_type")
    op.drop_column("strategy_component", "group_id")

    op.drop_column("signal", "group_type")
    op.drop_column("signal", "source")


def downgrade() -> None:
    # Re-alta VACÍA (los datos de grupo no se conservan). source vuelve NOT NULL
    # con server_default para no romper si la tabla signal ya tiene filas.
    op.add_column("signal", sa.Column(
        "source", sa.String(length=10), nullable=False, server_default="asset"))
    op.add_column("signal", sa.Column(
        "group_type", sa.String(length=30), nullable=True))

    op.add_column("strategy_component", sa.Column(
        "scope", sa.String(length=20), nullable=True))
    op.add_column("strategy_component", sa.Column(
        "group_type", sa.String(length=30), nullable=True))
    op.add_column("strategy_component", sa.Column(
        "group_id", sa.Integer(), nullable=True))

    op.create_table(
        "group_signal_value",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("signal_id", sa.Integer(), nullable=False),
        sa.Column("group_type", sa.String(length=30), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["signal_id"], ["signal.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("signal_id", "group_type", "group_id", "date"),
    )
    op.create_index("ix_group_signal_value_signal_id", "group_signal_value",
                    ["signal_id"])
    op.create_index("ix_group_signal_value_date", "group_signal_value", ["date"])
