"""
Perfila _compute_by_type (el calculo vectorizado de sinteticos, commit
e45f510) contra un formula real, aislado de la escritura a BD: carga los
price_frames una sola vez (unico costo de I/O real) y repite el computo puro
bajo cProfile. Sirve para confirmar que la vectorizacion realmente bajo el
costo (no solo que da el mismo resultado, que ya cubren los tests) y para ver
que queda como cuello de botella real.

Uso (en el Codespace, con la BD levantada):
    python scripts/profile_synthetic_service.py           # primera formula encontrada
    python scripts/profile_synthetic_service.py TICKER    # sintetico puntual
"""
import cProfile
import io
import pstats
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sqlalchemy as sa

from app.database import get_session
from app.models import Asset, SyntheticFormula
from app.services.synthetic_service import _load_price_frame, _compute_by_type, _anchor_price


def _pick_formula(session, ticker: str | None) -> SyntheticFormula:
    if ticker:
        row = session.execute(
            sa.select(Asset.id).where(Asset.ticker == ticker)
        ).first()
        if row is None:
            raise SystemExit(f"No existe el activo {ticker!r}")
        f = session.query(SyntheticFormula).filter_by(asset_id=row.id).first()
        if f is None:
            raise SystemExit(f"{ticker!r} no tiene formula sintetica")
        return f

    formulas = session.query(SyntheticFormula).all()
    if not formulas:
        raise SystemExit("No hay formulas sinteticas cargadas en la BD.")
    # La de mas componentes: el caso mas representativo del costo de _weighted_sums
    return max(formulas, key=lambda f: len(f.components))


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
    stats.print_stats(20)
    print(buf.getvalue())


def main():
    ticker = sys.argv[1] if len(sys.argv) > 1 else None
    session = get_session()
    formula = _pick_formula(session, ticker)
    ticker_str = formula.asset.ticker if formula.asset else str(formula.asset_id)
    comps = formula.components
    print(f"Sintetico: {ticker_str} (id={formula.asset_id}) — tipo={formula.formula_type}, "
          f"{len(comps)} componente(s)")

    all_asset_ids = list({c.asset_id for c in comps})
    t0 = time.perf_counter()
    price_frames = {aid: _load_price_frame(aid) for aid in all_asset_ids}
    load_s = time.perf_counter() - t0
    n_bars = max((len(f) for f in price_frames.values()), default=0)
    print(f"Carga de {len(all_asset_ids)} componente(s): {load_s:.3f}s "
          f"(~{n_bars} barras el mas largo)")

    base_prices = None
    if formula.formula_type == "index":
        base_prices = {aid: bp for aid in all_asset_ids
                       if (bp := _anchor_price(aid, formula.base_date, session)) is not None}

    _profile(
        f"_compute_by_type ({formula.formula_type})",
        lambda: _compute_by_type(formula, comps, price_frames, base_prices=base_prices),
        n_reps=20,
    )


if __name__ == "__main__":
    main()
