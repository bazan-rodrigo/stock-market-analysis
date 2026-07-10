"""asset_verification_flag: activos con hallazgos de /admin/verify (job semanal)

Persiste el resultado de la corrida completa de verificación (todos los
activos, todos los códigos) para poder marcar en los selectores de
activo de la app ("Análisis de Activo", RRG, Evolución, Pares,
Retornos) aquellos con posibles errores de datos de origen o
discrepancias de cálculo — sin tener que correr la verificación en vivo
cada vez que alguien abre un dropdown.

Solo tiene fila para activos CON algún hallazgo — un activo sin
problemas simplemente no aparece acá (no hace falta ON DELETE especial:
se trunca y repuebla entera en cada corrida del job).

Revision ID: 0057
Revises: 0056
"""
import sqlalchemy as sa
from alembic import op

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "asset_verification_flag",
        sa.Column("asset_id",       sa.Integer, sa.ForeignKey("assets.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("n_calc_diffs",   sa.Integer, nullable=False, default=0),
        sa.Column("n_sanity_diffs", sa.Integer, nullable=False, default=0),
        sa.Column("detail",         sa.Text,    nullable=True),
        sa.Column("checked_at",     sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("asset_verification_flag")
