"""group_scores_for (mapa al vuelo) + _Sweep.covering: leer la barra vigente de
cada cadencia aunque target_date no sea día hábil del activo.

- Diaria: as-of hacia atrás (última barra <= target_date). Si target_date cae en
  un día donde el activo no operó (p.ej. un sábado que cotizan monedas y las
  acciones no), toma la del último día hábil (viernes).
- Semanal/mensual: covering hacia adelante (primera barra >= target_date). La
  barra cierra en domingo / fin de mes, DESPUÉS de target_date.

El match exacto sobre target_date fallaba en ambos casos (diario vacío en
Sectores los fines de semana; semanal/mensual siempre vacíos). El mapa calcula
esto AL VUELO (no se persiste en group_scores).
"""
from datetime import date, timedelta

import pytest
import sqlalchemy as sa

from app.database import Base, engine, get_session

_IND   = ("ind_trend_daily", "ind_trend_weekly", "ind_trend_monthly")
_CLEAN = ("assets",)


@pytest.fixture()
def cov_db():
    import app.models  # noqa: F401 — registra los modelos en Base.metadata
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for t in _IND:
            conn.execute(sa.text(f"DROP TABLE IF EXISTS {t}"))
            conn.execute(sa.text(
                f"CREATE TABLE {t} ("
                "  asset_id INTEGER NOT NULL,"
                "  date DATE NOT NULL,"
                "  value VARCHAR(30),"
                "  PRIMARY KEY (asset_id, date))"))
        for t in _CLEAN:
            conn.execute(sa.text(f"DELETE FROM {t}"))
    yield
    with engine.begin() as conn:
        for t in _IND:
            conn.execute(sa.text(f"DROP TABLE IF EXISTS {t}"))
        for t in _CLEAN:
            conn.execute(sa.text(f"DELETE FROM {t}"))
    from app.models import indicator_store as _mod
    for t in _IND:
        if t in _mod._meta.tables:
            _mod._meta.remove(_mod._meta.tables[t])
    get_session().rollback()


def _seed_asset(sector_id=7, market_id=3):
    from app.models import Asset
    s = get_session()
    s.add(Asset(id=1, ticker="T1", name="T1", sector_id=sector_id,
                market_id=market_id, price_source_id=1))
    s.commit()


def _insert(code, rows):
    from app.models.indicator_store import get_ind_table
    with engine.begin() as conn:
        conn.execute(get_ind_table(code).insert(),
                     [{"asset_id": 1, "date": d, "value": v} for d, v in rows])


def test_group_scores_for_barra_en_curso(cov_db):
    """target_date día hábil: diario exacto, semanal/mensual del período en curso
    (barra que cierra en el futuro)."""
    from app.services.group_score_service import group_scores_for

    _seed_asset()
    target = date(2026, 7, 24)   # viernes
    _insert("trend_daily",   [(target,             "bullish")])
    _insert("trend_weekly",  [(date(2026, 7, 26),  "bullish")])   # domingo
    _insert("trend_monthly", [(date(2026, 7, 31),  "bearish")])   # fin de mes

    agg = group_scores_for(target)
    g = agg[("sector", 7)]
    assert g["regime_score_d"] == 60.0    # bullish
    assert g["regime_score_w"] == 60.0    # covering domingo 26
    assert g["regime_score_m"] == -60.0   # covering fin de mes
    assert g["n_assets"] == 1


def test_group_scores_for_diario_asof_finde(cov_db):
    """target_date = sábado (lo empujan monedas de fin de semana): el diario de la
    acción está el viernes → as-of lo trae; semanal/mensual por covering.
    Este caso fallaba con el match exacto (Diario vacío en Sectores)."""
    from app.services.group_score_service import group_scores_for

    _seed_asset()
    saturday = date(2026, 7, 25)
    _insert("trend_daily",   [(date(2026, 7, 24), "bullish")])   # viernes (< target)
    _insert("trend_weekly",  [(date(2026, 7, 26), "bullish")])   # domingo (> target)
    _insert("trend_monthly", [(date(2026, 7, 31), "bearish")])   # fin de mes (> target)

    agg = group_scores_for(saturday)
    g = agg[("sector", 7)]
    assert g["regime_score_d"] == 60.0    # as-of: barra del viernes 24
    assert g["regime_score_w"] == 60.0
    assert g["regime_score_m"] == -60.0


def test_group_scores_for_diario_respeta_tope_asof(cov_db):
    """Un diario más viejo que ASOF_MAX_LOOKBACK_DAYS no se arrastra."""
    from app.models.indicator_store import ASOF_MAX_LOOKBACK_DAYS
    from app.services.group_score_service import group_scores_for

    _seed_asset()
    target = date(2026, 7, 24)
    old    = target - timedelta(days=ASOF_MAX_LOOKBACK_DAYS + 5)
    _insert("trend_daily", [(old, "bullish")])

    agg = group_scores_for(target)
    # sin diario dentro de ventana ni semanal/mensual → ningún grupo
    assert agg == {}


def test_group_scores_for_covering_respeta_tope(cov_db):
    """Una barra semanal a más de COVERING_MAX_AHEAD_DAYS no se toma."""
    from app.services.group_score_service import (COVERING_MAX_AHEAD_DAYS,
                                                  group_scores_for)

    _seed_asset()
    target = date(2026, 7, 24)
    _insert("trend_daily",  [(target, "bullish")])
    _insert("trend_weekly", [(target + timedelta(days=COVERING_MAX_AHEAD_DAYS + 5),
                              "bullish")])

    g = group_scores_for(target)[("sector", 7)]
    assert g["regime_score_d"] == 60.0
    assert g["regime_score_w"] is None


