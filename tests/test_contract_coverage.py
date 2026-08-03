"""La INTERFAZ ofrece todo lo que el motor soporta.

Regla del proyecto: todo cambio del sistema se refleja en la interfaz y en el
contrato publicado, en el mismo commit. `test_pack_spec.py` cubre el contrato
(SPEC.md); este archivo cubre la otra cara — una capacidad que el motor
soporta pero ninguna pantalla ofrece es invisible para el usuario, y una que la
UI ofrece pero el motor ya no soporta (una fórmula removida que quedó en un
dropdown) es peor: se puede elegir y falla al guardar.

El vocabulario está declarado en un solo lugar por concepto
(`signal_engine.FORMULA_TYPES`, `strategy_filter.*_OPERATORS`,
`ATTRIBUTE_KEYS`), pero la UI necesita además etiquetas y textos de ayuda que
no se pueden derivar — así que las listas se repiten a mano y este test es el
trinquete que impide que se desincronicen. Mismo espíritu que
test_module_registration.py con _PAGES.
"""
import ast
import inspect
import json
from pathlib import Path

import pytest

from app.callbacks import signal_params_ui, strategy_filter_ui
from app.callbacks.admin_signals_callbacks import _FT_LABEL
from app.components.ui_constants import FORMULA_HELP
from app.services import pack_service, signal_engine, strategy_filter

ROOT = Path(__file__).resolve().parent.parent


def _literal(archivo: Path, nombre: str):
    """Constante literal de nivel de módulo, sin importar el archivo.

    Las páginas llaman a `dash.register_page()` al importarse y eso explota
    fuera de una app armada; leer el AST evita levantar media aplicación para
    mirar un dropdown.
    """
    arbol = ast.parse(archivo.read_text(encoding="utf-8"))
    for nodo in arbol.body:
        if isinstance(nodo, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == nombre for t in nodo.targets):
            return ast.literal_eval(nodo.value)
    raise AssertionError(f"no se encontró {nombre} en {archivo.name}")


# ── Fórmulas de señal ─────────────────────────────────────────────────────────

def test_el_abm_ofrece_todas_las_formulas():
    """El dropdown de la pantalla de Señales."""
    opts = _literal(ROOT / "app" / "pages" / "admin_signals.py", "_FORMULA_OPTS")
    ofrecidas = {o["value"] for o in opts}
    assert ofrecidas == set(signal_engine.FORMULA_TYPES), (
        f"el dropdown de fórmulas y signal_engine.FORMULA_TYPES no coinciden: "
        f"sobran {ofrecidas - set(signal_engine.FORMULA_TYPES)}, "
        f"faltan {set(signal_engine.FORMULA_TYPES) - ofrecidas}")


def test_toda_formula_tiene_ayuda_en_pantalla():
    assert set(FORMULA_HELP) == set(signal_engine.FORMULA_TYPES), (
        "FORMULA_HELP (ui_constants) no cubre las mismas fórmulas que el motor: "
        "la tarjeta de ayuda es lo único que explica al usuario cuándo usar cada "
        "una")


def test_toda_formula_tiene_etiqueta_en_la_grilla():
    assert set(_FT_LABEL) == set(signal_engine.FORMULA_TYPES), (
        "_FT_LABEL (admin_signals_callbacks) no cubre las mismas fórmulas: la "
        "columna de la grilla mostraría el código crudo o vacío")


# Un params canónico por fórmula, con la forma que el editor debe saber leer.
_PARAMS_CANONICOS = {
    "discrete_map": {"map": {"bullish": 100, "lateral": 0, "bearish": -100}},
    "threshold": {"thresholds": [[-5, 100], [-15, 50], [None, -50]]},
    "range": {"min": -3, "max": 3, "clamp": True},
}


def test_hay_un_params_canonico_por_formula():
    """Guarda del test siguiente: una fórmula nueva sin caso acá pasaría sin
    ejercitar el editor."""
    assert set(_PARAMS_CANONICOS) == set(signal_engine.FORMULA_TYPES)


