"""
Historial de señales por activo — queries para la pantalla de evolución.
"""
from datetime import date as date_type

import sqlalchemy as sa

from app.database import get_session
from app.models import SignalDefinition, Strategy, signal_store


def get_asset_signal_history(
    asset_id: int,
    signal_ids: list[int],
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> dict[int, list[tuple]]:
    """
    {signal_id: [(date, score), ...]} ordenado por fecha asc.
    Una query por señal (cada una tiene su tabla; el índice
    (asset_id, date) cubre esta lectura).
    """
    s = get_session()
    result: dict[int, list] = {sid: [] for sid in signal_ids}
    for sig_id in signal_ids:
        t = signal_store.ensure_sig_table(sig_id, bind=s.connection())
        q = sa.select(t.c.date, t.c.score).where(t.c.asset_id == asset_id)
        if date_from:
            q = q.where(t.c.date >= date_from)
        if date_to:
            q = q.where(t.c.date <= date_to)
        for dt, score in s.execute(q.order_by(t.c.date)):
            result[sig_id].append((dt, score))
    return result


def get_signals_for_strategy(strategy_id: int) -> list[SignalDefinition]:
    s = get_session()
    strat = s.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strat is None:
        return []
    sig_ids = list({c.signal_id for c in strat.components})
    return s.query(SignalDefinition).filter(SignalDefinition.id.in_(sig_ids)).order_by(SignalDefinition.name).all()


def get_all_signals_flat(user_id: int | None = None,
                         is_admin: bool = True) -> list[SignalDefinition]:
    """Default admin (todas) para compatibilidad; las pantallas pasan el
    viewer real para ver solo públicas + propias."""
    from app.services.visibility import visible_filter
    s = get_session()
    return (s.query(SignalDefinition)
            .filter(visible_filter(SignalDefinition, user_id, is_admin))
            .order_by(SignalDefinition.name).all())
