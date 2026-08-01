"""Columnas nuevas en las tablas anchas: price_position_52w, adx_* y rvol_daily.

Tres lecturas que el catálogo no tenía y que no se derivan de las que sí están:

- `price_position_52w`: posición del cierre dentro de su rango de 252 barras
  (0 = mínimo del año, 100 = máximo). NO es lo mismo que los `drawdown_*`, que
  miden contra el máximo ACUMULADO de toda la historia: un activo puede estar
  40% abajo de su máximo histórico y a la vez en el techo de sus últimas 52
  semanas.
- `adx_{daily,weekly,monthly}`: fuerza de la tendencia (ADX de Wilder, período
  fijo 14). Complementa a `trend_*`, que da la dirección pero no cuánto empuja:
  un `bullish_nascent` con ADX 12 es ruido y con ADX 28 es un movimiento ya
  iniciado, y hasta ahora nada distinguía esos dos casos.
- `rvol_daily`: volumen de la barra sobre el promedio de las 20 anteriores.
  Primer indicador del catálogo que usa la columna `prices.volume`, que existía
  pero no llegaba a ningún cálculo.

`rvol_daily` es también el primer indicador con COBERTURA PARCIAL a propósito:
los sintéticos calculados y las conversiones de moneda no tienen volumen propio
(un ratio no lo tiene) y quedan en NULL. Es una decisión, no una limitación —
pero tiene una consecuencia en el ranking que está documentada en
strategy_packs/SPEC.md: el score ponderado SALTEA los componentes sin valor y
renormaliza los pesos, así que una estrategia que puntúe por volumen tiene que
restringir el universo desde el filtro de elegibilidad (que sí excluye ante
valor ausente) o los activos sin volumen flotan hacia arriba.

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

Revision ID: 0098
Revises: 0097
"""
import sqlalchemy as sa
from alembic import op

revision = "0098"
down_revision = "0097"
branch_labels = None
depends_on = None

# (tabla, columna). Autocontenido (snapshot): NO importar app.
_COLUMNS = [
    ("ind_daily",   "price_position_52w"),
    ("ind_daily",   "adx_daily"),
    ("ind_daily",   "rvol_daily"),
    ("ind_weekly",  "adx_weekly"),
    ("ind_monthly", "adx_monthly"),
]


def upgrade() -> None:
    for table, column in _COLUMNS:
        op.add_column(table, sa.Column(column, sa.Float(precision=24),
                                       nullable=True))


def downgrade() -> None:
    for table, column in reversed(_COLUMNS):
        op.drop_column(table, column)
