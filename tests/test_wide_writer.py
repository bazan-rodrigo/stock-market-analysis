"""Fase 2 de la tabla ancha por cadencia (docs/notes/design_ind_wide_tables.md):
el escritor upsert_ind_cadence. Propiedad clave = UPSERT PARCIAL por columna:
varios códigos de la misma cadencia escriben la misma fila (asset_id, date) sin
pisarse. Todavía nadie lo llama en el pipeline vivo (cutover en fase 4).
"""
import datetime as dt

import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from app.models.indicator_store import ensure_wide_ind_tables
from app.services.technical_service import upsert_ind_cadence

_D = dt.date(2026, 7, 1)


def _session():
    eng = sa.create_engine("sqlite://")
    ensure_wide_ind_tables(bind=eng)
    return sessionmaker(bind=eng)()


def test_upsert_parcial_acumula_columnas_sin_pisar():
    """Escribir rsi_daily y luego trend_daily en la MISMA fila deja ambos."""
    s = _session()
    upsert_ind_cadence(s, "daily", ["rsi_daily"], [(1, _D, 55.0)])
    upsert_ind_cadence(s, "daily", ["trend_daily"], [(1, _D, "bullish")])
    s.commit()

    row = s.execute(sa.text(
        "SELECT rsi_daily, trend_daily FROM ind_daily WHERE asset_id = 1"
    )).fetchone()
    assert row.rsi_daily == 55.0
    assert row.trend_daily == "bullish"


def test_upsert_actualiza_columna_sin_tocar_hermanas():
    s = _session()
    upsert_ind_cadence(s, "daily", ["rsi_daily", "trend_daily"],
                       [(1, _D, 55.0, "bullish")])
    upsert_ind_cadence(s, "daily", ["rsi_daily"], [(1, _D, 60.0)])
    s.commit()

    row = s.execute(sa.text(
        "SELECT rsi_daily, trend_daily FROM ind_daily WHERE asset_id = 1"
    )).fetchone()
    assert row.rsi_daily == 60.0        # actualizada
    assert row.trend_daily == "bullish"  # intacta


def test_upsert_batch_y_vacio():
    s = _session()
    rows = [(aid, _D, float(aid)) for aid in range(1, 6)]
    assert upsert_ind_cadence(s, "daily", ["rsi_daily"], rows) == 5
    assert upsert_ind_cadence(s, "daily", ["rsi_daily"], []) == 0
    s.commit()
    assert s.execute(sa.text("SELECT COUNT(*) FROM ind_daily")).scalar() == 5


def test_upsert_weekly_y_monthly_van_a_su_tabla():
    s = _session()
    upsert_ind_cadence(s, "weekly", ["rsi_weekly"], [(1, _D, 40.0)])
    upsert_ind_cadence(s, "monthly", ["rsi_monthly"], [(1, _D, 30.0)])
    s.commit()
    assert s.execute(sa.text("SELECT COUNT(*) FROM ind_weekly")).scalar() == 1
    assert s.execute(sa.text("SELECT COUNT(*) FROM ind_monthly")).scalar() == 1
    assert s.execute(sa.text("SELECT COUNT(*) FROM ind_daily")).scalar() == 0
