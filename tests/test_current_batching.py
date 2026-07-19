"""Fase de VIGENTES por lotes de activos (etapa 5 del ProcessPool): la unidad
pasó de "un código para todos los activos" a "un lote de activos para todos los
códigos", con cada lote cargando su propio slice de precios/caches (cierra el
techo de memoria del padre). Cubre:
  - _current_batch: partición independiente — un lote de N activos escribe los
    mismos valores vigentes que trocearlo (el cómputo es per-activo).
  - recompute_current_indicators: orquesta threads/procesos, agrega errores,
    escribe indicator_update_log; multi-lote (threads) ≡ procesos-inline.

Se escribe a current_indicator_values (no necesita tablas anchas). Todo corre
secuencial (_POOL_WORKERS=1) o inline: sqlite no habilita escritura concurrente.
"""
from datetime import date, timedelta

import pandas as pd
import pytest
import sqlalchemy as sa

import app.services.technical_service as ts
from app.database import Base, Session, engine, get_session


_A1, _A2, _A3, _A4 = 98811, 98812, 98813, 98814
_IDS = [_A1, _A2, _A3, _A4]


class _InlineExecutor:
    """Future ya resuelto + round-trip de pickle sobre el resultado: valida el
    camino de procesos salvo el spawn real (sqlite → sin spawn)."""
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def submit(self, fn, *args, **kw):
        import pickle
        from concurrent.futures import Future
        f = Future()
        try:
            out = fn(*args, **kw)
            f.set_result(pickle.loads(pickle.dumps(out)))
        except Exception as exc:
            f.set_exception(exc)
        return f


def _price_df(start: date, n: int, base: float) -> pd.DataFrame:
    rows = [(start + timedelta(days=i), base + i, base + i + 1, base + i - 1)
            for i in range(n)]
    return pd.DataFrame(rows, columns=["date", "close", "high", "low"])


def _seed(s, Asset, Price, ids, days=260):
    for k, aid in enumerate(ids):
        if s.get(Asset, aid) is None:
            s.add(Asset(id=aid, ticker=f"CB{aid}", name=f"CB{aid}", price_source_id=1))
        df = _price_df(date(2024, 1, 1), days, 100.0 * (k + 1))
        for _, r in df.iterrows():
            s.add(Price(asset_id=aid, date=r["date"], close=r["close"],
                        high=r["high"], low=r["low"]))
    s.commit()


def _snap(s, CIV):
    rows = s.execute(
        sa.select(CIV.asset_id, CIV.code, CIV.value_num, CIV.value_str)
          .where(CIV.asset_id.in_(_IDS))).fetchall()
    return sorted(map(tuple, rows))


def _wipe_current(CIV):
    s = get_session()
    s.query(CIV).filter(CIV.asset_id.in_(_IDS)).delete(synchronize_session=False)
    s.commit()
    Session.remove()


@pytest.fixture()
def _seeded():
    import app.models  # noqa: F401
    from app.models import Asset, IndicatorUpdateLog, Price
    from app.models import CurrentIndicatorValue as CIV
    Base.metadata.create_all(engine)
    s = get_session()
    _seed(s, Asset, Price, _IDS)
    yield CIV
    s = get_session()
    s.rollback()
    s.query(CIV).filter(CIV.asset_id.in_(_IDS)).delete(synchronize_session=False)
    s.query(IndicatorUpdateLog).filter(
        IndicatorUpdateLog.asset_id.in_(_IDS)).delete(synchronize_session=False)
    s.query(Price).filter(Price.asset_id.in_(_IDS)).delete(synchronize_session=False)
    s.query(Asset).filter(Asset.id.in_(_IDS)).delete(synchronize_session=False)
    s.commit()
    Session.remove()


_CODES = None   # se resuelve en cada test (frozenset ordenado)


def _codes():
    return sorted(ts._CURRENT_ONLY_CODES)


