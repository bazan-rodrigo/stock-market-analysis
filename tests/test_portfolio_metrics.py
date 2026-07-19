"""Tests del motor puro de métricas de cartera (portfolio_metrics.py).

Codifican las convenciones: equity ↔ retornos, Sharpe/Sortino/vol anualizados,
drawdown con índices, métricas de trades (profit factor/expectancy/payoff),
desglose por motivo de salida, exposición, turnover y matriz mensual. Una
métrica no computable devuelve None (nunca inf/NaN).
"""
from datetime import date
from math import sqrt

import pytest

from app.services.portfolio_metrics import (annualized_volatility, cagr,
                                            drawdown_series, equity_from_returns,
                                            exit_reason_breakdown, expectancy,
                                            exposure, max_drawdown,
                                            monthly_return_matrix, payoff_ratio,
                                            profit_factor, returns_from_equity,
                                            sharpe, sortino, summary,
                                            total_return, turnover, win_rate)


# ── equity ↔ retornos ─────────────────────────────────────────────────────────

def test_returns_from_equity():
    assert returns_from_equity([100.0, 110.0, 121.0]) == pytest.approx([0.1, 0.1])


def test_returns_from_equity_zero_denominator():
    assert returns_from_equity([0.0, 100.0]) == [None]


def test_equity_from_returns_roundtrip():
    eq = equity_from_returns([0.1, 0.1], base=100.0)
    assert eq == pytest.approx([100.0, 110.0, 121.0])


# ── total return / cagr ───────────────────────────────────────────────────────

def test_total_return():
    assert total_return([100.0, 110.0]) == pytest.approx(0.1)
    assert total_return([100.0]) is None
    assert total_return([0.0, 100.0]) is None


def test_cagr_two_years():
    # 121/100 en 2 años → 10% anual compuesto
    assert cagr([100.0, 121.0], years=2) == pytest.approx(0.1)


def test_cagr_invalid_years():
    assert cagr([100.0, 121.0], years=0) is None
    assert cagr([100.0], years=2) is None


# ── volatilidad / sharpe / sortino ────────────────────────────────────────────

def test_annualized_volatility():
    # stdev muestral de [0, 0.02] = 0.0141421 ; × √252
    assert annualized_volatility([0.0, 0.02]) == pytest.approx(0.0141421356 * sqrt(252))
    assert annualized_volatility([0.01]) is None


def test_sharpe_constant_returns_is_none():
    assert sharpe([0.01, 0.01, 0.01]) is None  # desvío 0


def test_sharpe_symmetric_is_zero():
    assert sharpe([0.01, -0.01, 0.01, -0.01]) == pytest.approx(0.0)


def test_sharpe_known_value():
    # mean 0.01, std 0.0141421 → (0.01/0.0141421)·√252
    expected = (0.01 / 0.0141421356) * sqrt(252)
    assert sharpe([0.0, 0.02]) == pytest.approx(expected, rel=1e-6)


def test_sortino_no_downside_is_none():
    assert sortino([0.01, 0.02]) is None


def test_sortino_known_value():
    rs = [0.02, -0.01, 0.03, -0.02]
    dd = sqrt((0.01 ** 2 + 0.02 ** 2) / len(rs))
    expected = ((sum(rs) / len(rs)) / dd) * sqrt(252)
    assert sortino(rs) == pytest.approx(expected, rel=1e-6)


# ── drawdown ──────────────────────────────────────────────────────────────────

def test_drawdown_series():
    assert drawdown_series([100.0, 120.0, 90.0, 150.0]) == pytest.approx(
        [0.0, 0.0, -0.25, 0.0])


def test_max_drawdown_with_recovery():
    md = max_drawdown([100.0, 120.0, 90.0, 150.0])
    assert md["mdd"] == pytest.approx(-0.25)
    assert md["peak_idx"] == 1
    assert md["trough_idx"] == 2
    assert md["recovery_idx"] == 3


