"""
A/B del ProcessPool de indicadores: corre el MISMO delta real con varias
configuraciones de paralelismo, TODAS en el mismo proceso y una atrás de
otra, y las compara.

POR QUÉ ASÍ (y no corriendo el script una vez por config): Railway asigna
contenedores efímeros con CPU variable, así que dos corridas de sesiones
distintas NO son comparables — es la regla que ya está anotada en
project_scaling_target.md ("comparar corridas de sesiones distintas es
ruido"), y que igual se violó al comparar los 113s del log contra los 52.7s
medidos después. Con el Codespace retirado (jul-2026) no hay otra máquina
donde medir, así que la única mitigación posible es que todas las mediciones
del A/B compartan la MISMA sesión y el MISMO container. Mismo patrón que
scripts/bench_series_checksum.py y bench_pairs_to_write.py.

QUÉ DECIDE. Medido el 22-jul-2026: el delta completo con 4 procesos costó
105.64 ms/activo, contra una suma de componentes a 1 proceso de 85-120
ms/activo — o sea el pool compró entre 1.0x y 1.15x, no 4x. Dos explicaciones
que una sola medición no distingue:

  (a) OVERHEAD FIJO de spawn: cada hijo importa pandas + SQLAlchemy + la app.
      Ese costo NO escala con la cantidad de activos, así que a 10.000 se
      amortiza y el costo marginal real es mejor que el medido.
  (b) EL POOL NO ESCALA: contención de conexiones/DB entre los hijos. Agregar
      procesos no ayuda y el número medido es el que hay.

Barrer la cantidad de PROCESOS las separa: si el tiempo baja de 2 a 4 a 6, el
pool escala y lo que sobra es (a). Si queda plano o empeora, es (b) y ahí hay
un 3-4x sin cobrar que vale la pena perseguir. El camino de THREADS (procs=1,
porque _use_process_pool cae a threads con n_procs<=1) va como referencia: es
la línea base anterior al ProcessPool.

CONTROL DE DERIVA: la primera config con procesos se repite AL FINAL. Si las
dos corridas de la misma config difieren mucho, el container estuvo ruidoso
durante la medición y NINGUNA comparación de esta tanda es confiable — el
script lo dice explícitamente en vez de dejar que se lea una diferencia que
es puro ruido.

CALENTAMIENTO: antes de la primera medición corre un delta sin cronometrar.
El delta rellena huecos ADEMÁS de recalcular la última fecha, así que la
primera corrida haría más trabajo que las siguientes y quedaría penalizada
sin que eso tenga nada que ver con el paralelismo. Después del calentamiento
todas las corridas ven el mismo estado estacionario.

ACOPLADO A BD Y A PRODUCCIÓN: escribe de verdad, es el mismo trabajo que
"Actualizar indicadores" del Centro de Datos, repetido N+2 veces. Toma el
run_lock HEAVY_WRITE UNA vez para toda la tanda, así el job diario del
scheduler no se mete en el medio. Es delta, no rebuild: no borra historia.

DURACIÓN: cada corrida es un delta completo. Con las configs por defecto son
6 corridas — contando que el camino de threads es más lento, calcular entre 6
y 12 minutos. No cortarlo por la mitad: sin la repetición final no hay control
de deriva.

Uso (en la shell del servicio web de Railway):
    python scripts/bench_ind_pool_procs.py           # threads, 2, 4, 6 (+ repite 4)
    python scripts/bench_ind_pool_procs.py 1 4       # solo threads vs 4
    python scripts/bench_ind_pool_procs.py 4 8 12    # barrido más agresivo
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import Config
from app.database import get_session
from app.services import run_lock_service as _rl
from app.services.technical_service import (
    _count_price_assets, _use_process_pool, update_indicator_history,
)

_DEFAULT_CONFIGS = [1, 2, 4, 6]


def _correr(n_procs: int, n_assets: int, *, cronometrar: bool = True):
    """Corre un delta completo con IND_POOL_PROCS=n_procs. Devuelve
    (segundos, use_procs, procs_resueltos)."""
    # _resolve_pool_procs / _use_process_pool hacen `from app.config import
    # Config` ADENTRO de la función, así que leen el atributo de clase en cada
    # llamada: pisarlo acá alcanza para cambiar la config sin relanzar nada.
    Config.IND_POOL_PROCS = n_procs
    use_procs, procs = _use_process_pool(n_assets)

    etiqueta = f"procs={procs}" if use_procs else "THREADS"
    print(f"\n--- corriendo con IND_POOL_PROCS={n_procs} -> {etiqueta} "
          f"{'(calentamiento, sin cronometrar)' if not cronometrar else ''}",
          flush=True)

    t0 = time.perf_counter()
    res = update_indicator_history()
    elapsed = time.perf_counter() - t0

    errores = len(res.get("errors", []))
    print(f"    {elapsed:7.2f}s   ({res.get('success', 0)}/{res.get('total', 0)}"
          f"{f', {errores} errores' if errores else ''})", flush=True)
    return elapsed, use_procs, procs


def main():
    args = sys.argv[1:]
    try:
        configs = [int(a) for a in args] if args else list(_DEFAULT_CONFIGS)
    except ValueError:
        raise SystemExit(f"Argumentos inválidos: {args} — se esperan enteros "
                         f"(cantidad de procesos). Ej: 1 2 4 6")

    original = Config.IND_POOL_PROCS
    s = get_session()
    n_assets = _count_price_assets(s)
    print(f"Activos con precio: {n_assets}")
    print(f"IND_POOL_MIN_ASSETS={Config.IND_POOL_MIN_ASSETS} "
          f"(por debajo de esto NO se usa el pool)")
    print(f"Configs a medir: {configs}")

    if n_assets < Config.IND_POOL_MIN_ASSETS:
        print(f"\n*** AVISO: {n_assets} activos < umbral "
              f"{Config.IND_POOL_MIN_ASSETS}: TODAS las configs van a caer a "
              f"threads y el A/B no mide nada. Relanzá con "
              f"IND_POOL_MIN_ASSETS=1 en el entorno. ***")

    # Un solo lock para toda la tanda: son N+2 corridas reales seguidas.
    lock_token = _rl.guarded_acquire(_rl.HEAVY_WRITE)
    if lock_token is None:
        raise SystemExit(
            "Hay otra corrida pesada en curso (run_lock ocupado) — no se puede "
            "medir sin pisarla. Esperá a que termine o revisá el Centro de Datos."
        )

    resultados: list[tuple[int, float, bool, int]] = []
    try:
        with _rl.heartbeating(_rl.HEAVY_WRITE, lock_token):
            # Calentamiento: deja la base en estado estacionario (sin huecos),
            # para que la primera medición no pague el relleno.
            _correr(configs[0], n_assets, cronometrar=False)

            for n in configs:
                seg, use_procs, procs = _correr(n, n_assets)
                resultados.append((n, seg, use_procs, procs))

            # Control de deriva: repetir la PRIMERA config que haya usado
            # procesos (o la primera a secas, si ninguna los usó).
            repetir = next((n for n, _, up, _ in resultados if up), configs[0])
            print(f"\n--- control de deriva: repito IND_POOL_PROCS={repetir}")
            seg_repe, _, _ = _correr(repetir, n_assets)
    finally:
        Config.IND_POOL_PROCS = original

    # ── Reporte ──────────────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print(f"A/B del ProcessPool — {n_assets} activos, delta completo, "
          f"mismo proceso y mismo container")
    print(f"{'=' * 70}")
    print(f"{'config':>10}  {'camino':>8}  {'total':>9}  {'ms/activo':>10}  "
          f"{'vs threads':>11}")

    base_threads = next((seg for _, seg, up, _ in resultados if not up), None)
    for n, seg, use_procs, procs in resultados:
        camino = f"proc×{procs}" if use_procs else "threads"
        rel = f"{base_threads / seg:.2f}x" if base_threads and seg else "—"
        print(f"{n:>10}  {camino:>8}  {seg:8.2f}s  "
              f"{seg / n_assets * 1000:9.2f}  {rel:>11}")

    primera = dict((n, s) for n, s, _, _ in resultados)[repetir]
    deriva = abs(seg_repe - primera) / primera * 100 if primera else 0
    print(f"\nControl de deriva (IND_POOL_PROCS={repetir}): {seg_repe:.2f}s "
          f"contra {primera:.2f}s en la primera pasada — deriva {deriva:.1f}%")
    if deriva > 15:
        print("  *** >15%: el container estuvo RUIDOSO durante la tanda. "
              "Las diferencias entre configs de arriba pueden ser ruido, no "
              "efecto del paralelismo — repetir la medición. ***")
    else:
        print("  <=15%: el container se mantuvo estable, la comparación "
              "de arriba es utilizable.")

    print(f"\nCómo leerlo: si el tiempo BAJA al subir procesos, el pool escala "
          f"y lo que\nsobra contra el ideal es overhead fijo de spawn (se "
          f"amortiza a 10.000 activos).\nSi queda PLANO o empeora, es "
          f"contención y ahí hay un 3-4x sin cobrar.")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