def test_current_batch_particion_independiente(_seeded):
    """_current_batch(TODOS) ≡ _current_batch(sub1) + _current_batch(sub2): el
    cómputo per-activo no depende del conjunto del lote."""
    CIV = _seeded
    codes = _codes()

    ts._current_batch(_IDS, codes)
    snap_a = _snap(get_session(), CIV)
    Session.remove()
    _wipe_current(CIV)

    ts._current_batch(_IDS[:2], codes)
    ts._current_batch(_IDS[2:], codes)
    snap_b = _snap(get_session(), CIV)
    Session.remove()

    assert snap_a, "se escribió al menos un valor vigente"
    assert snap_a == snap_b


def test_recompute_current_threads_cubre_y_loguea(_seeded, monkeypatch):
    """recompute_current_indicators (threads, varios lotes secuenciales) cubre
    todos los activos, escribe un registro por activo en indicator_update_log,
    y el progreso por-código llega al total."""
    from app.models import IndicatorUpdateLog
    CIV = _seeded
    monkeypatch.setattr(ts, "_MIN_BATCH_ASSETS", 1)   # varios lotes
    monkeypatch.setattr(ts, "_POOL_WORKERS", 1)        # un escritor secuencial (sqlite)

    labels: list = []
    res = ts.recompute_current_indicators(
        progress_cb=lambda c, t, l="": labels.append((c, t)),
        codes=_codes(), asset_ids=list(_IDS), weights={aid: 100 for aid in _IDS})

    assert res["total"] == len(_IDS)
    s = get_session()
    logged = {r[0] for r in s.query(IndicatorUpdateLog.asset_id)
                             .filter(IndicatorUpdateLog.asset_id.in_(_IDS)).all()}
    assert logged == set(_IDS)                          # log por cada activo
    assert s.query(CIV).filter(CIV.asset_id.in_(_IDS)).count() > 0
    assert labels and labels[-1][0] == labels[-1][1]    # progreso al total


def test_recompute_current_procesos_inline_equivale(_seeded, monkeypatch):
    """El camino de PROCESOS (executor inline) escribe exactamente lo mismo que
    el de threads."""
    import app.services.process_pool as pp
    CIV = _seeded
    codes = _codes()
    weights = {aid: 100 for aid in _IDS}
    monkeypatch.setattr(ts, "_MIN_BATCH_ASSETS", 1)
    monkeypatch.setattr(ts, "_POOL_WORKERS", 1)

    ts.recompute_current_indicators(codes=codes, asset_ids=list(_IDS), weights=weights)
    snap_threads = _snap(get_session(), CIV)
    Session.remove()
    _wipe_current(CIV)

    monkeypatch.setattr(ts, "_use_process_pool", lambda n: (True, 2))
    monkeypatch.setattr(pp, "make_executor", lambda *a, **k: _InlineExecutor())
    ts.recompute_current_indicators(codes=codes, asset_ids=list(_IDS), weights=weights)
    snap_procs = _snap(get_session(), CIV)
    Session.remove()

    assert snap_threads, "se escribió algo"
    assert snap_threads == snap_procs


def test_recompute_current_preloaded_equivale_a_selfload(_seeded, monkeypatch):
    """La rama THREADS con price_cache (deriva las caches UNA vez y las comparte
    por referencia) escribe lo mismo que la rama self-load (cada lote relee su
    slice). Blinda el fix de la relectura redundante."""
    CIV = _seeded
    codes = _codes()
    weights = {aid: 100 for aid in _IDS}
    monkeypatch.setattr(ts, "_MIN_BATCH_ASSETS", 1)
    monkeypatch.setattr(ts, "_POOL_WORKERS", 1)

    full = ts._load_prices_for_assets(get_session(), list(_IDS))
    ts.recompute_current_indicators(codes=codes, asset_ids=list(_IDS),
                                    weights=weights, price_cache=full)
    snap_pre = _snap(get_session(), CIV)
    Session.remove()
    _wipe_current(CIV)

    ts.recompute_current_indicators(codes=codes, asset_ids=list(_IDS), weights=weights)
    snap_self = _snap(get_session(), CIV)
    Session.remove()

    assert snap_pre, "se escribió algo"
    assert snap_pre == snap_self