@pytest.mark.parametrize("ftype", signal_engine.FORMULA_TYPES)
def test_toda_formula_tiene_editor_estructurado(ftype):
    """Ida y vuelta por el editor de la pantalla: params guardado → controles →
    params. Sin editor propio, `builder_from_params` devuelve None y el usuario
    queda obligado al modo avanzado (escribir el JSON a mano)."""
    params = _PARAMS_CANONICOS[ftype]
    store = signal_params_ui.builder_from_params(ftype, json.dumps(params))
    assert store is not None, (
        f"el editor de la pantalla no sabe leer un params de '{ftype}'")

    devuelto, error = signal_params_ui.params_from_builder(ftype, store)
    assert error is None, f"el editor no puede volver a guardar '{ftype}': {error}"
    assert json.loads(devuelto) == params, (
        f"el editor de '{ftype}' no conserva los parámetros al ida y vuelta")


# ── Operadores del filtro de elegibilidad ─────────────────────────────────────

def test_el_constructor_ofrece_todos_los_operadores_numericos():
    ofrecidos = {o["value"] for o in strategy_filter_ui._NUM_OPS}
    assert ofrecidos == set(strategy_filter.NUMERIC_OPERATORS), (
        "_NUM_OPS (constructor de filtros) no coincide con NUMERIC_OPERATORS")


def test_el_constructor_ofrece_todos_los_operadores_categoricos():
    ofrecidos = {o["value"] for o in strategy_filter_ui._CAT_OPS}
    assert ofrecidos == set(strategy_filter.CATEGORICAL_OPERATORS), (
        "_CAT_OPS (constructor de filtros) no coincide con CATEGORICAL_OPERATORS")


# ── Atributos filtrables ──────────────────────────────────────────────────────

def test_todo_atributo_filtrable_tiene_etiqueta():
    assert set(strategy_filter_ui._ATTR_LABELS) == set(strategy_filter.ATTRIBUTE_KEYS), (
        "_ATTR_LABELS no cubre los mismos atributos que ATTRIBUTE_KEYS: el que "
        "falte no se puede elegir en el constructor de filtros")


def test_todo_atributo_filtrable_tiene_nombre_para_su_hueco():
    """El "(sin …)" de cada atributo lo muestra la UI y lo resuelven los packs
    desde NONE_LABELS: el que falte deja su hueco sin poder nombrarse."""
    assert set(strategy_filter.NONE_LABELS) == set(strategy_filter.ATTRIBUTE_KEYS), (
        "NONE_LABELS no cubre los mismos atributos que ATTRIBUTE_KEYS")


def test_los_indicadores_virtuales_se_ofrecen_en_el_filtro():
    """`last_close` no tiene fila en indicator_definitions, así que el
    constructor lo tiene que sumar aparte o el motor soportaría un operando
    que ninguna pantalla ofrece."""
    fuente = inspect.getsource(strategy_filter_ui.build_filter_opts)
    assert "_VIRTUAL_CODES" in fuente, (
        "build_filter_opts no suma los indicadores virtuales a los operandos")


def test_todo_atributo_filtrable_esta_en_el_dropdown():
    """La lista de operandos y el mapeo a tablas de catálogo viven dentro de
    build_filter_opts; se mira su código para no tener que levantar la base."""
    fuente = inspect.getsource(strategy_filter_ui.build_filter_opts)
    faltantes = [k for k in strategy_filter.ATTRIBUTE_KEYS if f'"{k}"' not in fuente]
    assert not faltantes, (
        f"atributos que no aparecen en build_filter_opts: {faltantes} — no se "
        f"ofrecerían como operando o no tendrían valores para elegir")


def test_todo_atributo_filtrable_se_resuelve_por_nombre_en_los_packs():
    """attribute_pairs arma los valores de los seis atributos: los cinco de
    tabla propia salen de _attribute_models y `benchmark` de su propia rama
    (apunta a activos, no a un catálogo). Se mira el código de las dos para no
    tener que levantar la base."""
    fuente = (inspect.getsource(pack_service._attribute_models)
              + inspect.getsource(pack_service.attribute_pairs))
    faltantes = [k for k in strategy_filter.ATTRIBUTE_KEYS if f'"{k}"' not in fuente]
    assert not faltantes, (
        f"atributos que attribute_pairs no cubre: {faltantes} — no se podrían "
        f"escribir por nombre en un pack (y el catálogo exportado tampoco los "
        f"listaría)")


# ── El catálogo publicado ─────────────────────────────────────────────────────

