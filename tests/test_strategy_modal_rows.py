"""El modal de estrategias tiene que DIBUJAR las filas de componentes.

Regresión real (producción, ago-2026): un `title=` en el `dbc.Input` del peso
hacía que dash-bootstrap-components 2.x tirara TypeError al construir la fila.
Como el armado ocurre DENTRO del callback, la excepción no rompe la pantalla:
se come la salida y el modal muestra la lista de componentes vacía — una
estrategia con cuatro señales se abría sin ninguna, y la previsualización decía
"SCORE = (sin componentes)". Los datos estaban intactos; lo roto era el render.

Ningún test construía componentes Dash, así que el error solo era visible
ejercitando la pantalla a mano. Esto lo ata: si una fila deja de construirse
—por una prop que el paquete ya no acepta, o por cualquier otra excepción—
la suite falla acá.

El recorrido del árbol es por id y no por posición: envolver un control en otro
contenedor es un cambio de layout legítimo y no debe romper este test.
"""
import pytest

from app.callbacks import admin_strategies_callbacks as cb


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


def _por_indice(rows, tipo):
    """{index: componente} para los ids pattern-matching de un tipo dado."""
    return {
        node.id["index"]: node
        for node in _walk(rows)
        if isinstance(getattr(node, "id", None), dict)
        and node.id.get("type") == tipo
    }


def _store(items):
    return {
        "uids": list(range(len(items))),
        "counter": len(items),
        "initial_values": {
            str(i): {"signal_key": key, "weight": w}
            for i, (key, w) in enumerate(items)
        },
    }


COMPONENTES = [("rsi_señal", 3.0), ("fuerza_relativa_52w", 2.0),
               ("dist_sma_pullback_d", 2.0), ("tendencia_d", 1.0)]
OPCIONES = [{"label": f"{k} — {k}", "value": k} for k, _ in COMPONENTES]


def test_render_dibuja_una_fila_por_componente():
    rows = cb.render_comp_rows(_store(COMPONENTES), OPCIONES)

    assert len(rows) == len(COMPONENTES)
    for tipo in ("str-comp-signal", "str-comp-weight", "str-remove-comp"):
        assert sorted(_por_indice(rows, tipo)) == [0, 1, 2, 3], (
            f"faltan controles '{tipo}': la fila no se construyó entera")


def test_render_conserva_señal_y_peso_de_cada_componente():
    rows = cb.render_comp_rows(_store(COMPONENTES), OPCIONES)
    señales = _por_indice(rows, "str-comp-signal")
    pesos   = _por_indice(rows, "str-comp-weight")

    for i, (key, weight) in enumerate(COMPONENTES):
        assert señales[i].value == key
        assert pesos[i].value == weight


def test_render_ofrece_las_señales_del_catalogo():
    rows = cb.render_comp_rows(_store(COMPONENTES), OPCIONES)

    for dropdown in _por_indice(rows, "str-comp-signal").values():
        assert dropdown.options == OPCIONES


@pytest.mark.parametrize("peso", [-2.5, -1, 0.01, 7])
def test_el_peso_admite_signo(peso):
    """El input NO lleva min=0: un peso negativo invierte el aporte de la
    señal (ver _compute_asset_score). Si alguien reintroduce el mínimo, el
    navegador marcaría inválido un valor que el motor sí acepta."""
    rows = cb.render_comp_rows(_store([("rsi_señal", peso)]), OPCIONES)
    campo = _por_indice(rows, "str-comp-weight")[0]

    assert campo.value == peso
    assert getattr(campo, "min", None) is None


def test_sin_componentes_no_hay_filas():
    assert cb.render_comp_rows(
        {"uids": [], "counter": 0, "initial_values": {}}, OPCIONES) == []


def test_render_no_depende_de_que_las_opciones_ya_esten_cargadas():
    """Al abrir el modal las filas se renderizan antes de que lleguen las
    opciones de señal (ver el comentario del callback): igual tiene que
    dibujar las filas, no descartarlas."""
    rows = cb.render_comp_rows(_store(COMPONENTES), None)

    assert len(rows) == len(COMPONENTES)
    assert sorted(_por_indice(rows, "str-comp-signal")) == [0, 1, 2, 3]
