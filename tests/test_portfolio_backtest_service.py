"""Tests de los núcleos puros de la orquestación de cartera (nivel C).

Codifican el mapeo trades → barras en posición y el ensamblado del cross-section.
La función que toca BD (run_portfolio_backtest) se verifica en el Codespace.
"""
from datetime import date

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

import app.models  # noqa: F401 — registra todos los modelos para create_all
from app.database import Base
from app.services import portfolio_backtest_service as pbs
from app.services.portfolio_backtest_service import _in_position, build_panels


def _session():
    eng = sa.create_engine("sqlite://")
    Base.metadata.create_all(eng)
    return Session(eng)


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


# ── persistencia de corridas (nivel D) ────────────────────────────────────────

def _mini_result(dates, gated_eq, rank_eq, bench_eq):
    def sub(eq, cagr):
        return {"equity": eq, "total_return": (eq[-1] - 1) if eq else None,
                "cagr": cagr, "sharpe": 1.0, "sortino": 1.0,
                "max_drawdown": -0.1, "volatility": 0.2}
    return {"dates": dates, "gated": sub(gated_eq, 0.5),
            "ranking": sub(rank_eq, 0.3), "benchmark_ew": sub(bench_eq, 0.1)}


def test_save_and_get_portfolio_run_roundtrip():
    s = _session()
    d1, d2 = date(2026, 1, 2), date(2026, 1, 3)
    result = _mini_result([d1, d2], [1.0, 1.1], [1.0, 1.05], [1.0, 1.02])
    run = pbs.save_portfolio_run(s, owner_id=1, strategy_id=7, name="Test",
                                 config={"top_n": 20}, result=result)
    got = pbs.get_portfolio_run(s, run.id)
    assert got["run"].name == "Test"
    assert got["config"]["top_n"] == 20
    assert got["summary"]["gated"]["cagr"] == 0.5
    assert got["series"]["gated"]["equity"] == [1.0, 1.1]
    assert got["series"]["gated"]["dates"] == [d1, d2]
    assert got["series"]["benchmark"]["equity"] == [1.0, 1.02]


def test_list_portfolio_runs_visibility():
    s = _session()
    empty = _mini_result([], [], [], [])
    pbs.save_portfolio_run(s, 1, 7, "Mia", {}, empty)
    pbs.save_portfolio_run(s, 2, 7, "Ajena", {}, empty)
    assert {r.name for r in pbs.list_portfolio_runs(s, 1, False)} == {"Mia"}
    assert len(pbs.list_portfolio_runs(s, 1, True)) == 2


# ── walk-forward (helpers puros) ──────────────────────────────────────────────

def test_window_splits_anchored_expanding():
    from app.services.portfolio_backtest_service import _window_splits
    # 100 fechas, 4 ventanas: seg=20, train desde 0, tests consecutivos al final
    assert _window_splits(100, 4) == [
        (0, 19, 20, 39), (0, 39, 40, 59), (0, 59, 60, 79), (0, 79, 80, 99)]
    # la última ventana estira hasta el final aunque no sea múltiplo exacto
    assert _window_splits(103, 4)[-1] == (0, 79, 80, 102)


def test_window_splits_insufficient_history():
    from app.services.portfolio_backtest_service import _window_splits
    assert _window_splits(3, 4) == []      # n < n_windows + 1
    assert _window_splits(50, 0) == []     # sin ventanas


def test_spec_with_trailing_replaces_existing():
    from app.services.portfolio_backtest_service import _spec_with_trailing
    base = {"entries": [{"type": "score", "th": 20}],
            "caps": [{"type": "stop_loss", "pct": 8},
                     {"type": "trailing_stop", "pct": 99}]}
    out = _spec_with_trailing(base, 15.0)
    trails = [c for c in out["caps"] if c["type"] == "trailing_stop"]
    assert len(trails) == 1 and trails[0]["pct"] == 15.0     # reemplazado, no dup
    assert {"type": "stop_loss", "pct": 8} in out["caps"]    # los demás intactos
    assert base["caps"][1]["pct"] == 99                      # base sin mutar


def test_gated_equity_range_runs_fresh_in_window():
    from app.services.portfolio_backtest_service import _gated_equity_range
    d = [date(2026, 1, i) for i in (2, 3, 4, 5, 6)]
    raw = {1: {"dates": d, "closes": [100.0, 110.0, 121.0, 133.0, 146.0],
               "scores": [9.0] * 5, "pcts": [None] * 5}}
    spec = {"entries": [{"type": "score", "th": 5}], "score_exits": [],
            "caps": [], "rearm": False, "cooldown": 0}
    # sub-rango [d2, d4]: sólo esas fechas entran al panel (arranque fresco)
    dates, eq = _gated_equity_range(raw, spec, top_n=1, date_from=d[1],
                                    date_to=d[3])
    assert dates == d[1:4]
    assert len(eq) == 3
    assert eq[-1] > 1.0        # el activo sube y se mantiene → equity crece


def test_span_cagr_annualizes_over_window():
    from app.services.portfolio_backtest_service import _span_cagr
    # +21% en ~1 año calendario → CAGR ≈ 21%
    dts = [date(2025, 1, 1), date(2026, 1, 1)]
    assert _span_cagr([1.0, 1.21], dts) == pytest.approx(0.21, abs=0.01)
    # sin datos suficientes → None (no comparable)
    assert _span_cagr([], []) is None
    assert _span_cagr([1.0], [date(2025, 1, 1)]) is None
