"""app_settings: tabla de configuración global de la aplicación

Revision ID: 0034
Revises: 0033
Create Date: 2026-06-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: Union[str, None] = "0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("id",            sa.Integer, primary_key=True),
        sa.Column("public_access", sa.Boolean, nullable=False, server_default="0"),
    )
    op.execute("INSERT INTO app_settings (id, public_access) VALUES (1, 0)")


def downgrade() -> None:
    op.drop_table("app_settings")
