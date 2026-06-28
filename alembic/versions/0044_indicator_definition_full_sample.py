"""Agregar columna full_sample a indicator_definitions.

Marca los indicadores cuyo algoritmo usa estadísticos sobre toda la serie
(ej: percentiles de ATR, umbrales de zonas de volatilidad). El backfill
histórico de estos indicadores siempre debe ejecutarse en modo force para
garantizar consistencia entre valores históricos y nuevos.

Revision ID: 0044
Revises: 0043
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None

_FULL_SAMPLE_CODES = [
    "atr_percentile_daily",
    "atr_percentile_weekly",
    "atr_percentile_monthly",
    "volatility_daily",
    "volatility_weekly",
    "volatility_monthly",
]


def upgrade() -> None:
    op.add_column(
        "indicator_definitions",
        sa.Column("full_sample", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    bind = op.get_bind()
    for code in _FULL_SAMPLE_CODES:
        bind.execute(
            sa.text("UPDATE indicator_definitions SET full_sample = TRUE WHERE code = :code"),
            {"code": code},
        )


def downgrade() -> None:
    op.drop_column("indicator_definitions", "full_sample")
