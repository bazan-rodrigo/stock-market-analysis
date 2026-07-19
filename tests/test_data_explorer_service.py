"""Explorador de datos: lecturas crudas de las tablas del pipeline. Toca el
sqlite stub local (hermético), nunca MySQL. Verifica el despacho, la forma de
la salida (tabla/columnas/registros) y el orden por fecha."""
import datetime as dt
import inspect

import pytest
import sqlalchemy as sa

from app.database import Base, engine, get_session
from app.models import signal_store
from app.models.fundamental_quarterly import FundamentalQuarterly
from app.models.group_scores import GroupScore
from app.models.group_signal_value import GroupSignalValue
from app.models.indicator_store import CurrentIndicatorValue, get_ind_table
from app.services import data_explorer_service as des

_CODE = "zz_test_explorer"  # prefijo zz: no colisiona con indicadores reales


@pytest.fixture(autouse=True)
def _tables():
    Base.metadata.create_all(engine)
    yield


# ── Despacho / catálogo ───────────────────────────────────────────────────────

def test_datasets_combos_son_kwargs_de_fetch():
    params = set(inspect.signature(des.fetch).parameters) - {"dataset"}
    for d in des.DATASETS.values():
        assert set(d["combos"]) <= params

def test_fetch_dataset_desconocido():
    with pytest.raises(ValueError):
        des.fetch("no-existe")


# ── Indicador histórico (tabla ind_{code} dinámica) ───────────────────────────

@pytest.fixture()
def ind_tbl():
    with engine.begin() as c:
        c.execute(sa.text(f"DROP TABLE IF EXISTS ind_{_CODE}"))
        c.execute(sa.text(
            f"CREATE TABLE ind_{_CODE} ("
            "  asset_id INTEGER NOT NULL, date DATE NOT NULL, value FLOAT,"
            "  PRIMARY KEY (asset_id, date))"))
    yield
    with engine.begin() as c:
        c.execute(sa.text(f"DROP TABLE IF EXISTS ind_{_CODE}"))
    from app.models import indicator_store as _mod
    if f"ind_{_CODE}" in _mod._meta.tables:
        _mod._meta.remove(_mod._meta.tables[f"ind_{_CODE}"])

def test_indicator_history(ind_tbl):
    t = get_ind_table(_CODE)
    with engine.begin() as c:
        c.execute(t.insert(), [
            {"asset_id": 1, "date": dt.date(2026, 7, 8), "value": 11.0},
            {"asset_id": 1, "date": dt.date(2026, 7, 7), "value": 10.0},
            {"asset_id": 2, "date": dt.date(2026, 7, 8), "value": 99.0},  # otro activo
        ])
    table, cols, recs = des.indicator_history(_CODE, 1)
    assert table == f"ind_{_CODE}"
    assert cols == ["date", "value"]
    assert [r["value"] for r in recs] == [10.0, 11.0]   # ordenado por fecha
    assert recs[0]["date"] == "2026-07-07"              # fecha serializada a str


# ── Indicadores vigentes ──────────────────────────────────────────────────────

def test_current_indicators():
    s = get_session()
    s.query(CurrentIndicatorValue).delete()
    s.add_all([
        CurrentIndicatorValue(asset_id=1, code="best_sma_d", value_num=50.0),
        CurrentIndicatorValue(asset_id=1, code="best_ema_d", value_str="X"),
        CurrentIndicatorValue(asset_id=2, code="best_sma_d", value_num=7.0),
    ])
    s.commit()
    table, cols, recs = des.current_indicators(1)
    assert table == "current_indicator_values"
    assert [r["code"] for r in recs] == ["best_ema_d", "best_sma_d"]  # por code


# ── Scores ────────────────────────────────────────────────────────────────────

def test_signal_asset():
    s = get_session()
    t1 = signal_store.ensure_sig_table(1)
    t2 = signal_store.ensure_sig_table(2)
    s.execute(t1.delete())
    s.execute(t2.delete())
    s.execute(t1.insert(), [
        {"asset_id": 1, "date": dt.date(2026, 7, 7), "score": 0.5},
        {"asset_id": 1, "date": dt.date(2026, 7, 8), "score": 0.7},
        {"asset_id": 2, "date": dt.date(2026, 7, 8), "score": 9.9},
    ])
    s.execute(t2.insert(), [
        {"asset_id": 1, "date": dt.date(2026, 7, 8), "score": 1.1},
    ])
    s.commit()
    table, cols, recs = des.signal_asset(1, 1)
    assert table == "sig_1"
    assert [r["score"] for r in recs] == [0.5, 0.7]

