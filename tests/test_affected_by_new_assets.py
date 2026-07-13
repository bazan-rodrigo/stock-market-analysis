"""Detector de señales/estrategias afectadas al agregar activos nuevos.

Un sintético/activo nuevo entra a los agregados de sus grupos (sector, mercado,
...): eso desactualiza en la historia las señales de grupo de esos tipos y las
estrategias que las usan. El detector lista exactamente eso, para el aviso de
"Recalcular completo".
"""
import json

import pytest
import sqlalchemy as sa

from app.database import Base, engine, get_session

_TABLES = ("strategy_component", "strategy", "`signal`", "assets")


@pytest.fixture()
def db():
    import app.models  # noqa: F401 — registra los modelos en Base.metadata
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for t in _TABLES:
            conn.execute(sa.text(f"DELETE FROM {t}"))
    yield
    with engine.begin() as conn:
        for t in _TABLES:
            conn.execute(sa.text(f"DELETE FROM {t}"))
    get_session().rollback()


def _asset(id_, sector_id=None, market_id=None):
    from app.models import Asset
    return Asset(id=id_, ticker=f"T{id_}", name=f"T{id_}", sector_id=sector_id,
                 market_id=market_id, price_source_id=1)


def _group_signal(key, group_type):
    from app.models import SignalDefinition
    return SignalDefinition(
        key=key, name=key, source="group", group_type=group_type,
        indicator_key="regime_score_d", formula_type="range",
        params=json.dumps({"min": -100, "max": 100}), is_public=True)


def test_activo_nuevo_afecta_senal_de_grupo_de_su_tipo_y_su_estrategia(db):
    from app.models import Strategy, StrategyComponent
    from app.services.signal_service import (
        signals_and_strategies_affected_by_new_assets)

    s = get_session()
    s.add(_asset(1, sector_id=7))
    sig = _group_signal("sector_trend", "sector")
    s.add(sig)
    s.flush()
    strat = Strategy(name="EstrategiaSector", is_public=True, filter_conditions=None)
    s.add(strat)
    s.flush()
    s.add(StrategyComponent(strategy_id=strat.id, signal_id=sig.id, weight=1.0,
                            scope="own_group", group_type="sector"))
    s.commit()

    out = signals_and_strategies_affected_by_new_assets([1])
    assert any("sector_trend" in x for x in out)
    assert any("EstrategiaSector" in x for x in out)


def test_senal_de_grupo_de_otro_tipo_no_se_lista(db):
    from app.services.signal_service import (
        signals_and_strategies_affected_by_new_assets)
    s = get_session()
    # activo solo con sector; la señal es de tipo market → no lo toca
    s.add(_asset(1, sector_id=7))
    s.add(_group_signal("market_trend", "market"))
    s.commit()
    assert signals_and_strategies_affected_by_new_assets([1]) == []


def test_sin_senales_de_grupo_no_afecta_nada(db):
    from app.services.signal_service import (
        signals_and_strategies_affected_by_new_assets)
    s = get_session()
    s.add(_asset(1, sector_id=7, market_id=3))
    s.commit()
    assert signals_and_strategies_affected_by_new_assets([1]) == []


def test_lista_vacia_de_ids(db):
    from app.services.signal_service import (
        signals_and_strategies_affected_by_new_assets)
    assert signals_and_strategies_affected_by_new_assets([]) == []
