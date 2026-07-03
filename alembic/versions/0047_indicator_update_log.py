"""indicator_update_log: registra éxito/error del recálculo de indicadores por activo

Revision ID: 0047
Revises: 0046
Create Date: 2026-07-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0047"
down_revision: Union[str, None] = "0046"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "indicator_update_log",
        sa.Column("id",              sa.Integer,  primary_key=True),
        sa.Column("asset_id",        sa.Integer,  sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("last_attempt_at", sa.DateTime, nullable=False),
        sa.Column("success",         sa.Boolean,  nullable=False),
        sa.Column("error_detail",    sa.Text),
    )


def downgrade() -> None:
    op.drop_table("indicator_update_log")
