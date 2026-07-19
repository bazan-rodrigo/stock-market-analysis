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
