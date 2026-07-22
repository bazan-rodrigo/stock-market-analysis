import logging
from datetime import date
from typing import Optional

import pandas as pd
import requests
import yfinance as yf

from app.sources.base import AssetMetadata, PriceSourceBase, TickerValidationResult

logger = logging.getLogger(__name__)

_YF_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d"
_YF_HEADERS   = {"User-Agent": "Mozilla/5.0"}


class YahooFinanceSource(PriceSourceBase):
    SOURCE_NAME = "Yahoo Finance"

    def validate_ticker(self, ticker: str,
                        need_metadata: bool = True) -> TickerValidationResult:
        # Validar con la API HTTP directa — más fiable que yfinance para índices e internacionales
        try:
            r = requests.get(
                _YF_CHART_URL.format(ticker=ticker),
                headers=_YF_HEADERS,
                timeout=10,
            )
            if r.status_code == 429:
                # Distinguir rate-limit de "no existe": el import masivo
                # reintenta con backoff los errores transitorios.
                return TickerValidationResult(
                    valid=False, error="Rate limit de Yahoo Finance (HTTP 429)"
                )
            if r.status_code != 200:
                return TickerValidationResult(
                    valid=False, error="Ticker no encontrado en Yahoo Finance"
                )
        except Exception as exc:
            logger.warning("Error HTTP validando ticker %s: %s", ticker, exc)
            return TickerValidationResult(valid=False, error=str(exc))

        if not need_metadata:
            # El llamador ya tiene todos los campos: se evita el .info (es
            # el paso lento — un request extra y pesado por ticker).
            return TickerValidationResult(valid=True, metadata=AssetMetadata())

        # .info para metadata — puede estar incompleto en índices/ETFs, no es bloqueante
        try:
            info = yf.Ticker(ticker).info or {}
        except Exception:
            info = {}

        meta = AssetMetadata(
            name=info.get("longName") or info.get("shortName"),
            sector=info.get("sector"),
            industry=info.get("industry"),
            currency_iso=info.get("currency"),
            exchange=info.get("exchange"),
            exchange_name=info.get("fullExchangeName") or info.get("exchange"),
            country=info.get("country"),
            quote_type=info.get("quoteType"),
        )
        return TickerValidationResult(valid=True, metadata=meta)

    def download_history(
        self, ticker: str, start: Optional[date] = None
    ) -> pd.DataFrame:
        t = yf.Ticker(ticker)
        if start is None:
            df = t.history(period="max", auto_adjust=True)
        else:
            df = t.history(start=start.isoformat(), auto_adjust=True)

        if df.empty:
            return pd.DataFrame(
                columns=["date", "open", "high", "low", "close", "volume"]
            )

        df = df.reset_index()
        df.rename(
            columns={
                "Date": "date",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            },
            inplace=True,
        )

        # Normalizar a datetime.date (yfinance puede devolver Timestamp con tz)
        df["date"] = pd.to_datetime(df["date"]).dt.date

        return df[["date", "open", "high", "low", "close", "volume"]]
