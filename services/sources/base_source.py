# -*- coding: utf-8 -*-
"""
Clase base para todas las fuentes de datos de precios.
Cada fuente (Yahoo, AlphaVantage, etc.) debe implementar esta interfaz.
"""

from abc import ABC, abstractmethod
import pandas as pd
from typing import Dict, Any

class PriceSourceAdapter(ABC):
    """
    Clase abstracta que define la estructura minima
    para cualquier adaptador de fuente de precios.
    """

    @abstractmethod
    def download_daily_prices(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        """
        Debe devolver un DataFrame con las columnas:
        trade_date, open, high, low, close, adj_close, volume
        """
        raise NotImplementedError()

    @abstractmethod
    def get_metadata(self, symbol: str) -> Dict[str, Any]:
        """
        Devuelve informacion adicional del activo (nombre, sector, moneda, etc.)
        """
        return {}