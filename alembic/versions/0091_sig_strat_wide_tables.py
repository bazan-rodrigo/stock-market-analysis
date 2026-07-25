"""Tablas anchas de señales y estrategias (base, sin columnas de valor).

Optimización de footprint (docs/notes/design_sig_wide_tables.md): las señales
son ~50% de la base (medido en Railway); cada tabla per-señal es ~80% overhead
de fila+índice pagado N veces. El modelo ancho agrupa todas las señales en una
fila por (asset_id, date), una COLUMNA por señal — y análogo para estrategias
(score+pct por estrategia). Paga el overhead una vez por fecha.

Esta migración solo CREA las tablas BASE (asset_id + date, sin columnas de
valor): las columnas por señal/estrategia son dinámicas y se agregan en runtime
con ALTER TABLE ADD COLUMN (signal_store.ensure_*_column). El cutover de
lectura/escritura ocurre en el código (fases 2-4 del diseño), no acá.

Esquema idéntico a signal_store.ensure_wide_signal_tables y a las sig_{id}
per-entidad: PK (date, asset_id) — date primero, para el append cronológico del
backfill —, índice secundario (asset_id, date) para las lecturas por activo, sin
FK a assets (purge_assets limpia estas tablas explícitamente). DDL portable
(sa puro): se renderiza en MySQL y PostgreSQL (tests/test_bootstrap_portability).

Revision ID: 0091
Revises: 0090
"""
import sqlalchemy as sa
from alembic import op

revision = "0091"
down_revision = "0090"
branch_labels = None
depends_on = None


def _create(name: str) -> None:
    op.create_table(
        name,
        sa.Column("asset_id", sa.Integer, nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.PrimaryKeyConstraint("date", "asset_id"),
    )
    op.create_index(f"ix_{name}_asset_date", name, ["asset_id", "date"])


def upgrade() -> None:
    _create("signal_values_wide")
    _create("strategy_results_wide")


def downgrade() -> None:
    op.drop_table("strategy_results_wide")
    op.drop_table("signal_values_wide")
