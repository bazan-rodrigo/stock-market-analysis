"""Eliminar screener_snapshot y agregar keep_history a indicator_definitions.

- DROP TABLE screener_snapshot: los datos de best_ma pasan a indicator_values;
  regime_zones, vol_zones y dd_events se calculan en tiempo real en el gráfico.
- ADD COLUMN indicator_definitions.keep_history BOOLEAN NOT NULL DEFAULT TRUE:
  cuando False, sólo existe una fila vigente por (asset_id, indicator_id)
  y se borra la anterior al escribir (ej: best_sma_d, best_ema_d, etc.).

Revision ID: 0042
Revises: 0041
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "indicator_definitions",
        sa.Column("keep_history", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.drop_table("screener_snapshot")


def downgrade() -> None:
    op.create_table(
        "screener_snapshot",
        sa.Column("id",            sa.Integer(),  nullable=False, autoincrement=True),
        sa.Column("asset_id",      sa.Integer(),  nullable=False),
        sa.Column("updated_at",    sa.DateTime(), nullable=False),
        sa.Column("sma20",         sa.Float(),    nullable=True),
        sa.Column("sma50",         sa.Float(),    nullable=True),
        sa.Column("sma200",        sa.Float(),    nullable=True),
        sa.Column("best_sma_d",    sa.Integer(),  nullable=True),
        sa.Column("best_ema_d",    sa.Integer(),  nullable=True),
        sa.Column("best_sma_w",    sa.Integer(),  nullable=True),
        sa.Column("best_ema_w",    sa.Integer(),  nullable=True),
        sa.Column("best_sma_m",    sa.Integer(),  nullable=True),
        sa.Column("best_ema_m",    sa.Integer(),  nullable=True),
        sa.Column("regime_zones_d", sa.Text(),    nullable=True),
        sa.Column("regime_zones_w", sa.Text(),    nullable=True),
        sa.Column("regime_zones_m", sa.Text(),    nullable=True),
        sa.Column("dd_events",      sa.Text(),    nullable=True),
        sa.Column("vol_zones_d",    sa.Text(),    nullable=True),
        sa.Column("vol_zones_w",    sa.Text(),    nullable=True),
        sa.Column("vol_zones_m",    sa.Text(),    nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
    )
    op.drop_column("indicator_definitions", "keep_history")
