"""
Perfila el costo real de _compute_regime_zones (technical_service), el hermano
full_sample de _compute_vol_zones. Es cómputo PURO sobre un DataFrame de precios
(EMA + slope + máquina de confirmación + segmentación en zonas), así que corre
LOCAL con datos sintéticos — no necesita base de datos.

Corre siempre de a un solo df/hilo (sin ThreadPoolExecutor), para que cProfile
mida cómputo puro sin contención de GIL entre workers paralelos.

Uso (LOCAL en esta PC, o en el Codespace — da igual, no toca la BD):
    ./venv/Scripts/python.exe scripts/profile_regime_zones.py

Los datos son un random-walk sintético (mismo generador que
tests/test_paridad_zonas.py). En el Codespace se podría cambiar el df por precios
reales (patrón get_session + activo con más historia de scripts/profile_vol_zones.py)
y el config por _get_regime_config() (que sí necesita la BD); acá se usan los
mismos valores por defecto que crea _get_regime_config().
"""
import cProfile
import io
import os
import pstats
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Apuntar DATABASE_URL a un stub sqlite (archivo temporal) ANTES de importar app,
# para que el import de app.services.technical_service no exija el driver de MySQL
# (mismo criterio que tests/conftest.py). Se usa un archivo y no ":memory:" porque
# app/database.py pasa pool_size/max_overflow, que el pool de sqlite en memoria
# rechaza. El cómputo perfilado no toca la BD.
_STUB = Path(tempfile.gettempdir()) / "profile_regime_zones_stub.db"
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_STUB}")
os.environ.setdefault("USE_WIDE_IND_TABLES", "0")

import numpy as np
import pandas as pd

from app.services.technical_service import _compute_regime_zones, _resample_ohlc


def _random_walk_df(n, seed, vol=1.0):
    """Copia literal del generador de tests/test_paridad_zonas.py."""
    rng = np.random.RandomState(seed)
    close = 100 + rng.randn(n).cumsum() * vol
    close = np.abs(close) + 5
    return pd.DataFrame({
        "date":  [date(2015, 1, 1) + timedelta(days=i) for i in range(n)],
        "close": close,
        "high":  close * (1 + rng.rand(n) * 0.02),
        "low":   close * (1 - rng.rand(n) * 0.02),
    })


def _profile(label: str, fn, n_reps: int) -> None:
    pr = cProfile.Profile()
    t0 = time.perf_counter()
    pr.enable()
    for _ in range(n_reps):
        fn()
    pr.disable()
    elapsed = time.perf_counter() - t0

    print(f"\n{'=' * 70}\n{label}: {elapsed:.3f}s total ({n_reps} rep., "
          f"{elapsed / n_reps * 1000:.1f}ms/rep)\n{'=' * 70}")
    buf = io.StringIO()
    stats = pstats.Stats(pr, stream=buf).sort_stats("cumulative")
    stats.print_stats(15)
    print(buf.getvalue())


def main():
    n_bars = 3000
    df = _random_walk_df(n_bars, seed=42)
    df_w = _resample_ohlc(df, "W")
    df_m = _resample_ohlc(df, "M")
    print(f"Random-walk sintetico: {len(df)} barras diarias "
          f"-> {len(df_w)} semanales, {len(df_m)} mensuales")

    # Mismos valores por defecto que _get_regime_config() (technical_service):
    # ema por timeframe + slope_lookback/threshold + confirm/nascent/strong.
    ema_period_d, ema_period_w, ema_period_m = 200, 50, 20
    slope_lookback          = 20
    slope_threshold_pct     = 0.5
    confirm_bars            = 3
    nascent_bars            = 20
    strong_slope_multiplier = 2.0

    n_reps = 20  # repetido para que cProfile tenga señal sobre su propio overhead

    _profile(
        "regime_zones_daily (_compute_regime_zones, ema=200)",
        lambda: _compute_regime_zones(
            df, ema_period_d, slope_lookback, slope_threshold_pct,
            confirm_bars, nascent_bars, strong_slope_multiplier),
        n_reps,
    )
    _profile(
        "regime_zones_weekly (_compute_regime_zones, ema=50)",
        lambda: _compute_regime_zones(
            df_w, ema_period_w, slope_lookback, slope_threshold_pct,
            confirm_bars, nascent_bars, strong_slope_multiplier),
        n_reps,
    )
    _profile(
        "regime_zones_monthly (_compute_regime_zones, ema=20)",
        lambda: _compute_regime_zones(
            df_m, ema_period_m, slope_lookback, slope_threshold_pct,
            confirm_bars, nascent_bars, strong_slope_multiplier),
        n_reps,
    )


if __name__ == "__main__":
    main()
