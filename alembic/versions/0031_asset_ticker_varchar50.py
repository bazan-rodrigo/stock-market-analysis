"""ampliar assets.ticker de VARCHAR(20) a VARCHAR(50)

Los tickers de activos sintéticos de conversión de monedas pueden superar
los 20 caracteres (ej: AGRO.BA_DOLAR CCL (GGAL)).

Revision ID: 0031
Revises: 0030
Create Date: 2026-04-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "assets", "ticker",
        existing_type=sa.String(20),
        type_=sa.String(50),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "assets", "ticker",
        existing_type=sa.String(50),
        type_=sa.String(20),
        nullable=False,
    )
