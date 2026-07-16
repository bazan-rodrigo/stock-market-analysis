"""Elimina las tablas staging del backfill: el diseño staging+merge no
cumplió el criterio de aceptación (el merge por anti-joins costaba
proporcional al TAMAÑO de los datos, no al cambio — 33min+ medidos, peor
que el rebuild completo). Reemplazado por el modo strategy_only del
backfill: las señales se LEEN (no se re-evalúan ni reescriben) y solo se
reconstruye strategy_result — a elección del usuario ("Incluir señales"
en Centro de Datos).

Revision ID: 0074
Revises: 0073
"""
import sqlalchemy as sa  # noqa: F401
from alembic import op

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None

_TABLES = ("signal_value_staging", "group_signal_value_staging",
           "group_scores_staging", "strategy_result_staging")


def upgrade() -> None:
    for t in _TABLES:
        op.drop_table(t)


def downgrade() -> None:
    # El diseño staging quedó descartado; recrearlo no tiene sentido.
    pass
