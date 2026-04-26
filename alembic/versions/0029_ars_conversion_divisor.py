"""tabla ars_conversion_divisor para sintéticos ARS automáticos

Almacena los activos usados como divisor para generar sintéticos de precio
convertido de ARS a otra moneda (CCL, MEP, Blue, etc.).
Por cada divisor configurado el sistema crea automáticamente un activo
sintético tipo ratio para cada activo en moneda ARS.

Revision ID: 0029
Revises: 0028
Create Date: 2026-04-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ars_conversion_divisor",
        sa.Column("id",               sa.Integer, primary_key=True),
        sa.Column("divisor_asset_id", sa.Integer,
                  sa.ForeignKey("assets.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
    )


def downgrade() -> None:
    op.drop_table("ars_conversion_divisor")
