"""Tests del motor puro de simulación de cartera (portfolio_sim_engine).

Codifican: pesos top-N equal-weight, semántica sin look-ahead (la cartera formada
al cierre de D gana recién en D+1) y costos sobre el turnover.
"""
from datetime import date

import pytest

from app.services.portfolio_sim_engine import (simulate_fixed_weights,
                                               simulate_gated, simulate_topn,
                                               topn_weights)


def test_topn_weights():
    assert topn_weights({1: 5.0, 2: 3.0, 3: 9.0}, 2) == {3: 0.5, 1: 0.5}
    assert topn_weights({1: 5.0}, 5) == {1: 1.0}   # menos activos que N
    assert topn_weights({}, 3) == {}


def test_simulate_topn_no_lookahead_and_equity():
    d1, d2, d3 = date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 4)
    scores = {d1: {1: 2.0, 2: 1.0}}                # forma en d1: top-1 = activo 1
    rets = {d2: {1: 0.10}, d3: {1: 0.20}}          # gana 10% en d2, 20% en d3
    res = simulate_topn([d1, d2, d3], scores, rets, top_n=1, rebalance_every=10)
    # d1: cartera vacía al acreditar (r=0), luego forma top-1 → equity 1.0
    # d2: +10% → 1.10 ; d3: +20% → 1.32
    assert res["equity"] == pytest.approx([1.0, 1.1, 1.32])
    assert res["weights"][0] == {1: 1.0}           # tiene el activo 1 desde d1


def test_simulate_topn_costs_on_turnover():
    d1, d2 = date(2026, 1, 2), date(2026, 1, 3)
    res = simulate_topn([d1, d2], {d1: {1: 1.0}}, {d2: {1: 0.10}},
                        top_n=1, rebalance_every=10, cost_bps=100)
    # d1: turnover 0.5 (0→100%), costo 1%·0.5 = 0.5% → equity 0.995
    assert res["turnover"][0] == pytest.approx(0.5)
    assert res["equity"][0] == pytest.approx(0.995)
    assert res["equity"][1] == pytest.approx(0.995 * 1.1)


def test_simulate_topn_rebalances_and_rotates():
    d1, d2, d3 = date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 4)
    # rebalanceo diario: en d2 el mejor score pasa a ser el activo 2
    scores = {d1: {1: 9.0, 2: 1.0}, d2: {1: 1.0, 2: 9.0}, d3: {1: 1.0, 2: 9.0}}
    rets = {d2: {1: 0.10, 2: -0.50}, d3: {1: 0.0, 2: 0.20}}
    res = simulate_topn([d1, d2, d3], scores, rets, top_n=1, rebalance_every=1)
    # d1 forma activo 1; d2 gana con activo 1 (+10%) y recién ahí rota a activo 2;
    # d3 gana con activo 2 (+20%)
    assert res["weights"][0] == {1: 1.0}
    assert res["weights"][1] == {2: 1.0}
    assert res["equity"] == pytest.approx([1.0, 1.1, 1.1 * 1.2])


# ── sub-modo gated ────────────────────────────────────────────────────────────

def test_gated_holds_intersection_of_topn_and_eligible():
    d1, d2 = date(2026, 1, 2), date(2026, 1, 3)
    scores = {d1: {1: 9.0, 2: 5.0, 3: 1.0}}     # top-2 = {1, 2}
    eligible = {d1: {2, 3}}                       # elegibles = {2, 3}
    rets = {d2: {2: 0.10}}
    res = simulate_gated([d1, d2], scores, eligible, rets, top_n=2,
                         rebalance_every=10)
    # held = {1,2} ∩ {2,3} = {2}  → el activo 1 (top-N pero no elegible) queda afuera
    assert res["weights"][0] == {2: 1.0}
    assert res["equity"] == pytest.approx([1.0, 1.1])


