"""
Servicio de eventos de mercado.
Gestiona el ABM y la consulta de eventos relevantes para un activo.
"""
from datetime import date

from sqlalchemy import or_

from app.database import get_session
from app.models import Asset, MarketEvent


def get_all_events() -> list[MarketEvent]:
    s = get_session()
    return s.query(MarketEvent).order_by(MarketEvent.start_date.desc()).all()


def get_event(event_id: int) -> MarketEvent | None:
    return get_session().query(MarketEvent).filter(MarketEvent.id == event_id).first()


def save_event(
    event_id: int | None,
    name: str,
    start_date: date,
    end_date: date,
    scope: str,
    country_id: int | None = None,
    asset_id: int | None = None,
    color: str = "#ff9800",
) -> MarketEvent:
    s = get_session()
    if event_id:
        ev = s.query(MarketEvent).filter(MarketEvent.id == event_id).first()
    else:
        ev = MarketEvent()
        s.add(ev)

    ev.name       = name.strip()
    ev.start_date = start_date
    ev.end_date   = end_date
    ev.scope      = scope
    ev.country_id = country_id if scope == "country" else None
    ev.asset_id   = asset_id   if scope == "asset"   else None
    ev.color      = color or "#ff9800"
    s.commit()
    return ev


def delete_event(event_id: int) -> None:
    s = get_session()
    ev = s.query(MarketEvent).filter(MarketEvent.id == event_id).first()
    if ev:
        s.delete(ev)
        s.commit()


def get_events_for_asset(asset_id: int, country_id: int | None) -> list[dict]:
    """
    Devuelve todos los eventos relevantes para un activo:
    - scope='global'
    - scope='country' y el country_id coincide
    - scope='asset' y el asset_id coincide
    """
    s = get_session()
    conditions = [
        MarketEvent.scope == "global",
        MarketEvent.asset_id == asset_id,
    ]
    if country_id:
        conditions.append(
            (MarketEvent.scope == "country") & (MarketEvent.country_id == country_id)
        )

    events = (
        s.query(MarketEvent)
        .filter(or_(*conditions))
        .order_by(MarketEvent.start_date)
        .all()
    )
    return [
        {
            "id":    ev.id,
            "name":  ev.name,
            "start": str(ev.start_date),
            "end":   str(ev.end_date),
            "color": ev.color or "#ff9800",
        }
        for ev in events
    ]
