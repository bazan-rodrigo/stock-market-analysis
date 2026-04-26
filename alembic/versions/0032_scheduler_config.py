"""scheduler_config: persiste configuración y estado del scheduler en DB

Revision ID: 0032
Revises: 0031
Create Date: 2026-04-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: Union[str, None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scheduler_config",
        sa.Column("id",      sa.Integer,  primary_key=True),
        sa.Column("enabled", sa.Boolean,  nullable=False, server_default="0"),
        sa.Column("hour",    sa.Integer,  nullable=False, server_default="18"),
        sa.Column("minute",  sa.Integer,  nullable=False, server_default="0"),
    )
    op.execute("INSERT INTO scheduler_config (id, enabled, hour, minute) VALUES (1, 0, 18, 0)")


def downgrade() -> None:
    op.drop_table("scheduler_config")
