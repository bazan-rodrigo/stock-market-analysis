"""
Servicio de screener.
Calcula métricas técnicas por activo y las persiste en screener_snapshot.
El screener consulta exclusivamente esa tabla (sin tocar la API externa).
"""
import logging
from datetime import date, datetime

import numpy as np
import pandas as pd

from app.database import get_session
from app.models import Asset, Price, ScreenerSnapshot

logger = logging.getLogger(__name__)

# Mínimo de filas de precios para calcular métricas
_MIN_ROWS = 20

_MA_PERIODS = [10, 20, 50, 100, 200]


def _find_best_ma(close: pd.Series, high: pd.Series, low: pd.Series, kind: str = "sma") -> int | None:
    """
    Devuelve el período de SMA/EMA que el precio respeta más.
    Un 'respeto' es cuando la vela toca la MA (rango incluye el valor) y el cierre
    permanece del mismo lado que el cierre anterior (rebote, no cruce limpio).
    """
    best_period = None
    best_score  = -1

    for period in _MA_PERIODS:
        if len(close) < period * 2:
            continue

        if kind == "sma":
            ma = close.rolling(period).mean()
        else:
            ma = close.ewm(span=period, adjust=False).mean()

        score = 0
        for i in range(period, len(close) - 1):
            ma_val = ma.iloc[i]
            if pd.isna(ma_val):
                continue
            if low.iloc[i] <= ma_val <= high.iloc[i]:
                prev_c = close.iloc[i - 1]
                curr_c = close.iloc[i]
                if (prev_c >= ma_val and curr_c >= ma_val) or (prev_c <= ma_val and curr_c <= ma_val):
                    score += 1

        if score > best_score:
            best_score  = score
            best_period = period

    return best_period