def test_group_scores():
    s = get_session()
    s.query(GroupScore).delete()
    s.add_all([
        GroupScore(group_type="sector", group_id=3, date=dt.date(2026, 7, 7),
                   regime_score_d=1.0, regime_score_w=2.0, regime_score_m=3.0, n_assets=5),
        GroupScore(group_type="sector", group_id=4, date=dt.date(2026, 7, 7),
                   regime_score_d=0.0, n_assets=1),
    ])
    s.commit()
    table, cols, recs = des.group_scores("sector", 3)
    assert table == "group_scores"
    assert len(recs) == 1
    assert recs[0]["n_assets"] == 5 and recs[0]["date"] == "2026-07-07"


# ── M8: señal por grupo, resultado de estrategia, fundamentales ───────────────

def test_signal_group():
    s = get_session()
    s.query(GroupSignalValue).delete()
    s.add_all([
        GroupSignalValue(signal_id=1, group_type="sector", group_id=3,
                         date=dt.date(2026, 7, 8), score=0.7),
        GroupSignalValue(signal_id=1, group_type="sector", group_id=3,
                         date=dt.date(2026, 7, 7), score=0.5),
        # ruido: otro signal / group_type / group_id → excluidos por el filtro
        GroupSignalValue(signal_id=2, group_type="sector", group_id=3,
                         date=dt.date(2026, 7, 8), score=9.9),
        GroupSignalValue(signal_id=1, group_type="market", group_id=3,
                         date=dt.date(2026, 7, 8), score=8.8),
        GroupSignalValue(signal_id=1, group_type="sector", group_id=4,
                         date=dt.date(2026, 7, 8), score=7.7),
    ])
    s.commit()
    table, cols, recs = des.signal_group(1, "sector", 3)
    assert table == "group_signal_value"
    assert cols == ["date", "score"]
    assert [r["score"] for r in recs] == [0.5, 0.7]   # solo el trío pedido, asc
    assert recs[0]["date"] == "2026-07-07"            # fecha serializada a str


def test_strategy_result():
    s = get_session()
    t1 = signal_store.ensure_strat_table(1)
    t2 = signal_store.ensure_strat_table(2)
    s.execute(t1.delete())
    s.execute(t2.delete())
    s.execute(t1.insert(), [
        {"asset_id": 1, "date": dt.date(2026, 7, 7), "score": 0.5, "pct": 10.0},
        {"asset_id": 1, "date": dt.date(2026, 7, 8), "score": 0.7, "pct": 20.0},
        {"asset_id": 2, "date": dt.date(2026, 7, 8), "score": 9.9, "pct": 99.0},
    ])
    s.execute(t2.insert(), [
        {"asset_id": 1, "date": dt.date(2026, 7, 8), "score": 1.1, "pct": 30.0},
    ])
    s.commit()
    table, cols, recs = des.strategy_result(1, 1)
    assert table == "strat_res_1"                     # tabla dinámica por id
    assert cols == ["date", "score"]
    assert [r["score"] for r in recs] == [0.5, 0.7]   # activo 1, otra estrat fuera


def test_fundamentals():
    s = get_session()
    s.query(FundamentalQuarterly).delete()
    s.add_all([
        FundamentalQuarterly(asset_id=1, period_date=dt.date(2025, 12, 31),
                             revenue=90.0, net_income=8.0),
        FundamentalQuarterly(asset_id=1, period_date=dt.date(2026, 3, 31),
                             revenue=100.0, net_income=10.0),
        FundamentalQuarterly(asset_id=2, period_date=dt.date(2026, 3, 31),
                             revenue=999.0),           # otro activo → excluido
    ])
    s.commit()
    table, cols, recs = des.fundamentals(1)
    assert table == "fundamental_quarterly"
    assert cols == des._FUND_COLS and cols[0] == "period_date"
    assert len(recs) == 2                              # solo el activo 1
    # más reciente arriba (period_date desc), fechas serializadas a str
    assert [r["period_date"] for r in recs] == ["2026-03-31", "2025-12-31"]
    assert recs[0]["revenue"] == 100.0

    # limpiar: fundamental_quarterly lo enumera globalmente otro test
    # (test_fundamental_batching._fund_asset_ids) sobre el stub compartido; no
    # dejar filas colgadas de este activo.
    s.query(FundamentalQuarterly).delete()
    s.commit()
