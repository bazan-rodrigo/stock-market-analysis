"""technical_service: helpers puros de cálculo (fechas, retornos, zonas, series)."""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.services.technical_service import (
    _Q_MONTH, _classify_duration, _compute_dd_events, _compute_regime_zones,
    _compute_vol_zones, _fv, _one_year_before, _pct_change, _rsi,
    _series_dates_values, _sma_zscore, _zones_to_series,
)


# ── Fechas ────────────────────────────────────────────────────────────────────

def test_one_year_before_normal():
    assert _one_year_before(date(2026, 7, 4)) == date(2025, 7, 4)

def test_one_year_before_29_febrero():
    assert _one_year_before(date(2024, 2, 29)) == date(2023, 2, 28)

def test_q_month_mapea_inicio_de_trimestre():
    assert _Q_MONTH[1] == 1 and _Q_MONTH[3] == 1
    assert _Q_MONTH[4] == 4 and _Q_MONTH[6] == 4
    assert _Q_MONTH[7] == 7 and _Q_MONTH[9] == 7
    assert _Q_MONTH[10] == 10 and _Q_MONTH[12] == 10


# ── Retornos y formato ────────────────────────────────────────────────────────

def test_pct_change():
    assert _pct_change(110, 100) == 10.0
    assert _pct_change(90, 100) == -10.0
    assert _pct_change(100, 0) is None
    assert _pct_change(None, 100) is None
    assert _pct_change(100, None) is None

def test_fv_none_nan_y_redondeo():
    assert _fv(None) is None
    assert _fv(float("nan")) is None
    assert _fv(3.14159) == 3.14
    assert _fv(3.14159, 1) == 3.1
    assert _fv("no numérico") is None


# ── z-score contra SMA ────────────────────────────────────────────────────────

def test_sma_zscore_valor_conocido():
    close = pd.Series([1.0, 2.0, 3.0, 4.0, 10.0])
    # SMA3 último = 17/3 ; std muestral de [3,4,10] = 3.78594
    assert _sma_zscore(close, 3) == pytest.approx(1.14, abs=0.01)

def test_sma_zscore_serie_constante_es_none():
    assert _sma_zscore(pd.Series([5.0] * 10), 3) is None

def test_sma_zscore_serie_corta_es_none():
    assert _sma_zscore(pd.Series([1.0, 2.0]), 5) is None


# ── RSI ───────────────────────────────────────────────────────────────────────

def test_rsi_subida_pura_es_100():
    close = pd.Series([float(i) for i in range(1, 31)])
    assert _rsi(close) == 100.0

def test_rsi_serie_corta_es_none():
    assert _rsi(pd.Series([1.0, 2.0, 3.0])) is None

def test_rsi_en_rango_0_100():
    rng = np.random.RandomState(42)
    close = pd.Series(100 + rng.randn(60).cumsum())
    val = _rsi(close)
    assert val is not None and 0 <= val <= 100


# ── Eventos de drawdown ───────────────────────────────────────────────────────

def _price_df(closes, start=date(2025, 1, 1)):
    return pd.DataFrame({
        "date":  [start + timedelta(days=i) for i in range(len(closes))],
        "close": closes,
    })

def test_dd_evento_cerrado():
    df = _price_df([100, 120, 60, 130])
    events = _compute_dd_events(df, min_depth_pct=20.0)
    assert len(events) == 1
    assert events[0]["depth"] == -50.0        # (60-120)/120
    assert events[0]["end"] is not None

def test_dd_en_curso_sin_end():
    events = _compute_dd_events(_price_df([100, 120, 60]), 20.0)
    assert len(events) == 1 and events[0]["end"] is None

def test_dd_caida_superficial_no_registra():
    assert _compute_dd_events(_price_df([100, 120, 110, 130]), 20.0) == []


# ── Zonas de régimen y volatilidad (smoke con datos sintéticos) ───────────────

def _trend_df(n=80, daily_ret=0.01, start_price=100.0):
    closes, p = [], start_price
    for _ in range(n):
        p *= (1 + daily_ret)
        closes.append(p)
    return pd.DataFrame({
        "date":  [date(2025, 1, 1) + timedelta(days=i) for i in range(n)],
        "close": closes,
        "high":  [c * 1.01 for c in closes],
        "low":   [c * 0.99 for c in closes],
    })

def test_regime_alcista_en_tendencia_alcista():
    zones = _compute_regime_zones(_trend_df(daily_ret=0.01), ema_period=10,
                                  slope_lookback=5, slope_threshold_pct=0.5,
                                  confirm_bars=2)
    assert zones and zones[-1]["regime"] == "bullish"
    assert "regime_detail" in zones[-1]

def test_regime_bajista_en_tendencia_bajista():
    zones = _compute_regime_zones(_trend_df(daily_ret=-0.01), ema_period=10,
                                  slope_lookback=5, slope_threshold_pct=0.5,
                                  confirm_bars=2)
    assert zones and zones[-1]["regime"] == "bearish"

def test_regime_df_corto_devuelve_vacio():
    assert _compute_regime_zones(_trend_df(n=5), 10, 5, 0.5, 2) == []

