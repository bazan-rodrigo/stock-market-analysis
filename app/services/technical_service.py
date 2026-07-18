"""
Servicio de screener.
Calcula métricas técnicas por activo y las persiste en las tablas ind_{code}
(serie temporal por indicador) y current_indicator_values (valores vigentes).
"""
import bisect
import hashlib
import logging
import math
import sys
import threading
from concurrent.futures import ThreadPoolExecutor as _TPE, as_completed
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import sqlalchemy as sa

from app.database import engine, get_session
from app.models import Asset, DrawdownConfig, Price, RegimeConfig, VolatilityConfig
from app.models.indicator_definition import IndicatorDefinition
from app.models.indicator_store import (CurrentIndicatorValue, IndAssetMeta,
                                        get_ind_table, use_wide_ind_tables,
                                        _WIDE, _WIDE_CADENCE_TABLE,
                                        _WIDE_CADENCE_COLUMNS, _get_wide_table)

from app.services import db_compat, sr_service
from app.services.db_compat import INSERTED
from app.services.db_compat import set_bulk_load_checks as _set_bulk_load_checks

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


def _wilder_smooth(s: pd.Series, period: int) -> pd.Series:
    """Suavizado de Wilder: semilla = SMA de los primeros `period` valores,
    luego alpha = 1/period. Idéntico al emaW del gráfico (chart_callbacks.js)
    y al estándar de la industria (TradingView, StockCharts)."""
    out = pd.Series(np.nan, index=s.index, dtype=float)
    if len(s) < period:
        return out
    seed   = float(s.iloc[:period].mean())
    seeded = pd.concat([pd.Series([seed]), s.iloc[period:]], ignore_index=True)
    vals   = seeded.ewm(alpha=1 / period, adjust=False).mean().to_numpy()
    out.iloc[period - 1:] = vals
    return out


def _atr_series(df: pd.DataFrame, period: int) -> pd.Series:
    prev_close = df["close"].shift(1).to_numpy()
    high = df["high"].to_numpy()
    low  = df["low"].to_numpy()
    tr = np.fmax(high - low,
         np.fmax(np.abs(high - prev_close), np.abs(low - prev_close)))
    return _wilder_smooth(pd.Series(tr, index=df.index), period)


def _confirm_codes(raw_codes: np.ndarray, confirm_bars: int) -> np.ndarray:
    """Máquina de confirmación de regímenes, iterando por RACHAS (RLE) en vez
    de barra por barra: decenas de iteraciones en lugar de miles por activo.
    Semántica idéntica al loop original (test de paridad en la suite):
    - los ceros (NaN) no cortan ni suman a la racha pendiente
    - una racha del código vigente resetea el candidato pendiente
    - un candidato nuevo arma pending en su 1ª ocurrencia SIN chequear el
      umbral; confirma recién en la ocurrencia max(2, confirm_bars)
    - la barra que confirma ya pertenece al régimen nuevo
    """
    n = len(raw_codes)
    confirmed = np.zeros(n, dtype=np.int8)
    nz = np.flatnonzero(raw_codes != 0)
    if len(nz) == 0:
        return confirmed
    seq     = raw_codes[nz].astype(np.int64)
    starts  = np.flatnonzero(np.r_[True, seq[1:] != seq[:-1]])
    lengths = np.diff(np.r_[starts, len(seq)])

    current, pending, pending_n = 0, 0, 0
    changes: list[tuple[int, int]] = []      # (índice original, nuevo vigente)
    for k, run_len in zip(starts, lengths):
        v = int(seq[k])
        if v == current:
            pending, pending_n = 0, 0
            continue
        if v == pending:
            need = max(1, confirm_bars - pending_n)
            if run_len >= need:
                changes.append((int(nz[k + need - 1]), v))
                current, pending, pending_n = v, 0, 0
            else:
                pending_n += int(run_len)
        else:
            j = max(2, confirm_bars)
            if run_len >= j:
                changes.append((int(nz[k + j - 1]), v))
                current, pending, pending_n = v, 0, 0
            else:
                pending, pending_n = v, int(run_len)

    for idx, val in changes:
        confirmed[idx:] = val
    return confirmed


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
    valid_arr  = valid.to_numpy()
    th_low     = float(np.nanpercentile(valid_arr, pct_low))
    th_high    = float(np.nanpercentile(valid_arr, pct_high))
    th_extreme = float(np.nanpercentile(valid_arr, pct_extreme))
    atr_vals = atr.values
    raw_codes = np.where(np.isnan(atr_vals), 0,
                np.where(atr_vals >= th_extreme, 4,
                np.where(atr_vals >= th_high,    3,
                np.where(atr_vals <= th_low,     1, 2)))).astype(np.int8)
    n = len(raw_codes)
    confirmed = _confirm_codes(raw_codes, confirm_bars)

    _CODE = [None, "baja", "normal", "alta", "extrema"]
    dates_arr = df["date"].values
    valid_sorted = np.sort(valid_arr)
    n_valid = len(valid_sorted)
    atr_pct_ranks = np.full(n, np.nan)
    if n_valid > 0:
        valid_mask = ~np.isnan(atr_vals)
        atr_pct_ranks[valid_mask] = (
            np.searchsorted(valid_sorted, atr_vals[valid_mask]) / n_valid * 100
        )
    # Último rank válido acumulado hasta cada barra (para el atr_pct de la zona)
    _valid_pos = np.where(~np.isnan(atr_pct_ranks), np.arange(n), -1)
    _last_valid = np.maximum.accumulate(_valid_pos)

    # Zonas por segmentos de `confirmed` (fechas solo en los bordes)
    seg_starts = np.flatnonzero(np.r_[True, confirmed[1:] != confirmed[:-1]])
    seg_ends   = np.r_[seg_starts[1:] - 1, n - 1]
    zones = []
    for i0, i1 in zip(seg_starts, seg_ends):
        c = int(confirmed[i0])
        if c == 0:
            continue
        j = int(_last_valid[i1])
        atr_pct = round(float(atr_pct_ranks[j]), 1) if j >= i0 else None
        zones.append({"start": _date_str(dates_arr[i0]),
                      "end":   _date_str(dates_arr[i1]),
                      "vol_regime": _CODE[c],
                      "_bars": int(i1 - i0 + 1),
                      "atr_pct": atr_pct,
                      "_i0": int(i0), "_i1": int(i1)})
    if not zones:
        return []
    dur_hist: dict[str, list[int]] = {"baja": [], "normal": [], "alta": [], "extrema": []}
    for z in zones[:-1]:
        dur_hist[z["vol_regime"]].append(z["_bars"])
    # Umbrales de percentil una vez por régimen (4), no una vez por zona:
    # todas las zonas de un mismo régimen comparten el mismo dur_hist, así
    # que _classify_duration recalculaba los mismos percentiles cientos de
    # veces por activo (uno por zona) en vez de reusarlos.
    dur_thresholds: dict[str, tuple[float, float] | None] = {}
    for regime, hist in dur_hist.items():
        if len(hist) < 3:
            dur_thresholds[regime] = None
        else:
            dur_thresholds[regime] = (
                float(np.percentile(hist, dur_short_pct)),
                float(np.percentile(hist, dur_long_pct)),
            )
    for z in zones:
        thresholds = dur_thresholds[z["vol_regime"]]
        bars = z["_bars"]
        if thresholds is None:
            z["dur_regime"] = "media"
        elif bars <= thresholds[0]:
            z["dur_regime"] = "corta"
        elif bars >= thresholds[1]:
            z["dur_regime"] = "larga"
        else:
            z["dur_regime"] = "media"
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
    confirmed = _confirm_codes(raw_codes, confirm_bars)

    _CODE = [None, "lateral", "bullish", "bearish"]
    dates_arr = df["date"].values
    slope_filled = np.where(np.isnan(s_vals), 0.0, s_vals)

    # Zonas por segmentos de `confirmed` (fechas solo en los bordes)
    seg_starts = np.flatnonzero(np.r_[True, confirmed[1:] != confirmed[:-1]])
    seg_ends   = np.r_[seg_starts[1:] - 1, n - 1]
    zones = []
    for i0, i1 in zip(seg_starts, seg_ends):
        c = int(confirmed[i0])
        if c == 0:
            continue
        regime = _CODE[c]
        zones.append({
            "start": _date_str(dates_arr[i0]),
            "end":   _date_str(dates_arr[i1]),
            "regime": regime,
            "regime_detail": _regime_detail(
                regime, int(i1 - i0 + 1), float(slope_filled[i1]),
                slope_threshold_pct, nascent_bars, strong_slope_multiplier,
            ),
            "_i0": int(i0), "_i1": int(i1),
        })
    return zones


def _rsi(close: pd.Series, period: int = 14) -> float | None:
    if len(close) < period + 1:
        return None
    val = _rsi_series(close, period).iloc[-1]
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
    close = subset.iloc[-1]["close"]
    return None if pd.isna(close) else float(close)


def _rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    """RSI con suavizado de Wilder, idéntico al del gráfico (JS)."""
    delta    = close.diff()
    gain     = delta.clip(lower=0).fillna(0.0)
    loss     = (-delta).clip(lower=0).fillna(0.0)
    avg_gain = _wilder_smooth(gain, period)
    avg_loss = _wilder_smooth(loss, period)
    rsi = 100 - 100 / (1 + avg_gain / avg_loss.replace(0, np.nan))
    # avg_loss == 0 con avg_gain calculado → RSI 100 (subida pura), no NaN
    rsi = rsi.where(~((avg_loss == 0) & avg_gain.notna()), 100.0)
    return rsi.round(2)


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


