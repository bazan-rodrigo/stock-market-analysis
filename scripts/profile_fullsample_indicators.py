"""
Perfila los otros indicadores full_sample prioritarios de technical_service:
dist_optimal_sma_{d,w,m} y relative_strength_52w.

Ambos son cómputo esencialmente PURO sobre DataFrames de precios, por lo que
corren LOCAL con datos sintéticos (random-walk, mismo generador que
tests/test_paridad_zonas.py). El único acoplamiento a BD de cada uno se satisface
sin base:

  - _bf_dist_optimal_sma(tf): sólo mira la BD para leer best_sma_{d,w,m} vía
    _query_best_sma(asset_id, session, best_sma_cache). Si se le pasa un
    best_sma_cache (dict), NO toca la sesión → acá se le pasa uno sintético y
    session=None. El resto es rolling mean/std sobre el df.

  - _bf_relative_strength_52w: sólo usa la sesión para resolver el benchmark_id
    del activo (session.query(Asset.benchmark_id)...). Se cubre con una sesión
    stub mínima que devuelve ese id, y el precio del benchmark se pasa por
    price_cache (df sintético de benchmark). El resto es cómputo numpy puro
    (loop O(n) de ordinales + búsquedas vectorizadas as-of).

Corre siempre de a un solo df/hilo (sin ThreadPoolExecutor) para que cProfile
mida cómputo puro sin contención de GIL.

Uso (LOCAL en esta PC, o en el Codespace — no toca la BD):
    ./venv/Scripts/python.exe scripts/profile_fullsample_indicators.py

En el Codespace, para perfilar contra datos reales, se puede reemplazar el
random-walk por precios reales (patrón get_session + activo con más historia de
scripts/profile_vol_zones.py); relative_strength_52w además requeriría un activo
con benchmark configurado y su serie en price_cache (o dejar que la lea de la BD).
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

# DATABASE_URL a un stub sqlite (archivo temporal) ANTES de importar app (mismo
# criterio que tests/conftest.py): permite importar technical_service sin el
# driver MySQL. Se usa un archivo y no ":memory:" porque app/database.py pasa
# pool_size/max_overflow, que el pool de sqlite en memoria rechaza. El cómputo
# perfilado no toca la BD (best_sma_cache / stub session + price_cache).
_STUB = Path(tempfile.gettempdir()) / "profile_fullsample_stub.db"
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_STUB}")
os.environ.setdefault("USE_WIDE_IND_TABLES", "0")

import numpy as np
import pandas as pd

from app.services.technical_service import (
    _bf_dist_optimal_sma, _bf_relative_strength_52w, _resample_ohlc,
)

ASSET_ID = 1
BENCH_ID = 999


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


class _StubSession:
    """Sesión mínima: sólo responde el único query que _bf_relative_strength_52w
    hace fuera del price_cache — session.query(Asset.benchmark_id)...scalar().
    Evita levantar la BD para perfilar el cómputo local."""
    def __init__(self, bm_id):
        self._bm_id = bm_id

    def query(self, *a, **k):
        return self

    def filter(self, *a, **k):
        return self

    def scalar(self):
        return self._bm_id


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
    print(f"Random-walk sintetico (activo): {len(df)} barras diarias "
          f"-> {len(df_w)} semanales, {len(df_m)} mensuales")

    n_reps = 20

    # ── dist_optimal_sma_{d,w,m} ──────────────────────────────────────────────
    # best_sma_cache sintético: la BD queda fuera (_query_best_sma corta antes de
    # tocar la sesión). Períodos representativos (subconjunto de _MA_PERIODS).
    best_sma_cache = {ASSET_ID: {"best_sma_d": 200, "best_sma_w": 50, "best_sma_m": 20}}
    dist_d = _bf_dist_optimal_sma("d")
    dist_w = _bf_dist_optimal_sma("w")
    dist_m = _bf_dist_optimal_sma("m")

    _profile(
        "dist_optimal_sma_daily (best_sma=200)",
        lambda: dist_d(df=df, df_w=df_w, df_m=df_m, session=None,
                       asset_id=ASSET_ID, best_sma_cache=best_sma_cache),
        n_reps,
    )
    _profile(
        "dist_optimal_sma_weekly (best_sma=50)",
        lambda: dist_w(df=df, df_w=df_w, df_m=df_m, session=None,
                       asset_id=ASSET_ID, best_sma_cache=best_sma_cache),
        n_reps,
    )
    _profile(
        "dist_optimal_sma_monthly (best_sma=20)",
        lambda: dist_m(df=df, df_w=df_w, df_m=df_m, session=None,
                       asset_id=ASSET_ID, best_sma_cache=best_sma_cache),
        n_reps,
    )

    # ── relative_strength_52w ─────────────────────────────────────────────────
    # Benchmark sintético (otra semilla) por price_cache + sesión stub que
    # resuelve el benchmark_id. df_w/df_m no los usa la función (van None).
    bm_df = _random_walk_df(n_bars, seed=7)[["date", "close"]]
    session = _StubSession(BENCH_ID)
    price_cache = {BENCH_ID: bm_df}

    _profile(
        "relative_strength_52w (activo vs benchmark sintetico)",
        lambda: _bf_relative_strength_52w(
            df=df, df_w=None, df_m=None, session=session,
            asset_id=ASSET_ID, price_cache=price_cache),
        n_reps,
    )


if __name__ == "__main__":
    main()
