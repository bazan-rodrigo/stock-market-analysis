"""EAV indicator storage: indicator_definitions + indicator_values;
slim screener_snapshot; drop indicator_snapshot; update signal indicator_key codes.

Revision ID: 0039
Revises: 0038
Create Date: 2026-06-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None

# Mapeo old indicator_key → new code (para signal_definitions)
_KEY_MAP = {
    "regime_d":          "trend_daily",
    "regime_w":          "trend_weekly",
    "regime_m":          "trend_monthly",
    "vol_d":             "volatility_daily",
    "vol_w":             "volatility_weekly",
    "vol_m":             "volatility_monthly",
    "atr_pct_d":         "atr_percentile_daily",
    "atr_pct_w":         "atr_percentile_weekly",
    "atr_pct_m":         "atr_percentile_monthly",
    "rsi":               "rsi_daily",
    "rsi_w":             "rsi_weekly",
    "rsi_m":             "rsi_monthly",
    "vs_sma20":          "dist_sma20",
    "vs_sma50":          "dist_sma50",
    "vs_sma200":         "dist_sma200",
    "dist_sma_d":        "dist_optimal_sma_daily",
    "dist_sma_w":        "dist_optimal_sma_weekly",
    "dist_sma_m":        "dist_optimal_sma_monthly",
    "dd_current":        "drawdown_current",
    "dd_max1":           "drawdown_max1",
    "dd_max2":           "drawdown_max2",
    "dd_max3":           "drawdown_max3",
    "var_daily":         "return_daily",
    "var_month":         "return_monthly",
    "var_quarter":       "return_quarterly",
    "var_year":          "return_yearly",
    "var_52w":           "return_52w",
    "pivot_resist_pct":  "resistance_pct",
    "pivot_support_pct": "support_pct",
    "last_close":        "last_close",
    "rel_strength_52w":  "relative_strength_52w",
}

# Columnas a eliminar de screener_snapshot
_SS_DROP = [
    "last_close", "var_daily", "var_month", "var_quarter", "var_year", "var_52w",
    "rsi", "rsi_w", "rsi_m",
    "vs_sma20", "vs_sma50", "vs_sma200",
    "dd_current", "dd_max1", "dd_max2", "dd_max3",
    "regime_d", "regime_w", "regime_m",
    "dist_sma_d", "dist_sma_w", "dist_sma_m",
    "vol_d", "vol_w", "vol_m",
    "atr_pct_d", "atr_pct_w", "atr_pct_m",
    "pivot_resist_pct", "pivot_support_pct",
]


def upgrade():
    # ── 1. Crear indicator_definitions ────────────────────────────────────────
    op.create_table(
        "indicator_definitions",
        sa.Column("id",          sa.Integer(),     nullable=False, autoincrement=True),
        sa.Column("code",        sa.String(50),    nullable=False),
        sa.Column("name",        sa.String(100),   nullable=False),
        sa.Column("category",    sa.String(50),    nullable=False),
        sa.Column("scale",       sa.String(50),    nullable=True),
        sa.Column("type",        sa.String(3),     nullable=False),
        sa.Column("description", sa.Text(),        nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_indicator_definitions_code", "indicator_definitions", ["code"])

    # ── 2. Crear indicator_values ─────────────────────────────────────────────
    op.create_table(
        "indicator_values",
        sa.Column("id",           sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("asset_id",     sa.Integer(), nullable=False),
        sa.Column("indicator_id", sa.Integer(), nullable=False),
        sa.Column("date",         sa.Date(),    nullable=False),
        sa.Column("value_num",    sa.Float(),   nullable=True),
        sa.Column("value_str",    sa.String(50), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id", "indicator_id", "date"),
        sa.ForeignKeyConstraint(["asset_id"],     ["assets.id"],              ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["indicator_id"], ["indicator_definitions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_indicator_values_asset_id",     "indicator_values", ["asset_id"])
    op.create_index("ix_indicator_values_indicator_id", "indicator_values", ["indicator_id"])
    op.create_index("ix_indicator_values_date",         "indicator_values", ["date"])

    # ── 3. Eliminar columnas de indicadores de screener_snapshot ──────────────
    for col in _SS_DROP:
        op.drop_column("screener_snapshot", col)

    # ── 4. Eliminar tabla indicator_snapshot ──────────────────────────────────
    op.drop_table("indicator_snapshot")

    # ── 5. Actualizar signal.indicator_key con nuevos códigos ────────────────
    conn = op.get_bind()
    for old_key, new_code in _KEY_MAP.items():
        conn.execute(
            sa.text(
                "UPDATE signal SET indicator_key = :new "
                "WHERE indicator_key = :old"
            ),
            {"new": new_code, "old": old_key},
        )


def downgrade():
    # Restaurar columnas en screener_snapshot
    _float_cols = [
        "last_close", "var_daily", "var_month", "var_quarter", "var_year", "var_52w",
        "rsi", "rsi_w", "rsi_m",
        "vs_sma20", "vs_sma50", "vs_sma200",
        "dd_current", "dd_max1", "dd_max2", "dd_max3",
        "dist_sma_d", "dist_sma_w", "dist_sma_m",
        "atr_pct_d", "atr_pct_w", "atr_pct_m",
        "pivot_resist_pct", "pivot_support_pct",
    ]
    _str_cols = [
        "regime_d", "regime_w", "regime_m",
        "vol_d", "vol_w", "vol_m",
    ]
    for col in _float_cols:
        op.add_column("screener_snapshot", sa.Column(col, sa.Float(), nullable=True))
    for col in _str_cols:
        op.add_column("screener_snapshot", sa.Column(col, sa.String(30), nullable=True))

    # Revertir indicator_key en signal_definitions
    conn = op.get_bind()
    for old_key, new_code in _KEY_MAP.items():
        conn.execute(
            sa.text(
                "UPDATE signal_definitions SET indicator_key = :old "
                "WHERE indicator_key = :new"
            ),
            {"old": old_key, "new": new_code},
        )

    op.drop_index("ix_indicator_values_date",         "indicator_values")
    op.drop_index("ix_indicator_values_indicator_id", "indicator_values")
    op.drop_index("ix_indicator_values_asset_id",     "indicator_values")
    op.drop_table("indicator_values")
    op.drop_index("ix_indicator_definitions_code", "indicator_definitions")
    op.drop_table("indicator_definitions")
