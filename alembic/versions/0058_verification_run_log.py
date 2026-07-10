"""verification_run_log: fila unica (id=1) con la ultima corrida de
update_flags_for_assets (boton manual o job semanal) - fecha, duracion
y resultado, para mostrarlo en /admin/verify sin depender de logs de
servidor.

Revision ID: 0058
Revises: 0057
"""
import sqlalchemy as sa
from alembic import op

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "verification_run_log",
        sa.Column("id",              sa.Integer,  primary_key=True, default=1),
        sa.Column("mode",            sa.String(20), nullable=False),
        sa.Column("started_at",      sa.DateTime, nullable=False),
        sa.Column("seconds",         sa.Float,    nullable=False),
        sa.Column("checked_assets",  sa.Integer,  nullable=False),
        sa.Column("flagged_assets",  sa.Integer,  nullable=False),
        sa.Column("cleared_assets",  sa.Integer,  nullable=False),
    )


def downgrade() -> None:
    op.drop_table("verification_run_log")
