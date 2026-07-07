"""Paridad de la version vectorizada de _compute_by_type (pandas/numpy) contra
el calculo escalar original (loop por fecha en Python puro), mas cobertura del
orden topologico de compute_all_synthetic para sinteticos que dependen de otros
sinteticos."""
from datetime import date
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from app.services.synthetic_service import (
    _compute_by_type,
    _common_index,
    _topological_levels,
    _weighted_sums,
)


def _frame(pairs: dict) -> pd.DataFrame:
    """pairs: {date: (open, close)} -> DataFrame con columnas close/eff_open,
    replicando la logica de _safe_open (open invalido -> usa el close de esa fecha)."""
    rows = []
    for d, (o, c) in pairs.items():
        eff_open = o if (o is not None and o != 0) else c
        rows.append((d, c, eff_open))
    df = pd.DataFrame(rows, columns=["date", "close", "eff_open"]).set_index("date")
    return df.sort_index()


def _comp(asset_id, role, weight=1.0):
    return SimpleNamespace(asset_id=asset_id, role=role, weight=weight)


def _formula(formula_type, base_value=None, base_date=None):
    return SimpleNamespace(formula_type=formula_type, base_value=base_value, base_date=base_date)


D1, D2, D3, D4 = date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)


# ── ratio ─────────────────────────────────────────────────────────────────────

def test_ratio_basico_paridad_escalar():
    price_frames = {
        1: _frame({D1: (10, 12), D2: (12, 14), D3: (14, 16)}),
        2: _frame({D1: (100, 110), D2: (110, 120), D3: (120, 130)}),
    }
    comps = [_comp(1, "numerator", 2.0), _comp(2, "denominator", 1.0)]
    out = _compute_by_type(_formula("ratio"), comps, price_frames)

    for d in (D1, D2, D3):
        num_c = 2.0 * price_frames[1].loc[d, "close"]
        den_c = 1.0 * price_frames[2].loc[d, "close"]
        num_o = 2.0 * price_frames[1].loc[d, "eff_open"]
        den_o = 1.0 * price_frames[2].loc[d, "eff_open"]
        close = num_c / den_c
        open_ = num_o / den_o
        assert out[d]["close"] == pytest.approx(close)
        assert out[d]["open"]  == pytest.approx(open_)
        assert out[d]["high"]  == pytest.approx(max(open_, close))
        assert out[d]["low"]   == pytest.approx(min(open_, close))


def test_ratio_denominador_cero_se_omite():
    price_frames = {
        1: _frame({D1: (10, 12), D2: (12, 14)}),
        2: _frame({D1: (0, 0),   D2: (5, 5)}),
    }
    comps = [_comp(1, "numerator"), _comp(2, "denominator")]
    out = _compute_by_type(_formula("ratio"), comps, price_frames)
    assert D1 not in out
    assert D2 in out


def test_ratio_open_invalido_usa_close_como_fallback():
    """den_o == 0 (todas las aperturas efectivas del denominador dan 0) -> open_ = close."""
    price_frames = {
        1: _frame({D1: (0, 10)}),   # eff_open = 10 (open invalido -> close)
        2: _frame({D1: (0, 0)}),    # close=0 -> eff_open tambien 0
    }
    comps = [_comp(1, "numerator"), _comp(2, "denominator", weight=0.0)]
    out = _compute_by_type(_formula("ratio"), comps, price_frames)
    # den_c = 0*0 = 0 -> la fecha se omite igual (denominador de cierre es 0)
    assert D1 not in out


# ── weighted_avg / weighted_sum ──────────────────────────────────────────────

def test_weighted_avg_paridad_escalar():
    price_frames = {
        1: _frame({D1: (10, 10), D2: (11, 12)}),
        2: _frame({D1: (20, 22), D2: (21, 23)}),
    }
    comps = [_comp(1, "component", 1.0), _comp(2, "component", 3.0)]
    out = _compute_by_type(_formula("weighted_avg"), comps, price_frames)
    total_w = 4.0
    for d in (D1, D2):
        close = (1.0 * price_frames[1].loc[d, "close"] + 3.0 * price_frames[2].loc[d, "close"]) / total_w
        assert out[d]["close"] == pytest.approx(close)


def test_weighted_sum_no_divide_por_total_de_pesos():
    price_frames = {
        1: _frame({D1: (10, 10)}),
        2: _frame({D1: (20, 22)}),
    }
    comps = [_comp(1, "component", 1.0), _comp(2, "component", 3.0)]
    out = _compute_by_type(_formula("weighted_sum"), comps, price_frames)
    assert out[D1]["close"] == pytest.approx(1.0 * 10 + 3.0 * 22)


