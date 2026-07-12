"""Filtro de elegibilidad de estrategias: evaluación del árbol AND/OR,
comparaciones por tipo, faltantes, validación de esquema y detección de
cadenas sin historia. Todo lógica pura — sin DB (salvo los helpers de
detección, que usan stubs)."""
import pytest

from app.services.strategy_filter import (
    _compare,
    collect_operands,
    evaluate_tree,
    parse_tree,
    uses_current_resolution,
    validate_tree,
)


def _cond(left, operator, right, resolution=None):
    cond = {"left": left, "operator": operator, "right": right}
    if resolution:
        cond["resolution"] = resolution
    return {"cond": cond}


def _ind(key):
    return {"type": "indicator", "key": key}


def _sig(key):
    return {"type": "signal", "key": key}


def _attr(key):
    return {"type": "attribute", "key": key}


def _const(value):
    return {"type": "const", "value": value}


# Catálogos de prueba para validate_tree
_IND_CODES = {"rsi_daily": "num", "trend_daily": "str", "sma50": "num",
              "sma100": "num", "best_sma_d": "num"}
_SIG_KEYS = {"rsi_low", "momentum"}
_CATEGORICAL = {"trend_daily": frozenset({"bullish", "bearish", "lateral"})}


def _validate(tree):
    return validate_tree(tree, indicator_codes=_IND_CODES,
                         signal_keys=_SIG_KEYS,
                         categorical_values=_CATEGORICAL)


# ── _compare ──────────────────────────────────────────────────────────────────

def test_compare_numericos():
    assert _compare(71.0, 70, ">")
    assert not _compare(70.0, 70, ">")
    assert _compare(70.0, 70, ">=")
    assert _compare(30.0, 70, "<")
    assert _compare(70.0, 70.0, "=")
    assert _compare(70.0, 69.9, "!=")

def test_compare_faltante_es_falso():
    for op in ("=", "!=", ">", "<", "in", "not_in"):
        assert not _compare(None, 70, op)
        assert not _compare(70, None, op)

def test_compare_strings_igualdad():
    assert _compare("bullish", "bullish", "=")
    assert _compare("bullish", "bearish", "!=")
    assert not _compare("bullish", "bearish", "=")

def test_compare_string_con_operador_ordenado_es_falso():
    assert not _compare("bullish", "bearish", ">")
    assert not _compare("bullish", 70, "<")

def test_compare_in_not_in():
    assert _compare("bullish", ["bullish", "lateral"], "in")
    assert not _compare("bearish", ["bullish", "lateral"], "in")
    assert _compare("bearish", ["bullish", "lateral"], "not_in")

def test_compare_in_mezcla_int_y_str():
    # atributos: ids int en DB, la UI puede guardar la lista como strings
    assert _compare(3, ["3", "5"], "in")
    assert _compare("3", [3, 5], "in")

def test_compare_in_sin_lista_es_falso():
    assert not _compare("bullish", "bullish", "in")


# ── evaluate_tree ─────────────────────────────────────────────────────────────

_VALUES = {
    ("indicator", "rsi_daily", "historic"): {1: 75.0, 2: 25.0},
    ("indicator", "sma50",     "historic"): {1: 100.0, 2: 100.0},
    ("indicator", "sma100",    "historic"): {1: 110.0, 2: 90.0},
    ("indicator", "trend_daily", "historic"): {1: "bullish", 2: "bearish"},
    ("indicator", "best_sma_d", "current"):  {1: 50.0},
    ("signal",    "rsi_low",   ""):          {1: -80.0, 2: 60.0},
}
_ATTRS = {1: {"sector": 3, "instrument_type": 1},
          2: {"sector": 5, "instrument_type": 4}}


def _eval(tree, asset_id):
    return evaluate_tree(tree, asset_id, _VALUES, _ATTRS[asset_id])


def test_condicion_simple_indicador_vs_constante():
    tree = _cond(_ind("rsi_daily"), ">", _const(70))
    assert _eval(tree, 1)
    assert not _eval(tree, 2)

def test_condicion_indicador_vs_indicador():
    tree = _cond(_ind("sma100"), ">", _ind("sma50"))
    assert _eval(tree, 1)      # 110 > 100
    assert not _eval(tree, 2)  # 90 > 100 es falso

def test_condicion_senal():
    tree = _cond(_sig("rsi_low"), "<", _const(0))
    assert _eval(tree, 1)
    assert not _eval(tree, 2)

def test_condicion_atributo_in():
    tree = _cond(_attr("instrument_type"), "in", _const([1, 4]))
    assert _eval(tree, 1)
    assert _eval(tree, 2)
    tree2 = _cond(_attr("sector"), "not_in", _const([5]))
    assert _eval(tree2, 1)
    assert not _eval(tree2, 2)

def test_condicion_categorica():
    tree = _cond(_ind("trend_daily"), "in", _const(["bullish", "lateral"]))
    assert _eval(tree, 1)
    assert not _eval(tree, 2)

