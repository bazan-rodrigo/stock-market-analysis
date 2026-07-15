"""delete_by_ranges (convención de DELETE masivo por ventanas) + mecánica del
escritor asíncrono del backfill (_consume_writes): orden FIFO, sentinel, y
drenado tras error para no dejar bloqueado al productor.
"""
import queue

import pytest
import sqlalchemy as sa

from app.database import Base, engine, get_session
from app.services.db_utils import delete_by_ranges
from app.services.signal_backfill_range import _consume_writes


# ── delete_in_batches (camino sqlite: una sola sentencia) ────────────────────

@pytest.fixture()
def sv_db():
    import app.models  # noqa: F401
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM signal_value"))
    yield
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM signal_value"))
    get_session().rollback()


def test_delete_by_ranges_borra_por_ventanas_y_respeta_filtro(sv_db):
    s = get_session()
    for i in range(10):
        s.execute(sa.text(
            "INSERT INTO signal_value (signal_id, asset_id, date, score) "
            "VALUES (:sig, 1, :d, 0)"),
            {"sig": 1 if i < 7 else 2, "d": f"2026-01-{i + 1:02d}"})
    s.commit()
    # dos ventanas que juntas cubren 01..06; señal 2 queda intacta aunque
    # sus fechas caigan dentro (where_extra)
    n = delete_by_ranges(s, "signal_value", "date",
                         [("2026-01-01", "2026-01-03"),
                          ("2026-01-04", "2026-01-06")],
                         "signal_id IN (1)")
    assert n == 6
    left = [r[0] for r in s.execute(sa.text(
        "SELECT date FROM signal_value ORDER BY date")).all()]
    assert left == ["2026-01-07", "2026-01-08", "2026-01-09", "2026-01-10"]


# ── _consume_writes ───────────────────────────────────────────────────────────

def test_consume_writes_orden_fifo_y_sentinel():
    q = queue.Queue()
    seen, errs = [], []
    for i in range(3):
        q.put(([i], f"lote{i}"))
    q.put(None)
    _consume_writes(q, lambda dates, tag: seen.append((dates[0], tag)), errs)
    assert seen == [(0, "lote0"), (1, "lote1"), (2, "lote2")]
    assert errs == []


def test_consume_writes_error_drena_sin_escribir_mas():
    q = queue.Queue()
    seen, errs = [], []

    def flush(dates, _tag):
        if dates[0] == 1:
            raise RuntimeError("boom")
        seen.append(dates[0])

    for i in range(4):
        q.put(([i], "x"))
    q.put(None)
    _consume_writes(q, flush, errs)
    assert seen == [0]                      # el lote 1 falló; 2 y 3 drenados
    assert len(errs) == 1 and "boom" in str(errs[0])
    assert q.empty()                        # la cola quedó vacía (productor libre)