"""Tests del núcleo de derivación de carteras reales (portfolio_service.py).

Codifican la semántica del registro de operaciones: costo promedio ponderado
(con comisiones/impuestos), ventas parciales con P&L realizado neto, cierre de
posición, filtro as-of y fallback de precio.
"""
from datetime import date

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.database import Base
from app.models.price import Price
from app.services import portfolio_service as ps
from app.services.portfolio_service import (positions_from_transactions,
                                            unrealized_pnl)


def _session():
    """sqlite en memoria con el esquema completo (no toca la base real)."""
    eng = sa.create_engine("sqlite://")
    Base.metadata.create_all(eng)
    return Session(eng)


def _txn(asset_id, kind, d, qty, price, commission=0.0, taxes=0.0):
    return {"asset_id": asset_id, "kind": kind, "trade_date": d,
            "quantity": qty, "price": price, "commission": commission,
            "taxes": taxes}


def test_weighted_average_cost():
    txns = [
        _txn(1, "buy", date(2026, 3, 4), 1200, 3450),
        _txn(1, "buy", date(2026, 4, 20), 400, 3610),
    ]
    p = positions_from_transactions(txns)[1]
    assert p["qty"] == 1600
    assert p["avg_cost"] == 3490.0          # (1200·3450 + 400·3610)/1600
    assert p["cost_basis"] == 3490.0 * 1600
    assert p["realized_pnl"] == 0.0


def test_partial_sell_realized_pnl():
    txns = [
        _txn(1, "buy", date(2026, 3, 4), 1200, 3450),
        _txn(1, "buy", date(2026, 4, 20), 400, 3610),
        _txn(1, "sell", date(2026, 5, 14), 600, 3600),
    ]
    p = positions_from_transactions(txns)[1]
    assert p["qty"] == 1000
    assert p["avg_cost"] == 3490.0           # no cambia al vender
    assert p["realized_pnl"] == 600 * (3600 - 3490)   # 66_000
    assert p["cost_basis"] == 3490.0 * 1000


def test_costs_affect_avg_and_realized():
    txns = [
        _txn(1, "buy", date(2026, 1, 2), 100, 100, commission=3, taxes=2),
        _txn(1, "sell", date(2026, 1, 10), 50, 110, commission=1, taxes=1),
    ]
    p = positions_from_transactions(txns)[1]
    assert p["avg_cost"] == 100.05           # (100·100 + 5)/100
    assert p["realized_pnl"] == 50 * (110 - 100.05) - 2
    assert p["qty"] == 50


def test_full_close_resets_position():
    txns = [
        _txn(1, "buy", date(2026, 1, 2), 100, 100),
        _txn(1, "sell", date(2026, 2, 2), 100, 120),
    ]
    p = positions_from_transactions(txns)[1]
    assert p["qty"] == 0.0
    assert p["avg_cost"] is None
    assert p["cost_basis"] == 0.0
    assert p["realized_pnl"] == 100 * (120 - 100)


def test_as_of_filters_later_transactions():
    txns = [
        _txn(1, "buy", date(2026, 1, 2), 100, 100),
        _txn(1, "buy", date(2026, 6, 1), 50, 200),
    ]
    p = positions_from_transactions(txns, as_of=date(2026, 3, 1))[1]
    assert p["qty"] == 100                    # la compra de junio queda afuera


def test_price_none_is_skipped():
    txns = [_txn(1, "buy", date(2026, 1, 2), 100, None)]
    assert positions_from_transactions(txns) == {1: {
        "qty": 0.0, "avg_cost": None, "cost_basis": 0.0, "realized_pnl": 0.0}}


def test_multiple_assets():
    txns = [
        _txn(1, "buy", date(2026, 1, 2), 100, 100),
        _txn(2, "buy", date(2026, 1, 3), 10, 500),
    ]
    pos = positions_from_transactions(txns)
    assert pos[1]["qty"] == 100 and pos[2]["qty"] == 10


