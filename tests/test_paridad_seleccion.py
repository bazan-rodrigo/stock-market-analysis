"""Paridad de las fechas de referencia vectorizadas.

_ref_return_vs_ref es la copia literal de la versión anterior (fecha por
fecha); la versión vectorizada con pandas Period debe producir exactamente
los mismos retornos, incluyendo el manejo del 29/2 en year_back.
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.services.technical_service import (
    _Q_MONTH, _one_year_before, _return_vs_ref_series,
)


def _ref_return_vs_ref(df, ref_date_fn):
    """Copia literal de la implementación anterior (loop por fecha)."""
    dates    = df["date"].values
    closes   = df["close"].values.astype(float)
    ordinals = np.array([d.toordinal() for d in dates])
    ref_ords = np.empty(len(dates), dtype=np.int64)
    for i, d in enumerate(dates):
        try:
            ref_ords[i] = ref_date_fn(d).toordinal()
        except ValueError:
            ref_ords[i] = -1
    indices    = np.searchsorted(ordinals, ref_ords, side="right") - 1
    valid      = (indices >= 0) & (ref_ords >= 0)
    ref_closes = closes[np.where(valid, indices, 0)]
    return np.where(valid & (ref_closes != 0),
                    np.round((closes / ref_closes - 1) * 100, 2), np.nan)


_LAMBDAS = {
    "month_start":   lambda d: d.replace(day=1),
    "quarter_start": lambda d: date(d.year, _Q_MONTH[d.month], 1),
    "year_start":    lambda d: date(d.year, 1, 1),
    "year_back":     _one_year_before,
}


@pytest.mark.parametrize("kind", list(_LAMBDAS))
def test_return_vs_ref_paridad(kind):
    rng = np.random.RandomState(9)
    # 900 días desde nov-2023: cruza el 29/2/2024 (bisiesto) y varios años
    n = 900
    df = pd.DataFrame({
        "date":  [date(2023, 11, 1) + timedelta(days=i) for i in range(n)],
        "close": np.abs(100 + rng.randn(n).cumsum()) + 5,
    })
    esperado = _ref_return_vs_ref(df, _LAMBDAS[kind])
    obtenido = _return_vs_ref_series(df, kind).to_numpy()
    assert np.allclose(obtenido, esperado, equal_nan=True)
