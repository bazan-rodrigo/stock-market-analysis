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
