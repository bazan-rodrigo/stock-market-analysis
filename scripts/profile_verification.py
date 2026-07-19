"""
Perfila el cómputo de verificación POR ACTIVO de verification_service —
verify_asset_code (indicadores técnicos) y verify_asset_ratio_code
(ratios fundamentales) — que update_flags_for_assets corre × N activos
dentro de _run_batched (un lote por worker).

Sigue el patrón de datos REALES de profile_vol_zones.py: get_session,
elegir el activo con MÁS historia y perfilar su verificación aislada, un
solo activo / un solo hilo, para que cProfile mida cómputo puro sin
contención de GIL entre los workers del pool.

verify_asset_code / verify_asset_ratio_code están ACOPLADAS A BD (leen
precios, trimestres y los valores guardados en ind_{code} para comparar),
así que la parte principal de este script SOLO corre en el Codespace con
la BD levantada.

El perfil de cómputo PURO (check_sanity + _values_equal: comparación de
bounds/tolerancias, sin tocar la base) sí corre local — usar `--pure`:

Uso:
    python scripts/profile_verification.py            # activo con mas historia (Codespace)
    python scripts/profile_verification.py TICKER      # activo puntual (Codespace)
    python scripts/profile_verification.py --pure       # solo cómputo puro (corre LOCAL, sin BD)
"""
import cProfile
import io
import os
import pstats
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Solo en modo --pure (cómputo puro, sin BD): apuntar DATABASE_URL a un stub
# sqlite ANTES de importar app, para que el import no exija el driver de MySQL
# en la PC de desarrollo (mismo criterio que tests/conftest.py). Se usa archivo
# y no ":memory:" porque app/database.py pasa pool_size/max_overflow, que el
# pool de sqlite en memoria rechaza.
# NO se aplica en el modo principal: ese necesita la BD REAL del Codespace, y
# forzar la URL acá la pisaría cuando viene de conf.properties (no de env).
if "--pure" in sys.argv:
    _STUB = Path(tempfile.gettempdir()) / "profile_verification_stub.db"
    os.environ.setdefault("DATABASE_URL", f"sqlite:///{_STUB}")
    os.environ.setdefault("USE_WIDE_IND_TABLES", "0")

import numpy as np
import sqlalchemy as sa

from app.database import get_session
from app.models import Asset, FundamentalQuarterly, Price
from app.services.fundamental_service import _ALL_FUND_CODES
from app.services.technical_service import (
    _BACKFILL_FNS, _DELTA_TAIL_MODE, _get_regime_config,
    _get_volatility_config, _resample_ohlc,
)
from app.services.verification_service import (
    _CATEGORICAL_VALUES, _NUMERIC_BOUNDS, _compute_daily_series_by_code,
    _compute_quarterly_by_idx, _current_ratio_fresh, _load_fund_price_rows,
    _load_price_df, _load_quarters, _prefetch_stored, _values_equal,
    check_sanity, verify_asset_code, verify_asset_ratio_code,
)


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


# ── Cómputo PURO (corre local, sin BD) ───────────────────────────────────────

def _profile_pure() -> None:
    """check_sanity / _values_equal son puras (bounds + tolerancias, sin
    tocar la base): se perfilan local para ver cuánto pesa la comparación
    fila-por-fila que verify_asset_code corre sobre cada (fecha, valor)."""
    # Muestra de (código, valor): numéricos dentro/fuera de rango + None,
    # más categóricos conocidos/desconocidos — cubre todas las ramas de
    # check_sanity.
    sanity_inputs: list = []
    for code, (lo, hi) in _NUMERIC_BOUNDS.items():
        sanity_inputs += [(code, (lo + hi) / 2.0), (code, hi * 10.0),
                          (code, lo - 1.0), (code, None)]
    for code, values in _CATEGORICAL_VALUES.items():
        for v in list(values)[:3]:
            sanity_inputs.append((code, v))
        sanity_inputs.append((code, "??categoria_inexistente??"))

    # Pares (fresco, guardado) para _values_equal: iguales por tolerancia
    # absoluta, iguales por tolerancia relativa, distintos, y no-numéricos.
    eq_pairs = [
        (1.234560, 1.234570), (100.0, 100.02), (1.0e6, 1.0001e6),
        (0.0, 0.0), (5.0, 7.0), ("categoria_a", "categoria_a"),
        ("categoria_a", "categoria_b"), (None, 5.0), (5.0, None),
    ]

    def _run_sanity():
        for code, value in sanity_inputs:
            check_sanity(code, value)

    def _run_equal():
        for fresh, stored in eq_pairs:
            _values_equal(fresh, stored)

    _profile(f"check_sanity ({len(sanity_inputs)} valores/rep)", _run_sanity, 2000)
    _profile(f"_values_equal ({len(eq_pairs)} pares/rep)", _run_equal, 5000)


# ── Datos reales (Codespace) ─────────────────────────────────────────────────

def _pick_asset(session, ticker: str | None):
    """Activo con más historia de precios (o el ticker puntual)."""
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


