"""strategy_service.percent_ranks: percentil de la cross-section que el
pipeline persiste en strategy_result.pct (migración 0071).

Fija la semántica de SQL PERCENT_RANK(): (rank−1)/(n−1)×100 con RANK() para
empates — el reemplazo exacto de la ventana que antes se corría al leer.
"""
import pytest

from app.services.strategy_service import percent_ranks


def test_basico_alineado_al_orden_de_entrada():
    # valores desordenados: el resultado respeta el orden de entrada
    assert percent_ranks([30.0, 10.0, 20.0]) == [100.0, 0.0, 50.0]


def test_semantica_percent_rank_sql():
    # 5 valores: ranks 1..5 → 0, 25, 50, 75, 100
    assert percent_ranks([1, 2, 3, 4, 5]) == [0.0, 25.0, 50.0, 75.0, 100.0]


def test_empates_comparten_el_rango_minimo():
    # [10, 20, 20, 30]: ranks RANK() = 1, 2, 2, 4 → 0, 33.33, 33.33, 100
    got = percent_ranks([10, 20, 20, 30])
    assert got[0] == 0.0
    assert got[1] == got[2] == pytest.approx(100 / 3)
    assert got[3] == 100.0


def test_todos_iguales():
    assert percent_ranks([5, 5, 5]) == [0.0, 0.0, 0.0]


def test_degenerados():
    assert percent_ranks([]) == []
    assert percent_ranks([42.0]) == [0.0]  # igual que SQL con n=1
