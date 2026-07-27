"""Columnas nuevas en las tablas anchas: atr_pct_* y drawdown_pct_daily.

Da HISTORIA a dos lecturas que hasta ahora solo existían como valor vigente o
solo en el navegador:

- `atr_pct_{daily,weekly,monthly}`: ATR como % del cierre. El panel "ATR" del
  gráfico calcula el ATR ABSOLUTO en JS (unidades de precio): no es comparable
  entre activos ni a lo largo de la historia de uno que cambió de escala, así
  que lo que se persiste es el normalizado. No confundir con
  `atr_percentile_*`, que ya existía y es el rank del ATR (0-100).
- `drawdown_pct_daily`: la serie de la caída % desde el máximo acumulado. Su
  último valor coincide con `drawdown_current` (keep_history=False, sin tabla),
  que mide contra el mismo máximo. Solo cadencia diaria: el drawdown es
  acumulativo desde el máximo histórico y resamplearlo a W/M submuestrea la
  misma curva.

Con esto los cuatro aparecen solos en Posicionamiento Histórico, que filtra por
type='num' + keep_history=True.

Las FILAS de indicator_definitions NO se insertan acá: startup_service
.ensure_builtin_data las crea desde _BUILTIN_INDICATORS en cada arranque (y
actualiza metadatos). Esta migración solo hace el DDL que ese camino no cubre —
ensure_wide_ind_tables crea tablas ausentes, pero no agrega columnas a una que
ya existe.

Las columnas nacen NULL: después de aplicar hay que correr "Recalcular completo"
de estos indicadores en el Centro de Datos para llenar la historia.

Portable (post-0076): DDL de nombre fijo, float4 igual que el resto de las
columnas numéricas anchas (ver 0087) → se renderiza offline en ambos dialectos
(tests/test_bootstrap_portability). Espeja
indicator_store._WIDE_DAILY/_WIDE_WEEKLY/_WIDE_MONTHLY.

Revision ID: 0097
Revises: 0096
"""
import sqlalchemy as sa
from alembic import op

revision = "0097"
down_revision = "0096"
branch_labels = None
depends_on = None

# (tabla, columna). Autocontenido (snapshot): NO importar app.
_COLUMNS = [
    ("ind_daily",   "atr_pct_daily"),
    ("ind_daily",   "drawdown_pct_daily"),
    ("ind_weekly",  "atr_pct_weekly"),
    ("ind_monthly", "atr_pct_monthly"),
]


def upgrade() -> None:
    for table, column in _COLUMNS:
        op.add_column(table, sa.Column(column, sa.Float(precision=24),
                                       nullable=True))


def downgrade() -> None:
    for table, column in reversed(_COLUMNS):
        op.drop_column(table, column)
