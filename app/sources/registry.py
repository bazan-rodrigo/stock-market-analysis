from typing import Type

from app.sources.base import PriceSourceBase
from app.sources.calculated import CalculatedSource
from app.sources.yahoo import YahooFinanceSource

_REGISTRY: dict[str, Type[PriceSourceBase]] = {}


def register(cls: Type[PriceSourceBase]) -> None:
    _REGISTRY[cls.SOURCE_NAME] = cls


def get_source(name: str) -> PriceSourceBase:
    if name not in _REGISTRY:
        raise ValueError(
            f"Fuente desconocida: '{name}'. Disponibles: {list(_REGISTRY.keys())}"
        )
    return _REGISTRY[name]()


def available_source_names() -> list[str]:
    return list(_REGISTRY.keys())


# Registro de fuentes disponibles
register(YahooFinanceSource)
register(CalculatedSource)
