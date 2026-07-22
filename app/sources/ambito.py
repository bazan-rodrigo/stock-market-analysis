import logging
from datetime import date, datetime
from typing import Optional

import pandas as pd
import requests

from app.sources.base import AssetMetadata, PriceSourceBase, TickerValidationResult

logger = logging.getLogger(__name__)

_BASE_URL = "https://mercados.ambito.com/riesgopais/historico-general"
_HEADERS = {"User-Agent": "Mozilla/5.0"}
_VALID_TICKERS = {"RIESGO_PAIS_AR"}
_EARLIEST = date(1998, 12, 11)


class AmbitoSource(PriceSourceBase):
    """
    Fuente: Ámbito Financiero — Riesgo País Argentina (EMBI JP Morgan).
    Ticker aceptado: RIESGO_PAIS_AR
    Cobertura: 11/12/1998 → hoy, frecuencia diaria.
    """

    SOURCE_NAME = "Ambito"

    def validate_ticker(self, ticker: str,
                        need_metadata: bool = True) -> TickerValidationResult:
        if ticker.upper() not in _VALID_TICKERS:
            return TickerValidationResult(
                valid=False,
                error=f"Ticker no reconocido por Ambito. Usar: {sorted(_VALID_TICKERS)}",
            )
        return TickerValidationResult(
            valid=True,
            metadata=AssetMetadata(
                name="Riesgo País Argentina (EMBI)",
                country="Argentina",
                currency_iso="USD",
                quote_type="INDEX",
            ),
        )

    def download_history(
        self, ticker: str, start: Optional[date] = None
    ) -> pd.DataFrame:
        desde = start if start is not None else _EARLIEST
        hasta = date.today()

        url = f"{_BASE_URL}/{desde.isoformat()}/{hasta.isoformat()}"
        logger.info("Ambito EMBI: GET %s", url)

        try:
            r = requests.get(url, headers=_HEADERS, timeout=20)
            r.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"Error descargando riesgo país de Ámbito: {exc}") from exc

        raw = r.json()
        if not isinstance(raw, list) or len(raw) < 2:
            raise RuntimeError("Respuesta inesperada de Ámbito: sin datos")

        rows = raw  # sin header separado; cada elemento es [fecha, valor]
        records = []
        for item in rows:
            if not isinstance(item, list) or len(item) < 2:
                continue
            try:
                fecha = datetime.strptime(item[0], "%d-%m-%Y").date()
                valor = float(str(item[1]).replace(",", "."))
                records.append({"date": fecha, "close": valor})
            except (ValueError, TypeError):
                continue

        if not records:
            return pd.DataFrame(
                columns=["date", "open", "high", "low", "close", "volume"]
            )

        df = pd.DataFrame(records)
        df["open"] = df["close"]
        df["high"] = df["close"]
        df["low"] = df["close"]
        df["volume"] = 0
        df = df.sort_values("date").reset_index(drop=True)

        return df[["date", "open", "high", "low", "close", "volume"]]
