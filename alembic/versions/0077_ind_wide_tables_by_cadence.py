"""Tablas anchas de indicadores por cadencia: ind_daily/ind_weekly/ind_monthly.

Optimización de footprint (docs/notes/design_ind_wide_tables.md): agrupa los
indicadores técnicos con historia en 3 tablas anchas — una fila por
(asset_id, date), una columna por indicador — en lugar de una tabla ind_{code}
por indicador. Paga el overhead de fila+índice de InnoDB una vez por fecha en
vez de N. Lossless: la migración de datos (0078, aparte) copia todo sin perder
historia.

Esta migración solo CREA las tablas (vacías). DDL portable (sa puro), se
renderiza en MySQL y PostgreSQL (tests/test_bootstrap_portability). El cutover
de lectura/escritura ocurre en el código (fases 2-4 del diseño), no acá.

Revision ID: 0077
Revises: 0076
"""
import sqlalchemy as sa
from alembic import op

revision = "0077"
down_revision = "0076"
branch_labels = None
depends_on = None

# Autocontenido (snapshot): NO importar app — el esquema de la app evoluciona.
# Debe coincidir con indicator_store._WIDE_* / ensure_wide_ind_tables.
_DAILY = [
    "trend_daily", "volatility_daily", "atr_percentile_daily", "rsi_daily",
    "dist_sma20", "dist_sma50", "dist_sma200", "dist_optimal_sma_daily",
    "return_daily", "return_monthly", "return_quarterly", "return_yearly",
    "return_52w", "relative_strength_52w",
]
_WEEKLY = [
    "trend_weekly", "volatility_weekly", "atr_percentile_weekly",
    "rsi_weekly", "dist_optimal_sma_weekly",
]
_MONTHLY = [
    "trend_monthly", "volatility_monthly", "atr_percentile_monthly",
    "rsi_monthly", "dist_optimal_sma_monthly",
]
_STR = {
    "trend_daily", "trend_weekly", "trend_monthly",
    "volatility_daily", "volatility_weekly", "volatility_monthly",
}


def _create(name: str, codes: list) -> None:
    cols = [
        sa.Column("asset_id", sa.Integer,
                  sa.ForeignKey("assets.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("date", sa.Date, nullable=False),
    ]
    for code in codes:
        ctype = sa.String(50) if code in _STR else sa.Float
        cols.append(sa.Column(code, ctype, nullable=True))
    op.create_table(name, *cols, sa.PrimaryKeyConstraint("asset_id", "date"))
    op.create_index(f"ix_{name}_date", name, ["date"])


def upgrade() -> None:
    _create("ind_daily", _DAILY)
    _create("ind_weekly", _WEEKLY)
    _create("ind_monthly", _MONTHLY)


def downgrade() -> None:
    op.drop_table("ind_monthly")
    op.drop_table("ind_weekly")
    op.drop_table("ind_daily")
