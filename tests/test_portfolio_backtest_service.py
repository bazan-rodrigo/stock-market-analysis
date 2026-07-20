"""Tests de los núcleos puros de la orquestación de cartera (nivel C).

Codifican el mapeo trades → barras en posición y el ensamblado del cross-section.
La función que toca BD (run_portfolio_backtest) se verifica en el Codespace.
"""
from datetime import date, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

import app.models  # noqa: F401 — registra todos los modelos para create_all
from app.database import Base
from app.models.price import Price
from app.services import portfolio_backtest_service as pbs
from app.services import portfolio_service as ps
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


# ── equity de teórica curada (curated_equity_series, nivel C) ─────────────────
#
# constant-mix (rebalanceo diario a los pesos objetivo) de los miembros de una
# cartera curada. Guardas: sin miembros → None; miembros sin precios → None.


def test_curated_equity_happy_path():
    s = _session()
    p = ps.create_portfolio(s, "Basket", "seg", owner_id=1,
                            composition_method="curated")
    ps.set_members(s, p.id, [10, 20])                 # EW 50/50 (sin pesos)
    d1, d2, d3 = date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 4)
    s.add_all([Price(asset_id=10, date=d1, close=100.0),
               Price(asset_id=10, date=d2, close=110.0),
               Price(asset_id=10, date=d3, close=121.0),
               Price(asset_id=20, date=d1, close=50.0),
               Price(asset_id=20, date=d2, close=55.0),
               Price(asset_id=20, date=d3, close=60.5)])
    s.commit()

    out = pbs.curated_equity_series(s, p.id)
    assert out is not None
    assert out["dates"] == [d1, d2, d3]
    # ambos miembros +10% por rueda → constant-mix EW también +10% (equity coincide
    # con simulate_fixed_weights: [1.0, 1.1, 1.21])
    assert out["equity"] == pytest.approx([1.0, 1.1, 1.21])
    # KPIs de portfolio_metrics.summary presentes
    assert out["total_return"] == pytest.approx(0.21)
    for k in ("cagr", "sharpe", "sortino", "max_drawdown", "volatility"):
        assert k in out


def test_curated_equity_none_when_no_members():
    s = _session()
    p = ps.create_portfolio(s, "Vacia", "seg", owner_id=1,
                            composition_method="curated")
    # sin set_members → resolve_membership devuelve [] → guarda de "sin miembros"
    assert pbs.curated_equity_series(s, p.id) is None


def test_curated_equity_none_when_no_prices():
    s = _session()
    p = ps.create_portfolio(s, "SinPrecios", "seg", owner_id=1,
                            composition_method="curated")
    ps.set_members(s, p.id, [10, 20])                 # miembros SIN precios
    # ningún miembro con precios → per_asset vacío → guarda de "sin precios"
    assert pbs.curated_equity_series(s, p.id) is None


def test_curated_equity_asset_with_price_gap():
    s = _session()
    p = ps.create_portfolio(s, "Gap", "seg", owner_id=1,
                            composition_method="curated")
    ps.set_members(s, p.id, [10, 20])                 # EW 50/50
    d1, d2, d3 = date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 4)
    # el activo 20 NO cotiza en d2 (hueco interior respecto del calendario de 10):
    # build_panels arrastra su tenencia y acredita el retorno que cruza el hueco
    # (50→60.5 = +21%) en d3 → equity computable, no rompe.
    s.add_all([Price(asset_id=10, date=d1, close=100.0),
               Price(asset_id=10, date=d2, close=110.0),
               Price(asset_id=10, date=d3, close=121.0),
               Price(asset_id=20, date=d1, close=50.0),
               Price(asset_id=20, date=d3, close=60.5)])
    s.commit()

    out = pbs.curated_equity_series(s, p.id)
    assert out is not None
    assert out["dates"] == [d1, d2, d3]
    # d2: sólo el 10 tiene retorno (0.5·10% = +5%); d3: 10 (+10%) y 20 (+21% que
    # cruzó el hueco) → 0.5·10% + 0.5·21% = +15.5% sobre 1.05
    assert out["equity"] == pytest.approx([1.0, 1.05, 1.21275])


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
    # los tres sub-modos de _SUBMODES salen (ranking incluido)
    assert got["series"]["ranking"]["equity"] == [1.0, 1.05]
    assert got["series"]["ranking"]["dates"] == [d1, d2]
    assert got["summary"]["ranking"]["cagr"] == 0.3


