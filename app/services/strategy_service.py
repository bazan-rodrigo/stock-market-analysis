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
from app.services import strategy_filter

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


def compute_strategy_results(strategy_id: int, target_date: date_type) -> int:
    """
    Calcula StrategyResult para todos los activos para strategy_id y target_date.
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
            SignalValue.date == target_date,
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
            GroupSignalValue.date == target_date,
        )
        .all()
    )
    group_scores: dict[tuple, float] = {
        (r.signal_id, r.group_type, r.group_id): r.score for r in grows
    }

    # Solo cargar grupos de activos que aparecen en los datos de señales del día
    asset_ids_with_data = list({asset_id for _, asset_id in signal_scores})
    if asset_ids_with_data:
        q = s.query(
            Asset.id, Asset.sector_id, Asset.market_id,
            Asset.industry_id, Asset.country_id, Asset.instrument_type_id,
        ).filter(Asset.id.in_(asset_ids_with_data))
        asset_groups: dict[int, dict] = {
            a.id: {
                "sector":          a.sector_id,
                "market":          a.market_id,
                "industry":        a.industry_id,
                "country":         a.country_id,
                "instrument_type": a.instrument_type_id,
            }
            for a in q.all()
        }
    else:
        asset_groups = {}

    # Filtro de elegibilidad: quien no cumple el árbol de condiciones no
    # participa del scoring ni aparece en strategy_result
    asset_ids = list(asset_groups.keys())
    filter_tree = strategy_filter.parse_tree(strategy.filter_conditions)
    if filter_tree is not None and asset_ids:
        operand_values = strategy_filter.load_operand_values(
            s, filter_tree, target_date)
        asset_ids = [
            aid for aid in asset_ids
            if strategy_filter.evaluate_tree(
                filter_tree, aid, operand_values, asset_groups[aid])
        ]

    # Calcular scores por activo
    scored: list[tuple[int, float]] = []

    for asset_id in asset_ids:
        score = _compute_asset_score(
            components, asset_id, asset_groups, signal_scores, group_scores
        )
        if score is not None:
            scored.append((asset_id, score))

    # Ranking: mayor score → rank 1
    scored.sort(key=lambda x: x[1], reverse=True)

    # Pre-cargar StrategyResults del día para esta estrategia
    existing_srs: dict[int, StrategyResult] = {
        sr.asset_id: sr
        for sr in s.query(StrategyResult).filter(
            StrategyResult.strategy_id == strategy_id,
            StrategyResult.date == target_date,
        ).all()
    }

    # Eliminar resultados de un recálculo previo del mismo día cuyos activos
    # ya no obtienen score (evita ranks duplicados u obsoletos)
    scored_ids = {asset_id for asset_id, _ in scored}
    for asset_id, sr in list(existing_srs.items()):
        if asset_id not in scored_ids:
            s.delete(sr)
            del existing_srs[asset_id]

    written = 0
    for rank, (asset_id, score) in enumerate(scored, start=1):
        sr = existing_srs.get(asset_id)
        if sr is None:
            sr = StrategyResult(
                strategy_id=strategy_id,
                asset_id=asset_id,
                date=target_date,
            )
            s.add(sr)
            existing_srs[asset_id] = sr
        sr.score = score
        sr.rank = rank
        written += 1

    s.commit()
    logger.info(
        "strategy_service: %d resultados escritos para strategy_id=%d en %s",
        written, strategy_id, target_date,
    )
    return written


def compute_all_strategies(target_date: date_type) -> dict:
    """Calcula los resultados de todas las estrategias para target_date."""
    s = get_session()
    strategies = s.query(Strategy.id).all()
    total = 0
    for (sid,) in strategies:
        total += compute_strategy_results(sid, target_date)
    return {"date": str(target_date), "strategy_results": total}


def run_daily(target_date: date_type | None = None) -> dict:
    """Pipeline diario de estrategias."""
    if target_date is None:
        from app.services.group_score_service import get_default_target_date
        target_date = get_default_target_date()

    return compute_all_strategies(target_date)


# ── CRUD ──────────────────────────────────────────────────────────────────────

def get_all_strategies() -> list:
    s = get_session()
    return s.query(Strategy).order_by(Strategy.id).all()


def get_visible_strategies(user_id: int | None, is_admin: bool) -> list:
    """Estrategias visibles para el usuario: públicas + propias (admin:
    todas). Para pantallas y dropdowns — el pipeline usa get_all_strategies."""
    from app.services.visibility import visible_filter
    s = get_session()
    return (s.query(Strategy)
            .filter(visible_filter(Strategy, user_id, is_admin))
            .order_by(Strategy.id).all())


def _validate_signal_refs_visibility(s, *, owner_id, is_public,
                                     signal_keys: set[str]) -> None:
    """Estrategia pública solo referencia señales públicas; privada,
    públicas + del mismo dueño (componentes y operandos del filtro)."""
    from app.models import SignalDefinition
    from app.services.visibility import can_reference

    if not signal_keys:
        return
    for ref in s.query(SignalDefinition).filter(
            SignalDefinition.key.in_(signal_keys)).all():
        if not can_reference(owner_id, is_public, ref.owner_id, ref.is_public):
            if is_public:
                raise ValueError(
                    f"Una estrategia pública no puede usar la señal "
                    f"privada '{ref.key}' — publicala primero.")
            raise ValueError(
                f"No podés usar la señal privada '{ref.key}' de otro usuario.")


def _filter_signal_keys(filter_conditions: str | None) -> set[str]:
    """Keys de señal usadas como operando en el filtro de elegibilidad."""
    tree = strategy_filter.parse_tree(filter_conditions)
    if tree is None:
        return set()
    return {k for t, k, _res in strategy_filter.collect_operands(tree)
            if t == "signal" and k}


def get_strategy_by_id(strategy_id: int) -> Strategy | None:
    s = get_session()
    return s.query(Strategy).filter(Strategy.id == strategy_id).first()


def validate_filter_conditions(filter_conditions: str | None) -> list[str]:
    """Errores del árbol de condiciones contra los catálogos vigentes
    (indicadores, señales, valores discretos). Vacío si es válido o NULL."""
    import json
    from app.models import SignalDefinition
    from app.models.indicator_definition import IndicatorDefinition
    from app.services.indicator_catalog import CATEGORICAL_VALUES

    if not filter_conditions:
        return []
    try:
        tree = json.loads(filter_conditions)
    except (json.JSONDecodeError, TypeError):
        return ["filtro: JSON inválido"]
    if not tree:
        return []

    s = get_session()
    indicator_codes = {
        d.code: d.type
        for d in s.query(IndicatorDefinition.code, IndicatorDefinition.type).all()
    }
    signal_keys = {r.key for r in s.query(SignalDefinition.key).all()}
    return strategy_filter.validate_tree(
        tree,
        indicator_codes=indicator_codes,
        signal_keys=signal_keys,
        categorical_values=CATEGORICAL_VALUES,
    )


def save_strategy(
    name: str,
    components: list[dict],
    *,
    description: str | None = None,
    filter_conditions: str | None = None,
    strategy_id: int | None = None,
    is_public: bool | None = None,
    acting_user_id: int | None = None,
    acting_is_admin: bool = True,
) -> Strategy:
    """is_public None = conservar el valor actual (o privada si es nueva).
    acting_* identifican a quién guarda: en alta queda como dueño; en
    edición se valida el permiso (default admin para scripts/tests)."""
    from datetime import datetime as _dt
    from app.models import SignalDefinition
    from app.services.visibility import can_edit

    filter_errors = validate_filter_conditions(filter_conditions)
    if filter_errors:
        raise ValueError("; ".join(filter_errors))

    s = get_session()
    if strategy_id:
        strat = s.query(Strategy).filter(Strategy.id == strategy_id).first()
        if strat is None:
            raise ValueError(f"Estrategia id={strategy_id} no encontrada.")
        if not can_edit(strat.owner_id, acting_user_id, acting_is_admin):
            raise ValueError("Solo el dueño o un administrador pueden "
                             "editar esta estrategia.")
        new_public = strat.is_public if is_public is None else bool(is_public)
        for comp in list(strat.components):
            s.delete(comp)
        s.flush()
    else:
        strat = Strategy()
        strat.owner_id   = acting_user_id
        strat.created_at = _dt.utcnow()
        s.add(strat)
        new_public = bool(is_public)

    _validate_signal_refs_visibility(
        s, owner_id=strat.owner_id, is_public=new_public,
        signal_keys={str(c.get("signal_key") or "").strip()
                     for c in components if c.get("signal_key")}
                    | _filter_signal_keys(filter_conditions))

    strat.name              = name
    strat.description       = description
    strat.filter_conditions = filter_conditions or None
    strat.is_public         = new_public
    strat.updated_at        = _dt.utcnow()
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


def delete_strategy(strategy_id: int, *, acting_user_id: int | None = None,
                    acting_is_admin: bool = True) -> None:
    from app.services.visibility import can_edit
    s = get_session()
    strat = s.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strat is None:
        raise ValueError(f"Estrategia id={strategy_id} no encontrada.")
    if not can_edit(strat.owner_id, acting_user_id, acting_is_admin):
        raise ValueError(f"Solo el dueño o un administrador pueden "
                         f"eliminar la estrategia '{strat.name}'.")
    s.delete(strat)
    s.commit()


def get_strategy_results(strategy_id: int, target_date) -> list[dict]:
    s = get_session()
    rows = (
        s.query(StrategyResult, Asset.ticker, Asset.name)
        .join(Asset, Asset.id == StrategyResult.asset_id)
        .filter(
            StrategyResult.strategy_id == strategy_id,
            StrategyResult.date == target_date,
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
    target_date,
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
            StrategyResult.date == target_date,
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
        for sv in s.query(SignalValue.signal_id, SignalValue.asset_id, SignalValue.score)
        .filter(
            SignalValue.signal_id.in_(sig_ids),
            SignalValue.asset_id.in_(asset_ids),
            SignalValue.date == target_date,
        )
        .all()
    }

    gsv_map: dict[tuple, float] = {
        (gsv.signal_id, gsv.group_type, gsv.group_id): gsv.score
        for gsv in s.query(
            GroupSignalValue.signal_id,
            GroupSignalValue.group_type,
            GroupSignalValue.group_id,
            GroupSignalValue.score,
        )
        .filter(
            GroupSignalValue.signal_id.in_(sig_ids),
            GroupSignalValue.date == target_date,
        )
        .all()
    }

    asset_group_map: dict[int, dict] = {
        row.id: {"sector": row.sector_id, "market": row.market_id}
        for row in s.query(Asset.id, Asset.sector_id, Asset.market_id)
                    .filter(Asset.id.in_(asset_ids)).all()
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
            StrategyResult.date < target_date,
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


def get_filter_options(strategy_id: int, target_date) -> dict:
    """Devuelve opciones de sector y market para los activos con resultados."""
    from app.models import Sector, Market
    s = get_session()

    asset_ids = [
        r[0]
        for r in s.query(StrategyResult.asset_id)
        .filter(StrategyResult.strategy_id == strategy_id,
                StrategyResult.date == target_date)
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


def get_top_assets_for_strategy(strategy_id: int, target_date, limit: int = 20) -> list[dict]:
    """Top activos por score en target_date, para usar como sugerencia en el historial."""
    return get_strategy_results(strategy_id, target_date)[:limit]


# ── Export / Import Excel ──────────────────────────────────────────────────────

def export_strategies_excel() -> bytes:
    import openpyxl
    from io import BytesIO
    from app.models import SignalDefinition
    from app.services.visibility import publica_str

    strategies = get_all_strategies()
    wb = openpyxl.Workbook()

    ws_s = wb.active
    ws_s.title = "Estrategias"
    ws_s.append(["name", "description", "filter_conditions", "publica"])

    ws_c = wb.create_sheet("Componentes")
    ws_c.append(["strategy_name", "signal_key", "weight", "scope", "group_type", "group_id"])

    s = get_session()
    all_sig_ids = {comp.signal_id for strat in strategies for comp in strat.components}
    sigs_by_id = {
        sig.id: sig
        for sig in s.query(SignalDefinition).filter(SignalDefinition.id.in_(all_sig_ids)).all()
    } if all_sig_ids else {}

    for strat in strategies:
        ws_s.append([strat.name, strat.description or "",
                     strat.filter_conditions or "",
                     publica_str(strat.is_public)])
        for comp in strat.components:
            sig = sigs_by_id.get(comp.signal_id)
            ws_c.append([
                strat.name, sig.key if sig else "",
                comp.weight, comp.scope or "",
                comp.group_type or "", comp.group_id or "",
            ])

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def import_strategies_excel(file_bytes: bytes,
                            owner_id: int | None = None) -> list[dict]:
    """La columna `publica` (sí/no; ausente = sí) define la visibilidad.
    owner_id = quien importa: dueño de las estrategias NUEVAS (las
    existentes conservan el suyo)."""
    import openpyxl
    from io import BytesIO
    from datetime import datetime as _dt
    from app.models import SignalDefinition
    from app.services.visibility import can_reference, parse_publica

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
            # Compatibilidad: Excel exportados antes de la migración 0061
            # traen "asset_filter" (JSON plano) en vez de "filter_conditions"
            filter_conditions = (
                data.get("filter_conditions")
                or strategy_filter.legacy_asset_filter_to_tree(
                    data.get("asset_filter"))
                or None
            )
            entry = {
                "description": data.get("description") or None,
                "filter_conditions": filter_conditions,
                "components": [],
                "is_public": True,
            }
            try:
                entry["is_public"] = parse_publica(data.get("publica"))
            except ValueError as exc:
                entry.setdefault("errors", []).append(str(exc))
            strategies[name] = entry

    if len(wb.worksheets) > 1:
        ws_c = wb.worksheets[1]
        rows_c = list(ws_c.iter_rows(values_only=True))
        headers_c = [str(h).strip().lower() for h in rows_c[0]] if rows_c else []
        for row in rows_c[1:]:
            data = dict(zip(headers_c, row))
            sname = str(data.get("strategy_name") or "").strip()
            if sname not in strategies:
                continue
            try:
                strategies[sname]["components"].append({
                    "signal_key": str(data.get("signal_key") or "").strip(),
                    "weight": float(data.get("weight") or 1.0),
                    "scope": str(data.get("scope") or "") or None,
                    "group_type": str(data.get("group_type") or "") or None,
                    "group_id": int(data.get("group_id")) if data.get("group_id") else None,
                })
            except (TypeError, ValueError) as exc:
                strategies[sname].setdefault("errors", []).append(
                    f"componente inválido: {exc}")

    db = get_session()

    # ── Pasada 1: validación completa sin escribir ────────────────────────────
    all_keys = {
        c["signal_key"]
        for sdata in strategies.values()
        for c in sdata["components"] if c["signal_key"]
    }
    sigs_by_key = {
        r.key: r
        for r in db.query(SignalDefinition)
                   .filter(SignalDefinition.key.in_(all_keys)).all()
    } if all_keys else {}
    sig_ids_by_key = {k: r.id for k, r in sigs_by_key.items()}
    existing_by_name = {
        st.name: st for st in db.query(Strategy)
        .filter(Strategy.name.in_(strategies)).all()
    } if strategies else {}

    invalid = False
    for name, sdata in strategies.items():
        errors = sdata.setdefault("errors", [])
        existing = existing_by_name.get(name)
        sdata["owner_id"] = existing.owner_id if existing else owner_id
        for comp in sdata["components"]:
            if not comp["signal_key"]:
                errors.append("componente sin signal_key")
            elif comp["signal_key"] not in sig_ids_by_key:
                errors.append(f"señal '{comp['signal_key']}' no encontrada")
        errors.extend(validate_filter_conditions(sdata["filter_conditions"]))
        # Visibilidad de las señales referenciadas (componentes + filtro)
        ref_keys = ({c["signal_key"] for c in sdata["components"]
                     if c["signal_key"]}
                    | _filter_signal_keys(sdata["filter_conditions"]))
        for rk in sorted(ref_keys):
            ref = sigs_by_key.get(rk) or db.query(SignalDefinition).filter(
                SignalDefinition.key == rk).first()
            if ref is not None and not can_reference(
                    sdata["owner_id"], sdata["is_public"],
                    ref.owner_id, ref.is_public):
                errors.append(
                    f"estrategia {'pública' if sdata['is_public'] else 'privada'} "
                    f"usa la señal privada '{rk}' de otro dueño")
        if errors:
            invalid = True

    if invalid:
        return [
            {"name": name,
             "status": "error" if sdata["errors"] else "omitido",
             "detail": "; ".join(sdata["errors"])
                       or "el archivo contiene errores; no se importó nada"}
            for name, sdata in strategies.items()
        ]

    # ── Pasada 2: escribir todo en una sola transacción ───────────────────────
    results: list[dict] = []
    try:
        for name, sdata in strategies.items():
            existing = db.query(Strategy).filter(Strategy.name == name).first()
            if existing:
                strat = existing
                for comp in list(strat.components):
                    db.delete(comp)
                db.flush()
            else:
                strat = Strategy()
                strat.owner_id   = owner_id
                strat.created_at = _dt.utcnow()
                db.add(strat)

            strat.name              = name
            strat.description       = sdata["description"]
            strat.filter_conditions = sdata["filter_conditions"] or None
            strat.is_public         = sdata["is_public"]
            strat.updated_at        = _dt.utcnow()
            db.flush()

            for comp_data in sdata["components"]:
                db.add(StrategyComponent(
                    strategy_id=strat.id,
                    signal_id=sig_ids_by_key[comp_data["signal_key"]],
                    weight=comp_data["weight"],
                    scope=comp_data["scope"],
                    group_type=comp_data["group_type"],
                    group_id=comp_data["group_id"],
                ))

            db.flush()
            results.append({"name": name, "status": "ok", "detail": f"id={strat.id}"})
        db.commit()
    except Exception as exc:
        db.rollback()
        names  = list(strategies)
        failed = names[len(results)] if len(results) < len(names) else "?"
        return [
            {"name": n,
             "status": "error" if n == failed else "revertido",
             "detail": str(exc) if n == failed
                       else "revertido por error en otra estrategia"}
            for n in names
        ]

    return results
