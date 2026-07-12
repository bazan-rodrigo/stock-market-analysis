"""Resolución de señales composite por dependencias y score de estrategias."""
import json
from types import SimpleNamespace

from app.services.signal_service import _build_composite_scores, _composite_refs
from app.services.strategy_service import _compute_asset_score


def _sig(id_, key, components=None, formula_type="composite"):
    params = json.dumps({"components": components or []})
    return SimpleNamespace(id=id_, key=key, formula_type=formula_type, params=params)


# ── _composite_refs ───────────────────────────────────────────────────────────

def test_composite_refs_extrae_keys():
    sig = _sig(1, "a", [{"signal_key": "x", "weight": 1}, {"signal_key": "y"}])
    assert _composite_refs(sig) == {"x", "y"}

def test_composite_refs_json_roto():
    sig = SimpleNamespace(id=1, key="a", formula_type="composite", params="{roto")
    assert _composite_refs(sig) == set()


# ── _build_composite_scores: orden de dependencias ────────────────────────────

def test_composite_anidada_espera_a_su_dependencia():
    # b (base) = 100, c (base) = 0
    # B = composite(c)          → 0
    # A = composite(B, b)       → (0 + 100) / 2 = 50  SOLO si B se resolvió antes
    signals = [
        _sig(10, "B", [{"signal_key": "c", "weight": 1}]),
        _sig(11, "A", [{"signal_key": "B", "weight": 1},
                       {"signal_key": "b", "weight": 1}]),
    ]
    scores = {"b": 100.0, "c": 0.0}
    _build_composite_scores(signals, scores)
    assert scores["B"] == 0.0
    assert scores["A"] == 50.0

def test_composite_anidada_orden_de_definicion_no_importa():
    # A definida ANTES que B en la lista: igual debe esperar a B
    signals = [
        _sig(11, "A", [{"signal_key": "B", "weight": 1},
                       {"signal_key": "b", "weight": 1}]),
        _sig(10, "B", [{"signal_key": "c", "weight": 1}]),
    ]
    scores = {"b": 100.0, "c": 0.0}
    _build_composite_scores(signals, scores)
    assert scores["A"] == 50.0

def test_composite_ciclo_no_cuelga_y_resuelve_con_lo_disponible():
    signals = [
        _sig(1, "A", [{"signal_key": "B", "weight": 1}, {"signal_key": "b", "weight": 1}]),
        _sig(2, "B", [{"signal_key": "A", "weight": 1}, {"signal_key": "b", "weight": 1}]),
    ]
    scores = {"b": 100.0}
    _build_composite_scores(signals, scores)
    assert scores["A"] is not None and scores["B"] is not None

def test_composite_sin_componentes_resolubles_es_none():
    signals = [_sig(1, "A", [{"signal_key": "inexistente", "weight": 1}])]
    scores = {}
    _build_composite_scores(signals, scores)
    assert scores["A"] is None


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

def test_closure_composites_recursivo():
    import json
    from types import SimpleNamespace
    from app.services.signal_service import _closure_composites
    def _sig2(id_, key, ftype="threshold", comps=None):
        return SimpleNamespace(id=id_, key=key, formula_type=ftype,
                               params=json.dumps({"components": comps or []}))
    signals = [
        _sig2(1, "a"),
        _sig2(2, "b"),
        _sig2(3, "AB", "composite", [{"signal_key": "a"}, {"signal_key": "b"}]),
        _sig2(4, "ABC", "composite", [{"signal_key": "AB"}, {"signal_key": "c"}]),
        _sig2(5, "c"),
        _sig2(6, "suelta"),
    ]
    # partir de la composite anidada arrastra toda la cadena, no lo suelto
    assert _closure_composites({4}, signals) == {1, 2, 3, 4, 5}
    # una hoja no arrastra nada
    assert _closure_composites({1}, signals) == {1}
