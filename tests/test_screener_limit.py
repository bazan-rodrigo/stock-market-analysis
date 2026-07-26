"""Tope de filas del screener de señales (etapa de contención hacia 10.000
activos): el corte se hace en el SERVIDOR y por score, y la UI dice cuántos
activos quedaron afuera. Sobre el sqlite stub.
"""
import json
from datetime import date

import pytest
import sqlalchemy as sa

from app.database import Base, engine, get_session

_TABLES = ("strategy_component", "strategy", "`signal`", "assets")
_TARGET = date(2026, 7, 24)
_PREV   = date(2026, 7, 23)


@pytest.fixture()
def sc_db():
    import app.models  # noqa: F401 — registra los modelos en Base.metadata
    from app.models import signal_store
    Base.metadata.create_all(engine)
    signal_store.ensure_strat_table(1)
    signal_store.ensure_sig_table(1)
    _wipe()
    yield
    _wipe()
    get_session().rollback()


def _wipe():
    with engine.begin() as conn:
        for t in _TABLES + ("strat_res_1", "sig_1"):
            conn.execute(sa.text(f"DELETE FROM {t}"))


def _seed(n_assets: int):
    """n activos con score decreciente: el activo i tiene score 100-i, así el
    ranking por score es exactamente A000, A001, A002, …"""
    from app.models import (Asset, SignalDefinition, Strategy,
                            StrategyComponent, signal_store)
    s = get_session()
    s.add(SignalDefinition(id=1, key="sig_test", name="Señal test",
                           indicator_key="trend_daily", formula_type="discrete_map",
                           params=json.dumps({"map": {"bullish": 100}}),
                           is_public=True))
    s.add(Strategy(id=1, name="Estrategia test", is_public=True))
    s.add(StrategyComponent(id=1, strategy_id=1, signal_id=1, weight=1.0))
    for i in range(n_assets):
        s.add(Asset(id=i + 1, ticker=f"A{i:03d}", name=f"Activo {i}",
                    price_source_id=1))
    s.flush()

    rt = signal_store.get_strat_table(1)
    st = signal_store.get_sig_table(1)
    for i in range(n_assets):
        score = 100.0 - i
        s.execute(rt.insert().values(asset_id=i + 1, date=_TARGET, score=score))
        s.execute(rt.insert().values(asset_id=i + 1, date=_PREV,  score=score - 1))
        s.execute(st.insert().values(asset_id=i + 1, date=_TARGET, score=score))
    s.commit()


def test_sin_tope_devuelve_todo_y_el_total_es_la_cantidad_de_filas(sc_db):
    from app.services import strategy_service as svc
    _seed(10)

    rows, comp_meta, total = svc.get_strategy_results_with_breakdown(1, _TARGET)

    assert len(rows) == 10
    assert total == 10
    assert len(comp_meta) == 1


def test_el_tope_corta_por_score_y_el_total_cuenta_el_ranking_completo(sc_db):
    from app.services import strategy_service as svc
    _seed(10)

    rows, _meta, total = svc.get_strategy_results_with_breakdown(1, _TARGET, limit=3)

    assert [r["ticker"] for r in rows] == ["A000", "A001", "A002"], \
        "el tope se queda con la CABEZA del ranking, no con filas cualesquiera"
    assert total == 10, "el total debe ignorar el tope (la UI avisa cuántos faltan)"


def test_el_tope_no_rompe_el_desglose_ni_el_delta(sc_db):
    """Las lecturas por señal y la del día anterior van con un IN sobre los
    asset_id traídos: si el tope las descoordina, el desglose sale vacío."""
    from app.services import strategy_service as svc
    _seed(10)

    rows, meta, _total = svc.get_strategy_results_with_breakdown(1, _TARGET, limit=2)

    key = meta[0]["signal_key"]
    assert [r["comp_scores"][key] for r in rows] == [100.0, 99.0]
    assert [r["delta_score"] for r in rows] == [1.0, 1.0]


def test_el_tope_convive_con_el_filtro_de_sector(sc_db):
    from app.models import Asset
    from app.services import strategy_service as svc
    _seed(10)
    s = get_session()
    for i in (1, 2, 3):                       # A000, A001, A002 al sector 7
        s.query(Asset).filter(Asset.id == i).update({"sector_id": 7})
    s.commit()

    rows, _meta, total = svc.get_strategy_results_with_breakdown(
        1, _TARGET, sector_id=7, limit=2)

    assert [r["ticker"] for r in rows] == ["A000", "A001"]
    assert total == 3, "el total se cuenta DESPUÉS de filtrar, antes de topear"


def test_estrategia_inexistente_devuelve_la_terna_vacia(sc_db):
    from app.services import strategy_service as svc

    assert svc.get_strategy_results_with_breakdown(999, _TARGET) == ([], [], 0)


def test_fecha_sin_resultados_devuelve_la_terna_vacia(sc_db):
    from app.services import strategy_service as svc
    _seed(3)

    assert svc.get_strategy_results_with_breakdown(
        1, date(2020, 1, 2), limit=5) == ([], [], 0)


# ── Etiqueta del contador (pura) ──────────────────────────────────────────────

def test_la_etiqueta_avisa_cuando_el_ranking_quedo_cortado():
    from app.callbacks.screener_signals_callbacks import _result_label

    assert _result_label(500, 10000) == ("500 de 10.000 activos", True)
    assert _result_label(120, 120)   == ("120 activos", False)
