"""
Motor de evaluación de fórmulas de señales.
Puro (sin acceso a DB): recibe parámetros y valores, devuelve scores -100..100.

Tipos de fórmula soportados:
  discrete_map  — {"map": {"bullish": 60, ...}}  → valor string → score int
  threshold     — {"thresholds": [[limit, score], ..., [null, default]]}
                  Evaluación: primer límite donde valor > limit → score; null = default
  range         — {"min": x, "max": y, "clamp": true/false}
                  Mapea valor numérico a -100..100 de forma lineal

(La fórmula "composite" —promedio ponderado de otras señales— se removió: la
combinación de señales se hace en la estrategia, con componentes ponderados.)
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


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate_params(formula_type: str, params: dict) -> str | None:
    """Valida que params tenga la forma que evaluate() espera para ese tipo
    de fórmula. Devuelve un mensaje de error o None si es válido.

    Motivación: un params sintácticamente válido pero con la forma equivocada
    (p.ej. un 'map' en una señal threshold) no rompe nada — evaluate devuelve
    None silenciosamente y la señal nunca puntúa. Para el import masivo eso
    es una trampa; mejor rechazarlo con mensaje."""
    if formula_type == "discrete_map":
        m = params.get("map")
        if not isinstance(m, dict) or not m:
            return "discrete_map requiere 'map' (diccionario no vacío)"
        bad = [k for k, v in m.items() if not _is_number(v)]
        if bad:
            return f"scores no numéricos en map: {bad}"
        return None

    if formula_type == "threshold":
        th = params.get("thresholds")
        if not isinstance(th, list) or not th:
            return "threshold requiere 'thresholds' (lista no vacía)"
        for i, pair in enumerate(th):
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                return f"thresholds[{i}] debe ser un par [límite, score]"
            limit, score = pair
            if limit is not None and not _is_number(limit):
                return f"thresholds[{i}]: límite no numérico: {limit!r}"
            if not _is_number(score):
                return f"thresholds[{i}]: score no numérico: {score!r}"
        return None

    if formula_type == "range":
        vmin, vmax = params.get("min"), params.get("max")
        if not _is_number(vmin) or not _is_number(vmax):
            return "range requiere 'min' y 'max' numéricos"
        if vmin == vmax:
            return "range: min y max no pueden ser iguales"
        return None

    return f"formula_type desconocido: {formula_type!r}"


def evaluate(
    formula_type: str,
    params_json: str,
    value,
    params: dict | None = None,
) -> float | None:
    """
    Punto de entrada unificado.

    Args:
        formula_type:   "discrete_map" | "threshold" | "range"
        params_json:    JSON serializado de los parámetros
        value:          valor del indicador (str para discrete_map, float para el resto)
        params:         parámetros ya parseados; evita re-parsear params_json en
                        llamadas repetidas con la misma señal
    Returns:
        score float en [-100, 100] o None si no computable
    """
    if params is None:
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

    logger.warning("signal_engine: formula_type desconocido: %r", formula_type)
    return None
