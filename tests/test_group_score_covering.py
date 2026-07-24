"""compute_group_scores / _Sweep.covering: leer la barra semanal/mensual EN CURSO.

La tendencia semanal/mensual se guarda etiquetada al CIERRE de su período
(domingo con resample("W"), fin de mes con resample("M")), que cae DESPUÉS del
último día con precio (target_date). La barra cuyo período contiene target_date
—la EN CURSO, preliminar— es la primera con fecha >= target_date. El match
exacto sobre target_date no la encontraba nunca: regime_score_w/m quedaban en
NULL (bug del Mapa de Tendencia de Mercado). El camino por-fecha
(compute_group_scores) y el de rango (_Sweep.covering) comparten la regla.
"""
from datetime import date, timedelta

import pytest
import sqlalchemy as sa

from app.database import Base, engine, get_session

_IND   = ("ind_trend_daily", "ind_trend_weekly", "ind_trend_monthly")
_CLEAN = ("group_scores", "assets")


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


def test_compute_group_scores_lee_barra_en_curso(cov_db):
    """Regresión del bug: con precio último en viernes y la barra semanal en
    domingo / la mensual a fin de mes, los tres scores quedan poblados."""
    from app.models import Asset, GroupScore
    from app.models.indicator_store import get_ind_table
    from app.services.group_score_service import compute_group_scores

    s = get_session()
    s.add(Asset(id=1, ticker="T1", name="T1", sector_id=7, market_id=3,
                price_source_id=1))
    s.commit()

    target    = date(2026, 7, 24)   # viernes = último día con precio
    sunday    = date(2026, 7, 26)   # cierre semanal W-SUN (2 días después)
    month_end = date(2026, 7, 31)   # cierre mensual ME (7 días después)
    with engine.begin() as conn:
        conn.execute(get_ind_table("trend_daily").insert(),
                     [{"asset_id": 1, "date": target, "value": "bullish"}])
        conn.execute(get_ind_table("trend_weekly").insert(),
                     [{"asset_id": 1, "date": sunday, "value": "bullish"}])
        conn.execute(get_ind_table("trend_monthly").insert(),
                     [{"asset_id": 1, "date": month_end, "value": "bearish"}])

    compute_group_scores(target)

    rows = {g.group_type: g for g in
            s.query(GroupScore).filter(GroupScore.date == target).all()}
    assert set(rows) == {"sector", "market"}
    g = rows["sector"]
    assert g.regime_score_d == 60.0    # bullish, fecha exacta
    assert g.regime_score_w == 60.0    # bullish, barra del domingo (EN CURSO)
    assert g.regime_score_m == -60.0   # bearish, barra de fin de mes
    assert g.n_assets == 1


def test_compute_group_scores_ignora_barra_fuera_de_tope(cov_db):
    """Una barra semanal a más de COVERING_MAX_AHEAD_DAYS no se arrastra (activo
    con hueco): regime_score_w queda en NULL en vez de tomar una barra lejana."""
    from app.models import Asset, GroupScore
    from app.models.indicator_store import get_ind_table
    from app.services.group_score_service import (COVERING_MAX_AHEAD_DAYS,
                                                  compute_group_scores)

    s = get_session()
    s.add(Asset(id=1, ticker="T1", name="T1", sector_id=7, price_source_id=1))
    s.commit()

    target = date(2026, 7, 24)
    far    = target + timedelta(days=COVERING_MAX_AHEAD_DAYS + 5)
    with engine.begin() as conn:
        conn.execute(get_ind_table("trend_daily").insert(),
                     [{"asset_id": 1, "date": target, "value": "bullish"}])
        conn.execute(get_ind_table("trend_weekly").insert(),
                     [{"asset_id": 1, "date": far, "value": "bullish"}])

    compute_group_scores(target)
    g = s.query(GroupScore).filter(GroupScore.group_type == "sector").one()
    assert g.regime_score_d == 60.0
    assert g.regime_score_w is None


def test_sweep_covering_primera_barra_ge_d_con_tope():
    from app.services.group_score_service import COVERING_MAX_AHEAD_DAYS
    from app.services.signal_backfill_range import _Sweep

    d0 = date(2026, 7, 20)   # lunes
    rows = sorted([
        (1, date(2026, 7, 19), "a"),   # domingo anterior (< d0): no aplica
        (1, date(2026, 7, 26), "b"),   # domingo de la semana en curso
        (2, date(2026, 7, 26), "c"),
        (3, d0,               "d"),    # exacto d0
        (4, d0 + timedelta(days=COVERING_MAX_AHEAD_DAYS + 1), "e"),  # fuera de tope
    ], key=lambda r: r[1])
    sw = _Sweep(rows)
    # activo 1 salta la barra vieja y toma la >= d0; activo 4 queda afuera (tope)
    assert sw.covering(d0) == {1: "b", 2: "c", 3: "d"}


def test_load_sweep_extiende_ventana_solo_semanal_mensual(cov_db):
    """_load_sweep extiende la ventana +COVERING_MAX_AHEAD_DAYS SOLO para las
    tendencias semanal/mensual (su barra en curso cae después de window_end);
    para la diaria no, así que una fila > window_end queda afuera."""
    from app.models.indicator_store import get_ind_table
    from app.services.signal_backfill_range import _load_sweep

    s = get_session()
    we    = date(2026, 7, 24)   # fin de ventana (viernes)
    after = date(2026, 7, 26)   # domingo: > we pero dentro de +40
    with engine.begin() as conn:
        conn.execute(get_ind_table("trend_weekly").insert(),
                     [{"asset_id": 1, "date": after, "value": "bullish"}])
        conn.execute(get_ind_table("trend_daily").insert(),
                     [{"asset_id": 1, "date": after, "value": "bullish"}])

    ws = we - timedelta(days=45)
    weekly = _load_sweep(s, "trend_weekly", ws, we)
    assert [r[1] for r in weekly.rows] == [after]   # ventana extendida la trae
    daily = _load_sweep(s, "trend_daily", ws, we)
    assert daily.rows == []                          # sin extensión, queda afuera
