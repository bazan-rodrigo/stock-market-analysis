"""signal_framework: indicator_snapshot, group_indicator_snapshot, signal/value/group tables,
strategy/component/result + seed de 16 señales iniciales y 1 estrategia ejemplo.

Revision ID: 0033
Revises: 0032
Create Date: 2026-04-26
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: Union[str, None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── indicator_snapshot ───────────────────────────────────────────────────
    op.create_table(
        "indicator_snapshot",
        sa.Column("id",       sa.Integer, primary_key=True),
        sa.Column("asset_id", sa.Integer, sa.ForeignKey("assets.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("date",     sa.Date, nullable=False),
        sa.Column("regime_d", sa.String(30)),
        sa.Column("regime_w", sa.String(30)),
        sa.Column("regime_m", sa.String(30)),
        sa.Column("dd_current",  sa.Float),
        sa.Column("dd_max1",     sa.Float),
        sa.Column("vol_d", sa.String(20)),
        sa.Column("vol_w", sa.String(20)),
        sa.Column("vol_m", sa.String(20)),
        sa.Column("atr_pct_d", sa.Float),
        sa.Column("atr_pct_w", sa.Float),
        sa.Column("atr_pct_m", sa.Float),
        sa.Column("rsi",   sa.Float),
        sa.Column("rsi_w", sa.Float),
        sa.Column("rsi_m", sa.Float),
        sa.Column("var_daily",   sa.Float),
        sa.Column("var_month",   sa.Float),
        sa.Column("var_quarter", sa.Float),
        sa.Column("var_year",    sa.Float),
        sa.Column("var_52w",     sa.Float),
        sa.Column("rel_strength_52w", sa.Float),
        sa.Column("dist_sma_d", sa.Float),
        sa.Column("dist_sma_w", sa.Float),
        sa.Column("dist_sma_m", sa.Float),
        sa.Column("vs_sma20",  sa.Float),
        sa.Column("vs_sma50",  sa.Float),
        sa.Column("vs_sma200", sa.Float),
        sa.Column("pivot_resist_pct",  sa.Float),
        sa.Column("pivot_support_pct", sa.Float),
        sa.Column("last_close", sa.Float),
        sa.UniqueConstraint("asset_id", "date"),
    )
    op.create_index("ix_indicator_snapshot_asset_id", "indicator_snapshot", ["asset_id"])
    op.create_index("ix_indicator_snapshot_date",     "indicator_snapshot", ["date"])

    # ── group_indicator_snapshot ─────────────────────────────────────────────
    op.create_table(
        "group_indicator_snapshot",
        sa.Column("id",         sa.Integer, primary_key=True),
        sa.Column("group_type", sa.String(30), nullable=False),
        sa.Column("group_id",   sa.Integer,    nullable=False),
        sa.Column("date",       sa.Date,       nullable=False),
        sa.Column("regime_score_d", sa.Float),
        sa.Column("regime_score_w", sa.Float),
        sa.Column("regime_score_m", sa.Float),
        sa.Column("n_assets", sa.Integer),
        sa.UniqueConstraint("group_type", "group_id", "date"),
    )
    op.create_index("ix_group_indicator_snapshot_group",
                    "group_indicator_snapshot", ["group_type", "group_id"])
    op.create_index("ix_group_indicator_snapshot_date",
                    "group_indicator_snapshot", ["date"])

    # ── signal ───────────────────────────────────────────────────────────────
    op.create_table(
        "signal",
        sa.Column("id",            sa.Integer,     primary_key=True),
        sa.Column("key",           sa.String(50),  nullable=False, unique=True),
        sa.Column("name",          sa.String(100), nullable=False),
        sa.Column("description",   sa.Text),
        sa.Column("source",        sa.String(10),  nullable=False),
        sa.Column("group_type",    sa.String(30)),
        sa.Column("indicator_key", sa.String(50)),
        sa.Column("formula_type",  sa.String(20),  nullable=False),
        sa.Column("params",        sa.Text,        nullable=False),
        sa.Column("is_system",     sa.Boolean,     nullable=False, server_default="1"),
        sa.Column("created_at",    sa.DateTime,    nullable=False,
                  server_default=sa.text("NOW()")),
    )

    # ── signal_value ─────────────────────────────────────────────────────────
    op.create_table(
        "signal_value",
        sa.Column("id",        sa.Integer, primary_key=True),
        sa.Column("signal_id", sa.Integer, sa.ForeignKey("signal.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("asset_id",  sa.Integer, sa.ForeignKey("assets.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("date",  sa.Date,  nullable=False),
        sa.Column("score", sa.Float, nullable=False),
        sa.UniqueConstraint("signal_id", "asset_id", "date"),
    )
    op.create_index("ix_signal_value_signal_id", "signal_value", ["signal_id"])
    op.create_index("ix_signal_value_asset_id",  "signal_value", ["asset_id"])
    op.create_index("ix_signal_value_date",      "signal_value", ["date"])

    # ── group_signal_value ───────────────────────────────────────────────────
    op.create_table(
        "group_signal_value",
        sa.Column("id",         sa.Integer,    primary_key=True),
        sa.Column("signal_id",  sa.Integer,    sa.ForeignKey("signal.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("group_type", sa.String(30), nullable=False),
        sa.Column("group_id",   sa.Integer,    nullable=False),
        sa.Column("date",  sa.Date,  nullable=False),
        sa.Column("score", sa.Float, nullable=False),
        sa.UniqueConstraint("signal_id", "group_type", "group_id", "date"),
    )
    op.create_index("ix_group_signal_value_signal_id", "group_signal_value", ["signal_id"])
    op.create_index("ix_group_signal_value_date",      "group_signal_value", ["date"])

    # ── strategy ─────────────────────────────────────────────────────────────
    op.create_table(
        "strategy",
        sa.Column("id",           sa.Integer,     primary_key=True),
        sa.Column("name",         sa.String(100), nullable=False),
        sa.Column("description",  sa.Text),
        sa.Column("asset_filter", sa.Text),
        sa.Column("created_by",   sa.Integer,
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime, nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime, nullable=False,
                  server_default=sa.text("NOW()")),
    )

    # ── strategy_component ───────────────────────────────────────────────────
    op.create_table(
        "strategy_component",
        sa.Column("id",          sa.Integer,    primary_key=True),
        sa.Column("strategy_id", sa.Integer,
                  sa.ForeignKey("strategy.id", ondelete="CASCADE"), nullable=False),
        sa.Column("signal_id",   sa.Integer,
                  sa.ForeignKey("signal.id",   ondelete="RESTRICT"), nullable=False),
        sa.Column("weight",      sa.Float,      nullable=False, server_default="1.0"),
        sa.Column("scope",       sa.String(20)),
        sa.Column("group_type",  sa.String(30)),
        sa.Column("group_id",    sa.Integer),
    )
    op.create_index("ix_strategy_component_strategy_id",
                    "strategy_component", ["strategy_id"])

    # ── strategy_result ──────────────────────────────────────────────────────
    op.create_table(
        "strategy_result",
        sa.Column("id",          sa.Integer, primary_key=True),
        sa.Column("strategy_id", sa.Integer,
                  sa.ForeignKey("strategy.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id",    sa.Integer,
                  sa.ForeignKey("assets.id",   ondelete="CASCADE"), nullable=False),
        sa.Column("date",  sa.Date,    nullable=False),
        sa.Column("score", sa.Float),
        sa.Column("rank",  sa.Integer),
        sa.UniqueConstraint("strategy_id", "asset_id", "date"),
    )
    op.create_index("ix_strategy_result_strategy_id", "strategy_result", ["strategy_id"])
    op.create_index("ix_strategy_result_asset_id",    "strategy_result", ["asset_id"])
    op.create_index("ix_strategy_result_date",        "strategy_result", ["date"])

    # ── Seed: señales iniciales ───────────────────────────────────────────────
    _seed_signals()


def _seed_signals() -> None:
    REGIME_MAP = json.dumps({"map": {
        "bullish_strong":         100,
        "bullish_nascent_strong":  75,
        "bullish":                 60,
        "bullish_nascent":         40,
        "lateral_nascent":          5,
        "lateral":                  0,
        "bearish_nascent":        -40,
        "bearish_nascent_strong": -75,
        "bearish":                -60,
        "bearish_strong":        -100,
    }})

    VOL_MAP = json.dumps({"map": {
        "normal_corta":  100, "normal_media":  75,  "normal_larga":  50,
        "baja_corta":     25, "baja_media":     0,  "baja_larga":   -25,
        "alta_corta":    -25, "alta_media":   -50,  "alta_larga":   -75,
        "extrema_corta": -50, "extrema_media": -75, "extrema_larga": -100,
    }})

    # threshold: [[upper_limit, score], ..., [null, default_score]]
    # evaluación: si valor > limit → retorna score; null = default
    DD_PARAMS = json.dumps({"thresholds": [
        [-5,   100],
        [-15,   50],
        [-30,    0],
        [None, -50],
    ]})

    RSI_PARAMS = json.dumps({"thresholds": [
        [70,  -100],
        [55,   -50],
        [45,     0],
        [30,    50],
        [None, 100],
    ]})

    IDENTITY_RANGE = json.dumps({"min": -100, "max": 100, "clamp": True})

    DIST_SMA_PARAMS = json.dumps({"min": -3.0, "max": 3.0, "clamp": True})

    ALIGN_PARAMS = json.dumps({"components": [
        {"signal_key": "tendencia_d", "weight": 1},
        {"signal_key": "tendencia_w", "weight": 1},
        {"signal_key": "tendencia_m", "weight": 1},
    ]})

    signals = [
        # key, name, source, group_type, indicator_key, formula_type, params
        ("tendencia_d", "Tendencia diaria",
         "asset", None, "regime_d", "discrete_map", REGIME_MAP),
        ("tendencia_w", "Tendencia semanal",
         "asset", None, "regime_w", "discrete_map", REGIME_MAP),
        ("tendencia_m", "Tendencia mensual",
         "asset", None, "regime_m", "discrete_map", REGIME_MAP),

        ("volatilidad_d", "Volatilidad diaria",
         "asset", None, "vol_d", "discrete_map", VOL_MAP),
        ("volatilidad_w", "Volatilidad semanal",
         "asset", None, "vol_w", "discrete_map", VOL_MAP),
        ("volatilidad_m", "Volatilidad mensual",
         "asset", None, "vol_m", "discrete_map", VOL_MAP),

        ("drawdown_controlado", "Drawdown controlado",
         "asset", None, "dd_current", "threshold", DD_PARAMS),

        ("rsi_señal", "RSI señal",
         "asset", None, "rsi", "threshold", RSI_PARAMS),

        ("dist_sma_d", "Distancia SMA diaria (z-score)",
         "asset", None, "dist_sma_d", "range", DIST_SMA_PARAMS),

        ("alineacion_timeframes", "Alineación de timeframes",
         "asset", None, None, "composite", ALIGN_PARAMS),

        ("tendencia_sector_d", "Tendencia sector diaria",
         "group", "sector", "regime_score_d", "range", IDENTITY_RANGE),
        ("tendencia_sector_w", "Tendencia sector semanal",
         "group", "sector", "regime_score_w", "range", IDENTITY_RANGE),
        ("tendencia_sector_m", "Tendencia sector mensual",
         "group", "sector", "regime_score_m", "range", IDENTITY_RANGE),

        ("tendencia_mercado_d", "Tendencia mercado diaria",
         "group", "market", "regime_score_d", "range", IDENTITY_RANGE),
        ("tendencia_mercado_w", "Tendencia mercado semanal",
         "group", "market", "regime_score_w", "range", IDENTITY_RANGE),
        ("tendencia_mercado_m", "Tendencia mercado mensual",
         "group", "market", "regime_score_m", "range", IDENTITY_RANGE),
    ]

    signal_table = sa.table("signal",
        sa.column("key",           sa.String),
        sa.column("name",          sa.String),
        sa.column("source",        sa.String),
        sa.column("group_type",    sa.String),
        sa.column("indicator_key", sa.String),
        sa.column("formula_type",  sa.String),
        sa.column("params",        sa.String),
        sa.column("is_system",     sa.Boolean),
    )

    op.bulk_insert(signal_table, [
        {
            "key": key, "name": name, "source": source,
            "group_type": group_type, "indicator_key": indicator_key,
            "formula_type": formula_type, "params": params,
            "is_system": True,
        }
        for key, name, source, group_type, indicator_key, formula_type, params in signals
    ])

    # ── Seed: estrategia ejemplo ─────────────────────────────────────────────
    # Inserta la estrategia y sus componentes usando SQL directo
    # (los IDs de señales son 1-16 en el orden del seed)
    op.execute(sa.text(
        "INSERT INTO strategy (name, description, asset_filter) VALUES "
        "('Estrategia ejemplo', "
        "'Combina tendencia diaria, sector, alineación de timeframes, "
        "drawdown y volatilidad.', NULL)"
    ))
    op.execute(sa.text("""
        INSERT INTO strategy_component (strategy_id, signal_id, weight, scope, group_type, group_id)
        SELECT 1, id, weight, scope, group_type, NULL FROM (
            SELECT id, 0.30 AS weight, NULL  AS scope, NULL     AS group_type FROM signal WHERE key='tendencia_d'
            UNION ALL
            SELECT id, 0.20,           'own_group', 'sector'                  FROM signal WHERE key='tendencia_sector_d'
            UNION ALL
            SELECT id, 0.10,           NULL,        NULL                       FROM signal WHERE key='alineacion_timeframes'
            UNION ALL
            SELECT id, 0.15,           NULL,        NULL                       FROM signal WHERE key='drawdown_controlado'
            UNION ALL
            SELECT id, 0.10,           NULL,        NULL                       FROM signal WHERE key='volatilidad_d'
            UNION ALL
            SELECT id, 0.15,           'own_group', 'market'                  FROM signal WHERE key='tendencia_mercado_d'
        ) t
    """))


def downgrade() -> None:
    op.drop_table("strategy_result")
    op.drop_table("strategy_component")
    op.drop_table("strategy")
    op.drop_table("group_signal_value")
    op.drop_table("signal_value")
    op.drop_table("signal")
    op.drop_table("group_indicator_snapshot")
    op.drop_table("indicator_snapshot")
