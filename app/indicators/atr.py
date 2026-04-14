import pandas as pd

from app.indicators.base import IndicatorBase, IndicatorParam, PANEL_SEPARATE


class ATRIndicator(IndicatorBase):
    NAME = "atr"
    LABEL = "ATR"
    PANEL = PANEL_SEPARATE
    PARAMS = [IndicatorParam("period", "Período", "int", 14, 2, 100, 1)]

    def compute(self, df: pd.DataFrame, period: int = 14, **kwargs) -> dict[str, pd.Series]:
        period = int(period)
        prev_close = df["close"].shift(1)
        tr = pd.concat(
            [
                df["high"] - df["low"],
                (df["high"] - prev_close).abs(),
                (df["low"] - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        return {f"ATR {period}": atr}
