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


# ── Retry ante lock InnoDB (1205 lock-timeout / 1213 deadlock) ────────────────
# _backfill_fund_batch reintenta la transacción del lote (rollback + backoff)
# cuando _backfill_fund_quarterly_all/_daily_all chocan con un deadlock/lock-
# timeout de otro worker escribiendo la misma tabla ancha; si agota
# _MAX_LOCK_RETRIES, el error del lote se ANOTA (no propaga: el hueco lo sana el
# próximo delta). El OperationalError se arma con .orig.args[0] == errno para que
# _is_retryable_lock_error lo clasifique (ver tests/test_lock_retry_and_purge.py).

def _op_err(errno):
    """OperationalError de SQLAlchemy con .orig.args[0] = errno de MySQL →
    _is_retryable_lock_error(exc) la clasifica como reintentable."""
    from sqlalchemy.exc import OperationalError
    return OperationalError("stmt", None, Exception(errno))


def test_backfill_fund_batch_retry_lock_reintenta_y_completa(_seeded, monkeypatch):
    """_backfill_fund_quarterly_all lanza un deadlock (1213) la 1ª vez y delega
    al real la 2ª → el lote reintenta y completa: escribe filas y res["errors"]
    queda vacío."""
    qcodes = sorted(fs._FUND_QUARTERLY_CODES)
    dcodes = sorted(fs._FUND_DAILY_CODES)
    s = _seeded

    # el TRUNCATE del rebuild lo hace el padre (el batch pasa skip_force_reset)
    fs._fund_force_reset(s, qcodes, dcodes)
    Session.remove()

    monkeypatch.setattr(fs.time, "sleep", lambda *a, **k: None)   # sin backoff real

    real_q = fs._backfill_fund_quarterly_all
    calls = {"n": 0}

    def _flaky_q(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _op_err(1213)              # deadlock la 1ª vez
        return real_q(*a, **kw)             # éxito al reintentar

    monkeypatch.setattr(fs, "_backfill_fund_quarterly_all", _flaky_q)

    res = fs._backfill_fund_batch(_IDS, qcodes, dcodes, force=True)

    assert calls["n"] == 2                    # falló una vez, reintentó y completó
    assert res["errors"] == []               # el retry exitoso limpia errors
    assert res["inserted"] > 0
    snap = _snapshot(get_session())
    assert snap["fund_quarterly"]            # las filas se escribieron
    assert snap["fund_daily"]


def test_backfill_fund_batch_retry_agota_y_anota(_seeded, monkeypatch):
    """_backfill_fund_quarterly_all lanza SIEMPRE lock-timeout (1205): tras
    _MAX_LOCK_RETRIES reintentos el lote DESISTE, anota el error en res["errors"]
    y NO propaga (la corrida sigue; el hueco lo sana el próximo delta)."""
    qcodes = sorted(fs._FUND_QUARTERLY_CODES)
    dcodes = sorted(fs._FUND_DAILY_CODES)
    s = _seeded

    fs._fund_force_reset(s, qcodes, dcodes)
    Session.remove()

    monkeypatch.setattr(fs.time, "sleep", lambda *a, **k: None)

    calls = {"n": 0}

    def _always_q(*a, **kw):
        calls["n"] += 1
        raise _op_err(1205)                  # lock-timeout siempre

    monkeypatch.setattr(fs, "_backfill_fund_quarterly_all", _always_q)

    # NO debe propagar: devuelve el dict con el error anotado
    res = fs._backfill_fund_batch(_IDS, qcodes, dcodes, force=True)

    assert calls["n"] == fs._MAX_LOCK_RETRIES + 1   # 1 intento + N reintentos
    assert len(res["errors"]) == 1                  # anotó el lote, sin abortar
    assert res["inserted"] == 0                     # nada se escribió


# ── Un lote que revienta NO tumba la corrida (anota y sigue) ─────────────────
# El catch-all de _backfill_fund_batch registra el fallo en out["errors"] y NO
# propaga; backfill_all_fundamental_values._consume lo agrega como {"code":"lote"}
# y los DEMÁS lotes escriben igual (backfill idempotente, el hueco lo sana el
# próximo delta). Un fallo NO-lock (RuntimeError) cae directo al catch-all sin
# pasar por el retry (que solo intercepta OperationalError reintentable).

def test_backfill_fund_un_lote_falla_y_sigue(_seeded, monkeypatch):
    """Con lotes de 1 activo (executor inline), un lote cuyo cómputo trimestral
    revienta se ANOTA en res["errors"] y NO escribe filas; los demás activos SÍ
    quedan escritos (partición independiente + resiliencia por-lote)."""
    import app.services.process_pool as pp
    s = _seeded  # noqa: F841 (fija el universo de activos sembrados)

    # camino real del padre, forzado a procesos-inline con un lote por activo
    monkeypatch.setattr(ts, "_MIN_BATCH_ASSETS", 1)
    monkeypatch.setattr(ts, "_use_process_pool", lambda n: (True, 3))
    monkeypatch.setattr(pp, "make_executor", lambda *a, **k: _InlineExecutor())

    _BAD = _IDS[1]
    real_q = fs._backfill_fund_quarterly_all

    def _flaky_q(codes, ids, *a, **kw):
        # revienta SOLO en el lote que contiene el activo marcado
        if _BAD in ids:
            raise RuntimeError("lote roto")
        return real_q(codes, ids, *a, **kw)

    monkeypatch.setattr(fs, "_backfill_fund_quarterly_all", _flaky_q)

    res = fs.backfill_all_fundamental_values()

    # el lote muerto quedó anotado, la corrida no abortó
    assert res["errors"], "un lote roto debe anotarse, no tumbar la corrida"
    assert all(e["code"] == "lote" for e in res["errors"])

    got = _snapshot(get_session())
    covered_q = {r[0] for r in got["fund_quarterly"]}
    covered_d = {r[0] for r in got["fund_daily"]}
    # el activo del lote roto no escribió NADA (rollback del batch entero)
    assert _BAD not in covered_q
    assert _BAD not in covered_d
    # los OTROS activos SÍ tienen filas (trimestrales y diarias)
    assert set(_IDS) - {_BAD} <= covered_q
    assert set(_IDS) - {_BAD} <= covered_d
