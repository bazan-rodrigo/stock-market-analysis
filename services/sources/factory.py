# -*- coding: utf-8 -*-
"""
Fabrica de adaptadores de fuentes de datos.
Permite crear dinamicamente el objeto correcto segun el codigo de fuente.
"""

from typing import Dict, Type
from .base_source import PriceSourceAdapter
from .yahoo_source import YahooFinanceSource

# Implementaciones placeholder para futuras fuentes
class AlphaVantageSource(PriceSourceAdapter):
    def download_daily_prices(self, symbol, start, end): raise NotImplementedError()
    def get_metadata(self, symbol): return {}

class FinnhubSource(PriceSourceAdapter):
    def download_daily_prices(self, symbol, start, end): raise NotImplementedError()
    def get_metadata(self, symbol): return {}

class PolygonSource(PriceSourceAdapter):
    def download_daily_prices(self, symbol, start, end): raise NotImplementedError()
    def get_metadata(self, symbol): return {}

# Registro central de fuentes
SOURCES_MAP: Dict[str, Type[PriceSourceAdapter]] = {
    "YAHOO": YahooFinanceSource,
    "ALPHAVANTAGE": AlphaVantageSource,
    "FINNHUB": FinnhubSource,
    "POLYGON": PolygonSource,
}

def get_source_adapter(code: str, **kwargs) -> PriceSourceAdapter:
    """
    Devuelve una instancia del adaptador correspondiente al codigo de fuente.
    Lanza error si la fuente no existe.
    """
    cls = SOURCES_MAP.get(code.upper())
    if not cls:
        raise ValueError(f"Unknown source code: {code}")
    return cls(**kwargs)