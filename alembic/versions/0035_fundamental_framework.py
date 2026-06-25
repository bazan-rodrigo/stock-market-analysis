"""fundamental_framework: fuentes, datos trimestrales, snapshot y log de fundamentales

Revision ID: 0035
Revises: 0034
Create Date: 2026-06-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0035"
down_revision: Union[str, None] = "0034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fundamental_sources",
        sa.Column("id",          sa.Integer,     primary_key=True),
        sa.Column("name",        sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text),
    )
    op.execute("INSERT INTO fundamental_sources (id, name, description) "
               "VALUES (1, 'Yahoo Finance', 'Fundamentales via yfinance (quarterly_financials, balance_sheet, cashflow)')")

    op.add_column("assets",
        sa.Column("fundamental_source_id", sa.Integer,
                  sa.ForeignKey("fundamental_sources.id", ondelete="SET NULL"),
                  nullable=True))

    op.create_table(
        "fundamental_quarterly",
        sa.Column("id",               sa.Integer, primary_key=True),
        sa.Column("asset_id",         sa.Integer, sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period_date",      sa.Date,    nullable=False),
        sa.Column("revenue",          sa.Float),
        sa.Column("gross_profit",     sa.Float),
        sa.Column("operating_income", sa.Float),
        sa.Column("net_income",       sa.Float),
        sa.Column("ebitda",           sa.Float),
        sa.Column("total_debt",       sa.Float),
        sa.Column("equity",           sa.Float),
        sa.Column("shares",           sa.Float),
        sa.Column("fcf",              sa.Float),
        sa.Column("operating_cf",     sa.Float),
        sa.Column("eps_actual",       sa.Float),
        sa.Column("eps_estimated",    sa.Float),
        sa.UniqueConstraint("asset_id", "period_date", name="uq_fund_asset_period"),
    )

    op.create_table(
        "fundamental_snapshot",
        sa.Column("id",                 sa.Integer,  primary_key=True),
        sa.Column("asset_id",           sa.Integer,  sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("updated_at",         sa.DateTime, nullable=False),
        sa.Column("pe_ttm",             sa.Float),
        sa.Column("pb",                 sa.Float),
        sa.Column("ps_ttm",             sa.Float),
        sa.Column("ev_ebitda",          sa.Float),
        sa.Column("net_margin",         sa.Float),
        sa.Column("gross_margin",       sa.Float),
        sa.Column("operating_margin",   sa.Float),
        sa.Column("debt_to_equity",     sa.Float),
        sa.Column("revenue_growth_yoy", sa.Float),
        sa.Column("eps_growth_yoy",     sa.Float),
    )

    op.create_table(
        "fundamental_update_log",
        sa.Column("id",              sa.Integer,  primary_key=True),
        sa.Column("asset_id",        sa.Integer,  sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("last_attempt_at", sa.DateTime, nullable=False),
        sa.Column("success",         sa.Boolean,  nullable=False),
        sa.Column("error_detail",    sa.Text),
    )


def downgrade() -> None:
    op.drop_table("fundamental_update_log")
    op.drop_table("fundamental_snapshot")
    op.drop_table("fundamental_quarterly")
    op.drop_column("assets", "fundamental_source_id")
    op.drop_table("fundamental_sources")
