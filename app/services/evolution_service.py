from datetime import date as _date, timedelta

_PALETTE = [
    "#60a5fa", "#34d399", "#f87171", "#fbbf24", "#a78bfa",
    "#fb923c", "#f472b6", "#4ade80", "#38bdf8", "#e879f9",
    "#94a3b8", "#2dd4bf", "#facc15", "#c084fc", "#f97316",
]


def assign_color(index: int) -> str:
    return _PALETTE[index % len(_PALETTE)]


def get_asset_label(asset_id: int) -> tuple:
    from app.database import get_session
    from app.models import Asset
    a = get_session().get(Asset, asset_id)
    if not a:
        return str(asset_id), ""
    return a.ticker, a.name or a.ticker


def get_related_assets(asset_id: int) -> dict:
    from app.database import get_session
    from app.models import Asset, Market
    from app.services.synthetic_service import get_formula_by_asset

    s = get_session()
    result = {
        "is_synthetic": False,
        "is_benchmark": False,
        "component_ids": [],
        "referenced_ids": [],
    }

    formula = get_formula_by_asset(asset_id)
    if formula:
        result["is_synthetic"] = True
        result["component_ids"] = [c.asset_id for c in formula.components]

    direct = [r[0] for r in s.query(Asset.id).filter(Asset.benchmark_id == asset_id).all()]
    market_ids = [m.id for m in s.query(Market).filter(Market.benchmark_id == asset_id).all()]
    via_market = []
    if market_ids:
        via_market = [r[0] for r in s.query(Asset.id).filter(Asset.market_id.in_(market_ids)).all()]

    referenced = list(set(direct + via_market) - {asset_id})
    if referenced:
        result["is_benchmark"] = True
        result["referenced_ids"] = referenced

    return result


def get_assets_by_filters(
    country_ids=None,
    currency_ids=None,
    instrument_type_ids=None,
    sector_ids=None,
    industry_ids=None,
    market_ids=None,
) -> list[dict]:
    from app.database import get_session
    from app.models import Asset

    s = get_session()
    q = s.query(Asset)
    if country_ids:
        q = q.filter(Asset.country_id.in_(country_ids))
    if currency_ids:
        q = q.filter(Asset.currency_id.in_(currency_ids))
    if instrument_type_ids:
        q = q.filter(Asset.instrument_type_id.in_(instrument_type_ids))
    if sector_ids:
        q = q.filter(Asset.sector_id.in_(sector_ids))
    if industry_ids:
        q = q.filter(Asset.industry_id.in_(industry_ids))
    if market_ids:
        q = q.filter(Asset.market_id.in_(market_ids))

    return [{"asset_id": a.id, "ticker": a.ticker, "name": a.name or a.ticker}
            for a in q.order_by(Asset.ticker).all()]


def get_events_for_assets(asset_ids: list) -> list[dict]:
    from app.database import get_session
    from app.models import Asset, MarketEvent
    from sqlalchemy import or_

    if not asset_ids:
        return []
    s = get_session()
    assets = [s.get(Asset, aid) for aid in asset_ids]
    country_ids = list({a.country_id for a in assets if a and a.country_id})

    conditions = [MarketEvent.scope == "global"]
    for aid in asset_ids:
        conditions.append(MarketEvent.asset_id == aid)
    for cid in country_ids:
        conditions.append(
            (MarketEvent.scope == "country") & (MarketEvent.country_id == cid)
        )

    events = (s.query(MarketEvent)
               .filter(or_(*conditions))
               .order_by(MarketEvent.start_date)
               .all())
    seen, result = set(), []
    for ev in events:
        if ev.id not in seen:
            seen.add(ev.id)
            result.append({
                "name":  ev.name,
                "start": str(ev.start_date),
                "end":   str(ev.end_date),
                "color": ev.color or "#ff9800",
            })
    return result


def get_normalized_prices(
    asset_ids: list,
    base_date: _date = None,
    end_date: _date = None,
) -> dict:
    from app.database import get_session
    from app.models import Asset, Price

    if not asset_ids:
        return {}

    s = get_session()
    price_maps = {}
    asset_info = {}

    for aid in asset_ids:
        asset = s.get(Asset, aid)
        if not asset:
            continue
        asset_info[aid] = (asset.ticker, asset.name or asset.ticker)
        prices = (
            s.query(Price)
            .filter(Price.asset_id == aid, Price.close.isnot(None))
            .order_by(Price.date)
            .all()
        )
        if prices:
            price_maps[aid] = {p.date: p.close for p in prices}

    if not price_maps:
        return {}

    all_date_sets = [set(pm.keys()) for pm in price_maps.values()]
    common_dates = sorted(set.intersection(*all_date_sets))

    if not common_dates:
        return {}

    if base_date is None:
        effective_base = common_dates[0]
    else:
        candidates = [d for d in common_dates if d <= base_date]
        effective_base = candidates[-1] if candidates else common_dates[0]

    display_dates = [d for d in common_dates if d >= effective_base]
    if end_date:
        display_dates = [d for d in display_dates if d <= end_date]
    if not display_dates:
        return {}

    result = {}
    for aid, pm in price_maps.items():
        base_price = pm.get(effective_base)
        if not base_price:
            continue
        ticker, name = asset_info[aid]
        result[aid] = {
            "ticker": ticker,
            "name":   name,
            "dates":  [str(d) for d in display_dates],
            "values": [pm[d] / base_price * 100 for d in display_dates],
            "base_date": str(effective_base),
        }

    return result
