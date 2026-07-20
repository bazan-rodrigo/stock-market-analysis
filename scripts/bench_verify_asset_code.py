"""
Valida la vectorizacion de verify_asset_code sobre datos REALES, comparando
la version previa y la actual en el mismo proceso.

Que cambio: la comparacion fresco-vs-guardado llamaba _values_equal y
check_sanity UNA VEZ POR FECHA (mas un pd.notna por valor al armar `fresh`).
En una serie de 16k barras eso son ~48k llamadas escalares por codigo, en su
mayoria para descubrir que no hay ninguna diferencia — el caso normal. Ahora
esas comparaciones se resuelven con operaciones de array (_diff_masks) y, si
no hay diferencias ni fechas faltantes, se evita recorrer la serie entera.

Que mide: SOLO la parte posterior al calculo del indicador. El compute_fn es
identico en ambas versiones y es caro, asi que incluirlo diluiria la
comparacion — por eso la serie se computa UNA vez por codigo y despues se
cronometran las dos implementaciones sobre esos mismos datos.

Antes de medir verifica IGUALDAD EXACTA de las listas de diffs entre ambas
versiones para cada codigo. verify_asset_code es codigo de verificacion de
datos: si la semantica se movio aunque sea un milimetro, aborta.

SOLO LECTURA: SELECTs sobre prices y las tablas ind_*.

Uso (Codespace o Railway, con la BD levantada):
    python scripts/bench_verify_asset_code.py           # activo con mas historia
    python scripts/bench_verify_asset_code.py TICKER    # activo puntual
"""
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
    _BACKFILL_FNS, _get_regime_config, _get_volatility_config,
    _resample_ohlc, _series_dates_values,
)
from app.services.verification_service import (
    _diff_category, _diffs_for_series, _prefetch_stored, _values_equal,
    check_sanity,
)


def _diffs_old(code: str, dates_list: list, vals_list: list,
               stored: dict) -> list:
    """Copia LITERAL de la version previa: un pd.notna por valor y una
    llamada a _values_equal + check_sanity por fecha."""
    fresh = {d: v for d, v in zip(dates_list, vals_list) if pd.notna(v)}
    diffs = []
    for d in sorted(set(fresh) | set(stored)):
        fv, sv = fresh.get(d), stored.get(d)
        if fv is None and sv is not None:
            kind = "solo en DB (¿debería haberse borrado?)"
            diffs.append((d, kind, sv, fv, _diff_category(kind)))
        elif fv is not None and sv is None:
            kind = "falta en DB (¿el delta no la escribió?)"
            diffs.append((d, kind, sv, fv, _diff_category(kind)))
        elif not _values_equal(fv, sv):
            kind = "valor distinto"
            diffs.append((d, kind, sv, fv, _diff_category(kind)))
        if fv is not None:
            sanity = check_sanity(code, fv)
            if sanity:
                diffs.append((d, sanity, sv, fv, _diff_category(sanity)))
    return diffs


def _pick_asset(session, ticker):
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
        .group_by(Price.asset_id, Asset.ticker)   # ticker agrupado: portable PG
        .order_by(sa.desc("n"))
        .limit(1)
    ).first()
    return row.asset_id, row.ticker


def main():
    ticker = sys.argv[1] if len(sys.argv) > 1 else None
    s = get_session()
    asset_id, tk = _pick_asset(s, ticker)

    rows = s.execute(
        sa.select(Price.date, Price.close, Price.high, Price.low)
        .where(Price.asset_id == asset_id).order_by(Price.date.asc())
    ).all()
    df = pd.DataFrame(rows, columns=["date", "close", "high", "low"])
    if len(df) < 300:
        raise SystemExit("Muy poca historia; elegí otro ticker.")
    print(f"Activo: {tk} (id={asset_id}) — {len(df)} barras\n")

    df_w, df_m = _resample_ohlc(df, "W"), _resample_ohlc(df, "M")
    regime_cfg, vol_cfg = _get_regime_config(), _get_volatility_config()
    codes = sorted(_BACKFILL_FNS)

    # Computar cada serie UNA vez (el compute_fn no es lo que se compara).
    print("Computando series frescas (una vez por codigo)...")
    stored_by_code = {}
    for code in codes:
        try:
            stored_by_code.update(_prefetch_stored(s, [code], [asset_id]))
        except Exception as exc:
            print(f"  (salteo {code}: {type(exc).__name__})")
    cases = []
    for code in codes:
        if code not in stored_by_code:
            continue
        try:
            values = _BACKFILL_FNS[code](
                df=df, df_w=df_w, df_m=df_m,
                regime_cfg=regime_cfg, vol_cfg=vol_cfg,
                session=s, asset_id=asset_id,
                price_cache=None, best_sma_cache=None)
            dates_list, vals_list = _series_dates_values(values, df)
        except Exception as exc:
            print(f"  (salteo {code}: {type(exc).__name__} al computar)")
            continue
        stored = stored_by_code.get(code, {}).get(asset_id, {})
        cases.append((code, dates_list, vals_list, stored))
    if not cases:
        raise SystemExit("No se pudo armar ningun caso.")
    print(f"{len(cases)} codigos listos\n")

    # ── Igualdad EXACTA de salidas, codigo por codigo ──
    print("Verificando igualdad de salidas old vs new...")
    for code, dl, vl, st in cases:
        a, b = _diffs_old(code, dl, vl, st), _diffs_for_series(code, dl, vl, st)
        if a != b:
            print(f"  {code}: DIFERENCIA — old {len(a)} diffs, new {len(b)}")
            for x, y in zip(a, b):
                if x != y:
                    print(f"    old: {x}\n    new: {y}")
                    break
            raise SystemExit("SEMANTICA ALTERADA — no seguir, revertir el cambio")
    print(f"  OK: las {len(cases)} listas de diffs son identicas\n")

    reps = 10
    def _run(fn):
        t0 = time.perf_counter()
        for _ in range(reps):
            for code, dl, vl, st in cases:
                fn(code, dl, vl, st)
        return (time.perf_counter() - t0) / reps * 1000

    ms_old = _run(_diffs_old)
    ms_new = _run(_diffs_for_series)
    print("=" * 66)
    print(f"  old (escalar por fecha) : {ms_old:8.2f} ms  ({len(cases)} codigos, 1 activo)")
    print(f"  new (vectorizado)       : {ms_new:8.2f} ms")
    print(f"  speedup                 : {(ms_old / ms_new if ms_new else 0):8.2f}x")
    print("=" * 66)
    print(f"\nPor activo (los {len(cases)} codigos): {ms_old:.0f} ms -> {ms_new:.0f} ms")
    print(f"Extrapolado a 10.000 activos, un solo hilo: "
          f"{ms_old * 10000 / 1000 / 60:.0f} min -> {ms_new * 10000 / 1000 / 60:.0f} min")
    print("\nOJO: esto mide SOLO la comparacion, no el calculo del indicador")
    print("(identico en ambas versiones). El profile mostraba esa comparacion")
    print("como ~85% del costo de verify_asset_code.")


if __name__ == "__main__":
    main()