def test_get_portfolio_run_missing_is_none():
    s = _session()
    assert pbs.get_portfolio_run(s, 99999) is None


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


def test_wf_score_prefers_steadier_equity():
    from app.services.portfolio_backtest_service import _wf_score
    steady = [1.0, 1.01, 1.02, 1.03, 1.04]        # sube parejo → Sharpe alto
    volatile = [1.0, 1.10, 0.95, 1.12, 1.04]      # ~mismo fin, con vaivenes
    # el objetivo risk-adjusted prefiere la curva pareja (mismo retorno, - riesgo)
    assert _wf_score(steady) > _wf_score(volatile)
    assert _wf_score([]) == float("-inf")         # degenerado → nunca elegido
    assert _wf_score([1.0]) == float("-inf")
    # vol cero → Sharpe indefinido → -inf (camino DISTINTO al de longitud < 2):
    # retornos CONSTANTES (no vacíos). Se usan potencias de 2 porque sus
    # cocientes son exactos en float → retornos [1.0, 1.0, 1.0] con desvío 0
    # (el literal [1.0, 1.1, 1.21, 1.331] del enunciado NO sirve: el redondeo
    # binario da retornos apenas distintos → desvío ≠ 0 → Sharpe finito enorme).
    assert _wf_score([1.0, 2.0, 4.0, 8.0]) == float("-inf")


# ── walk-forward (orquestación OOS, carga pesada monkeypatcheada) ─────────────

class _DummySession:
    """Sesión mínima: walk_forward sólo llama session.rollback() tras la carga."""

    def rollback(self):
        pass


_WF_SPEC = {"entries": [{"type": "score", "th": 5}], "score_exits": [],
            "caps": [], "rearm": False, "cooldown": 0}


def _rising_universe(n_dates, asset_ids, scores_val):
    """{aid: {dates, closes, scores, pcts}} día-completo (sin huecos), precios
    siempre en alza con retornos variables (alternar +2%/+1%). `scores_val`
    constante por activo. Todos los activos comparten el mismo camino → la equity
    OOS no depende de qué top_n se elija (asserts robustos)."""
    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(n_dates)]
    closes = [100.0]
    for i in range(1, n_dates):
        closes.append(closes[-1] * (1.02 if i % 2 else 1.01))
    return dates, {aid: {"dates": dates, "closes": list(closes),
                         "scores": [scores_val] * n_dates,
                         "pcts": [None] * n_dates} for aid in asset_ids}


def test_walk_forward_concatenates_oos_windows(monkeypatch):
    # 33 fechas, 2 ventanas → _window_splits: seg=11, tests all_dates[11:22] y
    # all_dates[22:33]. Activos elegibles (score 9 ≥ th 5) y en alza → siempre
    # en cartera; la equity OOS crece salvo en la costura (arranque plano).
    dates, raw = _rising_universe(33, (1, 2, 3), scores_val=9.0)
    monkeypatch.setattr(pbs, "_load_universe", lambda *a, **k: raw)

    res = pbs.walk_forward(_DummySession(), 7, _WF_SPEC,
                           topn_grid=(1, 2), trail_grid=(10.0, 20.0), n_windows=2)

    # 1) los tests OOS se concatenan: equity y fechas paralelas, unión de ambas
    #    ventanas = calendario desde el 1er test.
    assert len(res["oos_equity"]) == len(res["oos_dates"])
    assert res["oos_dates"] == dates[11:]
    assert len(res["windows"]) == 2

    eq = res["oos_equity"]
    # 2) encadenado monótono: precios siempre en alza → no decrece (costura plana).
    assert all(eq[i + 1] >= eq[i] - 1e-12 for i in range(len(eq) - 1))

    # 3) carryover: la 2ª ventana arranca fresca (teq[0]=1.0, sin costos) y se
    #    escala por el `val` acumulado → su 1er punto OOS = último de la 1ª ventana.
    w0 = res["windows"][0]
    n0 = sum(1 for d in dates if w0["test"][0] <= d <= w0["test"][1])
    assert eq[n0] == pytest.approx(eq[n0 - 1])
    assert eq[n0] > 1.0                         # ya heredó ganancia de la 1ª ventana

    # 4) metadata: config elegida dentro de los grids + Sharpe de train finito
    #    (universo con retornos variables → no degenerado).
    for win in res["windows"]:
        assert win["top_n"] in (1, 2)
        assert win["trailing"] in (10.0, 20.0)
        assert win["train_sharpe"] is not None
        assert win["train"][0] == dates[0]      # train anclado-expansivo (desde el inicio)


