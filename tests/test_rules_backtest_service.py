"""Tests del agregador puro del backtest nivel B (rules_backtest_service).

Codifica: ranking por retorno total descendente, desglose global de salidas por
motivo (ignora abiertos), y agregados solo sobre los activos con trades.
"""
import datetime as dt

import pytest

from app.database import Base, engine, get_session
from app.models import signal_store
from app.services.rules_backtest_service import (aggregate_rules_results,
                                                 run_rules_backtest)


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


def test_aggregate_activo_solo_abiertos_va_al_final():
    # summarize_trades devuelve total_ret=None / win_rate=None cuando hay
    # trades pero ninguno cerrado (posición abierta al final de la serie):
    # n_trades>0 pero sin retorno realizado. El agregador debe contarlo como
    # "con trades", NO colarlo en median/mean (filtra `is not None`), y
    # ordenarlo ÚLTIMO en el ranking (fallback float("-inf")).
    per_asset = [
        # cerrado: aporta a los agregados
        _asset(1, 1, 0.50, 1.00, [{"ret": 0.5, "reason": "take_profit"}]),
        # solo-abierto: n_trades>0 pero total_ret/win_rate None (trade abierto)
        {"asset_id": 2, "trades": [{"ret": None, "reason": None}], "summary": {
            "n_trades": 1, "n_closed": 0, "total_ret": None, "win_rate": None,
            "avg_ret": None, "avg_bars": None}},
    ]
    agg = aggregate_rules_results(per_asset)

    assert agg["n_with_trades"] == 2                 # el solo-abierto cuenta
    # el activo con total_ret=None queda ÚLTIMO (fallback -inf)
    assert [r["asset_id"] for r in agg["ranking"]] == [1, 2]
    assert agg["ranking"][-1]["asset_id"] == 2
    assert agg["ranking"][-1]["total_ret"] is None
    # median/mean SOLO sobre el cerrado (None no se cuela ni crashea)
    assert agg["median_total_ret"] == pytest.approx(0.50)
    assert agg["mean_total_ret"] == pytest.approx(0.50)
    assert agg["mean_win_rate"] == pytest.approx(1.00)
    # el trade abierto (reason None) no aporta al desglose de salidas
    assert agg["exit_reasons"] == {"take_profit": {
        "count": 1, "mean_ret": pytest.approx(0.5), "total_ret": pytest.approx(0.5)}}


# ── M7: guard de universo vacío en run_rules_backtest (toca el sqlite stub) ────
#
# run_rules_backtest enumera los asset_ids con score NO-NULO en strat_res_{id};
# si el universo queda vacío avisa con ValueError ('Recalcular completo') — es
# contrato de cara al usuario. El guard corta ANTES del fan-out
# (load_series/simulate_trades/summarize_trades): esos tres solo se ejercitan en
# el test del camino feliz, con las funciones pesadas monkeypatcheadas.

_SID = 777  # id de estrategia aislado (no colisiona con otros tests)


@pytest.fixture()
def empty_strat():
    """strat_res_{_SID} existe y arranca vacía (universo vacío por defecto)."""
    Base.metadata.create_all(engine)
    get_session().rollback()                       # soltar transacción colgada
    t = signal_store.ensure_strat_table(_SID)
    with engine.begin() as c:
        c.execute(t.delete())
    yield t
    get_session().rollback()
    with engine.begin() as c:
        c.execute(t.delete())


def test_run_rules_backtest_universo_vacio_avisa(empty_strat):
    # tabla sin filas → universo vacío → avisa (no revienta con un error opaco)
    with pytest.raises(ValueError, match="Recalcular completo"):
        run_rules_backtest(_SID, {})


def test_run_rules_backtest_solo_scores_nulos_avisa(empty_strat):
    # filas presentes pero todas con score NULL: el filtro .isnot(None) las
    # excluye → el universo sigue vacío → mismo ValueError (prueba que el guard
    # mira el score, no la mera existencia de filas).
    s = get_session()
    s.execute(empty_strat.insert(), [
        {"asset_id": 1, "date": dt.date(2026, 7, 7), "score": None, "pct": None},
        {"asset_id": 2, "date": dt.date(2026, 7, 8), "score": None, "pct": None},
    ])
    s.commit()
    with pytest.raises(ValueError, match="Recalcular completo"):
        run_rules_backtest(_SID, {})


def test_run_rules_backtest_con_universo_no_avisa(empty_strat, monkeypatch):
    """Camino feliz complementario: con al menos un score no-nulo el guard NO se
    dispara. Enumera el universo (el activo con score NULL queda afuera) y corre
    el fan-out con load_series/simulate_trades/summarize_trades monkeypatcheados
    (patrón de test_indicator_pipeline_order: mockear lo pesado, verificar el
    contrato)."""
    import app.services.trade_optimizer as topt
    import app.services.trade_simulator as tsim

    s = get_session()
    s.execute(empty_strat.insert(), [
        {"asset_id": 5, "date": dt.date(2026, 7, 7), "score": 1.0, "pct": 10.0},
        {"asset_id": 5, "date": dt.date(2026, 7, 8), "score": 2.0, "pct": 20.0},
        {"asset_id": 9, "date": dt.date(2026, 7, 8), "score": None, "pct": None},
    ])
    s.commit()

    seen = []
    monkeypatch.setattr(topt, "load_series",
                        lambda aid, sid: (seen.append(aid) or ([], [], [])))
    monkeypatch.setattr(tsim, "simulate_trades", lambda *a, **k: [])
    monkeypatch.setattr(tsim, "summarize_trades",
                        lambda trades: {"n_trades": 0, "n_closed": 0,
                                        "total_ret": None, "win_rate": None,
                                        "avg_ret": None, "avg_bars": None})

    out = run_rules_backtest(_SID, {})
    assert seen == [5]                 # el score NULL (activo 9) queda afuera
    assert out["n_assets"] == 1
    assert out["n_with_trades"] == 0
