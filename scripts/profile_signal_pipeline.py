"""
Perfila el CÓMPUTO PURO del pipeline de señales/estrategias — los evaluadores
compartidos por el camino por-fecha y el modo rango — aislado de la BD y de
la construcción as-of de snapshots (que tienen su propio costo de I/O).

Qué mide, por fecha (el loop caliente de un "Recalcular completo"):
  1. _evaluate_asset_signal_scores  (señales por activo)
  2. evaluate_tree_bulk             (filtro de elegibilidad de la estrategia)
  3. rank_strategy_assets           (score ponderado + orden)
  4. percent_ranks                  (percentil persistido, migración 0071)

Dataset sintético determinístico (sin BD): N_ASSETS × N_DATES con una mezcla
realista de señales (discrete_map / threshold / range) y una estrategia con
filtro AND. Corre en cualquier máquina:

    python scripts/profile_signal_pipeline.py [n_assets] [n_dates]
"""
import cProfile
import io
import json
import pstats
import random
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import os
os.environ.setdefault("DATABASE_URL", f"sqlite:///{ROOT / '.profile-stub.db'}")

from app.services.signal_engine import compile_evaluator
from app.services.signal_service import _evaluate_asset_signal_scores
from app.services.strategy_filter import evaluate_tree_bulk, parse_tree
from app.services.strategy_service import percent_ranks, rank_strategy_assets

N_ASSETS = int(sys.argv[1]) if len(sys.argv) > 1 else 500
N_DATES = int(sys.argv[2]) if len(sys.argv) > 2 else 250

_TRENDS = ["bullish", "bullish_strong", "lateral", "bearish", "bearish_strong"]


def _build_signals():
    """6 señales de activo con la mezcla de fórmulas del pack momentum."""
    specs = [
        ("tendencia_d", "trend_daily", "discrete_map",
         {"map": {"bullish": 80, "bullish_strong": 100, "lateral": 0,
                  "bearish": -80, "bearish_strong": -100}}),
        ("tendencia_w", "trend_weekly", "discrete_map",
         {"map": {"bullish": 80, "bullish_strong": 100, "lateral": 0,
                  "bearish": -80, "bearish_strong": -100}}),
        ("rsi_zona", "rsi_daily", "threshold",
         {"thresholds": [[70, -60], [55, 40], [45, 0], [30, -40], [None, 60]]}),
        ("rsi_extremo", "rsi_daily", "threshold",
         {"thresholds": [[80, -100], [20, 0], [None, 100]]}),
        ("dist_sma", "dist_sma50", "range", {"min": -30, "max": 30}),
        ("rs_52w", "relative_strength_52w", "range", {"min": -50, "max": 50}),
    ]
    signals = [
        SimpleNamespace(id=i + 1, key=key, source="asset", group_type=None,
                        indicator_key=ind, formula_type=ftype,
                        params=json.dumps(params))
        for i, (key, ind, ftype, params) in enumerate(specs)
    ]
    params_by_id = {sig.id: json.loads(sig.params) for sig in signals}
    return signals, params_by_id


def _build_dataset():
    rng = random.Random(42)
    asset_ids = list(range(1, N_ASSETS + 1))
    asset_groups = {aid: {"sector": aid % 11, "market": aid % 3,
                          "industry": aid % 29, "country": aid % 7,
                          "instrument_type": aid % 4}
                    for aid in asset_ids}
    # isnaps por fecha: {aid: {code: valor}} — prearmados FUERA del profile
    # (en el modo rango los arma el barrido as-of; acá medimos evaluadores)
    per_date = []
    for _ in range(N_DATES):
        isnaps = {}
        for aid in asset_ids:
            isnaps[aid] = {
                "trend_daily": rng.choice(_TRENDS),
                "trend_weekly": rng.choice(_TRENDS),
                "rsi_daily": rng.uniform(5, 95),
                "dist_sma50": rng.uniform(-40, 40),
                "relative_strength_52w": rng.uniform(-60, 60),
            }
        per_date.append(isnaps)
    return asset_ids, asset_groups, per_date


def main():
    signals, params_by_id = _build_signals()
    compiled_by_id = {sig.id: compile_evaluator(sig.formula_type,
                                                params_by_id[sig.id],
                                                sig.params)
                      for sig in signals}
    asset_ids, asset_groups, per_date = _build_dataset()

    components = [SimpleNamespace(scope=None, signal_id=sig.id,
                                  group_type=None, group_id=None,
                                  weight=w)
                  for sig, w in zip(signals, [2, 2, 1, 1, 1.5, 1.5])]
    tree = parse_tree(json.dumps({"op": "AND", "children": [
        {"cond": {"left": {"type": "indicator", "key": "trend_daily"},
                  "operator": "in",
                  "right": {"type": "const",
                            "value": ["bullish", "bullish_strong", "lateral"]},
                  "resolution": "historic"}},
        {"cond": {"left": {"type": "signal", "key": "rsi_zona"},
                  "operator": ">",
                  "right": {"type": "const", "value": -50},
                  "resolution": "historic"}},
    ]}))

    t_eval = t_filter = t_rank = t_pct = 0.0

    def one_pass():
        nonlocal t_eval, t_filter, t_rank, t_pct
        for isnaps in per_date:
            t0 = time.perf_counter()
            sv = _evaluate_asset_signal_scores(
                signals=signals, asset_signals=signals, group_signals=[],
                params_by_id=params_by_id, compiled_by_id=compiled_by_id,
                isnaps=isnaps, asset_groups=asset_groups, gscores={})
            t1 = time.perf_counter()

            sig_id_by_key = {sig.key: sig.id for sig in signals}
            operand_values = {
                ("indicator", "trend_daily", "historic"):
                    {aid: isnaps[aid]["trend_daily"] for aid in isnaps},
                ("signal", "rsi_zona", "historic"):
                    {aid: sv.get((sig_id_by_key["rsi_zona"], aid))
                     for aid in isnaps},
            }
            t2 = time.perf_counter()

            scored = rank_strategy_assets(
                components=components, asset_groups=asset_groups,
                signal_scores=sv, group_scores={},
                filter_tree=tree, operand_values=operand_values)
            t3 = time.perf_counter()

            percent_ranks([s for _, s in scored])
            t4 = time.perf_counter()

            t_eval += t1 - t0
            t_filter += t2 - t1   # armado de operandos (parte del filtro real)
            t_rank += t3 - t2     # filtro bulk + score ponderado + sort
            t_pct += t4 - t3

    prof = cProfile.Profile()
    wall0 = time.perf_counter()
    prof.enable()
    one_pass()
    prof.disable()
    wall = time.perf_counter() - wall0

    print(f"\n=== {N_ASSETS} activos x {N_DATES} fechas "
          f"({len(signals)} señales, 1 estrategia con filtro AND) ===")
    print(f"total: {wall:.2f}s  ({wall / N_DATES * 1000:.2f} ms/fecha; "
          f"extrapolado a 2500 fechas: {wall / N_DATES * 2500:.1f}s)")
    print(f"  señales (evaluadores): {t_eval:.2f}s "
          f"({t_eval / N_DATES * 1000:.2f} ms/fecha)")
    print(f"  operandos del filtro:  {t_filter:.2f}s")
    print(f"  filtro+rank+sort:      {t_rank:.2f}s")
    print(f"  percent_ranks:         {t_pct:.2f}s")

    out = io.StringIO()
    stats = pstats.Stats(prof, stream=out)
    stats.strip_dirs().sort_stats("cumulative").print_stats(22)
    print(out.getvalue())


if __name__ == "__main__":
    main()
