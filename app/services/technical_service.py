"""
Servicio de screener.
Calcula métricas técnicas por activo y las persiste en las tablas ind_{code}
(serie temporal por indicador) y current_indicator_values (valores vigentes).
"""
import bisect
import logging
import math
from concurrent.futures import ThreadPoolExecutor as _TPE, as_completed
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import insert as _mysql_insert

from app.database import engine, get_session
from app.models import Asset, DrawdownConfig, Price, RegimeConfig, VolatilityConfig
from app.models.indicator_definition import IndicatorDefinition
from app.models.indicator_store import CurrentIndicatorValue, get_ind_table

from app.services import sr_service

logger = logging.getLogger(__name__)

# Mínimo de filas de precios para calcular métricas
_MIN_ROWS = 20

# Barras cargadas en modo quick (~4 años)
_QUICK_DAYS = 1500

_MA_PERIODS = [5, 8, 10, 13, 15, 21, 25, 30, 34, 50, 55, 89, 100, 144, 200, 233]

_Q_MONTH = {1:1, 2:1, 3:1, 4:4, 5:4, 6:4, 7:7, 8:7, 9:7, 10:10, 11:10, 12:10}


# ── Helpers de cálculo ────────────────────────────────────────────────────────

def _find_best_ma(close: pd.Series, high: pd.Series, low: pd.Series, kind: str = "sma") -> int | None:
    best_period = None
    best_score  = -1.0
    prev_c = close.shift(1)
    for period in _MA_PERIODS:
        if len(close) < period * 2:
            continue
        ma = close.rolling(period).mean() if kind == "sma" \
             else close.ewm(span=period, adjust=False).mean()
        valid         = ma.notna()
        touched       = valid & (low <= ma) & (ma <= high)
        total_touches = int(touched.sum())
        if total_touches < 5:
            continue
        bounce       = ((prev_c >= ma) & (close >= ma)) | ((prev_c <= ma) & (close <= ma))
        bounces_held = int((touched & bounce).sum())
        score = bounces_held / total_touches
        if score > best_score:
            best_score  = score
            best_period = period
    return best_period


