"""Editor estructurado de parámetros de señal: conversión builder ↔ params
JSON (el formato que consume signal_engine), validaciones amigables e ida y
vuelta con los cuatro tipos de fórmula."""
import json

from app.callbacks.signal_params_ui import (
    builder_from_params,
    capture_pb_fields,
    empty_params_store,
    params_from_builder,
)


def _store_with(section, **kwargs):
    store = empty_params_store()
    store[section].update(kwargs)
    return store


def _rows_section(rows: list[dict]):
    return {
        "uids": list(range(len(rows))),
        "counter": len(rows),
        "rows": {str(i): r for i, r in enumerate(rows)},
    }


# ── discrete_map ──────────────────────────────────────────────────────────────

def test_map_basico():
    store = _store_with("map", **_rows_section([
        {"cat": "bullish", "score": 100},
        {"cat": "bearish", "score": -100},
    ]))
    params, error = params_from_builder("discrete_map", store)
    assert error is None
    assert json.loads(params) == {"map": {"bullish": 100, "bearish": -100}}

def test_map_fila_sin_score_se_omite():
    store = _store_with("map", **_rows_section([
        {"cat": "bullish", "score": 100},
        {"cat": "lateral", "score": None},
    ]))
    params, error = params_from_builder("discrete_map", store)
    assert error is None
    assert json.loads(params) == {"map": {"bullish": 100}}

def test_map_vacio_da_error():
    params, error = params_from_builder("discrete_map", empty_params_store())
    assert params is None and error

def test_map_categoria_repetida_da_error():
    store = _store_with("map", **_rows_section([
        {"cat": "bullish", "score": 100},
        {"cat": "bullish", "score": 50},
    ]))
    params, error = params_from_builder("discrete_map", store)
    assert params is None and "repetida" in error


# ── threshold ─────────────────────────────────────────────────────────────────

def test_threshold_ordena_desc_y_agrega_default():
    sec = _rows_section([
        {"limit": -30, "score": 0},
        {"limit": -5, "score": 100},
        {"limit": -15, "score": 50},
    ])
    store = _store_with("thresholds", **sec, default=-50)
    params, error = params_from_builder("threshold", store)
    assert error is None
    assert json.loads(params) == {
        "thresholds": [[-5, 100], [-15, 50], [-30, 0], [None, -50]]}

def test_threshold_sin_default_es_valido():
    store = _store_with("thresholds", **_rows_section([{"limit": 70, "score": 100}]))
    params, error = params_from_builder("threshold", store)
    assert error is None
    assert json.loads(params) == {"thresholds": [[70, 100]]}

def test_threshold_fila_a_medias_da_error():
    store = _store_with("thresholds", **_rows_section([{"limit": 70, "score": None}]))
    params, error = params_from_builder("threshold", store)
    assert params is None and error

def test_threshold_limites_repetidos_da_error():
    store = _store_with("thresholds", **_rows_section([
        {"limit": 70, "score": 100}, {"limit": 70, "score": 0}]))
    params, error = params_from_builder("threshold", store)
    assert params is None and "repetidos" in error

def test_threshold_vacio_da_error():
    params, error = params_from_builder("threshold", empty_params_store())
    assert params is None and error


# ── range ─────────────────────────────────────────────────────────────────────

def test_range_basico():
    store = _store_with("range", min=-3.0, max=3.0, clamp=False)
    params, error = params_from_builder("range", store)
    assert error is None
    assert json.loads(params) == {"min": -3.0, "max": 3.0, "clamp": False}

def test_range_incompleto_o_degenerado_da_error():
    assert params_from_builder("range", _store_with("range", min=1.0))[1]
    assert params_from_builder("range", _store_with("range", min=1.0, max=1.0))[1]


# ── composite ─────────────────────────────────────────────────────────────────

def test_composite_basico_y_peso_default():
    store = _store_with("components", **_rows_section([
        {"signal_key": "tendencia_d", "weight": 2},
        {"signal_key": "tendencia_w", "weight": None},
    ]))
    params, error = params_from_builder("composite", store)
    assert error is None
    assert json.loads(params) == {"components": [
        {"signal_key": "tendencia_d", "weight": 2},
        {"signal_key": "tendencia_w", "weight": 1.0},
    ]}

def test_composite_sin_senal_da_error():
    store = _store_with("components", **_rows_section([{"signal_key": None, "weight": 1}]))
    assert params_from_builder("composite", store)[1]

def test_composite_repetida_da_error():
    store = _store_with("components", **_rows_section([
        {"signal_key": "a", "weight": 1}, {"signal_key": "a", "weight": 2}]))
    assert "repetida" in params_from_builder("composite", store)[1]


# ── builder_from_params (editar) ─────────────────────────────────────────────

def test_ida_y_vuelta_todos_los_tipos():
    cases = [
        ("discrete_map", {"map": {"bullish": 100.0, "lateral": 0.0}}),
        ("threshold",    {"thresholds": [[70.0, 100.0], [30.0, 0.0], [None, -50.0]]}),
        ("range",        {"min": -3.0, "max": 3.0, "clamp": True}),
        ("composite",    {"components": [
            {"signal_key": "a", "weight": 2.0},
            {"signal_key": "b", "weight": 1.0}]}),
    ]
    for ftype, params in cases:
        store = builder_from_params(ftype, json.dumps(params))
        assert store is not None, ftype
        regen, error = params_from_builder(ftype, store)
        assert error is None, (ftype, error)
        assert json.loads(regen) == params, ftype

def test_json_roto_devuelve_none():
    assert builder_from_params("range", "{roto") is None
    assert builder_from_params("discrete_map", '{"map": "no-un-dict"}') is None
    assert builder_from_params("range", '{"min": "abc", "max": 3}') is None

def test_json_vacio_devuelve_store_vacio():
    assert builder_from_params("threshold", "{}") == empty_params_store()
    assert builder_from_params("threshold", None) == empty_params_store()


# ── capture_pb_fields ─────────────────────────────────────────────────────────

def test_capture_vuelca_valores_por_uid():
    store = _store_with("thresholds", **_rows_section([
        {"limit": None, "score": None}, {"limit": None, "score": None}]))
    store = capture_pb_fields(store, [
        ([{"index": 0}, {"index": 1}], [70, 30], "thresholds", "limit"),
        ([{"index": 0}, {"index": 1}], [100, 0], "thresholds", "score"),
        ([{"index": 0}], [-50], "thresholds", "default"),
        ([{"index": 0}], [-3.0], "range", "min"),
    ])
    assert store["thresholds"]["rows"]["0"] == {"limit": 70, "score": 100}
    assert store["thresholds"]["rows"]["1"] == {"limit": 30, "score": 0}
    assert store["thresholds"]["default"] == -50
    assert store["range"]["min"] == -3.0
