"""Indice por date en prices.

La tabla solo tenia PK(id) y UNIQUE(asset_id, date): cualquier consulta
global por fecha hacia full scan de millones de filas — MAX(prices.date)
(get_default_target_date, llamada en cada corrida del pipeline), el
calendario de fechas del backfill de senales (SELECT DISTINCT date >= X)
y el indicador virtual last_close (WHERE date = :d).

Revision ID: 0063
Revises: 0062
"""
import sqlalchemy as sa
from alembic import op

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    exists = bind.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.statistics "
        "WHERE table_schema = DATABASE() AND table_name = 'prices' "
        "  AND column_name = 'date' AND seq_in_index = 1"
    )).scalar()
    if not exists:
        op.create_index("ix_prices_date", "prices", ["date"])


def downgrade() -> None:
    op.drop_index("ix_prices_date", table_name="prices")
