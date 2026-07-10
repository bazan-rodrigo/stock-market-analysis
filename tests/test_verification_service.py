"""check_sanity: chequeos de cordura independientes del delta — ¿el valor
tiene sentido para ese código, sin importar cómo se calculó?"""
from app.services.verification_service import check_sanity


def test_rsi_en_rango_no_dispara():
    assert check_sanity("rsi_daily", 55.3) is None
    assert check_sanity("rsi_daily", 0) is None
    assert check_sanity("rsi_daily", 100) is None


def test_rsi_fuera_de_rango_dispara():
    assert check_sanity("rsi_daily", 150) is not None
    assert check_sanity("rsi_weekly", -5) is not None


def test_atr_percentile_fuera_de_rango_dispara():
    assert check_sanity("atr_percentile_monthly", 101) is not None


def test_trend_categoria_valida_no_dispara():
    for v in ("bullish", "bearish", "lateral", "bullish_nascent_strong"):
        assert check_sanity("trend_daily", v) is None


def test_trend_categoria_desconocida_dispara():
    assert check_sanity("trend_daily", "sideways") is not None


def test_volatility_categoria_valida_no_dispara():
    assert check_sanity("volatility_weekly", "alta_larga") is None


def test_volatility_categoria_desconocida_dispara():
    assert check_sanity("volatility_weekly", "muy_alta_larga") is not None


def test_return_extremo_dispara():
    assert check_sanity("return_daily", 50000) is not None


def test_return_razonable_no_dispara():
    assert check_sanity("return_daily", -8.5) is None


def test_fundamental_margin_extremo_dispara():
    assert check_sanity("fundamental_net_margin", 500) is not None


def test_fundamental_margin_razonable_no_dispara():
    assert check_sanity("fundamental_net_margin", 0.15) is None


def test_codigo_sin_bounds_conocidos_no_dispara():
    # un código sin entrada en _NUMERIC_BOUNDS/_CATEGORICAL_VALUES no se
    # puede validar — no dispara falso positivo
    assert check_sanity("codigo_inventado_sin_bounds", "cualquier cosa") is None


def test_valor_none_no_dispara():
    assert check_sanity("rsi_daily", None) is None
