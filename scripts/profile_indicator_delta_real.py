"""
Mide el costo REAL de punta a punta de la fase de indicadores (delta o
rebuild), llamando al mismo entrypoint que usa producción —
update_indicator_history() / rebuild_indicator_history()— con el ProcessPool
REAL activo (spawn de verdad, pickling, Queue de progreso, contención de
conexiones entre los hijos). A diferencia de profile_pool_batch.py (que corre
UN lote INLINE, sin spawn, para aislar el cómputo puro), este script es la
otra mitad de la comparación: el tiempo de pared que un usuario vería.

MOTIVO: el 22-jul-2026 se comparó el cómputo puro medido acá en el Codespace
(profile_pool_batch.py --raw, backfill delta: 0.0556 s/activo, 1 proceso) más
compute_current_indicators (profile_current_indicators.py, quick=True:
~0.065 s/activo, 1 proceso) contra el dato real de producción en Railway
(113s / 499 activos = 0.2265 s/activo, CON el ProcessPool de 4 procesos ya
puesto). La proyección ingenua (sumar los componentes y dividir por 4) dio
7.5x MENOS que el número real. Ese hueco puede ser: contención real de
IPC/DB entre los 4 procesos, diferencia de hardware Codespace↔Railway, o que
el activo de referencia (^GSPC, la serie con más historia) no sea
representativo del promedio. Este script corre el camino REAL para separar
esas tres causas: si el número acá (Codespace, ProcessPool real) queda cerca
del 0.2265 s/activo de Railway, el hueco es overhead de paralelismo real (no
hardware). Si queda cerca de la proyección ingenua (~0.03 s/activo), el hueco
es específico de Railway (hardware, contención de red con Yahoo si hay
descarga de por medio, o `max_connections` compitiendo con otra carga).

IMPORTANTE — umbral del pool: `_use_process_pool` NO activa el ProcessPool
por debajo de `IND_POOL_MIN_ASSETS` (default 1500; Railway lo tiene en 300
según medición previa, así que ahí se activa solo). Si se corre contra una
base con un universo más chico que ese umbral, bajarlo por variable de
entorno para forzar el camino de procesos — si no, esto mide threads, no lo
que se quiere comparar. El script imprime el (use_procs, n_procs) resuelto
ANTES de correr para poder verificarlo.

ACOPLADO A BD Y A PRODUCCIÓN: escribe de verdad (upsert en
current_indicator_values e ind_{code}), exactamente lo mismo que
"Actualizar indicadores" del Centro de Datos — es delta, no debería sorprender
a nadie que mire el resultado. En rebuild además BORRA y recalcula toda la
historia de cada activo — mismo efecto que "Recalcular completo" desde la UI,
pero SIN el guard adicional que la UI podría tener. Por eso el script toma el
mismo lock (`run_lock_service.HEAVY_WRITE`) que usa el Centro de Datos ANTES
de arrancar: si hay una corrida real en curso (el job diario del scheduler, o
alguien tocando un botón desde la UI al mismo tiempo), esto se niega a correr
en vez de pisarla. Igual, correrlo es lanzar una corrida real contra
producción — pensarlo como tal, no como un experimento aislado.

Uso (contra la base real, con la app corriendo o no):
    # delta (default) — el camino diario real, equivalente a "Actualizar indicadores"
    python scripts/profile_indicator_delta_real.py

    # rebuild — CUIDADO: borra y recalcula TODA la historia de indicadores
    python scripts/profile_indicator_delta_real.py --rebuild

    # forzar el ProcessPool en una base con menos activos que el umbral:
    IND_POOL_MIN_ASSETS=1 IND_POOL_PROCS=4 python scripts/profile_indicator_delta_real.py
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import get_session
from app.services import run_lock_service as _rl
from app.services.technical_service import (
    _count_price_assets, _use_process_pool, rebuild_indicator_history,
    update_indicator_history,
)


def main():
    rebuild = "--rebuild" in sys.argv[1:]

    s = get_session()
    n_assets = _count_price_assets(s)
    use_procs, n_procs = _use_process_pool(n_assets)
    print(f"Activos con precio: {n_assets}")
    print(f"_use_process_pool -> use_procs={use_procs}, n_procs={n_procs}")
    if not use_procs:
        print(
            "\n*** AVISO: esto va a correr por THREADS, no por procesos. ***\n"
            "Si querés comparar contra el ProcessPool real, relanzá con:\n"
            "    IND_POOL_MIN_ASSETS=1 IND_POOL_PROCS=4 python "
            f"{Path(__file__).name} {'--rebuild' if rebuild else ''}\n"
        )

    # Mismo lock que usa el Centro de Datos (HEAVY_WRITE, compartido entre
    # descarga de precios, indicadores y fundamentales): si hay una corrida
    # real en curso, no pisarla.
    lock_token = _rl.guarded_acquire(_rl.HEAVY_WRITE)
    if lock_token is None:
        raise SystemExit(
            "Hay otra corrida pesada en curso (run_lock ocupado) — no se "
            "puede medir sin pisarla. Esperá a que termine o revisá el "
            "Centro de Datos."
        )

    last_pct = -1

    def _cb(cur, total, label=""):
        nonlocal last_pct
        pct = int(cur * 100 / total) if total else 0
        if pct != last_pct and pct % 10 == 0:
            last_pct = pct
            print(f"  {pct:3d}%  ({cur}/{total})  {label}")

    fn = rebuild_indicator_history if rebuild else update_indicator_history
    label = "rebuild_indicator_history" if rebuild else "update_indicator_history"

    print(f"\nCorriendo {label}() REAL (recompute_current + backfill), "
          f"contra la base real...\n")
    try:
        with _rl.heartbeating(_rl.HEAVY_WRITE, lock_token):
            t0 = time.perf_counter()
            result = fn(progress_cb=_cb)
            elapsed = time.perf_counter() - t0
    except BaseException:
        # heartbeating ya libera el lock al salir (éxito o excepción) —
        # no hay nada más que limpiar acá.
        raise

    por_activo = elapsed / n_assets if n_assets else 0.0
    print(f"\n{'=' * 70}")
    print(f"{label} — SIN profiler, ProcessPool real: {elapsed:.3f}s total, "
          f"{n_assets} activos, {por_activo * 1000:.2f}ms/activo")
    print(f"resumen: {result}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
