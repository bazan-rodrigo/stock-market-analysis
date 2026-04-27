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

    # Info de grupo de cada activo (todas las dimensiones soportadas como group_type)
    asset_groups: dict[int, dict] = {
        a.id: {
            "sector":          a.sector_id,
            "market":          a.market_id,
            "industry":        a.industry_id,
            "country":         a.country_id,
            "instrument_type": a.instrument_type_id,
        }
        for a in s.query(
            Asset.id, Asset.sector_id, Asset.market_id,
            Asset.industry_id, Asset.country_id, Asset.instrument_type_id,
        ).all()
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


# ── CRUD ──────────────────────────────────────────────────────────────────────

def get_all_strategies() -> list:
    s = get_session()
    return s.query(Strategy).order_by(Strategy.id).all()


def save_strategy(
    name: str,
    components: list[dict],
    *,
    description: str | None = None,
    asset_filter: str | None = None,
    strategy_id: int | None = None,
) -> Strategy:
    from datetime import datetime as _dt
    from app.models import SignalDefinition

    s = get_session()
    if strategy_id:
        strat = s.query(Strategy).filter(Strategy.id == strategy_id).first()
        if strat is None:
            raise ValueError(f"Estrategia id={strategy_id} no encontrada.")
        for comp in list(strat.components):
            s.delete(comp)
        s.flush()
    else:
        strat = Strategy()
        strat.created_at = _dt.utcnow()
        s.add(strat)

    strat.name         = name
    strat.description  = description
    strat.asset_filter = asset_filter or None
    strat.updated_at   = _dt.utcnow()
    s.flush()

    for comp_data in components:
        sig_key = str(comp_data.get("signal_key") or "").strip()
        if not sig_key:
            raise ValueError("Cada componente requiere signal_key.")
        sig = s.query(SignalDefinition).filter(SignalDefinition.key == sig_key).first()
        if sig is None:
            raise ValueError(f"Señal '{sig_key}' no encontrada.")
        comp = StrategyComponent(
            strategy_id=strat.id,
            signal_id=sig.id,
            weight=float(comp_data.get("weight") or 1.0),
            scope=comp_data.get("scope") or None,
            group_type=comp_data.get("group_type") or None,
            group_id=comp_data.get("group_id") or None,
        )
        s.add(comp)

    s.commit()
    return strat


def delete_strategy(strategy_id: int) -> None:
    s = get_session()
    strat = s.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strat is None:
        raise ValueError(f"Estrategia id={strategy_id} no encontrada.")
    s.delete(strat)
    s.commit()


def get_strategy_results(strategy_id: int, snap_date) -> list[dict]:
    s = get_session()
    rows = (
        s.query(StrategyResult, Asset.ticker, Asset.name)
        .join(Asset, Asset.id == StrategyResult.asset_id)
        .filter(
            StrategyResult.strategy_id == strategy_id,
            StrategyResult.date == snap_date,
        )
        .order_by(StrategyResult.rank)
        .all()
    )
    return [
        {"rank": r.rank, "asset_id": r.asset_id,
         "ticker": ticker, "name": name, "score": r.score}
        for r, ticker, name in rows
    ]


def get_strategy_results_with_breakdown(
    strategy_id: int,
    snap_date,
    *,
    sector_id: int | None = None,
    market_id: int | None = None,
) -> tuple[list[dict], list[dict]]:
    """
    Devuelve (resultados, componentes) donde:
    - resultados: [{rank, asset_id, ticker, name, sector_id, market_id, score,
                    component_scores: {signal_key: score}}]
    - componentes: [{signal_key, signal_name, weight, scope, group_type}]
    """
    from app.models import SignalDefinition, SignalValue, GroupSignalValue

    s = get_session()
    strategy = s.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        return [], []

    components = strategy.components
    sig_ids = [c.signal_id for c in components]

    sigs_by_id = {
        sig.id: sig
        for sig in s.query(SignalDefinition)
        .filter(SignalDefinition.id.in_(sig_ids))
        .all()
    }

    # Resultado base
    q = (
        s.query(StrategyResult, Asset.ticker, Asset.name,
                Asset.sector_id, Asset.market_id)
        .join(Asset, Asset.id == StrategyResult.asset_id)
        .filter(
            StrategyResult.strategy_id == strategy_id,
            StrategyResult.date == snap_date,
        )
    )
    if sector_id is not None:
        q = q.filter(Asset.sector_id == sector_id)
    if market_id is not None:
        q = q.filter(Asset.market_id == market_id)
    q = q.order_by(StrategyResult.rank)
    rows = q.all()

    if not rows:
        return [], []

    asset_ids = [r.asset_id for r, *_ in rows]

    sv_map: dict[tuple, float] = {
        (sv.signal_id, sv.asset_id): sv.score
        for sv in s.query(SignalValue)
        .filter(
            SignalValue.signal_id.in_(sig_ids),
            SignalValue.asset_id.in_(asset_ids),
            SignalValue.date == snap_date,
        )
        .all()
    }

    gsv_map: dict[tuple, float] = {
        (gsv.signal_id, gsv.group_type, gsv.group_id): gsv.score
        for gsv in s.query(GroupSignalValue)
        .filter(
            GroupSignalValue.signal_id.in_(sig_ids),
            GroupSignalValue.date == snap_date,
        )
        .all()
    }

    asset_group_map: dict[int, dict] = {
        a.id: {"sector": a.sector_id, "market": a.market_id}
        for a in s.query(Asset).filter(Asset.id.in_(asset_ids)).all()
    }

    comp_meta = [
        {
            "signal_key":  sigs_by_id[c.signal_id].key  if c.signal_id in sigs_by_id else str(c.signal_id),
            "signal_name": sigs_by_id[c.signal_id].name if c.signal_id in sigs_by_id else "?",
            "weight":      c.weight,
            "scope":       c.scope,
            "group_type":  c.group_type,
        }
        for c in components
    ]

    # Fecha anterior con resultados para esta estrategia
    from sqlalchemy import distinct as _distinct
    prev_date_row = (
        s.query(_distinct(StrategyResult.date))
        .filter(
            StrategyResult.strategy_id == strategy_id,
            StrategyResult.date < snap_date,
        )
        .order_by(StrategyResult.date.desc())
        .first()
    )
    prev_date = prev_date_row[0] if prev_date_row else None

    prev_score_map: dict[int, float] = {}
    prev_rank_map:  dict[int, int]   = {}
    if prev_date:
        prev_rows = (
            s.query(StrategyResult.asset_id, StrategyResult.score, StrategyResult.rank)
            .filter(
                StrategyResult.strategy_id == strategy_id,
                StrategyResult.date == prev_date,
                StrategyResult.asset_id.in_(asset_ids),
            )
            .all()
        )
        prev_score_map = {r.asset_id: r.score for r in prev_rows}
        prev_rank_map  = {r.asset_id: r.rank  for r in prev_rows}

    results = []
    for r, ticker, name, s_id, m_id in rows:
        groups = asset_group_map.get(r.asset_id, {})
        comp_scores: dict[str, float | None] = {}

        for comp in components:
            sig = sigs_by_id.get(comp.signal_id)
            key = sig.key if sig else str(comp.signal_id)
            scope = comp.scope

            if scope is None or scope == "":
                score = sv_map.get((comp.signal_id, r.asset_id))
            elif scope == "own_group":
                grp_id = groups.get(comp.group_type)
                score = gsv_map.get((comp.signal_id, comp.group_type, grp_id)) if grp_id else None
            else:
                score = gsv_map.get((comp.signal_id, comp.group_type, comp.group_id))

            comp_scores[key] = score

        prev_sc   = prev_score_map.get(r.asset_id)
        prev_rk   = prev_rank_map.get(r.asset_id)
        delta_score = round(r.score - prev_sc, 4) if (prev_sc is not None and r.score is not None) else None
        delta_rank  = (prev_rk - r.rank)          if prev_rk is not None else None

        results.append({
            "rank":        r.rank,
            "asset_id":    r.asset_id,
            "ticker":      ticker,
            "name":        name or "—",
            "sector_id":   s_id,
            "market_id":   m_id,
            "score":       r.score,
            "prev_score":  prev_sc,
            "delta_score": delta_score,
            "delta_rank":  delta_rank,
            "comp_scores": comp_scores,
        })

    return results, comp_meta


def get_filter_options(strategy_id: int, snap_date) -> dict:
    """Devuelve opciones de sector y market para los activos con resultados."""
    from app.models import Sector, Market
    s = get_session()

    asset_ids = [
        r[0]
        for r in s.query(StrategyResult.asset_id)
        .filter(StrategyResult.strategy_id == strategy_id,
                StrategyResult.date == snap_date)
        .all()
    ]
    if not asset_ids:
        return {"sectors": [], "markets": []}

    sectors = (
        s.query(Asset.sector_id, Sector.name)
        .join(Sector, Sector.id == Asset.sector_id)
        .filter(Asset.id.in_(asset_ids), Asset.sector_id.isnot(None))
        .distinct()
        .order_by(Sector.name)
        .all()
    )
    markets = (
        s.query(Asset.market_id, Market.name)
        .join(Market, Market.id == Asset.market_id)
        .filter(Asset.id.in_(asset_ids), Asset.market_id.isnot(None))
        .distinct()
        .order_by(Market.name)
        .all()
    )
    return {
        "sectors": [{"label": n, "value": sid} for sid, n in sectors],
        "markets": [{"label": n, "value": mid} for mid, n in markets],
    }


def get_available_dates(strategy_id: int) -> list:
    """Devuelve las fechas con resultados para una estrategia, ordenadas desc."""
    from sqlalchemy import distinct
    s = get_session()
    dates = (
        s.query(distinct(StrategyResult.date))
        .filter(StrategyResult.strategy_id == strategy_id)
        .order_by(StrategyResult.date.desc())
        .all()
    )
    return [r[0] for r in dates]


def get_strategy_score_history(
    strategy_id: int,
    asset_ids: list[int],
    date_from=None,
    date_to=None,
) -> dict[int, list[tuple]]:
    """
    {asset_id: [(date, score, rank), ...]} ordenado por fecha asc.
    """
    s = get_session()
    q = (
        s.query(StrategyResult.asset_id, StrategyResult.date,
                StrategyResult.score, StrategyResult.rank)
        .filter(
            StrategyResult.strategy_id == strategy_id,
            StrategyResult.asset_id.in_(asset_ids),
        )
    )
    if date_from:
        q = q.filter(StrategyResult.date >= date_from)
    if date_to:
        q = q.filter(StrategyResult.date <= date_to)
    q = q.order_by(StrategyResult.date)

    result: dict[int, list] = {aid: [] for aid in asset_ids}
    for asset_id, dt, score, rank in q.all():
        result[asset_id].append((dt, score, rank))
    return result


def get_top_assets_for_strategy(strategy_id: int, snap_date, limit: int = 20) -> list[dict]:
    """Top activos por score en snap_date, para usar como sugerencia en el historial."""
    return get_strategy_results(strategy_id, snap_date)[:limit]


# ── Export / Import Excel ──────────────────────────────────────────────────────

def export_strategies_excel() -> bytes:
    import openpyxl
    from io import BytesIO
    from app.models import SignalDefinition

    strategies = get_all_strategies()
    wb = openpyxl.Workbook()

    ws_s = wb.active
    ws_s.title = "Estrategias"
    ws_s.append(["name", "description", "asset_filter"])

    ws_c = wb.create_sheet("Componentes")
    ws_c.append(["strategy_name", "signal_key", "weight", "scope", "group_type", "group_id"])

    s = get_session()
    for strat in strategies:
        ws_s.append([strat.name, strat.description or "", strat.asset_filter or ""])
        for comp in strat.components:
            sig = s.query(SignalDefinition).filter(SignalDefinition.id == comp.signal_id).first()
            ws_c.append([
                strat.name, sig.key if sig else "",
                comp.weight, comp.scope or "",
                comp.group_type or "", comp.group_id or "",
            ])

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def import_strategies_excel(file_bytes: bytes) -> list[dict]:
    import openpyxl
    from io import BytesIO

    wb = openpyxl.load_workbook(BytesIO(file_bytes))
    ws_s = wb.worksheets[0]
    rows_s = list(ws_s.iter_rows(values_only=True))
    if not rows_s:
        return []

    headers_s = [str(h).strip().lower() for h in rows_s[0]]
    strategies: dict[str, dict] = {}
    for row in rows_s[1:]:
        data = dict(zip(headers_s, row))
        name = str(data.get("name") or "").strip()
        if name:
            strategies[name] = {
                "description": data.get("description") or None,
                "asset_filter": data.get("asset_filter") or None,
                "components": [],
            }

    if len(wb.worksheets) > 1:
        ws_c = wb.worksheets[1]
        rows_c = list(ws_c.iter_rows(values_only=True))
        headers_c = [str(h).strip().lower() for h in rows_c[0]] if rows_c else []
        for row in rows_c[1:]:
            data = dict(zip(headers_c, row))
            sname = str(data.get("strategy_name") or "").strip()
            if sname in strategies:
                strategies[sname]["components"].append({
                    "signal_key": str(data.get("signal_key") or "").strip(),
                    "weight": float(data.get("weight") or 1.0),
                    "scope": str(data.get("scope") or "") or None,
                    "group_type": str(data.get("group_type") or "") or None,
                    "group_id": int(data.get("group_id")) if data.get("group_id") else None,
                })

    db = get_session()
    results = []
    for name, sdata in strategies.items():
        existing = db.query(Strategy).filter(Strategy.name == name).first()
        sid = existing.id if existing else None
        try:
            strat = save_strategy(
                name=name,
                description=sdata["description"],
                asset_filter=sdata["asset_filter"],
                components=sdata["components"],
                strategy_id=sid,
            )
            results.append({"name": name, "status": "ok", "detail": f"id={strat.id}"})
        except Exception as exc:
            results.append({"name": name, "status": "error", "detail": str(exc)})

    return results