def _resample_ohlc(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Resamplea OHLC a frecuencia semanal ('W') o mensual ('M')."""
    tmp = df.copy()
    tmp["date"] = pd.to_datetime(tmp["date"])
    tmp = tmp.set_index("date")
    rule = "W" if freq == "W" else "ME"
    resampled = tmp.resample(rule).agg({"close": "last", "high": "max", "low": "min"}).dropna()
    return resampled.reset_index(drop=True)


def _pct_change(current: float, reference: float) -> float | None:
    if reference and reference != 0:
        return round((current - reference) / reference * 100, 2)
    return None


def _closest_price_on_or_before(df: pd.DataFrame, target: date) -> float | None:
    """Precio de cierre en o antes de target."""
    subset = df[df["date"] <= target]
    if subset.empty:
        return None
    return float(subset.iloc[-1]["close"])


def compute_and_save_snapshot(asset_id: int) -> None:
    s = get_session()
    # Cargar TODOS los precios para drawdown histórico correcto
    rows = (
        s.query(Price)
        .filter(Price.asset_id == asset_id)
        .order_by(Price.date.asc())
        .all()
    )

    if len(rows) < _MIN_ROWS:
        return

    df = pd.DataFrame(
        [{"date": r.date, "close": r.close, "high": r.high, "low": r.low} for r in rows]
    ).reset_index(drop=True)

    # --- Drawdown desde el máximo histórico (usa TODOS los datos) ---
    running_max = df["close"].cummax()
    dd_series = (df["close"] - running_max) / running_max * 100
    dd_current = float(dd_series.iloc[-1])
    dd_sorted = dd_series.nsmallest(3).values
    dd_max1 = float(dd_sorted[0]) if len(dd_sorted) > 0 else None
    dd_max2 = float(dd_sorted[1]) if len(dd_sorted) > 1 else None
    dd_max3 = float(dd_sorted[2]) if len(dd_sorted) > 2 else None

    # --- MA más respetada por timeframe (usa TODOS los datos) ---
    best_sma_d = _find_best_ma(df["close"], df["high"], df["low"], "sma")
    best_ema_d = _find_best_ma(df["close"], df["high"], df["low"], "ema")
    df_w = _resample_ohlc(df, "W")
    best_sma_w = _find_best_ma(df_w["close"], df_w["high"], df_w["low"], "sma")
    best_ema_w = _find_best_ma(df_w["close"], df_w["high"], df_w["low"], "ema")
    df_m = _resample_ohlc(df, "M")
    best_sma_m = _find_best_ma(df_m["close"], df_m["high"], df_m["low"], "sma")
    best_ema_m = _find_best_ma(df_m["close"], df_m["high"], df_m["low"], "ema")

    # Para el resto de métricas usar solo los últimos 260 días
    df = df.tail(260).reset_index(drop=True)

    today = df.iloc[-1]["date"]
    last_close = float(df.iloc[-1]["close"])

    # --- Variaciones ---
    prev_close = float(df.iloc[-2]["close"]) if len(df) >= 2 else None

    month_start = date(today.year, today.month, 1)
    q_month = {1: 1, 2: 1, 3: 1, 4: 4, 5: 4, 6: 4, 7: 7, 8: 7, 9: 7, 10: 10, 11: 10, 12: 10}
    quarter_start = date(today.year, q_month[today.month], 1)
    year_start = date(today.year, 1, 1)
    w52_start = date(today.year - 1, today.month, today.day)

    ref_month = _closest_price_on_or_before(df, month_start)
    ref_quarter = _closest_price_on_or_before(df, quarter_start)
    ref_year = _closest_price_on_or_before(df, year_start)
    ref_52w = _closest_price_on_or_before(df, w52_start)

    # --- SMAs ---
    close = df["close"]
    sma20_series = close.rolling(20).mean()
    sma50_series = close.rolling(50).mean()
    sma200_series = close.rolling(200).mean()

    sma20 = float(sma20_series.iloc[-1]) if not pd.isna(sma20_series.iloc[-1]) else None
    sma50 = float(sma50_series.iloc[-1]) if not pd.isna(sma50_series.iloc[-1]) else None
    sma200 = float(sma200_series.iloc[-1]) if not pd.isna(sma200_series.iloc[-1]) else None

    # --- RSI (14) ---
    period = 14
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("inf"))
    rsi_series = 100 - (100 / (1 + rs))
    rsi = float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else None

    # --- Guardar / actualizar snapshot ---
    snap = s.query(ScreenerSnapshot).filter(
        ScreenerSnapshot.asset_id == asset_id
    ).first()
    if snap is None:
        snap = ScreenerSnapshot(asset_id=asset_id)
        s.add(snap)

    snap.updated_at = datetime.utcnow()
    snap.last_close = last_close
    snap.var_daily = _pct_change(last_close, prev_close)
    snap.var_month = _pct_change(last_close, ref_month)
    snap.var_quarter = _pct_change(last_close, ref_quarter)
    snap.var_year = _pct_change(last_close, ref_year)
    snap.var_52w = _pct_change(last_close, ref_52w)
    snap.rsi = round(rsi, 2) if rsi is not None else None
    snap.sma20 = round(sma20, 4) if sma20 is not None else None
    snap.sma50 = round(sma50, 4) if sma50 is not None else None
    snap.sma200 = round(sma200, 4) if sma200 is not None else None
    snap.vs_sma20 = _pct_change(last_close, sma20)
    snap.vs_sma50 = _pct_change(last_close, sma50)
    snap.vs_sma200 = _pct_change(last_close, sma200)
    snap.dd_current = round(dd_current, 2)
    snap.dd_max1 = round(dd_max1, 2) if dd_max1 is not None else None
    snap.dd_max2 = round(dd_max2, 2) if dd_max2 is not None else None
    snap.dd_max3 = round(dd_max3, 2) if dd_max3 is not None else None
    snap.best_sma_d = best_sma_d
    snap.best_ema_d = best_ema_d
    snap.best_sma_w = best_sma_w
    snap.best_ema_w = best_ema_w
    snap.best_sma_m = best_sma_m
    snap.best_ema_m = best_ema_m

    s.commit()


def recompute_all_snapshots(progress_cb=None) -> dict:
    s = get_session()
    asset_ids = [r[0] for r in s.query(Asset.id).filter(Asset.active == True).all()]
    total = len(asset_ids)
    errors = []
    for i, aid in enumerate(asset_ids):
        if progress_cb:
            progress_cb(i + 1, total)
        try:
            compute_and_save_snapshot(aid)
        except Exception as exc:
            logger.warning("Error snapshot activo id=%d: %s", aid, exc)
            errors.append(aid)
    return {"total": total, "errors": errors}


def _fmt_dd_top3(d1, d2, d3) -> str:
    parts = [f"{v:.1f}%" for v in [d1, d2, d3] if v is not None]
    return " / ".join(parts) if parts else ""


def get_screener_data(
    country_ids: list[int] | None = None,
    market_ids: list[int] | None = None,
    instrument_type_ids: list[int] | None = None,
    sector_ids: list[int] | None = None,
    industry_ids: list[int] | None = None,
    rsi_min: float | None = None,
    rsi_max: float | None = None,
    above_sma20: bool | None = None,
    above_sma50: bool | None = None,
    above_sma200: bool | None = None,
) -> list[dict]:
    """
    Devuelve datos del screener aplicando los filtros indicados.
    Consulta exclusivamente screener_snapshot (sin tocar precios o APIs).
    """
    s = get_session()
    q = (
        s.query(Asset, ScreenerSnapshot)
        .join(ScreenerSnapshot, Asset.id == ScreenerSnapshot.asset_id)
        .filter(Asset.active == True)
    )

    if country_ids:
        q = q.filter(Asset.country_id.in_(country_ids))
    if market_ids:
        q = q.filter(Asset.market_id.in_(market_ids))
    if instrument_type_ids:
        q = q.filter(Asset.instrument_type_id.in_(instrument_type_ids))
    if sector_ids:
        q = q.filter(Asset.sector_id.in_(sector_ids))
    if industry_ids:
        q = q.filter(Asset.industry_id.in_(industry_ids))
    if rsi_min is not None:
        q = q.filter(ScreenerSnapshot.rsi >= rsi_min)
    if rsi_max is not None:
        q = q.filter(ScreenerSnapshot.rsi <= rsi_max)
    if above_sma20 is True:
        q = q.filter(ScreenerSnapshot.vs_sma20 > 0)
    elif above_sma20 is False:
        q = q.filter(ScreenerSnapshot.vs_sma20 < 0)
    if above_sma50 is True:
        q = q.filter(ScreenerSnapshot.vs_sma50 > 0)
    elif above_sma50 is False:
        q = q.filter(ScreenerSnapshot.vs_sma50 < 0)
    if above_sma200 is True:
        q = q.filter(ScreenerSnapshot.vs_sma200 > 0)
    elif above_sma200 is False:
        q = q.filter(ScreenerSnapshot.vs_sma200 < 0)

    rows = q.all()
    result = []
    for asset, snap in rows:
        result.append(
            {
                "id": asset.id,
                "ticker": asset.ticker,
                "name": asset.name,
                "last_close": snap.last_close,
                "var_daily": snap.var_daily,
                "var_month": snap.var_month,
                "var_quarter": snap.var_quarter,
                "var_year": snap.var_year,
                "var_52w": snap.var_52w,
                "rsi": snap.rsi,
                "vs_sma20": snap.vs_sma20,
                "vs_sma50": snap.vs_sma50,
                "vs_sma200": snap.vs_sma200,
                "dd_current": snap.dd_current,
                "dd_top3": _fmt_dd_top3(snap.dd_max1, snap.dd_max2, snap.dd_max3),
            }
        )
    return result
