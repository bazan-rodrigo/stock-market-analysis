"""fundamental_service: fórmulas de ratios (única fuente de verdad) y fechas."""
from datetime import date

import numpy as np
import pytest

from app.services.fundamental_service import (
    _Quarter, _compute_daily_ratios, _compute_quarterly_ratios, _ref_1y_ord,
    _safe_div_r,
)


def q(period, **kw):
    base = {f: None for f in _Quarter._fields}
    base["period_date"] = period
    base.update(kw)
    return _Quarter(**base)


# ── _safe_div_r ───────────────────────────────────────────────────────────────

def test_safe_div_basico_y_bordes():
    assert _safe_div_r(1, 3) == 0.3333
    assert _safe_div_r(None, 3) is None
    assert _safe_div_r(1, 0) is None
    assert _safe_div_r(1, None) is None


# ── _ref_1y_ord (29 de febrero) ───────────────────────────────────────────────

def test_ref_1y_normal():
    assert _ref_1y_ord(date(2026, 7, 4)) == date(2025, 7, 4).toordinal()

def test_ref_1y_bisiesto():
    assert _ref_1y_ord(date(2024, 2, 29)) == date(2023, 2, 28).toordinal()


# ── _compute_quarterly_ratios ─────────────────────────────────────────────────

def _quarters_basicos():
    """8 trimestres idénticos (fechas ascendentes; solo importa el orden)."""
    return [q(date(2024, 1, i + 1),
              revenue=1000, net_income=100, gross_profit=400, operating_income=200,
              total_debt=500, equity=1000)
            for i in range(8)]


def test_margenes_y_deuda():
    qs = [q(date(2025, 3, 31), revenue=1000, net_income=100, gross_profit=400,
            operating_income=200, total_debt=500, equity=1000)]
    r = _compute_quarterly_ratios(qs, 0)
    assert r["fundamental_net_margin"] == 0.1
    assert r["fundamental_gross_margin"] == 0.4
    assert r["fundamental_operating_margin"] == 0.2
    assert r["fundamental_debt_to_equity"] == 0.5

def test_growth_necesita_5_trimestres():
    qs = _quarters_basicos()
    assert _compute_quarterly_ratios(qs, 3)["fundamental_revenue_growth_yoy"] is None
    qs2 = qs[:4] + [qs[4]._replace(revenue=1200, net_income=150)]
    r = _compute_quarterly_ratios(qs2, 4)
    # idx 4 vs idx 0: (1200-1000)/1000 y (150-100)/100
    assert r["fundamental_revenue_growth_yoy"] == 0.2
    assert r["fundamental_eps_growth_yoy"] == 0.5

def test_roic_prefiere_nopat_ic_avg():
    qs = [q(date(2025, 3, 31), net_income=100, equity=1000, total_debt=500,
            nopat=60, invested_capital_avg=600)]
    assert _compute_quarterly_ratios(qs, 0)["fundamental_roic"] == 0.1  # 60/600

def test_roic_fallback_equity_mas_deuda():
    qs = [q(date(2025, 3, 31), net_income=150, equity=1000, total_debt=500)]
    assert _compute_quarterly_ratios(qs, 0)["fundamental_roic"] == 0.1  # 150/1500


# ── _compute_daily_ratios ─────────────────────────────────────────────────────

def _ttm_quarters(shares=100):
    dates_ = [date(2025, 3, 31), date(2025, 6, 30), date(2025, 9, 30), date(2025, 12, 31)]
    return [q(d, revenue=250, net_income=25, equity=1000, shares=shares) for d in dates_]


def _daily(price, quarters, ref_1y_ord=None, price_1y=None):
    q_ords = np.array([x.period_date.toordinal() for x in quarters])
    if price_1y is not None:
        p_ords, p_cls = np.array([ref_1y_ord]), np.array([float(price_1y)])
    else:
        p_ords, p_cls = np.array([], dtype=np.int64), np.array([])
    return _compute_daily_ratios(price, quarters, q_ords, len(quarters) - 1,
                                 p_ords, p_cls, ref_1y_ord or 0)


def test_pe_pb_ps():
    r = _daily(20.0, _ttm_quarters())
    assert r["fundamental_pe_ttm"] == 20.0    # eps TTM = 100/100 acciones = 1
    assert r["fundamental_pb"] == 2.0         # book = 1000/100 = 10
    assert r["fundamental_ps_ttm"] == 2.0     # rev/acción TTM = 10

def test_shares_usa_el_dato_mas_reciente():
    qs = _ttm_quarters()
    qs = [qs[0]._replace(shares=50), qs[1]._replace(shares=None),
          qs[2]._replace(shares=None), qs[3]._replace(shares=100)]
    r = _daily(20.0, qs)
    assert r["fundamental_pe_ttm"] == 20.0    # usa 100, no 50

def test_eps_negativo_no_da_pe():
    qs = [x._replace(net_income=-25) for x in _ttm_quarters()]
    assert _daily(20.0, qs)["fundamental_pe_ttm"] is None

def test_pe_growth_contra_hace_un_anio():
    qs_prev = [q(d, revenue=250, net_income=20, equity=1000, shares=100)
               for d in [date(2024, 3, 31), date(2024, 6, 30),
                         date(2024, 9, 30), date(2024, 12, 31)]]
    qs = qs_prev + _ttm_quarters()
    ref = date(2025, 1, 15).toordinal()       # hace 1 año: TTM 2024 (eps_ps 0.8)
    q_ords = np.array([x.period_date.toordinal() for x in qs])
    r = _compute_daily_ratios(20.0, qs, q_ords, len(qs) - 1,
                              np.array([ref]), np.array([16.0]), ref)
    # pe hoy = 20/1 = 20 ; pe hace 1 año = 16/0.8 = 20 → growth 0
    assert r["fundamental_pe_growth_yoy"] == pytest.approx(0.0)

def test_pe_growth_sin_historia_es_none():
    r = _daily(20.0, _ttm_quarters(), ref_1y_ord=date(2020, 1, 1).toordinal())
    assert r["fundamental_pe_growth_yoy"] is None
