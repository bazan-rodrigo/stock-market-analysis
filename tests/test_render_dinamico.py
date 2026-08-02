"""Los renders que arman controles DENTRO de un callback tienen que dibujarlos.

Segunda capa de la red que dejó pasar el modal de estrategias vacío (ver
test_dash_props.py para la primera, estática, y el bug que la motivó). Acá se
ejercitan de verdad los renders que construyen filas y árboles a partir de un
store: si uno explota, o deja de emitir un control, la suite falla.

Los casos se DERIVAN de las fuentes únicas que declara CLAUDE.md —
`strategy_filter.{NUMERIC,CATEGORICAL}_OPERATORS`, `signal_engine.FORMULA_TYPES`,
`indicator_catalog.CATEGORICAL_VALUES`— y no de una lista propia: un operador o
una fórmula que se agregue al motor entra acá solo, y si no se puede dibujar,
rompe la suite. Los packs de strategy_packs/ se suman como material real cuando
están, pero nada depende de que exista un archivo con cierto nombre (ya
desaparecieron una vez mientras se escribía este test).

Cubre los renders importables sin base ni red. Los de sintéticos y evolución
piden una app Dash instanciada y yfinance: su modo de falla real —una prop que
el componente no acepta— lo cubre el análisis estático, que lee el fuente y no
necesita importarlos.
"""
import json
from pathlib import Path

import pytest

from app.callbacks import signal_params_ui as pb
from app.callbacks import strategy_filter_ui as ft
from app.services.indicator_catalog import CATEGORICAL_VALUES
from app.services.signal_engine import FORMULA_TYPES
from app.services.strategy_filter import CATEGORICAL_OPERATORS, NUMERIC_OPERATORS

PACKS = Path(__file__).resolve().parent.parent / "strategy_packs"

IND_NUM = "dist_sma200"                        # numérico cualquiera
IND_CAT = sorted(CATEGORICAL_VALUES)[0]        # el primero del catálogo real


def _walk(node):
    """Todos los componentes del árbol, sin depender del anidamiento."""
    if isinstance(node, (list, tuple)):
        for item in node:
            yield from _walk(item)
        return
    if not hasattr(node, "_prop_names"):
        return
    yield node
    yield from _walk(getattr(node, "children", None))


def _ids(arbol, tipo):
    """Índices de los controles pattern-matching de un tipo."""
    return sorted(
        n.id["index"] for n in _walk(arbol)
        if isinstance(getattr(n, "id", None), dict) and n.id.get("type") == tipo
    )


# ── Constructor del filtro de elegibilidad ────────────────────────────────────

def _cond(key, operador, valor):
    return {"cond": {"left": {"type": "indicator", "key": key},
                     "operator": operador,
                     "right": {"type": "const", "value": valor}}}


def _opts(claves=()):
    """Catálogo con la misma forma que build_filter_opts (que lo arma desde la
    base). Los valores categóricos salen del catálogo real del código."""
    claves = set(claves) | {f"ind:{IND_NUM}", f"ind:{IND_CAT}"}
    return {
        "operands": [{"label": k, "value": k} for k in sorted(claves)],
        "numeric": [f"ind:{IND_NUM}"],
        "cat_values": {f"ind:{code}": [{"label": v, "value": v}
                                       for v in sorted(vals)]
                       for code, vals in CATEGORICAL_VALUES.items()},
        "no_hist": [],
    }


@pytest.mark.parametrize("operador", sorted(NUMERIC_OPERATORS))
def test_se_dibuja_una_condicion_numerica_por_cada_operador(operador):
    """Derivado de NUMERIC_OPERATORS: un operador nuevo en el motor que la UI
    no sepa dibujar rompe acá."""
    tree = json.dumps({"op": "AND", "children": [_cond(IND_NUM, operador, 0)]})
    store = ft.tree_to_store(tree)

    arbol = ft.render_filter_tree(store, _opts())

    assert len(_ids(arbol, "strf-left")) == 1, f"'{operador}' no se dibujó"
    # val + vs (este último oculto cuando no aplica) siempre salen de a pares:
    # las colecciones ALL de los callbacks tienen que quedar alineadas.
    assert _ids(arbol, "strf-val") == _ids(arbol, "strf-vs") == _ids(arbol, "strf-op")


@pytest.mark.parametrize("operador", sorted(CATEGORICAL_OPERATORS))
def test_se_dibuja_una_condicion_categorica_por_cada_operador(operador):
    """Ídem con CATEGORICAL_OPERATORS y los valores reales del catálogo."""
    valores = sorted(CATEGORICAL_VALUES[IND_CAT])
    valor = valores[:2] if operador in ("in", "not_in") else valores[0]
    tree = json.dumps({"op": "AND", "children": [_cond(IND_CAT, operador, valor)]})
    store = ft.tree_to_store(tree)

    arbol = ft.render_filter_tree(store, _opts())

    assert len(_ids(arbol, "strf-left")) == 1, f"'{operador}' no se dibujó"
    assert _ids(arbol, "strf-val") == _ids(arbol, "strf-op")


