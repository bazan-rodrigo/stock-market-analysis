"""
Motor de evaluación de fórmulas de señales.
Puro (sin acceso a DB): recibe parámetros y valores, devuelve scores -100..100.

Tipos de fórmula soportados:
  discrete_map  — {"map": {"bullish": 60, ...}}  → valor string → score int
  threshold     — {"thresholds": [[limit, score], ..., [null, default]]}
                  Evaluación: primer límite donde valor > limit → score; null = default
  range         — {"min": x, "max": y, "clamp": true/false}
                  Mapea valor numérico a -100..100 de forma lineal
  composite     — {"components": [{"signal_key": "k", "weight": w}, ...]}
                  Promedio ponderado de scores de otras señales (resuelto externamente)
"""
import json
import logging

logger = logging.getLogger(__name__)


def _clamp(value: float, low: float = -100.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def evaluate_discrete_map(params: dict, value: str | None) -> float | None:
    """
    Mapea un valor de cadena a un score según un diccionario.
    Devuelve None si el valor es None o no está en el mapa.
    """
    if value is None:
        return None
    mapping: dict = params.get("map", {})
    result = mapping.get(value)
    return float(result) if result is not None else None


def evaluate_threshold(params: dict, value: float | None) -> float | None:
    """
    Recorre thresholds en orden; retorna el score del primer límite donde value > limit.
    El último par [null, score] actúa como default.
    """
    if value is None:
        return None
    thresholds: list = params.get("thresholds", [])
    for limit, score in thresholds:
        if limit is None:
            return float(score)
        if value > limit:
            return float(score)
    return None


def evaluate_range(params: dict, value: float | None) -> float | None:
    """
    Mapea un valor numérico dentro de [min, max] a [-100, 100] de forma lineal.
    Si clamp=True recorta valores fuera del rango; si False puede superar ±100.
    """
    if value is None:
        return None
    vmin: float = params.get("min", -100.0)
    vmax: float = params.get("max",  100.0)
    do_clamp: bool = params.get("clamp", True)

    span = vmax - vmin
    if span == 0:
        return 0.0

    normalized = ((value - vmin) / span) * 200.0 - 100.0
    if do_clamp:
        normalized = _clamp(normalized)
    return float(normalized)


def evaluate_composite(params: dict, scores_by_key: dict[str, float | None]) -> float | None:
    """
    Promedio ponderado de scores de otras señales.
    Ignora componentes cuyo score sea None.
    Devuelve None si todos los componentes son None.
    """
    components: list = params.get("components", [])
    total_weight = 0.0
    weighted_sum = 0.0

    for comp in components:
        key    = comp.get("signal_key")
        weight = float(comp.get("weight", 1.0))
        score  = scores_by_key.get(key)
        if score is not None:
            weighted_sum  += score * weight
            total_weight  += weight

    if total_weight == 0:
        return None
    return float(weighted_sum / total_weight)


def evaluate(
    formula_type: str,
    params_json: str,
    value,
    scores_by_key: dict[str, float | None] | None = None,
) -> float | None:
    """
    Punto de entrada unificado.

    Args:
        formula_type:   "discrete_map" | "threshold" | "range" | "composite"
        params_json:    JSON serializado de los parámetros
        value:          valor del indicador (str para discrete_map, float para el resto,
                        ignorado en composite)
        scores_by_key:  dict {signal_key: score} requerido para composite
    Returns:
        score float en [-100, 100] o None si no computable
    """
    try:
        params = json.loads(params_json)
    except (json.JSONDecodeError, TypeError):
        logger.error("signal_engine: params_json inválido: %r", params_json)
        return None

    if formula_type == "discrete_map":
        return evaluate_discrete_map(params, value)
    if formula_type == "threshold":
        return evaluate_threshold(params, value)
    if formula_type == "range":
        return evaluate_range(params, value)
    if formula_type == "composite":
        return evaluate_composite(params, scores_by_key or {})

    logger.warning("signal_engine: formula_type desconocido: %r", formula_type)
    return None
