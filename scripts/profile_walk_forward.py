"""
Perfila `walk_forward` (app/services/portfolio_backtest_service.py) — el candidato
#1 de performance del módulo Backtest: grid (top_n × trailing) × ventanas, y cada
combinación reconstruye paneles (`_panels_for_range` → simulate_trades por activo +
build_panels) y corre `simulate_gated`.

Corre 100% LOCAL sin base de datos: monkeypatchea `_load_universe` (el único
seam de BD de walk_forward — mismo punto que los tests `test_walk_forward_*`)
para devolver un universo SINTÉTICO de random-walk (~80 activos × ~750 fechas),
y usa una sesión dummy (walk_forward sólo llama session.rollback() tras la carga).

Uso:
    python scripts/profile_walk_forward.py
    python scripts/profile_walk_forward.py 60 500   # n_assets n_dates
"""
import cProfile
import io
import os
import pstats
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Sin BD: apuntar DATABASE_URL a un stub sqlite ANTES de importar app (igual que
# tests/conftest.py). walk_forward igual no toca la base porque _load_universe
# está monkeypatcheado; esto sólo permite importar los servicios sin el driver.
os.environ.setdefault("DATABASE_URL", f"sqlite:///{ROOT / '.profile-stub.db'}")

import numpy as np

from app.services import portfolio_backtest_service as pbs


# Spec base del simulador (contrato de trade_simulator). El walk-forward reemplaza
# el trailing_stop por cada valor de trail_grid; rearm=True para que los stops
# generen re-entradas → churn de elegibilidad representativo.
_BASE_SPEC = {
    "entries": [{"type": "score", "th": 5.0}],
    "score_exits": [],
    "caps": [{"type": "trailing_stop", "pct": 15.0}],
    "rearm": True,
    "cooldown": 0,
}


class _DummySession:
    """walk_forward sólo invoca session.rollback() tras _load_universe."""

    def rollback(self):
        pass


def _synthetic_universe(n_assets, n_dates, seed=0):
    """{aid: {dates, closes, scores, pcts}} día-completo (sin huecos), la forma
    exacta que devuelve `_load_universe`/`_load_raw`. Closes random-walk positivos
    (idea de _random_walk_df en tests/test_paridad_zonas.py); scores ruidosos
    alrededor del umbral de entrada (5) para que las entradas disparen y el
    ranking transversal (top-N) rote. pcts=None (la spec usa entries de tipo
    'score', no 'pct')."""
    rng = np.random.RandomState(seed)
    dates = [date(2015, 1, 1) + timedelta(days=i) for i in range(n_dates)]
    per_asset = {}
    for aid in range(1, n_assets + 1):
        close = np.abs(100.0 + (rng.randn(n_dates) * 1.0).cumsum()) + 5.0
        scores = 5.0 + rng.randn(n_dates) * 4.0
        per_asset[aid] = {
            "dates": dates,
            "closes": [float(c) for c in close],
            "scores": [float(s) for s in scores],
            "pcts": [None] * n_dates,
        }
    return dates, per_asset


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
    n_assets = int(sys.argv[1]) if len(sys.argv) > 1 else 80
    n_dates = int(sys.argv[2]) if len(sys.argv) > 2 else 750

    _dates, universe = _synthetic_universe(n_assets, n_dates)
    # Monkeypatch del único seam de BD: _load_universe → universo sintético.
    pbs._load_universe = lambda *a, **k: universe

    topn_grid = (10, 20, 30)
    trail_grid = (10.0, 15.0, 20.0)
    n_windows = 4
    print(f"Universo sintético: {n_assets} activos × {n_dates} fechas | "
          f"grid top_n={topn_grid} × trailing={trail_grid} × {n_windows} ventanas")

    def run():
        return pbs.walk_forward(_DummySession(), 1, _BASE_SPEC,
                                topn_grid=topn_grid, trail_grid=trail_grid,
                                n_windows=n_windows)

    # Chequeo de humo: una corrida real produce curva OOS no vacía.
    out = run()
    print(f"OOS: {len(out['oos_equity'])} puntos, {len(out['windows'])} "
          f"ventanas | equity final={out['oos_equity'][-1]:.4f}")

    _profile("walk_forward (grid completo × ventanas)", run, n_reps=3)


if __name__ == "__main__":
    main()
