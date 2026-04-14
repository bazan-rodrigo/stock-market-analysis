import logging
from datetime import date
from typing import Optional

import pandas as pd
import yfinance as yf

from app.sources.base import AssetMetadata, PriceSourceBase, TickerValidationResult

logger = logging.getLogger(__name__)


class YahooFinanceSource(PriceSourceBase):
    SOURCE_NAME = "Yahoo Finance"

    def validate_ticker(self, ticker: str) -> TickerValidationResult:
        try:
            t = yf.Ticker(ticker)
            info = t.info or {}

            # yfinance devuelve dict vacío o mínimo para tickers inválidos
            has_price = any(
                info.get(k) is not None
                for k in ("regularMarketPrice", "currentPrice", "previousClose")
            )
            if not has_price:
                # Intento adicional con fast_info
                try:
                    fi = t.fast_info
                    if getattr(fi, "last_price", None) is None:
                        return TickerValidationResult(
                            valid=False, error="Ticker no encontrado en Yahoo Finance"
                        )
                except Exception:
                    return TickerValidationResult(
                        valid=False, error="Ticker no encontrado en Yahoo Finance"
                    )

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

        except Exception as exc:
            logger.warning("Error validando ticker %s en Yahoo Finance: %s", ticker, exc)
            return TickerValidationResult(valid=False, error=str(exc))

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
