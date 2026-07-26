"""Bitácora persistida de corridas (run_history_service): apertura/cierre de
una corrida, marca 'aborted' de las huérfanas al arranque (M2), poda por
retención y fail-open sin la tabla. Lógica pura sobre el stub sqlite."""
from datetime import timedelta

import pytest
import sqlalchemy as sa

import app.models  # noqa: F401 — registra RunHistory
from app.database import Base, Session, engine, get_session
from app.models.run_history import RunHistory
from app.services import run_history_service as rh


@pytest.fixture(autouse=True)
def _clean_run_history():
    Base.metadata.create_all(engine)
    rh._unavailable = False          # el latch es global de módulo; aislar tests
    s = get_session()
    s.execute(sa.delete(RunHistory))
    s.commit()
    yield
    try:
        s.execute(sa.delete(RunHistory))
        s.commit()
    except Exception:
        s.rollback()                 # el test de fail-open dropea la tabla
    rh._unavailable = False
    Session.remove()


def _add(op, status, started_at=None, **kw):
    s = get_session()
    row = RunHistory(op=op, status=status,
                     started_at=started_at or rh._utcnow(), **kw)
    s.add(row)
    s.commit()
    return row.id


def _status(run_id):
    return get_session().get(RunHistory, run_id).status


def test_start_run_abre_running():
    rid = rh.start_run("indicators", scope="rebuild_all")
    assert rid is not None
    row = get_session().get(RunHistory, rid)
    assert row.status == "running"
    assert row.finished_at is None
    assert row.op == "indicators" and row.scope == "rebuild_all"
    assert row.pid  # se registró quién la corrió


def test_finish_run_cierra_con_ok_y_conteos():
    rid = rh.start_run("signals")
    rh.finish_run(rid, "ok", total=120, unit="fechas", ok=118,
                  first_error=None)
    row = get_session().get(RunHistory, rid)
    assert row.status == "ok"
    assert row.finished_at is not None
    assert (row.total, row.unit, row.ok) == (120, "fechas", 118)


def test_finish_run_con_none_es_noop():
    # start_run pudo no abrir la fila (bitácora no disponible): finish no rompe
    rh.finish_run(None, "ok")
    assert get_session().query(RunHistory).count() == 0


def test_abort_orphans_solo_toca_las_running():
    r_run = _add("prices", "running")
    r_ok  = _add("fund", "ok")
    r_err = _add("snap", "error")

    n = rh.abort_orphans()

    assert n == 1
    assert _status(r_run) == "aborted"
    assert _status(r_ok)  == "ok"       # un final limpio no se toca
    assert _status(r_err) == "error"
    # y le puso finished_at a la que abortó
    assert get_session().get(RunHistory, r_run).finished_at is not None


def test_prune_old_borra_por_antiguedad():
    old    = _add("daily", "ok", started_at=rh._utcnow() - timedelta(days=200))
    recent = _add("daily", "ok", started_at=rh._utcnow() - timedelta(days=10))

    n = rh.prune_old(retention_days=180)

    assert n == 1
    ids = {r.id for r in get_session().query(RunHistory).all()}
    assert ids == {recent}
    assert old not in ids


def test_get_recent_mas_nueva_primero_y_limita():
    now = rh._utcnow()
    for i in range(5):
        _add(f"op{i}", "ok", started_at=now - timedelta(minutes=i))
    recent = rh.get_recent(limit=3)
    assert [r["op"] for r in recent] == ["op0", "op1", "op2"]   # descendente
    assert all(isinstance(r, dict) for r in recent)             # filas planas


def test_fail_open_sin_tabla():
    # Sin la tabla (pre-migración): todo devuelve neutro y se latchea, no rompe.
    RunHistory.__table__.drop(engine)
    get_session().rollback()

    assert rh.start_run("prices") is None
    assert rh._unavailable is True
    assert rh.get_recent() == []
    assert rh.abort_orphans() == 0
    assert rh.prune_old() == 0
    rh.finish_run(123, "ok")           # no levanta

    Base.metadata.create_all(engine)   # restaurar para el teardown
