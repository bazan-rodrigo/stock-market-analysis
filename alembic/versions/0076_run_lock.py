"""Tabla run_lock: lock de corrida persistido con heartbeat (ver modelo
RunLock y run_lock_service). Endurece la exclusión mutua del Centro de
Datos, que hasta ahora vivía solo en memoria del proceso WSGI.

Primera migración de la cadena portable (post-freeze 0075): DDL sin sabor
de motor, se renderiza en MySQL y PostgreSQL (tests/test_bootstrap_portability).

Revision ID: 0076
Revises: 0075
"""
import sqlalchemy as sa
from alembic import op

revision = "0076"
down_revision = "0075"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "run_lock",
        sa.Column("op", sa.String(64), primary_key=True, nullable=False),
        sa.Column("token", sa.String(32), nullable=False),
        sa.Column("pid", sa.Integer, nullable=False),
        sa.Column("host", sa.String(255), nullable=True),
        sa.Column("started_at", sa.DateTime, nullable=False),
        sa.Column("heartbeat", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("run_lock")
