"""
Catálogo de valores posibles de los indicadores categóricos (type='str').

Fuente única compartida por:
  - verification_service (chequeo de cordura: ¿la categoría guardada existe?)
  - el constructor de filtros de estrategia (dropdown de valores + validación
    del árbol de condiciones al guardar)

Si technical_service agrega una categoría nueva (p.ej. un régimen de
tendencia), hay que sumarla acá — verification_service la marcaría como
"categoría desconocida" y el constructor de filtros no la ofrecería.
"""

# trend_*: combinaciones de _regime_detail (technical_service.py:164).
TREND_VALUES = frozenset({
    "bullish", "bearish", "lateral",
    "bullish_nascent", "bearish_nascent", "lateral_nascent",
    "bullish_strong", "bearish_strong",
    "bullish_nascent_strong", "bearish_nascent_strong",
})

# volatility_*: f"{vol_regime}_{dur_regime}" (technical_service.py:282, 248).
VOLATILITY_VALUES = frozenset({
    f"{v}_{d}" for v in ("baja", "normal", "alta", "extrema")
    for d in ("corta", "media", "larga")
})

CATEGORICAL_VALUES: dict[str, frozenset] = {
    "trend_daily": TREND_VALUES, "trend_weekly": TREND_VALUES,
    "trend_monthly": TREND_VALUES,
    "volatility_daily": VOLATILITY_VALUES, "volatility_weekly": VOLATILITY_VALUES,
    "volatility_monthly": VOLATILITY_VALUES,
}


def get_categorical_values(code: str) -> frozenset | None:
    """Valores posibles de un indicador categórico, o None si es numérico
    (o desconocido)."""
    return CATEGORICAL_VALUES.get(code)
