"""Renombrar tabla group_indicator_snapshot a group_scores.

El término "snapshot" quedó de un diseño anterior (tablas screener_snapshot /
fundamental_snapshot, eliminadas en 0040/0042). La tabla guarda scores de
tendencia agregados por grupo y fecha, de ahí el nuevo nombre.

Revision ID: 0050
Revises: 0049
"""
from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("group_indicator_snapshot", "group_scores")


def downgrade() -> None:
    op.rename_table("group_scores", "group_indicator_snapshot")
