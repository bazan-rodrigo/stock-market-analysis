"""Ninguna construcción de componente puede pasar una prop que el paquete no
acepta.

Regresión real (producción, ago-2026): un `title=` en el `dbc.Input` del peso
tiraba TypeError al construir la fila del modal de estrategias. Como el armado
ocurre DENTRO de un callback, la excepción no rompe la pantalla — se come ese
Output y todo lo demás se ve perfecto, así que un render que explota parece un
dato que falta: la estrategia se abría sin ninguno de sus cuatro componentes.
Estuvo en producción hasta que alguien lo notó a mano.

El chequeo es ESTÁTICO a propósito. Ejercitar los 99 callbacks que devuelven
`children` exigiría datos y base para cada uno, y la lista de cuáles están
cubiertos se pudriría (el patrón que ya falló en cleanup_service). Esto en
cambio deriva de las dos únicas fuentes que importan —el código fuente y las
firmas reales de los componentes instalados— y cubre TODA construcción de la
app: layouts, callbacks y componentes compartidos, se ejerciten o no.

Lo que NO cubre: props válidas con valores inválidos, y errores de lógica del
render. Para eso están los tests que ejercitan cada render (ver
test_render_dinamico.py y test_strategy_modal_rows.py).
"""
import ast
import importlib
import inspect
from pathlib import Path

import dash_bootstrap_components as dbc
import pytest
from dash import html
from dash.development.base_component import Component

ROOT = Path(__file__).resolve().parent.parent

# Wildcards que Dash acepta en cualquier componente (_valid_wildcard_attributes)
WILDCARDS = ("data-", "aria-")


def _props_validas(cls) -> set[str] | None:
    """Nombres de prop que el componente acepta, o None si no se puede saber."""
    try:
        sig = inspect.signature(cls.__init__)
    except (TypeError, ValueError):
        return None
    nombres = {p.name for p in sig.parameters.values()
               if p.name != "self"
               and p.kind not in (inspect.Parameter.VAR_KEYWORD,
                                  inspect.Parameter.VAR_POSITIONAL)}
    # Sin props nombradas solo queda **kwargs: no hay nada contra qué validar.
    return nombres or None


def _alias_de_imports(tree: ast.AST) -> dict[str, str]:
    """{nombre_local: modulo} de los imports del archivo.

    Se ignora todo lo que cuelgue de `app.`: los componentes son de terceros y
    resolver los módulos propios importaría media aplicación dentro del test.
    """
    alias: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if not a.name.startswith("app"):
                    alias[a.asname or a.name.split(".")[0]] = a.name
        elif isinstance(node, ast.ImportFrom):
            if node.module and not node.module.startswith("app") and not node.level:
                for a in node.names:
                    alias[a.asname or a.name] = f"{node.module}.{a.name}"
    return alias


_cache: dict[tuple[str, str], object] = {}


def _resolver(modulo: str, nombre: str):
    """El objeto `modulo.nombre`, o None si no se puede importar."""
    clave = (modulo, nombre)
    if clave not in _cache:
        try:
            _cache[clave] = getattr(importlib.import_module(modulo), nombre, None)
        except Exception:  # noqa: BLE001 — dependencia ausente: no es asunto de este test
            _cache[clave] = None
    return _cache[clave]


def analizar(src: str, origen: str) -> tuple[list[tuple], int]:
    """(props inválidas, construcciones revisadas) de un fuente Python.

    Una construcción se reconoce por lo que ES —una subclase de
    dash.Component— y no por una lista de paquetes: sumar mañana otra
    biblioteca de componentes queda cubierto sin tocar este archivo.
    """
    tree = ast.parse(src, origen)
    alias = _alias_de_imports(tree)
    hallazgos, revisadas = [], 0

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
            modulo = alias.get(f.value.id)
            if modulo is None:
                continue
            cls, etiqueta = _resolver(modulo, f.attr), f"{f.value.id}.{f.attr}"
        elif isinstance(f, ast.Name) and "." in alias.get(f.id, ""):
            modulo, _, nombre = alias[f.id].rpartition(".")
            cls, etiqueta = _resolver(modulo, nombre), f.id
        else:
            continue

        if not (inspect.isclass(cls) and issubclass(cls, Component)):
            continue
        validas = _props_validas(cls)
        if validas is None:
            continue
        revisadas += 1
        for kw in node.keywords:
            if kw.arg is None:      # **algo: no se puede saber en estático
                continue
            if kw.arg not in validas and not kw.arg.startswith(WILDCARDS):
                hallazgos.append((origen, kw.lineno, etiqueta, kw.arg))

    return hallazgos, revisadas


