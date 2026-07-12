"""Registro de fechas evaluadas por el backfill de senales/estrategias.

Sin esto, una fecha que corrio y produjo 0 resultados (nadie paso el
filtro de elegibilidad — normal en decadas donde solo existia ^GSPC) es
indistinguible de un hueco real, y el delta con alcance la reprocesa
entera en CADA corrida (1927->1993 casi vacio, una y otra vez).

Revision ID: 0067
Revises: 0066
"""
import sqlalchemy as sa
from alembic import op

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "signal_eval_log",
        sa.Column("scope_kind", sa.String(10), primary_key=True),
        sa.Column("ref_id",     sa.Integer,    primary_key=True),
        sa.Column("date",       sa.Date,       primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("signal_eval_log")
