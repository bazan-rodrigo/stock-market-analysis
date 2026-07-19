"""
Compara el costo REAL de las dos implementaciones de _series_checksum sobre
series REALES de la base, en UNA SOLA corrida y en el mismo proceso.

Por que existe: la version por bytes crudos (commit d607273) se midio 14x
mas rapida con datos SINTETICOS en la PC de desarrollo, pero no habia forma
de validarla en entorno real. El A/B "correr el lote entero antes y despues"
exige git checkout y una maquina estable — imposible en Railway (contenedores
efimeros, CPU variable, sin git). Este script resuelve eso: cronometra AMBAS
implementaciones una al lado de la otra, mismo hardware, misma sesion, mismos
datos. Corre en cualquier entorno con la BD levantada.

SOLO LECTURA: unicamente SELECTs sobre prices y las tablas ind_*. No escribe
nada, no invalida checksums, no dispara recalculos.

Como se arma cada serie: _series_checksum se aplica a la serie COMPLETA recien
calculada (con None/NaN en el warmup de las ventanas moviles y en los huecos),
no solo a los valores guardados. Por eso se reconstruye contra el calendario
de precios del activo: vals[i] = valor guardado en esa fecha, o None. Eso
reproduce la densidad de nulos real, que es justo lo que mi benchmark
sintetico podia estar representando mal.

Uso (Codespace o Railway, con la BD levantada):
    python scripts/bench_series_checksum.py           # 20 activos con mas historia
    python scripts/bench_series_checksum.py 50        # 50 activos
"""
import hashlib
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import sqlalchemy as sa

from app.database import get_session
from app.models import Price
from app.services.technical_service import (
    _CHECKSUM_DEP_CODES, _series_checksum,
)
from app.services.verification_service import _prefetch_stored

# Llamadas a _series_checksum observadas en un lote delta real de 144 activos
# x 24 codigos (cProfile: 3425 ncalls). Se usa para extrapolar el ahorro por
# lote a partir del costo por serie.
_CALLS_PER_BATCH = 3425


def _checksum_old(vals: list) -> str:
    """Copia LITERAL de la implementacion previa a d607273 (un str() por
    valor). Es el brazo de control del A/B."""
    if not vals:
        return ""
    parts = []
    for v in vals:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            parts.append("")
        else:
            parts.append(str(v))
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def _top_assets(session, limit: int) -> list:
    """Activos con mas historia de precios (lote mas pesado/representativo).
    No selecciona columnas fuera del GROUP BY: portable MySQL/PostgreSQL."""
    rows = session.execute(
        sa.select(Price.asset_id, sa.func.count().label("n"))
        .group_by(Price.asset_id)
        .order_by(sa.desc("n"))
        .limit(limit)
    ).all()
    return [r.asset_id for r in rows]


def _calendars(session, asset_ids: list) -> dict:
    """{asset_id: [fechas ordenadas]} — el calendario propio de cada activo."""
    rows = session.execute(
        sa.select(Price.asset_id, Price.date)
        .where(Price.asset_id.in_(asset_ids))
        .order_by(Price.asset_id, Price.date)
    ).all()
    out: dict = {}
    for aid, d in rows:
        out.setdefault(aid, []).append(d)
    return out


def _build_series(calendars: dict, stored_by_code: dict) -> list:
    """[(code, vals)] reconstruyendo la serie completa contra el calendario:
    None donde no hay valor guardado (warmup de ventanas moviles y huecos)."""
    series = []
    for code, by_asset in stored_by_code.items():
        for aid, dates in calendars.items():
            stored = by_asset.get(aid)
            if not stored:
                continue          # ese activo no tiene ese indicador calculado
            series.append((code, [stored.get(d) for d in dates]))
    return series


def _time(fn, series: list, reps: int) -> float:
    """ms promedio por serie."""
    t0 = time.perf_counter()
    for _ in range(reps):
        for _code, vals in series:
            fn(vals)
    elapsed = time.perf_counter() - t0
    return elapsed / reps / len(series) * 1000


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 20
    s = get_session()

    asset_ids = _top_assets(s, limit)
    if not asset_ids:
        raise SystemExit("No hay precios cargados en esta base.")
    calendars = _calendars(s, asset_ids)
    codes = sorted(_CHECKSUM_DEP_CODES)

    print(f"Leyendo series guardadas: {len(asset_ids)} activos x {len(codes)} "
          f"codigos con checksum...")
    # Codigo por codigo: si un indicador nunca se calculo su tabla no existe
    # (NoSuchTableError) y no debe tumbar el bench — se saltea y se avisa.
    stored_by_code: dict = {}
    for code in codes:
        try:
            stored_by_code.update(_prefetch_stored(s, [code], asset_ids))
        except Exception as exc:
            print(f"  (salteo {code}: {type(exc).__name__})")
    series = _build_series(calendars, stored_by_code)
    if not series:
        raise SystemExit(
            "No hay series de _CHECKSUM_DEP_CODES guardadas para esos activos "
            "(la base no tiene indicadores calculados todavia).")

    n_bars = sum(len(v) for _c, v in series) / len(series)
    print(f"{len(series)} series reales, {n_bars:.0f} barras promedio\n")

    # Sanidad: sobre datos reales, ambas versiones tienen que ser
    # DETERMINISTAS (misma serie -> mismo hash en dos llamadas seguidas).
    for label, fn in (("old", _checksum_old), ("new", _series_checksum)):
        _c, sample = series[0]
        if fn(sample) != fn(sample):
            raise SystemExit(f"{label} no es determinista — abortando")

    reps = 5
    ms_old = _time(_checksum_old, series, reps)
    ms_new = _time(_series_checksum, series, reps)

    print(f"{'=' * 62}")
    print(f"  old (str por valor)  : {ms_old:8.4f} ms/serie")
    print(f"  new (bytes crudos)   : {ms_new:8.4f} ms/serie")
    speedup = (ms_old / ms_new) if ms_new else float("inf")
    print(f"  speedup              : {speedup:8.2f}x")
    print(f"{'=' * 62}")

    a = ms_old * _CALLS_PER_BATCH / 1000
    b = ms_new * _CALLS_PER_BATCH / 1000
    print(f"\nExtrapolado a un lote delta ({_CALLS_PER_BATCH} llamadas):")
    print(f"  old: {a:6.2f} s   new: {b:6.2f} s   ->  ahorro {a - b:6.2f} s")
    print("\nCriterio: contra un lote delta real de ~19 s, un ahorro de pocos")
    print("decimos de segundo NO justifica la invalidacion unica del cambio de")
    print("hash (revertir d607273); un ahorro de varios segundos si.")

    # Desglose numerico vs texto: el camino de texto quedo intacto en
    # d607273, asi que ahi no deberia haber diferencia.
    num = [(c, v) for c, v in series if not c.startswith("trend_")]
    txt = [(c, v) for c, v in series if c.startswith("trend_")]
    for label, subset in (("numericas", num), ("texto (trend_*)", txt)):
        if not subset:
            continue
        o = _time(_checksum_old, subset, reps)
        n = _time(_series_checksum, subset, reps)
        print(f"\n  {label:16s}: old {o:7.4f} / new {n:7.4f} ms  "
              f"({(o / n if n else float('inf')):5.2f}x, {len(subset)} series)")


if __name__ == "__main__":
    main()
