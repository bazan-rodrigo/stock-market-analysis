"""
Perfila el CÓMPUTO PURO de ratios fundamentales — local, con inputs sintéticos,
SIN base de datos.

Objetivo: _compute_quarterly_ratios y _compute_daily_ratios
(app/services/fundamental_service.py), el núcleo de fórmulas que la reescritura
fila-completa (_backfill_fund_quarterly_all) ejecuta una vez por (activo,
trimestre). Este script mide SOLO ese cómputo aislado, no toca InnoDB ni la
tabla ancha.

Qué NO mide (y por qué): el camino de ESCRITURA fila-completa
(_backfill_fund_quarterly_all: upserts de la fila completa a la tabla ancha
ind_fundamental_quarterly, deltas contra fechas existentes, retry de locks) es
dominado por la BD y solo tiene sentido medirlo en el Codespace con MariaDB/
PostgreSQL real. Esta PC de desarrollo no levanta la app (sin driver MySQL ni
yfinance), así que acá aislamos el cómputo con un stub sqlite —igual que
tests/conftest.py— sin abrir jamás una conexión (los ratios son lógica pura).

Cómo corre local: se construye un activo sintético representativo (~40
trimestres = 10 años, con crecimiento y ruido determinista) y una serie de
precios diaria (~2600 barras), replicando la construcción de inputs de
tests/test_fundamental_ratios.py (helper q(), _Quarter namedtuple, arrays de
ordinales). No hace falta BD.

Uso:
    ./venv/Scripts/python.exe scripts/profile_fundamental_ratios.py   # bash
    venv\\Scripts\\python.exe scripts\\profile_fundamental_ratios.py    # Windows
"""
import cProfile
import io
import os
import pstats
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Igual que tests/conftest.py: apuntar DATABASE_URL a un stub sqlite ANTES de
# importar nada de app, para poder importar el servicio sin el driver de MySQL.
# Los ratios son lógica pura: nunca se abre una conexión.
os.environ.setdefault("DATABASE_URL", f"sqlite:///{ROOT / '.profile-stub.db'}")

import numpy as np

from app.services.fundamental_service import (
    _Quarter, _compute_daily_ratios, _compute_quarterly_ratios, _ref_1y_ord,
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


# ── construcción de inputs sintéticos (espeja tests/test_fundamental_ratios.py) ──

def q(period, **kw):
    """_Quarter con todos los campos en None salvo period_date + kwargs
    (idéntico al helper q() de los tests)."""
    base = {f: None for f in _Quarter._fields}
    base["period_date"] = period
    base.update(kw)
    return _Quarter(**base)


def _quarter_end_dates(n: int) -> list:
    """n fechas de cierre trimestral ascendentes (mar/jun/sep/dic)."""
    ends = [(3, 31), (6, 30), (9, 30), (12, 31)]
    out, year, i = [], 2015, 0
    while len(out) < n:
        m, d = ends[i % 4]
        out.append(date(year, m, d))
        i += 1
        if i % 4 == 0:
            year += 1
    return out


def _build_quarters(n: int = 40) -> list:
    """Activo sintético con ~10 años de trimestres, crecimiento + ruido
    determinista. Se llenan los campos que usan las fórmulas (revenue,
    net_income, márgenes, deuda/equity, eps_actual para eps_growth, nopat/
    invested_capital_avg para el camino ROIC preferido) y shares en cada
    trimestre (regla de negocio: se toma el shares TTM MÁS RECIENTE)."""
    rng = np.random.RandomState(7)
    dates_ = _quarter_end_dates(n)
    quarters = []
    for i, d in enumerate(dates_):
        growth = 1.0 + 0.03 * i               # tendencia creciente trimestre a trimestre
        rev = float(round(1000 * growth * (1 + 0.05 * rng.randn()), 2))
        ni = float(round(0.10 * rev * (1 + 0.15 * rng.randn()), 2))
        quarters.append(q(
            d,
            revenue=rev,
            gross_profit=round(0.40 * rev, 2),
            operating_income=round(0.20 * rev, 2),
            net_income=ni,
            ebitda=round(0.25 * rev, 2),
            total_debt=round(500 * growth, 2),
            equity=round(1000 * growth, 2),
            shares=float(100 + i),            # shares reportado cada trimestre
            fcf=round(0.08 * rev, 2),
            operating_cf=round(0.18 * rev, 2),
            eps_actual=round(ni / (100 + i), 4),
            eps_estimated=round(ni / (100 + i) * 0.98, 4),
            nopat=round(0.14 * rev, 2),
            invested_capital_avg=round(1500 * growth, 2),
        ))
    return quarters


def _build_prices(quarters: list, days: int = 2600):
    """Serie diaria de cierres desde el primer trimestre (garantiza last_q>=0
    para toda fecha). Devuelve (dates, d_ords, closes)."""
    rng = np.random.RandomState(11)
    start = quarters[0].period_date
    dates = [start + timedelta(days=i) for i in range(days)]
    d_ords = np.array([d.toordinal() for d in dates], dtype=np.int64)
    closes = np.round(50 + rng.randn(days).cumsum() * 0.3, 2).astype(float)
    closes = np.abs(closes) + 1.0             # precios positivos
    return dates, d_ords, closes


# ── passes de cómputo (una "rep" = el trabajo de UN activo) ────────────────────

def _quarterly_pass(quarters: list) -> None:
    """Todos los trimestres de un activo, tal como los recorre el camino
    fila-completa (_compute_quarterly_ratios una vez por trimestre)."""
    for idx in range(len(quarters)):
        _compute_quarterly_ratios(quarters, idx)


def _daily_pass(quarters, q_ords, d_ords, closes) -> None:
    """Todas las fechas de un activo, una llamada a _compute_daily_ratios por
    fecha (el camino por-fecha que _daily_ratio_series vectoriza)."""
    for i in range(len(closes)):
        d_ord = int(d_ords[i])
        last_q = int(np.searchsorted(q_ords, d_ord, side="right")) - 1
        ref = _ref_1y_ord(date.fromordinal(d_ord))
        _compute_daily_ratios(float(closes[i]), quarters, q_ords, last_q,
                              d_ords, closes, ref)


def main():
    quarters = _build_quarters(40)
    q_ords = np.array([x.period_date.toordinal() for x in quarters], dtype=np.int64)
    dates, d_ords, closes = _build_prices(quarters, 2600)

    print(f"Activo sintetico: {len(quarters)} trimestres "
          f"({quarters[0].period_date} -> {quarters[-1].period_date}), "
          f"{len(closes)} barras diarias ({dates[0]} -> {dates[-1]})")

    quarterly_reps = 100   # 100 rep × 40 trimestres = 4.000 llamadas
    daily_reps = 50        # 50 rep × 2600 fechas  = 130.000 llamadas

    _profile(
        "_compute_quarterly_ratios (pass completo por activo x 40 trimestres)",
        lambda: _quarterly_pass(quarters),
        quarterly_reps,
    )
    _profile(
        "_compute_daily_ratios (pass completo por activo x 2600 fechas)",
        lambda: _daily_pass(quarters, q_ords, d_ords, closes),
        daily_reps,
    )


if __name__ == "__main__":
    main()
