"""drop redundant ix_prices_asset_date (duplica uq_asset_date)

ix_prices_asset_date es un índice regular sobre (asset_id, date) creado
en 0001, pero UniqueConstraint("asset_id", "date") ya genera uq_asset_date
sobre las mismas columnas. Mantener los dos duplica el overhead de escritura
en cada INSERT/DELETE sobre prices sin ningún beneficio de lectura.

Revision ID: 0027
Revises: 0026
Create Date: 2026-04-26
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_prices_asset_date", table_name="prices")


def downgrade() -> None:
    op.create_index("ix_prices_asset_date", "prices", ["asset_id", "date"])
