"""
Perfila compute_current_indicators(quick=True) — el camino que corre UNA VEZ
POR ACTIVO en cada actualizacion diaria (update_all_active_assets). A 10000
activos es la operacion mas multiplicada de todo el pipeline, aunque cada
llamada sea barata: cualquier overhead fijo por-activo se nota x10000.

Nota: la funcion hace su propio s.commit() al final (upsert de los valores
de "hoy"), asi que cada rep sobreescribe la misma fila — idempotente, no
acumula basura, pero SI pega contra la BD real en cada rep (a diferencia de
profile_vol_zones.py que es puro computo). Por eso los reps son pocos.

Uso (en el Codespace, con la BD levantada):
    python scripts/profile_current_indicators.py            # activo con mas historia
    python scripts/profile_current_indicators.py TICKER      # activo puntual
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
from app.models import Asset, Price
from app.services.technical_service import compute_current_indicators


def _pick_asset(session, ticker: str | None):
    if ticker:
        row = session.execute(
            sa.select(Asset.id, Asset.ticker).where(Asset.ticker == ticker)
        ).first()
        if row is None:
            raise SystemExit(f"No existe el activo {ticker!r}")
        return row.id, row.ticker

    row = session.execute(
        sa.select(Price.asset_id, sa.func.count().label("n"), Asset.ticker)
        .join(Asset, Asset.id == Price.asset_id)
        .group_by(Price.asset_id)
        .order_by(sa.desc("n"))
        .limit(1)
    ).first()
    return row.asset_id, row.ticker


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
    asset_id, asset_ticker = _pick_asset(session, ticker)
    print(f"Activo: {asset_ticker} (id={asset_id})")

    _profile(
        "compute_current_indicators(quick=True)  — corre 1x/activo/dia",
        lambda: compute_current_indicators(asset_id, quick=True),
        n_reps=10,
    )
    _profile(
        "compute_current_indicators(quick=False) — referencia, camino pesado",
        lambda: compute_current_indicators(asset_id, quick=False),
        n_reps=3,
    )


if __name__ == "__main__":
    main()
