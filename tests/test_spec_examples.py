"""Los ejemplos del SPEC, ejecutables.

`test_pack_spec.py` verifica el VOCABULARIO del contrato publicado (que estén
documentadas todas las fórmulas, operadores y columnas). Este archivo verifica
la SEMÁNTICA: cada afirmación numérica de strategy_packs/SPEC.md se comprueba
contra el motor.

Sin esto, un cambio de semántica —`>` por `>=` en los umbrales, el sentido de
la interpolación, que una señal sin valor pase a contar como cero— no rompe
nada y el documento pasa a mentir con total seguridad. Y a un SPEC que miente
le creen: es lo único que ve quien arma packs desde afuera.

Mismo patrón que tests/fixtures/trade_simulator_cases.json con el simulador de
trades: el documento es un contrato, y el contrato se ejecuta.

Cada test cita la sección del SPEC que fija.
"""
from types import SimpleNamespace

from app.services import signal_engine, strategy_filter
from app.services.strategy_service import _compute_asset_score
from app.services.visibility import can_reference


# ── §4 · Mapa discreto ────────────────────────────────────────────────────────

MAPA = {"map": {"bullish_strong": 100, "bullish": 60, "lateral": 0,
                "bearish": -60, "bearish_strong": -100}}


def test_mapa_discreto_asigna_el_puntaje_de_la_categoria():
    assert signal_engine.evaluate_discrete_map(MAPA, "bullish") == 60
    assert signal_engine.evaluate_discrete_map(MAPA, "bearish_strong") == -100


def test_categoria_sin_puntaje_no_puntua():
    """SPEC §4: «Una categoría que no esté en el mapa deja la señal sin valor
    ese día» — None, no 0. Es la trampa más frecuente del formato."""
    assert signal_engine.evaluate_discrete_map(MAPA, "bullish_nascent") is None


def test_mapa_discreto_sobre_un_valor_numerico_nunca_puntua():
    """SPEC §3: por eso cruzar la fórmula con el tipo del indicador es error."""
    assert signal_engine.evaluate_discrete_map(MAPA, 72.0) is None


# ── §4 · Umbrales ─────────────────────────────────────────────────────────────

DRAWDOWN = {"thresholds": [[-5, 100], [-15, 50], [-30, 0], [None, -50]]}


def test_el_ejemplo_del_drawdown_da_50():
    """SPEC §4, textual: «Un activo con −10% de drawdown no supera el primer
    límite pero sí el segundo, y saca 50»."""
    assert signal_engine.evaluate_threshold(DRAWDOWN, -10) == 50


def test_gana_el_primer_limite_que_el_valor_supera():
    assert signal_engine.evaluate_threshold(DRAWDOWN, -3) == 100
    assert signal_engine.evaluate_threshold(DRAWDOWN, -20) == 0


def test_la_comparacion_es_estrictamente_mayor():
    """SPEC §4: «gana el primer límite que el valor SUPERA (estrictamente
    mayor)». El valor exacto del límite NO lo supera."""
    assert signal_engine.evaluate_threshold(DRAWDOWN, -5) == 50


def test_el_tramo_final_captura_todo_lo_demas():
    assert signal_engine.evaluate_threshold(DRAWDOWN, -80) == -50


def test_sin_tramo_final_los_valores_bajos_quedan_sin_puntaje():
    """SPEC §4: «sin él los valores que no superan ningún límite quedan sin
    puntaje»."""
    sin_default = {"thresholds": [[-5, 100], [-15, 50], [-30, 0]]}
    assert signal_engine.evaluate_threshold(sin_default, -80) is None


def test_thresholds_desordenados_absorben_los_tramos_de_abajo():
    """SPEC §4: «mal ordenados, el tramo más permisivo absorbe todo y los de
    abajo nunca se alcanzan — sin ningún error visible». Con −10, el orden
    correcto da 50 y el invertido da 0."""
    desordenado = {"thresholds": [[-30, 0], [-15, 50], [-5, 100], [None, -50]]}
    assert signal_engine.evaluate_threshold(desordenado, -10) == 0
    assert signal_engine.evaluate_threshold(DRAWDOWN, -10) == 50


# ── §4 · Rango lineal ─────────────────────────────────────────────────────────

RANGO = {"min": -3, "max": 3, "clamp": True}


def test_min_vale_menos_cien_y_max_vale_cien():
    assert signal_engine.evaluate_range(RANGO, -3) == -100
    assert signal_engine.evaluate_range(RANGO, 3) == 100


def test_el_punto_medio_da_cero():
    assert signal_engine.evaluate_range(RANGO, 0) == 0


def test_clamp_recorta_a_cien_exactos():
    assert signal_engine.evaluate_range(RANGO, 50) == 100
    assert signal_engine.evaluate_range(RANGO, -50) == -100


def test_sin_clamp_el_puntaje_se_desborda():
    """SPEC §4: «en una escala de −3 a 3, un valor de 6 da 200»."""
    assert signal_engine.evaluate_range({"min": -3, "max": 3, "clamp": False}, 6) == 200


def test_min_mayor_que_max_invierte_la_escala():
    """SPEC §3/§4: es el ejemplo del RSI —«cuanto más sobrevendido, mejor
    puntaje»— y funciona sin ningún campo extra, solo dando vuelta min y max."""
    rsi = {"min": 70, "max": 30, "clamp": True}
    assert signal_engine.evaluate_range(rsi, 30) == 100
    assert signal_engine.evaluate_range(rsi, 70) == -100
    assert signal_engine.evaluate_range(rsi, 50) == 0


def test_clamp_viene_activado_por_defecto():
    assert signal_engine.evaluate_range({"min": -3, "max": 3}, 50) == 100


