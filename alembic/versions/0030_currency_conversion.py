"""renombrar ars_conversion_divisor → currency_conversion_divisor + agregar currency_id

Revision ID: 0030
Revises: 0029
Create Date: 2026-04-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(conn, name: str) -> bool:
    return bool(conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t"
    ), {"t": name}).scalar())


def _column_exists(conn, table: str, column: str) -> bool:
    return bool(conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
    ), {"t": table, "c": column}).scalar())


def _index_exists(conn, table: str, index: str) -> bool:
    return bool(conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND INDEX_NAME = :i"
    ), {"t": table, "i": index}).scalar())


def _constraint_exists(conn, table: str, name: str) -> bool:
    return bool(conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND CONSTRAINT_NAME = :n"
    ), {"t": table, "n": name}).scalar())


def _fk_on_column(conn, table: str, column: str, ref_table: str) -> str | None:
    """Retorna el nombre del FK constraint sobre esa columna, o None."""
    return conn.execute(text(
        "SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t "
        "AND COLUMN_NAME = :c AND REFERENCED_TABLE_NAME = :r LIMIT 1"
    ), {"t": table, "c": column, "r": ref_table}).scalar()


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Rename table (puede ya estar hecho si la migración fue parcialmente aplicada)
    if _table_exists(conn, "ars_conversion_divisor"):
        op.rename_table("ars_conversion_divisor", "currency_conversion_divisor")

    # 2. Agregar currency_id si no existe
    if not _column_exists(conn, "currency_conversion_divisor", "currency_id"):
        op.add_column(
            "currency_conversion_divisor",
            sa.Column("currency_id", sa.Integer(), nullable=True),
        )
        op.execute(text("""
            UPDATE currency_conversion_divisor
            SET currency_id = (SELECT id FROM currencies WHERE iso_code = 'ARS' LIMIT 1)
        """))
        op.alter_column("currency_conversion_divisor", "currency_id",
                        existing_type=sa.Integer(), nullable=False)

    # 3. FK de currency_id → currencies
    if not _constraint_exists(conn, "currency_conversion_divisor", "fk_ccd_currency"):
        op.create_foreign_key(
            "fk_ccd_currency", "currency_conversion_divisor",
            "currencies", ["currency_id"], ["id"],
            ondelete="CASCADE",
        )

    # 4. Eliminar FK sobre divisor_asset_id antes de poder borrar su índice (requerido en MariaDB)
    fk_div = _fk_on_column(conn, "currency_conversion_divisor", "divisor_asset_id", "assets")
    if fk_div:
        op.drop_constraint(fk_div, "currency_conversion_divisor", type_="foreignkey")

    # 5. Borrar índice único simple sobre divisor_asset_id
    if _index_exists(conn, "currency_conversion_divisor", "divisor_asset_id"):
        op.drop_index("divisor_asset_id", table_name="currency_conversion_divisor")

    # 6. Crear unique compuesto (currency_id, divisor_asset_id)
    if not _constraint_exists(conn, "currency_conversion_divisor", "uq_currency_conversion_divisor"):
        op.create_unique_constraint(
            "uq_currency_conversion_divisor",
            "currency_conversion_divisor",
            ["currency_id", "divisor_asset_id"],
        )

    # 7. Recrear FK sobre divisor_asset_id
    if not _fk_on_column(conn, "currency_conversion_divisor", "divisor_asset_id", "assets"):
        op.create_foreign_key(
            "fk_ccd_divisor_asset", "currency_conversion_divisor",
            "assets", ["divisor_asset_id"], ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    conn = op.get_bind()

    fk_div = _fk_on_column(conn, "currency_conversion_divisor", "divisor_asset_id", "assets")
    if fk_div:
        op.drop_constraint(fk_div, "currency_conversion_divisor", type_="foreignkey")

    if _constraint_exists(conn, "currency_conversion_divisor", "uq_currency_conversion_divisor"):
        op.drop_constraint("uq_currency_conversion_divisor",
                           "currency_conversion_divisor", type_="unique")

    op.create_unique_constraint(
        "uq_ars_divisor", "currency_conversion_divisor", ["divisor_asset_id"]
    )

    op.create_foreign_key(
        None, "currency_conversion_divisor",
        "assets", ["divisor_asset_id"], ["id"],
        ondelete="CASCADE",
    )

    if _constraint_exists(conn, "currency_conversion_divisor", "fk_ccd_currency"):
        op.drop_constraint("fk_ccd_currency", "currency_conversion_divisor", type_="foreignkey")

    if _column_exists(conn, "currency_conversion_divisor", "currency_id"):
        op.drop_column("currency_conversion_divisor", "currency_id")

    if _table_exists(conn, "currency_conversion_divisor"):
        op.rename_table("currency_conversion_divisor", "ars_conversion_divisor")
