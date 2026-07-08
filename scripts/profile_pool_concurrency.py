"""
Compara el costo SECUENCIAL (un solo hilo) vs CONCURRENTE (un thread por
código, igual que el pool real) de correr varios indicadores sobre todos
los activos reales — sin tocar la base (puro cómputo), para aislar si la
brecha entre cómputo puro y tiempo de pared real (ver
profile_pool_contention.py: ~2s de cómputo vs 53-63s de pared) es
contención de GIL entre threads o está en otro lado.

profile_pool_contention.py ya midió el costo secuencial de estos códigos
por separado, pero eso no prueba si paralelizan bien — nunca los corrió
REALMENTE al mismo tiempo en threads. Este script sí: mide el mismo total
corrido en 1 hilo vs en N hilos simultáneos (N = cantidad de códigos, como
la primera tanda real del pool).

Si el tiempo concurrente es ~igual al secuencial (speedup ~1x), confirma
contención de GIL: el cómputo es CPU-bound en Python puro/pandas y agregar
threads no ayuda porque compiten por el mismo intérprete. Si escala cerca
de linealmente con los threads, el cómputo SÍ paraleliza razonablemente y
el cuello de botella real está en otro lado (I/O a la base, commits,
overhead de scheduling).

Uso (en el Codespace, con la BD levantada):
    python scripts/profile_pool_concurrency.py
"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import Session as _DbSession
from app.database import get_session
from app.services.technical_service import (
    _BACKFILL_FNS, _MIN_ROWS, _get_regime_config, _get_volatility_config,
    _load_all_prices, _load_best_sma_cache, _resample_ohlc,
)

# La primera tanda real de 6 workers en el último rebuild (ver last_rebuild_seconds)
_CODES = ["volatility_daily", "trend_daily", "atr_percentile_daily", "rsi_daily",
          "relative_strength_52w", "return_yearly"]


def _run_code(code, price_cache, df_w_cache, df_m_cache, best_sma_cache,
              regime_cfg, vol_cfg, session) -> int:
    compute_fn = _BACKFILL_FNS[code]
    n = 0
    for asset_id, df in price_cache.items():
        if len(df) < _MIN_ROWS:
            continue
        compute_fn(
            df=df, df_w=df_w_cache[asset_id], df_m=df_m_cache[asset_id],
            regime_cfg=regime_cfg, vol_cfg=vol_cfg,
            session=session, asset_id=asset_id,
            price_cache=price_cache, best_sma_cache=best_sma_cache,
        )
        n += 1
    return n


def main():
    for code in _CODES:
        if code not in _BACKFILL_FNS:
            raise SystemExit(f"Código desconocido: {code!r}")

    s = get_session()
    print("Cargando precios en memoria...")
    price_cache = _load_all_prices(s)
    print(f"{len(price_cache)} activos cargados")
    print("Precalculando resamples...")
    df_w_cache = {aid: _resample_ohlc(df, "W") for aid, df in price_cache.items()}
    df_m_cache = {aid: _resample_ohlc(df, "M") for aid, df in price_cache.items()}
    best_sma_cache = _load_best_sma_cache(s)
    regime_cfg = _get_regime_config()
    vol_cfg = _get_volatility_config()

    common = dict(price_cache=price_cache, df_w_cache=df_w_cache, df_m_cache=df_m_cache,
                  best_sma_cache=best_sma_cache, regime_cfg=regime_cfg, vol_cfg=vol_cfg)

    # --- Secuencial: un solo hilo, un código a la vez ---
    t0 = time.perf_counter()
    for code in _CODES:
        _run_code(code, session=s, **common)
    seq_elapsed = time.perf_counter() - t0
    print(f"\nSECUENCIAL (1 hilo, {len(_CODES)} códigos): {seq_elapsed:.2f}s")

    # --- Concurrente: un thread por código, cada uno con su propia sesión
    # (mismo patrón que _backfill_indicator_worker) ---
    def _worker(code):
        sess = get_session()
        try:
            return _run_code(code, session=sess, **common)
        finally:
            _DbSession.remove()

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=len(_CODES)) as pool:
        list(pool.map(_worker, _CODES))
    conc_elapsed = time.perf_counter() - t0
    print(f"CONCURRENTE ({len(_CODES)} threads): {conc_elapsed:.2f}s")

    speedup = seq_elapsed / conc_elapsed if conc_elapsed else float("inf")
    print(f"\nSpeedup real: {speedup:.1f}x  (ideal con {len(_CODES)} threads: {len(_CODES)}.0x)")
    if speedup < 2:
        print("→ Contención de GIL: los threads casi no paralelizan el cómputo puro.")
    else:
        print("→ El cómputo sí paraleliza razonablemente — el cuello de botella real "
              "de la corrida completa está en otro lado (I/O a la base, commits).")


if __name__ == "__main__":
    main()