def test_faltante_no_pasa():
    tree = _cond(_ind("best_sma_d"), ">", _const(10), resolution="current")
    assert _eval(tree, 1)
    assert not _eval(tree, 2)  # el activo 2 no tiene best_sma_d

def test_and_cortocircuito():
    tree = {"op": "AND", "children": [
        _cond(_ind("rsi_daily"), ">", _const(70)),
        _cond(_ind("trend_daily"), "=", _const("bullish")),
    ]}
    assert _eval(tree, 1)
    assert not _eval(tree, 2)

def test_or_y_anidamiento():
    # (rsi > 70) OR (rsi < 30 AND trend = bearish)
    tree = {"op": "OR", "children": [
        _cond(_ind("rsi_daily"), ">", _const(70)),
        {"op": "AND", "children": [
            _cond(_ind("rsi_daily"), "<", _const(30)),
            _cond(_ind("trend_daily"), "=", _const("bearish")),
        ]},
    ]}
    assert _eval(tree, 1)
    assert _eval(tree, 2)

def test_grupo_vacio_no_filtra():
    assert evaluate_tree({"op": "AND", "children": []}, 1, {}, {})


# ── parse_tree / collect_operands / uses_current_resolution ───────────────────

def test_parse_tree_none_y_json_roto():
    assert parse_tree(None) is None
    assert parse_tree("") is None
    assert parse_tree("{roto") is None
    assert parse_tree("{}") is None

def test_collect_operands():
    tree = {"op": "AND", "children": [
        _cond(_ind("rsi_daily"), ">", _const(70)),
        _cond(_ind("sma100"), ">", _ind("sma50")),
        _cond(_sig("rsi_low"), "<", _const(0)),
        _cond(_attr("sector"), "=", _const(3)),
        _cond(_ind("best_sma_d"), ">", _const(10), resolution="current"),
    ]}
    ops = collect_operands(tree)
    assert ("indicator", "rsi_daily", "historic") in ops
    assert ("indicator", "sma100", "historic") in ops
    assert ("indicator", "sma50", "historic") in ops
    assert ("signal", "rsi_low", "") in ops
    assert ("attribute", "sector", "") in ops
    assert ("indicator", "best_sma_d", "current") in ops
    # las constantes no se recolectan
    assert all(t != "const" for t, _, _ in ops)

def test_uses_current_resolution():
    historic = _cond(_ind("rsi_daily"), ">", _const(70))
    current  = _cond(_ind("best_sma_d"), ">", _const(10), resolution="current")
    assert not uses_current_resolution(historic)
    assert uses_current_resolution({"op": "AND", "children": [historic, current]})
    assert not uses_current_resolution(None)


# ── validate_tree ─────────────────────────────────────────────────────────────

def test_valida_arbol_correcto():
    tree = {"op": "AND", "children": [
        _cond(_ind("rsi_daily"), ">", _const(70)),
        {"op": "OR", "children": [
            _cond(_ind("trend_daily"), "in", _const(["bullish", "lateral"])),
            _cond(_ind("sma100"), ">", _ind("sma50")),
            _cond(_sig("rsi_low"), "<", _const(0)),
            _cond(_attr("sector"), "in", _const([3, 5])),
        ]},
    ]}
    assert _validate(tree) == []

def test_rechaza_operador_desconocido():
    assert _validate(_cond(_ind("rsi_daily"), "~", _const(70)))

def test_rechaza_indicador_desconocido():
    assert _validate(_cond(_ind("no_existe"), ">", _const(70)))

def test_rechaza_senal_desconocida():
    assert _validate(_cond(_sig("no_existe"), ">", _const(0)))

def test_rechaza_atributo_desconocido():
    assert _validate(_cond(_attr("color"), "=", _const(3)))

def test_rechaza_ordenado_sobre_categorico():
    errors = _validate(_cond(_ind("trend_daily"), ">", _const("bullish")))
    assert errors

def test_rechaza_tipos_incompatibles_en_igualdad():
    assert _validate(_cond(_ind("rsi_daily"), "=", _const("bullish")))

def test_rechaza_in_sin_lista():
    assert _validate(_cond(_ind("trend_daily"), "in", _const("bullish")))

def test_rechaza_lista_sin_in():
    assert _validate(_cond(_ind("rsi_daily"), ">", _const([70, 80])))

def test_rechaza_valor_fuera_de_catalogo():
    errors = _validate(_cond(_ind("trend_daily"), "in",
                             _const(["bullish", "inventado"])))
    assert any("inventado" in e for e in errors)

def test_rechaza_constante_a_la_izquierda():
    assert _validate(_cond(_const(70), "<", _ind("rsi_daily")))

def test_rechaza_grupo_vacio():
    assert _validate({"op": "AND", "children": []})

def test_rechaza_op_desconocido():
    assert _validate({"op": "XOR", "children": [
        _cond(_ind("rsi_daily"), ">", _const(70))]})

def test_rechaza_resolution_desconocida():
    assert _validate(_cond(_ind("rsi_daily"), ">", _const(70),
                           resolution="magic"))
