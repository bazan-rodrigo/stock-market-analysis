"""Columna checksum en ind_asset_meta.

Usada por volatility_daily/weekly/monthly y atr_percentile_daily/weekly/
monthly (ver _CHECKSUM_DEP_CODES): hash del prefijo histórico calculado en
la última corrida. En el delta, si el hash de hoy coincide, el prefijo no
cambió (sin deriva de percentiles) y alcanza con escribir la cola; si no
coincide, ese activo cae al dict-compare completo de siempre.

Revision ID: 0054
Revises: 0053
"""
import sqlalchemy as sa
from alembic import op

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ind_asset_meta",
                  sa.Column("checksum", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("ind_asset_meta", "checksum")
