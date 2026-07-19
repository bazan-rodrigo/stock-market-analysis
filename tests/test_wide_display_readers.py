"""Lectores de display/verificación sobre tablas anchas
(docs/notes/design_ind_wide_tables.md): con el flag on, la historia del
explorador de datos y el prefetch de la verificación deben IGNORAR las filas
donde la columna del código es NULL (fila que creó un código HERMANO de la
cadencia). Sin el filtro `col IS NOT NULL` esas filas NULL aparecían como
historia espuria en el explorador y como diferencias FALSAS en la verificación
de datos. En per-código el filtro es no-op (esas tablas no tienen filas NULL).
"""
import datetime as dt

import pytest
import sqlalchemy as sa

from app.database import engine, get_session
from app.models import indicator_store as _mod
from app.models.indicator_store import ensure_wide_ind_tables
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


def _seed_sibling_null(s):
    """rsi_daily con valor SOLO el 7; trend_daily con valor el 7 y el 8. La fila
    del 8 existe (la creó trend_daily) con rsi_daily NULL: es el caso que el
    filtro debe descartar para rsi_daily."""
    upsert_ind_cadence(s, "daily", ["rsi_daily", "trend_daily"],
                       [(1, _D1, 55.0, "bullish")])
    upsert_ind_cadence(s, "daily", ["trend_daily"],
                       [(1, _D2, "bearish")])
    s.commit()


def test_indicator_history_ignora_filas_null_de_hermanos(wide_tables, wide_on):
    from app.services.data_explorer_service import indicator_history
    _seed_sibling_null(get_session())

    name, names, records = indicator_history("rsi_daily", 1)
    assert name == "ind_rsi_daily"
    # el header de la columna de valor es el nombre del código en la ancha
    assert names == ["date", "rsi_daily"]
    # solo el 7: el 8 tiene rsi_daily NULL (fila de trend_daily), no es historia
    assert len(records) == 1
    assert records[0]["rsi_daily"] == 55.0

    # el hermano SÍ ve sus dos días
    _, _, rec_trend = indicator_history("trend_daily", 1)
    assert len(rec_trend) == 2


def test_prefetch_stored_ignora_filas_null_de_hermanos(wide_tables, wide_on):
    from app.services.verification_service import _prefetch_stored
    s = get_session()
    _seed_sibling_null(s)

    stored = _prefetch_stored(s, ["rsi_daily", "trend_daily"], [1])
    # rsi_daily: SOLO el 7 (sin la fila NULL del 8) → nada de diferencias falsas
    assert set(stored["rsi_daily"][1].keys()) == {_D1}
    assert stored["rsi_daily"][1][_D1] == 55.0
    # trend_daily: ambos días, con sus valores propios
    assert set(stored["trend_daily"][1].keys()) == {_D1, _D2}
    assert stored["trend_daily"][1][_D1] == "bullish"
    assert stored["trend_daily"][1][_D2] == "bearish"
