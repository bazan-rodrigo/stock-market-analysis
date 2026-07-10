"""scheduler_config: horario propio para la verificacion semanal, separado
del habilitado/hora/minuto de la actualizacion diaria de precios - nace
deshabilitada (weekly_verify_enabled=False) a diferencia del job diario.

Revision ID: 0059
Revises: 0058
"""
import sqlalchemy as sa
from alembic import op

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scheduler_config",
                  sa.Column("weekly_verify_enabled", sa.Boolean(), nullable=False,
                            server_default=sa.false()))
    op.add_column("scheduler_config",
                  sa.Column("weekly_verify_day", sa.String(3), nullable=False,
                            server_default="sun"))
    op.add_column("scheduler_config",
                  sa.Column("weekly_verify_hour", sa.Integer(), nullable=False,
                            server_default="3"))
    op.add_column("scheduler_config",
                  sa.Column("weekly_verify_minute", sa.Integer(), nullable=False,
                            server_default="0"))


def downgrade() -> None:
    op.drop_column("scheduler_config", "weekly_verify_minute")
    op.drop_column("scheduler_config", "weekly_verify_hour")
    op.drop_column("scheduler_config", "weekly_verify_day")
    op.drop_column("scheduler_config", "weekly_verify_enabled")
