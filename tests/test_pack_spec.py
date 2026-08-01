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


# ── Los packs publicados en strategy_packs/ ──────────────────────────────────

PACKS = ROOT / "strategy_packs"


def _packs_json() -> list[Path]:
    return sorted(PACKS.glob("*.json"))


def _filas_xlsx(path: Path) -> list[list]:
    import openpyxl

    wb = openpyxl.load_workbook(path)
    return [[list(r) for r in ws.iter_rows(values_only=True)]
            for ws in wb.worksheets]


def test_cada_pack_publicado_valida_sin_errores():
    """Un pack roto en el repositorio se copia como ejemplo. Sin catálogo no se
    verifican los indicadores (dependen de la instalación), pero sí toda la
    forma."""
    assert _packs_json(), "no hay ningún pack JSON en strategy_packs/"
    for path in _packs_json():
        pack = ps.parse_pack(path.read_bytes())
        errores = ps.validate_pack(pack, None)["errors"]
        assert errores == [], f"{path.name}: {errores}"


def test_cada_planilla_publicada_tiene_su_json():
    """El formato canónico es el JSON (SPEC §10): un pack que solo exista como
    planilla no se puede leer ni entregar en el formato que el estándar
    publica."""
    faltantes = [p.name for p in sorted(PACKS.glob("*_senales.xlsx"))
                 if not (PACKS / f"{p.stem.replace('_senales', '')}.json").exists()]
    assert not faltantes, (
        f"planillas sin su pack JSON: {faltantes}. Generalo con "
        f"scripts/pack_to_json.py")


def test_el_json_y_las_planillas_de_cada_pack_dicen_lo_mismo():
    """Los dos formatos del MISMO pack tienen que coincidir: si se editan por
    separado, el canónico y el histórico empiezan a describir estrategias
    distintas con el mismo nombre y nadie se entera."""
    for path in _packs_json():
        pack = ps.parse_pack(path.read_bytes())
        nombre = path.stem

        senales = PACKS / f"{nombre}_senales.xlsx"
        if senales.exists():
            esperado = [list(ps.SIGNAL_COLUMNS)] + [
                [f.get(c) for c in ps.SIGNAL_COLUMNS]
                for f in ps.signal_rows_from_pack(pack)]
            assert _filas_xlsx(senales)[0] == esperado, (
                f"{senales.name} no coincide con {path.name}: regenerá la "
                f"planilla con scripts/pack_from_json.py")

        estrategia = PACKS / f"{nombre}_estrategia.xlsx"
        if estrategia.exists():
            rows_s, rows_c = ps.strategy_rows_from_pack(pack)
            hojas = _filas_xlsx(estrategia)
            assert hojas[0] == [list(ps.STRATEGY_COLUMNS)] + [
                [f.get(c) for c in ps.STRATEGY_COLUMNS] for f in rows_s], (
                f"{estrategia.name}: la hoja de estrategias no coincide con "
                f"{path.name}")
            assert hojas[1] == [list(ps.COMPONENT_COLUMNS)] + [
                [f.get(c) for c in ps.COMPONENT_COLUMNS] for f in rows_c], (
                f"{estrategia.name}: la hoja de componentes no coincide con "
                f"{path.name}")
