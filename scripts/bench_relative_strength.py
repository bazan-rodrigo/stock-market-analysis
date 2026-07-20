"""
Valida la vectorizacion de las conversiones de fecha de
_bf_relative_strength_52w, sobre datos REALES y en una sola corrida.

Que cambio: la funcion convertia fechas a ordinales con list-comprehensions y
un loop por barra:

    bm_ords = np.array([d.toordinal() for d in bm_df["date"]])
    a_ords  = np.array([d.toordinal() for d in df["date"]])
    for i, d in enumerate(df["date"]):
        ref_ords[i] = _one_year_before(d).toordinal()

En el profile eso eran ~180k toordinal + 60k _one_year_before por activo.
Ahora se resuelve con _dates_to_ordinals / _one_year_before_ordinals.

Mide DOS cosas, a proposito:
  1. Las conversiones solas (lo que cambio): old vs new.
  2. La FUNCION COMPLETA, para saber que fraccion representan.

El punto 2 evita el error que se cometio con verify_asset_code, donde se
midio solo la parte cambiada y la fraccion se estimo desde la tabla de
cProfile — que la exageraba. Aca la fraccion se mide.

Verifica IGUALDAD EXACTA de los arrays de ordinales antes de cronometrar; si
difieren, aborta (la regla del 29/2 es contrato, ver test_technical_helpers).

SOLO LECTURA: SELECTs sobre assets y prices.

Uso (Codespace o Railway, con la BD levantada):
    python scripts/bench_relative_strength.py           # activo con benchmark y mas historia
    python scripts/bench_relative_strength.py TICKER
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import sqlalchemy as sa

from app.database import get_session
from app.models import Asset, Price
from app.services.technical_service import (
    _bf_relative_strength_52w, _dates_to_ordinals, _one_year_before,
    _one_year_before_ordinals,
)


def _conv_old(a_dates, bm_dates):
    """Copia LITERAL de las conversiones previas a la vectorizacion."""
    bm_ords = np.array([d.toordinal() for d in bm_dates])
    a_ords = np.array([d.toordinal() for d in a_dates])
    ref_ords = np.empty(len(a_dates), dtype=np.int64)
    for i, d in enumerate(a_dates):
        ref_ords[i] = _one_year_before(d).toordinal()
    return bm_ords, a_ords, ref_ords


def _conv_new(a_dates, bm_dates):
    return (_dates_to_ordinals(bm_dates), _dates_to_ordinals(a_dates),
            _one_year_before_ordinals(a_dates))


def _pick(session, ticker):
    """Activo CON benchmark asignado y la mayor historia (si no tiene
    benchmark, _bf_relative_strength_52w corta y no mide nada)."""
    if ticker:
        row = session.execute(
            sa.select(Asset.id, Asset.ticker, Asset.benchmark_id)
            .where(Asset.ticker == ticker)).first()
        if row is None:
            raise SystemExit(f"No existe {ticker!r}")
        if not row.benchmark_id:
            raise SystemExit(f"{ticker} no tiene benchmark asignado.")
        return row.id, row.ticker, row.benchmark_id
    row = session.execute(
        sa.select(Price.asset_id, sa.func.count().label("n"),
                  Asset.ticker, Asset.benchmark_id)
        .join(Asset, Asset.id == Price.asset_id)
        .where(Asset.benchmark_id.isnot(None))
        .group_by(Price.asset_id, Asset.ticker, Asset.benchmark_id)
        .order_by(sa.desc("n")).limit(1)).first()
    if row is None:
        raise SystemExit("Ningun activo con benchmark asignado y precios.")
    return row.asset_id, row.ticker, row.benchmark_id


def _prices(session, asset_id):
    rows = session.execute(
        sa.select(Price.date, Price.close, Price.high, Price.low)
        .where(Price.asset_id == asset_id).order_by(Price.date.asc())).all()
    return pd.DataFrame(rows, columns=["date", "close", "high", "low"])


def _time(fn, reps):
    t0 = time.perf_counter()
    for _ in range(reps):
        fn()
    return (time.perf_counter() - t0) / reps * 1000


def main():
    ticker = next((a for a in sys.argv[1:] if not a.startswith("-")), None)
    s = get_session()
    asset_id, tk, bm_id = _pick(s, ticker)

    df = _prices(s, asset_id)
    bm_df = _prices(s, bm_id)
    if df.empty or bm_df.empty:
        raise SystemExit("Sin precios suficientes.")
    print(f"Activo: {tk} (id={asset_id}) — {len(df)} barras | "
          f"benchmark id={bm_id} — {len(bm_df)} barras\n")

    a_dates = list(df["date"])
    bm_dates = list(bm_df["date"])

    # ── igualdad exacta antes de medir ──
    old, new = _conv_old(a_dates, bm_dates), _conv_new(a_dates, bm_dates)
    for nombre, o, n in zip(("bm_ords", "a_ords", "ref_ords"), old, new):
        if not np.array_equal(o, n):
            mal = np.flatnonzero(o != n)[:3]
            print(f"  {nombre}: DIFIERE en {len(np.flatnonzero(o != n))} posiciones")
            for i in mal:
                print(f"    idx {i}: old {o[i]} vs new {n[i]}")
            raise SystemExit("SEMANTICA ALTERADA (ojo la regla del 29/2) — revertir")
    print("  OK: los 3 arrays de ordinales son identicos\n")

    reps = 20
    ms_old = _time(lambda: _conv_old(a_dates, bm_dates), reps)
    ms_new = _time(lambda: _conv_new(a_dates, bm_dates), reps)

    # funcion completa (con la version nueva ya adentro)
    ms_fn = _time(lambda: _bf_relative_strength_52w(
        df, None, None, session=s, asset_id=asset_id, price_cache=None), 5)

    resto = ms_fn - ms_new
    fn_old = resto + ms_old
    print("=" * 66)
    print(f"  conversiones de fecha  old {ms_old:7.2f} / new {ms_new:7.2f} ms"
          f"   ({(ms_old / ms_new if ms_new else 0):.2f}x)")
    print(f"  funcion completa (new)     {ms_fn:7.2f} ms")
    print(f"  resto de la funcion        {resto:7.2f} ms  (no cambio)")
    print(f"  funcion completa (old)  ~= {fn_old:7.2f} ms")
    print(f"  MEJORA END-TO-END          {(fn_old / ms_fn if ms_fn else 0):.2f}x"
          f"   — las conversiones eran {100 * ms_old / fn_old:.0f}% de la funcion")
    print("=" * 66)
    print("\nOJO: la funcion completa incluye una query del benchmark; con")
    print("price_cache (como corre en el pool real) esa parte no esta.")
    print("\nCriterio: si la mejora end-to-end es marginal, revertir — el valor")
    print("de la optimizacion se juzga a nivel funcion, no a nivel de la parte")
    print("que se toco.")


if __name__ == "__main__":
    main()
