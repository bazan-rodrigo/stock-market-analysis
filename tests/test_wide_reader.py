"""Fase 3 de la tabla ancha por cadencia (docs/notes/design_ind_wide_tables.md):
el lector. Con el flag use_wide_ind_tables ON, get_ind_table devuelve un
_CodeView sobre ind_{cadencia} y query_values_asof lee la columna del código
con semántica as-of FIEL (salta NULLs, arrastra el último valor válido).

El flag default es OFF: en producción nada de esto se activa hasta el cutover.
"""
import datetime as dt

import pytest
import sqlalchemy as sa

from app.database import engine, get_session
from app.models import indicator_store as _mod
from app.models.indicator_store import (
    _CodeView, ensure_wide_ind_tables, get_ind_table, query_values_asof,
    use_wide_ind_tables,
)
from app.services.technical_service import upsert_ind_cadence

_D1 = dt.date(2026, 7, 7)
_D2 = dt.date(2026, 7, 8)


@pytest.fixture()
def wide_tables():
    ensure_wide_ind_tables(bind=engine)
    yield
    with engine.begin() as conn:
        for n in ("ind_daily", "ind_weekly", "ind_monthly"):
            conn.execute(sa.text(f"DROP TABLE IF EXISTS {n}"))
    for n in ("ind_daily", "ind_weekly", "ind_monthly"):
        if n in _mod._meta.tables:
            _mod._meta.remove(_mod._meta.tables[n])


@pytest.fixture()
def wide_on(monkeypatch):
    monkeypatch.setenv("USE_WIDE_IND_TABLES", "1")


def test_flag_default_off():
    assert use_wide_ind_tables() is False


def test_get_ind_table_devuelve_proxy_con_flag(wide_tables, wide_on):
    t = get_ind_table("rsi_daily")
    assert isinstance(t, _CodeView)
    assert t.name == "ind_daily"
    assert t.c.value.name == "rsi_daily"           # mapea a la columna del código
    assert [c.name for c in t.c] == ["asset_id", "date", "rsi_daily"]


def test_asof_sobre_ancha_es_fiel_por_columna(wide_tables, wide_on):
    s = get_session()
    # rsi_daily tiene valor el 7 y NULL el 8; trend_daily tiene valor ambos días
    upsert_ind_cadence(s, "daily", ["rsi_daily", "trend_daily"],
                       [(1, _D1, 55.0, "bullish")])
    upsert_ind_cadence(s, "daily", ["trend_daily"],
                       [(1, _D2, "bearish")])   # crea la fila del 8 con rsi NULL
    s.commit()

    # as-of del 8: la fila del 8 tiene rsi_daily NULL → arrastra el 55 del 7
    assert query_values_asof(s, "rsi_daily", _D2) == {1: 55.0}
    # trend_daily sí tiene valor propio el 8
    assert query_values_asof(s, "trend_daily", _D2) == {1: "bearish"}


def test_asof_sobre_ancha_respeta_cadencias_separadas(wide_tables, wide_on):
    s = get_session()
    upsert_ind_cadence(s, "weekly", ["rsi_weekly"], [(1, _D1, 40.0)])
    upsert_ind_cadence(s, "monthly", ["rsi_monthly"], [(1, _D1, 30.0)])
    s.commit()
    assert query_values_asof(s, "rsi_weekly", _D2) == {1: 40.0}
    assert query_values_asof(s, "rsi_monthly", _D2) == {1: 30.0}
