"""Trinquete: la PROSA del SPEC de packs (hueco #5 del relevamiento,
docs/notes/project_trinquetes_faltantes.md).

`test_pack_spec.py` ata las **enumeraciones** del contrato: fórmulas,
operadores, atributos, columnas. Por eso siguió en verde mientras §1 describía
durante cuatro días un flujo que ya no existía, y por eso la frase "las señales
las escribe solo un administrador" —agregada el 1-ago— no tenía quién la
verificara: si mañana se revierte el gate, el documento publicado sigue
afirmándolo y nadie se entera.

Un SPEC que miente es peor que no tenerlo: quien arma packs afuera de este repo
no tiene forma de descubrirlo, porque el documento ES su única fuente.

**Cómo funciona.** Cada afirmación normativa se registra dos veces: el texto que
tiene que seguir estando en el documento, y el hecho del código que la vuelve
verdad. Se verifica en los DOS sentidos, y ahí está lo que lo hace un trinquete
y no una decoración:

- si el código cambia (se saca el gate de admin, se vuelve a Σpeso), el
  verificador falla y hay que ir a corregir el SPEC;
- si alguien reescribe o borra la frase, el texto no matchea y hay que volver a
  registrar la afirmación con su verificador.

**Por qué no hay marcas dentro del SPEC.** Se evaluó anclar cada frase con un
comentario HTML. Se descartó: el SPEC es un documento **publicado**, que se le
entrega a gente y a modelos que no ven este repo, y llenarlo de andamiaje de
test lo ensucia para su lector real. El costo es que esto cubre las
afirmaciones registradas, no todas — no promete una partición.
"""
import re
from pathlib import Path

import pytest

SPEC = Path(__file__).resolve().parent.parent / "strategy_packs" / "SPEC.md"


# ── Los hechos del código, uno por afirmación ────────────────────────────────

def _divisor_en_valor_absoluto():
    """SCORE = Σ(peso·señal) / Σ|peso|, no / Σpeso."""
    from collections import namedtuple

    from app.services.strategy_service import _compute_asset_score

    Comp = namedtuple("Comp", "signal_id weight")
    comps = [Comp(1, 2.0), Comp(2, -1.0)]
    scores = {(1, 7): 80.0, (2, 7): 60.0}

    # Con Σ|peso| el divisor es 3. Con Σpeso sería 1 y el score daría 100.
    assert _compute_asset_score(comps, 7, scores) == round(100 / 3, 4)


def _peso_cero_rechazado_negativo_aceptado():
    from app.services.strategy_service import parse_component_weight

    assert parse_component_weight(-2) == -2.0
    assert parse_component_weight(None) == 1.0
    with pytest.raises(ValueError):
        parse_component_weight(0)


def _senales_solo_las_escribe_un_admin():
    import inspect

    from app.services import signal_service

    with pytest.raises(ValueError):
        signal_service.require_signal_admin(False)
    signal_service.require_signal_admin(True)

    # Y el default de cada camino de escritura es "no soy admin": un llamador
    # que se olvide del flag tiene que fallar cerrado, no escribir.
    for nombre in ("save_signal", "delete_signal", "import_signal_rows"):
        firma = inspect.signature(getattr(signal_service, nombre))
        assert firma.parameters["acting_is_admin"].default is False, nombre


def _spec_version_es_1():
    from app.services import pack_service

    assert pack_service.SPEC_VERSION == 1


def _composite_source_group_y_scope_rechazados():
    from app.services import pack_service, signal_engine

    assert "composite" not in signal_engine.FORMULA_TYPES

    pack = {"spec_version": 1,
            "signals": [{"key": "x", "name": "X", "indicator_key": "rsi_14",
                         "formula_type": "composite", "params": {}}]}
    assert pack_service.validate_pack(pack)["errors"]

    pack = {"spec_version": 1,
            "signals": [{"key": "x", "name": "X", "indicator_key": "rsi_14",
                         "source": "group", "formula_type": "range",
                         "params": {"min": 0, "max": 10}}]}
    assert pack_service.validate_pack(pack)["errors"]


def _una_version_desconocida_se_rechaza_entera():
    from app.services import pack_service

    with pytest.raises(pack_service.PackError):
        pack_service.parse_pack(b'{"spec_version": 99, "signals": []}')


# ── El registro: texto publicado ↔ hecho del código ──────────────────────────

AFIRMACIONES = (
    ("§5 el divisor del ranking es Σ|peso|",
     r"SCORE\s*=\s*Σ\(peso\s*·\s*señal\)\s*/\s*Σ\|peso\|",
     _divisor_en_valor_absoluto),

    ("§5 el peso es distinto de 0 y puede ser negativo",
     r"`weight` es un número \*\*distinto de 0\*\*",
     _peso_cero_rechazado_negativo_aceptado),

    ("§5 el peso negativo evita duplicar la señal invertida",
     r"\*\*El peso puede ser NEGATIVO\*\*",
     _peso_cero_rechazado_negativo_aceptado),

    ("§8 las señales las escribe solo un administrador",
     r"\*\*Las señales las escribe solo un administrador\.\*\*",
     _senales_solo_las_escribe_un_admin),

    ("§11 la versión actual del formato es 1",
     r"`spec_version: 1` es la versión actual",
     _spec_version_es_1),

    ("§11 una versión desconocida se rechaza, nunca a medias",
     r"que la\s+instalación no entiende se rechaza",
     _una_version_desconocida_se_rechaza_entera),

    ("§11 composite / source:group / scope están removidos",
     r"`formula_type: \"composite\"`",
     _composite_source_group_y_scope_rechazados),
)


@pytest.fixture(scope="module")
def spec() -> str:
    return SPEC.read_text(encoding="utf-8")


@pytest.mark.parametrize("nombre,patron,_verificar",
                         AFIRMACIONES, ids=[a[0] for a in AFIRMACIONES])
def test_la_afirmacion_sigue_escrita_en_el_spec(nombre, patron, _verificar,
                                                spec):
    assert re.search(patron, spec), (
        f"El SPEC ya no dice «{nombre}». Si la regla cambió, actualizá el "
        f"verificador de este test; si solo se reescribió la frase, "
        f"actualizá el patrón. Lo que no puede pasar es que el contrato "
        f"publicado y el código digan cosas distintas.")


@pytest.mark.parametrize("nombre,_patron,verificar",
                         AFIRMACIONES, ids=[a[0] for a in AFIRMACIONES])
def test_la_afirmacion_sigue_siendo_verdad_en_el_codigo(nombre, _patron,
                                                        verificar):
    verificar()


def test_el_trinquete_no_es_vacuo(spec):
    """Que los patrones matcheen no prueba nada si matchearan cualquier cosa."""
    assert not re.search(r"\*\*Las señales las escribe cualquiera\.\*\*", spec)
    assert not re.search(r"SCORE\s*=\s*Σ\(peso\s*·\s*señal\)\s*/\s*Σpeso", spec)
    # Y el registro no puede quedar vacío por un refactor distraído.
    assert len(AFIRMACIONES) >= 7
