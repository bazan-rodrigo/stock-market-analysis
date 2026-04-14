"""Esquema inicial completo

Revision ID: 0001
Revises:
Create Date: 2026-01-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(80), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.Enum("admin", "analyst"), nullable=False, server_default="analyst"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        mysql_charset="utf8mb4",
    )

    op.create_table(
        "countries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("iso_code", sa.String(3), nullable=False, unique=True),
        mysql_charset="utf8mb4",
    )

    op.create_table(
        "currencies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("iso_code", sa.String(10), nullable=False, unique=True),
        mysql_charset="utf8mb4",
    )

    op.create_table(
        "markets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column(
            "country_id",
            sa.Integer(),
            sa.ForeignKey("countries.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        mysql_charset="utf8mb4",
    )

    op.create_table(
        "instrument_types",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column(
            "default_currency_id",
            sa.Integer(),
            sa.ForeignKey("currencies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        mysql_charset="utf8mb4",
    )

    op.create_table(
        "sectors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        mysql_charset="utf8mb4",
    )

    op.create_table(
        "industries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column(
            "sector_id",
            sa.Integer(),
            sa.ForeignKey("sectors.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        mysql_charset="utf8mb4",
    )

    op.create_table(
        "price_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
        mysql_charset="utf8mb4",
    )

    op.create_table(
        "assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticker", sa.String(20), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("country_id", sa.Integer(), sa.ForeignKey("countries.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("market_id", sa.Integer(), sa.ForeignKey("markets.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("instrument_type_id", sa.Integer(), sa.ForeignKey("instrument_types.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("currency_id", sa.Integer(), sa.ForeignKey("currencies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("sector_id", sa.Integer(), sa.ForeignKey("sectors.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("industry_id", sa.Integer(), sa.ForeignKey("industries.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("price_source_id", sa.Integer(), sa.ForeignKey("price_sources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
        mysql_charset="utf8mb4",
    )

    op.create_table(
        "prices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("open", sa.Float()),
        sa.Column("high", sa.Float()),
        sa.Column("low", sa.Float()),
        sa.Column("close", sa.Float()),
        sa.Column("volume", sa.BigInteger()),
        sa.UniqueConstraint("asset_id", "date", name="uq_asset_date"),
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_prices_asset_date", "prices", ["asset_id", "date"])

    op.create_table(
        "price_update_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_detail", sa.Text()),
        mysql_charset="utf8mb4",
    )

    op.create_table(
        "import_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticker", sa.String(20), nullable=False, unique=True),
        sa.Column("status", sa.Enum("imported", "skipped", "error"), nullable=False),
        sa.Column("detail", sa.Text()),
        sa.Column("attempted_at", sa.DateTime(), nullable=False),
        mysql_charset="utf8mb4",
    )

    op.create_table(
        "screener_snapshot",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_close", sa.Float()),
        sa.Column("var_daily", sa.Float()),
        sa.Column("var_month", sa.Float()),
        sa.Column("var_quarter", sa.Float()),
        sa.Column("var_year", sa.Float()),
        sa.Column("var_52w", sa.Float()),
        sa.Column("rsi", sa.Float()),
        sa.Column("sma20", sa.Float()),
        sa.Column("sma50", sa.Float()),
        sa.Column("sma200", sa.Float()),
        sa.Column("vs_sma20", sa.Float()),
        sa.Column("vs_sma50", sa.Float()),
        sa.Column("vs_sma200", sa.Float()),
        mysql_charset="utf8mb4",
    )


def downgrade() -> None:
    op.drop_table("screener_snapshot")
    op.drop_table("import_log")
    op.drop_table("price_update_log")
    op.drop_index("ix_prices_asset_date", "prices")
    op.drop_table("prices")
    op.drop_table("assets")
    op.drop_table("price_sources")
    op.drop_table("industries")
    op.drop_table("sectors")
    op.drop_table("instrument_types")
    op.drop_table("markets")
    op.drop_table("currencies")
    op.drop_table("countries")
    op.drop_table("users")
