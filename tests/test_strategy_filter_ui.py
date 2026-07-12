"""Conversión store (UI del constructor) ↔ árbol JSON (strategy_filter):
ida y vuelta, condiciones incompletas, resolution=current automática para
operandos sin historia."""
import json

from app.callbacks.strategy_filter_ui import (
    empty_filter_store,
    store_to_tree,
    tree_to_store,
)


def _cond_node(left, op, val=None, vs=None):
    return {"kind": "cond", "left": left, "op": op, "val": val, "vs": vs}


# ── store → árbol ─────────────────────────────────────────────────────────────

def test_store_vacio_da_none():
    tree, errors = store_to_tree(empty_filter_store(), set())
    assert tree is None and errors == []

def test_condicion_simple():
    store = {"nodes": {"0": {"kind": "group", "op": "AND", "children": [1]},
                       "1": _cond_node("ind:rsi_daily", ">", val=70)},
             "root": 0, "counter": 2}
    tree_json, errors = store_to_tree(store, set())
    assert errors == []
    tree = json.loads(tree_json)
    cond = tree["children"][0]["cond"]
    assert cond["left"] == {"type": "indicator", "key": "rsi_daily"}
    assert cond["operator"] == ">"
    assert cond["right"] == {"type": "const", "value": 70}
    assert "resolution" not in cond

def test_operando_vs_operando():
    store = {"nodes": {"0": {"kind": "group", "op": "AND", "children": [1]},
                       "1": _cond_node("ind:sma100", ">", vs="ind:sma50")},
             "root": 0, "counter": 2}
    tree_json, errors = store_to_tree(store, set())
    assert errors == []
    cond = json.loads(tree_json)["children"][0]["cond"]
    assert cond["right"] == {"type": "indicator", "key": "sma50"}

def test_in_escalar_se_convierte_a_lista():
    store = {"nodes": {"0": {"kind": "group", "op": "OR", "children": [1]},
                       "1": _cond_node("attr:sector", "in", val=3)},
             "root": 0, "counter": 2}
    tree_json, _ = store_to_tree(store, set())
    cond = json.loads(tree_json)["children"][0]["cond"]
    assert cond["right"]["value"] == [3]

def test_sin_historia_marca_resolution_current():
    store = {"nodes": {"0": {"kind": "group", "op": "AND", "children": [1]},
                       "1": _cond_node("ind:best_sma_d", ">", val=50)},
             "root": 0, "counter": 2}
    tree_json, _ = store_to_tree(store, {"ind:best_sma_d"})
    cond = json.loads(tree_json)["children"][0]["cond"]
    assert cond["resolution"] == "current"

def test_condicion_incompleta_da_error():
    store = {"nodes": {"0": {"kind": "group", "op": "AND", "children": [1]},
                       "1": _cond_node(None, None)},
             "root": 0, "counter": 2}
    tree, errors = store_to_tree(store, set())
    assert tree is None and errors

def test_condicion_sin_valor_da_error():
    store = {"nodes": {"0": {"kind": "group", "op": "AND", "children": [1]},
                       "1": _cond_node("ind:rsi_daily", ">")},
             "root": 0, "counter": 2}
    tree, errors = store_to_tree(store, set())
    assert tree is None and errors

def test_grupo_anidado_vacio_se_omite():
    store = {"nodes": {"0": {"kind": "group", "op": "AND", "children": [1, 2]},
                       "1": _cond_node("ind:rsi_daily", ">", val=70),
                       "2": {"kind": "group", "op": "OR", "children": []}},
             "root": 0, "counter": 3}
    tree_json, errors = store_to_tree(store, set())
    assert errors == []
    assert len(json.loads(tree_json)["children"]) == 1


# ── árbol → store → árbol (ida y vuelta) ─────────────────────────────────────

def test_ida_y_vuelta():
    original = {"op": "AND", "children": [
        {"cond": {"left": {"type": "indicator", "key": "rsi_daily"},
                  "operator": ">",
                  "right": {"type": "const", "value": 70}}},
        {"op": "OR", "children": [
            {"cond": {"left": {"type": "attribute", "key": "instrument_type"},
                      "operator": "in",
                      "right": {"type": "const", "value": [1, 4]}}},
            {"cond": {"left": {"type": "indicator", "key": "sma100"},
                      "operator": ">",
                      "right": {"type": "indicator", "key": "sma50"}}},
        ]},
    ]}
    store = tree_to_store(json.dumps(original))
    regen_json, errors = store_to_tree(store, set())
    assert errors == []
    assert json.loads(regen_json) == original

def test_tree_to_store_none_y_roto():
    assert tree_to_store(None) == empty_filter_store()
    assert tree_to_store("{roto") == empty_filter_store()

def test_raiz_condicion_suelta_se_envuelve_en_grupo():
    tree = {"cond": {"left": {"type": "indicator", "key": "rsi_daily"},
                     "operator": ">",
                     "right": {"type": "const", "value": 70}}}
    store = tree_to_store(json.dumps(tree))
    root = store["nodes"][str(store["root"])]
    assert root["kind"] == "group" and len(root["children"]) == 1
