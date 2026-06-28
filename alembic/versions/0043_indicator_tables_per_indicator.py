"""Reemplazar indicator_values EAV con una tabla por indicador.

- Crea current_indicator_values para keep_history=False (best_sma/ema_*)
- Crea ind_{code} por cada indicador con keep_history=True (42 tablas)
  PK compuesta (asset_id, date) — sin columna id autoincrement
- Migra datos desde indicator_values hacia las tablas correspondientes
- Elimina indicator_values

Revision ID: 0043
Revises: 0042
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None

# Indicadores con keep_history=True y su tipo de columna value
_HIST_INDICATORS = [
    # Tendencia (str)
    ("trend_daily",              "str"),
    ("trend_weekly",             "str"),
    ("trend_monthly",            "str"),
    # Volatilidad régimen (str)
    ("volatility_daily",         "str"),
    ("volatility_weekly",        "str"),
    ("volatility_monthly",       "str"),
    # Volatilidad ATR percentil (num)
    ("atr_percentile_daily",     "num"),
    ("atr_percentile_weekly",    "num"),
    ("atr_percentile_monthly",   "num"),
    # RSI (num)
    ("rsi_daily",                "num"),
    ("rsi_weekly",               "num"),
    ("rsi_monthly",              "num"),
    # Distancia SMAs fijas (num)
    ("dist_sma20",               "num"),
    ("dist_sma50",               "num"),
    ("dist_sma200",              "num"),
    # Distancia SMA óptima (num)
    ("dist_optimal_sma_daily",   "num"),
    ("dist_optimal_sma_weekly",  "num"),
    ("dist_optimal_sma_monthly", "num"),
    # Drawdown (num)
    ("drawdown_current",         "num"),
    ("drawdown_max1",            "num"),
    ("drawdown_max2",            "num"),
    ("drawdown_max3",            "num"),
    # Retornos (num)
    ("return_daily",             "num"),
    ("return_monthly",           "num"),
    ("return_quarterly",         "num"),
    ("return_yearly",            "num"),
    ("return_52w",               "num"),
    # Soporte / Resistencia (num)
    ("resistance_pct",           "num"),
    ("support_pct",              "num"),
    # Precio (num)
    ("last_close",               "num"),
    # Fuerza relativa (num)
    ("relative_strength_52w",    "num"),
    # Fundamentales (num)
    ("fundamental_pe_ttm",             "num"),
    ("fundamental_pb",                 "num"),
    ("fundamental_ps_ttm",             "num"),
    ("fundamental_net_margin",         "num"),
    ("fundamental_gross_margin",       "num"),
    ("fundamental_operating_margin",   "num"),
    ("fundamental_debt_to_equity",     "num"),
    ("fundamental_revenue_growth_yoy", "num"),
    ("fundamental_eps_growth_yoy",     "num"),
    ("fundamental_pe_growth_yoy",      "num"),
    ("fundamental_roic",               "num"),
]

# Indicadores keep_history=False → current_indicator_values
_NO_HIST_CODES = [
    "best_sma_d", "best_ema_d",
    "best_sma_w", "best_ema_w",
    "best_sma_m", "best_ema_m",
]


def upgrade() -> None:
    bind = op.get_bind()

    # ── 1. Crear current_indicator_values ─────────────────────────────────────
    op.create_table(
        "current_indicator_values",
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("code",     sa.String(50), nullable=False),
        sa.Column("value_num", sa.Float(),    nullable=True),
        sa.Column("value_str", sa.String(50), nullable=True),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("asset_id", "code"),
    )

    # Migrar indicadores sin historia → current_indicator_values
    for code in _NO_HIST_CODES:
        bind.execute(sa.text("""
            INSERT INTO current_indicator_values (asset_id, code, value_num, value_str)
            SELECT iv.asset_id, :code, iv.value_num, iv.value_str
            FROM indicator_values iv
            JOIN indicator_definitions idef ON iv.indicator_id = idef.id
            WHERE idef.code = :code
            ON DUPLICATE KEY UPDATE value_num = VALUES(value_num), value_str = VALUES(value_str)
        """), {"code": code})

    # ── 2. Crear ind_{code} para cada indicador con historia ──────────────────
    for code, ind_type in _HIST_INDICATORS:
        table_name = f"ind_{code}"
        vcol = sa.Column("value", sa.String(50), nullable=True) \
               if ind_type == "str" \
               else sa.Column("value", sa.Float(), nullable=True)

        op.create_table(
            table_name,
            sa.Column("asset_id", sa.Integer(), nullable=False),
            sa.Column("date",     sa.Date(),    nullable=False),
            vcol,
            sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("asset_id", "date"),
        )

        # Migrar datos desde indicator_values
        if ind_type == "str":
            bind.execute(sa.text(f"""
                INSERT INTO `{table_name}` (asset_id, date, value)
                SELECT iv.asset_id, iv.date, iv.value_str
                FROM indicator_values iv
                JOIN indicator_definitions idef ON iv.indicator_id = idef.id
                WHERE idef.code = :code AND iv.value_str IS NOT NULL
            """), {"code": code})
        else:
            bind.execute(sa.text(f"""
                INSERT INTO `{table_name}` (asset_id, date, value)
                SELECT iv.asset_id, iv.date, iv.value_num
                FROM indicator_values iv
                JOIN indicator_definitions idef ON iv.indicator_id = idef.id
                WHERE idef.code = :code AND iv.value_num IS NOT NULL
            """), {"code": code})

    # ── 3. Eliminar indicator_values ──────────────────────────────────────────
    op.drop_table("indicator_values")


def downgrade() -> None:
    bind = op.get_bind()

    # Recrear indicator_values
    op.create_table(
        "indicator_values",
        sa.Column("id",           sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("asset_id",     sa.Integer(), nullable=False),
        sa.Column("indicator_id", sa.Integer(), nullable=False),
        sa.Column("date",         sa.Date(),    nullable=False),
        sa.Column("value_num",    sa.Float(),   nullable=True),
        sa.Column("value_str",    sa.String(50), nullable=True),
        sa.ForeignKeyConstraint(["asset_id"],     ["assets.id"],              ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["indicator_id"], ["indicator_definitions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id", "indicator_id", "date"),
    )

    # Restaurar desde ind_* tables
    for code, ind_type in _HIST_INDICATORS:
        table_name = f"ind_{code}"
        col = "value_str" if ind_type == "str" else "value_num"
        bind.execute(sa.text(f"""
            INSERT INTO indicator_values (asset_id, indicator_id, date, {col})
            SELECT t.asset_id, idef.id, t.date, t.value
            FROM `{table_name}` t
            JOIN indicator_definitions idef ON idef.code = :code
        """), {"code": code})
        op.drop_table(table_name)

    # Restaurar keep_history=False desde current_indicator_values
    for code in _NO_HIST_CODES:
        bind.execute(sa.text("""
            INSERT INTO indicator_values (asset_id, indicator_id, date, value_num, value_str)
            SELECT civ.asset_id, idef.id, CURRENT_DATE(), civ.value_num, civ.value_str
            FROM current_indicator_values civ
            JOIN indicator_definitions idef ON idef.code = civ.code
            WHERE civ.code = :code
        """), {"code": code})

    op.drop_table("current_indicator_values")
