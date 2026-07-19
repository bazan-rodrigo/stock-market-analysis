"""
Perfila el worker del ProcessPool por lotes de activos,
_backfill_batch_worker (technical_service.py), corriendo UN lote INLINE
—en este mismo proceso, sin spawn— bajo cProfile: mide el CÓMPUTO PURO
por lote (todos los códigos de backfill × los activos del lote), sin el
ruido de pickling / IPC / arranque de procesos hijos.

Arma la corrida igual que profile_pool_contention.py / profile_pool_
concurrency.py: get_session, _load_all_prices, resamples W/M por activo,
_load_best_sma_cache y _precompute_all_tail_stats, y llama al worker con
los mismos kwargs que le pasa el orquestador real (_process_batch_task
delega en él con estos argumentos posicionales).

ACOPLADO A BD (lee precios/best-sma y ESCRIBE en las tablas ind_{code} vía
upsert idempotente) → correr en el Codespace con la BD levantada. En
`rebuild` (default) recomputa la historia completa de cada activo del lote
—el cómputo que vale la pena perfilar— y reescribe sus filas ind_{code}
(usar una BD descartable). En `delta` mide el camino del job diario (solo
recalcula la cola), que rinde casi nada si las tablas ya están al día.

IMPORTANTE — qué NO mide cProfile acá: al correr el lote INLINE se ve el
cómputo del worker, pero el overhead de pickling de argumentos/resultados,
la IPC (Queue de progreso) y el scheduling del ProcessPoolExecutor NO
aparecen — nacen y mueren fuera de este proceso. Para dimensionar ese
overhead hay que medir tiempo de PARED de la corrida real por procesos
contra el cómputo puro de acá, y mirar information_schema.processlist
mientras corre (contención de conexiones/locks entre hijos), como en la
nota de escalado (project_processpool_particion_activos / project_scaling_target).

Uso (en el Codespace, con la BD levantada):
    python scripts/profile_pool_batch.py               # rebuild, toda la historia como un lote
    python scripts/profile_pool_batch.py delta          # delta (camino del job diario)
    python scripts/profile_pool_batch.py rebuild 100    # rebuild, lote de 100 activos (mas historia primero)
    python scripts/profile_pool_batch.py delta 100
    python scripts/profile_pool_batch.py delta --raw    # wall-clock SIN profiler (baseline real)

El flag --raw corre el mismo lote sin instrumentar: es el numero honesto
para comparar antes/despues de una optimizacion. El total que imprime el
modo con profiler esta inflado (cProfile cobra por cada llamada, y este
camino hace decenas de millones), asi que NO sirve como baseline.
"""
import cProfile
import io
import pstats
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import get_session
from app.models import IndicatorDefinition
from app.services.technical_service import (
    _BACKFILL_FNS, _backfill_batch_worker, _load_all_prices,
    _load_best_sma_cache, _precompute_all_tail_stats, _resample_ohlc,
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


def _raw(label: str, fn, n_reps: int) -> None:
    """Wall-clock SIN cProfile: el baseline real.

    cProfile instrumenta cada llamada, asi que infla mucho las funciones
    llamadas millones de veces (medido: pd.notna a ~15M llamadas aparecia
    ~12x mas caro bajo el profiler que su costo real). Para saber cuanto
    tarda de verdad el lote —y para comparar antes/despues de una
    optimizacion— hay que medir sin instrumentar."""
    t0 = time.perf_counter()
    for _ in range(n_reps):
        fn()
    elapsed = time.perf_counter() - t0
    print(f"\n{'=' * 70}\n{label} [SIN profiler]: {elapsed:.3f}s total "
          f"({n_reps} rep., {elapsed / n_reps * 1000:.1f}ms/rep)\n{'=' * 70}")


def main():
    args = sys.argv[1:]
    mode  = "rebuild"
    limit = None
    raw   = False
    for a in args:
        if a in ("delta", "rebuild"):
            mode = a
        elif a == "--raw":
            raw = True
        elif a.isdigit():
            limit = int(a)
    force = (mode == "rebuild")

    s = get_session()
    # Mismos códigos que el orquestador real (backfill_all_indicators): los
    # indicadores keep_history con función de backfill, en orden de id.
    defs = s.query(IndicatorDefinition).filter(
        IndicatorDefinition.keep_history.is_(True)
    ).order_by(IndicatorDefinition.id).all()
    codes = [d.code for d in defs if d.code in _BACKFILL_FNS]
    if not codes:
        raise SystemExit("No hay indicadores keep_history con función de backfill.")

    print("Cargando precios en memoria...")
    price_cache = _load_all_prices(s)
    asset_ids = list(price_cache.keys())
    if limit:
        # Los de más historia primero: lote más pesado/representativo.
        asset_ids = sorted(asset_ids, key=lambda a: len(price_cache[a]),
                           reverse=True)[:limit]
        price_cache = {a: price_cache[a] for a in asset_ids}
    print(f"Lote: {len(asset_ids)} activos × {len(codes)} códigos — modo {mode}")

    print("Precalculando resamples semanales/mensuales...")
    df_w_cache = {aid: _resample_ohlc(df, "W") for aid, df in price_cache.items()}
    df_m_cache = {aid: _resample_ohlc(df, "M") for aid, df in price_cache.items()}
    best_sma_cache = _load_best_sma_cache(s)
    # {} en rebuild (force=True); en delta, tail-stats por código desde ind_asset_meta.
    tail_stats_by_code = _precompute_all_tail_stats(s, codes, force)

    def _run_batch():
        # Mismos argumentos posicionales con los que _process_batch_task
        # invoca al worker en el proceso hijo (asset_tick=None: sin progreso).
        return _backfill_batch_worker(
            0, asset_ids, codes, force, None,
            price_cache, best_sma_cache, df_w_cache, df_m_cache,
            tail_stats_by_code)

    # Un solo lote (n_reps=1): el worker escribe en la BD; repetir solo
    # re-upsertearía las mismas filas.
    label = f"_backfill_batch_worker (1 lote inline, {mode})"
    (_raw if raw else _profile)(label, _run_batch, 1)


if __name__ == "__main__":
    main()
