"""fundamental_eps_growth_yoy media crecimiento de Net Income, no de EPS por
accion - nombre enganoso. Se separa en dos indicadores: eps_growth_yoy pasa
a calcularse con eps_actual (EPS real), y se crea net_income_growth_yoy con
la formula vieja (net_income Q vs Q-4).

La tabla ind_fundamental_eps_growth_yoy ya tenia guardados los valores
correctos para el indicador NUEVO (net_income_growth_yoy) porque hasta
ahora calculaba justamente eso - se copian tal cual, sin recalcular. La
tabla vieja se vacia: la proxima corrida de fundamentales la repuebla sola
con la formula nueva (el delta llena "fechas faltantes"; con la tabla
vacia, todas las fechas estan faltantes).

Revision ID: 0060
Revises: 0059
"""
import sqlalchemy as sa
from alembic import op

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None

_OLD_TABLE = "ind_fundamental_eps_growth_yoy"
_NEW_TABLE = "ind_fundamental_net_income_growth_yoy"


def upgrade() -> None:
    op.create_table(
        _NEW_TABLE,
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("date",     sa.Date(),    nullable=False),
        sa.Column("value",    sa.Float(),   nullable=True),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("asset_id", "date"),
    )

    bind = op.get_bind()
    bind.execute(sa.text(
        f"INSERT INTO `{_NEW_TABLE}` (asset_id, date, value) "
        f"SELECT asset_id, date, value FROM `{_OLD_TABLE}`"
    ))
    bind.execute(sa.text(f"TRUNCATE TABLE `{_OLD_TABLE}`"))


def downgrade() -> None:
    op.drop_table(_NEW_TABLE)
    # No se restaura el contenido de ind_fundamental_eps_growth_yoy (quedo
    # vacia en el upgrade) - se repuebla sola en la proxima corrida de
    # fundamentales, igual que en el upgrade.
