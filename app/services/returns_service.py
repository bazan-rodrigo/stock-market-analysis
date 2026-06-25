from datetime import date, timedelta


def period_to_dates(period: str, date_from=None, date_to=None) -> tuple[date, date]:
    today = date.today()
    if period == "rng":
        return (
            date.fromisoformat(date_from) if date_from else today - timedelta(days=30),
            date.fromisoformat(date_to)   if date_to   else today,
        )
    if period == "YTD":
        return date(today.year, 1, 1), today
    _MAP = {
        "1D": timedelta(days=1),
        "1S": timedelta(weeks=1),
        "1M": timedelta(days=30),
        "3M": timedelta(days=91),
        "6M": timedelta(days=182),
        "1A": timedelta(days=365),
    }
    return today - _MAP.get(period, timedelta(days=30)), today


def resolve_asset_ids(mode, individual_ids, group_dim, group_val,
                      benchmark_ids, synthetic_ids) -> list[int]:
    from app.database import get_session
    from app.models import Asset
    from app.services.evolution_service import get_related_assets
    from app.services.synthetic_service import get_formula_by_asset

    s   = get_session()
    ids = set()

    if mode == "individual":
        ids.update(individual_ids or [])

    elif mode == "grupo":
        if group_dim and group_val is not None:
            _COL = {
                "sector":   Asset.sector_id,
                "industry": Asset.industry_id,
                "country":  Asset.country_id,
                "market":   Asset.market_id,
                "itype":    Asset.instrument_type_id,
            }
            col = _COL.get(group_dim)
            if col is not None:
                ids.update(r[0] for r in s.query(Asset.id).filter(col == group_val).all())

    elif mode == "benchmark":
        for bm_id in (benchmark_ids or []):
            info = get_related_assets(bm_id)
            refs = info.get("referenced_ids", [])
            ids.update(refs if refs else [bm_id])

    elif mode == "sintetico":
        for syn_id in (synthetic_ids or []):
            formula = get_formula_by_asset(syn_id)
            if formula:
                ids.update(c.asset_id for c in formula.components)
            else:
                ids.add(syn_id)

    return list(ids)


def get_returns(asset_ids: list[int], d_from: date, d_to: date) -> list[dict]:
    from app.database import get_session
    from app.models import Asset, Price

    if not asset_ids:
        return []

    s       = get_session()
    results = []
    for aid in asset_ids:
        p_start = (
            s.query(Price)
            .filter(Price.asset_id == aid, Price.date <= d_from)
            .order_by(Price.date.desc())
            .first()
        )
        p_end = (
            s.query(Price)
            .filter(Price.asset_id == aid, Price.date <= d_to)
            .order_by(Price.date.desc())
            .first()
        )
        if not p_start or not p_end or p_start.id == p_end.id:
            continue
        if not p_start.close or p_start.close == 0:
            continue
        asset = s.get(Asset, aid)
        if not asset:
            continue
        ret = (p_end.close / p_start.close - 1) * 100
        results.append({
            "id":          aid,
            "ticker":      asset.ticker,
            "name":        asset.name or asset.ticker,
            "return_pct":  round(ret, 2),
            "date_start":  p_start.date.isoformat(),
            "date_end":    p_end.date.isoformat(),
            "close_start": p_start.close,
            "close_end":   p_end.close,
        })

    results.sort(key=lambda x: x["return_pct"], reverse=True)
    return results
