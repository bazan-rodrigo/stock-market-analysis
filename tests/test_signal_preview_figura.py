"""La vista previa del editor de señales se CONSTRUYE de verdad.

Motivación (lección cara de este proyecto): un error dentro de un callback de
Dash no rompe la pantalla — la deja a medias, y se ve como un dato que falta.
Ya pasó: `dbc.Input` dejó de aceptar `title` en dbc 2.x y una estrategia con
cuatro componentes se abría vacía sin que ningún test fallara, porque los tests
son lógica pura y nunca construyen nada de la UI.

`preview_figure` devuelve una figura de Plotly, no un componente Dash, así que
sí se puede ejercitar acá. Estos tests la llaman con las tres fórmulas y con la
distribución real de fondo: un nombre mal importado o una clave que no existe
revienta acá y no en producción.
"""
from app.callbacks.signal_params_ui import preview_figure

_DIST_NUM = {
    "histograma": {"bins": [0, 25, 50, 75, 100], "conteos": [3, 10, 8, 2],
                   "fuera_izq": 1, "fuera_der": 1},
    "n": 24, "cobertura_pct": 80.0,
}
_DIST_CAT = {"categorias": [{"valor": "bullish", "n": 10, "pct": 50.0},
                            {"valor": "lateral", "n": 6, "pct": 30.0},
                            {"valor": "sin_mapear", "n": 4, "pct": 20.0}]}


def _store_range(vmin, vmax):
    return {"range": {"min": vmin, "max": vmax, "clamp": True}}


def _store_threshold():
    return {"thresholds": {"uids": [1, 2], "counter": 2, "default": -100,
                           "rows": {"1": {"limit": 70, "score": 100},
                                    "2": {"limit": 30, "score": 0}}}}


def _store_map():
    return {"map": {"uids": [1, 2], "counter": 2,
                    "rows": {"1": {"cat": "bullish", "score": 100},
                             "2": {"cat": "lateral", "score": 0}}}}


def test_range_con_la_distribucion_de_fondo():
    fig = preview_figure("range", _store_range(0, 100), _DIST_NUM)
    tipos = [t.type for t in fig.data]
    assert "bar" in tipos, "falta el histograma real de fondo"
    assert "scatter" in tipos, "falta la curva de la señal"


def test_threshold_con_la_distribucion_de_fondo():
    fig = preview_figure("threshold", _store_threshold(), _DIST_NUM)
    assert "bar" in [t.type for t in fig.data]


def test_el_mapa_discreto_muestra_las_categorias_que_no_estan_mapeadas():
    """Una categoría sin mapear deja la señal MUDA: no vale cero, se saltea y
    los pesos se renormalizan a favor de ese activo. Que aparezca en el gráfico
    es la única forma de verla antes de guardar."""
    fig = preview_figure("discrete_map", _store_map(), _DIST_CAT)
    barras = next(t for t in fig.data if t.type == "bar")
    assert "sin_mapear" in list(barras.x)


def test_sin_distribucion_sigue_dibujando_la_formula_sola():
    """El fondo es contexto: si la base no contestó, la vista previa tiene que
    seguir mostrando la curva en vez de quedar vacía."""
    for ftype, store in (("range", _store_range(0, 100)),
                         ("threshold", _store_threshold()),
                         ("discrete_map", _store_map())):
        fig = preview_figure(ftype, store, None)
        assert fig.data, f"{ftype}: la vista previa quedó vacía sin distribución"


def test_una_distribucion_vacia_no_rompe():
    fig = preview_figure("range", _store_range(0, 100),
                         {"histograma": {"bins": [], "conteos": []}})
    assert fig.data
