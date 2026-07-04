"""Tabla pnf_config: configuración del gráfico Punto y Figura.

Revision ID: 0051
Revises: 0050
"""
import sqlalchemy as sa
from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pnf_config",
        sa.Column("id",             sa.Integer, primary_key=True),
        sa.Column("box_method",     sa.String(10), nullable=False, server_default="atr"),
        sa.Column("box_pct",        sa.Float,      nullable=False, server_default="1.0"),
        sa.Column("box_atr_period", sa.Integer,    nullable=False, server_default="14"),
        sa.Column("box_fixed",      sa.Float,      nullable=False, server_default="1.0"),
        sa.Column("reversal",       sa.Integer,    nullable=False, server_default="3"),
        sa.Column("source",         sa.String(5),  nullable=False, server_default="close"),
    )


def downgrade() -> None:
    op.drop_table("pnf_config")
