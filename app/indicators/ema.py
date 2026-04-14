import pandas as pd

from app.indicators.base import IndicatorBase, IndicatorParam, PANEL_OVERLAY


class EMAIndicator(IndicatorBase):
    NAME = "ema"
    LABEL = "EMA"
    PANEL = PANEL_OVERLAY
    PARAMS = [IndicatorParam("period", "Período", "int", 20, 2, 500, 1)]

    def compute(self, df: pd.DataFrame, period: int = 20, **kwargs) -> dict[str, pd.Series]:
        return {
            f"EMA {int(period)}": df["close"].ewm(span=int(period), adjust=False).mean()
        }
