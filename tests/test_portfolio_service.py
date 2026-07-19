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
from app.models import signal_store
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


def test_dividend_split_are_noops():
    """B5: 'dividend' y 'split' todavía no se procesan (fase pendiente). Fija que
    NO alteran qty / cost_basis / realized_pnl: la posición con esas operaciones
    debe ser idéntica a la posición sin ellas. Cuando se implementen dividendos,
    este test tendrá que cambiar deliberadamente."""
    base = positions_from_transactions([
        _txn(1, "buy", date(2026, 1, 2), 100, 100),
    ])[1]
    with_events = positions_from_transactions([
        _txn(1, "buy", date(2026, 1, 2), 100, 100),
        _txn(1, "dividend", date(2026, 1, 3), 100, 2),     # importe por acción
        _txn(1, "split", date(2026, 1, 4), 2, None),        # factor, sin precio
    ])[1]
    assert with_events == base
    assert with_events["qty"] == 100
    assert with_events["cost_basis"] == 100 * 100
    assert with_events["realized_pnl"] == 0.0


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


def test_resolve_membership_curated_mixed_weights():
    """M6: pesos mezclados (algunos None) → los None valen 0.0 y se normaliza por
    la suma de los definidos (regla `w or 0.0`). set_members([10,20],[3.0,None])
    → {10:1.0, 20:0.0}."""
    s = _session()
    p = ps.create_portfolio(s, "Mix", "seg", owner_id=1,
                            composition_method="curated")
    ps.set_members(s, p.id, [10, 20], weights=[3.0, None])
    m = dict(ps.resolve_membership(s, p.id))
    assert m[10] == pytest.approx(1.0)      # 3.0 / (3.0 + 0.0)
    assert m[20] == pytest.approx(0.0)      # None → 0.0


def test_resolve_membership_curated_no_members_empty():
    """M6: método 'curated' sin miembros cargados → [] (rama `if not rows`)."""
    s = _session()
    p = ps.create_portfolio(s, "Vacia", "seg", owner_id=1,
                            composition_method="curated")   # sin set_members
    assert ps.resolve_membership(s, p.id) == []


def test_tracking_drift_composition():
    s = _session()
    teo = ps.create_portfolio(s, "Target", "seg", owner_id=1,
                              composition_method="curated")
    ps.set_members(s, teo.id, [1, 2])                     # objetivo EW 50/50
    real = ps.create_portfolio(s, "Real", "real", owner_id=1,
                               linked_portfolio_id=teo.id)
    s.add(Price(asset_id=1, date=date(2026, 1, 2), close=100))
    s.commit()
    ps.add_transaction(s, real.id, 1, "buy", date(2026, 1, 2),
                       quantity=10, price=100)            # sólo tiene el activo 1
    d = ps.tracking_drift(s, real.id)
    assert d["target_name"] == "Target"
    byid = {r["asset_id"]: r for r in d["rows"]}
    assert byid[1]["target_w"] == pytest.approx(0.5)
    assert byid[1]["real_w"] == pytest.approx(1.0)
    assert byid[2]["diff"] == pytest.approx(-0.5)         # activo 2 faltante


def test_tracking_drift_none_when_not_linked():
    s = _session()
    real = ps.create_portfolio(s, "Real", "real", owner_id=1)
    assert ps.tracking_drift(s, real.id) is None


def test_tracking_drift_extra_asset():
    """M5: un activo presente SOLO en la real (no en el objetivo) aparece con
    target_w=0 y diff>0 (`extra puro`)."""
    s = _session()
    teo = ps.create_portfolio(s, "Target", "seg", owner_id=1,
                              composition_method="curated")
    ps.set_members(s, teo.id, [1])                        # objetivo: sólo activo 1
    real = ps.create_portfolio(s, "Real", "real", owner_id=1,
                               linked_portfolio_id=teo.id)
    s.add_all([Price(asset_id=1, date=date(2026, 1, 2), close=100),
               Price(asset_id=2, date=date(2026, 1, 2), close=100)])
    s.commit()
    # real: mitad en el activo 1 (del objetivo) y mitad en el 2 (fuera del objetivo)
    ps.add_transaction(s, real.id, 1, "buy", date(2026, 1, 2), quantity=10, price=100)
    ps.add_transaction(s, real.id, 2, "buy", date(2026, 1, 2), quantity=10, price=100)
    d = ps.tracking_drift(s, real.id)
    byid = {r["asset_id"]: r for r in d["rows"]}
    # activo 2: sólo en la real → objetivo 0, real 0.5, drift positivo
    assert byid[2]["target_w"] == pytest.approx(0.0)
    assert byid[2]["real_w"] == pytest.approx(0.5)
    assert byid[2]["diff"] == pytest.approx(0.5)
    assert byid[2]["diff"] > 0
    # activo 1: compartido, sub-ponderado respecto del objetivo (drift negativo)
    assert byid[1]["target_w"] == pytest.approx(1.0)
    assert byid[1]["real_w"] == pytest.approx(0.5)
    assert byid[1]["diff"] == pytest.approx(-0.5)