def test_se_dibujan_todas_las_condiciones_de_un_arbol_con_grupos():
    """Un filtro como los que arma la gente: varias condiciones y un grupo
    anidado con otro operador lógico."""
    tree = json.dumps({"op": "AND", "children": [
        _cond(IND_CAT, "in", sorted(CATEGORICAL_VALUES[IND_CAT])[:3]),
        _cond(IND_NUM, ">", 0),
        {"op": "OR", "children": [_cond(IND_NUM, "<", 10),
                                  _cond(IND_NUM, ">=", 50)]},
    ]})
    store = ft.tree_to_store(tree)
    condiciones = sum(1 for n in store["nodes"].values()
                      if n.get("kind") == "cond")

    arbol = ft.render_filter_tree(store, _opts())

    assert len(_ids(arbol, "strf-left")) == condiciones == 4
    assert len(_ids(arbol, "strf-groupop")) == 2, "faltan los AND/OR raíz y anidado"


def test_el_filtro_vacio_no_dibuja_condiciones():
    assert _ids(ft.render_filter_tree(ft.empty_filter_store(), _opts()),
                "strf-left") == []


def test_sin_catalogo_todavia_no_se_rompe():
    """Al abrir el modal el árbol se renderiza antes de que lleguen las
    opciones."""
    assert ft.render_filter_tree(ft.empty_filter_store(), None) is not None


# ── Constructor de parámetros de señal ────────────────────────────────────────

CATALOGO = {"signal_opts": [],
            "cat_values": {c: sorted(v) for c, v in CATEGORICAL_VALUES.items()}}

# Params mínimos por fórmula. La clave es que el conjunto se compara contra
# FORMULA_TYPES en el test de abajo: una fórmula nueva sin caso rompe la suite
# en vez de quedar sin ejercitar.
PARAMS_POR_FORMULA = {
    "discrete_map": {"map": {v: 50 for v in sorted(CATEGORICAL_VALUES[IND_CAT])}},
    "threshold":    {"thresholds": [[70, -100], [30, 50], [None, 100]]},
    "range":        {"min": 2.0, "max": -2.0, "clamp": True},
}
# Por fórmula con filas repetidas: (sección del store, los dos controles que
# cada fila tiene que emitir).
FILAS_POR_FORMULA = {
    "discrete_map": ("map",        ("sigpb-map-cat", "sigpb-map-score")),
    "threshold":    ("thresholds", ("sigpb-th-limit", "sigpb-th-score")),
}
# range no repite filas: son tres campos fijos.
CAMPOS_DE_RANGE = ("sigpb-range-min", "sigpb-range-max", "sigpb-range-clamp")


def test_hay_un_caso_por_cada_formula_del_motor():
    """El trinquete del trinquete: sin esto, agregar una fórmula al motor
    dejaría su editor sin ejercitar y nadie se enteraría."""
    assert set(PARAMS_POR_FORMULA) == set(FORMULA_TYPES)


@pytest.mark.parametrize("ftype", sorted(FORMULA_TYPES))
def test_el_editor_dibuja_los_parametros_de_cada_formula(ftype):
    store = pb.builder_from_params(ftype, json.dumps(PARAMS_POR_FORMULA[ftype]))
    assert store is not None, f"{ftype}: el editor no puede representarla"

    body, _style = pb.render_builder(store, CATALOGO, ftype, IND_CAT,
                                     advanced=False)

    assert body is not None
    if ftype in FILAS_POR_FORMULA:
        seccion, controles = FILAS_POR_FORMULA[ftype]
        esperados = sorted(store[seccion]["uids"])
        for tipo in controles:
            assert _ids(body, tipo) == esperados, (
                f"{ftype}: se dibujaron {len(_ids(body, tipo))} '{tipo}' de "
                f"{len(esperados)} filas")
    else:
        faltan = [c for c in CAMPOS_DE_RANGE if not _ids(body, c)]
        assert not faltan, f"range: faltan los campos {faltan}"


def _señales_publicadas():
    """Las señales de los packs que haya en el repo, si hay alguno."""
    return [
        pytest.param(sig, id=f"{archivo.stem}:{sig['key']}")
        for archivo in sorted(PACKS.glob("*.json"))
        for sig in json.loads(archivo.read_text(encoding="utf-8")).get("signals") or []
        if sig.get("formula_type") in FORMULA_TYPES
    ]


@pytest.mark.parametrize("sig", _señales_publicadas())
def test_el_editor_dibuja_las_señales_de_los_packs_publicados(sig):
    """Material real: lo que entra por un pack tiene que poder editarse en
    pantalla. Se saltea solo si no hay packs en el repo."""
    ftype = sig["formula_type"]
    store = pb.builder_from_params(ftype, json.dumps(sig["params"]))
    assert store is not None, f"{sig['key']}: el editor no puede representarla"

    body, _ = pb.render_builder(store, CATALOGO, ftype,
                                sig.get("indicator_key"), advanced=False)

    assert body is not None
    if ftype in FILAS_POR_FORMULA:
        seccion, controles = FILAS_POR_FORMULA[ftype]
        for tipo in controles:
            assert _ids(body, tipo) == sorted(store[seccion]["uids"])


def test_el_modo_avanzado_no_dibuja_el_editor():
    body, _ = pb.render_builder(pb.empty_params_store(), CATALOGO,
                                "threshold", "rsi_daily", advanced=True)

    assert _ids(body, "sigpb-th-limit") == []


def test_sin_tipo_de_formula_el_editor_pide_elegirlo():
    body, style = pb.render_builder(pb.empty_params_store(), CATALOGO, None,
                                    None, advanced=False)

    assert body is not None and style == {"display": "none"}