def test_el_catalogo_publica_el_vocabulario_desde_las_fuentes_unicas():
    """El catálogo que se descarga para armar packs incluye el vocabulario del
    motor. Se verifica que salga de las fuentes únicas y no de copias: si
    alguien redeclarara la lista, este test seguiría pasando pero el de arriba
    fallaría — acá lo que se fija es que el catálogo no se olvide de publicarlo.
    """
    fuente = inspect.getsource(pack_service.build_catalog)
    for atributo in ("FORMULA_TYPES", "NUMERIC_OPERATORS", "CATEGORICAL_OPERATORS",
                     "OPERAND_TYPES", "ATTRIBUTE_KEYS"):
        assert atributo in fuente, (
            f"build_catalog no publica {atributo}: quien arma un pack sin ver "
            f"el código se quedaría sin esa parte del vocabulario")


# ── Lo que la IA puede hacer, y lo que el manual dice que puede ────────────────

def test_toda_familia_de_herramientas_esta_descrita_en_el_manual():
    """La otra cara de la regla, para la capa de IA: una capacidad que el
    usuario no sabe que tiene es una capacidad que no existe.

    `test_manual_coverage.py` ata PANTALLAS ↔ manual, y las herramientas de IA
    no son pantallas: quedaban fuera de toda red. El resultado medido fue que
    la sección describía 8 de 15 herramientas —sin mencionar que la IA corre
    backtests y simula carteras— durante días, sin que nada fallara.

    El puente son las familias (registry.FAMILIAS) y no los nombres técnicos:
    el manual lo lee alguien que no programa, así que enumerar
    `run_backtest_preview` ahí sería jerga. Las dos listas se derivan: una de
    las herramientas registradas, la otra del front-matter de la sección.
    """
    from app.ai import registry
    from app.services import manual_service

    ruta = Path(__file__).resolve().parent.parent / "docs" / "manual"
    archivos = [p for p in ruta.glob("*.md")
                if "conexion-ia" in manual_service.parse_front_matter(
                    p.read_text(encoding="utf-8"))[0].get("slug", "")]
    assert archivos, "no existe la sección conexion-ia del manual"

    meta, _ = manual_service.parse_front_matter(
        archivos[0].read_text(encoding="utf-8"))
    declaradas = {f.strip() for f in (meta.get("familias_ia") or "").split(",")
                  if f.strip()}
    en_uso = {t.familia for t in registry.all_tools()}

    sin_documentar = sorted(en_uso - declaradas)
    assert not sin_documentar, (
        f"familias de herramientas que el manual no describe: "
        f"{sin_documentar}. La IA puede hacerlo y el usuario no se entera: "
        f"describilo en la sección Conexión IA y sumalo a `familias_ia`.")

    de_mas = sorted(declaradas - en_uso)
    assert not de_mas, (
        f"el manual promete capacidades que ya no existen: {de_mas}. Peor que "
        f"faltar: el usuario las pide y no están.")


def test_el_brochure_publicita_todas_las_familias_de_ia():
    """La tercera cara de la misma regla, para la página pública.

    El manual le cuenta qué puede hacer su IA a quien YA tiene usuario; el
    brochure (/acerca) es lo único que se lo cuenta a quien todavía no lo
    tiene. Una capacidad que nadie sabe que existe no vende nada, y una que la
    página promete pero el registro ya no tiene es peor: se pide y no está.

    Se lee el AST por lo mismo que `_literal`: importar la página dispara
    `register_page`.
    """
    from app.ai import registry

    caps = _literal(ROOT / "app" / "pages" / "brochure.py", "_IA_CAPACIDADES")
    publicitadas = {c["familia"] for c in caps}
    en_uso = {t.familia for t in registry.all_tools()}

    sin_publicitar = sorted(en_uso - publicitadas)
    assert not sin_publicitar, (
        f"familias de herramientas que el brochure no menciona: "
        f"{sin_publicitar}. La IA puede hacerlo y quien mira la página no se "
        f"entera: sumalas a _IA_CAPACIDADES en app/pages/brochure.py.")

    de_mas = sorted(publicitadas - en_uso)
    assert not de_mas, (
        f"el brochure promete capacidades de IA que ya no existen: {de_mas}.")


def test_las_familias_declaradas_estan_en_el_vocabulario():
    """Un typo en `familia=` crearía una familia fantasma. El constructor de
    Tool ya lo rechaza; esto fija que el vocabulario no se pueble solo."""
    from app.ai import registry

    fuera = sorted({t.familia for t in registry.all_tools()} - registry.FAMILIAS)
    assert not fuera, f"familias fuera de FAMILIAS: {fuera}"