# ── index ─────────────────────────────────────────────────────────────────────

def test_index_con_base_date_exacta():
    price_frames = {
        1: _frame({D1: (100, 100), D2: (110, 110)}),
    }
    comps = [_comp(1, "component", 1.0)]
    formula = _formula("index", base_value=100.0, base_date=D1)
    out = _compute_by_type(formula, comps, price_frames)
    assert out[D1]["close"] == pytest.approx(100.0)
    assert out[D2]["close"] == pytest.approx(110.0)


def test_index_base_date_usa_fecha_anterior_mas_cercana():
    """Si base_date no tiene precio exacto, usa la fecha <= base_date mas cercana."""
    price_frames = {
        1: _frame({D1: (100, 100), D3: (120, 120)}),
    }
    comps = [_comp(1, "component", 1.0)]
    formula = _formula("index", base_value=100.0, base_date=D2)  # D2 no existe
    out = _compute_by_type(formula, comps, price_frames)
    # base price = close en D1 (unica fecha <= D2)
    assert out[D3]["close"] == pytest.approx(100.0 * 120 / 100)


def test_index_sin_base_date_usa_ultima_fecha_disponible():
    price_frames = {
        1: _frame({D1: (100, 100), D2: (110, 110)}),
    }
    comps = [_comp(1, "component", 1.0)]
    formula = _formula("index", base_value=100.0, base_date=None)
    out = _compute_by_type(formula, comps, price_frames)
    # base price = close en D2 (la ultima), asi que D2 vale exactamente base_value
    assert out[D2]["close"] == pytest.approx(100.0)


# ── helpers de fechas comunes ─────────────────────────────────────────────────

def test_common_index_interseca_fechas():
    price_frames = {
        1: _frame({D1: (1, 1), D2: (1, 1), D3: (1, 1)}),
        2: _frame({D2: (1, 1), D3: (1, 1), D4: (1, 1)}),
    }
    common = _common_index([1, 2], price_frames)
    assert list(common) == [D2, D3]


def test_weighted_sums_pondera_correctamente():
    price_frames = {
        1: _frame({D1: (2, 4)}),
        2: _frame({D1: (10, 20)}),
    }
    common = _common_index([1, 2], price_frames)
    close_sum, open_sum = _weighted_sums([(1.0, 1), (2.0, 2)], price_frames, common)
    assert close_sum[0] == pytest.approx(1.0 * 4 + 2.0 * 20)
    assert open_sum[0]  == pytest.approx(1.0 * 2 + 2.0 * 10)


# ── orden topologico de sinteticos que dependen de otros sinteticos ─────────

def _syn_formula(asset_id, dep_ids):
    return SimpleNamespace(
        asset_id=asset_id,
        asset=SimpleNamespace(ticker=f"SYN{asset_id}"),
        components=[SimpleNamespace(asset_id=d) for d in dep_ids],
    )


def test_topological_levels_cadena_simple():
    # C depende de B, B depende de A, A no depende de nada
    a = _syn_formula(1, [])
    b = _syn_formula(2, [1])
    c = _syn_formula(3, [2])
    levels = _topological_levels([c, b, a])  # orden de entrada desordenado a proposito
    ids_by_level = [sorted(f.asset_id for f in level) for level in levels]
    assert ids_by_level == [[1], [2], [3]]


def test_topological_levels_diamante_mismo_nivel():
    # B y C dependen de A; D depende de B y C. B y C deben quedar en el mismo nivel.
    a = _syn_formula(1, [])
    b = _syn_formula(2, [1])
    c = _syn_formula(3, [1])
    d = _syn_formula(4, [2, 3])
    levels = _topological_levels([a, b, c, d])
    ids_by_level = [sorted(f.asset_id for f in level) for level in levels]
    assert ids_by_level == [[1], [2, 3], [4]]


def test_topological_levels_sin_dependencias_un_solo_nivel():
    a = _syn_formula(1, [])
    b = _syn_formula(2, [])
    levels = _topological_levels([a, b])
    assert len(levels) == 1
    assert sorted(f.asset_id for f in levels[0]) == [1, 2]


def test_topological_levels_ciclo_no_cuelga():
    # A depende de B y B depende de A: ciclo. No debe entrar en loop infinito.
    a = _syn_formula(1, [2])
    b = _syn_formula(2, [1])
    levels = _topological_levels([a, b])
    all_ids = sorted(f.asset_id for level in levels for f in level)
    assert all_ids == [1, 2]
