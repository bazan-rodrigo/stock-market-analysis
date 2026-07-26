"""Tabla run_history: bitácora persistida de corridas pesadas (ver modelo
RunHistory y run_history_service). Monitoreo M1/M2: un registro durable de
qué corrió y cómo terminó, para que una corrida cortada por un reciclado del
contenedor no desaparezca sin rastro (antes el historial vivía en memoria).

Cadena portable (post-freeze 0075): DDL sin sabor de motor, se renderiza en
MySQL y PostgreSQL (tests/test_bootstrap_portability).

Revision ID: 0096
Revises: 0095
"""
import sqlalchemy as sa
from alembic import op

revision = "0096"
down_revision = "0095"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "run_history",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True,
                  nullable=False),
        sa.Column("op", sa.String(32), nullable=False),
        sa.Column("scope", sa.String(64), nullable=True),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("started_at", sa.DateTime, nullable=False),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.Column("total", sa.Integer, nullable=True),
        sa.Column("unit", sa.String(16), nullable=True),
        sa.Column("ok", sa.Integer, nullable=True),
        sa.Column("first_error", sa.Text, nullable=True),
        sa.Column("pid", sa.Integer, nullable=True),
        sa.Column("host", sa.String(255), nullable=True),
    )
    op.create_index("ix_run_history_started_at", "run_history", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_run_history_started_at", table_name="run_history")
    op.drop_table("run_history")
