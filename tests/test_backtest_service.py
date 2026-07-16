"""Integración del backtest sobre el sqlite stub: run completo end-to-end.

Verifica el GATE de lectura (scores arrastrados en fechas sin precio propio
quedan afuera), la persistencia del run (status/rango/resultados) y el camino
de error (estrategia sin historia).
"""
import json
from datetime import date, timedelta

import pytest
import sqlalchemy as sa

from app.database import Base, engine, get_session

_TABLES = ("backtest_ic_point", "backtest_quantile_stat", "backtest_run",
           "strategy", "prices", "assets")


@pytest.fixture()
def bt_db():
    import app.models  # noqa: F401 — registra los modelos en Base.metadata
    from app.models import signal_store
    Base.metadata.create_all(engine)
    signal_store.ensure_strat_table(1)
    with engine.begin() as conn:
        for t in _TABLES + ("strat_res_1",):
            conn.execute(sa.text(f"DELETE FROM {t}"))
    yield
    with engine.begin() as conn:
        for t in _TABLES + ("strat_res_1",):
            conn.execute(sa.text(f"DELETE FROM {t}"))
    get_session().rollback()


def _trading_dates(n, start=date(2026, 1, 5)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _seed(dates):
    """A sube 1%/rueda, B baja 1%/rueda; C tiene score TODAS las fechas pero
    precio solo la primera (simula el score arrastrado por as-of)."""
    from app.models import Asset, Price, Strategy, signal_store
    s = get_session()
    for i, ticker in ((1, "GANA"), (2, "PIERDE"), (3, "ARRASTRADO")):
        s.add(Asset(id=i, ticker=ticker, name=ticker, price_source_id=1))
    s.add(Strategy(id=1, name="BT test", is_public=True))
    s.flush()

    rt = signal_store.get_strat_table(1)
    pa, pb = 100.0, 100.0
    for n, d in enumerate(dates):
        s.add(Price(asset_id=1, date=d, close=pa))
        s.add(Price(asset_id=2, date=d, close=pb))
        if n == 0:
            s.add(Price(asset_id=3, date=d, close=50.0))
        pa *= 1.01
        pb *= 0.99
        for aid, score in ((1, 100.0), (2, 0.0), (3, 50.0)):
            s.execute(rt.insert(), [{"asset_id": aid, "date": d,
                                     "score": score}])
    s.commit()


_CFG = {"horizons": [1], "lag": 1, "n_quantiles": 2, "min_assets": 2}


def test_run_completo_con_gate(bt_db):
    from app.models import BacktestIcPoint, BacktestQuantileStat, BacktestRun
    from app.services.backtest_service import get_run_results, run_backtest

    dates = _trading_dates(10)
    _seed(dates)

    run_id = run_backtest(1, _CFG)
    s = get_session()
    run = s.get(BacktestRun, run_id)
    assert run.status == "done"
    assert json.loads(run.config)["horizons"] == [1]

    # lag=1 + h=1 necesita i+2 dentro de la serie → computa dates[0..7]
    points = (s.query(BacktestIcPoint)
              .filter(BacktestIcPoint.run_id == run_id)
              .order_by(BacktestIcPoint.date).all())
    assert len(points) == 8
    assert run.date_from == dates[0] and run.date_to == dates[7]
    assert run.n_dates == 8

    # GATE: el activo 3 tiene score todas las fechas pero precio solo la
    # primera (y sin serie no hay retorno forward) → nunca entra: n=2 siempre.
    assert all(p.n_assets == 2 for p in points)

    # Monotonía perfecta: top (scores altos = GANA) ≈ +1%/rueda, bottom ≈ −1%.
    stats = {st.quantile: st for st in
             s.query(BacktestQuantileStat)
              .filter(BacktestQuantileStat.run_id == run_id).all()}
    assert stats[2].mean_ret == pytest.approx(0.01, abs=1e-9)
    assert stats[1].mean_ret == pytest.approx(-0.01, abs=1e-9)
    assert stats[2].pct_pos == 1.0 and stats[1].pct_pos == 0.0
    assert all(p.spread == pytest.approx(0.02, abs=1e-9) for p in points)
    # Con 2 activos no hay Spearman (necesita ≥3) — None, no crash.
    assert all(p.ic is None for p in points)

    res = get_run_results(run_id)
    assert res["run"].id == run_id
    assert len(res["quantile_stats"]) == 2
    assert res["ic_summary"] == {}  # sin ICs válidos


def test_estrategia_sin_historia_marca_error(bt_db):
    from app.models import BacktestRun, Strategy
    from app.services.backtest_service import run_backtest

    s = get_session()
    s.add(Strategy(id=1, name="Vacía", is_public=True))
    s.commit()

    with pytest.raises(ValueError, match="Recalcular completo"):
        run_backtest(1, _CFG)
    run = s.query(BacktestRun).one()
    assert run.status == "error"
    assert "Recalcular completo" in run.error


def test_normalize_config_valida():
    from app.services.backtest_service import normalize_config

    cfg = normalize_config({"horizons": [20, 5, 5], "n_quantiles": 4,
                            "min_assets": 2})
    assert cfg["horizons"] == [5, 20]
    assert cfg["min_assets"] == 4  # nunca menor que n_quantiles
    with pytest.raises(ValueError):
        normalize_config({"horizons": []})
    with pytest.raises(ValueError):
        normalize_config({"n_quantiles": 1})
