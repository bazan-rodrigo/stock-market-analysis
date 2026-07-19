"""
Perfila el backtest de cartera (nivel C): `run_portfolio_backtest` completo y,
por separado, sus núcleos PUROS para localizar dónde se va el tiempo —
construcción de paneles (`build_panels`) vs simulación por-fecha
(`simulate_topn` / `simulate_gated`) vs la máquina de estados por-activo
(`simulate_trades`).

Corre 100% LOCAL sin base de datos. `run_portfolio_backtest` toca BD en tres
puntos (get_session, signal_store.ensure_strat_table, _load_raw); se
monkeypatchean los tres para inyectar un universo SINTÉTICO de random-walk
(mismo generador que profile_walk_forward.py). Los núcleos son puros y se
perfilan directo sobre los paneles pre-armados.

Uso:
    python scripts/profile_portfolio_backtest.py
    python scripts/profile_portfolio_backtest.py 200 750   # n_assets n_dates
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

# Sin BD: stub sqlite en DATABASE_URL antes de importar app (tests/conftest.py).
os.environ.setdefault("DATABASE_URL", f"sqlite:///{ROOT / '.profile-stub.db'}")

import numpy as np
import sqlalchemy as sa

import app.database as db
from app.models import signal_store
from app.services import portfolio_backtest_service as pbs
from app.services import portfolio_sim_engine as eng
from app.services.portfolio_backtest_service import _in_position, build_panels
from app.services.trade_simulator import simulate_trades

# Mismo contrato de spec que en producción (entrada por score + trailing_stop).
_SPEC = {
    "entries": [{"type": "score", "th": 5.0}],
    "score_exits": [],
    "caps": [{"type": "trailing_stop", "pct": 15.0}],
    "rearm": True,
    "cooldown": 0,
}


def _synthetic_universe(n_assets, n_dates, seed=0):
    """{aid: {dates, closes, scores, pcts}} — misma forma que `_load_raw`.
    Closes random-walk positivos; scores ruidosos en torno al umbral de entrada
    (5) para churn de entradas y del ranking transversal. pcts=None (spec 'score')."""
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


def _panels_from_universe(universe):
    """Arma el input de build_panels ({aid: {dates,closes,scores,in_position}})
    corriendo simulate_trades por activo, y devuelve tanto ese input como los
    paneles ensamblados (para perfilar cada núcleo por separado)."""
    per_asset = {}
    for aid, raw in universe.items():
        trades = simulate_trades(raw["closes"], raw["scores"], _SPEC,
                                 percentiles=raw["pcts"])
        per_asset[aid] = {
            "dates": raw["dates"], "closes": raw["closes"],
            "scores": raw["scores"],
            "in_position": _in_position(trades, len(raw["closes"]))}
    panels = build_panels(per_asset)   # (dates, scores_bd, rets_bd, elig_bd)
    return per_asset, panels


# ── Monkeypatch de los tres seams de BD de run_portfolio_backtest ─────────────
#
# Una Table real y liviana para que `sa.select(rt.c.asset_id).where(...)` se
# construya (aunque la ejecución esté fakeada); una sesión que devuelve los
# asset_ids del universo; y _load_raw → el universo sintético.

_FAKE_META = sa.MetaData()
_FAKE_RT = sa.Table(
    "fake_strat", _FAKE_META,
    sa.Column("asset_id", sa.Integer),
    sa.Column("date", sa.Date),
    sa.Column("score", sa.Float),
    sa.Column("pct", sa.Float),
)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, asset_ids):
        self._aids = asset_ids

    def connection(self):
        return None

    def execute(self, _stmt):
        # run_portfolio_backtest sólo ejecuta la query de asset_ids distintos.
        return _FakeResult([(a,) for a in self._aids])


def _install_bd_fakes(universe):
    asset_ids = sorted(universe)
    db.get_session = lambda: _FakeSession(asset_ids)
    signal_store.ensure_strat_table = lambda strategy_id, bind=None: _FAKE_RT
    pbs._load_raw = lambda s, rt, asset_ids, progress_cb=None: universe


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
    n_assets = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    n_dates = int(sys.argv[2]) if len(sys.argv) > 2 else 750
    top_n = 20

    _dates, universe = _synthetic_universe(n_assets, n_dates)
    per_asset, panels = _panels_from_universe(universe)
    dates, scores_bd, rets_bd, elig_bd = panels
    print(f"Universo sintético: {n_assets} activos × {n_dates} fechas | "
          f"calendario común={len(dates)} fechas, top_n={top_n}")

    # 1) simulate_trades por-activo sobre todo el universo (máquina de estados,
    #    insumo de la elegibilidad).
    def all_trades():
        for raw in universe.values():
            simulate_trades(raw["closes"], raw["scores"], _SPEC,
                            percentiles=raw["pcts"])

    _profile("simulate_trades × universo (elegibilidad por-activo)",
             all_trades, n_reps=10)

    # 2) build_panels (ensamblado del cross-section).
    _profile("build_panels (ensamblado del cross-section)",
             lambda: build_panels(per_asset), n_reps=10)

    # 3) simulate_topn (ranking puro, por-fecha).
    _profile("simulate_topn (ranking por-fecha)",
             lambda: eng.simulate_topn(dates, scores_bd, rets_bd, top_n=top_n),
             n_reps=20)

    # 4) simulate_gated (top-N ∩ elegibles, por-fecha).
    _profile("simulate_gated (gated por-fecha)",
             lambda: eng.simulate_gated(dates, scores_bd, elig_bd, rets_bd,
                                        top_n=top_n),
             n_reps=20)

    # 5) run_portfolio_backtest completo (BD monkeypatcheada) — la orquestación
    #    de punta a punta: simulate_trades × universo + build_panels + los tres
    #    sub-modos (ranking/gated/benchmark) + KPIs.
    _install_bd_fakes(universe)
    out = pbs.run_portfolio_backtest(1, _SPEC, top_n=top_n)
    print(f"\nrun_portfolio_backtest OK: {len(out['dates'])} fechas | "
          f"gated total_return={out['gated']['total_return']:.4f} | "
          f"ranking total_return={out['ranking']['total_return']:.4f}")
    _profile("run_portfolio_backtest (orquestación completa, BD fakeada)",
             lambda: pbs.run_portfolio_backtest(1, _SPEC, top_n=top_n),
             n_reps=5)


if __name__ == "__main__":
    main()