def _resample_ohlc(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    tmp = df.copy()
    tmp["date"] = pd.to_datetime(tmp["date"])
    tmp = tmp.set_index("date")
    rule = "W" if freq == "W" else "M"
    agg = {"close": "last", "high": "max", "low": "min"}
    try:
        resampled = tmp.resample(rule).agg(agg)
    except ValueError:
        resampled = tmp.resample("ME").agg(agg)
    resampled = resampled.dropna(subset=["close"])
    resampled.index.name = "date"
    return resampled.reset_index()


def _get_drawdown_config():
    s = get_session()
    cfg = s.query(DrawdownConfig).filter(DrawdownConfig.id == 1).first()
    if cfg is None:
        cfg = DrawdownConfig(id=1, min_depth_pct=20.0)
        s.add(cfg)
        s.commit()
    return cfg


def _compute_dd_events(df: pd.DataFrame, min_depth_pct: float) -> list[dict]:
    close = df["close"].values
    dates = df["date"].values
    events = []
    ath = close[0]
    in_dd = False
    dd_start_i = trough_i = 0
    for i in range(len(close)):
        if close[i] >= ath:
            if in_dd:
                depth = (close[trough_i] - ath) / ath * 100
                if depth <= -min_depth_pct:
                    events.append({
                        "start":  _date_str(dates[dd_start_i]),
                        "trough": _date_str(dates[trough_i]),
                        "end":    _date_str(dates[i]),
                        "depth":  round(depth, 1),
                    })
                in_dd = False
            ath = close[i]
        else:
            if not in_dd:
                in_dd, dd_start_i, trough_i = True, i, i
            elif close[i] < close[trough_i]:
                trough_i = i
    if in_dd:
        depth = (close[trough_i] - ath) / ath * 100
        if depth <= -min_depth_pct:
            events.append({
                "start":  _date_str(dates[dd_start_i]),
                "trough": _date_str(dates[trough_i]),
                "end":    None,
                "depth":  round(depth, 1),
            })
    return events


def _get_regime_config():
    s = get_session()
    cfg = s.query(RegimeConfig).filter(RegimeConfig.id == 1).first()
    if cfg is None:
        cfg = RegimeConfig(
            id=1, ema_period_d=200, ema_period_w=50, ema_period_m=20,
            slope_lookback=20, slope_threshold_pct=0.5, confirm_bars=3,
            nascent_bars=20, strong_slope_multiplier=2.0,
        )
        s.add(cfg)
        s.commit()
    return cfg


def _get_volatility_config():
    s = get_session()
    cfg = s.query(VolatilityConfig).filter(VolatilityConfig.id == 1).first()
    if cfg is None:
        cfg = VolatilityConfig(
            id=1, atr_period=14, pct_low=25.0, pct_high=75.0, pct_extreme=90.0,
            confirm_bars=3, dur_short_pct=33.0, dur_long_pct=67.0,
        )
        s.add(cfg)
        s.commit()
    return cfg


def _date_str(val) -> str:
    return str(val.date()) if hasattr(val, "date") else str(val)


def _one_year_before(d: date) -> date:
    """Fecha equivalente un año atrás (29/2 sin equivalente → día 28)."""
    try:
        return date(d.year - 1, d.month, d.day)
    except ValueError:
        return date(d.year - 1, d.month, 28)


def _regime_detail(regime: str, bars: int, slope_last: float,
                   threshold_pct: float, nascent_bars: int, strong_mult: float) -> str:
    is_nascent = bars < nascent_bars
    is_strong  = abs(slope_last) > threshold_pct * strong_mult
    if regime in ("bullish", "bearish"):
        if is_nascent and is_strong:
            return f"{regime}_nascent_strong"
        if is_nascent:
            return f"{regime}_nascent"
        if is_strong:
            return f"{regime}_strong"
        return regime
    return "lateral_nascent" if is_nascent else "lateral"


def _atr_series(df: pd.DataFrame, period: int) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"]  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def _classify_duration(bars: int, hist: list[int], dur_short_pct: float, dur_long_pct: float) -> str:
    if len(hist) < 3:
        return "media"
    p_short = float(np.percentile(hist, dur_short_pct))
    p_long  = float(np.percentile(hist, dur_long_pct))
    if bars <= p_short: return "corta"
    if bars >= p_long:  return "larga"
    return "media"


def _compute_vol_zones(
    df: pd.DataFrame, atr_period: int, confirm_bars: int,
    pct_low: float, pct_high: float, pct_extreme: float,
    dur_short_pct: float, dur_long_pct: float,
) -> list[dict]:
    min_bars = atr_period * 3
    if len(df) < min_bars:
        return []
    atr   = _atr_series(df, atr_period)
    valid = atr.dropna()
    if valid.empty:
        return []
    th_low     = float(np.nanpercentile(valid, pct_low))
    th_high    = float(np.nanpercentile(valid, pct_high))
    th_extreme = float(np.nanpercentile(valid, pct_extreme))
    atr_vals = atr.values
    raw_codes = np.where(np.isnan(atr_vals), 0,
                np.where(atr_vals >= th_extreme, 4,
                np.where(atr_vals >= th_high,    3,
                np.where(atr_vals <= th_low,     1, 2)))).astype(np.int8)
    n = len(raw_codes)
    confirmed = np.zeros(n, dtype=np.int8)
    current = pending = pending_n = 0
    for i in range(n):
        r = int(raw_codes[i])
        if r == 0:
            confirmed[i] = current
        elif r == current:
            pending = pending_n = 0
            confirmed[i] = current
        elif r == pending:
            pending_n += 1
            if pending_n >= confirm_bars:
                current = r; pending = pending_n = 0
            confirmed[i] = current
        else:
            pending = r; pending_n = 1
            confirmed[i] = current
    _CODE = [None, "baja", "normal", "alta", "extrema"]
    dates_arr = df["date"].values
    valid_sorted = np.sort(valid.values)
    n_valid = len(valid_sorted)
    atr_pct_ranks = np.full(n, np.nan)
    if n_valid > 0:
        valid_mask = ~np.isnan(atr_vals)
        atr_pct_ranks[valid_mask] = (
            np.searchsorted(valid_sorted, atr_vals[valid_mask]) / n_valid * 100
        )
    zones = []
    for i in range(n):
        c = int(confirmed[i])
        if c == 0:
            continue
        vr  = _CODE[c]
        dt  = _date_str(dates_arr[i])
        apr = atr_pct_ranks[i]
        atr_pct_rank = float(apr) if not np.isnan(apr) else None
        if not zones or zones[-1]["vol_regime"] != vr:
            if zones:
                zones[-1]["end"] = _date_str(dates_arr[i - 1])
            zones.append({"start": dt, "end": dt, "vol_regime": vr,
                          "_bars": 1, "atr_pct": round(atr_pct_rank, 1) if atr_pct_rank is not None else None})
        else:
            zones[-1]["_bars"] += 1
            if atr_pct_rank is not None:
                zones[-1]["atr_pct"] = round(atr_pct_rank, 1)
    if not zones:
        return []
    zones[-1]["end"] = _date_str(dates_arr[-1])
    dur_hist: dict[str, list[int]] = {"baja": [], "normal": [], "alta": [], "extrema": []}
    for z in zones[:-1]:
        dur_hist[z["vol_regime"]].append(z["_bars"])
    for z in zones:
        z["dur_regime"] = _classify_duration(
            z["_bars"], dur_hist[z["vol_regime"]], dur_short_pct, dur_long_pct
        )
        z.pop("_bars", None)
    return zones


def _compute_regime_zones(
    df: pd.DataFrame, ema_period: int, slope_lookback: int,
    slope_threshold_pct: float, confirm_bars: int,
    nascent_bars: int = 20, strong_slope_multiplier: float = 2.0,
) -> list[dict]:
    min_bars = ema_period + slope_lookback + confirm_bars
    if len(df) < min_bars:
        return []
    close = df["close"]
    ema   = close.ewm(span=ema_period, adjust=False).mean()
    slope = (ema - ema.shift(slope_lookback)) / ema.shift(slope_lookback) * 100
    s_vals = slope.values
    e_vals = ema.values
    c_vals = close.values
    nan_mask = np.isnan(s_vals) | np.isnan(e_vals)
    raw_codes = np.where(nan_mask, 0,
                np.where((s_vals >  slope_threshold_pct) & (c_vals > e_vals), 2,
                np.where((s_vals < -slope_threshold_pct) & (c_vals < e_vals), 3, 1))).astype(np.int8)
    n = len(raw_codes)
    confirmed = np.zeros(n, dtype=np.int8)
    current = pending = pending_n = 0
    for i in range(n):
        r = int(raw_codes[i])
        if r == 0:
            confirmed[i] = current
        elif r == current:
            pending = pending_n = 0
            confirmed[i] = current
        elif r == pending:
            pending_n += 1
            if pending_n >= confirm_bars:
                current = r; pending = pending_n = 0
            confirmed[i] = current
        else:
            pending = r; pending_n = 1
            confirmed[i] = current
    _CODE = [None, "lateral", "bullish", "bearish"]
    dates_arr = df["date"].values
    zones = []
    for i in range(n):
        c = int(confirmed[i])
        if c == 0:
            continue
        regime = _CODE[c]
        dt     = _date_str(dates_arr[i])
        sl_val = float(s_vals[i]) if not np.isnan(s_vals[i]) else 0.0
        if not zones or zones[-1]["regime"] != regime:
            if zones:
                prev = zones[-1]
                prev["end"] = _date_str(dates_arr[i - 1])
                prev["regime_detail"] = _regime_detail(
                    prev["regime"], prev["_bars"], prev["_slope_last"],
                    slope_threshold_pct, nascent_bars, strong_slope_multiplier,
                )
            zones.append({"start": dt, "end": dt, "regime": regime,
                          "_bars": 1, "_slope_last": sl_val})
        else:
            zones[-1]["_bars"] += 1
            zones[-1]["_slope_last"] = sl_val
    if zones:
        last = zones[-1]
        last["end"] = _date_str(df.iloc[-1]["date"])
        last["regime_detail"] = _regime_detail(
            last["regime"], last["_bars"], last["_slope_last"],
            slope_threshold_pct, nascent_bars, strong_slope_multiplier,
        )
    for z in zones:
        z.pop("_bars", None)
        z.pop("_slope_last", None)
    return zones


def _rsi(close: pd.Series, period: int = 14) -> float | None:
    if len(close) < period + 1:
        return None
    delta    = close.diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs       = avg_gain / avg_loss.replace(0, float("nan"))
    rsi_series = (100 - (100 / (1 + rs))).fillna(100)
    val = rsi_series.iloc[-1]
    return float(val) if not pd.isna(val) else None


def _sma_zscore(close: pd.Series, period: int) -> float | None:
    if len(close) < period + 1:
        return None
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    last_sma = sma.iloc[-1]
    last_std = std.iloc[-1]
    if pd.isna(last_sma) or pd.isna(last_std) or last_std == 0:
        return None
    return round((float(close.iloc[-1]) - float(last_sma)) / float(last_std), 2)


def _pct_change(current: float, reference: float) -> float | None:
    if current is not None and reference is not None and reference != 0:
        return round((current - reference) / reference * 100, 2)
    return None


def _closest_price_on_or_before(df: pd.DataFrame, target: date) -> float | None:
    subset = df[df["date"] <= target]
    if subset.empty:
        return None
    return float(subset.iloc[-1]["close"])


def _rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    delta    = close.diff()
    gain     = delta.clip(lower=0)
    loss     = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs       = avg_gain / avg_loss.replace(0, float("nan"))
    return (100 - (100 / (1 + rs))).round(2)


def _atr_pct_series_v(df: pd.DataFrame, period: int) -> pd.Series:
    atr          = _atr_series(df, period)
    valid_sorted = np.sort(atr.dropna().values)
    n            = len(valid_sorted)
    if n == 0:
        return pd.Series(np.nan, index=df.index)
    atr_vals = atr.values
    pcts = np.where(
        np.isnan(atr_vals),
        np.nan,
        np.searchsorted(valid_sorted, atr_vals) / n * 100,
    )
    return pd.Series(np.round(pcts, 1), index=df.index)


def _return_vs_ref_series(df: pd.DataFrame, ref_date_fn) -> pd.Series:
    dates    = df["date"].values
    closes   = df["close"].values.astype(float)
    ordinals = np.array([d.toordinal() for d in dates])

    ref_ords = np.empty(len(dates), dtype=np.int64)
    for i, d in enumerate(dates):
        try:    ref_ords[i] = ref_date_fn(d).toordinal()
        except ValueError: ref_ords[i] = -1

    indices    = np.searchsorted(ordinals, ref_ords, side="right") - 1
    valid      = (indices >= 0) & (ref_ords >= 0)
    ref_closes = closes[np.where(valid, indices, 0)]
    results    = np.where(
        valid & (ref_closes != 0),
        np.round((closes / ref_closes - 1) * 100, 2),
        np.nan,
    )
    return pd.Series(results, index=df.index)


def _zones_to_series(zones: list[dict], df: pd.DataFrame, value_key: str,
                     df_period: pd.DataFrame | None = None) -> list | pd.Series:
    """Mapea zonas a una serie de valores.

    Sin df_period → lista diaria (comportamiento original).
    Con df_period → pd.Series con índice del período (weekly/monthly).
    """
    target = df_period if df_period is not None else df
    if not zones:
        if df_period is not None:
            return pd.Series(dtype=object)
        return [None] * len(df)
    zone_starts = [z["start"] for z in zones]
    out = []
    for d in target["date"]:
        d_str = _date_str(d)
        idx   = bisect.bisect_right(zone_starts, d_str) - 1
        if idx >= 0 and zones[idx]["end"] >= d_str:
            out.append(zones[idx].get(value_key))
        else:
            out.append(None)
    if df_period is not None:
        return pd.Series(out, index=_period_index(df_period))
    return out


def _to_date(x):
    """Convierte pd.Timestamp o datetime a datetime.date."""
    return x.date() if isinstance(x, pd.Timestamp) else x


def _period_index(df_period: pd.DataFrame) -> list:
    """Retorna lista de datetime.date a partir de un df semanal/mensual."""
    return [_to_date(d) for d in df_period["date"]]


def _fv(x, decimals: int = 2):
    if x is None:
        return None
    try:
        f = float(x)
        return None if math.isnan(f) else round(f, decimals)
    except (TypeError, ValueError):
        return None


# ── Lectura de best_sma desde current_indicator_values ───────────────────────

def _query_best_sma(asset_id: int, session, best_sma_cache: dict | None = None) -> dict[str, int]:
    if best_sma_cache is not None:
        return best_sma_cache.get(asset_id, {})
    rows = session.query(
        CurrentIndicatorValue.code,
        CurrentIndicatorValue.value_num,
    ).filter(
        CurrentIndicatorValue.asset_id == asset_id,
        CurrentIndicatorValue.code.in_(["best_sma_d", "best_sma_w", "best_sma_m"]),
    ).all()
    return {code: int(val) for code, val in rows if val is not None}


def _load_benchmark_cache(s) -> dict:
    """Precarga {asset_id: benchmark_id} para todos los activos con benchmark."""
    rows = s.query(Asset.id, Asset.benchmark_id).filter(Asset.benchmark_id.isnot(None)).all()
    return {aid: bid for aid, bid in rows}


def _load_best_sma_cache(s) -> dict:
    """Precarga best_sma_d/w/m para todos los activos. {asset_id: {code: val}}"""
    rows = s.query(
        CurrentIndicatorValue.asset_id,
        CurrentIndicatorValue.code,
        CurrentIndicatorValue.value_num,
    ).filter(
        CurrentIndicatorValue.code.in_(["best_sma_d", "best_sma_w", "best_sma_m"])
    ).all()
    cache: dict = {}
    for asset_id, code, val in rows:
        if val is not None:
            cache.setdefault(asset_id, {})[code] = int(val)
    return cache


# ── Escritura a tablas ind_* y current_indicator_values ──────────────────────

def _upsert_ind(session, code: str, asset_id: int, target_date, value) -> None:
    """UPSERT de un valor en ind_{code}."""
    if value is None:
        return
    t    = get_ind_table(code)
    stmt = _mysql_insert(t).values(asset_id=asset_id, date=target_date, value=value)
    stmt = stmt.on_duplicate_key_update(value=stmt.inserted.value)
    session.execute(stmt)


def _upsert_current_ind(session, asset_id: int, code: str,
                        value_num=None, value_str=None) -> None:
    """UPSERT de un valor vigente en current_indicator_values."""
    stmt = _mysql_insert(CurrentIndicatorValue.__table__).values(
        asset_id=asset_id, code=code, value_num=value_num, value_str=value_str,
    )
    stmt = stmt.on_duplicate_key_update(value_num=value_num, value_str=value_str)
    session.execute(stmt)


def _batch_upsert_ind(session, code: str, rows: list[dict]) -> None:
    """Inserta o actualiza múltiples filas en ind_{code} de una vez."""
    if not rows:
        return
    t    = get_ind_table(code)
    stmt = _mysql_insert(t)
    stmt = stmt.on_duplicate_key_update(value=stmt.inserted.value)
    session.execute(stmt, rows)


# ── Compute functions para backfill por indicador ────────────────────────────

def _bf_return_daily(df, df_w, df_m, **kw):
    return [_fv(v) for v in df["close"].pct_change() * 100]

def _bf_return_monthly(df, df_w, df_m, **kw):
    return [_fv(v) for v in _return_vs_ref_series(df, lambda d: d.replace(day=1))]

def _bf_return_quarterly(df, df_w, df_m, **kw):
    return [_fv(v) for v in _return_vs_ref_series(
        df, lambda d: date(d.year, _Q_MONTH[d.month], 1))]

def _bf_return_yearly(df, df_w, df_m, **kw):
    return [_fv(v) for v in _return_vs_ref_series(df, lambda d: date(d.year, 1, 1))]

def _bf_return_52w(df, df_w, df_m, **kw):
    return [_fv(v) for v in _return_vs_ref_series(df, _one_year_before)]

def _bf_dist_sma(period):
    def fn(df, df_w, df_m, **kw):
        close = df["close"]
        sma   = close.rolling(period).mean()
        return [_fv(v) for v in ((close - sma) / sma * 100).round(2)]
    return fn

def _bf_rsi_daily(df, df_w, df_m, **kw):
    return [_fv(v) for v in _rsi_series(df["close"])]

def _bf_rsi_weekly(df, df_w, df_m, **kw):
    if len(df_w) >= 15:
        return pd.Series([_fv(v) for v in _rsi_series(df_w["close"])],
                         index=_period_index(df_w))
    return pd.Series(dtype=float)

def _bf_rsi_monthly(df, df_w, df_m, **kw):
    if len(df_m) >= 15:
        return pd.Series([_fv(v) for v in _rsi_series(df_m["close"])],
                         index=_period_index(df_m))
    return pd.Series(dtype=float)

def _bf_atr_daily(df, df_w, df_m, vol_cfg, **kw):
    return [_fv(v, 1) for v in _atr_pct_series_v(df, vol_cfg.atr_period)]

def _bf_atr_weekly(df, df_w, df_m, vol_cfg, **kw):
    if len(df_w) >= vol_cfg.atr_period * 3:
        return pd.Series([_fv(v, 1) for v in _atr_pct_series_v(df_w, vol_cfg.atr_period)],
                         index=_period_index(df_w))
    return pd.Series(dtype=float)

def _bf_atr_monthly(df, df_w, df_m, vol_cfg, **kw):
    if len(df_m) >= vol_cfg.atr_period * 3:
        return pd.Series([_fv(v, 1) for v in _atr_pct_series_v(df_m, vol_cfg.atr_period)],
                         index=_period_index(df_m))
    return pd.Series(dtype=float)

def _bf_trend(tf_key):
    def fn(df, df_w, df_m, regime_cfg, **kw):
        df_tf     = {"d": df, "w": df_w, "m": df_m}[tf_key]
        period    = {"d": regime_cfg.ema_period_d, "w": regime_cfg.ema_period_w,
                     "m": regime_cfg.ema_period_m}[tf_key]
        sl, st, cb = regime_cfg.slope_lookback, regime_cfg.slope_threshold_pct, regime_cfg.confirm_bars
        nb, sm    = regime_cfg.nascent_bars, regime_cfg.strong_slope_multiplier
        zones     = _compute_regime_zones(df_tf, period, sl, st, cb, nb, sm)
        return _zones_to_series(zones, df, "regime_detail",
                                df_period=None if tf_key == "d" else df_tf)
    return fn

def _bf_volatility(tf_key):
    def fn(df, df_w, df_m, vol_cfg, **kw):
        df_tf    = {"d": df, "w": df_w, "m": df_m}[tf_key]
        vol_args = dict(
            atr_period=vol_cfg.atr_period, confirm_bars=vol_cfg.confirm_bars,
            pct_low=vol_cfg.pct_low, pct_high=vol_cfg.pct_high, pct_extreme=vol_cfg.pct_extreme,
            dur_short_pct=vol_cfg.dur_short_pct, dur_long_pct=vol_cfg.dur_long_pct,
        )
        vz       = _compute_vol_zones(df_tf, **vol_args)
        combined = [{**z, "_vk": f"{z['vol_regime']}_{z['dur_regime']}"} for z in vz]
        return _zones_to_series(combined, df, "_vk",
                                df_period=None if tf_key == "d" else df_tf)
    return fn

def _bf_dist_optimal_sma(tf_key):
    code_map = {"d": "best_sma_d", "w": "best_sma_w", "m": "best_sma_m"}
    def fn(df, df_w, df_m, session, asset_id, best_sma_cache=None, **kw):
        df_tf    = {"d": df, "w": df_w, "m": df_m}[tf_key]
        best     = _query_best_sma(asset_id, session, best_sma_cache)
        best_val = best.get(code_map[tf_key])
        if best_val and best_val >= 2:
            cl   = df_tf["close"]
            sma  = cl.rolling(best_val).mean()
            std  = cl.rolling(best_val).std().replace(0, np.nan)
            dist = ((cl - sma) / std).round(2)
            if tf_key == "d":
                return [_fv(v) for v in dist]
            return pd.Series([_fv(v) for v in dist], index=_period_index(df_tf))
        if tf_key != "d":
            return pd.Series(dtype=float)
        return [None] * len(df)
    return fn

def _bf_relative_strength_52w(df, df_w, df_m, session, asset_id, price_cache=None, **kw):
    n   = len(df)
    bm_id = session.query(Asset.benchmark_id).filter(Asset.id == asset_id).scalar()
    if not bm_id:
        return [None] * n
    if price_cache and bm_id in price_cache:
        bm_df = price_cache[bm_id]
    else:
        bm_rows = session.query(Price.date, Price.close).filter(
            Price.asset_id == bm_id
        ).order_by(Price.date.asc()).all()
        if not bm_rows:
            return [None] * n
        bm_df = pd.DataFrame(bm_rows, columns=["date", "close"])

    bm_ords   = np.array([d.toordinal() for d in bm_df["date"]])
    bm_closes = bm_df["close"].values.astype(float)
    a_ords    = np.array([d.toordinal() for d in df["date"]])
    a_cls     = df["close"].values.astype(float)

    # Ordinal de referencia (52 semanas atrás) para cada fecha
    ref_ords = np.empty(n, dtype=np.int64)
    for i, d in enumerate(df["date"]):
        ref_ords[i] = _one_year_before(d).toordinal()

    def _vlkup(ords, closes, targets):
        idx = np.searchsorted(ords, targets, side="right") - 1
        valid = idx >= 0
        return np.where(valid, closes[np.where(valid, idx, 0)], np.nan)

    bm_now = _vlkup(bm_ords, bm_closes, a_ords)   # precio benchmark en fecha i
    bm_ref = _vlkup(bm_ords, bm_closes, ref_ords)  # precio benchmark hace 52w
    a_ref  = _vlkup(a_ords,  a_cls,     ref_ords)  # precio activo hace 52w
    # ref_ords[i] < a_ords[i] siempre, por lo que no se necesita slice

    ok = (~np.isnan(bm_now) & ~np.isnan(bm_ref) & (bm_ref != 0) &
          ~np.isnan(a_ref)  & (a_ref  != 0) & (a_cls != 0))
    ret_a  = np.where(ok, (a_cls    - a_ref)  / a_ref  * 100, np.nan)
    ret_bm = np.where(ok, (bm_now   - bm_ref) / bm_ref * 100, np.nan)
    rs     = np.where(ok, np.round(ret_a - ret_bm, 2), np.nan)
    return [None if np.isnan(v) else float(v) for v in rs]


# Mapa código → función de cómputo para backfill
_BACKFILL_FNS: dict[str, callable] = {
    "return_daily":             _bf_return_daily,
    "return_monthly":           _bf_return_monthly,
    "return_quarterly":         _bf_return_quarterly,
    "return_yearly":            _bf_return_yearly,
    "return_52w":               _bf_return_52w,
    "dist_sma20":               _bf_dist_sma(20),
    "dist_sma50":               _bf_dist_sma(50),
    "dist_sma200":              _bf_dist_sma(200),
    "rsi_daily":                _bf_rsi_daily,
    "rsi_weekly":               _bf_rsi_weekly,
    "rsi_monthly":              _bf_rsi_monthly,
    "atr_percentile_daily":     _bf_atr_daily,
    "atr_percentile_weekly":    _bf_atr_weekly,
    "atr_percentile_monthly":   _bf_atr_monthly,
    "trend_daily":              _bf_trend("d"),
    "trend_weekly":             _bf_trend("w"),
    "trend_monthly":            _bf_trend("m"),
    "volatility_daily":         _bf_volatility("d"),
    "volatility_weekly":        _bf_volatility("w"),
    "volatility_monthly":       _bf_volatility("m"),
    "dist_optimal_sma_daily":   _bf_dist_optimal_sma("d"),
    "dist_optimal_sma_weekly":  _bf_dist_optimal_sma("w"),
    "dist_optimal_sma_monthly": _bf_dist_optimal_sma("m"),
    "relative_strength_52w":    _bf_relative_strength_52w,
    # drawdown_max2/max3, resistance_pct, support_pct son keep_history=False
    # (ver _CURRENT_ONLY_CODES) — pendiente evaluar si se implementa backfill.
}


# ── Backfill por indicador ────────────────────────────────────────────────────

def _load_all_prices(_s) -> dict:
    """Carga todos los precios en memoria via pd.read_sql. {asset_id: df}."""
    from sqlalchemy import text as _text
    with engine.connect() as conn:
        df = pd.read_sql(
            _text("SELECT asset_id, date, close, high, low FROM prices"
                  " ORDER BY asset_id, date"),
            conn,
        )
    return {aid: sub.reset_index(drop=True) for aid, sub in df.groupby("asset_id")}


_RECENT_LOOKBACK_DAYS = 1500  # ~6 años; suficiente para RSI, ATR, zonas, RS52w


def _load_recent_prices(s) -> tuple[dict, dict, dict]:
    """Carga precios para valores vigentes.

    Retorna (price_cache, ath_cache, close_cache) donde:
    - price_cache:  {asset_id: df} con close/high/low de los últimos 1500 días
    - ath_cache:    {asset_id: float} con el máximo histórico de close
    - close_cache:  {asset_id: np.ndarray} con cierre completo histórico (para drawdowns)
    """
    from sqlalchemy import text as _text

    cutoff = (date.today() - timedelta(days=_RECENT_LOOKBACK_DAYS)).isoformat()

    with engine.connect() as conn:
        # ATH histórico
        ath_rows = conn.execute(
            _text("SELECT asset_id, MAX(close) FROM prices"
                  " WHERE close IS NOT NULL GROUP BY asset_id")
        ).fetchall()
        ath_cache = {aid: float(ath) for aid, ath in ath_rows if ath is not None}

        # Precios recientes
        price_rows = conn.execute(
            _text(f"SELECT asset_id, date, close, high, low FROM prices"
                  f" WHERE date >= '{cutoff}' ORDER BY asset_id, date")
        ).fetchall()

        # Cierre completo histórico para drawdowns (2 columnas, mysqlclient lo hace rápido)
        close_rows = conn.execute(
            _text("SELECT asset_id, close FROM prices"
                  " WHERE close IS NOT NULL ORDER BY asset_id, date")
        ).fetchall()

    df = pd.DataFrame(price_rows, columns=["asset_id", "date", "close", "high", "low"])
    price_cache = {int(aid): sub.reset_index(drop=True) for aid, sub in df.groupby("asset_id")}

    df_c = pd.DataFrame(close_rows, columns=["asset_id", "close"])
    close_cache = {
        int(aid): sub["close"].to_numpy(dtype=float)
        for aid, sub in df_c.groupby("asset_id")
    }

    return price_cache, ath_cache, close_cache


# Activos por query al leer fechas existentes durante un backfill delta
_EXISTING_CHUNK = 100


def backfill_indicator(code: str, *, force: bool = False, asset_tick=None,
                       price_cache: dict | None = None,
                       best_sma_cache: dict | None = None,
                       df_w_cache: dict | None = None,
                       df_m_cache: dict | None = None) -> dict:
    """
    Backfill histórico de un indicador específico para todos los activos.
    Escribe en la tabla ind_{code}.

    Si el indicador tiene full_sample=True en indicator_definitions (usa
    estadísticos sobre toda la serie, como percentiles de ATR), se fuerza
    mode force independientemente del argumento recibido.

    df_w_cache / df_m_cache permiten reutilizar resamples precalculados entre
    los workers (sin ellos, cada indicador resamplearía los mismos precios).
    """
    compute_fn = _BACKFILL_FNS.get(code)
    if compute_fn is None:
        return {"inserted": 0, "skipped": True, "reason": "no_compute_fn"}

    s = get_session()

    # Si el indicador usa estadísticos full-sample, forzar recálculo completo
    # independientemente de lo que pida el caller (lógica en indicator_definitions)
    defn = s.query(IndicatorDefinition).filter(IndicatorDefinition.code == code).first()
    if defn and defn.full_sample:
        force = True

    t          = get_ind_table(code)
    regime_cfg = _get_regime_config()
    vol_cfg    = _get_volatility_config()
    asset_ids  = [r[0] for r in s.query(Asset.id).all()]

    inserted = 0
    _BATCH = 500

    for chunk_start in range(0, len(asset_ids), _EXISTING_CHUNK):
        chunk = asset_ids[chunk_start:chunk_start + _EXISTING_CHUNK]

        # Fechas existentes de todo el chunk en una sola query (evita 1 por activo)
        existing_by_asset: dict[int, set] = {}
        if not force:
            for aid, d in s.execute(
                sa.select(t.c.asset_id, t.c.date).where(t.c.asset_id.in_(chunk))
            ).fetchall():
                existing_by_asset.setdefault(aid, set()).add(d)

        for asset_id in chunk:
            if price_cache is not None:
                df = price_cache.get(asset_id)
                if df is None or len(df) < _MIN_ROWS:
                    if asset_tick:
                        asset_tick()
                    continue
            else:
                rows = s.query(Price.date, Price.close, Price.high, Price.low).filter(
                    Price.asset_id == asset_id
                ).order_by(Price.date.asc()).all()
                if len(rows) < _MIN_ROWS:
                    if asset_tick:
                        asset_tick()
                    continue
                df = pd.DataFrame(rows, columns=["date", "close", "high", "low"])

            df_w = df_w_cache.get(asset_id) if df_w_cache is not None else None
            if df_w is None:
                df_w = _resample_ohlc(df, "W")
            df_m = df_m_cache.get(asset_id) if df_m_cache is not None else None
            if df_m is None:
                df_m = _resample_ohlc(df, "M")

            values = compute_fn(
                df=df, df_w=df_w, df_m=df_m,
                regime_cfg=regime_cfg, vol_cfg=vol_cfg,
                session=s, asset_id=asset_id,
                price_cache=price_cache, best_sma_cache=best_sma_cache,
            )

            # Opt 1: compute_fn puede retornar list (diario) o pd.Series (semanal/mensual)
            if isinstance(values, pd.Series):
                dates_list = values.index.tolist()
                vals_list  = values.tolist()
            else:
                dates_list = df["date"].tolist()
                vals_list  = list(values)

            if force:
                s.execute(t.delete().where(t.c.asset_id == asset_id))
                pairs = [(d, v) for d, v in zip(dates_list, vals_list) if pd.notna(v)]
            else:
                existing = existing_by_asset.get(asset_id, set())
                # La última fecha se recalcula siempre: el último precio es
                # preliminar y puede haber cambiado desde la corrida anterior
                last_d = dates_list[-1] if dates_list else None
                pairs = [(d, v) for d, v in zip(dates_list, vals_list)
                         if pd.notna(v) and (d not in existing or d == last_d)]

            batch = []
            for d, v in pairs:
                batch.append({"asset_id": asset_id, "date": d, "value": v})
                if len(batch) >= _BATCH:
                    _batch_upsert_ind(s, code, batch)
                    s.commit()
                    inserted += len(batch)
                    batch = []

            if batch:
                _batch_upsert_ind(s, code, batch)
                s.commit()
                inserted += len(batch)

            if asset_tick:
                asset_tick()

    return {"inserted": inserted, "code": code}


def _backfill_indicator_worker(code: str, force: bool = False, asset_tick=None,
                               price_cache: dict | None = None,
                               best_sma_cache: dict | None = None,
                               df_w_cache: dict | None = None,
                               df_m_cache: dict | None = None) -> dict:
    from app.database import Session as _DbSession
    try:
        return backfill_indicator(code, force=force, asset_tick=asset_tick,
                                  price_cache=price_cache, best_sma_cache=best_sma_cache,
                                  df_w_cache=df_w_cache, df_m_cache=df_m_cache)
    except Exception as exc:
        logger.warning("Backfill error code=%s: %s", code, exc)
        return {"inserted": 0, "code": code, "error": str(exc)}
    finally:
        _DbSession.remove()


def backfill_all_indicator_values(progress_cb=None, *, force: bool = False,
                                  price_cache: dict | None = None) -> dict:
    """
    Backfill histórico parallelizado por indicador.
    Un worker por indicador (keep_history=True con función de cómputo definida).
    El número de workers se adapta dinámicamente al número de indicadores.
    Progreso reportado por activo procesado (no por indicador) para feedback más fino.
    price_cache permite reutilizar precios ya cargados por el caller.
    """
    import threading as _th
    s    = get_session()
    hist = [
        d.code for d in s.query(IndicatorDefinition).filter(
            IndicatorDefinition.keep_history.is_(True)
        ).order_by(IndicatorDefinition.id).all()
        if d.code in _BACKFILL_FNS
    ]

    n_indicators = len(hist)
    if not n_indicators:
        return {"total": 0, "success": 0, "inserted": 0, "errors": []}

    # Avisa al UI antes de la carga (puede tardar varios segundos)
    if progress_cb:
        progress_cb(0, 1, "Cargando precios en memoria...")

    if price_cache is None:
        logger.info("Pre-cargando precios en memoria...")
        price_cache = _load_all_prices(s)
    best_sma_cache  = _load_best_sma_cache(s)
    n_assets        = len(price_cache)
    total_work      = n_indicators * n_assets
    logger.info("Precios cargados: %d activos", n_assets)

    # Resamples W/M una sola vez, compartidos por todos los workers
    if progress_cb:
        progress_cb(0, 1, "Precalculando resamples semanales y mensuales...")
    df_w_cache = {aid: _resample_ohlc(df, "W") for aid, df in price_cache.items()}
    df_m_cache = {aid: _resample_ohlc(df, "M") for aid, df in price_cache.items()}

    from app.database import Session as _DbSession
    _DbSession.remove()   # libera la conexión principal antes de lanzar workers

    done_ind = 0
    inserted = 0
    errors: list[dict] = []

    # Contador total compartido + contador por indicador (thread-safe)
    _assets_done = 0
    _lock        = _th.Lock()

    def _make_tick(code):
        per_ind = [0]
        def _tick():
            nonlocal _assets_done
            per_ind[0] += 1
            with _lock:
                _assets_done += 1
                n = _assets_done
            if progress_cb:
                progress_cb(n, total_work, f"{code}: {per_ind[0]}/{n_assets}")
        return _tick

    with _TPE(max_workers=n_indicators) as pool:
        futures = {
            pool.submit(_backfill_indicator_worker, code, force, _make_tick(code),
                        price_cache, best_sma_cache, df_w_cache, df_m_cache): code
            for code in hist
        }
        if progress_cb:
            # Mensaje especial para pre-poblar todos los workers en el UI
            progress_cb(0, total_work, f"__init__:{n_assets}:{','.join(hist)}")
        for future in as_completed(futures):
            done_ind += 1
            code      = futures[future]
            try:
                res = future.result()
                inserted += res.get("inserted", 0)
                if "error" in res:
                    errors.append({"code": code, "error": res["error"]})
            except Exception as exc:
                logger.warning("Backfill future error code=%s: %s", code, exc)
                errors.append({"code": code, "error": str(exc)})

    return {"total": n_indicators, "success": n_indicators - len(errors),
            "inserted": inserted, "errors": errors}


# ── Log de actualización de indicadores ────────────────────────────────────────

def _save_indicator_log(asset_id: int, success: bool, error: str | None, session=None) -> None:
    """Registra éxito/error del último recálculo de indicadores de un activo."""
    from app.models import IndicatorUpdateLog
    s = session if session is not None else get_session()
    log = s.query(IndicatorUpdateLog).filter(
        IndicatorUpdateLog.asset_id == asset_id
    ).first()
    if log is None:
        log = IndicatorUpdateLog(asset_id=asset_id, success=success, error_detail=error)
        s.add(log)
    else:
        log.last_attempt_at = datetime.utcnow()
        log.success = success
        log.error_detail = error
    s.commit()


# ── compute_current_indicators ─────────────────────────────────────────────────

def compute_current_indicators(
    asset_id: int,
    *,
    _dd_cfg=None,
    _regime_cfg=None,
    _vol_cfg=None,
    _sr_cfg=None,
    quick: bool = False,
) -> None:
    s = get_session()

    # Leer best_sma previo para reutilizar en modo quick
    _prev_best: dict[str, int] = {}
    if quick:
        _bm_codes = ["best_sma_d", "best_ema_d", "best_sma_w", "best_ema_w", "best_sma_m", "best_ema_m"]
        _bm_rows  = s.query(
            CurrentIndicatorValue.code, CurrentIndicatorValue.value_num,
        ).filter(
            CurrentIndicatorValue.asset_id == asset_id,
            CurrentIndicatorValue.code.in_(_bm_codes),
        ).all()
        _prev_best = {code: int(val) for code, val in _bm_rows if val is not None}

    if quick and not _prev_best.get("best_sma_d"):
        quick = False

    # Carga de precios
    if quick:
        rows = (
            s.query(Price.date, Price.close, Price.high, Price.low)
            .filter(Price.asset_id == asset_id)
            .order_by(Price.date.desc())
            .limit(_QUICK_DAYS)
            .all()
        )
        rows = list(reversed(rows))
    else:
        rows = (
            s.query(Price.date, Price.close, Price.high, Price.low)
            .filter(Price.asset_id == asset_id)
            .order_by(Price.date.asc())
            .all()
        )

    if len(rows) < _MIN_ROWS:
        return

    df = pd.DataFrame(rows, columns=["date", "close", "high", "low"])

    # Drawdown
    if quick:
        from sqlalchemy import func
        ath = s.query(func.max(Price.close)).filter(Price.asset_id == asset_id).scalar()
        dd_current = float((df.iloc[-1]["close"] - ath) / ath * 100) if ath else 0.0
        dd_map = dict(s.query(
            CurrentIndicatorValue.code, CurrentIndicatorValue.value_num,
        ).filter(
            CurrentIndicatorValue.asset_id == asset_id,
            CurrentIndicatorValue.code.in_(
                ["drawdown_max1", "drawdown_max2", "drawdown_max3"]),
        ).all())
        dd_max1 = dd_map.get("drawdown_max1")
        dd_max2 = dd_map.get("drawdown_max2")
        dd_max3 = dd_map.get("drawdown_max3")
        dd_events = []
    else:
        running_max = df["close"].cummax()
        dd_series   = (df["close"] - running_max) / running_max * 100
        dd_current  = float(dd_series.iloc[-1])
        dd_sorted   = dd_series.nsmallest(3).values
        dd_max1 = float(dd_sorted[0]) if len(dd_sorted) > 0 else None
        dd_max2 = float(dd_sorted[1]) if len(dd_sorted) > 1 else None
        dd_max3 = float(dd_sorted[2]) if len(dd_sorted) > 2 else None
        dd_cfg    = _dd_cfg if _dd_cfg is not None else _get_drawdown_config()
        dd_events = _compute_dd_events(df, dd_cfg.min_depth_pct)

    cfg  = _regime_cfg if _regime_cfg is not None else _get_regime_config()
    vcfg = _vol_cfg    if _vol_cfg    is not None else _get_volatility_config()

    sl, st_pct, cb = cfg.slope_lookback, cfg.slope_threshold_pct, cfg.confirm_bars
    nb, sm         = cfg.nascent_bars, cfg.strong_slope_multiplier

    _vol_args = dict(
        atr_period=vcfg.atr_period, confirm_bars=vcfg.confirm_bars,
        pct_low=vcfg.pct_low, pct_high=vcfg.pct_high, pct_extreme=vcfg.pct_extreme,
        dur_short_pct=vcfg.dur_short_pct, dur_long_pct=vcfg.dur_long_pct,
    )

    df_w_reg = _resample_ohlc(df, "W")
    df_m_reg = _resample_ohlc(df, "M")

    if quick:
        rz_d = _compute_regime_zones(df,       cfg.ema_period_d, sl, st_pct, cb, nb, sm)
        rz_w = _compute_regime_zones(df_w_reg, cfg.ema_period_w, sl, st_pct, cb, nb, sm)
        rz_m = _compute_regime_zones(df_m_reg, cfg.ema_period_m, sl, st_pct, cb, nb, sm)
        vz_d = _compute_vol_zones(df,       **_vol_args)
        vz_w = _compute_vol_zones(df_w_reg, **_vol_args)
        vz_m = _compute_vol_zones(df_m_reg, **_vol_args)
    else:
        # Secuencial: en Codespace (2 CPUs) el pool interno genera contención de GIL
        # y es más lento que ejecutar numpy/pandas en serie.
        rz_d = _compute_regime_zones(df,       cfg.ema_period_d, sl, st_pct, cb, nb, sm)
        rz_w = _compute_regime_zones(df_w_reg, cfg.ema_period_w, sl, st_pct, cb, nb, sm)
        rz_m = _compute_regime_zones(df_m_reg, cfg.ema_period_m, sl, st_pct, cb, nb, sm)
        vz_d = _compute_vol_zones(df,       **_vol_args)
        vz_w = _compute_vol_zones(df_w_reg, **_vol_args)
        vz_m = _compute_vol_zones(df_m_reg, **_vol_args)

    if quick:
        best_sma_d = _prev_best.get("best_sma_d")
        best_ema_d = _prev_best.get("best_ema_d")
        best_sma_w = _prev_best.get("best_sma_w")
        best_ema_w = _prev_best.get("best_ema_w")
        best_sma_m = _prev_best.get("best_sma_m")
        best_ema_m = _prev_best.get("best_ema_m")
    else:
        best_sma_d = _find_best_ma(df["close"],       df["high"],       df["low"],       "sma")
        best_ema_d = _find_best_ma(df["close"],       df["high"],       df["low"],       "ema")
        best_sma_w = _find_best_ma(df_w_reg["close"], df_w_reg["high"], df_w_reg["low"], "sma")
        best_ema_w = _find_best_ma(df_w_reg["close"], df_w_reg["high"], df_w_reg["low"], "ema")
        best_sma_m = _find_best_ma(df_m_reg["close"], df_m_reg["high"], df_m_reg["low"], "sma")
        best_ema_m = _find_best_ma(df_m_reg["close"], df_m_reg["high"], df_m_reg["low"], "ema")

    dist_sma_d = _sma_zscore(df["close"], best_sma_d)       if best_sma_d else None
    dist_sma_w = _sma_zscore(df_w_reg["close"], best_sma_w) if best_sma_w else None
    dist_sma_m = _sma_zscore(df_m_reg["close"], best_sma_m) if best_sma_m else None

    rsi_w = _rsi(df_w_reg["close"])
    rsi_m = _rsi(df_m_reg["close"])

    df = df.tail(260).reset_index(drop=True)

    today      = df.iloc[-1]["date"]
    last_close = float(df.iloc[-1]["close"])
    prev_close = float(df.iloc[-2]["close"]) if len(df) >= 2 else None

    month_start   = date(today.year, today.month, 1)
    quarter_start = date(today.year, _Q_MONTH[today.month], 1)
    year_start    = date(today.year, 1, 1)
    w52_start     = _one_year_before(today)

    ref_month   = _closest_price_on_or_before(df, month_start)
    ref_quarter = _closest_price_on_or_before(df, quarter_start)
    ref_year    = _closest_price_on_or_before(df, year_start)
    ref_52w     = _closest_price_on_or_before(df, w52_start)

    close = df["close"]
    sma20  = float(close.rolling(20).mean().iloc[-1])  if not pd.isna(close.rolling(20).mean().iloc[-1])  else None
    sma50  = float(close.rolling(50).mean().iloc[-1])  if not pd.isna(close.rolling(50).mean().iloc[-1])  else None
    sma200 = float(close.rolling(200).mean().iloc[-1]) if not pd.isna(close.rolling(200).mean().iloc[-1]) else None

    rsi = _rsi(close)

    def _vol_key(zones):
        return f"{zones[-1]['vol_regime']}_{zones[-1]['dur_regime']}" if zones else None

    def _atr_pct_last(zones):
        return zones[-1].get("atr_pct") if zones else None

    ind_trend_d   = rz_d[-1]["regime_detail"] if rz_d else None
    ind_trend_w   = rz_w[-1]["regime_detail"] if rz_w else None
    ind_trend_m   = rz_m[-1]["regime_detail"] if rz_m else None
    ind_vol_d     = _vol_key(vz_d)
    ind_vol_w     = _vol_key(vz_w)
    ind_vol_m     = _vol_key(vz_m)
    ind_atr_pct_d = _atr_pct_last(vz_d)
    ind_atr_pct_w = _atr_pct_last(vz_w)
    ind_atr_pct_m = _atr_pct_last(vz_m)
    ind_rsi_d     = round(rsi,   2) if rsi   is not None else None
    ind_rsi_w     = round(rsi_w, 2) if rsi_w is not None else None
    ind_rsi_m     = round(rsi_m, 2) if rsi_m is not None else None

    ind_resist_pct = ind_support_pct = None
    try:
        sr = sr_service.compute_sr_from_df(df, cfg=_sr_cfg)
        if sr:
            ind_resist_pct  = sr["pivot_resist_pct"]
            ind_support_pct = sr["pivot_support_pct"]
    except Exception as exc:
        logger.warning("SR compute falló para asset_id=%d: %s", asset_id, exc)

    ind_rs_52w = None
    bm_id = s.query(Asset.benchmark_id).filter(Asset.id == asset_id).scalar()
    if bm_id:
        bm_last = (s.query(Price.close).filter(Price.asset_id == bm_id)
                   .order_by(Price.date.desc()).first())
        bm_ref  = (s.query(Price.close)
                   .filter(Price.asset_id == bm_id, Price.date <= w52_start)
                   .order_by(Price.date.desc()).first())
        if bm_last and bm_ref:
            bm_return_52w = _pct_change(float(bm_last[0]), float(bm_ref[0]))
            ret_52w       = _pct_change(last_close, ref_52w)
            if bm_return_52w is not None and ret_52w is not None:
                ind_rs_52w = round(ret_52w - bm_return_52w, 2)

    # Escritura en ind_* (keep_history=True, valor del día de hoy)
    _current_inds = {
        "trend_daily":              ind_trend_d,
        "trend_weekly":             ind_trend_w,
        "trend_monthly":            ind_trend_m,
        "volatility_daily":         ind_vol_d,
        "volatility_weekly":        ind_vol_w,
        "volatility_monthly":       ind_vol_m,
        "atr_percentile_daily":     ind_atr_pct_d,
        "atr_percentile_weekly":    ind_atr_pct_w,
        "atr_percentile_monthly":   ind_atr_pct_m,
        "rsi_daily":                ind_rsi_d,
        "rsi_weekly":               ind_rsi_w,
        "rsi_monthly":              ind_rsi_m,
        "dist_sma20":               _pct_change(last_close, sma20),
        "dist_sma50":               _pct_change(last_close, sma50),
        "dist_sma200":              _pct_change(last_close, sma200),
        "dist_optimal_sma_daily":   dist_sma_d,
        "dist_optimal_sma_weekly":  dist_sma_w,
        "dist_optimal_sma_monthly": dist_sma_m,
        "return_daily":             _pct_change(last_close, prev_close),
        "return_monthly":           _pct_change(last_close, ref_month),
        "return_quarterly":         _pct_change(last_close, ref_quarter),
        "return_yearly":            _pct_change(last_close, ref_year),
        "return_52w":               _pct_change(last_close, ref_52w),
        "relative_strength_52w":    ind_rs_52w,
    }
    for code, value in _current_inds.items():
        _upsert_ind(s, code, asset_id, today, value)

    # Escritura en current_indicator_values (keep_history=False)
    for code, val in [
        ("best_sma_d", best_sma_d), ("best_ema_d", best_ema_d),
        ("best_sma_w", best_sma_w), ("best_ema_w", best_ema_w),
        ("best_sma_m", best_sma_m), ("best_ema_m", best_ema_m),
        ("drawdown_current", round(dd_current, 2)),
        ("drawdown_max1",    round(dd_max1, 2) if dd_max1 is not None else None),
        ("drawdown_max2",    round(dd_max2, 2) if dd_max2 is not None else None),
        ("drawdown_max3",    round(dd_max3, 2) if dd_max3 is not None else None),
        ("resistance_pct",   ind_resist_pct),
        ("support_pct",      ind_support_pct),
    ]:
        if val is not None:
            _upsert_current_ind(s, asset_id, code, value_num=float(val))

    s.commit()


# ── Valor vigente por indicador (mismo UI que backfill) ────────────────────────────

def _cur_trend(tf_key: str):
    def fn(df, df_w, df_m, regime_cfg, **kw):
        df_tf  = {"d": df, "w": df_w, "m": df_m}[tf_key]
        period = {"d": regime_cfg.ema_period_d, "w": regime_cfg.ema_period_w,
                  "m": regime_cfg.ema_period_m}[tf_key]
        zones  = _compute_regime_zones(
            df_tf, period,
            regime_cfg.slope_lookback, regime_cfg.slope_threshold_pct,
            regime_cfg.confirm_bars, regime_cfg.nascent_bars,
            regime_cfg.strong_slope_multiplier,
        )
        return zones[-1]["regime_detail"] if zones else None
    return fn


def _cur_volatility(tf_key: str):
    def fn(df, df_w, df_m, vol_cfg, **kw):
        df_tf    = {"d": df, "w": df_w, "m": df_m}[tf_key]
        vol_args = dict(
            atr_period=vol_cfg.atr_period, confirm_bars=vol_cfg.confirm_bars,
            pct_low=vol_cfg.pct_low, pct_high=vol_cfg.pct_high,
            pct_extreme=vol_cfg.pct_extreme,
            dur_short_pct=vol_cfg.dur_short_pct, dur_long_pct=vol_cfg.dur_long_pct,
        )
        vz = _compute_vol_zones(df_tf, **vol_args)
        if not vz:
            return None
        last = vz[-1]
        return f"{last['vol_regime']}_{last['dur_regime']}"
    return fn


def _cur_drawdown_current(df, asset_id=None, ath_cache=None, **kw):
    """Caída desde ATH histórico (usa ath_cache si está disponible)."""
    last = float(df["close"].iloc[-1])
    ath  = (ath_cache.get(asset_id) if ath_cache and asset_id is not None
            else float(df["close"].astype(float).max()))
    return round((last - ath) / ath * 100, 2) if ath else 0.0


def _cur_drawdown_max1(df, asset_id=None, close_cache=None, **kw):
    c = pd.Series(close_cache.get(int(asset_id)) if (close_cache and asset_id is not None)
                  else df["close"].to_numpy(dtype=float))
    vals = ((c - c.cummax()) / c.cummax() * 100).nsmallest(3).values
    return round(float(vals[0]), 2) if len(vals) >= 1 else None


def _cur_drawdown_max2(df, asset_id=None, close_cache=None, **kw):
    c = pd.Series(close_cache.get(int(asset_id)) if (close_cache and asset_id is not None)
                  else df["close"].to_numpy(dtype=float))
    vals = ((c - c.cummax()) / c.cummax() * 100).nsmallest(3).values
    return round(float(vals[1]), 2) if len(vals) >= 2 else None


def _cur_drawdown_max3(df, asset_id=None, close_cache=None, **kw):
    c = pd.Series(close_cache.get(int(asset_id)) if (close_cache and asset_id is not None)
                  else df["close"].to_numpy(dtype=float))
    vals = ((c - c.cummax()) / c.cummax() * 100).nsmallest(3).values
    return round(float(vals[2]), 2) if len(vals) >= 3 else None


def _cur_best_ma(tf_key: str, kind: str):
    def fn(df, df_w, df_m, **kw):
        df_tf = {"d": df, "w": df_w, "m": df_m}[tf_key]
        return _find_best_ma(df_tf["close"], df_tf["high"], df_tf["low"], kind)
    return fn


def _cur_resistance_pct(df, **kw):
    try:
        cfg = kw.get("sr_cfg") or sr_service._get_sr_config()
        r = sr_service.compute_sr_from_df(df.tail(260).reset_index(drop=True), cfg=cfg)
        return r["pivot_resist_pct"] if r else None
    except Exception:
        return None


def _cur_support_pct(df, **kw):
    try:
        cfg = kw.get("sr_cfg") or sr_service._get_sr_config()
        r = sr_service.compute_sr_from_df(df.tail(260).reset_index(drop=True), cfg=cfg)
        return r["pivot_support_pct"] if r else None
    except Exception:
        return None


def _cur_relative_strength_52w(df, session, asset_id,
                              price_cache=None, benchmark_cache=None, **kw):
    """Valor vigente: solo el ultimo dato — O(log N) sin loop completo."""
    d          = df.iloc[-1]["date"]
    last_close = float(df.iloc[-1]["close"])
    ref_ord    = _one_year_before(d).toordinal()

    if benchmark_cache is not None:
        bm_id = benchmark_cache.get(asset_id)
    else:
        bm_id = session.query(Asset.benchmark_id).filter(Asset.id == asset_id).scalar()
    if not bm_id:
        return None

    if price_cache and bm_id in price_cache:
        bm_df = price_cache[bm_id]
    else:
        bm_rows = session.query(Price.date, Price.close).filter(
            Price.asset_id == bm_id
        ).order_by(Price.date.asc()).all()
        if not bm_rows:
            return None
        bm_df = pd.DataFrame(bm_rows, columns=["date", "close"])

    bm_ords   = np.array([dd.toordinal() for dd in bm_df["date"]])
    bm_closes = bm_df["close"].values.astype(float)
    a_ords    = np.array([dd.toordinal() for dd in df["date"]])
    a_cls     = df["close"].values.astype(float)

    def _lkup(ords, cls, target):
        j = int(np.searchsorted(ords, target, side="right")) - 1
        return float(cls[j]) if j >= 0 else None

    bm_now = _lkup(bm_ords, bm_closes, a_ords[-1])
    bm_ref = _lkup(bm_ords, bm_closes, ref_ord)
    a_ref  = _lkup(a_ords,  a_cls,     ref_ord)

    if (bm_now is not None and bm_ref and bm_ref != 0
            and a_ref is not None and a_ref != 0 and last_close != 0):
        return round(
            (last_close - a_ref) / a_ref * 100 - (bm_now - bm_ref) / bm_ref * 100,
            2,
        )
    return None


def _make_current_fn(code: str):
    """Envuelve _BACKFILL_FNS[code] para retornar solo el último valor."""
    bf = _BACKFILL_FNS[code]
    def fn(**kw):
        values = bf(**kw)
        if isinstance(values, pd.Series):
            return values.iloc[-1] if len(values) > 0 else None
        return values[-1] if values else None
    return fn


# Código → función de valor vigente: retorna un único valor (el de hoy)
_CURRENT_FNS: dict[str, callable] = {
    code: _make_current_fn(code) for code in _BACKFILL_FNS
}
_CURRENT_FNS.update({
    # trend/volatility: sobreescriben _make_current_fn, evitan _zones_to_series loop
    "trend_daily":           _cur_trend("d"),
    "trend_weekly":          _cur_trend("w"),
    "trend_monthly":         _cur_trend("m"),
    "volatility_daily":      _cur_volatility("d"),
    "volatility_weekly":     _cur_volatility("w"),
    "volatility_monthly":    _cur_volatility("m"),
    # keep_history=False
    "drawdown_current":      _cur_drawdown_current,
    "drawdown_max1":         _cur_drawdown_max1,
    # keep_history=True, sin backfill fn
    "drawdown_max2":         _cur_drawdown_max2,
    "drawdown_max3":         _cur_drawdown_max3,
    "best_sma_d":            _cur_best_ma("d", "sma"),
    "best_ema_d":            _cur_best_ma("d", "ema"),
    "best_sma_w":            _cur_best_ma("w", "sma"),
    "best_ema_w":            _cur_best_ma("w", "ema"),
    "best_sma_m":            _cur_best_ma("m", "sma"),
    "best_ema_m":            _cur_best_ma("m", "ema"),
    "resistance_pct":        _cur_resistance_pct,
    "support_pct":           _cur_support_pct,
    "relative_strength_52w": _cur_relative_strength_52w,
})

# Estos indicadores no tienen tabla ind_*; van a current_indicator_values
_CURRENT_ONLY_CODES = frozenset({
    "drawdown_current", "drawdown_max1", "drawdown_max2", "drawdown_max3",
    "resistance_pct", "support_pct",
    "best_sma_d", "best_ema_d",
    "best_sma_w", "best_ema_w",
    "best_sma_m", "best_ema_m",
})


def _compute_current_indicator(code: str, asset_ids: list,
                        *, price_cache: dict, df_w_cache: dict, df_m_cache: dict,
                        best_sma_cache: dict,
                        benchmark_cache: dict, ath_cache: dict,
                        close_cache: dict,
                        regime_cfg, vol_cfg, sr_cfg,
                        asset_tick=None,
                        error_collector=None, collector_lock=None) -> None:
    s = get_session()
    compute_fn   = _CURRENT_FNS[code]
    current_only = code in _CURRENT_ONLY_CODES

    for asset_id in asset_ids:
        df = price_cache.get(asset_id)
        if df is None or len(df) < _MIN_ROWS:
            if asset_tick:
                asset_tick()
            continue

        asset_date = df["date"].iloc[-1]
        df_w = df_w_cache.get(asset_id)
        df_m = df_m_cache.get(asset_id)

        try:
            val = compute_fn(
                df=df, df_w=df_w, df_m=df_m,
                regime_cfg=regime_cfg, vol_cfg=vol_cfg,
                session=s, asset_id=asset_id,
                price_cache=price_cache, best_sma_cache=best_sma_cache,
                benchmark_cache=benchmark_cache, ath_cache=ath_cache,
                close_cache=close_cache,
                sr_cfg=sr_cfg,
            )
            if val is not None and pd.notna(val):
                if current_only:
                    v_num = float(val) if isinstance(val, (int, float, np.floating)) else None
                    v_str = str(val) if v_num is None else None
                    _upsert_current_ind(s, asset_id, code, value_num=v_num, value_str=v_str)
                else:
                    _upsert_ind(s, code, asset_id, asset_date, val)
            s.commit()
        except Exception as exc:
            logger.warning("Error valor vigente code=%s asset_id=%d: %s", code, asset_id, exc)
            s.rollback()
            if error_collector is not None:
                with collector_lock:
                    error_collector.setdefault(asset_id, []).append(f"{code}: {exc}")
        finally:
            if asset_tick:
                asset_tick()


def _compute_current_indicator_worker(code, asset_ids,
                               price_cache, df_w_cache, df_m_cache,
                               best_sma_cache, benchmark_cache,
                               ath_cache, close_cache, regime_cfg, vol_cfg, sr_cfg, asset_tick,
                               error_collector=None, collector_lock=None):
    from app.database import Session as _DbSession
    try:
        _compute_current_indicator(
            code, asset_ids,
            price_cache=price_cache, df_w_cache=df_w_cache, df_m_cache=df_m_cache,
            best_sma_cache=best_sma_cache,
            benchmark_cache=benchmark_cache, ath_cache=ath_cache,
            close_cache=close_cache,
            regime_cfg=regime_cfg, vol_cfg=vol_cfg, sr_cfg=sr_cfg,
            asset_tick=asset_tick,
            error_collector=error_collector, collector_lock=collector_lock,
        )
    except Exception as exc:
        logger.warning("Error worker valor vigente code=%s: %s", code, exc)
        if error_collector is not None:
            with collector_lock:
                for asset_id in asset_ids:
                    error_collector.setdefault(asset_id, []).append(f"{code}: {exc}")
    finally:
        _DbSession.remove()


def recompute_current_indicators(progress_cb=None, *, codes=None,
                            preloaded_caches: tuple | None = None) -> dict:
    """Recomputa el valor vigente de los indicadores.

    codes: subconjunto de _CURRENT_FNS a procesar (None = todos).
    preloaded_caches: (price_cache, ath_cache, close_cache) ya cargados por el
    caller para no releer precios de la DB.
    """
    import threading as _th

    current_codes = sorted(codes) if codes is not None else sorted(_CURRENT_FNS.keys())
    n_ind      = len(current_codes)

    if progress_cb:
        progress_cb(0, 1, "Cargando precios en memoria...")

    s = get_session()
    if preloaded_caches is not None:
        price_cache, ath_cache, close_cache = preloaded_caches
    else:
        price_cache, ath_cache, close_cache = _load_recent_prices(s)
    best_sma_cache                            = _load_best_sma_cache(s)
    benchmark_cache                           = _load_benchmark_cache(s)
    asset_ids       = sorted(price_cache.keys())
    n_assets        = len(asset_ids)
    total_work      = n_ind * n_assets

    if progress_cb:
        progress_cb(0, 1, "Precalculando resamples semanales y mensuales...")
    df_w_cache = {aid: _resample_ohlc(df, "W") for aid, df in price_cache.items()}
    df_m_cache = {aid: _resample_ohlc(df, "M") for aid, df in price_cache.items()}

    regime_cfg = _get_regime_config()
    vol_cfg    = _get_volatility_config()
    sr_cfg     = sr_service._get_sr_config()

    from app.database import Session as _DbSession
    _DbSession.remove()

    _assets_done = 0
    _lock        = _th.Lock()
    asset_errors: dict = {}   # asset_id -> [errores de cualquier indicador]

    def _make_tick(code):
        per_ind = [0]
        def _tick():
            nonlocal _assets_done
            per_ind[0] += 1
            with _lock:
                _assets_done += 1
                n = _assets_done
            if progress_cb:
                progress_cb(n, total_work, f"{code}: {per_ind[0]}/{n_assets}")
        return _tick

    with _TPE(max_workers=n_ind) as pool:
        futures = {
            pool.submit(
                _compute_current_indicator_worker,
                code, asset_ids,
                price_cache, df_w_cache, df_m_cache,
                best_sma_cache, benchmark_cache,
                ath_cache, close_cache, regime_cfg, vol_cfg, sr_cfg,
                _make_tick(code),
                error_collector=asset_errors, collector_lock=_lock,
            ): code
            for code in current_codes
        }
        if progress_cb:
            progress_cb(0, total_work, f"__init__:{n_assets}:{','.join(current_codes)}")
        for future in as_completed(futures):
            code = futures[future]
            try:
                future.result()
            except Exception as exc:
                logger.warning("Error valor vigente code=%s: %s", code, exc)

    # Un registro por activo en indicator_update_log, agregando errores de
    # todos los indicadores (no solo el último que se haya procesado).
    log_session = get_session()
    for asset_id in asset_ids:
        errs = asset_errors.get(asset_id)
        _save_indicator_log(
            asset_id, success=not errs,
            error="; ".join(errs) if errs else None,
            session=log_session,
        )

    ticker_map = {
        r[0]: r[1] for r in log_session.query(Asset.id, Asset.ticker)
                          .filter(Asset.id.in_(asset_ids)).all()
    }
    errors = [
        {"ticker": ticker_map.get(aid, str(aid)), "error": "; ".join(errs)}
        for aid, errs in asset_errors.items()
    ]

    return {"total": n_assets, "success": n_assets - len(errors), "errors": errors}


# ── Acciones combinadas (Centro de Datos) ───────────────────────────────────────

def _derive_recent_caches(price_cache_full: dict) -> tuple[dict, dict, dict]:
    """Deriva (price_cache 1500d, ath_cache, close_cache) desde precios completos
    ya en memoria, con la misma semántica que _load_recent_prices pero sin
    volver a leer la DB."""
    cutoff = date.today() - timedelta(days=_RECENT_LOOKBACK_DAYS)
    price_cache: dict = {}
    ath_cache:   dict = {}
    close_cache: dict = {}
    for aid, df in price_cache_full.items():
        closes = df["close"].dropna()
        if len(closes):
            ath_cache[aid]   = float(closes.max())
            close_cache[aid] = closes.to_numpy(dtype=float)
        price_cache[aid] = df[df["date"] >= cutoff].reset_index(drop=True)
    return price_cache, ath_cache, close_cache


def _refresh_group_scores() -> None:
    """Refresca group_scores para que el mapa de mercado quede al día."""
    try:
        from app.services import indicator_service
        indicator_service.compute_group_scores(
            indicator_service.get_default_target_date())
    except Exception as exc:
        logger.warning("Error refrescando scores de grupo: %s", exc)


def update_indicator_history(progress_cb=None) -> dict:
    """Recomputa los indicadores vigentes sin historia (best_*, drawdowns, S/R)
    y completa huecos históricos de los demás (backfill delta).

    Los precios se cargan una sola vez, y el valor de hoy de los indicadores
    con historia lo escribe el backfill (no se computa dos veces)."""
    s = get_session()
    if progress_cb:
        progress_cb(0, 1, "Cargando precios en memoria...")
    price_cache_full = _load_all_prices(s)
    snap_caches      = _derive_recent_caches(price_cache_full)

    r1 = recompute_current_indicators(progress_cb=progress_cb,
                                 codes=_CURRENT_ONLY_CODES,
                                 preloaded_caches=snap_caches)
    r2 = backfill_all_indicator_values(progress_cb=progress_cb, force=False,
                                       price_cache=price_cache_full)
    _refresh_group_scores()
    errors = r1["errors"] + r2["errors"]
    total  = r1["total"]
    return {"total": total, "success": max(total - len(errors), 0), "errors": errors}


def rebuild_indicator_history(progress_cb=None) -> dict:
    """Borra y recalcula toda la historia de indicadores técnicos desde cero."""
    s = get_session()
    if progress_cb:
        progress_cb(0, 1, "Cargando precios en memoria...")
    price_cache_full = _load_all_prices(s)
    snap_caches      = _derive_recent_caches(price_cache_full)

    r1 = backfill_all_indicator_values(progress_cb=progress_cb, force=True,
                                       price_cache=price_cache_full)
    r2 = recompute_current_indicators(progress_cb=progress_cb,
                                 codes=_CURRENT_ONLY_CODES,
                                 preloaded_caches=snap_caches)
    _refresh_group_scores()
    errors = r1["errors"] + r2["errors"]
    total  = r2["total"]
    return {"total": total, "success": max(total - len(errors), 0), "errors": errors}


# ── Funciones públicas para gráficos ─────────────────────────────────────────

def get_regime_zones_for_chart(df: "pd.DataFrame", cfg=None) -> dict:
    if cfg is None:
        cfg = _get_regime_config()
    sl, st_pct, cb = cfg.slope_lookback, cfg.slope_threshold_pct, cfg.confirm_bars
    nb, sm = cfg.nascent_bars, cfg.strong_slope_multiplier
    df_w = _resample_ohlc(df, "W")
    df_m = _resample_ohlc(df, "M")
    return {
        "D": _compute_regime_zones(df,   cfg.ema_period_d, sl, st_pct, cb, nb, sm),
        "W": _compute_regime_zones(df_w, cfg.ema_period_w, sl, st_pct, cb, nb, sm),
        "M": _compute_regime_zones(df_m, cfg.ema_period_m, sl, st_pct, cb, nb, sm),
    }


def get_vol_zones_for_chart(df: "pd.DataFrame", cfg=None) -> dict:
    if cfg is None:
        cfg = _get_volatility_config()
    vol_args = dict(
        atr_period=cfg.atr_period, confirm_bars=cfg.confirm_bars,
        pct_low=cfg.pct_low, pct_high=cfg.pct_high, pct_extreme=cfg.pct_extreme,
        dur_short_pct=cfg.dur_short_pct, dur_long_pct=cfg.dur_long_pct,
    )
    df_w = _resample_ohlc(df, "W")
    df_m = _resample_ohlc(df, "M")
    return {
        "D": _compute_vol_zones(df,   **vol_args),
        "W": _compute_vol_zones(df_w, **vol_args),
        "M": _compute_vol_zones(df_m, **vol_args),
    }


def get_dd_events_for_chart(df: "pd.DataFrame", cfg=None) -> list:
    if cfg is None:
        cfg = _get_drawdown_config()
    return _compute_dd_events(df, cfg.min_depth_pct)


def get_market_map_data() -> dict:
    """Promedios de tendencia por grupo, leídos de group_scores
    (última fecha disponible). Los calcula indicator_service.compute_group_scores,
    que se refresca en el pipeline diario y tras cada actualización de indicadores."""
    from app.models import (
        Country, GroupScore, Industry, InstrumentType, Market, Sector,
    )

    s = get_session()

    _GT_TO_KEY = {
        "sector":          "sector",
        "industry":        "industry",
        "country":         "country",
        "instrument_type": "itype",
        "market":          "market",
    }
    result: dict = {dk: {} for dk in _GT_TO_KEY.values()}

    last = s.query(sa.func.max(GroupScore.date)).scalar()
    if last is None:
        return result

    names = {
        "sector":   {r.id: r.name for r in s.query(Sector.id, Sector.name).all()},
        "industry": {r.id: r.name for r in s.query(Industry.id, Industry.name).all()},
        "country":  {r.id: r.name for r in s.query(Country.id, Country.name).all()},
        "itype":    {r.id: r.name for r in s.query(InstrumentType.id, InstrumentType.name).all()},
        "market":   {r.id: r.name for r in s.query(Market.id, Market.name).all()},
    }

    def _r(v):
        return round(v) if v is not None else None

    gscores = (s.query(GroupScore)
               .filter(GroupScore.date == last)
               .all())
    for gs in gscores:
        dk = _GT_TO_KEY.get(gs.group_type)
        if dk is None:
            continue
        result[dk][gs.group_id] = {
            "name": names[dk].get(gs.group_id, f"#{gs.group_id}"),
            "n":    gs.n_assets,
            "d":    _r(gs.regime_score_d),
            "w":    _r(gs.regime_score_w),
            "m":    _r(gs.regime_score_m),
        }
    return result
