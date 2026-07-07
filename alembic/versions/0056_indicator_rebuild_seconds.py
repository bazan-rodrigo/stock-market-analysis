"""Columna last_rebuild_seconds en indicator_definitions.

last_backfill_seconds (migración 0052) ordena la cola LPT del delta normal,
pero se sobreescribía también en un rebuild completo (force=True) con el
mismo campo — mezclando dos costos muy distintos: un delta típico reescribe
1 fila por activo (camino rápido de tail-mode), mientras que un rebuild
reescribe la historia ENTERA de cada activo (miles de filas). Con un solo
campo compartido, la cola LPT de un rebuild quedaba ordenada por duraciones
de delta, subestimando código como dist_sma20/dist_optimal_sma_daily/
return_quarterly (baratos en delta, pesados en rebuild) y arrancándolos
tarde en vez de en la primera tanda junto a volatility_daily/trend_daily.

last_rebuild_seconds guarda la medición de la última corrida force=True por
separado, para que cada modo ordene su propia cola con el costo real de ESE
modo.

Revision ID: 0056
Revises: 0055
"""
import sqlalchemy as sa
from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("indicator_definitions",
                  sa.Column("last_rebuild_seconds", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("indicator_definitions", "last_rebuild_seconds")
