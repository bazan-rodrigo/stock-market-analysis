"""Fase 4 (cutover) de la tabla ancha por cadencia: el camino de ESCRITURA
gateado por el flag. Con el flag ON, los dos chokepoints (_upsert_ind y
_write_ind_series) escriben en la columna de la tabla ancha; los "borrados"
(existing=None / stale) nullean la columna en vez de borrar la fila (que
comparten otros códigos). Con el flag OFF nada de esto se activa.
"""
import datetime as dt

import pytest
import sqlalchemy as sa

from app.database import engine, get_session
from app.models import indicator_store as _mod
from app.models.indicator_store import ensure_wide_ind_tables
from app.services.technical_service import (
    _null_wide_column, _upsert_ind, _write_ind_series,
)

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


def test_upsert_ind_rutea_a_columna_ancha(wide_tables, wide_on):
    s = get_session()
    _upsert_ind(s, "rsi_daily", 1, _D1, 55.0)
    _upsert_ind(s, "trend_daily", 1, _D1, "bullish")  # str va a su columna
    s.commit()
    row = s.execute(sa.text(
        "SELECT rsi_daily, trend_daily FROM ind_daily WHERE asset_id = 1"
    )).fetchone()
    assert row.rsi_daily == 55.0
    assert row.trend_daily == "bullish"


def test_upsert_ind_ignora_nan(wide_tables, wide_on):
    s = get_session()
    _upsert_ind(s, "rsi_daily", 1, _D1, float("nan"))
    s.commit()
    assert s.execute(sa.text("SELECT COUNT(*) FROM ind_daily")).scalar() == 0


def test_write_ind_series_escribe_columna(wide_tables, wide_on):
    s = get_session()
    n = _write_ind_series(s, "rsi_daily", 1, [_D1, _D2], [55.0, 60.0],
                          existing=None)
    s.commit()
    assert n == 2
    vals = [r.rsi_daily for r in s.execute(sa.text(
        "SELECT rsi_daily FROM ind_daily WHERE asset_id = 1 ORDER BY date"))]
    assert vals == [55.0, 60.0]


def test_write_ind_series_stale_nullea_solo_su_columna(wide_tables, wide_on):
    s = get_session()
    _write_ind_series(s, "rsi_daily", 1, [_D1, _D2], [55.0, 60.0], existing=None)
    _write_ind_series(s, "trend_daily", 1, [_D1, _D2], ["a", "b"], existing=None)
    s.commit()
    # rsi_daily del D2 pasa a NaN => stale => nullea SOLO rsi_daily del D2
    _write_ind_series(s, "rsi_daily", 1, [_D1, _D2], [55.0, float("nan")],
                      existing={_D1: 55.0, _D2: 60.0})
    s.commit()
    # ORDER BY date => [D1, D2] (posicional: sqlite devuelve date como str)
    rows = s.execute(sa.text(
        "SELECT rsi_daily, trend_daily FROM ind_daily WHERE asset_id = 1 "
        "ORDER BY date")).fetchall()
    assert rows[0].rsi_daily == 55.0    # D1 intacto
    assert rows[1].rsi_daily is None    # rsi_daily del D2 nulleado
    assert rows[1].trend_daily == "b"   # trend_daily del D2 NO se pisó


def test_buffer_rebuild_escribe_fila_completa_una_vez(wide_tables, wide_on):
    """Opción B (sin bloat): con el buffer activo (rebuild), _write_ind_series
    acumula por código; el flush escribe UNA fila completa por (activo,fecha)
    con todas las columnas — sin updates repetidos."""
    from app.services.technical_service import (
        _wide_buffer_clear, _wide_buffer_flush, _wide_buffer_start,
    )
    s = get_session()
    _wide_buffer_start()
    try:
        n1 = _write_ind_series(s, "rsi_daily", 1, [_D1, _D2], [55.0, 60.0],
                               existing=set())
        n2 = _write_ind_series(s, "trend_daily", 1, [_D1, _D2], ["a", "b"],
                               existing=set())
        assert n1 == 2 and n2 == 2
        # nada escrito todavía: está en el buffer
        assert s.execute(sa.text("SELECT COUNT(*) FROM ind_daily")).scalar() == 0
        _wide_buffer_flush(s)
        s.commit()
    finally:
        _wide_buffer_clear()

    # una fila por (activo,fecha), con AMBAS columnas (rsi + trend)
    rows = s.execute(sa.text(
        "SELECT rsi_daily, trend_daily FROM ind_daily WHERE asset_id = 1 "
        "ORDER BY date")).fetchall()
    assert [(r.rsi_daily, r.trend_daily) for r in rows] == [(55.0, "a"), (60.0, "b")]


def test_buffer_no_pisa_con_null_las_columnas_que_no_trae(wide_tables, wide_on):
    """El buffer tambien se usa en DELTA, donde la fila YA existe y solo se
    reescribe la cola de algunos codigos. El flush debe tocar unicamente las
    columnas que trae: si volcara todas las de la cadencia con None en las
    ausentes, borraria los valores guardados por los otros codigos.

    Es el riesgo concreto que habilita bufferizar el delta — sin este
    agrupado, activar el buffer fuera del rebuild destruye datos."""
    from app.services.technical_service import (
        _wide_buffer_clear, _wide_buffer_flush, _wide_buffer_start,
    )
    s = get_session()
    # estado previo: la fila ya tiene rsi_daily Y trend_daily guardados
    _write_ind_series(s, "rsi_daily", 7, [_D1], [10.0], existing=set())
    _write_ind_series(s, "trend_daily", 7, [_D1], ["alta"], existing=set())
    s.commit()

    # delta: solo rsi_daily recalcula esa fecha; trend_daily no entra al buffer
    _wide_buffer_start()
    try:
        _write_ind_series(s, "rsi_daily", 7, [_D1], [99.0], existing=set())
        _wide_buffer_flush(s)
        s.commit()
    finally:
        _wide_buffer_clear()

    row = s.execute(sa.text(
        "SELECT rsi_daily, trend_daily FROM ind_daily "
        "WHERE asset_id = 7")).fetchone()
    assert row.rsi_daily == 99.0        # se actualizo
    assert row.trend_daily == "alta"    # NO se piso con NULL


def test_null_wide_column_acota_por_activo(wide_tables, wide_on):
    s = get_session()
    _upsert_ind(s, "rsi_weekly", 1, _D1, 40.0)
    _upsert_ind(s, "rsi_weekly", 2, _D1, 41.0)
    s.commit()
    _null_wide_column(s, "weekly", "rsi_weekly", asset_id=1)
    s.commit()
    rows = {r.asset_id: r.rsi_weekly for r in s.execute(sa.text(
        "SELECT asset_id, rsi_weekly FROM ind_weekly"))}
    assert rows[1] is None
    assert rows[2] == 41.0