def test_unrealized_pnl():
    pos = {"qty": 1000, "avg_cost": 3490.0}
    assert unrealized_pnl(pos, 3742.0) == 1000 * (3742.0 - 3490.0)
    assert unrealized_pnl({"qty": 0.0, "avg_cost": None}, 100) is None
    assert unrealized_pnl(pos, None) is None


# ── Capa con BD (sqlite en memoria) ───────────────────────────────────────────

def test_market_close_and_fallback():
    s = _session()
    s.add_all([Price(asset_id=1, date=date(2026, 3, 3), close=3400),
               Price(asset_id=1, date=date(2026, 3, 4), close=3450),
               Price(asset_id=1, date=date(2026, 3, 10), close=3600)])
    s.commit()
    assert ps.market_close(s, 1, date(2026, 3, 4)) == 3450
    assert ps.market_close(s, 1, date(2026, 3, 9)) == 3450   # último <= fecha
    assert ps.market_close(s, 1) == 3600                     # el más reciente
    assert ps.market_close(s, 99) is None


def test_resolve_holdings_uses_price_fallback_and_pnl():
    s = _session()
    p = ps.create_portfolio(s, "Cuenta", "real", owner_id=1)
    s.add_all([Price(asset_id=1, date=date(2026, 3, 4), close=3450),
               Price(asset_id=1, date=date(2026, 5, 1), close=3742)])
    s.commit()
    # compra SIN precio → debe tomar el cierre de mercado de la fecha (3450)
    ps.add_transaction(s, p.id, 1, "buy", date(2026, 3, 4), quantity=100,
                       price=None)
    h = ps.resolve_holdings(s, p.id)
    assert len(h) == 1
    hh = h[0]
    assert hh["quantity"] == 100 and hh["avg_cost"] == 3450
    assert hh["market_price"] == 3742
    assert hh["market_value"] == 100 * 3742
    assert hh["unrealized_pnl"] == 100 * (3742 - 3450)


def test_list_portfolios_visibility():
    s = _session()
    ps.create_portfolio(s, "propia priv", "real", owner_id=1)
    ps.create_portfolio(s, "ajena pub", "seg", owner_id=2, is_public=True)
    ps.create_portfolio(s, "ajena priv", "seg", owner_id=2)
    # user 1 (no admin): ve la propia + la pública ajena, no la privada ajena
    names = {p.name for p in ps.list_portfolios(s, user_id=1, is_admin=False)}
    assert names == {"propia priv", "ajena pub"}
    # admin ve todas
    assert len(ps.list_portfolios(s, user_id=1, is_admin=True)) == 3
    # filtro por tipo
    segs = ps.list_portfolios(s, user_id=1, is_admin=True, ptype="seg")
    assert {p.name for p in segs} == {"ajena pub", "ajena priv"}


def test_add_and_list_transactions_ordered():
    s = _session()
    p = ps.create_portfolio(s, "Cuenta", "real", owner_id=1)
    ps.add_transaction(s, p.id, 1, "sell", date(2026, 4, 4), quantity=50, price=120)
    ps.add_transaction(s, p.id, 1, "buy", date(2026, 3, 4), quantity=100, price=100)
    txs = ps.list_transactions(s, p.id)
    assert [t.kind for t in txs] == ["buy", "sell"]   # ordenadas por fecha


def _buy100(s, pid):
    ps.add_transaction(s, pid, 1, "buy", date(2026, 3, 4), quantity=100, price=100)


def test_equity_series_is_pnl_curve_with_zero_cash():
    s = _session()
    p = ps.create_portfolio(s, "Cuenta", "real", owner_id=1)
    s.add_all([Price(asset_id=1, date=date(2026, 3, 4), close=100),
               Price(asset_id=1, date=date(2026, 3, 5), close=110),
               Price(asset_id=1, date=date(2026, 3, 6), close=90)])
    s.commit()
    _buy100(s, p.id)
    ds = [date(2026, 3, 4), date(2026, 3, 5), date(2026, 3, 6)]
    es = ps.equity_series(s, p.id, dates=ds)
    assert es["holdings_value"] == [10000.0, 11000.0, 9000.0]
    assert es["cash"] == [-10000.0, -10000.0, -10000.0]
    assert es["nav"] == [0.0, 1000.0, -1000.0]     # P&L: 100·(precio−100)