def _return_vs_ref_series(df: pd.DataFrame, kind: str) -> pd.Series:
    """Retorno % de cada barra contra su fecha de referencia, vectorizado.

    kind: 'month_start' | 'quarter_start' | 'year_start' | 'year_back'.
    Equivalentes exactos de los cálculos fecha-por-fecha anteriores
    (DateOffset(years=1) resuelve 29/2 → 28/2 igual que _one_year_before);
    paridad verificada en la suite."""
    closes = df["close"].values.astype(float)
    dts    = pd.to_datetime(pd.Series(list(df["date"])))
    if kind == "month_start":
        ref = dts.dt.to_period("M").dt.start_time
    elif kind == "quarter_start":
        ref = dts.dt.to_period("Q").dt.start_time
    elif kind == "year_start":
        ref = dts.dt.to_period("Y").dt.start_time
    elif kind == "year_back":
        ref = dts - pd.DateOffset(years=1)
    else:
        raise ValueError(f"kind desconocido: {kind!r}")

    indices    = np.searchsorted(dts.values, ref.values, side="right") - 1
    valid      = indices >= 0
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

    if "_i0" in zones[0]:
        # Camino rápido: las zonas traen índices del frame de origen (que es
        # el mismo target) — llenado por slices, sin convertir fechas por barra
        out = [None] * len(target)
        for z in zones:
            val = z.get(value_key)
            out[z["_i0"]:z["_i1"] + 1] = [val] * (z["_i1"] - z["_i0"] + 1)
    else:
        # Camino legacy: mapeo por rango de fechas (zonas externas sin índices)
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
    """UPSERT de un valor en ind_{code}.

    pd.isna (no solo None) porque un NaN numérico llega tal cual hasta acá
    si algún cálculo previo no lo convirtió a None (p.ej. un close NULL en
    la fila de precio propaga NaN a través de _pct_change sin que
    "reference != 0" lo filtre) — MySQLdb no sabe serializar NaN y tira
    ProgrammingError en el INSERT."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return
    if use_wide_ind_tables() and code in _WIDE:
        _tbl, column, cadence = _WIDE[code]
        upsert_ind_cadence(session, cadence, [column],
                           [(asset_id, target_date, value)])
        return
    t    = get_ind_table(code)
    stmt = db_compat.upsert(
        session, t,
        dict(asset_id=asset_id, date=target_date, value=value),
        {"value": INSERTED})
    session.execute(stmt)


def _null_wide_column(session, cadence: str, column: str, *,
                      asset_id=None, asset_ids=None, dates=None) -> None:
    """Pone en NULL una columna de la tabla ancha (docs/notes/
    design_ind_wide_tables.md): el equivalente al DELETE de fila del camino
    per-código — en la ancha no se borra la fila porque otras columnas la
    comparten. Sin filtros nullea la columna entera; con asset_id/asset_ids/
    dates acota."""
    wt = _get_wide_table(_WIDE_CADENCE_TABLE[cadence])
    stmt = sa.update(wt).values({wt.c[column]: None})
    if asset_id is not None:
        stmt = stmt.where(wt.c.asset_id == asset_id)
    elif asset_ids is not None:
        stmt = stmt.where(wt.c.asset_id.in_(asset_ids))
    if dates is not None:
        stmt = stmt.where(wt.c.date.in_(dates))
    session.execute(stmt)


def _upsert_current_ind(session, asset_id: int, code: str,
                        value_num=None, value_str=None) -> None:
    """UPSERT de un valor vigente en current_indicator_values."""
    stmt = db_compat.upsert(
        session, CurrentIndicatorValue.__table__,
        dict(asset_id=asset_id, code=code, value_num=value_num,
             value_str=value_str),
        {"value_num": value_num, "value_str": value_str})
    session.execute(stmt)


def _upsert_current_ind_batch(session, asset_id: int, values: list[tuple[str, float]]) -> None:
    """UPSERT en batch de varios códigos vigentes en current_indicator_values:
    a diferencia de _upsert_ind (una tabla ind_* por código, no fusionable),
    todos estos códigos comparten la misma tabla, así que un solo INSERT
    multi-fila reemplaza N round-trips por uno (medido con cProfile: la mitad
    de las queries de compute_current_indicators(quick=True) eran esto)."""
    rows = [{"asset_id": asset_id, "code": code, "value_num": float(val), "value_str": None}
            for code, val in values if val is not None]
    if not rows:
        return
    stmt = db_compat.upsert(
        session, CurrentIndicatorValue.__table__, rows,
        {"value_num": INSERTED, "value_str": INSERTED})
    session.execute(stmt)


_IND_BATCH = 5000  # filas por INSERT al escribir series de indicadores


def _series_dates_values(values, df) -> tuple[list, list]:
    """Las compute_fn de backfill retornan list (diario, indexada como df)
    o pd.Series (semanal/mensual, con su propio índice de fechas)."""
    if isinstance(values, pd.Series):
        return values.index.tolist(), values.tolist()
    return df["date"].tolist(), list(values)


# Filas acumuladas por transacción en backfills masivos: equilibrio entre
# pocos fsyncs (commits caros) y transacciones acotadas (undo log de InnoDB)
_COMMIT_ROWS = 25_000


def _pairs_to_write(dates_list: list, vals_list: list, existing) -> list:
    """Filtra qué (fecha, valor) escribir según el modo:

    None → todo (reemplazo total).
    set  → solo fechas faltantes + la última (el último precio es preliminar).
    dict {fecha: valor_guardado} → faltantes + cambiados + la última.
      Es el modo de los indicadores full_sample en delta: la serie se
      recalcula entera pero los valores viejos casi no cambian, así que
      solo se escriben las diferencias reales.

    Nota: se probó una variante vectorizada con numpy y el benchmark la
    descartó — este camino escalar cuesta ~1 ms por activo, y la versión
    numpy pagaba sorts y conversiones que no amortizaba.
    """
    if existing is None:
        return [(d, v) for d, v in zip(dates_list, vals_list) if pd.notna(v)]

    last_d = dates_list[-1] if dates_list else None
    if isinstance(existing, dict):
        def _keep(d, v):
            if d == last_d or d not in existing:
                return True
            old = existing[d]
            try:
                return float(old) != float(v)
            except (TypeError, ValueError):
                return str(old) != str(v)
        return [(d, v) for d, v in zip(dates_list, vals_list)
                if pd.notna(v) and _keep(d, v)]

    return [(d, v) for d, v in zip(dates_list, vals_list)
            if pd.notna(v) and (d not in existing or d == last_d)]


def _stale_dates_to_delete(dates_list: list, vals_list: list, existing) -> list:
    """Fechas con fila ya guardada en ind_{code} cuyo valor recién calculado
    salió inválido (None/NaN): el valor viejo quedó obsoleto (p.ej.
    best_sma_* dejó de ser válido en dist_optimal_sma_*, o se le quitó el
    benchmark a un activo en relative_strength_52w) y hay que borrar la
    fila — _pairs_to_write solo agrega/actualiza, nunca borra, así que sin
    esto la fila vieja quedaría para siempre representando un cálculo que
    ya no es válido. Solo tiene sentido cuando `existing` trae fechas ya
    guardadas (set o dict); con existing=None ya se borró todo el activo
    antes, y con existing vacío no hay nada que pueda estar obsoleto.

    dates_list vacío es un caso aparte: no es "una fecha con valor NaN"
    sino "cero fechas" (serie vacía de verdad, no una serie del largo del
    df pero con NaN) — pasa en semanal/mensual cuando la historia no
    alcanza el mínimo de barras (_zones_to_series, _bf_rsi_weekly/monthly,
    _bf_atr_weekly/monthly, _bf_dist_optimal_sma_weekly/monthly). Ahí no
    hay con qué comparar fecha por fecha, pero como `existing` en el único
    caller (backfill_indicator) es siempre la historia COMPLETA del activo
    para este código —nunca una cola parcial: el modo tail_mode usa
    existing=set() en su camino rápido—, todo lo guardado quedó obsoleto."""
    if not existing:
        return []
    if not dates_list:
        return list(existing)
    return [d for d, v in zip(dates_list, vals_list) if pd.isna(v) and d in existing]


def _write_ind_series(s, code: str, asset_id: int,
                      dates_list: list, vals_list: list,
                      existing) -> int:
    """Escribe la serie de un indicador para un activo. Devuelve filas escritas.

    existing: ver _pairs_to_write. Con None, además borra las filas previas
    del activo. NO commitea: el caller decide el tamaño de la transacción.
    """
    wide = use_wide_ind_tables() and code in _WIDE
    if wide:
        _tbl, column, cadence = _WIDE[code]

    if existing is None:
        if wide:
            _null_wide_column(s, cadence, column, asset_id=asset_id)
        else:
            t = get_ind_table(code)
            s.execute(t.delete().where(t.c.asset_id == asset_id))
    else:
        stale = _stale_dates_to_delete(dates_list, vals_list, existing)
        if stale:
            if wide:
                _null_wide_column(s, cadence, column,
                                  asset_id=asset_id, dates=stale)
            else:
                t = get_ind_table(code)
                s.execute(t.delete().where(
                    t.c.asset_id == asset_id, t.c.date.in_(stale)))
    pairs = _pairs_to_write(dates_list, vals_list, existing)
    if not pairs:
        return 0

    if wide:
        if _wide_buffer_active():
            # Rebuild bufferizado: acumular; el worker escribe la fila completa
            # una sola vez al final (sin updates repetidos → sin bloat).
            for d, v in pairs:
                _wide_buffer_append(cadence, asset_id, d, column, v)
            return len(pairs)
        # Delta: UPSERT parcial a la columna (bloat chico de la cola → autovacuum).
        return upsert_ind_cadence(
            s, cadence, [column], [(asset_id, d, v) for d, v in pairs])

    # executemany crudo con tuplas: evita construir un dict de Python por
    # fila (54M en un rebuild) y la compilación de SQLAlchemy por batch
    table = get_ind_table(code).name
    sql = db_compat.upsert_sql(
        s, table, ("asset_id", "date", "value"),
        update_cols=("value",), pk_cols=("asset_id", "date"),
        quote_table=True)
    conn = s.connection()
    written = 0
    for i in range(0, len(pairs), _IND_BATCH):
        rows = [(asset_id, d, v if isinstance(v, str) else float(v))
                for d, v in pairs[i:i + _IND_BATCH]]
        conn.exec_driver_sql(sql, rows)
        written += len(rows)
    return written


def upsert_ind_cadence(session, cadence: str, columns, rows) -> int:
    """UPSERT multi-columna en la tabla ancha de la cadencia (ind_daily/weekly/
    monthly) — escritor de la fase 2 del refactor a tablas anchas
    (docs/notes/design_ind_wide_tables.md). Todavía NADIE lo llama en el
    pipeline vivo: el cutover (fases 2-4) conecta este escritor junto con el
    lector ancho, para no dejar las tablas viejas desactualizadas en el medio.

    columns: nombres de columna a escribir (subconjunto de las de la cadencia).
    rows:    iterable de (asset_id, date, *valores) alineadas con `columns`.

    UPSERT PARCIAL: solo se insertan/actualizan `columns`; las demás columnas
    de la fila NO se tocan. Así varios códigos de la misma cadencia escriben la
    misma fila (asset_id, date) sin pisarse — la fila acumula sus columnas.
    Mismo camino crudo (executemany + upsert_sql) que _write_ind_series; el
    valor se coacciona a float salvo str/None. NO commitea."""
    from app.models.indicator_store import _WIDE_CADENCE_TABLE

    rows = list(rows)
    if not rows:
        return 0
    columns = tuple(columns)
    table = _WIDE_CADENCE_TABLE[cadence]
    sql = db_compat.upsert_sql(
        session, table, ("asset_id", "date", *columns),
        update_cols=columns, pk_cols=("asset_id", "date"), quote_table=True)
    conn = session.connection()
    written = 0
    for i in range(0, len(rows), _IND_BATCH):
        chunk = [
            (aid, d, *[(v if (v is None or isinstance(v, str)) else float(v))
                       for v in vals])
            for aid, d, *vals in rows[i:i + _IND_BATCH]
        ]
        conn.exec_driver_sql(sql, chunk)
        written += len(chunk)
    return written


# ── Buffer de escritura ancha (fase 5, opción B): rebuild sin bloat ───────────
# El rebuild escribe columna por columna (un código a la vez); en la tabla
# ancha eso ACTUALIZA cada fila N veces → N-1 tuplas muertas por fila en
# Postgres (bloat ~Nx). El buffer junta las columnas de una cadencia por
# (activo,fecha) durante el rebuild y las escribe como fila COMPLETA una sola
# vez al final del worker (la tabla ya fue truncada por el padre → inserts
# puros, sin conflictos ni tuplas muertas). Thread-local: cada worker acumula
# lo suyo. El DELTA no se bufferiza (escribe la cola per-columna; su bloat
# chico lo recupera autovacuum).
_WIDE_WRITE_BUFFER = threading.local()


def _wide_buffer_active() -> bool:
    return getattr(_WIDE_WRITE_BUFFER, "active", False)


def _wide_buffer_start() -> None:
    _WIDE_WRITE_BUFFER.active = True
    _WIDE_WRITE_BUFFER.data = {}   # {cadence: {(asset_id, date): {col: val}}}


def _wide_buffer_append(cadence: str, asset_id: int, date_, column: str,
                        value) -> None:
    (_WIDE_WRITE_BUFFER.data.setdefault(cadence, {})
     .setdefault((asset_id, date_), {})[column]) = value


def _wide_buffer_flush(session) -> None:
    """Vuelca el buffer como filas COMPLETAS (una por (activo,fecha) y
    cadencia). La tabla fue truncada por el padre → upsert_ind_cadence no
    dispara conflictos (inserts puros) → sin tuplas muertas."""
    data = getattr(_WIDE_WRITE_BUFFER, "data", None) or {}
    for cadence, rows_by_key in data.items():
        if not rows_by_key:
            continue
        cols = _WIDE_CADENCE_COLUMNS[cadence]
        rows = [(aid, d, *[colvals.get(c) for c in cols])
                for (aid, d), colvals in rows_by_key.items()]
        upsert_ind_cadence(session, cadence, cols, rows)


def _wide_buffer_clear() -> None:
    _WIDE_WRITE_BUFFER.active = False
    _WIDE_WRITE_BUFFER.data = {}


# ── Compute functions para backfill por indicador ────────────────────────────

def _bf_return_daily(df, df_w, df_m, **kw):
    return (df["close"].pct_change() * 100).round(2).tolist()

def _bf_return_monthly(df, df_w, df_m, **kw):
    return _return_vs_ref_series(df, "month_start").tolist()

def _bf_return_quarterly(df, df_w, df_m, **kw):
    return _return_vs_ref_series(df, "quarter_start").tolist()

def _bf_return_yearly(df, df_w, df_m, **kw):
    return _return_vs_ref_series(df, "year_start").tolist()

def _bf_return_52w(df, df_w, df_m, **kw):
    return _return_vs_ref_series(df, "year_back").tolist()

def _bf_dist_sma(period):
    def fn(df, df_w, df_m, **kw):
        close = df["close"]
        sma   = close.rolling(period).mean()
        return ((close - sma) / sma * 100).round(2).tolist()
    return fn

def _bf_rsi_daily(df, df_w, df_m, **kw):
    return _rsi_series(df["close"]).tolist()

def _bf_rsi_weekly(df, df_w, df_m, **kw):
    if len(df_w) >= 15:
        return pd.Series(_rsi_series(df_w["close"]).to_numpy(),
                         index=_period_index(df_w))
    return pd.Series(dtype=float)

def _bf_rsi_monthly(df, df_w, df_m, **kw):
    if len(df_m) >= 15:
        return pd.Series(_rsi_series(df_m["close"]).to_numpy(),
                         index=_period_index(df_m))
    return pd.Series(dtype=float)

def _bf_atr_daily(df, df_w, df_m, vol_cfg, **kw):
    return _atr_pct_series_v(df, vol_cfg.atr_period).tolist()

def _bf_atr_weekly(df, df_w, df_m, vol_cfg, **kw):
    if len(df_w) >= vol_cfg.atr_period * 3:
        return pd.Series(_atr_pct_series_v(df_w, vol_cfg.atr_period).to_numpy(),
                         index=_period_index(df_w))
    return pd.Series(dtype=float)

def _bf_atr_monthly(df, df_w, df_m, vol_cfg, **kw):
    if len(df_m) >= vol_cfg.atr_period * 3:
        return pd.Series(_atr_pct_series_v(df_m, vol_cfg.atr_period).to_numpy(),
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
                return dist.tolist()
            return pd.Series(dist.to_numpy(), index=_period_index(df_tf))
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


def _resolve_backfill_fn(code: str):
    """Resolución de la función de backfill por CÓDIGO (string), en un único
    punto. Las entradas de _BACKFILL_FNS son closures de fábrica (no
    picklables): un worker en otro proceso no puede recibir la función, solo
    el código — importa este módulo y resuelve acá. El módulo futuro de
    indicadores por plantilla enchufaría acá la instanciación
    "plantilla + parámetros" leída de IndicatorDefinition, sin tocar el pool."""
    return _BACKFILL_FNS.get(code)


# Códigos aptos para el camino rápido del delta: el valor de una fecha, una
# vez escrito, no cambia con barras nuevas — así que si el historial guardado
# está completo alcanza con escribir la cola (>= última fecha guardada).
#   "series": la serie no tiene huecos legítimos entre la primera y la última
#             fecha guardada; se valida contra la grilla y ante un hueco
#             histórico el activo cae al camino lento (que lo rellena).
#   "zones":  la serie tiene Nones legítimos (barras sin zona confirmada);
#             no se puede validar contra la grilla, se asume cola-solamente.
# volatility_*/atr_percentile_* (full_sample: un dato nuevo puede reclasificar
# historia vieja), trend_* (EMA recursiva sobre regime_cfg, editable por el
# admin), relative_strength_52w (depende del valor de los precios del
# benchmark, no solo de qué benchmark es) y dist_optimal_sma_* (depende de
# best_sma_*, recalculado todos los días) también entran acá, pero con una
# compuerta extra — ver _CHECKSUM_DEP_CODES — que verifica que el prefijo
# histórico recién calculado no haya cambiado antes de confiar en la cola;
# de paso, esa compuerta también detecta si se corrigieron/redescargaron
# precios ya guardados del propio activo (o del benchmark), sin depender de
# que alguien se acuerde de forzar un rebuild manual.
_DELTA_TAIL_MODE: dict[str, str] = {
    "return_daily":             "series",
    "return_monthly":           "series",
    "return_quarterly":         "series",
    "return_yearly":            "series",
    "return_52w":               "series",
    "dist_sma20":               "series",
    "dist_sma50":               "series",
    "dist_sma200":              "series",
    "rsi_daily":                "series",
    "rsi_weekly":               "series",
    "rsi_monthly":              "series",
    "dist_optimal_sma_daily":   "series",
    "dist_optimal_sma_weekly":  "series",
    "dist_optimal_sma_monthly": "series",
    "relative_strength_52w":    "series",
    "trend_daily":              "zones",
    "trend_weekly":             "zones",
    "trend_monthly":            "zones",
    "atr_percentile_daily":     "series",
    "atr_percentile_weekly":    "series",
    "atr_percentile_monthly":   "series",
    "volatility_daily":         "zones",
    "volatility_weekly":        "zones",
    "volatility_monthly":       "zones",
}


def _confirmed_empty_fast_path(stats, cached_stat) -> bool:
    """True si este activo no tiene NINGÚN valor válido para este código en
    la serie recién calculada (stats=None, ver _series_stats) Y la corrida
    anterior ya lo había confirmado (cached_stat=(None,None,0), ver
    _upsert_ind_stats_meta). Evita repetir el camino lento (dict-compare
    contra la tabla) para siempre en activos estructuralmente sin datos
    para este código — p.ej. best_sma_* inválido en dist_optimal_sma_* (no
    se encontró ningún período con >=5 toques, ver _find_best_ma) o activo
    sin benchmark configurado en relative_strength_52w. Si esta corrida
    encuentra valores válidos (stats deja de ser None), no dispara: cae al
    camino lento normal para escribir la serie recién vuelta válida."""
    return stats is None and cached_stat is not None and cached_stat[2] == 0


def _delta_tail_start(dates_list: list, stat, mode: str):
    """Decide el camino del delta para un activo.

    stat = (min_fecha, max_fecha, cantidad) de las filas ya guardadas.
    Devuelve el índice de dates_list desde el cual escribir (la cola, que
    incluye la última fecha guardada: pudo haberse calculado con un precio
    preliminar), o None si corresponde el camino lento: activo sin filas,
    hueco histórico detectado, o precios por detrás de lo guardado.
    """
    if not stat or not stat[2] or not dates_list:
        return None
    mn, mx, cnt = stat
    if mode != "zones":
        # Sin huecos ⇔ cada fecha de la grilla entre mn y mx está guardada.
        # Un NaN legítimo a mitad de serie (p.ej. benchmark sin datos en
        # relative_strength) también dispara el camino lento: correcto pero
        # más lento, solo para ese activo.
        lo = bisect.bisect_left(dates_list, mn)
        hi = bisect.bisect_right(dates_list, mx)
        if hi - lo != cnt:
            return None
    if dates_list[-1] < mx:
        return None
    return bisect.bisect_left(dates_list, mx)


# Códigos cuyo valor histórico depende de una referencia externa por activo
# (no de precios) que puede cambiar sin dejar huecos: relative_strength_52w
# se calcula contra Asset.benchmark_id, editable desde el ABM. Si cambia,
# TODA la historia guardada quedó calculada contra el benchmark viejo — el
# camino rápido de _delta_tail_start no lo detecta porque no hay huecos.
_BENCHMARK_DEP_CODES = frozenset({"relative_strength_52w"})


def _series_stats(dates_list: list, vals_list: list) -> tuple | None:
    """(min_date, max_date, count) de los valores no-nulos de la serie
    recién calculada: el estado que debería quedar en ind_{code} para este
    activo tras un backfill exitoso (cachea lo que hoy resuelve un full-scan
    de _query_tail_stats). None si no hay ningún valor válido.

    Se deriva de la serie COMPLETA recién calculada, no de un delta
    aritmético sobre lo efectivamente escrito: es seguro y uniforme en los
    4 caminos (rápido/gap/checksum/bench/force) porque la tabla, tras un
    _write_ind_series exitoso, siempre termina reflejando exactamente las
    fechas no-nulas de esta serie — mismo invariante en el que ya confía
    todo el sistema de tail-mode (_pairs_to_write sólo filtra pd.notna(v)
    en sus 3 modos)."""
    valid = [d for d, v in zip(dates_list, vals_list) if pd.notna(v)]
    return (valid[0], valid[-1], len(valid)) if valid else None


def _stale_bench_assets(bench_current: dict, bench_stored: dict) -> set:
    """Activos cuyo benchmark vigente difiere del usado en el último cálculo
    guardado (incluye activos sin fila en ind_asset_meta: primera corrida
    tras habilitar el chequeo, o activo nuevo)."""
    return {aid for aid, bid in bench_current.items()
            if bid != bench_stored.get(aid, object())}


def _upsert_ind_asset_meta(s, code: str, *, bench_by_asset: dict | None = None,
                           checksum_by_asset: dict | None = None) -> None:
    """Persiste, por activo, el metadato de invalidación de este código:
    el benchmark usado (relative_strength_52w, ver _BENCHMARK_DEP_CODES) o
    el checksum del prefijo histórico calculado (volatility_*/atr_percentile_*,
    ver _CHECKSUM_DEP_CODES). Referencia para la próxima corrida: si difiere
    de lo vigente, ese activo cae al camino lento (dict-compare) aunque su
    historial no tenga huecos."""
    data = bench_by_asset or checksum_by_asset
    if not data:
        return
    col = "benchmark_id" if bench_by_asset else "checksum"
    sql = db_compat.upsert_sql(
        s, "ind_asset_meta", ("asset_id", "code", col),
        update_cols=(col,), pk_cols=("asset_id", "code"))
    rows = [(aid, code, val) for aid, val in data.items()]
    s.connection().exec_driver_sql(sql, rows)
    s.commit()


def _upsert_ind_stats_meta(s, code: str, stats_by_asset: dict) -> None:
    """Persiste (min_date, max_date, row_count) por activo para este código
    (ver _series_stats). Función separada de _upsert_ind_asset_meta a
    propósito: bench/checksum y stats pueden tener distinto conjunto de
    asset_id para el mismo código (p.ej. un activo sin barras suficientes
    entra en bench_current pero no en stats_by_asset). Si se combinaran en
    un único INSERT multi-columna, una fila sin dato para una columna
    escribiría NULL y pisaría un valor cacheado válido de otra corrida."""
    if not stats_by_asset:
        return
    sql = db_compat.upsert_sql(
        s, "ind_asset_meta",
        ("asset_id", "code", "min_date", "max_date", "row_count"),
        update_cols=("min_date", "max_date", "row_count"),
        pk_cols=("asset_id", "code"))
    rows = [(aid, code, mn, mx, cnt) for aid, (mn, mx, cnt) in stats_by_asset.items()]
    s.connection().exec_driver_sql(sql, rows)
    s.commit()


# Códigos cuyo historial calculado puede cambiar sin que aparezca un hueco
# de calendario, por tres motivos distintos:
#   - full_sample (volatility_*/atr_percentile_*): un dato nuevo puede
#     reclasificar historia vieja (percentiles/zonas sobre toda la
#     muestra).
#   - config editable por el admin (trend_*: regime_cfg: ema_period_*,
#     slope_lookback, slope_threshold_pct, confirm_bars, nascent_bars,
#     strong_slope_multiplier): la EMA es recursiva sobre TODA la historia,
#     así que cambiar la config recalcula distinto cualquier fecha vieja,
#     no solo la cola — sin esta compuerta, un delta normal después de
#     editar la config solo actualiza la cola y deja la historia con los
#     parámetros anteriores, silenciosamente (volatility_*/atr_percentile_*
#     con vol_cfg tienen el mismo riesgo, ya cubierto acá).
#   - referencia externa cuyo VALOR puede cambiar sin avisar
#     (relative_strength_52w: depende de los precios del benchmark, no
#     solo de Asset.benchmark_id — _BENCHMARK_DEP_CODES/_stale_bench_assets
#     ya cubre el cambio de benchmark_id, pero si se redescargan/corrigen
#     los precios del benchmark vigente sin cambiar el id, esa compuerta no
#     lo detecta; el checksum sí, porque hashea el valor calculado, no la
#     referencia.
#     dist_optimal_sma_*: depende de best_sma_* — el período de SMA que
#     mejor "rebotó" históricamente (_find_best_ma), recalculado TODOS los
#     días. Si un día nuevo de precio hace que otro período gane, la
#     fórmula de toda la historia cambia (rolling(best_val) con un
#     best_val distinto), no solo la cola).
# En los cuatro casos _series_checksum permite comprobarlo sin leer lo
# guardado: si el hash del prefijo recién calculado coincide con el de la
# corrida anterior, el camino rápido de cola es seguro; si no coincide (o
# no hay checksum guardado todavía), cae al dict-compare de siempre — pero
# solo para ese activo.
_CHECKSUM_DEP_CODES = frozenset({
    "volatility_daily", "volatility_weekly", "volatility_monthly",
    "atr_percentile_daily", "atr_percentile_weekly", "atr_percentile_monthly",
    "trend_daily", "trend_weekly", "trend_monthly",
    "relative_strength_52w",
    "dist_optimal_sma_daily", "dist_optimal_sma_weekly", "dist_optimal_sma_monthly",
})


def _series_checksum(vals: list) -> str:
    """Hash estable de una serie de valores (numéricos o string; None/NaN se
    normalizan al mismo marcador para que el hash no dependa del tipo)."""
    if not vals:
        return ""
    parts = []
    for v in vals:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            parts.append("")
        else:
            parts.append(str(v))
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def _checksum_prefix(dates_list: list, vals_list: list, own_mx) -> str:
    """Hash del prefijo histórico hasta la propia última fecha válida
    (own_mx, ver _series_stats) — NO "todo menos la última posición del
    array" a ciegas.

    Necesario porque para algunos códigos (relative_strength_52w: el
    benchmark puede no tener dato reciente; en principio también
    aplicable a trend_*/volatility_* si el último tramo queda sin zona
    confirmada) la última fecha con valor válido puede quedar antes de la
    última fecha del calendario propio del activo. La comparación de la
    próxima corrida usa _delta_tail_start, que calcula
    k = bisect_left(dates_list, mx) con el mx CACHEADO — si el checksum
    se guardara con vals_list[:-1] en vez de vals_list[:k], ambos slices
    tendrían distinto largo cuando mx != última fecha del calendario, y
    el checksum nunca coincidiría con la corrida anterior aunque nada
    haya cambiado (bug real, encontrado con relative_strength_52w: ~46
    activos con checksum='lento' estable en cada delta, siempre los
    mismos, min/max/count en ind_asset_meta confirmó max_date desfasado
    varios días respecto de la corrida)."""
    k = bisect.bisect_left(dates_list, own_mx)
    return _series_checksum(vals_list[:k])


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


def _count_price_assets(s) -> int:
    """Cantidad de activos con al menos una fila de precios — barato
    (COUNT DISTINCT), suficiente para decidir el modo threads/procesos
    sin cargar precios ni el GROUP BY completo de _load_price_weights."""
    return int(s.query(sa.func.count(sa.distinct(Price.asset_id))).scalar() or 0)


def _load_price_weights(s) -> dict:
    """{asset_id: cantidad de filas de precios} — el proxy de costo del
    particionador (_partition_assets), sin cargar la tabla entera en
    memoria: en modo procesos el padre no necesita los precios (cada hijo
    carga su lote) y este conteo alcanza para armar lotes balanceados y
    el denominador del progreso."""
    rows = s.query(Price.asset_id, sa.func.count(Price.date)) \
            .group_by(Price.asset_id).all()
    return {aid: int(n) for aid, n in rows}


def _load_prices_for_assets(s, asset_ids: list) -> dict:
    """Precios de un lote (+ los benchmarks de sus activos) para un proceso
    hijo: la versión particionada de _load_all_prices — cada hijo carga
    SOLO lo suyo, que es el objetivo de memoria del diseño. Los benchmarks
    se suman porque relative_strength_52w necesita el df del benchmark,
    que puede pertenecer a otro lote (suelen ser pocos índices repetidos:
    duplicarlos entre lotes es barato).

    Select de Core (no SQL crudo): los result processors de SQLAlchemy
    tipan `date` también en sqlite, así los tests comparan fechas reales.
    """
    bench_ids = {bid for (bid,) in s.query(Asset.benchmark_id).filter(
        Asset.id.in_(asset_ids), Asset.benchmark_id.isnot(None)
    ).distinct()}
    want = sorted(set(asset_ids) | bench_ids)
    sel = (sa.select(Price.asset_id, Price.date, Price.close,
                     Price.high, Price.low)
           .where(Price.asset_id.in_(want))
           .order_by(Price.asset_id, Price.date))
    with engine.connect() as conn:
        df = pd.read_sql(sel, conn)
    df.columns = ["asset_id", "date", "close", "high", "low"]
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

# Workers de los pools masivos: derivado del hardware (~cores + margen de
# I/O). Con un thread por indicador todos se reparten el GIL y el más pesado
# termina solo al final usando un único core; con pocos workers y encolando
# los pesados primero (LPT), todos los cores quedan ocupados casi toda la corrida.
# Probado cores+6 (diag jul-2026) para el hueco de scheduling del delta real:
# empeoró (3m08s -> 3m42s). La causa no era falta de workers sino contención
# de disco en el GROUP BY...COUNT(*) de tail_stats (ver backfill_indicator):
# más threads = más de esos full-scans compitiendo por el mismo I/O a la vez.
# Vuelto a cores+2; el fix real es sacar ese prefetch de adentro del worker.
import os as _os
_POOL_WORKERS = max(3, (_os.cpu_count() or 2) + 2)


def _resolve_pool_procs() -> int:
    """Procesos del ProcessPool: config explícita, o auto = cores - 1
    (un core libre para el padre: UI, drenaje de progreso, BD), acotado
    por IND_POOL_MAX_PROCS para no reventar max_connections en máquinas
    grandes. Una config explícita (IND_POOL_PROCS > 0) NO se acota: el
    operador se hace responsable del presupuesto de conexiones."""
    from app.config import Config
    n = Config.IND_POOL_PROCS
    if n > 0:
        return n
    return max(1, min((_os.cpu_count() or 2) - 1, Config.IND_POOL_MAX_PROCS))


def _use_process_pool(n_assets: int) -> tuple[bool, int]:
    """Decide procesos vs threads para el backfill por lotes (fase 2).

    Threads cuando: sqlite (tests/stub — spawn no comparte el monkeypatch
    de la suite y un archivo sqlite con escritores concurrentes da
    SQLITE_BUSY), sys.executable no es python (Apache+mod_wsgi embebido:
    spawn no podría arrancar los hijos — degradar en vez de fallar la
    corrida en silencio), un solo proceso resuelto, o universo chico (por
    debajo del umbral el overhead de spawn+import supera el beneficio; a
    561 activos la línea base de threads ya está optimizada). PostgreSQL y
    MySQL usan el mismo camino de procesos — nunca el de sqlite."""
    from app.config import Config
    from app.services import process_pool as _pp
    if engine.dialect.name == "sqlite":
        return False, 0
    if not _pp.spawn_executable_ok():
        logger.warning("ProcessPool desactivado: sys.executable=%s no es un "
                       "intérprete de Python (¿mod_wsgi embebido?) — usando "
                       "threads. Configurar multiprocessing.set_executable "
                       "para habilitarlo.", sys.executable)
        return False, 0
    n_procs = _resolve_pool_procs()
    if n_procs <= 1 or n_assets < Config.IND_POOL_MIN_ASSETS:
        return False, 0
    return True, n_procs


def _cost_rank(code: str) -> float:
    """Peso estimado de un indicador para ordenar la cola (pesados primero).

    Aproximación: largo de la serie del timeframe × costo del algoritmo.
    No necesita ser exacta — LPT es robusto a errores de estimación."""
    if code.endswith(("_monthly", "_m")):
        tf = 1.0
    elif code.endswith(("_weekly", "_w")):
        tf = 4.0
    else:
        tf = 21.0            # daily y códigos sin sufijo (returns, dist_sma, RS)

    if code.startswith("volatility"):
        algo = 4.0           # ATR + percentiles + loop de confirmación + duración
    elif code.startswith("atr_percentile"):
        algo = 2.5
    elif code.startswith("best_"):
        algo = 2.0           # 16 períodos de MA probados
    elif code.startswith("trend"):
        algo = 1.5
    else:
        algo = 1.0
    return tf * algo


def _lpt_order(codes: list, measured: dict) -> list:
    """Ordena la cola de workers: pesados primero (LPT).

    measured: {code: segundos de la última corrida DEL MISMO MODO — el
    caller decide si es delta o rebuild completo, ver migración 0056, no
    mezclar duraciones de un modo para ordenar el otro}. Los códigos SIN
    medición (indicadores nuevos, o primera corrida de ese modo) van
    primero por seguridad: si resultan pesados quedan bien priorizados, y
    si son livianos no cuesta nada. Sin ninguna medición cae a la
    heurística _cost_rank."""
    if not measured:
        return sorted(codes, key=_cost_rank, reverse=True)
    return sorted(codes, key=lambda c: measured.get(c, float("inf")), reverse=True)


# Lotes por worker en el pool por lotes de activos: más lotes que workers da
# balanceo dinámico (un lote que resulta pesado no deja al resto esperando),
# pero cada (lote × código) paga queries scopeadas propias — el piso de
# activos por lote evita que ese overhead domine en universos chicos.
_BATCH_FACTOR      = 4
_MIN_BATCH_ASSETS  = 25


def _n_batches(n_assets: int, workers: int) -> int:
    """Cantidad de lotes para particionar n_assets activos entre `workers`."""
    if n_assets <= 0:
        return 0
    by_floor = n_assets // _MIN_BATCH_ASSETS
    return max(1, min(workers * _BATCH_FACTOR, by_floor if by_floor else 1))


def _partition_assets(asset_ids: list, weights: dict, n_batches: int) -> list[list]:
    """Particiona activos en lotes de rangos CONTIGUOS de asset_id,
    balanceados por peso acumulado (peso = largo de la historia de precios,
    proxy del costo de cómputo del activo).

    Contiguos a propósito, no greedy-LPT: las tablas ind_{code} tienen PK
    (asset_id, date) y los N workers escriben la MISMA tabla a la vez — con
    lotes contiguos, los activos vecinos en la PK caen en el mismo lote y
    los next-key/gap locks de InnoDB de workers distintos casi no se tocan
    (solo en las fronteras entre rangos). Un reparto por peso puro
    intercalaría vecinos de PK entre lotes y convertiría cada frontera de
    activo en superficie de deadlock.

    Garantiza: cada activo en exactamente un lote, sin lotes vacíos (si hay
    menos activos que lotes, devuelve menos lotes), determinístico."""
    n_batches = min(n_batches, len(asset_ids))
    if n_batches <= 0:
        return []
    ordered = sorted(asset_ids)
    if n_batches == 1:
        return [ordered]
    remaining_total = float(sum(weights.get(a) or 0 for a in ordered))
    batches: list[list] = []
    i = 0
    for b in range(n_batches):
        remaining_batches = n_batches - b
        if remaining_batches == 1:
            batches.append(ordered[i:])
            break
        target = remaining_total / remaining_batches
        # dejar al menos un activo para cada lote restante
        max_i = len(ordered) - (remaining_batches - 1)
        batch: list = []
        w = 0.0
        while i < max_i and (not batch or w < target):
            batch.append(ordered[i])
            w += weights.get(ordered[i]) or 0
            i += 1
        batches.append(batch)
        remaining_total -= w
    return batches


def _slice_by_assets(d: dict | None, asset_ids: list) -> dict:
    """Sub-dict con solo los activos del lote: lo único que viaja pickleado
    a un proceso hijo (mandar los dicts completos multiplicaría el payload
    por N lotes sin necesidad)."""
    if not d:
        return {}
    return {aid: d[aid] for aid in asset_ids if aid in d}


def _force_reset_ind_tables(s, codes: list) -> list[dict]:
    """Reset del rebuild (force) IZADO al padre del pool: TRUNCATE de cada
    ind_{code} + limpieza de su caché de ind_asset_meta, UNA vez y ANTES de
    lanzar los workers. Con partición por activos ningún worker puede
    truncar (borraría lo que ya escribieron los otros lotes). Mismo criterio
    de crash-safety que tenía backfill_indicator adentro: si la corrida
    muere a mitad, la tabla queda truncada+parcial pero el caché AUSENTE
    (no con un valor viejo) — el próximo delta cae al camino lento para ese
    código en vez de confiar en un min/max/count que ya no corresponde a la
    tabla real. wipe_table emite el TRUNCATE histórico en MySQL y cae a
    DELETE en sqlite (tests).

    Trade-off asumido de izar el reset (documentado a propósito): las
    tablas de TODOS los códigos quedan vacías durante toda la corrida (el
    pool viejo truncaba cada tabla recién al arrancar su worker), y un
    rebuild interrumpido deja vacía la historia completa hasta re-correr.

    Devuelve los códigos que NO pudieron resetearse (p.ej. metadata lock
    del TRUNCATE): el caller DEBE excluirlos de la corrida — backfillear
    en force sobre una tabla no truncada mezclaría filas nuevas con
    historia vieja no recalculada."""
    failed: list[dict] = []
    wide_on = use_wide_ind_tables()
    wiped_wide: set = set()   # tablas de cadencia ya truncadas (una vez c/u)
    for code in codes:
        try:
            if wide_on and code in _WIDE:
                # En la ancha los N códigos de una cadencia comparten tabla:
                # TRUNCAR la tabla de cadencia UNA vez (codes = todos los
                # técnicos en el rebuild completo) y limpiar el meta por código.
                wide_name = _WIDE_CADENCE_TABLE[_WIDE[code][2]]
                if wide_name not in wiped_wide:
                    db_compat.wipe_table(s, wide_name)
                    wiped_wide.add(wide_name)
            else:
                t = get_ind_table(code)
                db_compat.wipe_table(s, t.name)
            s.execute(sa.text("DELETE FROM ind_asset_meta WHERE code = :code"),
                      {"code": code})
            s.commit()
        except Exception as exc:
            logger.warning("Reset de rebuild falló code=%s: %s", code, exc)
            s.rollback()
            failed.append({"code": code, "error": f"reset: {exc}"})
    return failed


def _query_tail_stats(session, code: str) -> dict:
    """{asset_id: (min_date, max_date, count)} cacheado en ind_asset_meta
    para este código (migración 0055), mantenido por backfill_indicator en
    cada corrida exitosa (ver _series_stats/_upsert_ind_stats_meta y el
    DELETE junto al TRUNCATE en force). Reemplaza el full-scan que antes
    hacía un GROUP BY asset_id + COUNT(*) sobre ind_{code} — el COUNT
    impedía el loose index scan que MIN/MAX solos permitirían."""
    return {aid: (mn, mx, cnt) for aid, mn, mx, cnt in session.execute(
        sa.select(IndAssetMeta.asset_id, IndAssetMeta.min_date,
                  IndAssetMeta.max_date, IndAssetMeta.row_count)
        .where(IndAssetMeta.code == code, IndAssetMeta.row_count.isnot(None))
    ).fetchall()}


def _precompute_all_tail_stats(session, codes: list, force: bool) -> dict:
    """tail_stats de todos los códigos tail-mode, antes de lanzar el pool de
    workers. Históricamente esto era secuencial para evitar que varios
    full-scans de ind_{code} compitieran por el mismo disco a la vez (medido:
    3m08s -> 3m42s con más workers); desde que _query_tail_stats lee de un
    caché indexado por PK en ind_asset_meta en vez de escanear ind_{code},
    ya no hay full-scan que evitar, pero se deja secuencial por simplicidad
    (el costo real hoy es solo N lookups baratos por PK)."""
    if force:
        return {}
    out: dict = {}
    for code in codes:
        if not _DELTA_TAIL_MODE.get(code):
            continue
        out[code] = _query_tail_stats(session, code)
    return out


def backfill_indicator(code: str, *, force: bool = False, asset_tick=None,
                       price_cache: dict | None = None,
                       best_sma_cache: dict | None = None,
                       df_w_cache: dict | None = None,
                       df_m_cache: dict | None = None,
                       precomputed_tail_stats: dict | None = None,
                       asset_ids: list | None = None,
                       skip_force_reset: bool = False,
                       defer_meta: bool = False) -> dict:
    """
    Backfill histórico de un indicador específico para todos los activos.
    Escribe en la tabla ind_{code}.

    asset_ids: lote explícito de activos (partición por activos del pool por
    lotes). Además de acotar la iteración, scopea las queries de metadatos
    (benchmark/checksum de ind_asset_meta) al lote — sin scope, cada lote
    traería y re-escribiría los metadatos de TODOS los activos.
    skip_force_reset: el caller ya trunca ind_{code} y limpió ind_asset_meta
    (ver _force_reset_ind_tables — con partición por activos el reset va en
    el padre, un lote no puede truncar sin borrar el trabajo de los demás).
    defer_meta: no upsertear ind_asset_meta acá; devolver los dicts en el
    resultado (clave "meta") para que el caller los consolide — con N lotes
    escribiendo el mismo código, el único escritor de ind_asset_meta debe
    ser el padre (evita contención/deadlocks sin necesidad).

    force=True trunca la tabla del indicador y la reconstruye completa.
    Si el indicador tiene full_sample=True (estadísticos sobre toda la serie,
    como percentiles de ATR), en delta la serie se recalcula completa pero
    solo se escriben los valores que cambiaron respecto de lo guardado.
    Para los códigos de _DELTA_TAIL_MODE el delta usa el camino rápido:
    si el historial guardado del activo no tiene huecos, escribe solo la
    cola (>= última fecha guardada) sin prefetchear las fechas existentes.

    df_w_cache / df_m_cache permiten reutilizar resamples precalculados entre
    los workers (sin ellos, cada indicador resamplearía los mismos precios).

    precomputed_tail_stats: {asset_id: (min_date, max_date, count)} ya
    calculado por el caller (ver _precompute_all_tail_stats). Se lee de
    ind_asset_meta (migración 0055), cacheado por este mismo método en la
    corrida anterior — reemplaza el full-scan que antes hacía un
    GROUP BY asset_id + COUNT(*) sobre ind_{code} (COUNT impedía el loose
    index scan que MIN/MAX solos permiten).
    """
    compute_fn = _resolve_backfill_fn(code)
    if compute_fn is None:
        return {"inserted": 0, "skipped": True, "reason": "no_compute_fn"}

    s = get_session()
    scoped = asset_ids is not None

    # full_sample (percentiles/zonas sobre toda la muestra): en delta la serie
    # se recalcula ENTERA igual, pero en vez de borrar y reescribir todo se
    # comparan los valores guardados y se escriben solo las diferencias.
    defn = s.query(IndicatorDefinition).filter(IndicatorDefinition.code == code).first()
    full_sample = bool(defn and defn.full_sample)

    t          = get_ind_table(code)
    regime_cfg = _get_regime_config()
    vol_cfg    = _get_volatility_config()
    # Si hay price_cache (camino normal, paralelo), iterar sus asset_id en
    # vez de volver a consultar Asset.id: price_cache es la misma fuente
    # que usó el caller para calcular n_assets/total_work del progreso —
    # activos sin precio descargado todavía quedan afuera de las dos
    # cuentas por igual (antes: aparecían en el loop vía asset_ids pero no
    # en el denominador, mostrando p.ej. "497/495" en el panel).
    if scoped:
        pass                       # lote explícito del pool por lotes
    elif price_cache is not None:
        asset_ids = list(price_cache.keys())
    else:
        asset_ids = [r[0] for r in s.query(Asset.id).all()]

    # Camino rápido del delta (ver _DELTA_TAIL_MODE): el prefetch pasa de
    # traer millones de (fecha[, valor]) a 3 agregados por activo, y por
    # activo se escribe solo la cola en lugar de filtrar la serie entera.
    tail_mode  = None if force else _DELTA_TAIL_MODE.get(code)
    # tail_eligible, a diferencia de tail_mode, NO se anula en force: incluso
    # en un rebuild completo queremos recalcular el caché de stats para que
    # el próximo delta ya tenga camino rápido disponible (ver _series_stats
    # y _upsert_ind_stats_meta, al final de esta función).
    tail_eligible     = code in _DELTA_TAIL_MODE
    stats_by_asset: dict = {}
    tail_stats: dict = {}
    if tail_mode:
        if precomputed_tail_stats is not None:
            tail_stats = precomputed_tail_stats
        else:
            tail_stats = _query_tail_stats(s, code)

    # Invalidación por referencia externa (ver _BENCHMARK_DEP_CODES): un
    # activo con benchmark cambiado cae al dict-compare aunque no haya huecos.
    needs_bench   = code in _BENCHMARK_DEP_CODES
    bench_current: dict = {}
    bench_stale:   set  = set()
    if needs_bench:
        bench_q = s.query(Asset.id, Asset.benchmark_id)
        if scoped:
            bench_q = bench_q.filter(Asset.id.in_(asset_ids))
        bench_current = dict(bench_q.all())
        if tail_mode:
            bench_sel = sa.select(
                IndAssetMeta.asset_id, IndAssetMeta.benchmark_id
            ).where(IndAssetMeta.code == code)
            if scoped:
                bench_sel = bench_sel.where(IndAssetMeta.asset_id.in_(asset_ids))
            bench_stored = dict(s.execute(bench_sel).fetchall())
            bench_stale = _stale_bench_assets(bench_current, bench_stored)

    # Invalidación por checksum (ver _CHECKSUM_DEP_CODES): full_sample sin
    # prefetch completo — se compara el hash del prefijo recién calculado
    # contra el de la corrida anterior antes de confiar en la cola.
    needs_checksum      = code in _CHECKSUM_DEP_CODES
    needs_dict_fallback = needs_bench or needs_checksum
    checksum_stored:  dict = {}
    checksum_by_asset: dict = {}
    if needs_checksum and tail_mode:
        cs_sel = sa.select(
            IndAssetMeta.asset_id, IndAssetMeta.checksum
        ).where(IndAssetMeta.code == code)
        if scoped:
            cs_sel = cs_sel.where(IndAssetMeta.asset_id.in_(asset_ids))
        checksum_stored = dict(s.execute(cs_sel).fetchall())

    if force and not skip_force_reset:
        # TRUNCATE en lugar de DELETE por activo: instantáneo y sin undo log
        # (millones de filas). Trade-offs asumidos: la tabla queda vacía
        # mientras se rellena, y si la corrida falla hay que re-correr el
        # rebuild (TRUNCATE es DDL, no se rollbackea). wipe_table emite el
        # TRUNCATE histórico en MySQL; en sqlite (tests) cae a DELETE.
        if use_wide_ind_tables() and code in _WIDE:
            # En la ancha no se puede TRUNCATE por un solo código (comparte
            # tabla con los otros de la cadencia): se nullea su columna.
            _tbl, column, cadence = _WIDE[code]
            _null_wide_column(s, cadence, column,
                              asset_ids=(asset_ids if scoped else None))
        else:
            db_compat.wipe_table(s, t.name)
        # Limpia el caché de ind_asset_meta (benchmark_id/checksum/stats) en
        # el MISMO commit que el TRUNCATE, no al final: si el proceso se cae
        # a mitad del rebuild, la tabla queda truncada+parcial pero el caché
        # queda AUSENTE (no con un valor viejo) — el próximo delta cae al
        # camino lento para todo ese código en vez de confiar en un
        # min/max/count que ya no corresponde a la tabla real.
        s.execute(sa.text("DELETE FROM ind_asset_meta WHERE code = :code"), {"code": code})
        s.commit()

    inserted = 0
    rows_since_commit = 0

    # Diagnóstico del camino rápido del delta: cuántos activos lo usaron y
    # por qué cayeron al lento los demás (hueco, checksum, benchmark).
    # "empty" es distinto de "gap": no es un hueco real en el calendario,
    # es que el indicador no tiene NINGÚN valor válido para ese activo por
    # su propia naturaleza (best_sma_* inválido en dist_optimal_sma_*,
    # activo sin benchmark en relative_strength_52w, historia insuficiente
    # para el período del indicador, etc.) — no cuenta como "lento" ni en
    # el log ni en el panel del Centro de Datos (ver __pc__: más abajo),
    # para no confundirlo con huecos reales que sí ameritan revisión.
    path_counts = {"fast": 0, "gap": 0, "checksum": 0, "bench": 0, "empty": 0}
    # Mismo diagnóstico pero con el asset_id puntual, no solo el conteo —
    # para cazar activos que caen al lento de forma estable corrida tras
    # corrida (sospecha de hueco real en su propia historia, no solo
    # caché frío) sin tener que adivinar cuáles son.
    slow_asset_ids: dict[str, list] = {"gap": [], "checksum": [], "bench": [], "empty": []}

    for chunk_start in range(0, len(asset_ids), _EXISTING_CHUNK):
        chunk = asset_ids[chunk_start:chunk_start + _EXISTING_CHUNK]

        # Fechas existentes de todo el chunk en una sola query (evita 1 por activo);
        # para full_sample se trae también el valor, para escribir solo cambios.
        # Con tail_mode no se prefetchea nada: alcanza con tail_stats.
        existing_by_asset: dict = {}
        if not force and not tail_mode:
            # value IS NOT NULL: en la tabla ancha una fila puede tener ESTA
            # columna en NULL (la escribió otro código); "existente" = la
            # columna del código tiene valor. En per-código (sin value NULL)
            # es no-op.
            if full_sample:
                for aid, d, v in s.execute(
                    sa.select(t.c.asset_id, t.c.date, t.c.value)
                    .where(t.c.asset_id.in_(chunk), t.c.value.isnot(None))
                ).fetchall():
                    existing_by_asset.setdefault(aid, {})[d] = v
            else:
                for aid, d in s.execute(
                    sa.select(t.c.asset_id, t.c.date)
                    .where(t.c.asset_id.in_(chunk), t.c.value.isnot(None))
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
            dates_list, vals_list = _series_dates_values(values, df)
            if tail_eligible:
                # se guarda siempre (force, cola o dict-compare) para que el
                # próximo delta tenga tail_stats al día sin full-scan (ver
                # _series_stats: se deriva de la serie completa recién
                # calculada, no de lo efectivamente escrito este run)
                stats = _series_stats(dates_list, vals_list)
                # (None, None, 0) es un valor cacheable válido, no "sin
                # info": confirma que este activo no tiene NINGÚN valor
                # válido para este código (p.ej. best_sma_* inválido en
                # dist_optimal_sma_*, o activo sin benchmark en
                # relative_strength_52w) — ver el chequeo de abajo, que
                # evita repetir el camino lento en cada delta si la
                # próxima corrida confirma que sigue vacío.
                stats_by_asset[asset_id] = stats if stats is not None else (None, None, 0)
            if needs_checksum and stats is not None:
                # se guarda siempre (force, cola o dict-compare) para que el
                # próximo delta arranque con el checksum al día — con la
                # posición de la propia última fecha válida (ver
                # _checksum_prefix), no con [:-1] a ciegas. Si stats es
                # None no hay última fecha válida propia: ese activo va
                # por "empty", nunca llega a comparar este checksum.
                checksum_by_asset[asset_id] = _checksum_prefix(dates_list, vals_list, stats[1])
            # force: la tabla ya fue truncada → set() vacío escribe todo
            # sin el DELETE por activo del modo existing=None
            if force:
                existing = set()
            elif tail_mode:
                reason = None
                k = None
                cached_stat = tail_stats.get(asset_id)
                if needs_bench and asset_id in bench_stale:
                    reason = "bench"
                elif stats is None:
                    # esta corrida no tiene NINGÚN valor válido: no es un
                    # hueco de calendario (_delta_tail_start no aplica,
                    # está pensada para series con al menos un valor), es
                    # que el indicador no tiene nada que mostrar para este
                    # activo — motivo "empty", no "gap".
                    reason = "empty"
                    if _confirmed_empty_fast_path(stats, cached_stat):
                        k = len(dates_list)
                else:
                    k = _delta_tail_start(dates_list, cached_stat, tail_mode)
                    if k is None:
                        reason = "gap"
                    elif needs_checksum and (
                        _series_checksum(vals_list[:k]) != checksum_stored.get(asset_id)
                    ):
                        k = None
                        reason = "checksum"
                if k is None:
                    path_counts[reason] += 1
                    slow_asset_ids[reason].append(asset_id)
                    # activo nuevo, con huecos, benchmark o checksum cambiado:
                    # camino lento solo para él (dict-compare si necesita
                    # comparar valores, set si solo hay que rellenar huecos)
                    if needs_dict_fallback:
                        existing = {d: v for d, v in s.execute(
                            sa.select(t.c.date, t.c.value).where(
                                t.c.asset_id == asset_id, t.c.value.isnot(None)))}
                    else:
                        existing = {d for (d,) in s.execute(
                            sa.select(t.c.date).where(
                                t.c.asset_id == asset_id, t.c.value.isnot(None)))}
                else:
                    path_counts["fast"] += 1
                    dates_list, vals_list = dates_list[k:], vals_list[k:]
                    existing = set()
            else:
                existing = existing_by_asset.get(asset_id, {} if full_sample else set())
            written   = _write_ind_series(s, code, asset_id,
                                          dates_list, vals_list, existing)
            inserted          += written
            rows_since_commit += written
            # Commit por volumen: junta ~_COMMIT_ROWS filas por transacción
            if rows_since_commit >= _COMMIT_ROWS:
                s.commit()
                rows_since_commit = 0

            if asset_tick:
                asset_tick()

        s.commit()   # cierra el lote al fin de cada chunk de activos
        rows_since_commit = 0

    result = {"inserted": inserted, "code": code, "path_counts": path_counts,
              "slow_asset_ids": slow_asset_ids}
    if defer_meta:
        # El caller consolida y persiste (ver docstring). Dicts de tipos
        # simples (int/str/date/tuplas): el contrato ya es apto para volver
        # pickleado desde un proceso hijo en la fase 2 del ProcessPool.
        result["meta"] = {
            "bench_by_asset":    bench_current if needs_bench else None,
            "checksum_by_asset": checksum_by_asset if needs_checksum else None,
            "stats_by_asset":    stats_by_asset if tail_eligible else None,
        }
        return result

    if needs_bench:
        _upsert_ind_asset_meta(s, code, bench_by_asset=bench_current)
    if needs_checksum:
        _upsert_ind_asset_meta(s, code, checksum_by_asset=checksum_by_asset)
    if tail_eligible:
        _upsert_ind_stats_meta(s, code, stats_by_asset)

    return result


# Progreso vivo del modo procesos (fase 3): marcador de fin de la Queue IPC
# y tamaño del batch de ticks del hijo. El hijo acumula cuentas por código y
# flushea cada _TICK_FLUSH activos procesados — a 10k activos × 24 códigos
# serían ~240k mensajes sin batchear; con 50, ~4800.
_IPC_STOP = "__ind_pump_stop__"
_TICK_FLUSH = 50


def _make_ipc_queue():
    """(manager, queue) para el progreso vivo del modo procesos. La cola es
    un Manager().Queue() — un proxy PICKLABLE que cruza a los hijos por el
    submit (una mp.Queue cruda solo se comparte por herencia). El caller
    cierra el manager en su finally. Punto de inyección para los tests, que
    lo reemplazan por una queue.Queue en proceso (sin levantar un Manager
    real)."""
    import multiprocessing as _mp
    mgr = _mp.get_context("spawn").Manager()
    return mgr, mgr.Queue()


# Reintentos ante deadlock (1213) / lock timeout (1205) por (lote, código):
# con partición por activos, N workers escriben CONCURRENTEMENTE las mismas
# tablas ind_{code} (el pool viejo tenía un único escritor por tabla) — la
# clase de contención que CLAUDE.md documenta como esperable con retry
# obligatorio (patrón de fundamental_service._fund_worker).
_MAX_LOCK_RETRIES = 3


def _backfill_batch_worker(batch_idx: int, batch_asset_ids: list, codes: list,
                           force: bool = False, asset_tick=None,
                           price_cache: dict | None = None,
                           best_sma_cache: dict | None = None,
                           df_w_cache: dict | None = None,
                           df_m_cache: dict | None = None,
                           tail_stats_by_code: dict | None = None) -> dict:
    """Worker del pool por LOTES de activos: calcula todos los códigos de
    backfill para su lote y devuelve un resultado agregable por el padre
    (dicts de tipos simples — el contrato ya es apto para cruzar a un
    proceso hijo en la fase 2 del ProcessPool; hoy corre en threads y
    recibe los cachés completos por referencia, con partición real solo de
    la iteración vía asset_ids).

    asset_tick(code): una llamada por (código, activo) procesado — el padre
    agrega los contadores por código entre lotes.
    El reset del force (TRUNCATE) NO ocurre acá: lo hace el padre una vez
    por código antes del pool (_force_reset_ind_tables). Los metadatos de
    ind_asset_meta tampoco se escriben acá (defer_meta): los consolida el
    padre como único escritor.
    Un error en un código no aborta el lote: se anota y se sigue con el
    resto (mismo criterio que el pool histórico por indicador)."""
    import random as _random
    import time as _time
    from sqlalchemy.exc import OperationalError
    from app.database import Session as _DbSession
    out = {"batch": batch_idx, "inserted": 0, "per_code": {}, "errors": []}
    # Rebuild + wide: bufferizar las escrituras y volcarlas como fila completa
    # al final (sin bloat). El delta (force=False) NO se bufferiza.
    wide_buffered = force and use_wide_ind_tables()
    try:
        if wide_buffered:
            _wide_buffer_start()
        if force:
            # Bulk-load: sin validación FK/unique por fila durante el rebuild
            _set_bulk_load_checks(get_session(), False)
        for code in codes:
            t0 = _time.monotonic()
            res = None
            emitted = 0
            for attempt in range(_MAX_LOCK_RETRIES + 1):
                seen = 0

                def _code_tick(c=code):
                    # En reintentos, los activos ya contados no re-emiten:
                    # el dn por código del panel es acumulativo entre lotes
                    # y un doble tick lo pasaría del total (dn > tn).
                    nonlocal seen, emitted
                    seen += 1
                    if seen > emitted:
                        emitted = seen
                        asset_tick(c)

                try:
                    res = backfill_indicator(
                        code, force=force,
                        asset_tick=_code_tick if asset_tick else None,
                        price_cache=price_cache, best_sma_cache=best_sma_cache,
                        df_w_cache=df_w_cache, df_m_cache=df_m_cache,
                        precomputed_tail_stats=(tail_stats_by_code or {}).get(code),
                        asset_ids=batch_asset_ids,
                        skip_force_reset=True, defer_meta=True)
                    break
                except OperationalError as exc:
                    # SIEMPRE rollback antes de decidir: la transacción quedó
                    # envenenada (en PG cualquier statement posterior daría
                    # InFailedSqlTransaction; en SQLAlchemy 2.0,
                    # PendingRollbackError) y el resto de los códigos del
                    # lote comparten esta misma sesión thread-local.
                    get_session().rollback()
                    if (attempt < _MAX_LOCK_RETRIES
                            and db_compat.is_retryable_lock_error(exc)):
                        # Deadlock (1213) / lock timeout (1205) contra otro
                        # worker del pool: N lotes escriben las mismas
                        # tablas ind_* — reintentar la transacción completa
                        # es seguro (upserts idempotentes, meta diferida).
                        # Mismo patrón que fundamental_service._fund_worker.
                        _time.sleep(0.2 * (attempt + 1) + _random.uniform(0, 0.2))
                        continue
                    logger.warning("Backfill error lote=%d code=%s: %s",
                                   batch_idx, code, exc)
                    out["errors"].append({"code": code, "error": str(exc)})
                    break
                except Exception as exc:
                    # rollback también acá: descarta el chunk parcial sin
                    # commitear del código fallido (el pool viejo lo hacía
                    # implícito con el remove() al morir su worker) y deja
                    # la sesión usable para el próximo código del lote.
                    get_session().rollback()
                    logger.warning("Backfill error lote=%d code=%s: %s",
                                   batch_idx, code, exc)
                    out["errors"].append({"code": code, "error": str(exc)})
                    break
            if res is not None:
                res["seconds"] = round(_time.monotonic() - t0, 1)
                out["inserted"] += res.get("inserted", 0)
                out["per_code"][code] = res
        if wide_buffered:
            # Volcar el buffer: fila completa por (activo,fecha), una sola vez.
            for attempt in range(_MAX_LOCK_RETRIES + 1):
                try:
                    _wide_buffer_flush(get_session())
                    get_session().commit()
                    break
                except OperationalError as exc:
                    get_session().rollback()
                    if (attempt < _MAX_LOCK_RETRIES
                            and db_compat.is_retryable_lock_error(exc)):
                        _time.sleep(0.2 * (attempt + 1) + _random.uniform(0, 0.2))
                        continue
                    logger.warning("Flush ancho lote=%d falló: %s", batch_idx, exc)
                    out["errors"].append({"code": "wide_flush", "error": str(exc)})
                    break
                except Exception as exc:
                    get_session().rollback()
                    logger.warning("Flush ancho lote=%d falló: %s", batch_idx, exc)
                    out["errors"].append({"code": "wide_flush", "error": str(exc)})
                    break
    finally:
        if wide_buffered:
            _wide_buffer_clear()
        if force:
            # Restaurar SIEMPRE antes de devolver la conexión al pool
            _set_bulk_load_checks(get_session(), True)
        _DbSession.remove()
    return out


def _process_batch_task(batch_idx: int, batch_asset_ids: list, codes: list,
                        force: bool,
                        best_sma_slice: dict | None,
                        tail_stats_slices: dict | None,
                        progress_q=None) -> dict:
    """Tarea del PROCESO HIJO (fase 2 del ProcessPool): carga los precios
    de SU lote (+ benchmarks), resamplea localmente y delega en
    _backfill_batch_worker — la misma unidad de trabajo que valida la
    suite en modo threads.

    Contrato del boundary de proceso: recibe y devuelve SOLO tipos simples
    picklables y chicos (ids, dicts de fechas/floats); los DataFrames nunca
    viajan — nacen y mueren en el hijo. progress_q (fase 3): Queue IPC por
    la que el hijo emite cuentas por código {code: n} batcheadas cada
    _TICK_FLUSH activos, que el padre drena hacia el panel. Nunca deja
    escapar una excepción: los errores viajan como strings en el dict (las
    excepciones de SQLAlchemy pueden fallar al des-picklearse y volverse
    errores opacos en el padre)."""
    from app.database import Session as _DbSession
    pending: dict = {}
    acc = [0]

    def _emit(code):
        pending[code] = pending.get(code, 0) + 1
        acc[0] += 1
        if acc[0] >= _TICK_FLUSH:
            try:
                progress_q.put(dict(pending))
            except Exception:
                pass
            pending.clear()
            acc[0] = 0

    try:
        s = get_session()
        price_cache = _load_prices_for_assets(s, batch_asset_ids)
        df_w_cache = {aid: _resample_ohlc(price_cache[aid], "W")
                      for aid in batch_asset_ids if aid in price_cache}
        df_m_cache = {aid: _resample_ohlc(price_cache[aid], "M")
                      for aid in batch_asset_ids if aid in price_cache}
        return _backfill_batch_worker(
            batch_idx, batch_asset_ids, codes, force,
            _emit if progress_q is not None else None, price_cache,
            best_sma_slice, df_w_cache, df_m_cache, tail_stats_slices)
    except Exception as exc:
        logger.warning("Tarea de lote %d falló: %s", batch_idx, exc)
        return {"batch": batch_idx, "inserted": 0, "per_code": {},
                "errors": [{"code": f"lote-{batch_idx}", "error": str(exc)}]}
    finally:
        # flush de la cola pendiente ANTES de retornar: garantiza que todas
        # las cuentas del hijo están en la Queue cuando el padre pone _STOP
        if progress_q is not None and pending:
            try:
                progress_q.put(dict(pending))
            except Exception:
                pass
        _DbSession.remove()


def backfill_all_indicator_values(progress_cb=None, *, force: bool = False,
                                  price_cache: dict | None = None) -> dict:
    """
    Backfill histórico paralelizado por LOTES DE ACTIVOS.

    Fase 1 del plan ProcessPool (partición por activos): la unidad de
    trabajo es un lote de activos × todos los códigos de backfill, hoy
    ejecutada en threads — el mismo eje que tendrán los procesos hijos en
    la fase 2, así la corrección del particionado se valida con la
    infraestructura actual. El padre trunca (force), precalcula tail-stats,
    reparte lotes balanceados por largo de historia, agrega el progreso por
    código entre lotes y consolida ind_asset_meta y diagnósticos como único
    escritor. price_cache permite reutilizar precios ya cargados por el
    caller.
    """
    import threading as _th
    s    = get_session()
    defs = s.query(IndicatorDefinition).filter(
        IndicatorDefinition.keep_history.is_(True)
    ).order_by(IndicatorDefinition.id).all()
    hist = [d.code for d in defs if d.code in _BACKFILL_FNS]
    # Duraciones medidas del modo que corresponde: delta y rebuild completo
    # tienen costos muy distintos para el mismo código (ver migración 0056).
    # Con partición por activos ya no ordenan workers: ordenan los códigos
    # DENTRO de cada lote (pesados primero, ver _lpt_order más abajo).
    measured = {
        d.code: (d.last_rebuild_seconds if force else d.last_backfill_seconds)
        for d in defs if d.code in _BACKFILL_FNS
        and (d.last_rebuild_seconds if force else d.last_backfill_seconds)
    }

    n_indicators = len(hist)
    if not n_indicators:
        return {"total": 0, "success": 0, "inserted": 0, "errors": []}
    all_codes = set(hist)   # para success al final (hist puede achicarse)

    # Pesos de partición ANTES de decidir el modo: en procesos el padre NO
    # carga los precios (cada hijo carga su lote) — el conteo de filas por
    # activo alcanza para el umbral, los lotes y el denominador del
    # progreso, sin pagar la tabla entera en memoria.
    if price_cache is not None:
        # caller ya cargó los precios (camino threads): pesos gratis del df
        weights = {aid: len(df) for aid, df in price_cache.items()}
        n_assets = len(weights)
        use_procs, n_procs = _use_process_pool(n_assets)
    else:
        # sin cache: decidir el modo con un COUNT barato ANTES de cargar
        # nada — en procesos el padre no carga precios, y en threads los
        # pesos salen del cache que se carga igual (sin el GROUP BY extra).
        n_assets = _count_price_assets(s)
        use_procs, n_procs = _use_process_pool(n_assets)
        if use_procs:
            weights = _load_price_weights(s)          # para particionar
        else:
            if progress_cb:
                progress_cb(0, 1, "Cargando precios en memoria...")
            logger.info("Pre-cargando precios en memoria...")
            price_cache = _load_all_prices(s)
            weights = {aid: len(df) for aid, df in price_cache.items()}
            n_assets = len(price_cache)               # autoritativo
    total_work = n_indicators * n_assets

    best_sma_cache = _load_best_sma_cache(s)
    logger.info("Backfill por lotes: %d activos, modo %s", n_assets,
                f"{n_procs} procesos" if use_procs else "threads")

    # Resamples W/M una sola vez, compartidos por referencia entre los
    # workers-thread; en modo procesos cada hijo resamplea SOLO su lote
    # (acá no se paga nada).
    df_w_cache = df_m_cache = None
    if not use_procs:
        if progress_cb:
            progress_cb(0, 1, "Precalculando resamples semanales y mensuales...")
        df_w_cache = {aid: _resample_ohlc(df, "W") for aid, df in price_cache.items()}
        df_m_cache = {aid: _resample_ohlc(df, "M") for aid, df in price_cache.items()}

    # force: reset IZADO al padre, una vez por código y ANTES del pool —
    # con partición por activos un worker no puede truncar (ver
    # _force_reset_ind_tables). Un código cuyo reset falló queda EXCLUIDO
    # de la corrida: backfillear en force sobre una tabla no truncada
    # mezclaría filas nuevas con historia vieja.
    reset_errors: list[dict] = []
    if force:
        if progress_cb:
            progress_cb(0, 1, "Vaciando tablas de indicadores (rebuild)...")
        reset_errors = _force_reset_ind_tables(s, hist)
        if reset_errors:
            bad = {e["code"] for e in reset_errors}
            hist = [c for c in hist if c not in bad]
            total_work = len(hist) * n_assets

    # tail_stats de todos los códigos tail-mode, SECUENCIAL y antes del pool
    # (ver _precompute_all_tail_stats): evita que varios indicadores
    # full-scaneen su tabla al mismo tiempo cuando arranquen los workers.
    if progress_cb:
        progress_cb(0, 1, "Calculando estadísticas de historial (tail-mode)...")
    tail_stats_by_code = _precompute_all_tail_stats(s, hist, force)

    # Partición por activos: lotes balanceados por largo de historia
    asset_ids = list(weights.keys())
    batches   = _partition_assets(
        asset_ids, weights,
        _n_batches(n_assets, n_procs if use_procs else _POOL_WORKERS))

    from app.database import Session as _DbSession
    _DbSession.remove()   # libera la conexión principal antes de lanzar workers

    inserted = 0
    errors: list[dict] = list(reset_errors)
    failed_codes: set = {e["code"] for e in reset_errors}

    # Contador total + contador por código, compartidos entre lotes: varios
    # workers avanzan el MISMO código a la vez, así que el "dn" por código
    # del panel se agrega acá (ya no es local de un worker por indicador).
    _assets_done  = 0
    _done_by_code = {c: 0 for c in hist}
    _lock         = _th.Lock()

    # Diagnóstico (jul-2026): número de worker (0..N-1) estable por hilo,
    # asignado la primera vez que ese hilo llama a _tick. Se ve en el panel
    # para confirmar cuántos workers reales están activos en paralelo
    # (ver _POOL_WORKERS) y detectar huecos de scheduling.
    _worker_slots: dict[int, int] = {}

    def _worker_slot() -> int:
        ident = _th.get_ident()
        with _lock:
            if ident not in _worker_slots:
                _worker_slots[ident] = len(_worker_slots)
            return _worker_slots[ident]

    def _bump(code, delta=1, tag=""):
        # Avanza los contadores agregados por código y emite la fila del
        # panel. Lo llaman el _tick de los workers-thread (delta=1) y el
        # thread bomba que drena la Queue IPC del modo procesos (delta=N).
        nonlocal _assets_done
        with _lock:
            _assets_done += delta
            _done_by_code[code] = _done_by_code.get(code, 0) + delta
            n, k = _assets_done, _done_by_code[code]
        if progress_cb:
            suffix = f" {tag}" if tag else ""
            progress_cb(n, total_work, f"{code}: {k}/{n_assets}{suffix}")

    def _tick(code):
        _bump(code, 1, f"w{_worker_slot()}")

    # Orden de códigos dentro de cada lote: pesados primero por duración
    # MEDIDA de la corrida anterior (nuevos primero; heurística solo en la
    # primera corrida de una instalación). Todos los lotes comparten el
    # orden — los códigos caros terminan parejo entre lotes.
    hist = _lpt_order(hist, measured)

    # Agregación por código entre lotes: duraciones (suma), path_counts
    # (suma), slow_asset_ids (concatenación) y metadatos de ind_asset_meta
    # (unión de dicts por activo — los lotes son disjuntos). El padre es el
    # único que persiste y el único que emite __pc__/log por código: sin
    # este merge, el panel mostraría solo los conteos del último lote.
    durations: dict = {}
    agg_pc:    dict = {}
    agg_slow:  dict = {}
    agg_meta:  dict = {}

    def _merge_code_result(code: str, res: dict) -> None:
        if res.get("seconds") is not None:
            durations[code] = round(durations.get(code, 0) + res["seconds"], 1)
        pc = res.get("path_counts")
        if pc:
            tgt = agg_pc.setdefault(code, {})
            for k, v in pc.items():
                tgt[k] = tgt.get(k, 0) + v
        for k, ids in (res.get("slow_asset_ids") or {}).items():
            if ids:
                agg_slow.setdefault(code, {}).setdefault(k, []).extend(ids)
        meta = res.get("meta") or {}
        tgt = agg_meta.setdefault(code, {"bench_by_asset": {},
                                         "checksum_by_asset": {},
                                         "stats_by_asset": {}})
        for key in ("bench_by_asset", "checksum_by_asset", "stats_by_asset"):
            if meta.get(key):
                tgt[key].update(meta[key])

    def _consume_batch(out: dict) -> None:
        nonlocal inserted
        inserted += out.get("inserted", 0)
        for err in out.get("errors", []):
            failed_codes.add(err["code"])
            if err["code"] not in all_codes:
                # entrada 'lote-N': el lote entero no corrió (catch-all del
                # hijo) — afecta a todos los códigos para esos activos
                failed_codes.update(hist)
            errors.append(err)
        for code, res in out.get("per_code", {}).items():
            _merge_code_result(code, res)

    def _drain(futures: dict) -> None:
        for future in as_completed(futures):
            bi = futures[future]
            try:
                out = future.result()
            except Exception as exc:
                # En procesos, BrokenProcessPool cae acá para TODOS los
                # lotes en vuelo cuando un hijo muere sin excepción Python
                # (OOM-killer/segfault): cada lote queda anotado como no
                # corrido y la corrida sigue re-ejecutable por delta.
                logger.warning("Backfill future error lote=%d: %s", bi, exc)
                failed_codes.update(hist)
                errors.append({"code": f"lote-{bi}", "error": str(exc)})
                continue
            _consume_batch(out)

    if batches and use_procs:
        from app.config import BASE_DIR, Config
        from app.services import process_pool as _pp

        # Progreso vivo por activo (fase 3): los hijos no comparten los
        # closures de _tick — emiten cuentas por código en una Queue IPC
        # que un thread bomba del padre drena hacia _bump (mismas filas del
        # panel que el modo threads). El manager es un punto de inyección
        # para los tests (evita levantar un proceso Manager real).
        #
        # Sin progress_cb (job diario desatendido) NO se arma el canal: el
        # Manager, la bomba y los puts de los hijos serían puro desperdicio
        # (los contadores que alimentan solo se leen bajo `if progress_cb`).
        mgr = pq = pump = None
        if progress_cb is not None:
            mgr, pq = _make_ipc_queue()

            def _pump():
                while True:
                    try:
                        msg = pq.get()
                    except (EOFError, OSError):
                        break
                    if msg == _IPC_STOP:
                        break
                    if isinstance(msg, dict):
                        for code, delta in msg.items():
                            try:
                                _bump(code, delta)
                            except Exception:
                                logger.warning("bomba de progreso falló", exc_info=True)

            pump = _th.Thread(target=_pump, name="ind-progress-pump", daemon=True)
            pump.start()
        try:
            with _pp.make_executor(min(len(batches), n_procs), str(BASE_DIR),
                                   Config.IND_CHILD_DB_POOL,
                                   Config.LOG_LEVEL) as pool:
                futures = {
                    pool.submit(_process_batch_task, i, batch, hist, force,
                                _slice_by_assets(best_sma_cache, batch),
                                {c: _slice_by_assets(st, batch)
                                 for c, st in tail_stats_by_code.items()},
                                pq): i
                    for i, batch in enumerate(batches)
                }
                if progress_cb:
                    # Mensaje especial para pre-poblar todos los workers en el UI
                    progress_cb(0, total_work, f"__init__:{n_assets}:{','.join(hist)}")
                _drain(futures)
        finally:
            # Cada paso del cleanup en su propio try/except: si el proceso
            # Manager murió, pq.put/pump.join NO deben saltear el shutdown ni
            # enmascarar una excepción de la corrida (la consolidación de
            # ind_asset_meta viene DESPUÉS y no debe abortarse por el cleanup
            # del canal de progreso).
            if pump is not None:
                # Todos los hijos volvieron (flushearon su cola pendiente
                # antes de retornar) → el STOP queda último en la Queue FIFO.
                try:
                    pq.put(_IPC_STOP)
                except Exception:
                    logger.warning("no se pudo cerrar la cola de progreso",
                                   exc_info=True)
                try:
                    pump.join(timeout=30)
                except Exception:
                    pass
            if mgr is not None:
                try:
                    mgr.shutdown()
                except Exception:
                    pass
    elif batches:
        with _TPE(max_workers=min(len(batches), _POOL_WORKERS)) as pool:
            futures = {
                pool.submit(_backfill_batch_worker, i, batch, hist, force,
                            _tick, price_cache, best_sma_cache,
                            df_w_cache, df_m_cache, tail_stats_by_code): i
                for i, batch in enumerate(batches)
            }
            if progress_cb:
                # Mensaje especial para pre-poblar todos los workers en el UI
                # (las filas del panel siguen siendo por código; el tag [wN]
                # identifica al worker de lote que lo avanzó último)
                progress_cb(0, total_work, f"__init__:{n_assets}:{','.join(hist)}")
            _drain(futures)

    # Consolidación en el padre (único escritor de ind_asset_meta) + log y
    # __pc__ por código con los conteos COMPLETOS sumados entre lotes. Solo
    # entran los lotes que terminaron bien ese código: un (lote, código)
    # fallido deja sus metadatos sin actualizar → ese subconjunto cae al
    # camino lento en el próximo delta (mismo criterio de seguridad que el
    # worker por indicador, que ante error no upserteaba nada).
    s2 = get_session()
    for code in hist:
        try:
            meta = agg_meta.get(code)
            if meta:
                if meta["bench_by_asset"]:
                    _upsert_ind_asset_meta(s2, code, bench_by_asset=meta["bench_by_asset"])
                if meta["checksum_by_asset"]:
                    _upsert_ind_asset_meta(s2, code, checksum_by_asset=meta["checksum_by_asset"])
                if meta["stats_by_asset"]:
                    _upsert_ind_stats_meta(s2, code, meta["stats_by_asset"])
            pc = agg_pc.get(code)
            if pc and sum(pc.values()):
                logger.info(
                    "Backfill %s (%.1fs): rápido=%d gap=%d checksum=%d bench=%d empty=%d",
                    code, durations.get(code, 0),
                    pc["fast"], pc["gap"], pc["checksum"], pc["bench"], pc["empty"],
                )
                slow_ids = agg_slow.get(code) or {}
                if any(slow_ids.values()):
                    logger.info(
                        "Backfill %s activos no-rápidos — gap=%s checksum=%s bench=%s empty=%s",
                        code, slow_ids.get("gap"), slow_ids.get("checksum"),
                        slow_ids.get("bench"), slow_ids.get("empty"),
                    )
                # Mensaje especial (mismo mecanismo que __init__:) para que
                # el panel del Centro de Datos muestre cuántos activos
                # cayeron al camino lento (gap/checksum/bench) por código
                # — "empty" queda afuera a propósito, no es un hueco real
                # que amerite revisión (ver comentario en path_counts).
                if progress_cb:
                    progress_cb(_assets_done, total_work,
                                f"__pc__:{code}:{pc['fast']}:{pc['gap']}:"
                                f"{pc['checksum']}:{pc['bench']}")
            # Fila final autoritativa por código: dn agregado + costo real
            # (t= suma de segundos entre lotes). Devuelve al panel el costo
            # POR CÓDIGO que el eje invertido le quitó al span inicio→fin
            # (todas las filas abren en la primera ola y cierran en la
            # última), y corrige cualquier tick final desordenado.
            if progress_cb and code in durations:
                progress_cb(_assets_done, total_work,
                            f"{code}: {_done_by_code.get(code, 0)}/{n_assets}"
                            f" t={durations[code]}")
        except Exception as exc:
            # Un fallo consolidando UN código no aborta el resto (sin esto,
            # una caída en el primer upsert dejaba a los 24 códigos sin
            # meta/diagnóstico y el panel mostraba éxito total en verde).
            logger.warning("Consolidación de meta falló code=%s: %s", code, exc)
            try:
                s2.rollback()
            except Exception:
                pass
            failed_codes.add(code)
            errors.append({"code": code, "error": f"consolidación: {exc}"})

    # Persistir las duraciones medidas: ordenan los códigos dentro de los
    # lotes de la próxima corrida del MISMO modo (ver migración 0056). Con
    # partición por activos la duración por código es la SUMA entre lotes
    # (proxy del costo total del código, no wall-clock de un worker) — el
    # orden relativo, que es lo que LPT necesita, se preserva.
    if durations:
        try:
            attr = "last_rebuild_seconds" if force else "last_backfill_seconds"
            for d in s2.query(IndicatorDefinition).filter(
                    IndicatorDefinition.code.in_(list(durations))).all():
                setattr(d, attr, durations[d.code])
            s2.commit()
        except Exception:
            logger.warning("No se pudieron guardar las duraciones de backfill",
                           exc_info=True)

    # errors: UNA entrada por código, como en el pool viejo — los
    # consumidores (panel '{X}/{Y} OK', acumuladores de price_service)
    # cuentan len(errors) contra el total de códigos; con N lotes, un error
    # sistémico en un código generaría N entradas e inflaría la cuenta.
    # Las entradas 'lote-N' (lote entero caído) se conservan tal cual.
    deduped: list[dict] = []
    seen_codes: dict = {}
    for e in errors:
        c = e.get("code")
        if c in all_codes:
            if c in seen_codes:
                seen_codes[c] += 1
                continue
            seen_codes[c] = 1
        deduped.append(dict(e))
    for e in deduped:
        n = seen_codes.get(e.get("code"), 1)
        if n > 1:
            e["error"] += f" (x{n} lotes)"
    errors = deduped

    n_failed = len(failed_codes & all_codes)
    return {"total": n_indicators, "success": n_indicators - n_failed,
            "inserted": inserted, "errors": errors}


def backfill_asset_history(asset_id: int) -> dict:
    """Reconstruye la historia completa de indicadores (keep_history) de UN activo.

    Pensado para cuando la historia de precios de un activo nace o se
    reconstruye (activo nuevo, sintético recién creado, redescarga completa):
    borra las filas ind_* del activo y las recalcula desde cero, sin pasar por
    el backfill masivo del Centro de Datos.

    Requiere que los valores vigentes (best_sma_*) ya estén calculados —
    llamar después de compute_current_indicators().
    """
    s = get_session()
    rows = s.query(Price.date, Price.close, Price.high, Price.low).filter(
        Price.asset_id == asset_id
    ).order_by(Price.date.asc()).all()
    if len(rows) < _MIN_ROWS:
        return {"inserted": 0}

    df   = pd.DataFrame(rows, columns=["date", "close", "high", "low"])
    df_w = _resample_ohlc(df, "W")
    df_m = _resample_ohlc(df, "M")

    regime_cfg = _get_regime_config()
    vol_cfg    = _get_volatility_config()
    hist = [
        d.code for d in s.query(IndicatorDefinition).filter(
            IndicatorDefinition.keep_history.is_(True)
        ).order_by(IndicatorDefinition.id).all()
        if d.code in _BACKFILL_FNS
    ]

    inserted = 0
    for code in hist:
        values = _BACKFILL_FNS[code](
            df=df, df_w=df_w, df_m=df_m,
            regime_cfg=regime_cfg, vol_cfg=vol_cfg,
            session=s, asset_id=asset_id,
            price_cache=None, best_sma_cache=None,
        )
        dates_list, vals_list = _series_dates_values(values, df)
        inserted += _write_ind_series(s, code, asset_id,
                                      dates_list, vals_list, existing=None)
        s.commit()   # un activo: transacción por indicador

    logger.info("Backfill por activo id=%d: %d valores en %d indicadores",
                asset_id, inserted, len(hist))
    return {"inserted": inserted}


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

    today           = df.iloc[-1]["date"]
    _last_close_raw = df.iloc[-1]["close"]
    last_close      = None if pd.isna(_last_close_raw) else float(_last_close_raw)
    if len(df) >= 2 and not pd.isna(df.iloc[-2]["close"]):
        prev_close = float(df.iloc[-2]["close"])
    else:
        prev_close = None

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
        if bm_last and bm_ref and bm_last[0] is not None and bm_ref[0] is not None:
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
    if use_wide_ind_tables():
        # Agrupar por cadencia y escribir la fila COMPLETA (una vez por
        # cadencia) en vez de 24 upserts por-columna → sin updates repetidos.
        from collections import defaultdict as _dd
        _by_cad = _dd(dict)
        for code, value in _current_inds.items():
            _tbl, _column, _cadence = _WIDE[code]
            _by_cad[_cadence][_column] = (
                None if isinstance(value, float) and pd.isna(value) else value)
        for _cadence, _colvals in _by_cad.items():
            _cols = _WIDE_CADENCE_COLUMNS[_cadence]
            upsert_ind_cadence(
                s, _cadence, _cols,
                [(asset_id, today, *[_colvals.get(c) for c in _cols])])
    else:
        for code, value in _current_inds.items():
            _upsert_ind(s, code, asset_id, today, value)

    # Escritura en current_indicator_values (keep_history=False): batch en 1
    # round-trip en vez de uno por código (todos comparten la misma tabla).
    _upsert_current_ind_batch(s, asset_id, [
        ("best_sma_d", best_sma_d), ("best_ema_d", best_ema_d),
        ("best_sma_w", best_sma_w), ("best_ema_w", best_ema_w),
        ("best_sma_m", best_sma_m), ("best_ema_m", best_ema_m),
        ("drawdown_current", round(dd_current, 2)),
        ("drawdown_max1",    round(dd_max1, 2) if dd_max1 is not None else None),
        ("drawdown_max2",    round(dd_max2, 2) if dd_max2 is not None else None),
        ("drawdown_max3",    round(dd_max3, 2) if dd_max3 is not None else None),
        ("resistance_pct",   ind_resist_pct),
        ("support_pct",      ind_support_pct),
    ])

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

    pending = 0
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
            # Savepoint por activo: un error rollbackea SOLO este activo sin
            # perder los anteriores; el commit real (fsync) sale por lote
            with s.begin_nested():
                if val is not None and pd.notna(val):
                    if current_only:
                        v_num = float(val) if isinstance(val, (int, float, np.floating)) else None
                        v_str = str(val) if v_num is None else None
                        _upsert_current_ind(s, asset_id, code, value_num=v_num, value_str=v_str)
                    else:
                        _upsert_ind(s, code, asset_id, asset_date, val)
            pending += 1
            if pending >= _EXISTING_CHUNK:
                s.commit()
                pending = 0
        except Exception as exc:
            logger.warning("Error valor vigente code=%s asset_id=%d: %s", code, asset_id, exc)
            if not s.is_active:
                # sesión invalidada (no fue solo el savepoint): descartar lote
                s.rollback()
                pending = 0
            if error_collector is not None:
                with collector_lock:
                    error_collector.setdefault(asset_id, []).append(f"{code}: {exc}")
        finally:
            if asset_tick:
                asset_tick()

    s.commit()   # cierra el último lote pendiente


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
    # LPT: pesados primero (ver _cost_rank)
    current_codes = sorted(current_codes, key=_cost_rank, reverse=True)
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

    with _TPE(max_workers=min(n_ind, _POOL_WORKERS)) as pool:
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
        from app.services import group_score_service
        group_score_service.compute_group_scores(
            group_score_service.get_default_target_date())
    except Exception as exc:
        logger.warning("Error refrescando scores de grupo: %s", exc)


def _announce_worker_union(progress_cb, s, n_assets: int,
                           current_first: bool) -> tuple[list, list]:
    """Anuncia la unión de workers de ambas fases (vigentes + backfill) al
    inicio del proceso, para que la lista del panel no crezca al cambiar de
    fase. Los __init__ de cada fase después no duplican (setdefault).
    Devuelve (cur_codes, hist_codes) para que el caller arme una barra de
    progreso combinada entre las dos fases (ver _run_current_and_backfill)."""
    defs = s.query(IndicatorDefinition).filter(
        IndicatorDefinition.keep_history.is_(True)
    ).order_by(IndicatorDefinition.id).all()
    hist = [d.code for d in defs if d.code in _BACKFILL_FNS]
    cur  = sorted(_CURRENT_ONLY_CODES, key=_cost_rank, reverse=True)
    codes = (cur + hist) if current_first else (hist + cur)
    progress_cb(0, len(codes) * n_assets,
                f"__init__:{n_assets}:{','.join(codes)}")
    return cur, hist


def _run_current_and_backfill(progress_cb, *, force: bool) -> dict:
    """recompute_current_indicators + backfill_all_indicator_values en
    secuencia, con una barra de progreso COMBINADA entre las dos fases.

    Cada fase reporta su propio (cur, total) interno; sin combinarlos, la
    barra de progreso salta hacia atrás al pasar de una fase a la otra
    (fase 2 arranca en 0 con un total más chico) — el usuario lo notó como
    "se resetea". cb1/cb2 remapean cada fase al mismo total combinado,
    con la fase 2 offseteada por el tamaño de la fase 1."""
    s = get_session()
    if progress_cb:
        progress_cb(0, 1, "Cargando precios en memoria...")
    price_cache_full = _load_all_prices(s)
    snap_caches      = _derive_recent_caches(price_cache_full)
    n_assets         = len(price_cache_full)

    cb1 = cb2 = progress_cb
    if progress_cb:
        cur_codes, hist_codes = _announce_worker_union(progress_cb, s, n_assets,
                                                        current_first=True)
        combined_total = (len(cur_codes) + len(hist_codes)) * n_assets
        phase1_total   = len(cur_codes) * n_assets

        def cb1(cur, tot, label=""):
            progress_cb(cur, combined_total, label)

        def cb2(cur, tot, label=""):
            progress_cb(phase1_total + cur, combined_total, label)

    r1 = recompute_current_indicators(progress_cb=cb1,
                                 codes=_CURRENT_ONLY_CODES,
                                 preloaded_caches=snap_caches)
    # En modo procesos cada hijo carga los precios de SU lote: retener acá
    # el price_cache completo (que la fase 1 ya usó y terminó) sería el pico
    # de memoria que la partición quería evitar, encima del de los hijos.
    # Soltar las referencias del padre antes del backfill; los pesos de
    # partición salen de un COUNT liviano (price_cache=None). En threads el
    # backfill sí reutiliza el cache cargado. La fase de vigentes cargando
    # toda la tabla sigue siendo el techo de memoria del padre (diferido a
    # una etapa futura del plan — ver docs/notes).
    if _use_process_pool(n_assets)[0]:
        del price_cache_full, snap_caches
        r2 = backfill_all_indicator_values(progress_cb=cb2, force=force)
    else:
        r2 = backfill_all_indicator_values(progress_cb=cb2, force=force,
                                           price_cache=price_cache_full)
    _refresh_group_scores()
    errors = r1["errors"] + r2["errors"]
    total  = r1["total"]
    return {"total": total, "success": max(total - len(errors), 0), "errors": errors}


def update_indicator_history(progress_cb=None) -> dict:
    """Recomputa los indicadores vigentes sin historia (best_*, drawdowns, S/R)
    y completa huecos históricos de los demás (backfill delta).

    Los precios se cargan una sola vez, y el valor de hoy de los indicadores
    con historia lo escribe el backfill (no se computa dos veces)."""
    return _run_current_and_backfill(progress_cb, force=False)


def rebuild_indicator_history(progress_cb=None) -> dict:
    """Borra y recalcula toda la historia de indicadores técnicos desde cero.

    Orden igual que el delta: primero los vigentes (incluye best_sma_d/w/m),
    después el backfill. dist_optimal_sma_* depende de best_sma_* (lee
    best_sma_cache desde current_indicator_values) — calcularlo antes de
    recomputar best_sma_* usaría el valor de la corrida anterior."""
    return _run_current_and_backfill(progress_cb, force=True)


def reconcile_ind_asset_meta(progress_cb=None, *, codes: list[str] | None = None) -> dict:
    """Reconstruye desde cero, código por código, TODO lo cacheado en
    ind_asset_meta para el camino rápido del delta: benchmark_id, checksum
    y min_date/max_date/row_count.

    Red de seguridad para el único caso que backfill_indicator no
    autocorrige: alguien edita una tabla ind_{code} a mano (p.ej. consola
    SQL admin, ver nota en IndAssetMeta) sin pasar por los servicios,
    dejando el caché desincronizado de la tabla real.

    Cada columna se trata distinto según se pueda o no verificar contra una
    fuente de verdad independiente:
    - min_date/max_date/row_count SÍ se pueden recalcular sin ambigüedad:
      se leen del full-scan real (GROUP BY asset_id + MIN/MAX/COUNT) sobre
      ind_{code}, el mismo cálculo que hacía la vieja _query_tail_stats.
    - benchmark_id/checksum NO: no hay forma de derivarlos sin volver a
      correr el cómputo completo del indicador (equivalente a un rebuild
      force). En vez de adivinar un valor, se BORRAN — mismo principio de
      seguridad que el resto del sistema, ausente fuerza el camino lento
      y nunca hace creer que un activo está al día cuando no lo está. El
      próximo delta normal recalcula esos ~7 activos-código por el camino
      lento (dict-compare) y los vuelve a guardar bien, una única vez.

    No requiere recalcular ningún valor de indicador (a diferencia de un
    rebuild force): solo lee y corrige el metadato, así que es mucho más
    barata que un rebuild completo aunque pague el mismo costo del full-scan
    que el delta ya no paga.

    Firma compatible con progress_cb=None y limpieza de sesión propia para
    poder colgarla más adelante de una tarea programada en background (mismo
    patrón que backfill_all_indicator_values/_daily_update_job)."""
    from app.database import Session as _DbSession
    s = get_session()
    codes = list(codes) if codes else list(_DELTA_TAIL_MODE)
    errors: list[dict] = []
    try:
        for i, code in enumerate(codes):
            try:
                t = get_ind_table(code)
                real = {aid: (mn, mx, cnt) for aid, mn, mx, cnt in s.execute(
                    sa.select(t.c.asset_id, sa.func.min(t.c.date),
                              sa.func.max(t.c.date), sa.func.count())
                    .group_by(t.c.asset_id)
                ).fetchall()}
                # Reset total del código: benchmark_id/checksum no se pueden
                # recalcular sin recomputar el indicador entero (ver
                # docstring), así que se borran en vez de arrastrar un valor
                # viejo potencialmente corrupto. min_date/max_date/row_count
                # sí se recalculan al toque, abajo.
                s.execute(sa.text("DELETE FROM ind_asset_meta WHERE code = :code"),
                          {"code": code})
                s.commit()
                _upsert_ind_stats_meta(s, code, real)
            except Exception as exc:
                s.rollback()
                logger.warning("Reconciliación ind_asset_meta code=%s: %s", code, exc)
                errors.append({"code": code, "error": str(exc)})
            if progress_cb:
                progress_cb(i + 1, len(codes), code)
        total = len(codes)
        return {"total": total, "success": total - len(errors), "errors": errors}
    finally:
        _DbSession.remove()


# ── Funciones públicas para gráficos ─────────────────────────────────────────

def _strip_zone_internals(zones: list) -> list:
    """Quita las claves internas (_i0/_i1) antes de mandar zonas al browser."""
    return [{k: v for k, v in z.items() if not k.startswith("_")} for z in zones]


def get_regime_zones_for_chart(df: "pd.DataFrame", cfg=None) -> dict:
    if cfg is None:
        cfg = _get_regime_config()
    sl, st_pct, cb = cfg.slope_lookback, cfg.slope_threshold_pct, cfg.confirm_bars
    nb, sm = cfg.nascent_bars, cfg.strong_slope_multiplier
    df_w = _resample_ohlc(df, "W")
    df_m = _resample_ohlc(df, "M")
    return {
        "D": _strip_zone_internals(_compute_regime_zones(df,   cfg.ema_period_d, sl, st_pct, cb, nb, sm)),
        "W": _strip_zone_internals(_compute_regime_zones(df_w, cfg.ema_period_w, sl, st_pct, cb, nb, sm)),
        "M": _strip_zone_internals(_compute_regime_zones(df_m, cfg.ema_period_m, sl, st_pct, cb, nb, sm)),
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
        "D": _strip_zone_internals(_compute_vol_zones(df,   **vol_args)),
        "W": _strip_zone_internals(_compute_vol_zones(df_w, **vol_args)),
        "M": _strip_zone_internals(_compute_vol_zones(df_m, **vol_args)),
    }


def get_dd_events_for_chart(df: "pd.DataFrame", cfg=None) -> list:
    if cfg is None:
        cfg = _get_drawdown_config()
    return _compute_dd_events(df, cfg.min_depth_pct)


def get_market_map_data() -> dict:
    """Promedios de tendencia por grupo, leídos de group_scores
    (última fecha disponible). Los calcula group_score_service.compute_group_scores,
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
