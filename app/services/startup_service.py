import logging

logger = logging.getLogger(__name__)

_BUILTIN_SOURCES = [
    {"name": "Yahoo Finance", "description": "Fuente de precios de Yahoo Finance (yfinance)."},
    {"name": "Ambito",        "description": "Riesgo País Argentina (EMBI JP Morgan) vía Ámbito Financiero. Ticker: RIESGO_PAIS_AR."},
    {"name": "Calculado",     "description": "Fuente interna para activos sintéticos calculados."},
]

_BUILTIN_INDICATORS = [
    # Tendencia
    {"code": "trend_daily",              "name": "Trend Daily",               "category": "Trend",            "type": "str", "scale": "Categorical", "description": "Trend regime in daily timeframe based on the best-fit MA (e.g. bullish_strong, bearish)"},
    {"code": "trend_weekly",             "name": "Trend Weekly",              "category": "Trend",            "type": "str", "scale": "Categorical", "description": "Trend regime in weekly timeframe"},
    {"code": "trend_monthly",            "name": "Trend Monthly",             "category": "Trend",            "type": "str", "scale": "Categorical", "description": "Trend regime in monthly timeframe"},
    # Volatilidad — régimen
    {"code": "volatility_daily",         "name": "Volatility Daily",          "category": "Volatility",       "type": "str", "scale": "Categorical", "full_sample": True,  "description": "ATR volatility regime in daily timeframe (e.g. high_long, normal_short)"},
    {"code": "volatility_weekly",        "name": "Volatility Weekly",         "category": "Volatility",       "type": "str", "scale": "Categorical", "full_sample": True,  "description": "ATR volatility regime in weekly timeframe"},
    {"code": "volatility_monthly",       "name": "Volatility Monthly",        "category": "Volatility",       "type": "str", "scale": "Categorical", "full_sample": True,  "description": "ATR volatility regime in monthly timeframe"},
    # Volatilidad — percentil ATR
    {"code": "atr_percentile_daily",     "name": "ATR Percentile Daily",      "category": "Volatility",       "type": "num", "scale": "0 – 100",     "full_sample": True,  "description": "Percentile of current ATR relative to asset history (daily)"},
    {"code": "atr_percentile_weekly",    "name": "ATR Percentile Weekly",     "category": "Volatility",       "type": "num", "scale": "0 – 100",     "full_sample": True,  "description": "Percentile of current ATR relative to asset history (weekly)"},
    {"code": "atr_percentile_monthly",   "name": "ATR Percentile Monthly",    "category": "Volatility",       "type": "num", "scale": "0 – 100",     "full_sample": True,  "description": "Percentile of current ATR relative to asset history (monthly)"},
    # RSI
    {"code": "rsi_daily",                "name": "RSI Daily",                 "category": "Momentum",         "type": "num", "scale": "0 – 100",     "description": "Relative Strength Index 14 periods (daily)"},
    {"code": "rsi_weekly",               "name": "RSI Weekly",                "category": "Momentum",         "type": "num", "scale": "0 – 100",     "description": "RSI 14 periods (weekly)"},
    {"code": "rsi_monthly",              "name": "RSI Monthly",               "category": "Momentum",         "type": "num", "scale": "0 – 100",     "description": "RSI 14 periods (monthly)"},
    # Distancia a SMAs fijas
    {"code": "dist_sma20",               "name": "Distance % to SMA 20",      "category": "Trend - SMA",      "type": "num", "scale": "%",           "description": "Percentage distance from price to 20-period simple moving average"},
    {"code": "dist_sma50",               "name": "Distance % to SMA 50",      "category": "Trend - SMA",      "type": "num", "scale": "%",           "description": "Percentage distance from price to 50-period simple moving average"},
    {"code": "dist_sma200",              "name": "Distance % to SMA 200",     "category": "Trend - SMA",      "type": "num", "scale": "%",           "description": "Percentage distance from price to 200-period simple moving average"},
    # Distancia a SMA óptima
    {"code": "dist_optimal_sma_daily",   "name": "Distance σ Optimal SMA Daily",   "category": "Trend - SMA", "type": "num", "scale": "σ",           "description": "Distance in standard deviations from the best-fit MA (daily)"},
    {"code": "dist_optimal_sma_weekly",  "name": "Distance σ Optimal SMA Weekly",  "category": "Trend - SMA", "type": "num", "scale": "σ",           "description": "Distance in standard deviations from the best-fit MA (weekly)"},
    {"code": "dist_optimal_sma_monthly", "name": "Distance σ Optimal SMA Monthly", "category": "Trend - SMA", "type": "num", "scale": "σ",           "description": "Distance in standard deviations from the best-fit MA (monthly)"},
    # Drawdown
    {"code": "drawdown_current",         "name": "Drawdown Current",          "category": "Drawdown",         "type": "num", "scale": "% (negative)", "keep_history": False, "description": "Percentage fall from recent peak to current price"},
    {"code": "drawdown_max1",            "name": "Drawdown Max 1",            "category": "Drawdown",         "type": "num", "scale": "% (negative)", "keep_history": False, "description": "Largest drawdown in asset history"},
    {"code": "drawdown_max2",            "name": "Drawdown Max 2",            "category": "Drawdown",         "type": "num", "scale": "% (negative)", "description": "Second largest drawdown in asset history"},
    {"code": "drawdown_max3",            "name": "Drawdown Max 3",            "category": "Drawdown",         "type": "num", "scale": "% (negative)", "description": "Third largest drawdown in asset history"},
    # Retornos
    {"code": "return_daily",             "name": "Return Daily",              "category": "Returns",          "type": "num", "scale": "%",           "description": "Return of the last trading day"},
    {"code": "return_monthly",           "name": "Return Monthly",            "category": "Returns",          "type": "num", "scale": "%",           "description": "Return over the last calendar month"},
    {"code": "return_quarterly",         "name": "Return Quarterly",          "category": "Returns",          "type": "num", "scale": "%",           "description": "Return over the last quarter"},
    {"code": "return_yearly",            "name": "Return Yearly",             "category": "Returns",          "type": "num", "scale": "%",           "description": "Return over the last 12 months"},
    {"code": "return_52w",               "name": "Return 52 Weeks",           "category": "Returns",          "type": "num", "scale": "%",           "description": "Return over the last 52 calendar weeks"},
    # Soporte / Resistencia
    {"code": "resistance_pct",           "name": "Distance % to Resistance",  "category": "Support/Resistance", "type": "num", "scale": "%",         "description": "Percentage distance to the nearest pivot resistance above price"},
    {"code": "support_pct",              "name": "Distance % to Support",     "category": "Support/Resistance", "type": "num", "scale": "%",         "description": "Percentage distance to the nearest pivot support below price"},
    # Fuerza relativa
    {"code": "relative_strength_52w",    "name": "Relative Strength 52W",     "category": "Returns",          "type": "num", "scale": "%",           "description": "Return 52W minus benchmark return 52W"},
    # MA óptima por timeframe (valor vigente, sin historia)
    {"code": "best_sma_d", "name": "Best SMA Daily",   "category": "Trend - SMA", "type": "num", "scale": "period", "description": "SMA period that best acts as support/resistance in daily timeframe",   "keep_history": False},
    {"code": "best_ema_d", "name": "Best EMA Daily",   "category": "Trend - SMA", "type": "num", "scale": "period", "description": "EMA period that best acts as support/resistance in daily timeframe",   "keep_history": False},
    {"code": "best_sma_w", "name": "Best SMA Weekly",  "category": "Trend - SMA", "type": "num", "scale": "period", "description": "SMA period that best acts as support/resistance in weekly timeframe",  "keep_history": False},
    {"code": "best_ema_w", "name": "Best EMA Weekly",  "category": "Trend - SMA", "type": "num", "scale": "period", "description": "EMA period that best acts as support/resistance in weekly timeframe",  "keep_history": False},
    {"code": "best_sma_m", "name": "Best SMA Monthly", "category": "Trend - SMA", "type": "num", "scale": "period", "description": "SMA period that best acts as support/resistance in monthly timeframe", "keep_history": False},
    {"code": "best_ema_m", "name": "Best EMA Monthly", "category": "Trend - SMA", "type": "num", "scale": "period", "description": "EMA period that best acts as support/resistance in monthly timeframe", "keep_history": False},
    # Fundamentales
    {"code": "fundamental_pe_ttm",             "name": "P/E TTM",                      "category": "Fundamental",  "type": "num", "scale": "ratio",       "description": "Price / Trailing 12M EPS"},
    {"code": "fundamental_pb",                 "name": "P/B",                          "category": "Fundamental",  "type": "num", "scale": "ratio",       "description": "Price / Book Value per Share"},
    {"code": "fundamental_ps_ttm",             "name": "P/S TTM",                      "category": "Fundamental",  "type": "num", "scale": "ratio",       "description": "Price / Trailing 12M Revenue per Share"},
    {"code": "fundamental_net_margin",         "name": "Net Margin",                   "category": "Fundamental",  "type": "num", "scale": "ratio",       "description": "Net Income / Revenue (latest quarter)"},
    {"code": "fundamental_gross_margin",       "name": "Gross Margin",                 "category": "Fundamental",  "type": "num", "scale": "ratio",       "description": "Gross Profit / Revenue (latest quarter)"},
    {"code": "fundamental_operating_margin",   "name": "Operating Margin",             "category": "Fundamental",  "type": "num", "scale": "ratio",       "description": "Operating Income / Revenue (latest quarter)"},
    {"code": "fundamental_debt_to_equity",     "name": "Debt / Equity",                "category": "Fundamental",  "type": "num", "scale": "ratio",       "description": "Total Debt / Shareholders Equity (latest quarter)"},
    {"code": "fundamental_revenue_growth_yoy", "name": "Revenue Growth YoY",           "category": "Fundamental",  "type": "num", "scale": "ratio",       "description": "Revenue growth Q vs Q-4"},
    {"code": "fundamental_eps_growth_yoy",     "name": "EPS Growth YoY",               "category": "Fundamental",  "type": "num", "scale": "ratio",       "description": "Net income growth Q vs Q-4"},
    {"code": "fundamental_pe_growth_yoy",      "name": "P/E Change YoY",               "category": "Fundamental",  "type": "num", "scale": "ratio",       "description": "Change in TTM P/E vs 1 year ago"},
    {"code": "fundamental_roic",               "name": "ROIC",                         "category": "Fundamental",  "type": "num", "scale": "ratio",       "description": "Return on Invested Capital (TTM)"},
]


def ensure_builtin_data() -> None:
    from app.database import get_session
    from app.models import PriceSource
    from app.models.indicator_definition import IndicatorDefinition

    s = get_session()

    for src in _BUILTIN_SOURCES:
        exists = s.query(PriceSource).filter(PriceSource.name == src["name"]).first()
        if not exists:
            s.add(PriceSource(name=src["name"], description=src["description"]))
            logger.info("Creada fuente de precio integrada: %s", src["name"])

    for ind in _BUILTIN_INDICATORS:
        exists = s.query(IndicatorDefinition).filter(
            IndicatorDefinition.code == ind["code"]
        ).first()
        if not exists:
            s.add(IndicatorDefinition(**ind))
            logger.info("Creado indicador integrado: %s", ind["code"])
        else:
            # Actualizar metadatos si cambiaron
            for field in ("name", "category", "scale", "type", "description", "keep_history", "full_sample"):
                default = True if field == "keep_history" else False if field == "full_sample" else None
                val = ind.get(field, default)
                if getattr(exists, field) != val:
                    setattr(exists, field, val)

    s.commit()
