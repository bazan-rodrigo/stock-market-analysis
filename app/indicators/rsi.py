import pandas as pd

from app.indicators.base import IndicatorBase, IndicatorParam, PANEL_SEPARATE


class RSIIndicator(IndicatorBase):
    NAME = "rsi"
    LABEL = "RSI"
    PANEL = PANEL_SEPARATE
    PARAMS = [IndicatorParam("period", "Período", "int", 14, 2, 100, 1)]

    def compute(self, df: pd.DataFrame, period: int = 14, **kwargs) -> dict[str, pd.Series]:
        period = int(period)
        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, float("nan"))
        rsi = (100 - (100 / (1 + rs))).fillna(100)
        return {f"RSI {period}": rsi}
