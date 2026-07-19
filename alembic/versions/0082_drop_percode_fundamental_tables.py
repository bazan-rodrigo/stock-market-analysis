"""Limpieza fundamentales: DROP de las 12 ind_fundamental_* per-código.

Cierra el refactor wide de fundamentales (docs/notes/design_ind_wide_tables.md):
las columnas viven en ind_fundamental_daily (4 diarios) / ind_fundamental_quarterly
(8 trimestrales) desde la 0081, y el código las lee/escribe por defecto. Este
DROP libera el espacio — PUNTO DE NO RETORNO. Downgrade recrea las 12 tablas y
las repuebla desde las anchas (reverse pivot).

DDL (drop/create) renderiza offline; el repoblado del downgrade se saltea offline.

Revision ID: 0082
Revises: 0081
"""
import sqlalchemy as sa
from alembic import op

revision = "0082"
down_revision = "0081"
branch_labels = None
depends_on = None

# (code, tabla_ancha). Todos num (value FLOAT).
_MAP = [
    ("fundamental_pe_ttm", "ind_fundamental_daily"),
    ("fundamental_pb", "ind_fundamental_daily"),
    ("fundamental_ps_ttm", "ind_fundamental_daily"),
    ("fundamental_pe_growth_yoy", "ind_fundamental_daily"),
    ("fundamental_net_margin", "ind_fundamental_quarterly"),
    ("fundamental_gross_margin", "ind_fundamental_quarterly"),
    ("fundamental_operating_margin", "ind_fundamental_quarterly"),
    ("fundamental_debt_to_equity", "ind_fundamental_quarterly"),
    ("fundamental_revenue_growth_yoy", "ind_fundamental_quarterly"),
    ("fundamental_eps_growth_yoy", "ind_fundamental_quarterly"),
    ("fundamental_net_income_growth_yoy", "ind_fundamental_quarterly"),
    ("fundamental_roic", "ind_fundamental_quarterly"),
]


def _q(bind, name):
    return f"`{name}`" if bind.dialect.name in ("mysql", "mariadb") else f'"{name}"'


def upgrade() -> None:
    for code, _wide in _MAP:
        op.drop_table(f"ind_{code}")


def downgrade() -> None:
    for code, _wide in _MAP:
        name = f"ind_{code}"
        op.create_table(
            name,
            sa.Column("asset_id", sa.Integer(),
                      sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("value", sa.Float(), nullable=True),
            sa.PrimaryKeyConstraint("asset_id", "date"),
        )
        op.create_index(f"ix_{name}_date", name, ["date"])
    if not op.get_context().as_sql:
        bind = op.get_bind()
        for code, wide in _MAP:
            bind.execute(sa.text(
                f"INSERT INTO {_q(bind, 'ind_' + code)} (asset_id, date, value) "
                f"SELECT asset_id, date, {_q(bind, code)} FROM {_q(bind, wide)} "
                f"WHERE {_q(bind, code)} IS NOT NULL"))
