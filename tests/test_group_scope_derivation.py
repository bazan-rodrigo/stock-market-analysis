"""Derivación de qué grupos hace falta calcular para una señal de grupo.

Dos piezas puras (sin BD):
- strategy_filter.restricted_attribute_ids: qué ids de un atributo permite el
  filtro de una estrategia (o None = todos).
- signal_backfill_range._derive_needed_groups: cruza las señales de grupo con
  las estrategias que las consumen para decidir qué (group_type, group_id)
  calcular — el corazón de "solo calculo Argentina, no Estados Unidos".
"""
from types import SimpleNamespace

from app.services import strategy_filter
from app.services.signal_backfill_range import _derive_needed_groups


def _leaf(attr, op, value):
    return {"cond": {"left": {"type": "attribute", "key": attr},
                     "operator": op,
                     "right": {"type": "const", "value": value}}}


# ── restricted_attribute_ids ────────────────────────────────────────────────

def test_restricted_sin_arbol_es_todos():
    assert strategy_filter.restricted_attribute_ids(None, "country") is None


def test_restricted_igualdad():
    assert strategy_filter.restricted_attribute_ids(
        _leaf("country", "=", 5), "country") == {5}


def test_restricted_in():
    assert strategy_filter.restricted_attribute_ids(
        _leaf("country", "in", [5, 7]), "country") == {5, 7}


def test_restricted_otro_atributo_no_restringe():
    assert strategy_filter.restricted_attribute_ids(
        _leaf("sector", "=", 3), "country") is None


def test_restricted_not_in_no_acota():
    assert strategy_filter.restricted_attribute_ids(
        _leaf("country", "not_in", [5]), "country") is None


def test_restricted_and_intersecta():
    tree = {"op": "AND", "children": [
        _leaf("country", "in", [5, 7, 9]),
        _leaf("country", "in", [7, 9, 11]),
    ]}
    assert strategy_filter.restricted_attribute_ids(tree, "country") == {7, 9}


def test_restricted_and_con_rama_irrelevante():
    tree = {"op": "AND", "children": [
        _leaf("country", "=", 5),
        _leaf("sector", "=", 3),          # no menciona country → no acota
    ]}
    assert strategy_filter.restricted_attribute_ids(tree, "country") == {5}


def test_restricted_or_une():
    tree = {"op": "OR", "children": [
        _leaf("country", "=", 5),
        _leaf("country", "=", 7),
    ]}
    assert strategy_filter.restricted_attribute_ids(tree, "country") == {5, 7}


def test_restricted_or_con_rama_abierta_es_todos():
    tree = {"op": "OR", "children": [
        _leaf("country", "=", 5),
        _leaf("sector", "=", 3),          # esta rama deja pasar cualquier país
    ]}
    assert strategy_filter.restricted_attribute_ids(tree, "country") is None


# ── _derive_needed_groups ───────────────────────────────────────────────────
# Firma: (types_with_signals, strategies, gtypes_by_id, gtypes_by_key).
# strategies: [{"tree", "components": [ns(signal_id, scope, group_type,
# group_id)], "signal_operands": set(keys)}]. La derivación mira SIEMPRE todas
# las estrategias (no hay parámetro de alcance).

_COUNTRY = {"country"}
# La señal de país de estos casos es id=10, key="pais_trend"
_GT_BY_ID  = {10: _COUNTRY}
_GT_BY_KEY = {"pais_trend": _COUNTRY}


def _comp(signal_id=10, scope=None, group_type=None, group_id=None):
    return SimpleNamespace(signal_id=signal_id, scope=scope,
                           group_type=group_type, group_id=group_id)


def _strat(tree, components, signal_operands=()):
    return {"tree": tree, "components": components,
            "signal_operands": set(signal_operands)}


def _derive(strategies, types=_COUNTRY):
    return _derive_needed_groups(types, strategies, _GT_BY_ID, _GT_BY_KEY)


def test_sin_tipos_con_senal_no_necesita_nada():
    assert _derive_needed_groups(set(), [], _GT_BY_ID, _GT_BY_KEY) == {}


def test_senal_suelta_sin_estrategia_calcula_todos():
    assert _derive([]) == {"country": None}


def test_own_group_restringido_por_filtro():
    strat = _strat(_leaf("country", "in", [5, 7]),
                   [_comp(scope="own_group", group_type="country")])
    assert _derive([strat]) == {"country": {5, 7}}


def test_own_group_sin_filtro_es_todos():
    strat = _strat(None, [_comp(scope="own_group", group_type="country")])
    assert _derive([strat]) == {"country": None}


def test_specific_group_puntual():
    strat = _strat(None, [_comp(scope="specific_group",
                                group_type="country", group_id=5)])
    assert _derive([strat]) == {"country": {5}}


def test_dos_estrategias_unen_paises():
    ar = _strat(_leaf("country", "=", 5),
                [_comp(scope="own_group", group_type="country")])
    br = _strat(_leaf("country", "=", 7),
                [_comp(scope="own_group", group_type="country")])
    assert _derive([ar, br]) == {"country": {5, 7}}


def test_una_restringe_otra_abre_gana_todos():
    ar  = _strat(_leaf("country", "=", 5),
                 [_comp(scope="own_group", group_type="country")])
    all_ = _strat(None, [_comp(scope="own_group", group_type="country")])
    assert _derive([ar, all_]) == {"country": None}


def test_scope_directo_sobre_senal_de_grupo_usa_filtro():
    # componente con scope directo (None) cuya señal es de grupo → usa el
    # filtro para acotar los grupos del valor por-activo
    strat = _strat(_leaf("country", "in", [5]), [_comp(scope=None)])
    assert _derive([strat]) == {"country": {5}}


def test_senal_de_grupo_en_filtro_necesita_todos():
    # el filtro usa la señal de grupo como operando → se evalúa sobre todos los
    # candidatos antes de filtrar, hacen falta todos los países
    strat = _strat(None, [], signal_operands={"pais_trend"})
    assert _derive([strat]) == {"country": None}
