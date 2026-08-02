"""Filtro de elegibilidad de estrategias: evaluación del árbol AND/OR,
comparaciones por tipo, faltantes, validación de esquema y detección de
cadenas sin historia. Todo lógica pura — sin DB (salvo los helpers de
detección, que usan stubs)."""
from types import SimpleNamespace

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


# ── Atributos: se comparan contra su id de catálogo ───────────────────────────
# Un atributo guarda el ID de la fila (sector, mercado, …): un entero que NO es
# una cantidad. Tipándolo como texto, comparar el atributo contra su propio id
# daba "tipos incompatibles (str vs num)" y no se podía guardar una condición
# tan común como «tipo de instrumento = Equity». No se notaba porque in/not_in
# toma otra rama de la validación — el constructor de filtros suele usar in, y
# el bug aparecía al elegir "=" o al importar un pack que lo usara.

def test_acepta_atributo_igual_a_su_id():
    assert _validate(_cond(_attr("sector"), "=", _const(4))) == []

def test_acepta_atributo_distinto_de_su_id():
    assert _validate(_cond(_attr("instrument_type"), "!=", _const(7))) == []

def test_acepta_atributo_igual_a_un_nombre():
    """Antes de resolver el nombre a id (validación offline de un pack)."""
    assert _validate(_cond(_attr("sector"), "=", _const("Technology"))) == []

def test_acepta_atributo_en_lista_de_ids():
    assert _validate(_cond(_attr("market"), "in", _const([1, 2]))) == []

def test_rechaza_ordenar_por_atributo():
    """Un id de catálogo no tiene orden: 'sector > 3' no significa nada."""
    errors = _validate(_cond(_attr("sector"), ">", _const(3)))
    assert any("no se ordenan" in e for e in errors)

def test_el_arbol_que_arma_el_constructor_con_igual_es_valido():
    """Forma exacta que persiste la UI al elegir «Tipo de instrumento = Equity»
    (el dropdown de valores usa el id de la fila, un entero)."""
    tree = {"op": "AND", "children": [
        {"cond": {"left": {"type": "attribute", "key": "instrument_type"},
                  "operator": "=",
                  "right": {"type": "const", "value": 4}}}]}
    assert _validate(tree) == []


# ── El atributo benchmark y su "(sin benchmark)" ──────────────────────────────

def _fila(**overrides):
    """Fila de `assets` como la devuelve asset_attributes_query."""
    base = dict(sector_id=1, market_id=2, industry_id=3, country_id=4,
                instrument_type_id=5, currency_id=6, benchmark_id=7,
                synthetic_type=None)
    return SimpleNamespace(**{**base, **overrides})


def test_el_dict_de_atributos_cubre_todos_los_filtrables():
    """attributes_from_asset_row es la fuente única del dict que evalúa el
    filtro: un atributo declarado en ATTRIBUTE_KEYS que no salga de ahí se
    evaluaría siempre como vacío, o sea la condición siempre falsa."""
    from app.services.strategy_filter import ATTRIBUTE_KEYS, attributes_from_asset_row

    assert set(attributes_from_asset_row(_fila())) == set(ATTRIBUTE_KEYS)


def test_todo_atributo_vacio_llega_con_el_valor_de_hueco():
    """El NULL se materializa: si llegara como None, NINGUNA condición sobre
    ese atributo se cumpliría (ni siquiera !=) y el hueco sería inexpresable."""
    from app.services.strategy_filter import (
        ATTRIBUTE_KEYS, ATTRIBUTE_NONE_ID, attributes_from_asset_row)

    vacia = _fila(sector_id=None, market_id=None, industry_id=None,
                  country_id=None, instrument_type_id=None, currency_id=None,
                  benchmark_id=None, synthetic_type=None)
    valores = attributes_from_asset_row(vacia)
    assert set(valores) == set(ATTRIBUTE_KEYS)
    assert all(v == ATTRIBUTE_NONE_ID for v in valores.values())


def test_el_tipo_de_sintetico_viaja_como_texto():
    """Único atributo con valores de texto: los otros son ids de catálogo."""
    from app.services.strategy_filter import attributes_from_asset_row

    assert attributes_from_asset_row(_fila(synthetic_type="ratio"))["synthetic"] \
        == "ratio"


def test_distinto_de_sin_benchmark_deja_pasar_solo_a_los_que_tienen():
    """El caso de uso: sacar del ranking a los activos donde un indicador que
    depende del benchmark (relative_strength_52w) nunca se va a calcular."""
    from app.services.strategy_filter import ATTRIBUTE_NONE_ID

    tree = _cond(_attr("benchmark"), "!=", _const(ATTRIBUTE_NONE_ID))
    con    = {"benchmark": 12}
    sin    = {"benchmark": ATTRIBUTE_NONE_ID}
    assert evaluate_tree(tree, 1, {}, con) is True
    assert evaluate_tree(tree, 2, {}, sin) is False


def test_igual_a_sin_benchmark_aisla_a_los_que_no_tienen():
    from app.services.strategy_filter import ATTRIBUTE_NONE_ID

    tree = _cond(_attr("benchmark"), "=", _const(ATTRIBUTE_NONE_ID))
    assert evaluate_tree(tree, 1, {}, {"benchmark": ATTRIBUTE_NONE_ID}) is True
    assert evaluate_tree(tree, 2, {}, {"benchmark": 12}) is False


