"""
Servicio de estrategias.
Combina signal_value ponderados según la configuración de strategy_component
y persiste el score final + ranking en strategy_result.
"""
import logging
from datetime import date as date_type

from app.database import get_session
from app.models import (
    Asset,
    GroupSignalValue,
    SignalValue,
    Strategy,
    StrategyComponent,
    StrategyResult,
)

logger = logging.getLogger(__name__)


def _compute_asset_score(
    components: list[StrategyComponent],
    asset_id: int,
    asset_groups: dict[int, dict],
    signal_scores: dict[tuple, float],
    group_scores: dict[tuple, float],
) -> float | None:
    """
    Calcula el score ponderado de una estrategia para un activo.

    signal_scores: {(signal_id, asset_id): score}
    group_scores:  {(signal_id, group_type, group_id): score}
    """
    total_weight = 0.0
    weighted_sum = 0.0

    groups = asset_groups.get(asset_id, {})

    for comp in components:
        scope = comp.scope

        if scope is None or scope == "":
            # Señal de activo directo
            score = signal_scores.get((comp.signal_id, asset_id))
        elif scope == "own_group":
            # Grupo al que pertenece el activo según group_type del componente
            group_id = groups.get(comp.group_type)
            if group_id is None:
                continue
            score = group_scores.get((comp.signal_id, comp.group_type, group_id))
        elif scope == "specific_group":
            # Grupo fijo definido en el componente
            score = group_scores.get((comp.signal_id, comp.group_type, comp.group_id))
        else:
            continue

        if score is None:
            continue

        weight = comp.weight or 1.0
        weighted_sum += score * weight
        total_weight += weight

    if total_weight == 0:
        return None
    return round(weighted_sum / total_weight, 4)


def compute_strategy_results(strategy_id: int, snap_date: date_type) -> int:
    """
    Calcula StrategyResult para todos los activos para strategy_id y snap_date.
    Devuelve cantidad de resultados escritos.
    """
    s = get_session()

    strategy = s.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        logger.warning("strategy_service: strategy_id=%d no encontrada", strategy_id)
        return 0

    components = strategy.components
    if not components:
        return 0

    signal_ids = list({c.signal_id for c in components})

    # Cargar todos los signal_value relevantes del día
    rows = (
        s.query(SignalValue.signal_id, SignalValue.asset_id, SignalValue.score)
        .filter(
            SignalValue.signal_id.in_(signal_ids),
            SignalValue.date == snap_date,
        )
        .all()
    )
    signal_scores: dict[tuple, float] = {
        (r.signal_id, r.asset_id): r.score for r in rows
    }

    # Cargar group_signal_value relevantes del día
    grows = (
        s.query(
            GroupSignalValue.signal_id,
            GroupSignalValue.group_type,
            GroupSignalValue.group_id,
            GroupSignalValue.score,
        )
        .filter(
            GroupSignalValue.signal_id.in_(signal_ids),
            GroupSignalValue.date == snap_date,
        )
        .all()
    )
    group_scores: dict[tuple, float] = {
        (r.signal_id, r.group_type, r.group_id): r.score for r in grows
    }

    # Info de grupo de cada activo
    asset_groups: dict[int, dict] = {
        a.id: {"sector": a.sector_id, "market": a.market_id}
        for a in s.query(Asset.id, Asset.sector_id, Asset.market_id).all()
    }

    # Calcular scores por activo
    asset_ids = list(asset_groups.keys())
    scored: list[tuple[int, float]] = []

    for asset_id in asset_ids:
        score = _compute_asset_score(
            components, asset_id, asset_groups, signal_scores, group_scores
        )
        if score is not None:
            scored.append((asset_id, score))

    # Ranking: mayor score → rank 1
    scored.sort(key=lambda x: x[1], reverse=True)

    written = 0
    for rank, (asset_id, score) in enumerate(scored, start=1):
        sr = (
            s.query(StrategyResult)
            .filter(
                StrategyResult.strategy_id == strategy_id,
                StrategyResult.asset_id == asset_id,
                StrategyResult.date == snap_date,
            )
            .first()
        )
        if sr is None:
            sr = StrategyResult(
                strategy_id=strategy_id,
                asset_id=asset_id,
                date=snap_date,
            )
            s.add(sr)
        sr.score = score
        sr.rank = rank
        written += 1

    s.commit()
    logger.info(
        "strategy_service: %d resultados escritos para strategy_id=%d en %s",
        written, strategy_id, snap_date,
    )
    return written


def compute_all_strategies(snap_date: date_type) -> dict:
    """Calcula los resultados de todas las estrategias para snap_date."""
    s = get_session()
    strategies = s.query(Strategy.id).all()
    total = 0
    for (sid,) in strategies:
        total += compute_strategy_results(sid, snap_date)
    return {"date": str(snap_date), "strategy_results": total}


def run_daily(snap_date: date_type | None = None) -> dict:
    """Pipeline diario de estrategias."""
    from datetime import date as dt_date

    if snap_date is None:
        snap_date = dt_date.today()

    return compute_all_strategies(snap_date)
