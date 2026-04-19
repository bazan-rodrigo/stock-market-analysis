"""
Servicio de niveles de soporte y resistencia.
- Pivot S/R: extremos locales clusterizados por precio.
- Volume Profile (VPVR): nodos de alto volumen (HVN) y punto de control (POC).
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
            vpvr_buckets=100,
            hvn_factor=1.0,
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


def _compute_vpvr(df: pd.DataFrame, buckets: int, hvn_factor: float) -> dict:
    """Computes volume profile. Returns {poc_price, hvn_above, hvn_below, all_buckets}."""
    highs = df["high"].values
    lows = df["low"].values
    volumes = df["volume"].fillna(0).values

    price_min = float(lows.min())
    price_max = float(highs.max())
    if price_max <= price_min:
        return {"poc_price": None, "hvn_above": [], "hvn_below": [], "all_buckets": []}

    bucket_size = (price_max - price_min) / buckets
    vol_by_bucket = np.zeros(buckets)

    for i in range(len(df)):
        if volumes[i] <= 0:
            continue
        b_lo = int((lows[i] - price_min) / bucket_size)
        b_hi = int((highs[i] - price_min) / bucket_size)
        b_lo = max(0, min(b_lo, buckets - 1))
        b_hi = max(0, min(b_hi, buckets - 1))
        span = b_hi - b_lo + 1
        per_bucket = float(volumes[i]) / span
        for b in range(b_lo, b_hi + 1):
            vol_by_bucket[b] += per_bucket

    poc_idx = int(np.argmax(vol_by_bucket))
    threshold = float(vol_by_bucket.mean()) * hvn_factor
    last_close = float(df["close"].iloc[-1])
    poc_price = round(price_min + (poc_idx + 0.5) * bucket_size, 4)

    all_buckets = []
    for b in range(buckets):
        price_mid = round(price_min + (b + 0.5) * bucket_size, 4)
        is_hvn = bool(vol_by_bucket[b] >= threshold and vol_by_bucket[b] > 0)
        all_buckets.append({
            "price_mid": price_mid,
            "volume": float(vol_by_bucket[b]),
            "is_hvn": is_hvn,
            "is_poc": b == poc_idx,
        })

    hvn_above = [b for b in all_buckets if b["is_hvn"] and b["price_mid"] > last_close]
    hvn_below = [b for b in all_buckets if b["is_hvn"] and b["price_mid"] < last_close]

    return {
        "poc_price": poc_price,
        "hvn_above": hvn_above,
        "hvn_below": hvn_below,
        "all_buckets": all_buckets,
    }


def compute_sr_for_asset(asset_id: int) -> dict | None:
    """
    Calcula niveles de S/R (pivots y VPVR) para un activo.
    Retorna dict con datos completos para el gráfico y los % para el screener.
    """
    s = get_session()
    rows = (
        s.query(Price)
        .filter(Price.asset_id == asset_id)
        .order_by(Price.date.asc())
        .all()
    )
    if not rows:
        return None

    cfg = _get_sr_config()
    df = pd.DataFrame([{
        "date": r.date,
        "close": float(r.close) if r.close else None,
        "high": float(r.high) if r.high else None,
        "low": float(r.low) if r.low else None,
        "volume": int(r.volume or 0),
    } for r in rows]).dropna(subset=["close", "high", "low"])

    df = df.tail(cfg.lookback_days).reset_index(drop=True)

    if len(df) < cfg.pivot_window * 2 + 2:
        return None

    last_close = float(df["close"].iloc[-1])

    # ── Pivots ────────────────────────────────────────────────────────────────
    resist_levels, support_levels = _compute_pivots(
        df, cfg.pivot_window, cfg.cluster_pct, cfg.min_touches
    )
    resist_above = [r for r in resist_levels if r["price"] > last_close]
    support_below = [r for r in support_levels if r["price"] < last_close]

    nearest_resist = min(resist_above, key=lambda x: x["price"]) if resist_above else None
    nearest_support = max(support_below, key=lambda x: x["price"]) if support_below else None

    pivot_resist_pct = (
        round((nearest_resist["price"] - last_close) / last_close * 100, 2)
        if nearest_resist else None
    )
    pivot_support_pct = (
        round((nearest_support["price"] - last_close) / last_close * 100, 2)
        if nearest_support else None
    )

    # ── VPVR ──────────────────────────────────────────────────────────────────
    vpvr = _compute_vpvr(df, cfg.vpvr_buckets, cfg.hvn_factor)

    vpvr_resist_pct = None
    vpvr_support_pct = None
    if vpvr["hvn_above"]:
        nearest_hvn_above = min(vpvr["hvn_above"], key=lambda x: x["price_mid"])
        vpvr_resist_pct = round(
            (nearest_hvn_above["price_mid"] - last_close) / last_close * 100, 2
        )
    if vpvr["hvn_below"]:
        nearest_hvn_below = max(vpvr["hvn_below"], key=lambda x: x["price_mid"])
        vpvr_support_pct = round(
            (nearest_hvn_below["price_mid"] - last_close) / last_close * 100, 2
        )

    return {
        # Para snapshot del screener
        "pivot_resist_pct": pivot_resist_pct,
        "pivot_support_pct": pivot_support_pct,
        "vpvr_resist_pct": vpvr_resist_pct,
        "vpvr_support_pct": vpvr_support_pct,
        # Para el gráfico
        "sr_pivots": {
            "resist": resist_levels,
            "support": support_levels,
            "nearest_resist_pct": pivot_resist_pct,
            "nearest_support_pct": pivot_support_pct,
        },
        "sr_vpvr": {
            "poc_price": vpvr["poc_price"],
            "hvn_above": vpvr["hvn_above"],
            "hvn_below": vpvr["hvn_below"],
            "all_buckets": vpvr["all_buckets"],
            "nearest_resist_pct": vpvr_resist_pct,
            "nearest_support_pct": vpvr_support_pct,
        },
    }
