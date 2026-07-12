"""Eliminar el concepto de senales/estrategias "de sistema".

Las definiciones ahora se gestionan por Excel (strategy_packs/): toda
senal debe estar usada por alguna estrategia — las que no, solo agregan
costo de procesamiento al pipeline diario y al backfill.

1. Borra la estrategia seed "Estrategia ejemplo" (0033) con sus
   componentes y resultados (cascade).
2. Borra las senales del seed que ninguna estrategia referencia
   (volatilidad_*, drawdown_controlado, tendencia_sector_*,
   tendencia_mercado_* — y cualquier otra del seed que haya quedado sin
   uso). El chequeo de referencia es real (LEFT JOIN a
   strategy_component), no una lista a ciegas: si el usuario uso alguna
   en una estrategia propia, se conserva. Los signal_value/
   group_signal_value asociados caen por cascade.
3. Dropea signal.is_system: sin seed, todas las senales son iguales
   (editables/borrables); la identidad la da la key.

Revision ID: 0064
Revises: 0063
"""
import sqlalchemy as sa
from alembic import op

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None

_SEED_STRATEGY = "Estrategia ejemplo"

_SEED_SIGNAL_KEYS = (
    "tendencia_d", "tendencia_w", "tendencia_m",
    "volatilidad_d", "volatilidad_w", "volatilidad_m",
    "drawdown_controlado", "rsi_señal", "dist_sma_d",
    "alineacion_timeframes",
    "tendencia_sector_d", "tendencia_sector_w", "tendencia_sector_m",
    "tendencia_mercado_d", "tendencia_mercado_w", "tendencia_mercado_m",
)


def upgrade() -> None:
    import json

    bind = op.get_bind()

    bind.execute(sa.text(
        "DELETE FROM strategy WHERE name = :n"), {"n": _SEED_STRATEGY})

    # Señales protegidas: las referenciadas por composites que a su vez usa
    # alguna estrategia (resuelto en Python — un NOT EXISTS sobre `signal`
    # dentro del DELETE daría error 1093 en MariaDB)
    protected: set[str] = set()
    rows = bind.execute(sa.text(
        "SELECT DISTINCT c.params FROM `signal` c "
        "JOIN strategy_component sc ON sc.signal_id = c.id "
        "WHERE c.formula_type = 'composite'"
    )).fetchall()
    for (params,) in rows:
        try:
            protected |= {
                comp.get("signal_key")
                for comp in json.loads(params).get("components", [])
            }
        except (TypeError, ValueError):
            pass

    deletable = [k for k in _SEED_SIGNAL_KEYS if k not in protected]
    if deletable:
        keys = ",".join(f"'{k}'" for k in deletable)
        bind.execute(sa.text(f"""
            DELETE s FROM `signal` s
            LEFT JOIN strategy_component sc ON sc.signal_id = s.id
            WHERE sc.id IS NULL AND s.`key` IN ({keys})
        """))

    op.drop_column("signal", "is_system")


def downgrade() -> None:
    # Los datos borrados no se restauran (reimportar desde
    # strategy_packs/); solo se repone la columna.
    op.add_column("signal", sa.Column(
        "is_system", sa.Boolean(), nullable=False, server_default=sa.text("0")))
