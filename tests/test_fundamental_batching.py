"""Backfill fundamental por LOTES de activos (etapa 5 del ProcessPool): la
unidad de trabajo pasó de "un código para todos los activos" a "un lote de
activos para todos los códigos", reusando el harness de indicadores (threads o
procesos). Cubre:
  - _backfill_fund_batch: partición independiente — un lote de N activos escribe
    exactamente las mismas filas que trocearlo en sub-lotes (la lógica delta/
    wide/narrow por-activo queda intacta al escoparla a un subconjunto).
  - backfill_all_fundamental_values: el padre particiona, hoistea el TRUNCATE del
    rebuild y agrega; cobertura de todos los activos por el camino de procesos
    (executor inline, sin spawn real) == referencia de un solo lote.

Todo corre en el thread principal (executor inline): el stub sqlite no habilita
escritura concurrente multi-thread, igual que test_verification_batching.py.
"""
import datetime as dt

import pytest
import sqlalchemy as sa

import app.services.fundamental_service as fs
import app.services.technical_service as ts
from app.database import Base, Session, engine, get_session
from app.models import indicator_store as _ind_mod
from app.models.indicator_store import (_WIDE_CADENCE_COLUMNS,
                                         _WIDE_CADENCE_TABLE,
                                         ensure_wide_ind_tables)


# ── executor inline: corre la task del 'hijo' en el mismo proceso ─────────────

class _InlineExecutor:
    """Future ya resuelto: valida el camino de procesos salvo el spawn real."""
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


# ── fixture: tablas anchas + limpieza ─────────────────────────────────────────

@pytest.fixture()
def _wide():
    ensure_wide_ind_tables(bind=engine)
    yield
    names = ("ind_daily", "ind_weekly", "ind_monthly",
             "ind_fundamental_daily", "ind_fundamental_quarterly")
    with engine.begin() as conn:
        for n in names:
            conn.execute(sa.text(f"DROP TABLE IF EXISTS {n}"))
    for n in names:
        if n in _ind_mod._meta.tables:
            _ind_mod._meta.remove(_ind_mod._meta.tables[n])


# ── siembra ───────────────────────────────────────────────────────────────────

def _seed_fund(s, Asset, Price, ids, n_quarters=8, n_days=420):
    """Activos con historia trimestral (financieros válidos) + precios diarios,
    suficiente para que salgan ratios trimestrales y diarios no nulos."""
    from app.models import FundamentalQuarterly
    qdates = [dt.date(2023, 3, 31) + dt.timedelta(days=91 * k)
              for k in range(n_quarters)]
    pstart = dt.date(2023, 4, 1)
    for k, aid in enumerate(ids):
        if s.get(Asset, aid) is None:
            s.add(Asset(id=aid, ticker=f"FB{aid}", name=f"FB{aid}", price_source_id=1))
        for j, qd in enumerate(qdates):
            s.add(FundamentalQuarterly(
                asset_id=aid, period_date=qd,
                revenue=1000 + 10 * j, gross_profit=400 + 4 * j,
                operating_income=200 + 2 * j, net_income=100 + j,
                ebitda=250 + 2 * j, total_debt=250, equity=500 + 5 * j,
                shares=10, fcf=50, operating_cf=80,
                eps_actual=10 + 0.1 * j, eps_estimated=9,
                nopat=150 + j, invested_capital_avg=1000,
            ))
        base = 50.0 * (k + 1)
        for i in range(n_days):
            s.add(Price(asset_id=aid, date=pstart + dt.timedelta(days=i),
                        close=base + i * 0.1,
                        high=base + i * 0.1 + 1, low=base + i * 0.1 - 1))
    s.commit()


def _snapshot(s):
    """Filas escritas en las dos tablas anchas de fundamentales, como sets de
    tuplas (sin timestamps → comparables entre corridas)."""
    out = {}
    for cad in ("fund_quarterly", "fund_daily"):
        cols = ["asset_id", "date"] + _WIDE_CADENCE_COLUMNS[cad]
        rows = s.execute(sa.text(
            f"SELECT {', '.join(cols)} FROM {_WIDE_CADENCE_TABLE[cad]}"
            f" ORDER BY asset_id, date")).fetchall()
        out[cad] = frozenset(tuple(r) for r in rows)
    return out


_IDS = [771001, 771002, 771003, 771004]


@pytest.fixture()
def _seeded(_wide, monkeypatch):
    import app.models  # noqa: F401
    from app.models import Asset, FundamentalQuarterly, Price
    monkeypatch.setenv("USE_WIDE_IND_TABLES", "1")
    Base.metadata.create_all(engine)
    s = get_session()
    _seed_fund(s, Asset, Price, _IDS)
    yield s
    s.rollback()
    s.query(FundamentalQuarterly).filter(
        FundamentalQuarterly.asset_id.in_(_IDS)).delete(synchronize_session=False)
    s.query(Price).filter(Price.asset_id.in_(_IDS)).delete(synchronize_session=False)
    s.query(Asset).filter(Asset.id.in_(_IDS)).delete(synchronize_session=False)
    s.commit()
    Session.remove()


# ── tests ──────────────────────────────────────────────────────────────────────

