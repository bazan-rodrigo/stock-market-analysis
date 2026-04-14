import pandas as pd

from app.indicators.base import IndicatorBase, IndicatorParam, PANEL_OVERLAY


class SMAIndicator(IndicatorBase):
    NAME = "sma"
    LABEL = "SMA"
    PANEL = PANEL_OVERLAY
    PARAMS = [IndicatorParam("period", "Período", "int", 20, 2, 500, 1)]

    def compute(self, df: pd.DataFrame, period: int = 20, **kwargs) -> dict[str, pd.Series]:
        return {f"SMA {int(period)}": df["close"].rolling(window=int(period)).mean()}