def test_gated_two_held_equal_weight():
    d1, d2 = date(2026, 1, 2), date(2026, 1, 3)
    scores = {d1: {1: 9.0, 2: 5.0, 3: 1.0}}     # top-2 = {1, 2}
    eligible = {d1: {1, 2, 3}}
    rets = {d2: {1: 0.10, 2: 0.20}}
    res = simulate_gated([d1, d2], scores, eligible, rets, top_n=2,
                         rebalance_every=10)
    assert res["weights"][0] == {1: 0.5, 2: 0.5}
    # 0.5·10% + 0.5·20% = 15%
    assert res["equity"] == pytest.approx([1.0, 1.15])


def test_gated_all_cash_when_none_eligible():
    d1, d2 = date(2026, 1, 2), date(2026, 1, 3)
    scores = {d1: {1: 9.0, 2: 5.0}}
    eligible = {d1: set()}                        # nada elegible → todo cash
    rets = {d2: {1: 0.50}}
    res = simulate_gated([d1, d2], scores, eligible, rets, top_n=2,
                         rebalance_every=10)
    assert res["weights"][0] == {}
    assert res["equity"] == pytest.approx([1.0, 1.0])   # sin exposición, no gana


def test_gated_defers_exit_between_rebalances():
    # Entre rebalanceos los pesos NO se recalculan: un activo que deja de ser
    # elegible a mitad de ciclo PERMANECE en cartera hasta el próximo múltiplo de
    # rebalance_every (rebalanceo cuando i % rebalance_every == 0).
    d0, d1, d2, d3 = (date(2026, 1, 2), date(2026, 1, 3),
                      date(2026, 1, 5), date(2026, 1, 6))
    dates = [d0, d1, d2, d3]
    scores = {d: {1: 9.0} for d in dates}                 # activo 1 siempre top-1
    eligible = {d0: {1}, d1: set(), d2: set(), d3: set()}  # elegible sólo en d0
    rets = {d1: {1: 0.10}, d2: {1: 0.20}, d3: {1: 0.50}}

    res2 = simulate_gated(dates, scores, eligible, rets, top_n=1,
                          rebalance_every=2)
    # d0 (i%2==0) forma {1}; d1 (i%2==1) NO rebalancea → el activo 1 sigue en
    # cartera pese a ser inelegible (egreso diferido); d2 (i%2==0) SÍ es múltiplo
    # → recién ahí se lo evicta.
    assert res2["weights"][0] == {1: 1.0}
    assert res2["weights"][1] == {1: 1.0}     # difiere el egreso en mitad del ciclo
    assert res2["weights"][2] == {}           # se vende recién en el múltiplo
    assert res2["weights"][3] == {}
    # captura el retorno de d1 (0.10) y el de d2 (0.20) por seguir en cartera;
    # en d3 ya sin posición no gana el 0.50
    assert res2["equity"] == pytest.approx([1.0, 1.10, 1.32, 1.32])

    # con rebalanceo diario el egreso es inmediato en d1 → no captura el 0.20 de d2
    res1 = simulate_gated(dates, scores, eligible, rets, top_n=1,
                          rebalance_every=1)
    assert res1["weights"][1] == {}
    assert res1["equity"] == pytest.approx([1.0, 1.10, 1.10, 1.10])
    assert res2["equity"] != res1["equity"]   # difieren por el egreso diferido


def test_simulate_fixed_weights_constant_mix():
    d1, d2, d3 = date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 4)
    target = {1: 0.5, 2: 0.5}
    rets = {d2: {1: 0.10, 2: 0.20}, d3: {1: 0.0, 2: 0.0}}
    res = simulate_fixed_weights([d1, d2, d3], target, rets, rebalance_every=1)
    assert res["weights"][0] == {1: 0.5, 2: 0.5}
    # d2: 0.5·10% + 0.5·20% = 15% ; d3: 0
    assert res["equity"] == pytest.approx([1.0, 1.15, 1.15])
