"""
Servicio de niveles de soporte y resistencia.
Detecta extremos locales de precio, clusteriza niveles cercanos en zonas S/R.
"""
import logging

import numpy as np
import pandas as pd

from app.database import get_session
from app.models import Price, SRConfig

logger = logging.getLogger(__name__)


def _get_sr_config() -> SRConfig:
    s = get_session()
    cfg = s.query(SRConfig).filter(SRConfig.id == 1).first()
    if cfg is None:
        cfg = SRConfig(
            id=1,
            lookback_days=252,
            pivot_window=5,
            cluster_pct=0.5,
            min_touches=2,
        )
        s.add(cfg)
        s.commit()
    return cfg


def _cluster_levels(candidates: list[float], cluster_pct: float, min_touches: int) -> list[dict]:
    if not candidates:
        return []
    sorted_c = sorted(candidates)
    groups: list[list[float]] = [[sorted_c[0]]]
    for price in sorted_c[1:]:
        ref = groups[-1][0]
        if ref > 0 and (price - ref) / ref * 100 <= cluster_pct:
            groups[-1].append(price)
        else:
            groups.append([price])
    result = []
    for g in groups:
        if len(g) >= min_touches:
            result.append({"price": round(float(np.mean(g)), 4), "touches": len(g)})
    return result


def _compute_pivots(df: pd.DataFrame, window: int, cluster_pct: float, min_touches: int):
    """Returns (resist_levels, support_levels) each a list of {price, touches}."""
    highs = df["high"].values
    lows = df["low"].values
    n = len(df)
    resist_cands = []
    support_cands = []
    for i in range(window, n - window):
        if highs[i] == highs[i - window: i + window + 1].max():
            resist_cands.append(float(highs[i]))
        if lows[i] == lows[i - window: i + window + 1].min():
            support_cands.append(float(lows[i]))
    return (
        _cluster_levels(resist_cands, cluster_pct, min_touches),
        _cluster_levels(support_cands, cluster_pct, min_touches),
    )


def compute_sr_from_df(df: pd.DataFrame, cfg=None) -> dict | None:
    """
    Calcula S/R desde un DataFrame ya cargado (evita query redundante a DB).
    df debe tener columnas: date, close, high, low.
    """
    if cfg is None:
        cfg = _get_sr_config()

    df = df[["date", "close", "high", "low"]].copy()
    df = df.dropna(subset=["close", "high", "low"])
    df["close"] = df["close"].astype(float)
    df["high"]  = df["high"].astype(float)
    df["low"]   = df["low"].astype(float)
    df = df.tail(cfg.lookback_days).reset_index(drop=True)

    if len(df) < cfg.pivot_window * 2 + 2:
        return None

    last_close = float(df["close"].iloc[-1])
    resist_levels, support_levels = _compute_pivots(
        df, cfg.pivot_window, cfg.cluster_pct, cfg.min_touches
    )
    resist_above  = [r for r in resist_levels  if r["price"] > last_close]
    support_below = [r for r in support_levels if r["price"] < last_close]

    nearest_resist  = min(resist_above,  key=lambda x: x["price"]) if resist_above  else None
    nearest_support = max(support_below, key=lambda x: x["price"]) if support_below else None

    pivot_resist_pct = (
        round((nearest_resist["price"] - last_close) / last_close * 100, 2)
        if nearest_resist else None
    )
    pivot_support_pct = (
        round((nearest_support["price"] - last_close) / last_close * 100, 2)
        if nearest_support else None
    )

    return {
        "pivot_resist_pct": pivot_resist_pct,
        "pivot_support_pct": pivot_support_pct,
        "sr_pivots": {
            "resist": resist_levels,
            "support": support_levels,
            "nearest_resist_pct": pivot_resist_pct,
            "nearest_support_pct": pivot_support_pct,
        },
    }


def compute_sr_for_asset(asset_id: int) -> dict | None:
    """
    Calcula niveles de S/R para un activo cargando precios desde DB.
    Retorna dict con datos completos para el gráfico y los % para el screener.
    """
    s = get_session()
    rows = (
        s.query(Price.date, Price.close, Price.high, Price.low)
        .filter(Price.asset_id == asset_id)
        .order_by(Price.date.asc())
        .all()
    )
    if not rows:
        return None

    df = pd.DataFrame(rows, columns=["date", "close", "high", "low"])
    return compute_sr_from_df(df)
