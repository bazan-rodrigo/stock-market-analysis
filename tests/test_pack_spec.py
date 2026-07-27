"""El SPEC publicado (strategy_packs/SPEC.md) contra el código que lo aplica.

Motivación: el SPEC es el contrato que se le entrega a quien escribe un pack
sin acceso a este repositorio. Un documento desactualizado es peor que no
tenerlo — manda a escribir algo que el import rechaza, o peor, algo que
importa distinto de lo que dice. Ya pasó con `composite`, `source=group` y
`scope`, que se removieron del sistema.

Este archivo falla si el código gana una fórmula, un operador, un tipo de
operando, un atributo filtrable o una columna que el SPEC no documenta.
"""
import json
import re
from pathlib import Path

import pytest

from app.services import pack_service as ps
from app.services import signal_engine, strategy_filter

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "strategy_packs" / "SPEC.md"


@pytest.fixture(scope="module")
def texto() -> str:
    assert SPEC.exists(), f"falta el SPEC en {SPEC}"
    return SPEC.read_text(encoding="utf-8")


def _bloques_json(texto: str) -> list[str]:
    """Los ejemplos ```json del documento, salteando los que llevan comentarios
    /* … */ (esquemas ilustrativos, no JSON válido a propósito)."""
    bloques = re.findall(r"```json\n(.*?)```", texto, re.DOTALL)
    return [b for b in bloques if "/*" not in b]


def test_version_del_spec_coincide_con_el_codigo(texto):
    assert f"SPEC v{ps.SPEC_VERSION}" in texto
    assert f'"spec_version": {ps.SPEC_VERSION}' in texto


def test_documenta_todas_las_formulas(texto):
    faltantes = [f for f in signal_engine.FORMULA_TYPES
                 if f"`{f}`" not in texto]
    assert not faltantes, (
        f"fórmulas sin documentar en el SPEC: {faltantes}. Quien escriba un "
        f"pack no puede usar lo que no está en el documento.")


def test_documenta_todos_los_operadores(texto):
    faltantes = [op for op in strategy_filter.ALL_OPERATORS
                 if f"`{op}`" not in texto]
    assert not faltantes, f"operadores sin documentar en el SPEC: {faltantes}"


def test_documenta_todos_los_tipos_de_operando(texto):
    faltantes = [t for t in strategy_filter.OPERAND_TYPES if f"`{t}`" not in texto]
    assert not faltantes, f"tipos de operando sin documentar: {faltantes}"


def test_documenta_todos_los_atributos_filtrables(texto):
    faltantes = [a for a in strategy_filter.ATTRIBUTE_KEYS if f"`{a}`" not in texto]
    assert not faltantes, f"atributos filtrables sin documentar: {faltantes}"


def test_documenta_las_resoluciones(texto):
    faltantes = [r for r in strategy_filter.RESOLUTIONS if f'"{r}"' not in texto]
    assert not faltantes, f"resoluciones sin documentar: {faltantes}"


def test_documenta_los_operadores_de_grupo(texto):
    faltantes = [op for op in strategy_filter.GROUP_OPS if f"`{op}`" not in texto]
    assert not faltantes, f"operadores de grupo sin documentar: {faltantes}"


def test_documenta_las_columnas_de_las_planillas(texto):
    """El SPEC describe también el formato Excel; si cambian las columnas del
    export, la tabla del documento queda mintiendo."""
    columnas = (ps.SIGNAL_COLUMNS + ps.STRATEGY_COLUMNS + ps.COMPONENT_COLUMNS)
    faltantes = [c for c in columnas if f"`{c}`" not in texto]
    assert not faltantes, f"columnas sin documentar en el SPEC: {faltantes}"


def test_documenta_lo_removido(texto):
    """Lo que el import RECHAZA tiene que estar dicho: si no, quien escribe un
    pack lo intenta y no entiende el error."""
    for removido in ("composite", "source", "scope"):
        assert f"`{removido}" in texto or f'"{removido}"' in texto, (
            f"el SPEC no menciona '{removido}', que el import rechaza")


def test_los_ejemplos_json_son_json_valido(texto):
    """Un ejemplo con una coma de más se copia y pega tal cual: que falle acá
    y no en la pantalla de import."""
    for i, bloque in enumerate(_bloques_json(texto)):
        try:
            json.loads(bloque)
        except json.JSONDecodeError as exc:
            pytest.fail(f"el ejemplo #{i + 1} del SPEC no es JSON válido: "
                        f"línea {exc.lineno}, {exc.msg}")


def test_el_ejemplo_completo_pasa_el_validador(texto):
    """El pack de ejemplo del SPEC tiene que validar. Sin catálogo no se
    verifican los indicadores (dependen de la instalación), pero sí toda la
    forma: si el ejemplo publicado no pasa, nadie puede confiar en él."""
    completos = [b for b in _bloques_json(texto)
                 if '"strategies"' in b and '"signals"' in b]
    assert completos, "el SPEC no trae ningún pack de ejemplo completo"

    pack = ps.parse_pack(completos[-1].encode("utf-8"))
    resultado = ps.validate_pack(pack, None)
    assert resultado["errors"] == [], resultado["errors"]
    assert resultado["warnings"] == [], resultado["warnings"]


def test_el_ejemplo_completo_se_convierte_a_filas(texto):
    """El mismo ejemplo, por el camino de las planillas: los dos formatos son
    el mismo contenido."""
    completos = [b for b in _bloques_json(texto)
                 if '"strategies"' in b and '"signals"' in b]
    pack = ps.parse_pack(completos[-1].encode("utf-8"))

    filas = ps.signal_rows_from_pack(pack)
    assert {f["key"] for f in filas} == {"ej_rsi_sobreventa", "ej_tendencia_diaria"}

    rows_s, rows_c = ps.strategy_rows_from_pack(pack)
    assert len(rows_s) == 1
    assert {c["signal_key"] for c in rows_c} == {f["key"] for f in filas}, (
        "el ejemplo del SPEC no es autosuficiente: usa señales que no incluye")


def test_la_especificacion_se_puede_bajar_desde_la_pantalla(texto):
    """Quien usa la aplicación no tiene el repositorio: si `spec_bytes` no
    encuentra el archivo, la mitad fija del estándar queda inalcanzable para el
    usuario y el botón baja un error. Fija además la ruta relativa, que se
    rompe en silencio si el módulo cambia de lugar."""
    assert ps.SPEC_PATH == SPEC, (
        f"pack_service.SPEC_PATH apunta a {ps.SPEC_PATH}, no al SPEC del repo")
    assert ps.spec_bytes().decode("utf-8") == texto


def test_el_readme_de_packs_apunta_al_spec():
    readme = (ROOT / "strategy_packs" / "README.md").read_text(encoding="utf-8")
    assert "SPEC.md" in readme
