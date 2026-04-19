from datetime import date

import pandas as pd

from app.database import get_session
from app.models import Asset, MarketEvent, Price


def get_all_assets_options() -> list[dict]:
    s = get_session()
    assets = s.query(Asset).filter(Asset.active == True).order_by(Asset.ticker).all()
    return [{"label": f"{a.ticker} — {a.name}", "value": a.id} for a in assets]


def get_asset_label(asset_id: int) -> str:
    s = get_session()
    a = s.query(Asset).filter(Asset.id == asset_id).first()
    return f"{a.ticker} — {a.name}" if a else str(asset_id)


def get_paired_prices(asset1_id: int, asset2_id: int) -> list[dict]:
    s = get_session()
    p1 = s.query(Price.date, Price.close).filter(Price.asset_id == asset1_id).all()
    p2 = s.query(Price.date, Price.close).filter(Price.asset_id == asset2_id).all()

    df1 = pd.DataFrame(p1, columns=["date", "p1"]).set_index("date")
    df2 = pd.DataFrame(p2, columns=["date", "p2"]).set_index("date")

    df = df1.join(df2, how="inner").dropna().sort_index()
    return [
        {"date": str(idx), "p1": float(r["p1"]), "p2": float(r["p2"])}
        for idx, r in df.iterrows()
    ]


def get_events_with_coords(asset1_id: int, asset2_id: int,
                           pairs: list[dict]) -> list[dict]:
    """
    Retorna eventos relevantes (global o de alguno de los dos activos)
    con las coordenadas (p1, p2) del día más cercano al centro del evento.
    """
    if not pairs:
        return []

    s = get_session()
    events = s.query(MarketEvent).filter(
        (MarketEvent.scope == "global") |
        (
            (MarketEvent.scope == "asset") &
            MarketEvent.asset_id.in_([asset1_id, asset2_id])
        )
    ).all()

    date_map = {p["date"]: p for p in pairs}
    all_dates = [p["date"] for p in pairs]

    result = []
    for ev in events:
        try:
            mid = ev.start_date + (ev.end_date - ev.start_date) / 2
            mid_str = str(mid)
        except Exception:
            continue

        if mid_str in date_map:
            pair = date_map[mid_str]
        else:
            closest = min(all_dates,
                          key=lambda d: abs((date.fromisoformat(d) - mid).days))
            pair = date_map[closest]

        result.append({
            "name":       ev.name,
            "start_date": str(ev.start_date),
            "end_date":   str(ev.end_date),
            "color":      ev.color or "#ff9800",
            "p1":         pair["p1"],
            "p2":         pair["p2"],
        })

    return result
