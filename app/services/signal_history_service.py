"""
Historial de señales por activo — queries para la pantalla de evolución.
"""
from datetime import date as date_type

from app.database import get_session
from app.models import Asset, SignalDefinition, SignalValue, Strategy, StrategyComponent


def get_asset_signal_history(
    asset_id: int,
    signal_ids: list[int],
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> dict[int, list[tuple]]:
    """
    {signal_id: [(date, score), ...]} ordenado por fecha asc.
    """
    s = get_session()
    q = (
        s.query(SignalValue.signal_id, SignalValue.date, SignalValue.score)
        .filter(
            SignalValue.asset_id == asset_id,
            SignalValue.signal_id.in_(signal_ids),
        )
    )
    if date_from:
        q = q.filter(SignalValue.date >= date_from)
    if date_to:
        q = q.filter(SignalValue.date <= date_to)
    q = q.order_by(SignalValue.date)

    result: dict[int, list] = {sid: [] for sid in signal_ids}
    for sig_id, dt, score in q.all():
        result[sig_id].append((dt, score))
    return result


def get_signals_for_strategy(strategy_id: int) -> list[SignalDefinition]:
    s = get_session()
    strat = s.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strat is None:
        return []
    sig_ids = list({c.signal_id for c in strat.components})
    return s.query(SignalDefinition).filter(SignalDefinition.id.in_(sig_ids)).order_by(SignalDefinition.name).all()


def get_all_signals_flat() -> list[SignalDefinition]:
    s = get_session()
    return s.query(SignalDefinition).order_by(SignalDefinition.name).all()


def get_available_dates_for_asset(asset_id: int) -> list[date_type]:
    from sqlalchemy import distinct
    s = get_session()
    rows = (
        s.query(distinct(SignalValue.date))
        .filter(SignalValue.asset_id == asset_id)
        .order_by(SignalValue.date.desc())
        .all()
    )
    return [r[0] for r in rows]