def test_benchmark_es_un_atributo_valido_y_no_se_ordena():
    assert _validate(_cond(_attr("benchmark"), "in", _const([12, 34]))) == []
    errors = _validate(_cond(_attr("benchmark"), ">", _const(12)))
    assert any("no se ordenan" in e for e in errors)


def test_los_atributos_nuevos_son_validos():
    assert _validate(_cond(_attr("currency"), "=", _const(3))) == []
    assert _validate(_cond(_attr("synthetic"), "!=", _const("ratio"))) == []


def test_excluir_los_sinteticos_deja_pasar_al_activo_comun():
    """«Tipo de sintético = (no sintético)» saca del universo los calculados —
    entre ellos los que crea la conversión de divisas, que duplican activos."""
    from app.services.strategy_filter import ATTRIBUTE_NONE_ID

    tree = _cond(_attr("synthetic"), "=", _const(ATTRIBUTE_NONE_ID))
    assert evaluate_tree(tree, 1, {}, {"synthetic": ATTRIBUTE_NONE_ID}) is True
    assert evaluate_tree(tree, 2, {}, {"synthetic": "ratio"}) is False


def test_el_filtro_resuelve_el_indicador_virtual_sin_tabla(monkeypatch):
    """`last_close` no tiene tabla ind_*: la carga caía en NoSuchTableError,
    devolvía {} y la condición quedaba SIEMPRE FALSA con solo un warning en el
    log — un pack podía filtrar por precio y filtrar todo a cero."""
    from datetime import date

    from app.services import strategy_filter as sf

    llamadas = []

    def _fake(_session, code, _fecha):
        llamadas.append(code)
        return {7: 12.5}

    monkeypatch.setattr(sf, "_load_virtual_asof", _fake)
    tree = _cond(_ind("last_close"), ">", _const(10))
    values = sf.load_operand_values(object(), tree, date(2026, 1, 2))
    assert llamadas == ["last_close"]
    assert values[("indicator", "last_close", "historic")] == {7: 12.5}


def test_last_close_se_lee_as_of_contra_la_base():
    """El SQL del virtual es nuevo y no tiene tabla `ind_*` que lo respalde:
    se ejercita de verdad contra sqlite. Un activo que no cotizó ese día entra
    igual con su último precio (as-of); uno con precios más viejos que el tope
    de antigüedad, no."""
    import datetime

    import sqlalchemy as sa

    from app.database import Base, Session, engine, get_session
    from app.models import Asset, Price
    from app.models.indicator_store import ASOF_MAX_LOOKBACK_DAYS
    from app.services.strategy_filter import _load_virtual_asof

    Session.remove()
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM prices"))
        conn.execute(sa.text("DELETE FROM assets"))

    hoy = datetime.date(2026, 1, 2)
    s = get_session()
    for aid, ticker in ((901, "HOY"), (902, "AYER"), (903, "VIEJO")):
        s.add(Asset(id=aid, ticker=ticker, name=ticker, price_source_id=1))
    s.add(Price(asset_id=901, date=hoy, close=10.0))
    s.add(Price(asset_id=902, date=hoy - datetime.timedelta(days=1), close=20.0))
    s.add(Price(asset_id=903,
                date=hoy - datetime.timedelta(days=ASOF_MAX_LOOKBACK_DAYS + 5),
                close=30.0))
    s.commit()

    valores = _load_virtual_asof(s, "last_close", hoy)
    assert valores == {901: 10.0, 902: 20.0}

    Session.remove()


def test_distinto_de_un_valor_ahora_incluye_al_que_no_tiene_dato():
    """CAMBIO DE SEMÁNTICA al materializar el hueco: antes el activo sin sector
    no cumplía «sector != X» (su None no cumplía nada) y quedaba afuera."""
    from app.services.strategy_filter import ATTRIBUTE_NONE_ID

    tree = _cond(_attr("sector"), "!=", _const(3))
    assert evaluate_tree(tree, 1, {}, {"sector": ATTRIBUTE_NONE_ID}) is True
    assert evaluate_tree(tree, 2, {}, {"sector": 3}) is False


# ── legacy_asset_filter_to_tree ───────────────────────────────────────────────

def test_legacy_asset_filter_se_convierte():
    from app.services.strategy_filter import legacy_asset_filter_to_tree
    import json
    tree = json.loads(legacy_asset_filter_to_tree(
        '{"sector_id": 3, "instrument_type_id": 1}'))
    assert tree["op"] == "AND" and len(tree["children"]) == 2
    conds = {c["cond"]["left"]["key"]: c["cond"]["right"]["value"]
             for c in tree["children"]}
    assert conds == {"sector": 3, "instrument_type": 1}

def test_legacy_asset_filter_vacio_o_roto():
    from app.services.strategy_filter import legacy_asset_filter_to_tree
    assert legacy_asset_filter_to_tree(None) is None
    assert legacy_asset_filter_to_tree("{}") is None
    assert legacy_asset_filter_to_tree("{roto") is None