def _pick_fund_asset(session):
    """Activo con más trimestres fundamentales cargados."""
    row = session.execute(
        sa.select(FundamentalQuarterly.asset_id, sa.func.count().label("n"),
                  Asset.ticker)
        .join(Asset, Asset.id == FundamentalQuarterly.asset_id)
        .group_by(FundamentalQuarterly.asset_id)
        .order_by(sa.desc("n"))
        .limit(1)
    ).first()
    if row is None:
        return None, None
    return row.asset_id, row.ticker


def _profile_indicators(session) -> None:
    asset_id, ticker = _pick_asset(session, None)
    df = _load_price_df(session, asset_id)
    print(f"\nIndicadores — activo: {ticker} (id={asset_id}) — {len(df)} barras")
    if len(df) < 300:
        print("Muy poca historia para un perfil representativo.")
        return

    df_w = _resample_ohlc(df, "W")
    df_m = _resample_ohlc(df, "M")
    regime_cfg = _get_regime_config()
    vol_cfg    = _get_volatility_config()

    # Mismos códigos que run_verification: los tail-mode con función de backfill.
    codes = [c for c in _DELTA_TAIL_MODE if c in _BACKFILL_FNS]
    stored_by_code = _prefetch_stored(session, codes, [asset_id])

    def _run_all_codes():
        # Igual que _verify_one_asset: verify_asset_code por cada código,
        # reusando df_w/df_m/stored (una sola vez por activo).
        for code in codes:
            stored = stored_by_code.get(code, {}).get(asset_id, {})
            verify_asset_code(session, code, asset_id, df, df_w, df_m,
                              regime_cfg, vol_cfg, stored)

    _profile(f"verify_asset_code ({len(codes)} códigos, 1 activo)",
             _run_all_codes, 10)


def _profile_fundamentals(session) -> None:
    asset_id, ticker = _pick_fund_asset(session)
    if asset_id is None:
        print("\nFundamentales — no hay activos con trimestres cargados, se omite.")
        return
    quarters   = _load_quarters(session, asset_id)
    price_rows = _load_fund_price_rows(session, asset_id)
    print(f"\nFundamentales — activo: {ticker} (id={asset_id}) — "
          f"{len(quarters)} trimestres, {len(price_rows)} precios")
    if not quarters:
        return

    q_ords = np.array([q.period_date.toordinal() for q in quarters])

    # Costo de armar las series por activo (una sola vez, ver
    # _verify_one_fund_asset) — es donde vive el grueso del cómputo fund.
    def _run_prep():
        _compute_quarterly_by_idx(quarters)
        _compute_daily_series_by_code(quarters, q_ords, price_rows)
        _current_ratio_fresh(quarters, price_rows)

    _profile("precompute por activo (quarterly/daily/current)", _run_prep, 20)

    quarterly_by_idx = _compute_quarterly_by_idx(quarters)
    daily_series     = _compute_daily_series_by_code(quarters, q_ords, price_rows)
    current_ratios   = _current_ratio_fresh(quarters, price_rows)
    fund_codes = sorted(_ALL_FUND_CODES)
    stored_by_code = _prefetch_stored(session, fund_codes, [asset_id])

    def _run_all_codes():
        for code in fund_codes:
            stored = stored_by_code.get(code, {}).get(asset_id, {})
            verify_asset_ratio_code(code, asset_id, quarters, quarterly_by_idx,
                                    daily_series, current_ratios, stored)

    _profile(f"verify_asset_ratio_code ({len(fund_codes)} códigos, 1 activo)",
             _run_all_codes, 20)


def main():
    args = sys.argv[1:]
    pure_only = "--pure" in args
    ticker = next((a for a in args if not a.startswith("-")), None)

    # El perfil puro corre siempre (y es lo único que corre local).
    _profile_pure()
    if pure_only:
        return

    session = get_session()
    if ticker:
        # Un ticker puntual solo tiene sentido para el perfil de indicadores.
        asset_id, tk = _pick_asset(session, ticker)
        df = _load_price_df(session, asset_id)
        print(f"\nIndicadores — activo: {tk} (id={asset_id}) — {len(df)} barras")
        df_w = _resample_ohlc(df, "W")
        df_m = _resample_ohlc(df, "M")
        regime_cfg = _get_regime_config()
        vol_cfg    = _get_volatility_config()
        codes = [c for c in _DELTA_TAIL_MODE if c in _BACKFILL_FNS]
        stored_by_code = _prefetch_stored(session, codes, [asset_id])
        _profile(
            f"verify_asset_code ({len(codes)} códigos, {tk})",
            lambda: [verify_asset_code(
                session, code, asset_id, df, df_w, df_m, regime_cfg, vol_cfg,
                stored_by_code.get(code, {}).get(asset_id, {})) for code in codes],
            10,
        )
        return

    _profile_indicators(session)
    _profile_fundamentals(session)


if __name__ == "__main__":
    main()
