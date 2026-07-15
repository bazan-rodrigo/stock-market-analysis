"""
Perfila el optimizador de parámetros del simulador (grid search sobre
trade_simulator) con una serie sintética realista, en dos escenarios:
típico (estructura chica, cientos de combos) y estrés (cerca del tope).

    python scripts/profile_trade_optimizer.py
"""
import cProfile
import io
import math
import pstats
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import os
os.environ.setdefault("DATABASE_URL", f"sqlite:///{ROOT / '.profile-stub.db'}")

from app.services.trade_optimizer import build_combos, optimize

N_BARS = 2500


def _series():
    rng = random.Random(7)
    closes, scores, pcts = [], [], []
    price = 100.0
    score = 20.0
    for _ in range(N_BARS):
        price *= math.exp(rng.gauss(0.0003, 0.02))
        score = max(-100, min(100, score + rng.gauss(0, 8)))
        closes.append(price)
        scores.append(score if rng.random() > 0.05 else None)  # huecos de filtro
        pcts.append(min(100, max(0, 50 + score / 2)))
    return closes, scores, pcts


def _run(name, spec, closes, scores, pcts):
    n_combos = len(build_combos(spec))
    prof = cProfile.Profile()
    t0 = time.perf_counter()
    prof.enable()
    out = optimize(closes, scores, pcts, spec, min_trades=5)
    prof.disable()
    wall = time.perf_counter() - t0
    print(f"\n=== {name}: {n_combos} combos x {N_BARS} barras → {wall:.2f}s "
          f"({wall / n_combos * 1000:.2f} ms/combo) — "
          f"{len(out['results'])} en el top, {out['n_valid']} válidos ===")
    s = io.StringIO()
    pstats.Stats(prof, stream=s).strip_dirs().sort_stats("tottime").print_stats(10)
    print(s.getvalue())


def main():
    closes, scores, pcts = _series()

    tipico = {"entries": [{"type": "score", "th": 20}],
              "score_exits": [{"type": "trailing_score", "x": 20}],
              "caps": [{"type": "stop_loss", "pct": 10}],
              "rearm": True}
    _run("típico (Sc≥ + Máx−Δ + SL)", tipico, closes, scores, pcts)

    estres = {"entries": [{"type": "score", "th": 20}],
              "score_exits": [{"type": "absolute", "x": 0},
                              {"type": "trailing_score", "x": 20}],
              "caps": [{"type": "stop_loss", "pct": 10},
                       {"type": "max_bars", "n": 60}],
              "rearm": True}
    _run("estrés (5 ejes, 2240 combos)", estres, closes, scores, pcts)


if __name__ == "__main__":
    main()