def test_save_indicator_logs_bulk_insert_y_update(_seeded):
    """_save_indicator_logs_bulk: primera corrida INSERTa (con/sin error), la
    segunda UPDATEa el mismo registro (no duplica), en UN commit."""
    from app.models import IndicatorUpdateLog
    _CIV = _seeded  # noqa: F841 (el fixture crea los assets para el FK)
    s = get_session()
    ids = list(_IDS)

    ts._save_indicator_logs_bulk(ids, {ids[0]: ["boom", "bad"]}, s)
    rows = {r.asset_id: r for r in s.query(IndicatorUpdateLog)
            .filter(IndicatorUpdateLog.asset_id.in_(ids)).all()}
    assert set(rows) == set(ids)
    assert rows[ids[0]].success is False and "boom" in rows[ids[0]].error_detail
    assert rows[ids[1]].success is True and rows[ids[1]].error_detail is None

    # segunda corrida: ahora ids[1] falla y ids[0] sale limpio → UPDATE
    ts._save_indicator_logs_bulk(ids, {ids[1]: ["oops"]}, s)
    s.expire_all()
    rows2 = {r.asset_id: r for r in s.query(IndicatorUpdateLog)
             .filter(IndicatorUpdateLog.asset_id.in_(ids)).all()}
    assert len(rows2) == len(ids)                    # no duplicó (UPDATE, no INSERT)
    assert rows2[ids[0]].success is True and rows2[ids[0]].error_detail is None
    assert rows2[ids[1]].success is False and "oops" in rows2[ids[1]].error_detail
    Session.remove()


def test_recompute_current_universo_vacio():
    Base.metadata.create_all(engine)
    Session.remove()
    res = ts.recompute_current_indicators(
        codes=_codes(), asset_ids=[], weights={})
    assert res == {"total": 0, "success": 0, "errors": []}


def test_recompute_current_lote_muerto_marca_error(_seeded, monkeypatch):
    """Un lote que CRASHEA (BrokenProcessPool → _on_dead) deja a SUS activos con
    IndicatorUpdateLog.success=False (no darlos por actualizados) y los saca en
    res["errors"] con su ticker; los activos de lotes sanos quedan success=True.

    _current_batch normalmente atrapa todo y devuelve asset_errors; se
    monkeypatchea para LANZAR en un lote (simula el crash duro del hijo) y
    devolver limpio en los demás → aísla _on_dead + el mapeo del log/ticker sin
    depender del pipeline completo sobre sqlite."""
    from app.models import IndicatorUpdateLog
    CIV = _seeded  # noqa: F841
    monkeypatch.setattr(ts, "_MIN_BATCH_ASSETS", 1)   # un lote por activo
    monkeypatch.setattr(ts, "_POOL_WORKERS", 1)        # escritor secuencial (sqlite)

    _BAD = _A2

    def _flaky(batch, codes, preloaded=None):
        if _BAD in batch:
            raise RuntimeError("hijo muerto (BrokenProcessPool)")
        return {"asset_errors": {}}                    # lote sano

    monkeypatch.setattr(ts, "_current_batch", _flaky)

    res = ts.recompute_current_indicators(
        codes=_codes(), asset_ids=list(_IDS), weights={aid: 100 for aid in _IDS})

    s = get_session()
    logs = {r.asset_id: r for r in s.query(IndicatorUpdateLog)
            .filter(IndicatorUpdateLog.asset_id.in_(_IDS)).all()}
    assert set(logs) == set(_IDS)                       # log por cada activo
    assert logs[_BAD].success is False                  # el lote muerto NO se da por hecho
    for aid in set(_IDS) - {_BAD}:
        assert logs[aid].success is True                # los sanos, actualizados

    err_tickers = {e["ticker"] for e in res["errors"]}
    assert f"CB{_BAD}" in err_tickers                   # sale en errors con su ticker
    assert len(res["errors"]) == 1
    assert res["total"] == len(_IDS)
    assert res["success"] == len(_IDS) - len(res["errors"])
    Session.remove()
