"""drawdown_max2 y drawdown_max3 pasan a keep_history=False

Mismo motivo que 0046 con drawdown_current/max1: max1/max2/max3 salen del
mismo ranking nsmallest(3) sobre el historial completo, por lo que un valor
"histórico" por fecha no representa el drawdown real hasta esa fecha.
max2/max3 nunca tuvieron función de backfill; esto solo alinea el esquema
con ese hecho y corrige la lectura en modo quick (que ya los buscaba en
current_indicator_values).

Revision ID: 0048
Revises: 0047
Create Date: 2026-07-03
"""
from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DROP TABLE IF EXISTS ind_drawdown_max2")
    op.execute("DROP TABLE IF EXISTS ind_drawdown_max3")
    op.execute(
        "UPDATE indicator_definitions SET keep_history = 0 "
        "WHERE code IN ('drawdown_max2', 'drawdown_max3')"
    )


def downgrade():
    import sqlalchemy as sa
    op.create_table(
        "ind_drawdown_max2",
        sa.Column("asset_id", sa.Integer, sa.ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("date",     sa.Date,    primary_key=True),
        sa.Column("value",    sa.Float),
    )
    op.create_table(
        "ind_drawdown_max3",
        sa.Column("asset_id", sa.Integer, sa.ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("date",     sa.Date,    primary_key=True),
        sa.Column("value",    sa.Float),
    )
    op.execute(
        "UPDATE indicator_definitions SET keep_history = 1 "
        "WHERE code IN ('drawdown_max2', 'drawdown_max3')"
    )
