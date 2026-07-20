"""
Valida el commit 8a73ca4 (mascara pd.notna vectorizada) sobre series REALES,
cronometrando la version vieja y la nueva en el mismo proceso.

Por que existe: 8a73ca4 se aprobo con un micro-benchmark SINTETICO en la PC
de desarrollo (0.708 -> 0.321 ms). Ese mismo tipo de evidencia sobrestimo por
10x la optimizacion del checksum (d607273), que despues hubo que revertir al
medirla contra datos reales. Seria incoherente revertir una por falta de
evidencia real y dejar pasar la otra con la misma evidencia.

Ademas 8a73ca4 puede tener LA MISMA TRAMPA: pd.notna sobre una lista tiene
que convertirla a array de numpy, y en series largas y mayormente nulas esa
conversion puede costar mas de lo que ahorra evitando las llamadas escalares
— que es exactamente el mecanismo que hundio al checksum.

SOLO LECTURA: unicamente SELECTs sobre prices y las tablas ind_*.

Cubre los TRES modos de _pairs_to_write, usando como `existing` los valores
realmente guardados (que es lo que recibe en produccion):
  - None : rebuild (reemplazo total)
  - set  : delta tail-mode (faltantes + ultima)
  - dict : delta de full_sample (faltantes + cambiados + ultima)
y tambien _series_stats, que recorre la serie completa una vez por
(activo, codigo).

Uso (Codespace o Railway, con la BD levantada):
    python scripts/bench_pairs_to_write.py           # 20 activos con mas historia
    python scripts/bench_pairs_to_write.py 50        # 50 activos
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import sqlalchemy as sa

from app.database import get_session
from app.models import Price
from app.services.technical_service import (
    _CHECKSUM_DEP_CODES, _pairs_to_write, _series_stats,
)
from app.services.verification_service import _prefetch_stored

# ncalls observados para _pairs_to_write y _series_stats en un lote delta real
# de 144 activos x 24 codigos (cProfile: 3432 cada una).
_CALLS_PER_BATCH = 3432


# ── Implementaciones PREVIAS a 8a73ca4 (brazo de control) ────────────────────

def _pairs_old(dates_list: list, vals_list: list, existing) -> list:
    """Copia literal: una llamada escalar a pd.notna por valor."""
    if existing is None:
        return [(d, v) for d, v in zip(dates_list, vals_list) if pd.notna(v)]

    last_d = dates_list[-1] if dates_list else None
    if isinstance(existing, dict):
        def _keep(d, v):
            if d == last_d or d not in existing:
                return True
            old = existing[d]
            try:
                return float(old) != float(v)
            except (TypeError, ValueError):
                return str(old) != str(v)
        return [(d, v) for d, v in zip(dates_list, vals_list)
                if pd.notna(v) and _keep(d, v)]

    return [(d, v) for d, v in zip(dates_list, vals_list)
            if pd.notna(v) and (d not in existing or d == last_d)]


def _stats_old(dates_list: list, vals_list: list):
    """Copia literal previa a 8a73ca4."""
    valid = [d for d, v in zip(dates_list, vals_list) if pd.notna(v)]
    return (valid[0], valid[-1], len(valid)) if valid else None


# ── Carga de series reales (mismo criterio que bench_series_checksum) ────────

def _top_assets(session, limit: int) -> list:
    rows = session.execute(
        sa.select(Price.asset_id, sa.func.count().label("n"))
        .group_by(Price.asset_id)
        .order_by(sa.desc("n"))
        .limit(limit)
    ).all()
    return [r.asset_id for r in rows]


def _calendars(session, asset_ids: list) -> dict:
    rows = session.execute(
        sa.select(Price.asset_id, Price.date)
        .where(Price.asset_id.in_(asset_ids))
        .order_by(Price.asset_id, Price.date)
    ).all()
    out: dict = {}
    for aid, d in rows:
        out.setdefault(aid, []).append(d)
    return out


def _build_cases(calendars: dict, stored_by_code: dict) -> list:
    """[(dates, vals, stored)] — serie completa contra el calendario (None
    donde no hay valor) mas el dict de lo guardado, que es el `existing`
    real de los modos delta."""
    cases = []
    for _code, by_asset in stored_by_code.items():
        for aid, dates in calendars.items():
            stored = by_asset.get(aid)
            if not stored:
                continue
            cases.append((dates, [stored.get(d) for d in dates], stored))
    return cases


def _time(fn, cases: list, reps: int) -> float:
    t0 = time.perf_counter()
    for _ in range(reps):
        for args in cases:
            fn(*args)
    return (time.perf_counter() - t0) / reps / len(cases) * 1000


def _report(label: str, old_fn, new_fn, cases: list, reps: int) -> None:
    # Equivalencia sobre datos reales antes de cronometrar: si las salidas
    # difieren, el speedup no significa nada.
    for args in cases[:20]:
        if old_fn(*args) != new_fn(*args):
            raise SystemExit(f"{label}: SALIDAS DISTINTAS — abortando")
    ms_old = _time(old_fn, cases, reps)
    ms_new = _time(new_fn, cases, reps)
    a = ms_old * _CALLS_PER_BATCH / 1000
    b = ms_new * _CALLS_PER_BATCH / 1000
    speed = (ms_old / ms_new) if ms_new else float("inf")
    flag = "  <-- REGRESION" if speed < 1.0 else ""
    print(f"  {label:34s} old {ms_old:7.4f} / new {ms_new:7.4f} ms  "
          f"({speed:5.2f}x)  lote: {a:5.2f}s -> {b:5.2f}s  "
          f"ahorro {a - b:+6.2f}s{flag}")


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 20
    s = get_session()

    asset_ids = _top_assets(s, limit)
    if not asset_ids:
        raise SystemExit("No hay precios cargados en esta base.")
    calendars = _calendars(s, asset_ids)
    codes = sorted(_CHECKSUM_DEP_CODES)

    print(f"Leyendo series guardadas: {len(asset_ids)} activos x {len(codes)} codigos...")
    stored_by_code: dict = {}
    for code in codes:
        try:
            stored_by_code.update(_prefetch_stored(s, [code], asset_ids))
        except Exception as exc:
            print(f"  (salteo {code}: {type(exc).__name__})")
    cases = _build_cases(calendars, stored_by_code)
    if not cases:
        raise SystemExit("No hay series guardadas para esos activos.")

    n_bars = sum(len(d) for d, _v, _s in cases) / len(cases)
    print(f"{len(cases)} series reales, {n_bars:.0f} barras promedio\n")

    reps = 3
    print("=" * 108)
    _report("_series_stats",
            lambda d, v, _st: _stats_old(d, v),
            lambda d, v, _st: _series_stats(d, v), cases, reps)
    _report("_pairs_to_write (None, rebuild)",
            lambda d, v, _st: _pairs_old(d, v, None),
            lambda d, v, _st: _pairs_to_write(d, v, None), cases, reps)
    _report("_pairs_to_write (set, delta tail)",
            lambda d, v, st: _pairs_old(d, v, set(st)),
            lambda d, v, st: _pairs_to_write(d, v, set(st)), cases, reps)
    _report("_pairs_to_write (dict, full_sample)",
            lambda d, v, st: _pairs_old(d, v, st),
            lambda d, v, st: _pairs_to_write(d, v, st), cases, reps)
    print("=" * 108)
    print("\nCriterio: 8a73ca4 se queda si NINGUN modo regresiona y el ahorro")
    print("agregado es positivo; si algun camino real empeora (como le paso al")
    print("checksum con las series de texto), se revierte.")
    print("\nOJO: los modos set/dict construyen `existing` desde lo guardado, que")
    print("es lo que reciben en produccion. El modo None (rebuild) no usa existing.")


if __name__ == "__main__":
    main()