def test_tracking_drift_real_without_holdings():
    """M5: real sin tenencias (mv=0 → guard `if mv:`) ⇒ real_w vacío; las filas son
    los activos del objetivo con diff = -target_w."""
    s = _session()
    teo = ps.create_portfolio(s, "Target", "seg", owner_id=1,
                              composition_method="curated")
    ps.set_members(s, teo.id, [1, 2])                     # objetivo EW 50/50
    real = ps.create_portfolio(s, "Real", "real", owner_id=1,
                               linked_portfolio_id=teo.id)
    # sin operaciones → holdings=[] → mv=0 → real_w={}
    d = ps.tracking_drift(s, real.id)
    assert d["target_name"] == "Target"
    byid = {r["asset_id"]: r for r in d["rows"]}
    assert set(byid) == {1, 2}                            # sólo activos objetivo
    for aid in (1, 2):
        assert byid[aid]["real_w"] == pytest.approx(0.0)
        assert byid[aid]["target_w"] == pytest.approx(0.5)
        assert byid[aid]["diff"] == pytest.approx(-0.5)   # diff = -target_w


# ── carteras teóricas derivadas de estrategia (top-N por score as-of) ──────────
#
# `_strategy_topn_members` toma la ÚLTIMA fecha con score (<= as_of) de la tabla
# dinámica strat_res_{id} (columnas asset_id/date/score), ordena por `score`
# descendente, corta en top_n y reparte peso equal-weight (1/N).
#
# El harness usa un engine sqlite EFÍMERO por test (_session()), no el engine
# compartido de app.database; por eso la tabla strat_res_{id} se crea sobre la
# conexión de ESTA sesión (bind=s.connection()), replicando lo que hace el
# propio servicio al leer. Patrón de siembra tomado de test_backtest_service.


def _seed_strat(s, strategy_id, rows):
    """Siembra strat_res_{id} en el engine del harness.

    `rows`: iterable de (asset_id, date, score). Crea la tabla sobre la conexión
    de la sesión (engine efímero por test) e inserta las filas.
    """
    rt = signal_store.ensure_strat_table(strategy_id, bind=s.connection())
    s.execute(rt.insert(), [{"asset_id": a, "date": d, "score": sc}
                            for a, d, sc in rows])
    s.commit()
    return rt


def test_resolve_membership_strategy_topn():
    s = _session()
    p = ps.create_portfolio(s, "Top2", "seg", owner_id=1,
                            composition_method="strategy", strategy_id=901,
                            top_n=2)
    d1, d2 = date(2026, 1, 5), date(2026, 1, 6)
    _seed_strat(s, 901, [
        # fecha vieja: acá el top serían 1, 2 y sobre todo 5 (score altísimo)
        (1, d1, 100.0), (2, d1, 90.0), (5, d1, 999.0),
        # última fecha: el top-2 real es 3 y 4
        (1, d2, 5.0), (2, d2, 8.0), (3, d2, 200.0), (4, d2, 150.0),
    ])
    m = dict(ps.resolve_membership(s, p.id))
    assert set(m) == {3, 4}                        # top-2 de la ÚLTIMA fecha
    assert m[3] == pytest.approx(0.5)              # equal-weight 1/N
    assert m[4] == pytest.approx(0.5)
    # el 5, con score 999 pero SOLO en la fecha vieja, no entra → no mezcla fechas
    assert 5 not in m and 1 not in m and 2 not in m


def test_strategy_topn_asof_picks_last_date_le_asof():
    s = _session()
    p = ps.create_portfolio(s, "AsOf", "seg", owner_id=1,
                            composition_method="strategy", strategy_id=902,
                            top_n=1)
    d1, d2, d3 = date(2026, 1, 5), date(2026, 1, 10), date(2026, 1, 15)
    _seed_strat(s, 902, [
        (1, d1, 100.0), (2, d1, 1.0),      # d1: gana el activo 1
        (1, d2, 1.0),   (2, d2, 100.0),    # d2: gana el activo 2
        (1, d3, 100.0), (2, d3, 1.0),      # d3: gana el activo 1
    ])
    # as_of INTERMEDIO (entre d2 y d3) → última fecha <= as_of es d2 → activo 2
    assert ps.resolve_membership(s, p.id, as_of=date(2026, 1, 12)) == [(2, 1.0)]
    # as_of posterior a todo → d3 → activo 1 (confirma que avanza a la más nueva)
    assert ps.resolve_membership(s, p.id, as_of=date(2026, 1, 20)) == [(1, 1.0)]
    # as_of anterior a todo score → last_date None → []
    assert ps.resolve_membership(s, p.id, as_of=date(2026, 1, 1)) == []


def test_strategy_topn_n_exceeds_universe():
    s = _session()
    p = ps.create_portfolio(s, "AllIn", "seg", owner_id=1,
                            composition_method="strategy", strategy_id=903,
                            top_n=10)                  # top_n > universo
    d1 = date(2026, 1, 5)
    _seed_strat(s, 903, [(1, d1, 30.0), (2, d1, 20.0), (3, d1, 10.0)])
    m = dict(ps.resolve_membership(s, p.id))
    assert sorted(m) == [1, 2, 3]                      # devuelve todos
    assert all(w == pytest.approx(1 / 3) for w in m.values())   # EW sobre los 3


def test_strategy_topn_missing_table():
    s = _session()
    p = ps.create_portfolio(s, "Huerfana", "seg", owner_id=1,
                            composition_method="strategy", strategy_id=904,
                            top_n=5)
    # No se siembra strat_res_904: la estrategia no tiene historia/tabla poblada.
    # No debe crashear; devuelve []. (Con sqlite, ensure_strat_table+checkfirst
    # crea la tabla vacía y el resultado llega a [] por last_date is None, no por
    # la rama `except`; el resultado observable es el mismo.)
    assert ps.resolve_membership(s, p.id) == []
