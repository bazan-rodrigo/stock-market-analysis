"""returns_service: parseo de períodos a rango de fechas."""
from datetime import date, timedelta

from app.services.returns_service import period_to_dates


def test_periodo_rng_usa_fechas_explicitas():
    d_from, d_to = period_to_dates("rng", date_from="2024-01-01", date_to="2024-06-30")
    assert d_from == date(2024, 1, 1)
    assert d_to == date(2024, 6, 30)


def test_periodo_rng_sin_fechas_cae_a_ultimos_30_dias():
    today = date.today()
    d_from, d_to = period_to_dates("rng")
    assert d_from == today - timedelta(days=30)
    assert d_to == today


def test_periodo_ytd_arranca_1_de_enero():
    today = date.today()
    d_from, d_to = period_to_dates("YTD")
    assert d_from == date(today.year, 1, 1)
    assert d_to == today


def test_periodo_1d_1s_1m_3m_6m_1a():
    today = date.today()
    esperado = {
        "1D": timedelta(days=1), "1S": timedelta(weeks=1),
        "1M": timedelta(days=30), "3M": timedelta(days=91),
        "6M": timedelta(days=182), "1A": timedelta(days=365),
    }
    for periodo, delta in esperado.items():
        d_from, d_to = period_to_dates(periodo)
        assert d_from == today - delta
        assert d_to == today


def test_periodo_desconocido_cae_al_default_de_30_dias():
    today = date.today()
    d_from, d_to = period_to_dates("no_existe")
    assert d_from == today - timedelta(days=30)
    assert d_to == today
