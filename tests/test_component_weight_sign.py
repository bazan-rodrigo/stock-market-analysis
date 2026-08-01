"""El peso de un componente admite SIGNO, y el divisor va en valor absoluto.

El bug que arregla: `_compute_asset_score` dividía por Σpeso (con signo), así
que un único componente de peso −1 daba −s/−1 = +s — el peso negativo se
cancelaba contra su propio denominador y NO invertía nada. Con pesos mixtos era
peor: el divisor tendía a 0 y el score se disparaba fuera de −100..100, o daba
exactamente 0 y devolvía None. Y como el import aceptaba el peso sin validar el
signo, alguien podía cargar −1 hoy y obtener en silencio lo contrario de lo que
esperaba.

Que el score quede en −100..100 no es cosmético: los umbrales del simulador de
trades son ABSOLUTOS (`score >= th`, `absolute`, `delta_entry`,
`trailing_score`), así que si la escala se mueve, todas las reglas guardadas
cambian de significado.
"""
import pytest

from app.services.strategy_service import (_compute_asset_score,
                                           parse_component_weight)


class _Comp:
    """StrategyComponent mínimo: _compute_asset_score es lógica pura y solo
    mira signal_id y weight."""

    def __init__(self, signal_id, weight):
        self.signal_id = signal_id
        self.weight = weight


def _score(pesos, scores):
    comps = [_Comp(i, w) for i, w in enumerate(pesos)]
    return _compute_asset_score(comps, 1, {(i, 1): s for i, s in enumerate(scores)})


# ── El caso que estaba mal ────────────────────────────────────────────────────

def test_un_peso_negativo_invierte_de_verdad():
    """Con Σpeso daba +80 (la negación se cancelaba); ahora da −80."""
    assert _score([-1], [80]) == -80.0


def test_el_divisor_es_la_suma_de_valores_absolutos():
    """2·momentum − 1·volatilidad sobre 3, no sobre 1."""
    # (2·80 − 1·60) / |2|+|−1| = 100/3
    assert _score([2, -1], [80, 60]) == pytest.approx(33.3333, abs=1e-4)


def test_pesos_opuestos_ya_no_dan_divisor_cero():
    """+1 y −1 daban Σpeso = 0 → None. Ahora el divisor es 2."""
    assert _score([1, -1], [100, 100]) == 0.0
    assert _score([1, -1], [100, -100]) == 100.0


def test_el_score_se_queda_en_el_rango_de_las_senales():
    """Cualquier combinación de pesos con signo sigue siendo una combinación
    convexa: si las señales están en −100..100, el score también. Es lo que
    hace que los umbrales absolutos del simulador signifiquen siempre lo mismo."""
    for pesos, scores in (([1, -1], [100, -100]), ([5, -3, 2], [100, -100, 100]),
                          ([-1, -1], [-100, -100]), ([0.5, -4], [-100, 100])):
        s = _score(pesos, scores)
        assert -100.0 <= s <= 100.0, (pesos, scores, s)


# ── Retrocompatibilidad ───────────────────────────────────────────────────────

def test_con_pesos_positivos_no_cambia_nada():
    """abs() es la identidad sobre positivos: ninguna estrategia existente
    cambia de resultado."""
    assert _score([3, 1], [100, 20]) == pytest.approx(80.0)
    assert _score([1, 1, 1], [90, 60, 30]) == pytest.approx(60.0)
    assert _score([1], [42.5]) == 42.5


def test_el_componente_sin_dato_se_saltea_y_no_cuenta_en_el_divisor():
    """Regla vieja que se conserva: la señal sin score no es un 0, se descarta
    (y con ella su peso). Ver el aviso del SPEC §5 sobre cobertura parcial."""
    comps = [_Comp(0, 3), _Comp(1, 1)]
    # solo la señal 0 tiene score → 100·3/3
    assert _compute_asset_score(comps, 1, {(0, 1): 100}) == 100.0


def test_sin_ningun_componente_con_dato_devuelve_none():
    assert _compute_asset_score([_Comp(0, 1)], 1, {}) is None


# ── El peso 0 ─────────────────────────────────────────────────────────────────

def test_el_motor_trata_el_peso_cero_como_cero_no_como_uno():
    """Antes `comp.weight or 1.0` convertía el 0 en 1.0: un componente que el
    usuario quiso anular pesaba como cualquier otro. Ahora no aporta."""
    assert _score([1, 0], [100, -100]) == 100.0


def test_el_peso_none_sigue_valiendo_uno():
    assert _score([None, None], [100, 0]) == 50.0


def test_la_validacion_rechaza_el_peso_cero():
    with pytest.raises(ValueError, match="no puede ser 0"):
        parse_component_weight(0)
    with pytest.raises(ValueError, match="no puede ser 0"):
        parse_component_weight("0")


def test_la_validacion_acepta_negativos_y_vacios():
    assert parse_component_weight(-1) == -1.0
    assert parse_component_weight("-2.5") == -2.5
    assert parse_component_weight(None) == 1.0
    assert parse_component_weight("") == 1.0
    assert parse_component_weight("   ") == 1.0


def test_la_validacion_rechaza_lo_que_no_es_numero():
    for malo in ("abc", "1,5", object()):
        with pytest.raises(ValueError, match="peso inválido"):
            parse_component_weight(malo)


def test_la_validacion_rechaza_infinito_y_nan():
    for malo in ("inf", "-inf", "nan"):
        with pytest.raises(ValueError, match="peso inválido"):
            parse_component_weight(malo)


# ── La vista previa del ABM muestra la MISMA fórmula que calcula el motor ─────

def test_la_vista_previa_usa_el_divisor_absoluto_y_resta_los_negativos():
    """Si la vista previa mostrara Σpeso, un −1 se leería como si se cancelara
    (justo el bug que tenía el motor) y el divisor no sería el real."""
    from app.callbacks.admin_strategies_callbacks import _score_text

    txt = _score_text(["a", "b"], ["momentum", "volatilidad"], [2, -1])
    assert txt == "SCORE = (2·momentum − 1·volatilidad) / 3"


def test_la_vista_previa_con_pesos_positivos_no_cambia():
    from app.callbacks.admin_strategies_callbacks import _score_text

    txt = _score_text(["a", "b"], ["s1", "s2"], [3, 1])
    assert txt == "SCORE = (3·s1 + 1·s2) / 4"
