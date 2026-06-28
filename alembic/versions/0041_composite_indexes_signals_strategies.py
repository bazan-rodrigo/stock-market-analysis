"""Índices compuestos en signal_value, strategy_result y strategy_component.

- signal_value(signal_id, date): cubre la query de strategy_service que filtra
  por signal_id IN (...) AND date = snap_date (el UniqueConstraint existente
  tiene asset_id en el medio y no puede optimizar ese patrón).
- strategy_result(strategy_id, date): cubre get_available_dates(),
  get_strategy_results_with_breakdown() y compute_strategy_results(), que
  filtran por (strategy_id, date) sin asset_id.
- strategy_component(signal_id): cubre el check de ON DELETE RESTRICT y los
  JOINs al cargar componentes de una estrategia.

Revision ID: 0041
Revises: 0040
Create Date: 2026-06-27
"""
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_signal_value_signal_date",       "signal_value",       ["signal_id", "date"])
    op.create_index("ix_strategy_result_strategy_date",  "strategy_result",    ["strategy_id", "date"])
    op.create_index("ix_strategy_component_signal_id",   "strategy_component", ["signal_id"])


def downgrade() -> None:
    op.drop_index("ix_strategy_component_signal_id",  table_name="strategy_component")
    op.drop_index("ix_strategy_result_strategy_date", table_name="strategy_result")
    op.drop_index("ix_signal_value_signal_date",      table_name="signal_value")