def test_vol_zones_estructura():
    zones = _compute_vol_zones(_trend_df(n=100), atr_period=14, confirm_bars=2,
                               pct_low=25, pct_high=75, pct_extreme=90,
                               dur_short_pct=33, dur_long_pct=67)
    for z in zones:
        assert z["vol_regime"] in {"baja", "normal", "alta", "extrema"}
        assert z["dur_regime"] in {"corta", "media", "larga"}
        assert z["start"] <= z["end"]


# ── Duración de zonas ─────────────────────────────────────────────────────────

def test_classify_duration():
    assert _classify_duration(5, [], 33, 67) == "media"          # sin historia
    hist = [10, 20, 30]
    assert _classify_duration(10, hist, 33, 67) == "corta"
    assert _classify_duration(20, hist, 33, 67) == "media"
    assert _classify_duration(30, hist, 33, 67) == "larga"


# ── Series de backfill ────────────────────────────────────────────────────────

def test_series_dates_values_lista_diaria():
    df = _price_df([1, 2, 3])
    dates, vals = _series_dates_values([10, 20, 30], df)
    assert dates == list(df["date"]) and vals == [10, 20, 30]

def test_series_dates_values_serie_periodica():
    s = pd.Series([1.5, 2.5], index=[date(2025, 1, 5), date(2025, 1, 12)])
    dates, vals = _series_dates_values(s, None)   # df no se usa en este camino
    assert dates == [date(2025, 1, 5), date(2025, 1, 12)]
    assert vals == [1.5, 2.5]

def test_zones_to_series_mapea_por_rango():
    df = _price_df([1, 2, 3, 4])                  # 1-ene..4-ene
    zones = [{"start": "2025-01-01", "end": "2025-01-02", "v": "a"},
             {"start": "2025-01-04", "end": "2025-01-04", "v": "b"}]
    out = _zones_to_series(zones, df, "v")
    assert out == ["a", "a", None, "b"]

def test_zones_to_series_sin_zonas():
    df = _price_df([1, 2])
    assert _zones_to_series([], df, "v") == [None, None]


# ── _pairs_to_write: modos de escritura del backfill ─────────────────────────

def test_pairs_reemplazo_total():
    from app.services.technical_service import _pairs_to_write
    pairs = _pairs_to_write(["d1", "d2", "d3"], [1.0, float("nan"), 3.0], None)
    assert pairs == [("d1", 1.0), ("d3", 3.0)]        # NaN nunca se escribe

def test_pairs_solo_faltantes_mas_ultima():
    from app.services.technical_service import _pairs_to_write
    pairs = _pairs_to_write(["d1", "d2", "d3"], [1.0, 2.0, 3.0], {"d1", "d3"})
    # d1 existe → no; d2 falta → sí; d3 existe pero es la última → sí
    assert pairs == [("d2", 2.0), ("d3", 3.0)]

def test_pairs_solo_cambios_full_sample():
    from app.services.technical_service import _pairs_to_write
    existing = {"d1": 10.0, "d2": 20.0, "d3": "alta_corta", "d4": 40.0}
    pairs = _pairs_to_write(
        ["d1", "d2", "d3", "d4", "d5"],
        [10.0, 21.5, "alta_larga", 40.0, 50.0],
        existing,
    )
    # d1 sin cambio → no; d2 cambió → sí; d3 (string) cambió → sí;
    # d4 sin cambio pero NO es la última → no; d5 es la última → siempre
    assert pairs == [("d2", 21.5), ("d3", "alta_larga"), ("d5", 50.0)]

def test_pairs_ultima_fecha_siempre_aunque_no_cambie():
    from app.services.technical_service import _pairs_to_write
    pairs = _pairs_to_write(["d1", "d2"], [1.0, 2.0], {"d1": 1.0, "d2": 2.0})
    assert pairs == [("d2", 2.0)]


# ── _cost_rank: orden LPT de la cola de workers ──────────────────────────────

def test_cost_rank_pesados_primero():
    from app.services.technical_service import _cost_rank
    # volatility_daily es el trabajo más grande del sistema
    assert _cost_rank("volatility_daily") > _cost_rank("atr_percentile_daily")
    assert _cost_rank("volatility_daily") > _cost_rank("volatility_weekly")
    # dentro de un mismo algoritmo: daily > weekly > monthly
    assert (_cost_rank("rsi_daily") > _cost_rank("rsi_weekly")
            > _cost_rank("rsi_monthly"))
    # los códigos sin sufijo de timeframe son series diarias
    assert _cost_rank("return_52w") == _cost_rank("return_daily")

def test_lpt_order_usa_mediciones_y_prioriza_desconocidos():
    from app.services.technical_service import _lpt_order
    codes = ["liviano", "pesado", "nuevo_sin_medir", "medio"]
    measured = {"liviano": 5.0, "pesado": 300.0, "medio": 60.0}
    orden = _lpt_order(codes, measured)
    # el desconocido primero (seguridad), luego por duración medida desc
    assert orden == ["nuevo_sin_medir", "pesado", "medio", "liviano"]

def test_lpt_order_sin_mediciones_cae_a_la_heuristica():
    from app.services.technical_service import _lpt_order
    orden = _lpt_order(["rsi_monthly", "volatility_daily", "rsi_daily"], {})
    assert orden[0] == "volatility_daily"
    assert orden[-1] == "rsi_monthly"
