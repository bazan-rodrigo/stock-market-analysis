"""compile_evaluator ≡ evaluate — igualdad EXACTA, por propiedad.

Los evaluadores compilados (closures con params horneados, ver
signal_engine.compile_evaluator) reemplazan a evaluate() en el loop caliente
del backfill: cualquier divergencia sería un bug de datos silencioso en toda
la historia de señales. hypothesis genera params y valores al azar y exige
identidad de resultados (incluyendo None y la igualdad exacta de floats).
"""
import json
import math

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.signal_engine import compile_evaluator, evaluate

_KEYS = ["bullish", "bullish_strong", "lateral", "bearish",
         "bearish_strong", "otro", "x"]
_FINITE = st.floats(allow_nan=False, allow_infinity=False,
                    min_value=-1e6, max_value=1e6)


def _same(a, b):
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, float) and math.isnan(a):
        return isinstance(b, float) and math.isnan(b)
    return a == b


def _check(formula_type, params, value):
    compiled = compile_evaluator(formula_type, params, json.dumps(params))
    got = compiled(value)
    want = evaluate(formula_type, json.dumps(params), value, params=params)
    assert _same(got, want), (formula_type, params, value, got, want)


@settings(max_examples=300)
@given(
    mapping=st.dictionaries(st.sampled_from(_KEYS),
                            st.one_of(st.none(), st.integers(-100, 100),
                                      _FINITE)),
    value=st.one_of(st.none(), st.sampled_from(_KEYS), st.text(max_size=5)),
)
def test_discrete_map_identico(mapping, value):
    _check("discrete_map", {"map": mapping}, value)


@settings(max_examples=300)
@given(
    pairs=st.lists(st.tuples(st.one_of(st.none(), _FINITE), _FINITE),
                   max_size=6),
    value=st.one_of(st.none(), _FINITE),
)
def test_threshold_identico(pairs, value):
    _check("threshold", {"thresholds": [list(p) for p in pairs]}, value)


@settings(max_examples=300)
@given(
    vmin=_FINITE, vmax=_FINITE, clamp=st.booleans(),
    value=st.one_of(st.none(), _FINITE,
                    st.floats(allow_nan=True, allow_infinity=True)),
)
def test_range_identico(vmin, vmax, clamp, value):
    # incluye span=0 (cuando vmin==vmax), NaN e infinitos como valor
    _check("range", {"min": vmin, "max": vmax, "clamp": clamp}, value)


def test_formula_desconocida_y_params_none():
    assert compile_evaluator("zaraza", {"a": 1})(5) is None
    assert evaluate("zaraza", "{}", 5, params={"a": 1}) is None
    # params None → el compilado cae al wrapper de evaluate (parsea el json)
    c = compile_evaluator("range", None, json.dumps({"min": 0, "max": 10}))
    assert c(5) == evaluate("range", json.dumps({"min": 0, "max": 10}), 5)
