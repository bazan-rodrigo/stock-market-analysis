"""Tests de los núcleos puros de la orquestación de cartera (nivel C).

Codifican el mapeo trades → barras en posición y el ensamblado del cross-section.
La función que toca BD (run_portfolio_backtest) se verifica en el Codespace.
"""
from datetime import date

import pytest

from app.services.portfolio_backtest_service import _in_position, build_panels


def test_in_position_maps_trades_to_bars():
    trades = [{"entry_idx": 1, "exit_idx": 3},      # en posición barras 1,2
              {"entry_idx": 5, "exit_idx": None}]   # abierto → hasta la última
    assert _in_position(trades, n_bars=8) == {1, 2, 5, 6, 7}


def test_in_position_ignores_null_entries():
    assert _in_position([{"entry_idx": None, "exit_idx": None}], 4) == set()


def test_build_panels_assembles_cross_section():
    d1, d2, d3 = date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 4)
    per_asset = {
        1: {"dates": [d1, d2, d3], "closes": [100.0, 110.0, 121.0],
            "scores": [5.0, 6.0, 7.0], "in_position": {0, 1}},
        2: {"dates": [d1, d2], "closes": [50.0, 55.0],
            "scores": [3.0, None], "in_position": {0}},
    }
    dates, scores, rets, eligible = build_panels(per_asset)

    assert dates == [d1, d2, d3]
    # scores: el None del activo 2 en d2 queda afuera
    assert scores == {d1: {1: 5.0, 2: 3.0}, d2: {1: 6.0}, d3: {1: 7.0}}
    # retornos cierre-a-cierre en fechas propias (d1 no tiene previo)
    assert rets[d2][1] == pytest.approx(0.10)
    assert rets[d2][2] == pytest.approx(0.10)
    assert rets[d3][1] == pytest.approx(0.10)
    assert d1 not in rets
    # elegibles = in_position mapeado a fechas
    assert eligible == {d1: {1, 2}, d2: {1}}


def test_build_panels_carries_across_interior_gap():
    d1, d2, d3 = date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 5)
    per_asset = {
        # el activo 1 NO cotiza en d2 (hueco interior)
        1: {"dates": [d1, d3], "closes": [100.0, 121.0], "scores": [5.0, 7.0],
            "in_position": {0, 1}},
        2: {"dates": [d1, d2, d3], "closes": [50.0, 55.0, 60.0],
            "scores": [3.0, 4.0, 4.0], "in_position": {0, 1, 2}},
    }
    _dates, scores, rets, eligible = build_panels(per_asset)
    # en el hueco d2 el score y la elegibilidad del activo 1 se arrastran
    assert scores[d2][1] == 5.0
    assert 1 in eligible[d2]
    assert 1 not in rets.get(d2, {})               # sin retorno en el hueco
    assert rets[d3][1] == pytest.approx(0.21)      # el retorno cruza el hueco → d3


def test_cross_gap_return_is_earned_by_portfolio():
    from app.services.portfolio_sim_engine import simulate_topn
    d1, d2, d3 = date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 5)
    per_asset = {
        1: {"dates": [d1, d3], "closes": [100.0, 121.0], "scores": [5.0, 7.0],
            "in_position": {0, 1}},
        2: {"dates": [d1, d2, d3], "closes": [50.0, 55.0, 60.0],
            "scores": [3.0, 4.0, 4.0], "in_position": {0, 1, 2}},
    }
    dates, scores, rets, eligible = build_panels(per_asset)
    res = simulate_topn(dates, scores, rets, top_n=1, rebalance_every=1)
    # top-1 es siempre el activo 1 (score 5/5/7 > 3/4/4): no se evicta en el hueco
    # y gana el retorno que lo cruza (+21%) — sin el arrastre, se perdería
    assert res["weights"][0] == {1: 1.0} and res["weights"][1] == {1: 1.0}
    assert res["equity"][2] == pytest.approx(1.21)
