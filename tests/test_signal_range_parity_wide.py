"""Paridad del camino ANCHO (USE_WIDE_SIGNAL_TABLES=1) vs el per-entidad.

Reusa el fixture y el seeding de test_signal_range_parity. Corre el pipeline
per-entidad (flag OFF) como REFERENCIA y luego el mismo cálculo escribiendo a
las tablas anchas (flag ON), y exige que los scores leídos de las anchas sean
byte-idénticos. Cubre: el escritor de rango, el diario (compute_signal_values +
compute_strategy_results) y el lector de strategy_only (load_wide_signal_scores).
"""
import sqlalchemy as sa

from app.database import engine, get_session
from app.models import signal_store
from tests.test_signal_range_parity import (  # noqa: F401  (fixture + helpers)
    pipeline_db, _seed, _snapshot, _trading_dates, _wipe_derived)


def _drop_wide():
    with engine.begin() as conn:
        for t in (signal_store.SIG_WIDE_TABLE, signal_store.STRAT_WIDE_TABLE):
            conn.execute(sa.text(f"DROP TABLE IF EXISTS {t}"))
    for t in (signal_store.SIG_WIDE_TABLE, signal_store.STRAT_WIDE_TABLE):
        if t in signal_store._meta.tables:
            signal_store._meta.remove(signal_store._meta.tables[t])


def _snapshot_wide():
    """Mismo formato que _snapshot pero leyendo de las tablas anchas."""
    from app.models import Strategy
    from app.models import SignalDefinition
    s = get_session()

    sv = [
        (sid, aid, str(dt), round(score, 6))
        for dt, aid, sid, score in signal_store.load_wide_signal_scores(
            s, [x.id for x in s.query(SignalDefinition).all()],
            "0001-01-01", "9999-12-31")
    ]

    sr = []
    for st in s.query(Strategy).all():
        sc = signal_store.strat_score_column(st.id)
        pc = signal_store.strat_pct_column(st.id)
        rows = s.execute(sa.text(
            f"SELECT asset_id, date, {signal_store._q(s, sc)} AS score, "
            f"{signal_store._q(s, pc)} AS pct "
            f"FROM {signal_store._q(s, signal_store.STRAT_WIDE_TABLE)} "
            f"WHERE {signal_store._q(s, sc)} IS NOT NULL"))
        sr.extend((st.id, r.asset_id, str(r.date), round(r.score, 6),
                   round(r.pct, 6)) for r in rows)
    return {"sv": sorted(sv), "sr": sorted(sr)}


def _reference(dates, last):
    from app.services import signal_service, strategy_service
    for d in dates:
        signal_service.compute_signal_values(d, latest_price_date=last)
        strategy_service.compute_all_strategies(d)
    ref = _snapshot()
    assert ref["sv"] and ref["sr"]
    return ref


def test_paridad_ancha_rango(pipeline_db, monkeypatch):
    """El modo RANGO con flag ON reproduce EXACTO lo que escribe el per-entidad."""
    from app.services import signal_backfill_range
    _drop_wide()
    dates = _trading_dates()
    _seed(dates)
    last = dates[-1]

    reference = _reference(dates, last)

    _wipe_derived()
    monkeypatch.setenv("USE_WIDE_SIGNAL_TABLES", "1")
    result = signal_backfill_range.run_range(
        dates, only_ids=None, strategy_id=None, scope_kind=None,
        latest_price_date=last, eval_kind="all", eval_ref=0, logged=set())
    assert result["errors"] == []
    assert result["success"] == len(dates)

    assert _snapshot_wide() == reference
    _drop_wide()


def test_paridad_ancha_diario(pipeline_db, monkeypatch):
    """El camino DIARIO (compute_signal_values + compute_strategy_results) con
    flag ON escribe las anchas idéntico al per-entidad."""
    from app.services import signal_service, strategy_service
    _drop_wide()
    dates = _trading_dates()
    _seed(dates)
    last = dates[-1]

    reference = _reference(dates, last)

    _wipe_derived()
    monkeypatch.setenv("USE_WIDE_SIGNAL_TABLES", "1")
    for d in dates:
        signal_service.compute_signal_values(d, latest_price_date=last)
        strategy_service.compute_all_strategies(d)

    assert _snapshot_wide() == reference
    _drop_wide()


def test_paridad_ancha_rebuild_sobre_poblada(pipeline_db, monkeypatch):
    """Rebuild total (force + whole_history) SOBRE la ancha ya poblada: la
    limpieza (truncate) + INSERT plano reproduce el mismo estado, sin duplicados
    ni bloat, y con chunks/flush chicos (el corte no cambia el resultado)."""
    from app.services import signal_backfill_range
    _drop_wide()
    dates = _trading_dates()
    _seed(dates)
    last = dates[-1]
    reference = _reference(dates, last)

    _wipe_derived()
    monkeypatch.setenv("USE_WIDE_SIGNAL_TABLES", "1")
    monkeypatch.setattr(signal_backfill_range, "_CHUNK_DATES", 7)
    monkeypatch.setattr(signal_backfill_range, "_MAX_ROWS_PER_FLUSH", 40)

    # primera corrida (puebla)
    signal_backfill_range.run_range(
        dates, only_ids=None, strategy_id=None, scope_kind=None,
        latest_price_date=last, eval_kind="all", eval_ref=0, logged=set())
    assert _snapshot_wide() == reference

    # rebuild whole_history SOBRE poblada
    result = signal_backfill_range.run_range(
        dates, only_ids=None, strategy_id=None, scope_kind=None,
        latest_price_date=last, eval_kind="all", eval_ref=0,
        logged={d for d in dates}, force=True, full_wipe=True,
        whole_history=True)
    assert result["errors"] == []
    assert _snapshot_wide() == reference
    _drop_wide()


def test_strategy_only_ancho_lee_de_la_ancha(pipeline_db, monkeypatch):
    """strategy_only con flag ON: las señales se LEEN de la ancha
    (load_wide_signal_scores) y solo se reconstruyen las columnas de la
    estrategia — resultado idéntico, señales intactas."""
    from app.models import Strategy
    from app.services import signal_backfill_range, signal_service
    _drop_wide()
    dates = _trading_dates()
    _seed(dates)
    last = dates[-1]
    reference = _reference(dates, last)

    _wipe_derived()
    monkeypatch.setenv("USE_WIDE_SIGNAL_TABLES", "1")
    signal_backfill_range.run_range(
        dates, only_ids=None, strategy_id=None, scope_kind=None,
        latest_price_date=last, eval_kind="all", eval_ref=0, logged=set())
    assert _snapshot_wide() == reference

    s = get_session()
    sid = s.query(Strategy).one().id
    # Borrar SOLO las columnas de la estrategia y reconstruirlas leyendo las
    # señales guardadas en la ancha (end-to-end: rebuild_signal_history → rango).
    signal_store.drop_strat_columns(sid, bind=engine)
    result = signal_service.rebuild_signal_history(
        scope=f"strategy:{sid}", with_signals=False)
    assert result["errors"] == []

    after = _snapshot_wide()
    assert after["sr"] == reference["sr"]   # estrategia reconstruida idéntica
    assert after["sv"] == reference["sv"]   # señales intactas
    _drop_wide()
