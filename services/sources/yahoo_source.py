# -*- coding: utf-8 -*-
"""
Implementacion de la fuente de precios Yahoo Finance usando la libreria yfinance.
"""

import pandas as pd
import yfinance as yf
from typing import Dict, Any
from .base_source import PriceSourceAdapter

class YahooFinanceSource(PriceSourceAdapter):
    """Adaptador para Yahoo Finance."""

    def __init__(self) -> None:
        pass

    def download_daily_prices(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        """
        Descarga precios diarios OHLCV desde Yahoo Finance.
        Incluye columna 'Adj Close' ajustada.
        """
        df = yf.download(symbol, start=start, end=end, auto_adjust=False, actions=False, progress=False)
        if df is None or df.empty:
            return pd.DataFrame(columns=["trade_date","open","high","low","close","adj_close","volume"])

        # Renombrar columnas para mantener consistencia
        df = df.reset_index()
        df.rename(columns={
            "Date": "trade_date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adj_close",
            "Volume": "volume",
        }, inplace=True)

        # Formatear tipos de datos
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
        for c in ["open","high","low","close","adj_close","volume"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")

        return df[["trade_date","open","high","low","close","adj_close","volume"]]

    def get_metadata(self, symbol: str) -> Dict[str, Any]:
        """
        Devuelve metadatos basicos del activo desde Yahoo (nombre, sector, moneda, etc.)
        """
        try:
            t = yf.Ticker(symbol)
            raw = t.info or {}
            return {
                "longName": raw.get("longName"),
                "sector": raw.get("sector"),
                "industry": raw.get("industry"),
                "currency": raw.get("currency"),
                "exchange": raw.get("exchange"),
            }
        except Exception:
            return {}