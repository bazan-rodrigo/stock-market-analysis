"""
Servicio de Carteras (biblioteca de N carteras: reales y teóricas).

Este módulo arranca con el NÚCLEO de derivación de una cartera real: a partir
del registro de operaciones (portfolio_transaction) deriva la posición vigente
por activo — cantidad, costo promedio ponderado y P&L realizado —, manejando
compras/ventas parciales y los costos por operación (comisión + impuestos).

`positions_from_transactions` es lógica PURA (sin BD): recibe operaciones ya
materializadas (dicts) y devuelve las posiciones. Las funciones que consultan la
base (resolver precios de mercado para el fallback, valuar/armar la equity,
convertir monedas as-of) se apoyan en este núcleo y se agregan en el próximo
paso. La derivación de dividendos/splits también queda para ese paso (el
esquema ya los contempla vía `kind`).
"""

from bisect import bisect_right

from app.models.portfolio import (Portfolio, PortfolioMember,
                                  PortfolioTransaction)
from app.models.price import Price
from app.services import visibility


def _cost(txn):
    """Costo total de la operación (comisión + impuestos), en su moneda."""
    return (txn.get("commission") or 0.0) + (txn.get("taxes") or 0.0)


def positions_from_transactions(txns, as_of=None):
    """Deriva la posición por activo a partir del registro de operaciones.

    `txns`: iterable de dicts con claves: asset_id, kind ('buy'|'sell'|...),
    trade_date, quantity, price, commission, taxes. Se procesan en orden de
    fecha (y de id/orden de entrada como desempate estable). `as_of` (date)
    opcional: sólo considera operaciones con trade_date <= as_of.

    Devuelve dict {asset_id: {qty, avg_cost, cost_basis, realized_pnl}}:
      - qty: cantidad vigente (0 si se cerró).
      - avg_cost: costo promedio ponderado por acción (incluye comisiones/
        impuestos de las compras); None si no hay posición.
      - cost_basis: costo total de la posición vigente (qty · avg_cost).
      - realized_pnl: P&L realizado acumulado de las ventas, NETO de costos.

    Semántica (fijada por tests):
      - Compra: cost_basis += qty·precio + costos; avg_cost = cost_basis / qty.
      - Venta parcial: realized_pnl += qty·(precio − avg_cost) − costos; baja la
        cantidad y el cost_basis proporcionalmente; el avg_cost NO cambia.
      - Al cerrar (qty → 0) se limpian cost_basis y avg_cost.
      - Operaciones sin precio (price None) se saltean: el fallback a precio de
        mercado lo completa la capa que consulta la BD antes de llamar acá.
      - 'dividend' / 'split' todavía no se procesan (fase de dividendos/ajustes).
    """
    rows = [t for t in txns if as_of is None or t["trade_date"] <= as_of]
    rows.sort(key=lambda t: (t["asset_id"], t["trade_date"]))

    pos = {}
    for t in rows:
        aid = t["asset_id"]
        p = pos.setdefault(aid, {
            "qty": 0.0, "avg_cost": None, "cost_basis": 0.0, "realized_pnl": 0.0,
        })
        kind = t.get("kind")
        qty = t.get("quantity") or 0.0
        price = t.get("price")
        if kind in ("buy", "sell") and price is None:
            continue  # sin precio: lo completa el fallback de mercado

        if kind == "buy":
            p["cost_basis"] += qty * price + _cost(t)
            p["qty"] += qty
            p["avg_cost"] = p["cost_basis"] / p["qty"] if p["qty"] else None
        elif kind == "sell":
            avg = p["avg_cost"] or 0.0
            p["realized_pnl"] += qty * (price - avg) - _cost(t)
            p["qty"] -= qty
            p["cost_basis"] -= qty * avg
            if p["qty"] <= 1e-9:   # posición cerrada
                p["qty"] = 0.0
                p["cost_basis"] = 0.0
                p["avg_cost"] = None
        # 'dividend' / 'split': pendiente (fase de dividendos/ajustes)

    return pos


def unrealized_pnl(position, market_price):
    """P&L no realizado de una posición dado el precio de mercado actual.

    None si no hay precio de mercado o no hay posición.
    """
    if market_price is None or not position.get("qty"):
        return None
    return position["qty"] * (market_price - (position["avg_cost"] or 0.0))