def test_backfill_fund_batch_particion_independiente(_seeded):
    """batch(TODOS) ≡ batch(sub1) + batch(sub2): escopar el lote a un
    subconjunto de activos no cambia lo que se escribe por activo."""
    qcodes = sorted(fs._FUND_QUARTERLY_CODES)
    dcodes = sorted(fs._FUND_DAILY_CODES)
    s = _seeded

    # Path A: un solo lote con los 4 activos
    fs._fund_force_reset(s, qcodes, dcodes)
    Session.remove()
    ra = fs._backfill_fund_batch(_IDS, qcodes, dcodes, force=True)
    snap_a = _snapshot(get_session())

    # Path B: dos sub-lotes disjuntos
    s = get_session()
    fs._fund_force_reset(s, qcodes, dcodes)
    Session.remove()
    rb1 = fs._backfill_fund_batch(_IDS[:1], qcodes, dcodes, force=True)
    rb2 = fs._backfill_fund_batch(_IDS[1:], qcodes, dcodes, force=True)
    snap_b = _snapshot(get_session())

    assert ra["errors"] == [] and rb1["errors"] == [] and rb2["errors"] == []
    assert snap_a["fund_quarterly"]           # algo se escribió
    assert snap_a["fund_daily"]
    assert snap_a == snap_b                    # partición independiente
    assert ra["inserted"] == rb1["inserted"] + rb2["inserted"]


def test_backfill_fund_batch_delta_rellena_huecos(_seeded):
    """El camino DELTA (force=False) rellena huecos reales: build completo →
    borrar un activo entero + un rango medio de otro → el delta reconstruye
    EXACTAMENTE lo borrado (target = fechas faltantes + última preliminar) y no
    toca el resto."""
    qcodes = sorted(fs._FUND_QUARTERLY_CODES)
    dcodes = sorted(fs._FUND_DAILY_CODES)
    s = _seeded

    # 1) build completo (rebuild)
    fs._fund_force_reset(s, qcodes, dcodes)
    Session.remove()
    fs._backfill_fund_batch(_IDS, qcodes, dcodes, force=True)
    full = _snapshot(get_session())
    assert full["fund_quarterly"] and full["fund_daily"]

    # 2) crear huecos: un activo entero + una ventana media de otro
    s = get_session()
    for tbl in ("ind_fundamental_quarterly", "ind_fundamental_daily"):
        s.execute(sa.text(f"DELETE FROM {tbl} WHERE asset_id = :a"), {"a": _IDS[1]})
        s.execute(sa.text(
            f"DELETE FROM {tbl} WHERE asset_id = :a AND date >= :d1 AND date < :d2"),
            {"a": _IDS[2], "d1": "2023-08-01", "d2": "2024-01-01"})
    s.commit()
    partial = _snapshot(s)
    assert partial != full                     # efectivamente hay huecos
    assert partial["fund_daily"] < full["fund_daily"]
    Session.remove()

    # 3) delta: reconstruye lo borrado sin cambiar lo demás
    res = fs._backfill_fund_batch(_IDS, qcodes, dcodes, force=False)
    healed = _snapshot(get_session())
    assert res["errors"] == []
    assert healed == full                       # delta == estado completo


def test_backfill_all_inline_cubre_todos_y_equivale(_seeded, monkeypatch):
    """backfill_all_fundamental_values por el camino de PROCESOS (executor
    inline, varios lotes) cubre todos los activos y coincide con un solo lote."""
    import app.services.process_pool as pp
    qcodes = sorted(fs._FUND_QUARTERLY_CODES)
    dcodes = sorted(fs._FUND_DAILY_CODES)
    s = _seeded

    # referencia: un único lote a mano
    fs._fund_force_reset(s, qcodes, dcodes)
    Session.remove()
    fs._backfill_fund_batch(_IDS, qcodes, dcodes, force=True)
    ref = _snapshot(get_session())
    Session.remove()

    # camino real del padre, forzado a procesos-inline con varios lotes
    monkeypatch.setattr(ts, "_MIN_BATCH_ASSETS", 1)
    monkeypatch.setattr(ts, "_use_process_pool", lambda n: (True, 3))
    monkeypatch.setattr(pp, "make_executor", lambda *a, **k: _InlineExecutor())

    labels = []
    res = fs.backfill_all_fundamental_values(
        progress_cb=lambda c, t, l="": labels.append((c, t)))
    got = _snapshot(get_session())

    assert res["errors"] == []
    assert res["total"] == len(qcodes) + len(dcodes)
    assert got == ref                                  # multi-lote ≡ un lote
    # cobertura: cada activo tiene filas trimestrales y diarias
    covered_q = {r[0] for r in got["fund_quarterly"]}
    covered_d = {r[0] for r in got["fund_daily"]}
    assert covered_q == set(_IDS)
    assert covered_d == set(_IDS)
    assert labels and labels[-1][0] == labels[-1][1]   # progreso llega al total


def test_backfill_all_universo_vacio(_wide, monkeypatch):
    """Sin activos con fundamentales: no explota, no escribe, sin errores.
    Universo vacío forzado por monkeypatch → determinista, sin depender del
    estado global del stub sqlite (compartido entre tests)."""
    monkeypatch.setenv("USE_WIDE_IND_TABLES", "1")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(fs, "_fund_asset_ids", lambda s: [])
    Session.remove()
    res = fs.backfill_all_fundamental_values()
    assert res["errors"] == []
    assert res["inserted"] == 0
