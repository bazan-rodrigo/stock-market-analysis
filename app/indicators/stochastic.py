import pandas as pd

from app.indicators.base import IndicatorBase, IndicatorParam, PANEL_SEPARATE


class StochasticIndicator(IndicatorBase):
    NAME = "stochastic"
    LABEL = "Estocástico"
    PANEL = PANEL_SEPARATE
    PARAMS = [
        IndicatorParam("k_period", "Período %K", "int", 14, 2, 100, 1),
        IndicatorParam("d_period", "Período %D (suavizado)", "int", 3, 1, 20, 1),
    ]

    def compute(
        self, df: pd.DataFrame, k_period: int = 14, d_period: int = 3, **kwargs
    ) -> dict[str, pd.Series]:
        k_period, d_period = int(k_period), int(d_period)
        low_min = df["low"].rolling(window=k_period).min()
        high_max = df["high"].rolling(window=k_period).max()
        denom = (high_max - low_min).replace(0, float("nan"))
        k = 100 * (df["close"] - low_min) / denom
        d = k.rolling(window=d_period).mean()
        return {f"%K ({k_period})": k, f"%D ({d_period})": d}
