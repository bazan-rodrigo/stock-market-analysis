from datetime import date as _date

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


def get_normalized_prices(asset_ids: list, base_date: _date = None) -> dict:
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
            "name": name,
            "dates": [str(d) for d in display_dates],
            "values": [pm[d] / base_price * 100 for d in display_dates],
            "base_date": str(effective_base),
        }

    return result
