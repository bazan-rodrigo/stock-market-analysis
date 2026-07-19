"""Tests del agregador puro del backtest nivel B (rules_backtest_service).

Codifica: ranking por retorno total descendente, desglose global de salidas por
motivo (ignora abiertos), y agregados solo sobre los activos con trades.
"""
import pytest

from app.services.rules_backtest_service import aggregate_rules_results


def _asset(aid, n_trades, total_ret, win_rate, trades):
    return {"asset_id": aid, "trades": trades, "summary": {
        "n_trades": n_trades, "n_closed": n_trades, "total_ret": total_ret,
        "win_rate": win_rate, "avg_ret": 0.0, "avg_bars": 10}}


def test_aggregate_ranking_reasons_and_stats():
    per_asset = [
        _asset(1, 2, 0.50, 0.50, [{"ret": 0.3, "reason": "take_profit"},
                                  {"ret": -0.1, "reason": "stop_loss"}]),
        _asset(2, 1, 0.20, 1.00, [{"ret": 0.2, "reason": "take_profit"}]),
        _asset(3, 0, None, None, []),          # sin trades → fuera de agregados
    ]
    agg = aggregate_rules_results(per_asset)

    assert agg["n_assets"] == 3
    assert agg["n_with_trades"] == 2
    assert agg["total_trades"] == 3
    # ranking por retorno total descendente
    assert [r["asset_id"] for r in agg["ranking"]] == [1, 2]
    # desglose global de salidas (ignora activos sin trades)
    assert agg["exit_reasons"]["take_profit"]["count"] == 2
    assert agg["exit_reasons"]["stop_loss"]["count"] == 1
    # agregados solo sobre activos con trades
    assert agg["median_total_ret"] == pytest.approx(0.35)   # median([0.5, 0.2])
    assert agg["mean_win_rate"] == pytest.approx(0.75)       # mean([0.5, 1.0])


def test_aggregate_empty_universe():
    agg = aggregate_rules_results([_asset(1, 0, None, None, [])])
    assert agg["n_with_trades"] == 0
    assert agg["median_total_ret"] is None
    assert agg["mean_win_rate"] is None
    assert agg["ranking"] == []
    assert agg["exit_reasons"] == {}
