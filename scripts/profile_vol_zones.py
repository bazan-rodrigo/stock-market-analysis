"""
Perfila el costo real de _compute_vol_zones vs _bf_rsi_daily / _bf_trend
para activos reales, aislado de la concurrencia de workers del delta.

Corre siempre de a un solo activo/hilo (sin ThreadPoolExecutor), para que
cProfile mida cómputo puro sin contención de GIL entre workers paralelos.

Uso (en el Codespace, con la BD levantada):
    python scripts/profile_vol_zones.py            # activo con mas historia
    python scripts/profile_vol_zones.py TICKER      # activo puntual
"""
import cProfile
import io
import pstats
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import sqlalchemy as sa

from app.database import get_session
from app.models import Asset, Price
from app.services.technical_service import (
    _bf_rsi_daily, _bf_trend, _bf_volatility, _get_regime_config,
    _get_volatility_config, _resample_ohlc,
)


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
        # ticker va en el GROUP BY: PostgreSQL rechaza seleccionar una
        # columna no agregada ni agrupada (MySQL lo tolera). Es dependiente
        # funcional de asset_id, así que el resultado no cambia.
        .group_by(Price.asset_id, Asset.ticker)
        .order_by(sa.desc("n"))
        .limit(1)
    ).first()
    return row.asset_id, row.ticker


def _load_df(session, asset_id: int) -> pd.DataFrame:
    rows = session.execute(
        sa.select(Price.date, Price.close, Price.high, Price.low)
        .where(Price.asset_id == asset_id)
        .order_by(Price.date.asc())
    ).all()
    return pd.DataFrame(rows, columns=["date", "close", "high", "low"])


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
    ticker = sys.argv[1] if len(sys.argv) > 1 else None
    session = get_session()
    asset_id, asset_ticker = _pick_asset(session, ticker)

    df = _load_df(session, asset_id)
    print(f"Activo: {asset_ticker} (id={asset_id}) — {len(df)} barras diarias")
    if len(df) < 300:
        print("Muy poca historia para un perfil representativo, elegí otro ticker.")
        return

    df_w = _resample_ohlc(df, "W")
    df_m = _resample_ohlc(df, "M")
    regime_cfg = _get_regime_config()
    vol_cfg = _get_volatility_config()

    n_reps = 20  # repetido para que cProfile tenga señal por encima de su propio overhead

    _profile(
        "rsi_daily (referencia rápida)",
        lambda: _bf_rsi_daily(df=df, df_w=df_w, df_m=df_m),
        n_reps,
    )
    _profile(
        "trend_daily (zonas de régimen, referencia)",
        lambda: _bf_trend("d")(df=df, df_w=df_w, df_m=df_m, regime_cfg=regime_cfg),
        n_reps,
    )
    _profile(
        "volatility_daily (_compute_vol_zones)",
        lambda: _bf_volatility("d")(df=df, df_w=df_w, df_m=df_m, vol_cfg=vol_cfg),
        n_reps,
    )


if __name__ == "__main__":
    main()
