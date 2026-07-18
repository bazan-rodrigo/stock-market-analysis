"""Poblar ind_daily/ind_weekly/ind_monthly desde las ind_{code} per-código.

Cutover a tablas anchas (docs/notes/design_ind_wide_tables.md, fase 4): copia
byte a byte cada ind_{code}.value en la columna del código en la tabla ancha de
su cadencia. NO borra las ind_{code} viejas — quedan como red de rollback y se
dropean en una migración posterior (fase 5), tras validar.

Migración de DATOS (usa op.get_bind()): NO se renderiza offline. El guard de
is_offline_mode() la salta en el render del meta-test de portabilidad
(tests/test_bootstrap_portability); se verifica contra MySQL y PostgreSQL en el
entorno real. El upsert por columna acumula: cada código escribe/actualiza SOLO
su columna; las fechas sin valor para un código quedan en NULL (as-of fiel).

Revision ID: 0078
Revises: 0077
"""
import sqlalchemy as sa
from alembic import op

revision = "0078"
down_revision = "0077"
branch_labels = None
depends_on = None

# Autocontenido (snapshot): mismas listas que la 0077 / indicator_store._WIDE_*.
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
_WIDE = (("ind_daily", _DAILY), ("ind_weekly", _WEEKLY), ("ind_monthly", _MONTHLY))


def _copy_code(bind, wide: str, code: str) -> None:
    src = f"ind_{code}"
    if not sa.inspect(bind).has_table(src):
        return
    if bind.dialect.name in ("mysql", "mariadb"):
        bind.execute(sa.text(
            f"INSERT INTO `{wide}` (asset_id, date, `{code}`) "
            f"SELECT asset_id, date, value FROM `{src}` "
            f"ON DUPLICATE KEY UPDATE `{code}` = VALUES(`{code}`)"))
    else:  # postgresql (y sqlite, no usado: ON CONFLICT + comillas dobles)
        bind.execute(sa.text(
            f'INSERT INTO "{wide}" (asset_id, date, "{code}") '
            f'SELECT asset_id, date, value FROM "{src}" '
            f'ON CONFLICT (asset_id, date) DO UPDATE SET "{code}" = EXCLUDED."{code}"'))


def upgrade() -> None:
    if op.get_context().as_sql:
        return  # datos: no se renderiza offline (ver test_bootstrap_portability)
    bind = op.get_bind()
    for wide, codes in _WIDE:
        for code in codes:
            _copy_code(bind, wide, code)


def downgrade() -> None:
    if op.get_context().as_sql:
        return
    bind = op.get_bind()
    # Las ind_{code} viejas siguen intactas → basta vaciar las anchas.
    for wide, _codes in _WIDE:
        bind.execute(sa.text(f"DELETE FROM {wide}"))
