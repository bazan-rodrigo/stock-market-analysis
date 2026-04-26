import logging

import numpy as np
import pandas as pd

from app.database import get_session
from app.models import Asset, Price

logger = logging.getLogger(__name__)

_EMA_PERIOD  = 10   # semanas para suavizar RS
_NORM_WINDOW = 52   # semanas para normalización rolling


def _load_weekly(asset_id: int) -> pd.Series:
    s = get_session()
    rows = (
        s.query(Price.date, Price.close)
         .filter(Price.asset_id == asset_id)
         .order_by(Price.date.asc())
         .all()
    )
    if not rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame(rows, columns=["date", "close"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")["close"]
    return df.resample("W").last().dropna()


def _normalize_rolling(s: pd.Series, window: int) -> pd.Series:
    roll_mean = s.rolling(window, min_periods=window).mean()
    roll_std  = s.rolling(window, min_periods=window).std()
    return (s - roll_mean) / roll_std.replace(0, np.nan) * 10 + 100


_MAX_TRAIL = 30   # máximo de semanas que se almacenan en el store


def compute_rrg(
    asset_ids: list[int], benchmark_id: int, tail_weeks: int = 12
) -> tuple[dict, list[dict]]:
    """
    Calcula RS-Ratio y RS-Momentum para cada activo relativo al benchmark.

    Retorna (data, warnings):
      data:     {asset_id: {ticker, name, trail: [{ratio, momentum, date}]}}
      warnings: [{"id": int, "ticker": str, "reason": str}]
    """
    s = get_session()
    all_ids = list(set(list(asset_ids) + [benchmark_id]))
    assets  = {a.id: a for a in s.query(Asset).filter(Asset.id.in_(all_ids)).all()}

    bench_weekly = _load_weekly(benchmark_id)
    if bench_weekly.empty:
        return {}, []

    min_bars = _NORM_WINDOW + tail_weeks + _EMA_PERIOD

    result   = {}
    warnings = []
    for aid in asset_ids:
        if aid == benchmark_id:
            continue
        asset_obj = assets.get(aid)
        ticker    = asset_obj.ticker if asset_obj else f"id={aid}"
        try:
            asset_weekly = _load_weekly(aid)
            if asset_weekly.empty:
                warnings.append({"id": aid, "ticker": ticker, "reason": "sin precios disponibles"})
                continue

            df = pd.DataFrame({"asset": asset_weekly, "bench": bench_weekly}).dropna()
            if len(df) < min_bars:
                warnings.append({
                    "id":     aid,
                    "ticker": ticker,
                    "reason": f"historial insuficiente ({len(df)} sem., mín. {min_bars})",
                })
                logger.debug("RRG: datos insuficientes para id=%d (%d semanas, mín %d)", aid, len(df), min_bars)
                continue

            rs          = df["asset"] / df["bench"]
            rs_ema      = rs.ewm(span=_EMA_PERIOD, adjust=False).mean()
            rs_ratio    = _normalize_rolling(rs_ema, _NORM_WINDOW)
            rs_roc      = rs_ratio.pct_change(1) * 100
            rs_momentum = _normalize_rolling(rs_roc, _NORM_WINDOW)

            combined = pd.DataFrame({"ratio": rs_ratio, "momentum": rs_momentum}).dropna()
            if len(combined) < tail_weeks:
                warnings.append({
                    "id":     aid,
                    "ticker": ticker,
                    "reason": "datos normalizados insuficientes tras el cálculo",
                })
                continue

            trail = combined.tail(tail_weeks)

            result[aid] = {
                "ticker": ticker,
                "name":   asset_obj.name if asset_obj else ticker,
                "trail": [
                    {
                        "ratio":    round(float(row["ratio"]),    3),
                        "momentum": round(float(row["momentum"]), 3),
                        "date":     str(idx.date()),
                    }
                    for idx, row in trail.iterrows()
                ],
            }
        except Exception as exc:
            warnings.append({"id": aid, "ticker": ticker, "reason": f"error inesperado — {exc}"})
            logger.warning("RRG: error activo id=%d: %s", aid, exc)

    return result, warnings


def get_all_assets_options() -> list[dict]:
    s = get_session()
    assets = s.query(Asset).order_by(Asset.ticker).all()
    return [{"label": f"{a.ticker} — {a.name}", "value": a.id} for a in assets]


def get_assets_for_benchmark(benchmark_id: int) -> list[int]:
    """
    Retorna IDs de activos activos cuyo benchmark_id coincide con el dado,
    o cuyo mercado tiene ese benchmark, excluyendo el propio benchmark.
    """
    from app.models import Market
    from sqlalchemy import or_

    s = get_session()
    markets_with_bm = [
        m.id for m in s.query(Market).filter(Market.benchmark_id == benchmark_id).all()
    ]
    filters = [Asset.benchmark_id == benchmark_id]
    if markets_with_bm:
        filters.append(Asset.market_id.in_(markets_with_bm))

    assets = (
        s.query(Asset.id)
         .filter(Asset.id != benchmark_id, or_(*filters))
         .order_by(Asset.ticker)
         .all()
    )
    return [a.id for a in assets]
