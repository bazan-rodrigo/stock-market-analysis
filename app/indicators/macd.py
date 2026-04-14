import pandas as pd

from app.indicators.base import IndicatorBase, IndicatorParam, PANEL_SEPARATE


class MACDIndicator(IndicatorBase):
    NAME = "macd"
    LABEL = "MACD"
    PANEL = PANEL_SEPARATE
    PARAMS = [
        IndicatorParam("fast", "EMA Rápida", "int", 12, 2, 100, 1),
        IndicatorParam("slow", "EMA Lenta", "int", 26, 2, 200, 1),
        IndicatorParam("signal", "Señal", "int", 9, 2, 50, 1),
    ]

    def compute(
        self,
        df: pd.DataFrame,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
        **kwargs,
    ) -> dict[str, pd.Series]:
        fast_ema = df["close"].ewm(span=int(fast), adjust=False).mean()
        slow_ema = df["close"].ewm(span=int(slow), adjust=False).mean()
        macd_line = fast_ema - slow_ema
        signal_line = macd_line.ewm(span=int(signal), adjust=False).mean()
        histogram = macd_line - signal_line
        return {
            "MACD": macd_line,
            "Señal MACD": signal_line,
            "Histograma MACD": histogram,
        }
