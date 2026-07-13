"""Score de estrategias (componentes ponderados) y fechas del backfill.

La fórmula "composite" de señales se removió (la combinación se hace en la
estrategia): acá se verifica que quede rechazada, y se cubren el scoring
ponderado de estrategias y la selección de fechas del delta/rebuild.
"""
from types import SimpleNamespace

from app.services.strategy_service import _compute_asset_score


# ── composite rechazada ───────────────────────────────────────────────────────

def test_validate_params_rechaza_composite():
    from app.services import signal_engine
    err = signal_engine.validate_params("composite", {"components": []})
    assert err and "composite" in err


def test_evaluate_composite_devuelve_none():
    from app.services import signal_engine
    # ya no es un tipo válido: evaluate no lo computa
    assert signal_engine.evaluate("composite", "{}", None) is None


# ── _compute_asset_score (estrategias) ────────────────────────────────────────

def _comp(signal_id, weight=1.0, scope=None, group_type=None, group_id=None):
    return SimpleNamespace(signal_id=signal_id, weight=weight, scope=scope,
                           group_type=group_type, group_id=group_id)


def test_score_ponderado_de_senales_de_activo():
    comps = [_comp(1, weight=1), _comp(2, weight=3)]
    score = _compute_asset_score(
        comps, asset_id=7, asset_groups={7: {}},
        signal_scores={(1, 7): 100.0, (2, 7): 0.0}, group_scores={},
    )
    assert score == 25.0

def test_score_ignora_senales_sin_valor():
    comps = [_comp(1, weight=1), _comp(2, weight=9)]
    score = _compute_asset_score(
        comps, asset_id=7, asset_groups={7: {}},
        signal_scores={(1, 7): 80.0}, group_scores={},
    )
    assert score == 80.0

def test_score_todo_faltante_es_none():
    comps = [_comp(1)]
    assert _compute_asset_score(comps, 7, {7: {}}, {}, {}) is None

def test_score_own_group_usa_el_grupo_del_activo():
    comps = [_comp(1, scope="own_group", group_type="sector")]
    score = _compute_asset_score(
        comps, asset_id=7, asset_groups={7: {"sector": 3}},
        signal_scores={}, group_scores={(1, "sector", 3): 42.0},
    )
    assert score == 42.0

def test_score_specific_group_usa_el_grupo_fijo():
    comps = [_comp(1, scope="specific_group", group_type="market", group_id=9)]
    score = _compute_asset_score(
        comps, asset_id=7, asset_groups={7: {"market": 1}},   # el del activo NO se usa
        signal_scores={}, group_scores={(1, "market", 9): 33.0},
    )
    assert score == 33.0

def test_score_activo_sin_grupo_saltea_el_componente():
    comps = [_comp(1, scope="own_group", group_type="sector"),
             _comp(2, weight=1)]
    score = _compute_asset_score(
        comps, asset_id=7, asset_groups={7: {"sector": None}},
        signal_scores={(2, 7): 60.0}, group_scores={(1, "sector", 3): 999.0},
    )
    assert score == 60.0


# ── Backfill de señales: qué fechas correr ────────────────────────────────────

def test_dates_to_compute_delta_llena_huecos_y_siempre_la_ultima():
    from datetime import date
    from app.services.signal_service import _dates_to_compute
    d1, d2, d3, d4 = (date(2026, 7, 6), date(2026, 7, 7),
                      date(2026, 7, 8), date(2026, 7, 9))
    trading = [d1, d2, d3, d4]
    # d1 y d3 ya calculadas; d4 (ultima) se recalcula igual por preliminar
    out = _dates_to_compute(trading, {d1, d3, d4}, force=False)
    assert out == [d2, d4]

def test_dates_to_compute_force_todas():
    from datetime import date
    from app.services.signal_service import _dates_to_compute
    trading = [date(2026, 7, 6), date(2026, 7, 7)]
    assert _dates_to_compute(trading, set(trading), force=True) == trading

def test_dates_to_compute_vacio():
    from app.services.signal_service import _dates_to_compute
    assert _dates_to_compute([], set(), force=False) == []
    assert _dates_to_compute([], set(), force=True) == []
