"""Columna last_backfill_seconds en indicator_definitions.

Duración medida de la última corrida de backfill por indicador: la próxima
corrida ordena su cola LPT (pesados primero) por lo observado, en lugar de
una heurística estática. Los indicadores nuevos (NULL) se priorizan primero.

Revision ID: 0052
Revises: 0051
"""
import sqlalchemy as sa
from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("indicator_definitions",
                  sa.Column("last_backfill_seconds", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("indicator_definitions", "last_backfill_seconds")
