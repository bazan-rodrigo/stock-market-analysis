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


# trend_* guarda texto; el resto numerico (mismo criterio que ensure_ind_table)
_WIDE_TYPE = {"trend_daily": "str", "trend_weekly": "str", "trend_monthly": "str",
              "volatility_daily": "str", "volatility_weekly": "str",
              "volatility_monthly": "str"}


def _seed_asset_para_backfill(s, asset_id, codes, n_barras=300):
    """Activo con precios + definiciones keep_history, lo mínimo que
    backfill_asset_history necesita."""
    from app.database import Base
    import app.models  # noqa: F401 — registra los modelos en Base.metadata
    from app.models import Asset, IndicatorDefinition, Price
    from app.models.price_source import PriceSource
    import math
    Base.metadata.create_all(engine)   # el fixture wide_ solo crea las anchas
    if s.get(PriceSource, 1) is None:
        s.add(PriceSource(id=1, name="test"))
        s.flush()
    s.add(Asset(id=asset_id, ticker=f"BF{asset_id}", price_source_id=1))
    d0 = dt.date(2020, 1, 1)
    for i in range(n_barras):
        c = 100 + 10 * math.sin(i / 20) + i * 0.05
        s.add(Price(asset_id=asset_id, date=d0 + dt.timedelta(days=i),
                    close=c, high=c + 1, low=c - 1))
    for code in codes:
        # idempotente: las definiciones sobreviven entre tests (el fixture
        # solo dropea las tablas anchas, no el esquema base)
        if not s.query(IndicatorDefinition).filter(
                IndicatorDefinition.code == code).first():
            s.add(IndicatorDefinition(code=code, name=code, category="test",
                                      type=_WIDE_TYPE.get(code, "num"),
                                      keep_history=True))
    s.commit()


def _daily_codes_con_backfill():
    from app.services.technical_service import _BACKFILL_FNS
    from app.models.indicator_store import _WIDE
    return [c for c, (_t, _col, _cad) in _WIDE.items() if c in _BACKFILL_FNS]


def test_backfill_asset_history_es_idempotente_y_no_pierde_datos(wide_tables,
                                                                 wide_on):
    """backfill_asset_history vacía la cadencia de una vez (en vez de nullear
    columna por columna) y bufferiza las escrituras. Si ese borrado no
    reescribiera todo, la SEGUNDA corrida dejaría la fila vacía.

    Es el riesgo concreto del cambio: borra filas. Sin este test, una
    regresión ahí se lleva la historia de indicadores del activo en silencio.
    """
    from app.services.technical_service import backfill_asset_history

    s = get_session()
    codes = _daily_codes_con_backfill()          # cubre las 3 cadencias enteras
    _seed_asset_para_backfill(s, 4242, codes)

    r1 = backfill_asset_history(4242)
    assert r1["inserted"] > 0
    filas1 = s.execute(sa.text(
        "SELECT COUNT(*) FROM ind_daily WHERE asset_id = 4242")).scalar()
    vals1 = s.execute(sa.text(
        "SELECT date, return_daily FROM ind_daily WHERE asset_id = 4242 "
        "AND return_daily IS NOT NULL ORDER BY date")).fetchall()
    assert filas1 > 0 and len(vals1) > 0

    # segunda corrida: mismo resultado, sin perder nada
    r2 = backfill_asset_history(4242)
    filas2 = s.execute(sa.text(
        "SELECT COUNT(*) FROM ind_daily WHERE asset_id = 4242")).scalar()
    vals2 = s.execute(sa.text(
        "SELECT date, return_daily FROM ind_daily WHERE asset_id = 4242 "
        "AND return_daily IS NOT NULL ORDER BY date")).fetchall()

    assert r2["inserted"] == r1["inserted"]
    assert filas2 == filas1
    assert vals2 == vals1        # los valores sobreviven al borrado+reescritura


def test_backfill_asset_history_no_toca_otros_activos(wide_tables, wide_on):
    """El DELETE por cadencia debe acotarse al activo: si se llevara puestas
    las filas de los demás, sería una pérdida masiva y silenciosa."""
    from app.services.technical_service import backfill_asset_history

    s = get_session()
    codes = _daily_codes_con_backfill()
    _seed_asset_para_backfill(s, 5151, codes)
    # otro activo con una fila ya guardada en la misma tabla ancha
    _write_ind_series(s, "rsi_daily", 9999, [_D1], [42.0], existing=set())
    s.commit()

    backfill_asset_history(5151)

    otro = s.execute(sa.text(
        "SELECT rsi_daily FROM ind_daily WHERE asset_id = 9999")).fetchone()
    assert otro is not None and otro.rsi_daily == 42.0


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
