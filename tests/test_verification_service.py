"""check_sanity: chequeos de cordura independientes del delta — ¿el valor
tiene sentido para ese código, sin importar cómo se calculó?"""
from datetime import date, timedelta

from app.services.fundamental_service import _Quarter
from app.services.verification_service import (
    _current_ratio_fresh, _diff_category, _values_equal, check_sanity,
)


def _q(period_date, **kw):
    fields = {f: None for f in _Quarter._fields if f != "period_date"}
    fields.update(kw)
    return _Quarter(period_date=period_date, **fields)


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


# ── _values_equal: tolerancia absoluta + relativa ─────────────────────────────
# ind_fundamental_* guarda en una columna Float (FLOAT de MySQL, precisión
# simple) — para ratios de magnitud grande (pesos ARS/CLP) el redondeo de
# la propia columna ya supera 0.01 sin que sea un bug de cálculo.

def test_values_equal_dentro_de_tolerancia_absoluta():
    assert _values_equal(1.005, 1.01)


def test_values_equal_fuera_de_tolerancia_absoluta_magnitud_chica():
    assert not _values_equal(1.0, 1.5)


def test_values_equal_tolerancia_relativa_para_magnitudes_grandes():
    assert _values_equal(35955.5556, 35955.6)


def test_values_equal_diferencia_relativa_grande_si_dispara():
    assert not _values_equal(100.0, 200.0)


# ── _current_ratio_fresh: replica _compute_current_ratios (fundamental_
# service.py) en modo lectura — el ratio "vigente" que el sistema real
# escribe con fecha de hoy usando el último trimestre + último precio,
# sea o no hoy un cierre de trimestre o una fecha con precio propio.

def test_current_ratio_fresh_usa_ultimo_trimestre_y_ultimo_precio():
    today = date.today()
    quarters = [
        _q(today - timedelta(days=400), net_income=100, revenue=500,
           equity=1000, shares=100),
        _q(today - timedelta(days=100), net_income=120, revenue=550,
           equity=1100, shares=100),
    ]
    price_rows = [(today - timedelta(days=5), 50.0)]
    fresh = _current_ratio_fresh(quarters, price_rows)
    assert fresh["fundamental_pb"] == round(50.0 / (1100 / 100), 4)


def test_current_ratio_fresh_sin_quarters_devuelve_vacio():
    assert _current_ratio_fresh([], [(date.today(), 50.0)]) == {}


def test_current_ratio_fresh_sin_precio_no_agrega_ratios_diarios():
    today = date.today()
    quarters = [_q(today - timedelta(days=100), net_income=120, revenue=550,
                   equity=1100, shares=100, total_debt=200)]
    fresh = _current_ratio_fresh(quarters, [])
    assert "fundamental_pe_ttm" not in fresh
    assert "fundamental_pb" not in fresh
    # los trimestrales sí se calculan aunque no haya precio
    assert "fundamental_debt_to_equity" in fresh


# ── _diff_category: separa "sospecha de bug de caché" de "dato de origen
# raro" — guardado != recalculado es lo primero (el propósito real de esta
# herramienta); guardado == recalculado pero fuera de rango es lo segundo
# (ver hallazgos reales: ITX.MC precio corrupto, CMPC.SN P/E con <4
# trimestres) y no debería mezclarse con sospechas de bug de caché/delta.

def test_diff_category_discrepancia_de_valor_es_calc():
    assert _diff_category("valor distinto") == "calc"
    assert _diff_category("solo en DB (¿debería haberse borrado?)") == "calc"
    assert _diff_category("falta en DB (¿el delta no la escribió?)") == "calc"


def test_diff_category_sanity_es_cualquier_otro_motivo():
    assert _diff_category("fuera de rango [0,100] para rsi_daily: 150") == "sanity"
    assert _diff_category("categoría desconocida para trend_daily: 'sideways'") == "sanity"
