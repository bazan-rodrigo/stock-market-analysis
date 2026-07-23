"""float4 (precisión simple) en las 5 tablas anchas de indicadores.

Reduce footprint en PostgreSQL: Column(Float) sin precisión se materializó como
`double precision` (8 B) al migrar de MySQL, donde el mismo modelo daba FLOAT
(4 B). Declarar precisión simple restaura los 4 B por celda numérica — en
ind_daily son ~12 columnas float × millones de filas (la tabla más grande de la
base después de precios). Los valores guardados (RSI 0-100, distancias a medias
en %, retornos, percentiles) tienen 2-4 dígitos significativos; float4 da ~7.

NEUTRAL AL MOTOR (soporte dual, ver docs/notes/feedback_mariadb):
- MySQL: FLOAT → FLOAT(24) es el mismo tipo de 4 B → ALTER prácticamente no-op.
- PostgreSQL: double precision → real REESCRIBE la tabla (lock exclusivo por
  tabla mientras dura; tener disco temporal ~= tamaño de la tabla). Es una
  corrida de mantenimiento: correrla con el pipeline detenido.

Solo columnas NUMÉRICAS: trend_*/volatility_* son VARCHAR(50) categóricos y no
se tocan (eso es el ítem #3, aparte). DDL de nombre fijo y portable → se
renderiza offline en ambos dialectos (tests/test_bootstrap_portability).

Espeja indicator_store.ensure_wide_ind_tables (bases nuevas nacen ya en float4).

Revision ID: 0087
Revises: 0086
"""
import sqlalchemy as sa
from alembic import op

revision = "0087"
down_revision = "0086"
branch_labels = None
depends_on = None

# Autocontenido (snapshot): NO importar app. Debe coincidir con
# indicator_store._WIDE_CADENCE_COLUMNS / _WIDE_STR_CODES y las migraciones
# 0077 (ind_daily/weekly/monthly) y 0081 (fundamentales anchos).
_STR = {
    "trend_daily", "trend_weekly", "trend_monthly",
    "volatility_daily", "volatility_weekly", "volatility_monthly",
}
_TABLES = {
    "ind_daily": [
        "trend_daily", "volatility_daily", "atr_percentile_daily", "rsi_daily",
        "dist_sma20", "dist_sma50", "dist_sma200", "dist_optimal_sma_daily",
        "return_daily", "return_monthly", "return_quarterly", "return_yearly",
        "return_52w", "relative_strength_52w",
    ],
    "ind_weekly": [
        "trend_weekly", "volatility_weekly", "atr_percentile_weekly",
        "rsi_weekly", "dist_optimal_sma_weekly",
    ],
    "ind_monthly": [
        "trend_monthly", "volatility_monthly", "atr_percentile_monthly",
        "rsi_monthly", "dist_optimal_sma_monthly",
    ],
    "ind_fundamental_daily": [
        "fundamental_pe_ttm", "fundamental_pb", "fundamental_ps_ttm",
        "fundamental_pe_growth_yoy",
    ],
    "ind_fundamental_quarterly": [
        "fundamental_net_margin", "fundamental_gross_margin",
        "fundamental_operating_margin", "fundamental_debt_to_equity",
        "fundamental_revenue_growth_yoy", "fundamental_eps_growth_yoy",
        "fundamental_net_income_growth_yoy", "fundamental_roic",
    ],
}


def _retype(new_precision, old_precision) -> None:
    new_type = sa.Float(precision=new_precision) if new_precision else sa.Float()
    old_type = sa.Float(precision=old_precision) if old_precision else sa.Float()
    for table, codes in _TABLES.items():
        for code in codes:
            if code in _STR:
                continue
            op.alter_column(table, code, type_=new_type,
                            existing_type=old_type, existing_nullable=True)


def upgrade() -> None:
    _retype(24, None)          # double precision → real (PG) / FLOAT(24) (MySQL)


def downgrade() -> None:
    _retype(None, 24)          # vuelve a Float sin precisión (double en PG)
