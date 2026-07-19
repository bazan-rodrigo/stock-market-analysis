"""Composición de carteras teóricas (Fase 3).

Agrega a `portfolio` los campos de composición (curated / rule / strategy) y crea
`portfolio_member` (lista de activos de las curadas). Sólo DDL portable
(add_column + create_table), renderizable offline contra MySQL y PostgreSQL.

Revision ID: 0083
Revises: 0082
"""
import sqlalchemy as sa
from alembic import op

revision = "0083"
down_revision = "0082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("portfolio", sa.Column("composition_method", sa.String(10)))
    op.add_column("portfolio", sa.Column("strategy_id", sa.Integer()))
    op.add_column("portfolio", sa.Column("top_n", sa.Integer()))
    op.add_column("portfolio", sa.Column("rebalance", sa.Integer()))
    op.add_column("portfolio", sa.Column("rule_json", sa.Text()))
    op.create_table(
        "portfolio_member",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("portfolio_id", sa.Integer(),
                  sa.ForeignKey("portfolio.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("asset_id", sa.Integer(),
                  sa.ForeignKey("assets.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("weight", sa.Float()),
    )


def downgrade() -> None:
    op.drop_table("portfolio_member")
    op.drop_column("portfolio", "rule_json")
    op.drop_column("portfolio", "rebalance")
    op.drop_column("portfolio", "top_n")
    op.drop_column("portfolio", "strategy_id")
    op.drop_column("portfolio", "composition_method")
