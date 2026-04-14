from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Optional

import pandas as pd


@dataclass
class AssetMetadata:
    name: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    currency_iso: Optional[str] = None
    exchange: Optional[str] = None


@dataclass
class TickerValidationResult:
    valid: bool
    metadata: Optional[AssetMetadata] = None
    error: Optional[str] = None


class PriceSourceBase(ABC):
    """Interfaz que debe implementar cada fuente de precios."""

    SOURCE_NAME: str = ""  # Debe coincidir con PriceSource.name en la BD

    @abstractmethod
    def validate_ticker(self, ticker: str) -> TickerValidationResult:
        """Verifica si el ticker existe y devuelve los metadatos disponibles."""
        ...

    @abstractmethod
    def download_history(
        self, ticker: str, start: Optional[date] = None
    ) -> pd.DataFrame:
        """
        Descarga datos OHLCV.

        Si start es None, descarga toda la historia disponible.
        Devuelve DataFrame con columnas: date, open, high, low, close, volume.
        La columna date debe ser de tipo datetime.date.
        Lanza excepción si falla la descarga.
        """
        ...
