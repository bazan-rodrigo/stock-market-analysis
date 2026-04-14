from typing import Type

from app.indicators.base import IndicatorBase, PANEL_OVERLAY, PANEL_SEPARATE
from app.indicators.atr import ATRIndicator
from app.indicators.bollinger import BollingerBandsIndicator
from app.indicators.ema import EMAIndicator
from app.indicators.macd import MACDIndicator
from app.indicators.rsi import RSIIndicator
from app.indicators.sma import SMAIndicator
from app.indicators.stochastic import StochasticIndicator

_REGISTRY: dict[str, Type[IndicatorBase]] = {}


def register(cls: Type[IndicatorBase]) -> None:
    _REGISTRY[cls.NAME] = cls


def get_indicator(name: str) -> IndicatorBase:
    if name not in _REGISTRY:
        raise ValueError(f"Indicador desconocido: '{name}'")
    return _REGISTRY[name]()


def all_indicators() -> list[IndicatorBase]:
    return [cls() for cls in _REGISTRY.values()]


def overlay_indicators() -> list[IndicatorBase]:
    return [cls() for cls in _REGISTRY.values() if cls.PANEL == PANEL_OVERLAY]


def separate_indicators() -> list[IndicatorBase]:
    return [cls() for cls in _REGISTRY.values() if cls.PANEL == PANEL_SEPARATE]


# Registro de indicadores disponibles
for _cls in [
    SMAIndicator,
    EMAIndicator,
    BollingerBandsIndicator,
    RSIIndicator,
    MACDIndicator,
    StochasticIndicator,
    ATRIndicator,
]:
    register(_cls)
