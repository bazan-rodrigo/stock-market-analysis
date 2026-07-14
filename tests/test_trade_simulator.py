"""Tests del simulador de trades (contrato Python ↔ JS del gráfico).

Los casos viven en fixtures/trade_simulator_cases.json: son EL contrato de la
semántica de entrada/salida, compartido conceptualmente con la réplica JS de
chart_callbacks.py (regla de homologación en CLAUDE.md). Cambiar un caso es
cambiar la semántica: exige tocar ambas implementaciones en el mismo commit.
"""
import json
from pathlib import Path

import pytest

from app.services.trade_simulator import simulate_trades, summarize_trades

_CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "trade_simulator_cases.json")
    .read_text(encoding="utf-8")
)["cases"]


@pytest.mark.parametrize("case", _CASES, ids=[c["name"] for c in _CASES])
def test_contrato(case):
    trades = simulate_trades(case["closes"], case["scores"], case["spec"],
                             case.get("percentiles"))
    got = [{"entry_idx": t["entry_idx"], "exit_idx": t["exit_idx"],
            "reason": t["reason"]} for t in trades]
    assert got == case["expected"]

    # Invariantes de todos los casos: retornos consistentes con los closes,
    # entry/exit apuntando a los precios correctos, a lo sumo UN trade abierto
    # y solo al final.
    for t in trades:
        assert t["entry_close"] == case["closes"][t["entry_idx"]]
        if t["exit_idx"] is not None:
            assert t["exit_close"] == case["closes"][t["exit_idx"]]
            assert t["exit_idx"] > t["entry_idx"]
            expected_ret = case["closes"][t["exit_idx"]] / t["entry_close"] - 1
        else:
            assert t["exit_close"] is None
            expected_ret = case["closes"][-1] / t["entry_close"] - 1
        assert t["ret"] == pytest.approx(expected_ret)
    assert sum(1 for t in trades if t["exit_idx"] is None) <= 1
    if trades and trades[-1]["exit_idx"] is None:
        assert all(t["exit_idx"] is not None for t in trades[:-1])


def test_modo_desconocido_falla():
    with pytest.raises(ValueError):
        simulate_trades([100], [25],
                        {"entry": 20, "mode": {"type": "zaraza"}, "cap": None})


def test_tope_desconocido_falla():
    with pytest.raises(ValueError):
        simulate_trades([100], [25],
                        {"entry": 20, "mode": {"type": "absolute", "x": 0},
                         "cap": {"type": "zaraza"}})


def test_summarize_basico():
    trades = [
        {"entry_idx": 0, "exit_idx": 2, "entry_close": 100, "exit_close": 110,
         "ret": 0.10, "reason": "absolute"},
        {"entry_idx": 3, "exit_idx": 5, "entry_close": 100, "exit_close": 95,
         "ret": -0.05, "reason": "filter"},
        {"entry_idx": 6, "exit_idx": None, "entry_close": 100, "exit_close": None,
         "ret": 0.02, "reason": None},
    ]
    s = summarize_trades(trades)
    assert s["n_trades"] == 3
    assert s["n_closed"] == 2
    assert s["win_rate"] == pytest.approx(0.5)
    assert s["avg_ret"] == pytest.approx(0.025)
    assert s["median_ret"] == pytest.approx(0.025)
    assert s["avg_bars"] == pytest.approx(2.0)
    assert s["n_filter"] == 1
    assert s["open_ret"] == pytest.approx(0.02)


def test_summarize_vacio():
    s = summarize_trades([])
    assert s["n_trades"] == 0
    assert s["win_rate"] is None
    assert s["avg_ret"] is None
    assert s["open_ret"] is None