def test_walk_forward_window_metadata(monkeypatch):
    # Caso degenerado: scores por DEBAJO del umbral de entrada (1 < th 5) → ningún
    # activo entra nunca → cartera siempre en cash → equity plana 1.0 → Sharpe de
    # train indefinido → train_sharpe None (best obj = -inf). Igual reporta la
    # config (primera de cada grid, sin empate que la supere).
    dates, raw = _rising_universe(33, (1,), scores_val=1.0)
    monkeypatch.setattr(pbs, "_load_universe", lambda *a, **k: raw)

    res = pbs.walk_forward(_DummySession(), 7, _WF_SPEC,
                           topn_grid=(1,), trail_grid=(10.0,), n_windows=2)

    assert len(res["windows"]) == 2
    for win in res["windows"]:
        assert win["top_n"] == 1
        assert win["trailing"] == 10.0
        assert win["train_sharpe"] is None       # degenerado → -inf → None
    assert set(res["oos_equity"]) == {1.0}       # nunca invertida → equity plana


def test_walk_forward_raises_on_insufficient_history(monkeypatch):
    # 15 fechas con 2 ventanas → seg=5: el 1er tramo de train queda con 5 ruedas
    # (< _WF_MIN_SEG_BARS=10) → ValueError (guard de historia insuficiente).
    _dates, raw = _rising_universe(15, (1,), scores_val=9.0)
    monkeypatch.setattr(pbs, "_load_universe", lambda *a, **k: raw)
    with pytest.raises(ValueError):
        pbs.walk_forward(_DummySession(), 7, _WF_SPEC,
                         topn_grid=(1,), trail_grid=(10.0,), n_windows=2)


def _build_panels_ref(per_asset):
    """Copia LITERAL de la version fusionada previa al split de build_panels en
    _score_ret_panels + _eligible_by_date. Oraculo para verificar que separar
    las dos partes no cambio la semantica (arrastre en huecos incluido)."""
    all_dates = sorted({d for a in per_asset.values() for d in a["dates"]})
    pos = {d: i for i, d in enumerate(all_dates)}
    scores_by_date, rets_by_date, eligible_by_date = {}, {}, {}
    for aid, data in per_asset.items():
        dts, closes, scores = data["dates"], data["closes"], data["scores"]
        if not dts:
            continue
        inpos = data.get("in_position", set())
        own = {d: k for k, d in enumerate(dts)}
        last_score, last_elig, prev_close = None, False, None
        for ci in range(pos[dts[0]], pos[dts[-1]] + 1):
            d = all_dates[ci]
            k = own.get(d)
            if k is not None:
                if prev_close:
                    rets_by_date.setdefault(d, {})[aid] = closes[k] / prev_close - 1.0
                prev_close = closes[k]
                if scores[k] is not None:
                    scores_by_date.setdefault(d, {})[aid] = scores[k]
                    last_score = scores[k]
                last_elig = k in inpos
            elif last_score is not None:
                scores_by_date.setdefault(d, {})[aid] = last_score
            if last_elig:
                eligible_by_date.setdefault(d, set()).add(aid)
    return all_dates, scores_by_date, rets_by_date, eligible_by_date


def test_build_panels_split_identico_al_fusionado():
    """build_panels (ahora _score_ret_panels + _eligible_by_date) debe dar
    EXACTAMENTE lo mismo que la version fusionada, incluidos huecos interiores
    con arrastre de score y elegibilidad."""
    import random
    from datetime import date, timedelta
    rng = random.Random(0)
    cal = [date(2024, 1, 1) + timedelta(days=i) for i in range(30)]
    for seed in range(8):
        r = random.Random(seed)
        per_asset = {}
        for aid in range(6):
            # rango propio [ini, fin] con huecos internos aleatorios
            ini, fin = r.randint(0, 5), r.randint(20, 29)
            idxs = [i for i in range(ini, fin + 1) if r.random() > 0.25]
            if len(idxs) < 2:
                idxs = [ini, fin]
            dts = [cal[i] for i in idxs]
            closes = [round(50 + r.uniform(-5, 5), 3) for _ in idxs]
            scores = [None if r.random() < 0.1 else round(r.uniform(-100, 100), 2)
                      for _ in idxs]
            inpos = {k for k in range(len(idxs)) if r.random() > 0.5}
            per_asset[aid] = {"dates": dts, "closes": closes, "scores": scores,
                              "in_position": inpos}
        assert build_panels(per_asset) == _build_panels_ref(per_asset), f"seed={seed}"