# ── §5 · Ranking de la estrategia ─────────────────────────────────────────────

def _comp(signal_id, weight):
    return SimpleNamespace(signal_id=signal_id, weight=weight)


def test_el_ranking_es_el_promedio_ponderado():
    componentes = [_comp(1, 3), _comp(2, 1)]
    scores = {(1, 10): 100, (2, 10): -100}
    assert _compute_asset_score(componentes, 10, scores) == 50


def test_solo_importa_la_proporcion_entre_pesos():
    """SPEC §5: «3/2/1 y 6/4/2 dan el mismo ranking»."""
    scores = {(1, 10): 80, (2, 10): 20, (3, 10): -40}
    a = _compute_asset_score([_comp(1, 3), _comp(2, 2), _comp(3, 1)], 10, scores)
    b = _compute_asset_score([_comp(1, 6), _comp(2, 4), _comp(3, 2)], 10, scores)
    assert a == b


def test_una_señal_sin_valor_se_saltea_y_no_cuenta_como_cero():
    """SPEC §5: «el promedio se calcula solo sobre los componentes que
    puntuaron ese día». Con peso 3 sin valor y peso 1 en 60, el resultado es
    60 — si contara como cero daría 15."""
    componentes = [_comp(1, 3), _comp(2, 1)]
    assert _compute_asset_score(componentes, 10, {(2, 10): 60}) == 60


def test_sin_ningun_componente_con_valor_el_activo_no_rankea():
    """SPEC §5: «Si ninguno puntúa, el activo no aparece en el ranking»."""
    assert _compute_asset_score([_comp(1, 3)], 10, {}) is None


# ── §6 · Filtro de elegibilidad ───────────────────────────────────────────────

def _arbol(operador, valor, key="rsi_daily"):
    return {"cond": {"left": {"type": "indicator", "key": key},
                     "operator": operador,
                     "right": {"type": "const", "value": valor}}}


def _valores(valor, key="rsi_daily"):
    return {("indicator", key, "historic"): {10: valor}} if valor is not None else {}


def test_dato_faltante_es_condicion_no_cumplida():
    """SPEC §6: «Un activo sin ese indicador ese día queda afuera; el filtro
    nunca deja pasar por las dudas». Vale para cualquier operador."""
    for operador in ("<", ">", "=", "!=", ">=", "<="):
        assert strategy_filter.evaluate_tree(
            _arbol(operador, 50), 10, {}, {}) is False, operador


def test_comparacion_numerica():
    assert strategy_filter.evaluate_tree(_arbol(">", 50), 10, _valores(72), {})
    assert not strategy_filter.evaluate_tree(_arbol(">", 50), 10, _valores(30), {})


def test_in_y_not_in_con_lista():
    valores = _valores("bullish", key="trend_weekly")
    dentro = _arbol("in", ["bullish", "bullish_strong"], key="trend_weekly")
    fuera = _arbol("not_in", ["bullish", "bullish_strong"], key="trend_weekly")
    assert strategy_filter.evaluate_tree(dentro, 10, valores, {})
    assert not strategy_filter.evaluate_tree(fuera, 10, valores, {})


def test_and_exige_todas_y_or_alcanza_con_una():
    valores = _valores(72)
    cumple, no_cumple = _arbol(">", 50), _arbol("<", 20)
    y = {"op": "AND", "children": [cumple, no_cumple]}
    o = {"op": "OR", "children": [cumple, no_cumple]}
    assert not strategy_filter.evaluate_tree(y, 10, valores, {})
    assert strategy_filter.evaluate_tree(o, 10, valores, {})


def test_los_atributos_se_comparan_contra_el_grupo_del_activo():
    """SPEC §6: en el árbol guardado el atributo vale el id de catálogo — por
    eso el pack los escribe por nombre y el import los resuelve."""
    arbol = {"cond": {"left": {"type": "attribute", "key": "sector"},
                      "operator": "in",
                      "right": {"type": "const", "value": [3, 7]}}}
    assert strategy_filter.evaluate_tree(arbol, 10, {}, {"sector": 3})
    assert not strategy_filter.evaluate_tree(arbol, 10, {}, {"sector": 5})


def test_evaluacion_por_activo_y_en_lote_dan_lo_mismo():
    """El backfill usa la versión en lote; el SPEC describe una sola semántica."""
    arbol = {"op": "AND", "children": [_arbol(">", 50), _arbol("<", 90)]}
    valores = {("indicator", "rsi_daily", "historic"): {10: 72, 11: 95, 12: 30}}
    grupos = {10: {}, 11: {}, 12: {}}
    en_lote = strategy_filter.evaluate_tree_bulk(arbol, list(grupos), valores, grupos)
    uno_a_uno = {aid for aid in grupos
                 if strategy_filter.evaluate_tree(arbol, aid, valores, {})}
    assert en_lote == uno_a_uno == {10}


# ── §5 · Visibilidad ──────────────────────────────────────────────────────────

def test_una_estrategia_publica_no_puede_usar_señales_privadas():
    """SPEC §5: «una estrategia pública solo puede usar señales públicas»."""
    assert not can_reference(parent_owner_id=1, parent_is_public=True,
                             ref_owner_id=1, ref_is_public=False)
    assert can_reference(parent_owner_id=1, parent_is_public=True,
                         ref_owner_id=2, ref_is_public=True)


def test_una_estrategia_privada_puede_usar_las_propias():
    assert can_reference(parent_owner_id=1, parent_is_public=False,
                         ref_owner_id=1, ref_is_public=False)
    assert not can_reference(parent_owner_id=1, parent_is_public=False,
                             ref_owner_id=2, ref_is_public=False)
