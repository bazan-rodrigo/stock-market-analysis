"""Paridad entre los cálculos persistidos (pandas) y los del gráfico (JS).

Las funciones _ref_* son espejos 1:1 del JavaScript de chart_callbacks
(window._lwc.emaW / .rsi / .atr). Si alguien cambia un lado sin el otro,
estos tests gritan.
"""
import math

import numpy as np
import pandas as pd
import pytest

from app.services.technical_service import _atr_series, _rsi_series, _wilder_smooth


# ── Espejos del JS del gráfico ────────────────────────────────────────────────

def _ref_emaw(vals, n):
    """Espejo de window._lwc.emaW: warmup SMA, luego alpha = 1/n."""
    out = [float("nan")] * len(vals)
    if len(vals) < n:
        return out
    out[n - 1] = sum(vals[:n]) / n
    a = 1.0 / n
    for i in range(n, len(vals)):
        out[i] = a * vals[i] + (1 - a) * out[i - 1]
    return out


def _ref_rsi_js(close, n):
    """Espejo de window._lwc.rsi."""
    g, l = [0.0], [0.0]
    for i in range(1, len(close)):
        d = close[i] - close[i - 1]
        g.append(d if d > 0 else 0.0)
        l.append(-d if d < 0 else 0.0)
    ag, al = _ref_emaw(g, n), _ref_emaw(l, n)
    out = []
    for gv, lv in zip(ag, al):
        if math.isnan(gv):
            out.append(float("nan"))
        elif lv == 0:
            out.append(100.0)
        else:
            out.append(100 - 100 / (1 + gv / lv))
    return out


def _ref_atr_js(high, low, close, n):
    """Espejo de window._lwc.atr (con el primer TR = rango del día)."""
    tr = [high[0] - low[0]]
    for i in range(1, len(close)):
        tr.append(max(high[i] - low[i],
                      abs(high[i] - close[i - 1]),
                      abs(low[i] - close[i - 1])))
    return _ref_emaw(tr, n)


def _random_ohlc(n=120, seed=7):
    rng = np.random.RandomState(seed)
    close = 100 + rng.randn(n).cumsum()
    high  = close + rng.rand(n) * 2
    low   = close - rng.rand(n) * 2
    return high, low, close


# ── Paridad ───────────────────────────────────────────────────────────────────

def test_wilder_smooth_semilla_es_sma():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    out = _wilder_smooth(s, 5)
    assert math.isnan(out.iloc[3])
    assert out.iloc[4] == pytest.approx(3.0)          # SMA de 1..5
    assert out.iloc[5] == pytest.approx(0.2 * 6 + 0.8 * 3.0)

def test_wilder_smooth_serie_corta_todo_nan():
    assert _wilder_smooth(pd.Series([1.0, 2.0]), 5).isna().all()

def test_rsi_paridad_con_el_grafico():
    _, _, close = _random_ohlc()
    esperado = _ref_rsi_js(list(close), 14)
    obtenido = _rsi_series(pd.Series(close), 14)
    for i in range(14, len(close)):
        assert obtenido.iloc[i] == pytest.approx(round(esperado[i], 2), abs=0.01), f"i={i}"

def test_atr_paridad_con_el_grafico():
    high, low, close = _random_ohlc()
    df = pd.DataFrame({"high": high, "low": low, "close": close})
    esperado = _ref_atr_js(list(high), list(low), list(close), 14)
    obtenido = _atr_series(df, 14)
    for i in range(13, len(close)):
        assert obtenido.iloc[i] == pytest.approx(esperado[i], rel=1e-9), f"i={i}"

def test_rsi_subida_pura_da_100_tambien_en_la_serie():
    # antes: la serie persistida daba NaN en subida pura (no se escribía fila)
    # mientras el gráfico mostraba 100 — unificado a 100
    close = pd.Series([float(i) for i in range(1, 31)])
    serie = _rsi_series(close, 14)
    assert serie.iloc[-1] == 100.0
    assert serie.iloc[13] == 100.0                    # primer valor calculable
