"""resistance_pct y support_pct pasan a keep_history=False

Nunca tuvieron función de backfill (se recalculan sobre una ventana de 260
días terminando en la fecha de referencia, cara de recomputar por fecha
histórica). Se deja abierta la evaluación de implementar backfill más
adelante; por ahora se alinea el esquema con lo que realmente se calcula
(solo el valor vigente).

Revision ID: 0049
Revises: 0048
Create Date: 2026-07-03
"""
from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DROP TABLE IF EXISTS ind_resistance_pct")
    op.execute("DROP TABLE IF EXISTS ind_support_pct")
    op.execute(
        "UPDATE indicator_definitions SET keep_history = 0 "
        "WHERE code IN ('resistance_pct', 'support_pct')"
    )


def downgrade():
    import sqlalchemy as sa
    op.create_table(
        "ind_resistance_pct",
        sa.Column("asset_id", sa.Integer, sa.ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("date",     sa.Date,    primary_key=True),
        sa.Column("value",    sa.Float),
    )
    op.create_table(
        "ind_support_pct",
        sa.Column("asset_id", sa.Integer, sa.ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("date",     sa.Date,    primary_key=True),
        sa.Column("value",    sa.Float),
    )
    op.execute(
        "UPDATE indicator_definitions SET keep_history = 1 "
        "WHERE code IN ('resistance_pct', 'support_pct')"
    )
