from typing import Type

from app.sources.fundamental.base import FundamentalSourceBase
from app.sources.fundamental.yahoo import YahooFundamentalSource

_REGISTRY: dict[str, Type[FundamentalSourceBase]] = {}


def register(cls: Type[FundamentalSourceBase]) -> None:
    _REGISTRY[cls.SOURCE_NAME] = cls


def get_fundamental_source(name: str) -> FundamentalSourceBase:
    if name not in _REGISTRY:
        raise ValueError(f"Fuente de fundamentales desconocida: '{name}'. Disponibles: {list(_REGISTRY.keys())}")
    return _REGISTRY[name]()


register(YahooFundamentalSource)
