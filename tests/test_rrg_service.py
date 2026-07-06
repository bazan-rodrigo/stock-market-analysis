"""rrg_service: normalización rolling usada para el RS-Ratio/Momentum del RRG."""
import pandas as pd

from app.services.rrg_service import _normalize_rolling


def test_normalize_rolling_primeros_valores_son_nan_por_min_periods():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    out = _normalize_rolling(s, window=3)
    assert out.iloc[:2].isna().all()


def test_normalize_rolling_rampa_lineal_da_valor_constante():
    # en una rampa, media y desvío de cada ventana son iguales entre sí →
    # el z-score normalizado es constante (siempre el último punto de la
    # ventana está a +1 desvío de la media)
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    out = _normalize_rolling(s, window=3)
    assert out.iloc[2:].round(6).tolist() == [110.0, 110.0, 110.0, 110.0]


def test_normalize_rolling_desvio_cero_da_nan_no_error():
    s = pd.Series([5.0, 5.0, 5.0, 5.0, 5.0])
    out = _normalize_rolling(s, window=3)
    assert out.iloc[2:].isna().all()


def test_normalize_rolling_serie_mas_corta_que_la_ventana_es_toda_nan():
    s = pd.Series([1.0, 2.0])
    out = _normalize_rolling(s, window=5)
    assert out.isna().all()