def test_max_drawdown_no_recovery():
    md = max_drawdown([100.0, 120.0, 90.0])
    assert md["mdd"] == pytest.approx(-0.25)
    assert md["recovery_idx"] is None


# ── métricas de trades ────────────────────────────────────────────────────────

def test_win_rate():
    assert win_rate([0.1, -0.05, 0.2, -0.1]) == pytest.approx(0.5)
    assert win_rate([]) is None


def test_profit_factor():
    assert profit_factor([0.1, -0.05, 0.2, -0.1]) == pytest.approx(0.3 / 0.15)
    assert profit_factor([0.1, 0.2]) is None  # sin pérdidas → indefinido


def test_expectancy():
    assert expectancy([0.1, -0.05, 0.2, -0.1]) == pytest.approx(0.0375)


def test_payoff_ratio():
    # avg win 0.15, avg loss 0.075 → 2.0
    assert payoff_ratio([0.1, -0.05, 0.2, -0.1]) == pytest.approx(2.0)
    assert payoff_ratio([0.1, 0.2]) is None


def test_exit_reason_breakdown_ignores_open():
    trades = [
        {"ret": 0.1, "reason": "take_profit"},
        {"ret": -0.05, "reason": "stop_loss"},
        {"ret": 0.2, "reason": "take_profit"},
        {"ret": None, "reason": None},  # abierto
    ]
    br = exit_reason_breakdown(trades)
    assert br["take_profit"]["count"] == 2
    assert br["take_profit"]["mean_ret"] == pytest.approx(0.15)
    assert br["take_profit"]["total_ret"] == pytest.approx(0.3)
    assert br["stop_loss"]["count"] == 1
    assert "reason" not in br and None not in br


# ── exposición / turnover ─────────────────────────────────────────────────────

def test_exposure():
    trades = [
        {"entry_idx": 0, "exit_idx": 5},
        {"entry_idx": 10, "exit_idx": None},  # abierto hasta last_idx
    ]
    assert exposure(trades, total_bars=20, last_idx=15) == pytest.approx(0.5)
    assert exposure(trades, total_bars=0) is None


def test_turnover():
    snaps = [{"A": 0.5, "B": 0.5}, {"A": 0.5, "C": 0.5}]
    assert turnover(snaps) == pytest.approx(0.5)
    assert turnover([{"A": 1.0}]) is None


# ── matriz mensual ────────────────────────────────────────────────────────────

def test_monthly_return_matrix():
    dates = [date(2020, 1, 31), date(2020, 2, 15), date(2020, 2, 28),
             date(2020, 3, 10)]
    equity = [100.0, 110.0, 121.0, 133.1]
    m = monthly_return_matrix(dates, equity)
    # febrero compone dos +10% → +21% ; marzo +10%
    assert m[2020][2] == pytest.approx(0.21)
    assert m[2020][3] == pytest.approx(0.10)


def test_monthly_return_matrix_length_mismatch():
    assert monthly_return_matrix([date(2020, 1, 1)], [100.0, 110.0]) is None


# ── summary ───────────────────────────────────────────────────────────────────

def test_summary_keys_and_values():
    equity = [100.0, 110.0, 121.0, 133.1]
    dates = [date(2020, 1, 1), date(2020, 2, 1), date(2020, 3, 1),
             date(2021, 1, 1)]
    trades = [
        {"ret": 0.1, "reason": "take_profit", "entry_idx": 0, "exit_idx": 1},
        {"ret": -0.05, "reason": "stop_loss", "entry_idx": 2, "exit_idx": 3},
    ]
    s = summary(equity, dates=dates, trades=trades)
    assert s["total_return"] == pytest.approx(0.331)
    assert s["max_drawdown"] == pytest.approx(0.0)  # serie monótona creciente
    assert s["n_trades"] == 2 and s["n_closed"] == 2
    assert s["win_rate"] == pytest.approx(0.5)
    assert s["cagr"] is not None
    assert "monthly_returns" in s and "exit_reasons" in s