# ── Capa con BD ───────────────────────────────────────────────────────────────
# Estas funciones reciben una `session` de SQLAlchemy (testeable con sqlite en
# memoria); los callbacks pasan get_session(). La visibilidad/edición reusa
# app/services/visibility.py (owner_id + is_public), igual que estrategias.

def market_close(session, asset_id, on_or_before=None):
    """Último cierre de mercado del activo (en o antes de `on_or_before` si se
    da; si no, el más reciente disponible). Base del fallback de precio."""
    q = (session.query(Price.close)
         .filter(Price.asset_id == asset_id, Price.close.isnot(None)))
    if on_or_before is not None:
        q = q.filter(Price.date <= on_or_before)
    row = q.order_by(Price.date.desc()).first()
    return row[0] if row else None


def _transaction_dicts(session, portfolio_id, as_of=None):
    """Operaciones de la cartera como dicts, con el fallback de precio ya
    resuelto (price None → cierre de mercado de la fecha)."""
    q = (session.query(PortfolioTransaction)
         .filter(PortfolioTransaction.portfolio_id == portfolio_id))
    if as_of is not None:
        q = q.filter(PortfolioTransaction.trade_date <= as_of)
    out = []
    for t in q.order_by(PortfolioTransaction.trade_date,
                        PortfolioTransaction.id):
        price = t.price
        if price is None and t.kind in ("buy", "sell"):
            price = market_close(session, t.asset_id, t.trade_date)
        out.append({"asset_id": t.asset_id, "kind": t.kind,
                    "trade_date": t.trade_date, "quantity": t.quantity,
                    "price": price, "commission": t.commission,
                    "taxes": t.taxes})
    return out


def resolve_holdings(session, portfolio_id, as_of=None):
    """Posiciones vigentes de una cartera real, derivadas del registro.

    Devuelve una lista de dicts por activo con posición abierta: quantity,
    avg_cost, cost_basis, market_price (cierre de mercado), market_value,
    unrealized_pnl y realized_pnl. `as_of` opcional para valuar a una fecha.
    """
    txns = _transaction_dicts(session, portfolio_id, as_of)
    positions = positions_from_transactions(txns)
    holdings = []
    for asset_id, p in positions.items():
        if not p["qty"]:
            continue
        mkt = market_close(session, asset_id, as_of)
        holdings.append({
            "asset_id": asset_id,
            "quantity": p["qty"],
            "avg_cost": p["avg_cost"],
            "cost_basis": p["cost_basis"],
            "market_price": mkt,
            "market_value": p["qty"] * mkt if mkt is not None else None,
            "unrealized_pnl": unrealized_pnl(p, mkt),
            "realized_pnl": p["realized_pnl"],
        })
    return holdings


def realized_pnl_total(session, portfolio_id, as_of=None):
    """P&L realizado acumulado de TODAS las posiciones (abiertas y cerradas).

    `resolve_holdings` solo devuelve posiciones abiertas (qty > 0); para los KPIs
    se necesita también el realizado de las posiciones ya cerradas.
    """
    txns = _transaction_dicts(session, portfolio_id, as_of)
    positions = positions_from_transactions(txns, as_of=as_of)
    return sum(p["realized_pnl"] for p in positions.values())


# ── CRUD (visibilidad/edición vía visibility.py) ──────────────────────────────

def create_portfolio(session, name, ptype, owner_id, *, is_public=False,
                     base_currency=None, benchmark_asset_id=None,
                     linked_portfolio_id=None, composition_method=None,
                     strategy_id=None, top_n=None, rebalance=None):
    p = Portfolio(name=name, ptype=ptype, owner_id=owner_id,
                  is_public=is_public, base_currency=base_currency,
                  benchmark_asset_id=benchmark_asset_id,
                  linked_portfolio_id=linked_portfolio_id,
                  composition_method=composition_method, strategy_id=strategy_id,
                  top_n=top_n, rebalance=rebalance)
    session.add(p)
    session.commit()
    return p


def list_portfolios(session, user_id, is_admin, ptype=None):
    """Carteras visibles para el usuario (propias + públicas; admin: todas)."""
    q = session.query(Portfolio).filter(
        visibility.visible_filter(Portfolio, user_id, is_admin))
    if ptype is not None:
        q = q.filter(Portfolio.ptype == ptype)
    return q.order_by(Portfolio.created_at.desc()).all()


def get_portfolio(session, portfolio_id):
    return session.get(Portfolio, portfolio_id)


def delete_portfolio(session, portfolio_id):
    p = session.get(Portfolio, portfolio_id)
    if p is not None:
        session.delete(p)
        session.commit()


