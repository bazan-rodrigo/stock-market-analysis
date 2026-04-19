import pandas as pd

from app.sources.base import AssetMetadata, PriceSourceBase, TickerValidationResult


class CalculatedSource(PriceSourceBase):
    """
    Fuente interna: los precios se calculan como cociente de dos activos.
    No realiza ninguna conexión externa.
    """
    SOURCE_NAME = "Calculado"

    def validate_ticker(self, ticker: str) -> TickerValidationResult:
        return TickerValidationResult(valid=True, metadata=AssetMetadata())

    def download_history(self, ticker: str, start=None) -> pd.DataFrame:
        raise NotImplementedError(
            "Fuente 'Calculado': los precios se generan internamente, "
            "no se descargan de fuentes externas."
        )
