"""Columnas min_date/max_date/row_count en ind_asset_meta.

Cachea el (min_date, max_date, row_count) por (asset_id, code) que hoy
_query_tail_stats calcula con un GROUP BY asset_id + COUNT(*) sobre cada
tabla ind_{code} — en la práctica un full-scan completo, porque el
COUNT(*) impide el loose index scan que MIN/MAX solos permitirían. A
10000 activos ese full-scan (repetido para los 24 códigos de
_DELTA_TAIL_MODE en cada delta) vuelve a ser el cuello de botella.

Sin backfill de datos: al desplegar, el caché arranca vacío y cada
código cae al camino lento una sola corrida (mismo trato que un activo
nuevo, _delta_tail_start ya trata stat=None como "camino lento"); al
terminar esa corrida el caché queda poblado y el próximo delta ya usa
el camino rápido.

Revision ID: 0055
Revises: 0054
"""
import sqlalchemy as sa
from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ind_asset_meta", sa.Column("min_date", sa.Date(), nullable=True))
    op.add_column("ind_asset_meta", sa.Column("max_date", sa.Date(), nullable=True))
    op.add_column("ind_asset_meta", sa.Column("row_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("ind_asset_meta", "row_count")
    op.drop_column("ind_asset_meta", "max_date")
    op.drop_column("ind_asset_meta", "min_date")
