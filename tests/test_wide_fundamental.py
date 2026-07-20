"""Fundamentales diarios anchos (docs/notes/design_ind_wide_tables.md): con el
flag on, la escritura de los 4 fundamentales diarios va a ind_fundamental_daily.
Los 8 trimestrales siguen per-código.
"""
import datetime as dt

import pytest
import sqlalchemy as sa

from app.database import engine, get_session
from app.models import indicator_store as _mod
from app.models.indicator_store import ensure_wide_ind_tables

_WIDE_TABLES = ("ind_daily", "ind_weekly", "ind_monthly",
                "ind_fundamental_daily", "ind_fundamental_quarterly")


@pytest.fixture()
def fund_wide():
    ensure_wide_ind_tables(bind=engine)
    yield
    with engine.begin() as conn:
        for n in _WIDE_TABLES:
            conn.execute(sa.text(f"DROP TABLE IF EXISTS {n}"))
    for n in _WIDE_TABLES:
        if n in _mod._meta.tables:
            _mod._meta.remove(_mod._meta.tables[n])


@pytest.fixture()
def wide_on(monkeypatch):
    monkeypatch.setenv("USE_WIDE_IND_TABLES", "1")


def test_upsert_fund_value_rutea_diarios_a_wide(fund_wide, wide_on):
    from app.services.fundamental_service import _upsert_fund_value
    s = get_session()
    d = dt.date(2026, 7, 1)
    # dos diarios en la misma fila → acumulan sin pisarse
    _upsert_fund_value("fundamental_pe_ttm", 1, d, 15.5, s)
    _upsert_fund_value("fundamental_pb", 1, d, 2.3, s)
    s.commit()

    row = s.execute(sa.text(
        "SELECT fundamental_pe_ttm, fundamental_pb FROM ind_fundamental_daily "
        "WHERE asset_id = 1")).fetchone()
    assert row.fundamental_pe_ttm == 15.5
    assert row.fundamental_pb == 2.3


def test_upsert_fund_value_rutea_trimestrales_a_su_wide(fund_wide, wide_on):
    from app.services.fundamental_service import _upsert_fund_value
    s = get_session()
    d = dt.date(2026, 6, 30)
    _upsert_fund_value("fundamental_roic", 1, d, 0.12, s)
    _upsert_fund_value("fundamental_net_margin", 1, d, 0.25, s)
    s.commit()

    row = s.execute(sa.text(
        "SELECT fundamental_roic, fundamental_net_margin "
        "FROM ind_fundamental_quarterly WHERE asset_id = 1")).fetchone()
    assert row.fundamental_roic == 0.12
    assert row.fundamental_net_margin == 0.25


# ── backfill_asset_fund_history: vacía la cadencia una vez y bufferiza ────────
# (equivalente fundamental de backfill_asset_history; ver test_wide_cutover)

def _seed_fund_asset(s, asset_id, n_q=8, n_precios=200):
    """Activo con trimestrales y precios: lo mínimo para que los 12 ratios
    tengan con qué calcularse."""
    from app.database import Base
    import app.models  # noqa: F401
    from app.models import Asset, FundamentalQuarterly, Price
    from app.models.price_source import PriceSource
    Base.metadata.create_all(engine)
    if s.get(PriceSource, 1) is None:
        s.add(PriceSource(id=1, name="test")); s.flush()
    if s.get(Asset, asset_id) is None:
        s.add(Asset(id=asset_id, ticker=f"FD{asset_id}", price_source_id=1))
    base = dt.date(2022, 3, 31)
    for i in range(n_q):
        p = base.replace(year=base.year + (i // 4))
        p = dt.date(p.year, [3, 6, 9, 12][i % 4], 30)
        s.add(FundamentalQuarterly(
            asset_id=asset_id, period_date=p,
            revenue=1000 + i * 50, gross_profit=400 + i * 20,
            operating_income=200 + i * 10, net_income=100 + i * 5,
            ebitda=250 + i * 12, total_debt=500, equity=2000 + i * 30,
            shares=1000, fcf=90 + i * 4, operating_cf=150 + i * 6,
            eps_actual=0.1 + i * 0.005, nopat=150 + i * 8,
            invested_capital_avg=2500 + i * 40))
    d0 = dt.date(2022, 4, 1)
    for i in range(n_precios):
        s.add(Price(asset_id=asset_id, date=d0 + dt.timedelta(days=i),
                    close=20 + i * 0.05, high=21 + i * 0.05, low=19 + i * 0.05))
    s.commit()


def test_backfill_fund_history_idempotente_y_no_pierde_datos(fund_wide, wide_on):
    """Vacía cada cadencia fundamental de una vez y vuelca fila completa. Si
    ese borrado no reescribiera todo, la SEGUNDA corrida dejaría vacío."""
    from app.services.fundamental_service import backfill_asset_fund_history
    s = get_session()
    _seed_fund_asset(s, 7171)

    r1 = backfill_asset_fund_history(7171)
    assert r1["inserted"] > 0
    q1 = s.execute(sa.text(
        "SELECT COUNT(*) FROM ind_fundamental_quarterly WHERE asset_id = 7171"
    )).scalar()
    d1 = s.execute(sa.text(
        "SELECT COUNT(*) FROM ind_fundamental_daily WHERE asset_id = 7171"
    )).scalar()
    assert q1 > 0

    r2 = backfill_asset_fund_history(7171)
    q2 = s.execute(sa.text(
        "SELECT COUNT(*) FROM ind_fundamental_quarterly WHERE asset_id = 7171"
    )).scalar()
    d2 = s.execute(sa.text(
        "SELECT COUNT(*) FROM ind_fundamental_daily WHERE asset_id = 7171"
    )).scalar()
    assert (r2["inserted"], q2, d2) == (r1["inserted"], q1, d1)


def test_backfill_fund_history_no_toca_otros_activos(fund_wide, wide_on):
    """El DELETE por cadencia debe acotarse al activo."""
    from app.services.fundamental_service import (
        _upsert_fund_value, backfill_asset_fund_history)
    s = get_session()
    _seed_fund_asset(s, 7272)
    _upsert_fund_value("fundamental_roic", 8888, dt.date(2026, 6, 30), 0.99, s)
    s.commit()

    backfill_asset_fund_history(7272)

    otro = s.execute(sa.text(
        "SELECT fundamental_roic FROM ind_fundamental_quarterly "
        "WHERE asset_id = 8888")).fetchone()
    assert otro is not None and otro.fundamental_roic == 0.99
