"""Paridad de la vectorización de zonas (confirmación por rachas + segmentos).

Las funciones _ref_* son copias LITERALES de la implementación anterior
(barra por barra). Si la versión vectorizada diverge en cualquier serie
aleatoria, estos tests fallan.
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.services.technical_service import (
    _classify_duration, _compute_regime_zones, _compute_vol_zones,
    _confirm_codes, _date_str, _regime_detail, _zones_to_series,
)


# ── Referencia: máquina de confirmación barra por barra (implementación vieja) ──

def _ref_confirm(raw_codes, confirm_bars):
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
    return confirmed


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
@pytest.mark.parametrize("confirm_bars", [1, 2, 3, 5])
def test_confirmacion_paridad_series_aleatorias(seed, confirm_bars):
    rng = np.random.RandomState(seed)
    # series con ceros intercalados y rachas de largo variable
    raw = rng.choice([0, 1, 2, 3, 4], size=800,
                     p=[0.15, 0.2, 0.3, 0.2, 0.15]).astype(np.int8)
    esperado = _ref_confirm(raw, confirm_bars)
    obtenido = _confirm_codes(raw, confirm_bars)
    assert np.array_equal(obtenido, esperado)


def test_confirmacion_bordes():
    assert np.array_equal(_confirm_codes(np.array([], dtype=np.int8), 3),
                          np.array([], dtype=np.int8))
    solo_ceros = np.zeros(10, dtype=np.int8)
    assert np.array_equal(_confirm_codes(solo_ceros, 3), solo_ceros)
    # quirk histórico: con confirm_bars=1 la 1ª ocurrencia NO confirma
    raw = np.array([2, 1, 1], dtype=np.int8)
    assert np.array_equal(_confirm_codes(raw, 1), _ref_confirm(raw, 1))


# ── Referencia: constructores de zonas viejos (copias literales) ──────────────

def _ref_regime_zones(df, ema_period, slope_lookback, slope_threshold_pct,
                      confirm_bars, nascent_bars=20, strong_slope_multiplier=2.0):
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
    confirmed = _ref_confirm(raw_codes, confirm_bars)
    _CODE = [None, "lateral", "bullish", "bearish"]
    dates_arr = df["date"].values
    zones = []
    for i in range(len(raw_codes)):
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
                    slope_threshold_pct, nascent_bars, strong_slope_multiplier)
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
            slope_threshold_pct, nascent_bars, strong_slope_multiplier)
    for z in zones:
        z.pop("_bars", None)
        z.pop("_slope_last", None)
    return zones


def _ref_vol_zones(df, atr_period, confirm_bars, pct_low, pct_high, pct_extreme,
                   dur_short_pct, dur_long_pct):
    from app.services.technical_service import _atr_series
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
    confirmed = _ref_confirm(raw_codes, confirm_bars)
    _CODE = [None, "baja", "normal", "alta", "extrema"]
    dates_arr = df["date"].values
    valid_sorted = np.sort(valid.values)
    n_valid = len(valid_sorted)
    atr_pct_ranks = np.full(n, np.nan)
    if n_valid > 0:
        valid_mask = ~np.isnan(atr_vals)
        atr_pct_ranks[valid_mask] = (
            np.searchsorted(valid_sorted, atr_vals[valid_mask]) / n_valid * 100)
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
            zones.append({"start": dt, "end": dt, "vol_regime": vr, "_bars": 1,
                          "atr_pct": round(atr_pct_rank, 1) if atr_pct_rank is not None else None})
        else:
            zones[-1]["_bars"] += 1
            if atr_pct_rank is not None:
                zones[-1]["atr_pct"] = round(atr_pct_rank, 1)
    if not zones:
        return []
    zones[-1]["end"] = _date_str(dates_arr[-1])
    dur_hist = {"baja": [], "normal": [], "alta": [], "extrema": []}
    for z in zones[:-1]:
        dur_hist[z["vol_regime"]].append(z["_bars"])
    for z in zones:
        z["dur_regime"] = _classify_duration(
            z["_bars"], dur_hist[z["vol_regime"]], dur_short_pct, dur_long_pct)
        z.pop("_bars", None)
    return zones


def _random_walk_df(n, seed, vol=1.0):
    rng = np.random.RandomState(seed)
    close = 100 + rng.randn(n).cumsum() * vol
    close = np.abs(close) + 5
    return pd.DataFrame({
        "date":  [date(2015, 1, 1) + timedelta(days=i) for i in range(n)],
        "close": close,
        "high":  close * (1 + rng.rand(n) * 0.02),
        "low":   close * (1 - rng.rand(n) * 0.02),
    })


def _sin_internas(zones):
    return [{k: v for k, v in z.items() if not k.startswith("_")} for z in zones]


@pytest.mark.parametrize("seed", [0, 7, 42])
def test_regime_zones_paridad(seed):
    df = _random_walk_df(400, seed)
    ref   = _ref_regime_zones(df, ema_period=20, slope_lookback=10,
                              slope_threshold_pct=0.5, confirm_bars=3)
    nuevo = _compute_regime_zones(df, ema_period=20, slope_lookback=10,
                                  slope_threshold_pct=0.5, confirm_bars=3)
    assert _sin_internas(nuevo) == ref


@pytest.mark.parametrize("seed", [0, 7, 42])
def test_vol_zones_paridad(seed):
    df = _random_walk_df(400, seed, vol=2.0)
    kw = dict(atr_period=14, confirm_bars=3, pct_low=25, pct_high=75,
              pct_extreme=90, dur_short_pct=33, dur_long_pct=67)
    ref   = _ref_vol_zones(df, **kw)
    nuevo = _compute_vol_zones(df, **kw)
    assert _sin_internas(nuevo) == ref


def test_zones_to_series_camino_por_indices():
    df = pd.DataFrame({"date": [date(2025, 1, i) for i in range(1, 6)],
                       "close": [1, 2, 3, 4, 5]})
    zones = [{"start": "2025-01-01", "end": "2025-01-02", "v": "a", "_i0": 0, "_i1": 1},
             {"start": "2025-01-04", "end": "2025-01-05", "v": "b", "_i0": 3, "_i1": 4}]
    assert _zones_to_series(zones, df, "v") == ["a", "a", None, "b", "b"]
