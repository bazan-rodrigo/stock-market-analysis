"""signal_engine: fórmulas puras de señales (sin DB)."""
import json

from app.services import signal_engine as se


# ── discrete_map ──────────────────────────────────────────────────────────────

def test_discrete_map_conocido():
    assert se.evaluate_discrete_map({"map": {"bullish": 60}}, "bullish") == 60.0

def test_discrete_map_valor_none():
    assert se.evaluate_discrete_map({"map": {"bullish": 60}}, None) is None

def test_discrete_map_valor_desconocido():
    assert se.evaluate_discrete_map({"map": {"bullish": 60}}, "lateral") is None


# ── threshold ─────────────────────────────────────────────────────────────────

_THRESHOLDS = {"thresholds": [[-5, 100], [-15, 50], [-30, 0], [None, -50]]}

def test_threshold_primer_limite():
    assert se.evaluate_threshold(_THRESHOLDS, 0) == 100.0      # 0 > -5

def test_threshold_intermedio():
    assert se.evaluate_threshold(_THRESHOLDS, -10) == 50.0     # -10 > -15

def test_threshold_default_null():
    assert se.evaluate_threshold(_THRESHOLDS, -40) == -50.0    # cae al default

def test_threshold_igual_al_limite_no_matchea():
    # la comparación es estricta (>): -5 no supera -5, pasa al siguiente
    assert se.evaluate_threshold(_THRESHOLDS, -5) == 50.0

def test_threshold_sin_default_y_sin_match():
    assert se.evaluate_threshold({"thresholds": [[10, 100]]}, 5) is None

def test_threshold_valor_none():
    assert se.evaluate_threshold(_THRESHOLDS, None) is None


# ── range ─────────────────────────────────────────────────────────────────────

def test_range_extremos_y_centro():
    p = {"min": -3.0, "max": 3.0, "clamp": True}
    assert se.evaluate_range(p, -3.0) == -100.0
    assert se.evaluate_range(p, 3.0) == 100.0
    assert se.evaluate_range(p, 0.0) == 0.0

def test_range_clamp_recorta():
    p = {"min": 0, "max": 10, "clamp": True}
    assert se.evaluate_range(p, 20) == 100.0
    assert se.evaluate_range(p, -20) == -100.0

def test_range_sin_clamp_extrapola():
    p = {"min": 0, "max": 10, "clamp": False}
    assert se.evaluate_range(p, 20) == 300.0

def test_range_span_cero():
    assert se.evaluate_range({"min": 5, "max": 5}, 5) == 0.0

def test_range_valor_none():
    assert se.evaluate_range({"min": 0, "max": 10}, None) is None


# ── composite ─────────────────────────────────────────────────────────────────

def test_composite_promedio_ponderado():
    params = {"components": [{"signal_key": "a", "weight": 1},
                             {"signal_key": "b", "weight": 3}]}
    assert se.evaluate_composite(params, {"a": 100, "b": 0}) == 25.0

def test_composite_ignora_none():
    params = {"components": [{"signal_key": "a", "weight": 1},
                             {"signal_key": "b", "weight": 9}]}
    assert se.evaluate_composite(params, {"a": 80, "b": None}) == 80.0

def test_composite_todos_none():
    params = {"components": [{"signal_key": "a"}]}
    assert se.evaluate_composite(params, {"a": None}) is None

def test_composite_sin_componentes():
    assert se.evaluate_composite({"components": []}, {}) is None


# ── evaluate (dispatch) ───────────────────────────────────────────────────────

def test_evaluate_dispatch_threshold():
    assert se.evaluate("threshold", json.dumps(_THRESHOLDS), -10) == 50.0

def test_evaluate_json_invalido():
    assert se.evaluate("range", "{esto no es json", 5) is None

def test_evaluate_tipo_desconocido():
    assert se.evaluate("magia", "{}", 5) is None

def test_evaluate_params_preparseados_evitan_el_json():
    # con params pre-parseados, el params_json (roto) no debe tocarse
    p = {"min": 0, "max": 10, "clamp": True}
    assert se.evaluate("range", "{json roto", 5, params=p) == 0.0