def add_transaction(session, portfolio_id, asset_id, kind, trade_date, *,
                    quantity=None, price=None, commission=0.0, taxes=0.0,
                    currency=None, note=None):
    t = PortfolioTransaction(portfolio_id=portfolio_id, asset_id=asset_id,
                             kind=kind, trade_date=trade_date, quantity=quantity,
                             price=price, commission=commission, taxes=taxes,
                             currency=currency, note=note)
    session.add(t)
    session.commit()
    return t


def list_transactions(session, portfolio_id):
    return (session.query(PortfolioTransaction)
            .filter(PortfolioTransaction.portfolio_id == portfolio_id)
            .order_by(PortfolioTransaction.trade_date,
                      PortfolioTransaction.id)
            .all())


# ── Valuación en el tiempo (equity) ───────────────────────────────────────────

def _cash_flow(txn):
    """Flujo de caja de una operación (compra negativa, venta positiva, netos
    de costos). En la moneda de la operación (la conversión multi-moneda se
    aplica en un paso posterior). Precio None (sin fallback) → 0."""
    q = txn.get("quantity") or 0.0
    price = txn.get("price")
    kind = txn.get("kind")
    if price is None and kind in ("buy", "sell"):
        return 0.0
    if kind == "buy":
        return -(q * price + _cost(txn))
    if kind == "sell":
        return q * price - _cost(txn)
    return 0.0   # dividend / split: pendiente


def _price_lookup(session, asset_ids):
    """{asset_id: (fechas_ordenadas, closes)} para valuar as-of con bisect."""
    lut = {}
    for aid in set(asset_ids):
        rows = (session.query(Price.date, Price.close)
                .filter(Price.asset_id == aid, Price.close.isnot(None))
                .order_by(Price.date).all())
        lut[aid] = ([r[0] for r in rows], [r[1] for r in rows])
    return lut


def _close_asof(lut, asset_id, d):
    entry = lut.get(asset_id)
    if not entry or not entry[0]:
        return None
    dates, closes = entry
    i = bisect_right(dates, d) - 1
    return closes[i] if i >= 0 else None


def price_calendar(session, asset_ids, start=None, end=None):
    """Fechas con precio (unión de los activos dados), ordenadas — eje temporal
    para la valuación."""
    q = session.query(Price.date).filter(
        Price.asset_id.in_(list(set(asset_ids))), Price.close.isnot(None))
    if start is not None:
        q = q.filter(Price.date >= start)
    if end is not None:
        q = q.filter(Price.date <= end)
    return sorted({r[0] for r in q.distinct()})


def equity_series(session, portfolio_id, dates=None, initial_cash=0.0):
    """Valor de la cartera real en el tiempo (mark-to-market).

    Para cada fecha D: nav = cash + valor de mercado de las tenencias, donde
    `cash` acumula los flujos de las operaciones hasta D (compras negativas,
    ventas positivas, netas de costos) partiendo de `initial_cash`.

    Convención: con initial_cash=0 la NAV es el P&L acumulado (realizado + no
    realizado, arranca en ~0). Con initial_cash = capital depositado, es el valor
    de la cuenta. (La conversión multi-moneda y el tratamiento time-weighted de
    depósitos/retiros quedan para el paso siguiente; se define al armar la curva
    vs benchmark.)

    `dates` opcional: eje explícito (para tests/determinismo); si es None se toma
    el calendario de precios desde la primera operación. Devuelve
    {'dates', 'nav', 'holdings_value', 'cash'} (listas paralelas).
    """
    txns = _transaction_dicts(session, portfolio_id)   # precio resuelto as-of
    if not txns:
        return {"dates": [], "nav": [], "holdings_value": [], "cash": []}

    asset_ids = {t["asset_id"] for t in txns}
    lut = _price_lookup(session, asset_ids)
    if dates is None:
        start = min(t["trade_date"] for t in txns)
        dates = price_calendar(session, asset_ids, start=start)

    flows = sorted((t["trade_date"], _cash_flow(t)) for t in txns)
    navs, hvs, cashes = [], [], []
    for d in dates:
        positions = positions_from_transactions(txns, as_of=d)
        hv = 0.0
        for aid, p in positions.items():
            if not p["qty"]:
                continue
            close = _close_asof(lut, aid, d)
            if close is not None:
                hv += p["qty"] * close
        cash = initial_cash + sum(f for fd, f in flows if fd <= d)
        navs.append(cash + hv)
        hvs.append(hv)
        cashes.append(cash)
    return {"dates": dates, "nav": navs, "holdings_value": hvs, "cash": cashes}