def _fuentes_de_la_app():
    for path in sorted(ROOT.glob("app/**/*.py")):
        yield path, path.read_text(encoding="utf-8")


def _analizar_la_app():
    hallazgos, revisadas, archivos = [], 0, 0
    for path, src in _fuentes_de_la_app():
        h, r = analizar(src, path.relative_to(ROOT).as_posix())
        hallazgos += h
        revisadas += r
        archivos += bool(r)
    return hallazgos, revisadas, archivos


def test_ninguna_construccion_usa_una_prop_invalida():
    hallazgos, _, _ = _analizar_la_app()

    detalle = "\n".join(f"    {arch}:{linea}  {comp}(… {prop}=…)"
                        for arch, linea, comp, prop in hallazgos)
    assert not hallazgos, (
        f"{len(hallazgos)} construcción(es) pasan una prop que el componente "
        f"no acepta. Dash levanta TypeError al construirlas; si ocurre dentro "
        f"de un callback, la pantalla NO se rompe: ese Output queda sin "
        f"actualizar y parece un dato que falta.\n{detalle}\n"
        f"El tooltip de un control va en un html.Div envolvente.")


def test_el_analisis_recorre_la_app_entera():
    """Piso de cobertura: sin esto, un escáner que dejara de encontrar
    archivos (glob roto, imports que no resuelven) daría verde por vacío —
    justo el modo de falla que tuvieron los tests de cleanup_service."""
    _, revisadas, archivos = _analizar_la_app()

    assert revisadas > 1000 and archivos > 30, (
        f"el análisis solo vio {revisadas} construcciones en {archivos} "
        f"archivos: la app tiene miles. El escáner dejó de resolver los "
        f"componentes y este test estaría pasando por vacío.")


# ── El detector se verifica a sí mismo ────────────────────────────────────────

def _props(src):
    return {(comp, prop) for _, _, comp, prop in analizar(src, "<test>")[0]}


def test_el_detector_agarra_la_prop_que_vacio_el_modal():
    """El caso exacto que llegó a producción."""
    src = (
        "import dash_bootstrap_components as dbc\n"
        "fila = dbc.Input(id='x', type='number', title='Peso del componente')\n"
    )
    assert _props(src) == {("dbc.Input", "title")}

    # Y el arreglo que se le aplicó no debe marcarse.
    arreglado = (
        "import dash_bootstrap_components as dbc\n"
        "from dash import html\n"
        "fila = html.Div(dbc.Input(id='x', type='number'), title='Peso')\n"
    )
    assert _props(arreglado) == set()


def test_el_detector_no_marca_lo_valido():
    """Falsos positivos: `title` es legítimo en varios componentes, y los
    wildcards data-/aria- valen en todos."""
    src = (
        "import dash_bootstrap_components as dbc\n"
        "from dash import dcc, html\n"
        "a = dbc.Button('x', title='ok')\n"
        "b = html.Span('x', title='ok')\n"
        "c = dcc.Dropdown(options=[], value=None, placeholder='ok')\n"
        "d = html.Div('x', **{'data-rol': 'ok', 'aria-label': 'ok'})\n"
    )
    assert _props(src) == set()


def test_el_detector_sigue_los_alias_del_archivo():
    """El nombre local no dice qué componente es: `bs.Input` puede ser el de
    dbc (que rechaza title) o el de dcc (que también), y `html.Div` ninguno de
    los dos. Se resuelve por el import, no por el nombre."""
    src = (
        "import dash_bootstrap_components as bs\n"
        "x = bs.Input(id='x', title='no va')\n"
    )
    assert _props(src) == {("bs.Input", "title")}


def test_el_detector_no_inventa_componentes():
    """Una llamada a algo que no es un componente Dash no se toca."""
    src = (
        "import json\n"
        "x = json.dumps({}, indent=2, sort_keys=True)\n"
    )
    assert analizar(src, "<test>") == ([], 0)


@pytest.mark.parametrize("componente, prop, acepta", [
    (dbc.Input,  "title", False),
    (dbc.Button, "title", True),
    (html.Div,   "title", True),
])
def test_las_props_se_leen_del_paquete_instalado(componente, prop, acepta):
    """La verdad la pone la biblioteca, no una lista de este archivo: si una
    versión nueva cambia las props, el test se entera solo."""
    assert (prop in (_props_validas(componente) or set())) is acepta
