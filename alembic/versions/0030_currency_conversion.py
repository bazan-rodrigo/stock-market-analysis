"""renombrar ars_conversion_divisor → currency_conversion_divisor + agregar currency_id

Revision ID: 0030
Revises: 0029
Create Date: 2026-04-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table("ars_conversion_divisor", "currency_conversion_divisor")

    op.add_column(
        "currency_conversion_divisor",
        sa.Column("currency_id", sa.Integer(), nullable=True),
    )

    # Backfill: asignar moneda ARS a los registros existentes
    op.execute("""
        UPDATE currency_conversion_divisor
        SET currency_id = (
            SELECT id FROM currencies
            WHERE iso_code = 'ARS'
            LIMIT 1
        )
    """)

    op.alter_column("currency_conversion_divisor", "currency_id",
                    existing_type=sa.Integer(), nullable=False)

    op.create_foreign_key(
        "fk_ccd_currency", "currency_conversion_divisor",
        "currencies", ["currency_id"], ["id"],
        ondelete="CASCADE",
    )

    # Reemplazar unique(divisor_asset_id) → unique(currency_id, divisor_asset_id)
    op.drop_index("divisor_asset_id", table_name="currency_conversion_divisor")
    op.create_unique_constraint(
        "uq_currency_conversion_divisor",
        "currency_conversion_divisor",
        ["currency_id", "divisor_asset_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_currency_conversion_divisor",
                       "currency_conversion_divisor", type_="unique")
    op.drop_constraint("fk_ccd_currency",
                       "currency_conversion_divisor", type_="foreignkey")
    op.drop_column("currency_conversion_divisor", "currency_id")
    op.create_unique_constraint(
        "uq_ars_divisor", "currency_conversion_divisor", ["divisor_asset_id"]
    )
    op.rename_table("currency_conversion_divisor", "ars_conversion_divisor")