# ── Carteras teóricas: membresía (Fase 3) ─────────────────────────────────────

def set_members(session, portfolio_id, asset_ids, weights=None):
    """Reemplaza la lista de miembros de una cartera CURADA."""
    session.query(PortfolioMember).filter(
        PortfolioMember.portfolio_id == portfolio_id).delete()
    for i, aid in enumerate(asset_ids):
        session.add(PortfolioMember(
            portfolio_id=portfolio_id, asset_id=aid,
            weight=(weights[i] if weights else None)))
    session.commit()


def resolve_membership(session, portfolio_id, as_of=None):
    """Miembros vigentes de una cartera teórica: lista de (asset_id, weight).

    - 'curated': los PortfolioMember (peso tal cual, normalizado; si ninguno
      tiene peso, equal-weight).
    - 'strategy': top-N por score de la estrategia as-of (equal-weight).
    - 'rule' / None: [] (la regla dinámica se implementa después).
    """
    p = session.get(Portfolio, portfolio_id)
    if p is None:
        return []
    if p.composition_method == "curated":
        rows = (session.query(PortfolioMember.asset_id, PortfolioMember.weight)
                .filter(PortfolioMember.portfolio_id == portfolio_id).all())
        if not rows:
            return []
        if all(w is None for _, w in rows):
            ew = 1.0 / len(rows)
            return [(aid, ew) for aid, _ in rows]
        total = sum(w or 0.0 for _, w in rows) or 1.0
        return [(aid, (w or 0.0) / total) for aid, w in rows]
    if p.composition_method == "strategy" and p.strategy_id:
        return _strategy_topn_members(session, p.strategy_id, p.top_n or 20,
                                      as_of)
    return []


def _strategy_topn_members(session, strategy_id, top_n, as_of=None):
    """Top-N por score de la estrategia en la última fecha con scores (<= as_of),
    equal-weight. [] si la estrategia ya no tiene tabla o historia."""
    import sqlalchemy as sa

    from app.models import signal_store
    try:
        rt = signal_store.ensure_strat_table(strategy_id,
                                             bind=session.connection())
    except Exception:
        return []
    q = sa.select(sa.func.max(rt.c.date)).where(rt.c.score.isnot(None))
    if as_of is not None:
        q = q.where(rt.c.date <= as_of)
    last_date = session.execute(q).scalar()
    if last_date is None:
        return []
    rows = session.execute(
        sa.select(rt.c.asset_id, rt.c.score)
        .where(rt.c.date == last_date, rt.c.score.isnot(None))).all()
    ranked = sorted(rows, key=lambda r: r[1], reverse=True)[:top_n]
    if not ranked:
        return []
    ew = 1.0 / len(ranked)
    return [(aid, ew) for aid, _ in ranked]


def tracking_drift(session, portfolio_id):
    """Desvío de COMPOSICIÓN de una cartera real vs su teórica objetivo vinculada.

    Compara los pesos reales vigentes (market_value / total) con los pesos
    objetivo (resolve_membership de la teórica). Devuelve {'target_name', 'rows':
    [{asset_id, target_w, real_w, diff}]} (diff = real − objetivo; negativo =
    faltante) o None si la cartera no está vinculada. El tracking error por
    RETORNOS queda para cuando se resuelva la convención de equity/TWR.
    """
    p = session.get(Portfolio, portfolio_id)
    if p is None or not p.linked_portfolio_id:
        return None
    target = dict(resolve_membership(session, p.linked_portfolio_id))
    holdings = resolve_holdings(session, portfolio_id)
    mv = sum(h["market_value"] for h in holdings
             if h["market_value"] is not None)
    real_w = {}
    if mv:
        for h in holdings:
            if h["market_value"] is not None:
                real_w[h["asset_id"]] = h["market_value"] / mv
    rows = [{"asset_id": aid, "target_w": target.get(aid, 0.0),
             "real_w": real_w.get(aid, 0.0),
             "diff": real_w.get(aid, 0.0) - target.get(aid, 0.0)}
            for aid in sorted(set(target) | set(real_w))]
    linked = session.get(Portfolio, p.linked_portfolio_id)
    return {"target_name": linked.name if linked else "—", "rows": rows}
