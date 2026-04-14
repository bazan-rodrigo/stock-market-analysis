from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

PANEL_OVERLAY = "overlay"    # Se superpone al gráfico de precios
PANEL_SEPARATE = "separate"  # Tiene su propio subplot debajo del gráfico


@dataclass
class IndicatorParam:
    name: str
    label: str
    type: str          # "int" | "float"
    default: float
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    step: Optional[float] = None


class IndicatorBase(ABC):
    NAME: str = ""
    LABEL: str = ""
    PANEL: str = PANEL_OVERLAY
    PARAMS: list[IndicatorParam] = field(default_factory=list)

    @abstractmethod
    def compute(self, df: pd.DataFrame, **params) -> dict[str, pd.Series]:
        """
        Calcula el indicador.

        df: DataFrame con columnas date, open, high, low, close, volume.
        params: argumentos con los mismos nombres que PARAMS.
        Devuelve dict nombre_serie -> pd.Series alineada con el índice de df.
        """
        ...

    @property
    def default_params(self) -> dict:
        return {p.name: p.default for p in self.PARAMS}
