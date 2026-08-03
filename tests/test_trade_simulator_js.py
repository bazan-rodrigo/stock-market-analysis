"""HOMOLOGACIÓN REAL del simulador de trades: el espejo JS corre de verdad.

Cierra el último hueco del relevamiento de trinquetes (el #1,
docs/notes/project_trinquetes_faltantes.md). CLAUDE.md llama a la homologación
"la regla principal del módulo" y hasta ahora dependía enteramente de que la
persona se acordara de tocar los dos archivos: `test_trade_simulator.py` corría
los 35 casos del contrato contra **Python solamente**, y una divergencia en
`window._lwc.simulateTrades` producía un gráfico que mentía sobre los trades sin
que nada lo detectara.

Acá el JavaScript se **ejecuta**, con un intérprete embebido (dukpy → Duktape),
sobre los mismos casos.

**Se compara contra Python, no contra `expected`.** El fixture fija
entry_idx/exit_idx/reason; comparar las dos implementaciones entre sí cubre
además `entry_close`, `exit_close` y `ret`, que es justo donde una divergencia
pasaría desapercibida — el gráfico dibujaría los marcadores en el lugar correcto
y mentiría en el retorno.

**De dónde sale el JS.** El espejo vive dentro de `_JS_RENDER`, un f-string de
~1240 líneas en `chart_callbacks.py`, así que se recorta por los centinelas
`/* <homologacion:simulateTrades> */` y se des-duplican las llaves (`{{` → `{`).
No se importa el módulo a propósito: importarlo arrastra media app (y `yfinance`,
que no está en esta PC) para leer un string.

Esa des-duplicación mecánica es válida **solo si el bloque no tiene ninguna
interpolación de f-string**, y eso se verifica en vez de suponerse: si alguien
mete un `{variable}` adentro, el test falla explicando que hay que cambiar de
estrategia de extracción, en vez de correr un JavaScript corrupto y dar un
resultado sin sentido.
"""
import json
from pathlib import Path

import pytest

dukpy = pytest.importorskip(
    "dukpy",
    reason="dukpy falta: la homologacion Python/JS del simulador NO se esta "
           "verificando. Instalalo con `pip install -r requirements-dev.txt`.")

from app.services.trade_simulator import simulate_trades  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
CHART_CALLBACKS = RAIZ / "app" / "callbacks" / "chart_callbacks.py"

MARCA_INI = "/* <homologacion:simulateTrades> */"
MARCA_FIN = "/* </homologacion:simulateTrades> */"

_CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "trade_simulator_cases.json")
    .read_text(encoding="utf-8")
)["cases"]


def _verificar_llaves_duplicadas(bloque: str) -> None:
    """Toda llave del bloque tiene que estar duplicada (es un f-string).

    Una llave sola sería una interpolación de Python, y entonces el texto del
    archivo NO es el JavaScript que llega al navegador: habría que renderizar
    el f-string en vez de recortarlo.
    """
    i = 0
    while i < len(bloque):
        c = bloque[i]
        if c in "{}":
            if i + 1 >= len(bloque) or bloque[i + 1] != c:
                linea = bloque[:i].count("\n") + 1
                contexto = bloque.splitlines()[linea - 1].strip()
                raise AssertionError(
                    f"Llave sin duplicar en la línea {linea} del espejo JS: "
                    f"{contexto!r}. Si es una interpolación de f-string, este "
                    f"test ya no puede recortar el fuente: hay que renderizar "
                    f"_JS_RENDER y extraer de ahí.")
            i += 2
        else:
            i += 1


def extraer_espejo_js() -> str:
    fuente = CHART_CALLBACKS.read_text(encoding="utf-8")
    if MARCA_INI not in fuente or MARCA_FIN not in fuente:
        raise AssertionError(
            f"No están los centinelas {MARCA_INI} / {MARCA_FIN} en "
            f"chart_callbacks.py. Delimitan el espejo JS para poder correrlo; "
            f"sin ellos la homologación Python/JS deja de verificarse.")
    ini = fuente.index(MARCA_INI) + len(MARCA_INI)
    fin = fuente.index(MARCA_FIN)
    assert fin > ini, "los centinelas del espejo JS están al revés"
    bloque = fuente[ini:fin]
    _verificar_llaves_duplicadas(bloque)
    return bloque.replace("{{", "{").replace("}}", "}")


@pytest.fixture(scope="module")
def js():
    """Intérprete con el espejo ya cargado (uno solo para los 35 casos)."""
    interprete = dukpy.JSInterpreter()
    interprete.evaljs("var window = {}; window._lwc = {}; 0;")
    interprete.evaljs(extraer_espejo_js() + "\n0;")
    return interprete


def _correr_js(interprete, caso):
    return interprete.evaljs(
        "window._lwc.simulateTrades(dukpy['closes'], dukpy['scores'], "
        "dukpy['spec'], dukpy['percentiles'])",
        closes=caso["closes"], scores=caso["scores"], spec=caso["spec"],
        percentiles=caso.get("percentiles"))


def test_el_espejo_js_se_extrae_y_carga(js):
    fuente = extraer_espejo_js()
    assert "window._lwc.simulateTrades = function" in fuente
    # Y quedó ejecutable de verdad, no solo parseado.
    assert js.evaljs("typeof window._lwc.simulateTrades") == "function"


@pytest.mark.parametrize("caso", _CASES, ids=[c["name"] for c in _CASES])
def test_el_js_da_lo_mismo_que_python(caso, js):
    py = simulate_trades(caso["closes"], caso["scores"], caso["spec"],
                         caso.get("percentiles"))
    jsr = _correr_js(js, caso)

    assert len(jsr) == len(py), (
        f"{caso['name']}: Python devolvió {len(py)} trades y el JS {len(jsr)}")

    for n, (t_py, t_js) in enumerate(zip(py, jsr)):
        for campo in ("entry_idx", "exit_idx", "reason"):
            assert t_js[campo] == t_py[campo], f"{caso['name']} trade {n} · {campo}"
        for campo in ("entry_close", "exit_close", "ret"):
            if t_py[campo] is None:
                assert t_js[campo] is None, f"{caso['name']} trade {n} · {campo}"
            else:
                assert t_js[campo] == pytest.approx(t_py[campo]), (
                    f"{caso['name']} trade {n} · {campo}")


def test_el_trinquete_muerde(js):
    """Un trinquete que nunca se probó contra el defecto no es un trinquete.

    Se carga una versión ADULTERADA del espejo —invertida la comparación de
    entrada, que es el corazón de la semántica— y se exige que al menos un caso
    del contrato la delate.
    """
    adulterado = extraer_espejo_js().replace(
        "if (v === null || v < entries[e].th) return false;",
        "if (v === null || v > entries[e].th) return false;")
    assert adulterado != extraer_espejo_js(), (
        "no se pudo adulterar el espejo: cambió la línea que este test usa "
        "como defecto de prueba, actualizala")

    roto = dukpy.JSInterpreter()
    roto.evaljs("var window = {}; window._lwc = {}; 0;")
    roto.evaljs(adulterado + "\n0;")

    delatado = False
    for caso in _CASES:
        py = simulate_trades(caso["closes"], caso["scores"], caso["spec"],
                             caso.get("percentiles"))
        jsr = _correr_js(roto, caso)
        if len(jsr) != len(py) or any(
                a["entry_idx"] != b["entry_idx"] or a["exit_idx"] != b["exit_idx"]
                for a, b in zip(jsr, py)):
            delatado = True
            break
    assert delatado, ("el espejo adulterado pasó los 35 casos: el contrato no "
                      "cubre la comparación de entrada")
