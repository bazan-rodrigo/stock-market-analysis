"""
Servicio de señales.
Evalúa cada SignalDefinition contra indicator_snapshot / group_indicator_snapshot
y persiste los resultados en signal_value / group_signal_value.
"""
import logging
from datetime import date as date_type

from app.database import get_session
from app.models import (
    Asset,
    GroupIndicatorSnapshot,
    GroupSignalValue,
    IndicatorSnapshot,
    SignalDefinition,
    SignalValue,
)
from app.services import signal_engine

logger = logging.getLogger(__name__)


def _get_indicator_value(isnap: IndicatorSnapshot, key: str):
    """Lee el campo `key` del IndicatorSnapshot."""
    return getattr(isnap, key, None)


def _get_group_indicator_value(gsnap: GroupIndicatorSnapshot, key: str):
    """Lee el campo `key` del GroupIndicatorSnapshot."""
    return getattr(gsnap, key, None)


def _build_composite_scores(
    signals: list[SignalDefinition],
    asset_scores: dict[str, float | None],
) -> dict[str, float | None]:
    """
    Evalúa señales composite en orden topológico simple (dependencias ya evaluadas).
    Las señales composite que referencien otras composite se evalúan hasta 3 pasos.
    """
    import json

    composite = [s for s in signals if s.formula_type == "composite"]
    for _ in range(3):  # max anidamiento
        for sig in composite:
            if sig.key in asset_scores:
                continue
            score = signal_engine.evaluate(
                sig.formula_type, sig.params, None, asset_scores
            )
            asset_scores[sig.key] = score
    return asset_scores


def compute_signal_values(snap_date: date_type) -> int:
    """
    Calcula signal_value para todos los activos y todas las señales para snap_date.
    Devuelve cantidad de valores escritos.
    """
    s = get_session()

    signals = s.query(SignalDefinition).all()
    if not signals:
        return 0

    asset_signals  = [sg for sg in signals if sg.source == "asset"]
    group_signals  = [sg for sg in signals if sg.source == "group"]
    composite_sigs = [sg for sg in signals if sg.formula_type == "composite"]

    # Cargar todos los indicator_snapshots del día
    isnaps: dict[int, IndicatorSnapshot] = {
        sn.asset_id: sn
        for sn in s.query(IndicatorSnapshot).filter(IndicatorSnapshot.date == snap_date).all()
    }

    if not isnaps:
        logger.info("signal_service: sin indicator_snapshots para %s", snap_date)
        return 0

    # Cargar todos los group_indicator_snapshots del día indexados por (group_type, group_id)
    gsnaps: dict[tuple, GroupIndicatorSnapshot] = {
        (gs.group_type, gs.group_id): gs
        for gs in s.query(GroupIndicatorSnapshot).filter(GroupIndicatorSnapshot.date == snap_date).all()
    }

    # Cargar info de grupo de cada activo (sector_id, market_id)
    asset_groups: dict[int, dict] = {
        a.id: {"sector": a.sector_id, "market": a.market_id}
        for a in s.query(Asset.id, Asset.sector_id, Asset.market_id).all()
    }

    written = 0

    for asset_id, isnap in isnaps.items():
        # 1. Señales de activo (non-composite) primero
        asset_scores: dict[str, float | None] = {}

        for sig in asset_signals:
            if sig.formula_type == "composite":
                continue
            value = _get_indicator_value(isnap, sig.indicator_key) if sig.indicator_key else None
            score = signal_engine.evaluate(sig.formula_type, sig.params, value)
            asset_scores[sig.key] = score

        # 2. Señales de grupo (non-composite): buscar el grupo del activo
        groups = asset_groups.get(asset_id, {})
        for sig in group_signals:
            if sig.formula_type == "composite":
                continue
            group_id = groups.get(sig.group_type)
            if group_id is None:
                asset_scores[sig.key] = None
                continue
            gsnap = gsnaps.get((sig.group_type, group_id))
            if gsnap is None:
                asset_scores[sig.key] = None
                continue
            value = _get_group_indicator_value(gsnap, sig.indicator_key) if sig.indicator_key else None
            score = signal_engine.evaluate(sig.formula_type, sig.params, value)
            asset_scores[sig.key] = score

        # 3. Señales composite (pueden depender de cualquier otra)
        _build_composite_scores(signals, asset_scores)

        # 4. Persistir
        for sig in signals:
            score = asset_scores.get(sig.key)
            if score is None:
                continue

            sv = (
                s.query(SignalValue)
                .filter(
                    SignalValue.signal_id == sig.id,
                    SignalValue.asset_id == asset_id,
                    SignalValue.date == snap_date,
                )
                .first()
            )
            if sv is None:
                sv = SignalValue(signal_id=sig.id, asset_id=asset_id, date=snap_date)
                s.add(sv)
            sv.score = score
            written += 1

    s.commit()
    logger.info("signal_service: %d signal_value escritos para %s", written, snap_date)
    return written


def compute_group_signal_values(snap_date: date_type) -> int:
    """
    Calcula group_signal_value para todas las señales de grupo y cada grupo del día.
    Devuelve cantidad de valores escritos.
    """
    s = get_session()

    group_signals = (
        s.query(SignalDefinition).filter(SignalDefinition.source == "group").all()
    )
    if not group_signals:
        return 0

    gsnaps = (
        s.query(GroupIndicatorSnapshot)
        .filter(GroupIndicatorSnapshot.date == snap_date)
        .all()
    )

    written = 0

    for gsnap in gsnaps:
        for sig in group_signals:
            if sig.group_type and sig.group_type != gsnap.group_type:
                continue
            value = _get_group_indicator_value(gsnap, sig.indicator_key) if sig.indicator_key else None
            score = signal_engine.evaluate(sig.formula_type, sig.params, value)
            if score is None:
                continue

            gsv = (
                s.query(GroupSignalValue)
                .filter(
                    GroupSignalValue.signal_id == sig.id,
                    GroupSignalValue.group_type == gsnap.group_type,
                    GroupSignalValue.group_id == gsnap.group_id,
                    GroupSignalValue.date == snap_date,
                )
                .first()
            )
            if gsv is None:
                gsv = GroupSignalValue(
                    signal_id=sig.id,
                    group_type=gsnap.group_type,
                    group_id=gsnap.group_id,
                    date=snap_date,
                )
                s.add(gsv)
            gsv.score = score
            written += 1

    s.commit()
    logger.info("signal_service: %d group_signal_value escritos para %s", written, snap_date)
    return written


def run_daily(snap_date: date_type | None = None) -> dict:
    """
    Pipeline diario de señales: calcula signal_value y group_signal_value.
    Devuelve resumen con conteos.
    """
    from datetime import date as dt_date

    if snap_date is None:
        snap_date = dt_date.today()

    asset_written = compute_signal_values(snap_date)
    group_written = compute_group_signal_values(snap_date)

    return {"date": str(snap_date), "signal_values": asset_written, "group_signal_values": group_written}
