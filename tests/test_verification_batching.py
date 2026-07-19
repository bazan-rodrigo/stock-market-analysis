"""Verificación por LOTES de activos (etapa 5 del ProcessPool): la unidad
de trabajo pasó de "un activo" a "un lote", reusando el harness de
indicadores (threads o procesos). Cubre:
  - _run_batched: cobertura de todos los activos, progreso, y equivalencia
    threads ≡ procesos-inline (sin levantar spawn real).
  - _verify_batch: idéntico a llamar _verify_one_asset por activo suelto
    (la sesión compartida del lote no cambia el resultado).
"""
import datetime as dt

import pytest
import sqlalchemy as sa

import app.services.technical_service as ts
import app.services.verification_service as vs
from app.database import Base, Session, engine, get_session
from app.models import indicator_store as _ind_mod
from app.models.indicator_store import ensure_wide_ind_tables


# ── _run_batched: orquestación (mock del batch_fn, sin datos reales) ──────────

class _InlineExecutor:
    """Executor fake: corre la task del 'hijo' en el mismo proceso (Future ya
    resuelto). Valida el camino de procesos salvo el spawn real."""
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def submit(self, fn, *args, **kw):
        from concurrent.futures import Future
        f = Future()
        try:
            f.set_result(fn(*args, **kw))
        except Exception as exc:
            f.set_exception(exc)
        return f


def _fake_batch(batch_asset_ids, ticker_map, codes):
    """Un 'diff' por activo del lote — para verificar cobertura y agregación."""
    return {
        "results": [
            {"code": codes[0], "asset_id": aid, "ticker": ticker_map.get(aid, "?"),
             "diffs": [(None, "motivo", "g", "f", "calc")]}
            for aid in batch_asset_ids
        ],
        "n_assets": len(batch_asset_ids),
    }


def test_run_batched_threads_cubre_todos_los_activos_una_vez(monkeypatch):
    monkeypatch.setattr(ts, "_MIN_BATCH_ASSETS", 1)   # forzar varios lotes
    asset_ids = list(range(1, 12))
    codes = ["rsi_daily"]
    labels = []
    res = vs._run_batched(
        asset_ids, codes, {aid: f"T{aid}" for aid in asset_ids},
        _fake_batch, lambda c, t, l="": labels.append(c),
        len(codes) * len(asset_ids))
    assert sorted(r["asset_id"] for r in res) == asset_ids   # todos, una vez
    assert max(labels) == len(asset_ids)                     # progreso al total


def test_run_batched_procesos_inline_equivale_a_threads(monkeypatch):
    import app.services.process_pool as pp
    monkeypatch.setattr(ts, "_MIN_BATCH_ASSETS", 1)
    asset_ids = list(range(1, 10))
    codes = ["rsi_daily"]
    tm = {aid: f"T{aid}" for aid in asset_ids}
    tw = len(codes) * len(asset_ids)

    res_threads = vs._run_batched(asset_ids, codes, tm, _fake_batch, None, tw)

    # camino de PROCESOS con executor inline (sqlite → sin spawn real)
    monkeypatch.setattr(vs, "_use_process_pool", lambda n: (True, 2))
    monkeypatch.setattr(pp, "make_executor", lambda *a, **k: _InlineExecutor())
    res_procs = vs._run_batched(asset_ids, codes, tm, _fake_batch, None, tw)

    assert sorted(r["asset_id"] for r in res_threads) == asset_ids
    assert sorted(r["asset_id"] for r in res_procs) == asset_ids


def test_run_batched_universo_vacio():
    assert vs._run_batched([], ["rsi_daily"], {}, _fake_batch, None, 0) == []


# ── _verify_batch: equivalente a verificar por-activo (datos sembrados) ───────

@pytest.fixture()
def _wide():
    ensure_wide_ind_tables(bind=engine)
    yield
    with engine.begin() as conn:
        for n in ("ind_daily", "ind_weekly", "ind_monthly"):
            conn.execute(sa.text(f"DROP TABLE IF EXISTS {n}"))
    for n in ("ind_daily", "ind_weekly", "ind_monthly"):
        if n in _ind_mod._meta.tables:
            _ind_mod._meta.remove(_ind_mod._meta.tables[n])


_A1, _A2 = 88801, 88802


def _seed_prices(s, Asset, Price, ids, days=40):
    for k, aid in enumerate(ids):
        if s.get(Asset, aid) is None:
            s.add(Asset(id=aid, ticker=f"VB{aid}", name=f"VB{aid}", price_source_id=1))
        base = 100.0 * (k + 1)
        for i in range(days):
            s.add(Price(asset_id=aid, date=dt.date(2026, 1, 1) + dt.timedelta(days=i),
                        close=base + i, high=base + i + 1, low=base + i - 1))
    s.commit()


def test_verify_batch_equivale_a_por_activo(_wide, monkeypatch):
    import app.models  # noqa: F401
    from app.models import Asset, Price
    monkeypatch.setenv("USE_WIDE_IND_TABLES", "1")

    Base.metadata.create_all(engine)
    s = get_session()
    ids = [_A1, _A2]
    codes = ["return_daily", "rsi_daily"]
    try:
        _seed_prices(s, Asset, Price, ids)
        tm = {_A1: "VB1", _A2: "VB2"}

        # camino nuevo: un lote con los dos activos (sesión compartida)
        batch = vs._verify_batch(ids, tm, codes)

        # referencia: por-activo suelto (cada uno su propia sesión)
        s2 = get_session()
        regime = ts._get_regime_config()
        vol = ts._get_volatility_config()
        stored = vs._prefetch_stored(s2, codes, ids)
        ref = []
        for aid in ids:
            ref.extend(vs._verify_one_asset(aid, tm[aid], codes, regime, vol, stored))

        def _key(rows):
            return sorted((r["asset_id"], r["code"], tuple(r["diffs"])) for r in rows)

        assert batch["n_assets"] == 2
        assert _key(batch["results"]) == _key(ref)
        assert batch["results"]   # hay diferencias (fresco presente, nada guardado)
    finally:
        s.rollback()
        s.query(Price).filter(Price.asset_id.in_(ids)).delete(synchronize_session=False)
        s.query(Asset).filter(Asset.id.in_(ids)).delete(synchronize_session=False)
        s.commit()
        Session.remove()
