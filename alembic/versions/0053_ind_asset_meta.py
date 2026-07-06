"""Tabla ind_asset_meta: metadato de invalidación por activo e indicador.

Hoy solo la usa relative_strength_52w: guarda el benchmark_id con el que
se calculó la serie completa de cada activo. En el delta, si el benchmark
vigente del activo cambió respecto al guardado, ese activo cae al camino
lento (recompute completo) en lugar del camino rápido de cola-solamente,
porque toda su historia de RS quedó calculada contra el benchmark viejo.

Revision ID: 0053
Revises: 0052
"""
import sqlalchemy as sa
from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ind_asset_meta",
        sa.Column("asset_id",     sa.Integer(), nullable=False),
        sa.Column("code",         sa.String(50), nullable=False),
        sa.Column("benchmark_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("asset_id", "code"),
    )


def downgrade() -> None:
    op.drop_table("ind_asset_meta")
