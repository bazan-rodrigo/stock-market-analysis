import pandas as pd

from app.indicators.base import IndicatorBase, IndicatorParam, PANEL_OVERLAY


class BollingerBandsIndicator(IndicatorBase):
    NAME = "bollinger"
    LABEL = "Bandas de Bollinger"
    PANEL = PANEL_OVERLAY
    PARAMS = [
        IndicatorParam("period", "Período", "int", 20, 5, 100, 1),
        IndicatorParam("std_dev", "Desv. Estándar", "float", 2.0, 0.5, 4.0, 0.5),
    ]

    def compute(
        self, df: pd.DataFrame, period: int = 20, std_dev: float = 2.0, **kwargs
    ) -> dict[str, pd.Series]:
        period = int(period)
        sma = df["close"].rolling(window=period).mean()
        std = df["close"].rolling(window=period).std()
        upper = sma + std_dev * std
        lower = sma - std_dev * std
        label = f"BB({period},{std_dev})"
        return {
            f"{label} Superior": upper,
            f"{label} Media": sma,
            f"{label} Inferior": lower,
        }
