# -*- coding: utf-8 -*-
"""
Servicio: price_fetchers.py
--------------------------------------------
Provee funciones para obtener precios historicos
desde distintas fuentes de datos (ej. Yahoo Finance).
Cada funcion devuelve un DataFrame con columnas:
['Date', 'Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']
"""

import pandas as pd
import yfinance as yf
from datetime import date
from core.logging_config import get_logger

logger = get_logger(__name__)


def yahoo_fetch_prices(symbol: str, start_date: date) -> pd.DataFrame:
    """
    Descarga precios historicos diarios desde Yahoo Finance.
    Retorna un DataFrame ordenado por fecha ascendente.
    """
    try:
        logger.info(f"Descargando precios de {symbol} desde Yahoo Finance (inicio: {start_date})")
        data = yf.download(symbol, start=start_date)
        if data.empty:
            raise ValueError(f"No se obtuvieron datos para {symbol}")

        data.reset_index(inplace=True)
        data["Date"] = pd.to_datetime(data["Date"]).dt.date
        logger.info(f"{len(data)} registros obtenidos para {symbol}.")
        return data

    except Exception as e:
        logger.error(f"Error al descargar precios de {symbol} desde Yahoo: {e}")
        raise


# ==========================================================
# Futuras implementaciones (ejemplos para otras fuentes)
# ==========================================================

def finnhub_fetch_prices(symbol: str, start_date: date) -> pd.DataFrame:
    """
    Ejemplo de funcion placeholder para Finnhub.
    """
    raise NotImplementedError("Descarga desde Finnhub no implementada aun.")


def alphavantage_fetch_prices(symbol: str, start_date: date) -> pd.DataFrame:
    """
    Ejemplo de funcion placeholder para AlphaVantage.
    """
    raise NotImplementedError("Descarga desde AlphaVantage no implementada aun.")