def test_equity_series_with_initial_capital_is_account_value():
    s = _session()
    p = ps.create_portfolio(s, "Cuenta", "real", owner_id=1)
    s.add_all([Price(asset_id=1, date=date(2026, 3, 4), close=100),
               Price(asset_id=1, date=date(2026, 3, 5), close=110)])
    s.commit()
    _buy100(s, p.id)
    es = ps.equity_series(s, p.id, dates=[date(2026, 3, 4), date(2026, 3, 5)],
                          initial_cash=10000)
    assert es["nav"] == [10000.0, 11000.0]         # valor de cuenta 10k → 11k


def test_equity_series_costs_reduce_nav():
    s = _session()
    p = ps.create_portfolio(s, "Cuenta", "real", owner_id=1)
    s.add(Price(asset_id=1, date=date(2026, 3, 4), close=100))
    s.commit()
    ps.add_transaction(s, p.id, 1, "buy", date(2026, 3, 4), quantity=100,
                       price=100, commission=3, taxes=2)
    es = ps.equity_series(s, p.id, dates=[date(2026, 3, 4)])
    assert es["nav"] == [-5.0]                      # el costo de la operación


def test_equity_series_default_dates_from_price_calendar():
    s = _session()
    p = ps.create_portfolio(s, "Cuenta", "real", owner_id=1)
    s.add_all([Price(asset_id=1, date=date(2026, 3, 4), close=100),
               Price(asset_id=1, date=date(2026, 3, 5), close=110),
               Price(asset_id=1, date=date(2026, 3, 6), close=90)])
    s.commit()
    _buy100(s, p.id)
    es = ps.equity_series(s, p.id)                  # dates=None → calendario
    assert es["dates"] == [date(2026, 3, 4), date(2026, 3, 5), date(2026, 3, 6)]


def test_realized_pnl_total_includes_closed_positions():
    s = _session()
    p = ps.create_portfolio(s, "Cuenta", "real", owner_id=1)
    ps.add_transaction(s, p.id, 1, "buy", date(2026, 1, 2), quantity=10, price=100)
    ps.add_transaction(s, p.id, 1, "sell", date(2026, 2, 2), quantity=10, price=120)
    # posición cerrada → resolve_holdings no la devuelve, pero el realizado sí
    assert ps.resolve_holdings(s, p.id) == []
    assert ps.realized_pnl_total(s, p.id) == 10 * (120 - 100)


# ── carteras teóricas: membresía ──────────────────────────────────────────────

def test_resolve_membership_curated_equal_weight():
    s = _session()
    p = ps.create_portfolio(s, "Tech", "seg", owner_id=1,
                            composition_method="curated")
    ps.set_members(s, p.id, [10, 20, 30])
    m = ps.resolve_membership(s, p.id)
    assert sorted(a for a, _ in m) == [10, 20, 30]
    assert all(w == pytest.approx(1 / 3) for _, w in m)


def test_resolve_membership_curated_weighted_normalizes():
    s = _session()
    p = ps.create_portfolio(s, "W", "seg", owner_id=1,
                            composition_method="curated")
    ps.set_members(s, p.id, [10, 20], weights=[3.0, 1.0])
    m = dict(ps.resolve_membership(s, p.id))
    assert m[10] == pytest.approx(0.75) and m[20] == pytest.approx(0.25)


def test_set_members_replaces():
    s = _session()
    p = ps.create_portfolio(s, "Tech", "seg", owner_id=1,
                            composition_method="curated")
    ps.set_members(s, p.id, [10, 20, 30])
    ps.set_members(s, p.id, [40])                 # reemplaza
    assert [a for a, _ in ps.resolve_membership(s, p.id)] == [40]


def test_resolve_membership_no_method_is_empty():
    s = _session()
    p = ps.create_portfolio(s, "R", "seg", owner_id=1)   # sin método
    assert ps.resolve_membership(s, p.id) == []
