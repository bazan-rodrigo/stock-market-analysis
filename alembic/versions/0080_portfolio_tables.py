"""Tablas del módulo de Carteras (reales y teóricas).

portfolio = cartera de la biblioteca (seg|real);
portfolio_transaction = registro de operaciones de las reales
(buy/sell/dividend/split, con comisión e impuestos por operación y moneda).

Portable (post-freeze 0075): sólo DDL con tipos portables, renderizable offline
contra MySQL y PostgreSQL (tests/test_bootstrap_portability.py).

Revision ID: 0080
Revises: 0079
"""
import sqlalchemy as sa
from alembic import op

revision = "0080"
down_revision = "0079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("ptype", sa.String(10), nullable=False),   # 'seg' | 'real'
        sa.Column("owner_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("is_public", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("base_currency", sa.String(10)),
        sa.Column("benchmark_asset_id", sa.Integer(),
                  sa.ForeignKey("assets.id", ondelete="SET NULL")),
        sa.Column("linked_portfolio_id", sa.Integer(),
                  sa.ForeignKey("portfolio.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "portfolio_transaction",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("portfolio_id", sa.Integer(),
                  sa.ForeignKey("portfolio.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("asset_id", sa.Integer(),
                  sa.ForeignKey("assets.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),   # buy|sell|dividend|split
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("quantity", sa.Float()),
        sa.Column("price", sa.Float()),
        sa.Column("commission", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("taxes", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("currency", sa.String(10)),
        sa.Column("note", sa.String(255)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("portfolio_transaction")
    op.drop_table("portfolio")
