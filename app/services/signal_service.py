"""
Servicio de señales.
Evalúa cada SignalDefinition contra indicadores (ind_*) / group_scores
y persiste los resultados en signal_value / group_signal_value.
"""
import logging
import sqlalchemy as sa
from datetime import date as date_type

from app.database import get_session
from app.models import (
    Asset,
    GroupScore,
    GroupSignalValue,
    SignalDefinition,
    SignalValue,
)
from app.models.indicator_definition import IndicatorDefinition
from app.models.indicator_store import query_values_asof
from app.models.price import Price
from app.services import signal_engine

logger = logging.getLogger(__name__)


_VALID_GROUP_INDICATOR_KEYS = frozenset({"regime_score_d", "regime_score_w", "regime_score_m"})

# Indicadores virtuales: no tienen tabla ind_*, se leen de otra fuente
_VIRTUAL_CODES = frozenset({"last_close"})


def _load_virtual(s, code: str, target_date) -> dict:
    """Carga un indicador virtual. Retorna {asset_id: value}."""
    if code == "last_close":
        rows = s.query(Price.asset_id, Price.close).filter(Price.date == target_date).all()
        return {r[0]: float(r[1]) for r in rows if r[1] is not None}
    return {}


def _get_group_indicator_value(gscore: GroupScore, key: str):
    if key not in _VALID_GROUP_INDICATOR_KEYS:
        logger.warning("signal_service: indicator_key '%s' no es un campo válido de GroupScore", key)
        return None
    return getattr(gscore, key)


def _composite_refs(sig: SignalDefinition) -> set[str]:
    """Keys de señales referenciadas por una composite."""
    import json
    try:
        components = json.loads(sig.params).get("components", [])
    except (json.JSONDecodeError, TypeError):
        return set()
    return {c.get("signal_key") for c in components if c.get("signal_key")}


def _build_composite_scores(
    signals: list[SignalDefinition],
    asset_scores: dict[str, float | None],
    *,
    refs_by_key: dict[str, set] | None = None,
    params_by_id: dict[int, dict | None] | None = None,
) -> dict[str, float | None]:
    composite      = [s for s in signals if s.formula_type == "composite"]
    composite_keys = {s.key for s in composite}
    pending        = {s.key: s for s in composite if s.key not in asset_scores}

    def _params(sig):
        return params_by_id.get(sig.id) if params_by_id is not None else None

    # Resolver en orden de dependencias: una composite espera a que las
    # composites que referencia ya estén evaluadas.
    while pending:
        progressed = False
        for key, sig in list(pending.items()):
            refs = (refs_by_key.get(key) if refs_by_key is not None
                    else _composite_refs(sig))
            if refs is None:
                refs = _composite_refs(sig)
            if any(r in composite_keys and r not in asset_scores for r in refs):
                continue
            asset_scores[key] = signal_engine.evaluate(
                sig.formula_type, sig.params, None, asset_scores,
                params=_params(sig),
            )
            del pending[key]
            progressed = True
        if not progressed:
            break

    # Ciclos entre composites: evaluar con los scores disponibles
    if pending:
        logger.warning(
            "signal_service: referencias circulares entre composites: %s",
            sorted(pending),
        )
        for key, sig in pending.items():
            asset_scores[key] = signal_engine.evaluate(
                sig.formula_type, sig.params, None, asset_scores,
                params=_params(sig),
            )

    return asset_scores


def compute_signal_values(target_date: date_type,
                          only_signal_ids: set[int] | None = None) -> int:
    """
    Calcula signal_value para todos los activos para target_date.
    Lee valores desde cada tabla ind_{code} por separado.

    only_signal_ids acota el cálculo a un subconjunto (alcance por señal o
    estrategia del backfill) — el llamador es responsable de que incluya las
    dependencias de las composites (ver _scope_signal_ids).
    """
    s = get_session()

    signals = s.query(SignalDefinition).all()
    if only_signal_ids is not None:
        signals = [sg for sg in signals if sg.id in only_signal_ids]
    if not signals:
        return 0

    # Params parseados una sola vez por señal (evita json.loads por activo)
    import json as _json
    params_by_id: dict[int, dict | None] = {}
    for sig in signals:
        try:
            params_by_id[sig.id] = _json.loads(sig.params)
        except (TypeError, ValueError):
            params_by_id[sig.id] = None
    refs_by_key = {
        sig.key: {
            c.get("signal_key")
            for c in (params_by_id.get(sig.id) or {}).get("components", [])
            if c.get("signal_key")
        }
        for sig in signals if sig.formula_type == "composite"
    }

    asset_signals  = [sg for sg in signals if sg.source == "asset"]
    group_signals  = [sg for sg in signals if sg.source == "group"]

    # Descubrir qué indicator_keys necesitan las señales de activo
    needed_codes = {sg.indicator_key for sg in asset_signals if sg.indicator_key}

    # keep_history por código, para decidir de dónde leer cada uno
    keep_history_by_code = {
        d.code: d.keep_history for d in s.query(IndicatorDefinition).all()
    }

    hist_codes = {c for c in needed_codes - _VIRTUAL_CODES
                  if keep_history_by_code.get(c)}
    nohist_codes = {c for c in needed_codes - _VIRTUAL_CODES
                    if keep_history_by_code.get(c) is False}
    virtual_to_load = needed_codes & _VIRTUAL_CODES

    # Construir {asset_id: {code: value}} leyendo cada ind_* table con
    # lookup as-of (última fila <= target_date): los indicadores
    # semanales/mensuales se guardan con fechas de fin de período, un match
    # exacto los dejaba en 0 scores casi cualquier día (tendencia_w/m,
    # volatilidad_w/m nunca puntuaban)
    isnaps: dict[int, dict] = {}
    for code in hist_codes:
        try:
            values_by_asset = query_values_asof(s, code, target_date)
        except Exception:
            continue
        for asset_id_row, value in values_by_asset.items():
            isnaps.setdefault(asset_id_row, {})[code] = value

    # Indicadores sin historia (drawdown_current, etc.): solo existe el valor
    # vigente en current_indicator_values. Usarlo únicamente cuando
    # target_date ES la fecha vigente — para fechas pasadas sería sesgo de
    # anticipación silencioso, mejor que la señal no puntúe.
    if nohist_codes:
        from app.services.group_score_service import get_default_target_date
        if target_date == get_default_target_date():
            from app.models.indicator_store import CurrentIndicatorValue
            rows = s.query(
                CurrentIndicatorValue.asset_id, CurrentIndicatorValue.code,
                CurrentIndicatorValue.value_num, CurrentIndicatorValue.value_str,
            ).filter(CurrentIndicatorValue.code.in_(nohist_codes)).all()
            for asset_id_row, code, num, txt in rows:
                value = num if num is not None else txt
                if value is not None:
                    isnaps.setdefault(asset_id_row, {})[code] = value
        else:
            logger.info(
                "signal_service: señales sobre indicadores sin historia (%s) "
                "omitidas para fecha pasada %s (solo evaluables en la fecha "
                "vigente)", sorted(nohist_codes), target_date)

    # Indicadores virtuales (last_close → prices table)
    for code in virtual_to_load:
        for asset_id, value in _load_virtual(s, code, target_date).items():
            isnaps.setdefault(asset_id, {})[code] = value

    if not isnaps:
        logger.info("signal_service: sin valores de indicadores para %s", target_date)
        return 0

    # Cargar group_scores del día
    gscores: dict[tuple, GroupScore] = {
        (gs.group_type, gs.group_id): gs
        for gs in s.query(GroupScore).filter(GroupScore.date == target_date).all()
    }

    # Info de grupo de cada activo
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

    existing_svs: dict[tuple, SignalValue] = {
        (sv.signal_id, sv.asset_id): sv
        for sv in s.query(SignalValue).filter(SignalValue.date == target_date).all()
    }

    written = 0

    # Memo de scores de grupo: todos los activos de un mismo grupo comparten
    # el mismo score, no hace falta evaluarlo una vez por activo.
    group_score_memo: dict[tuple, float | None] = {}

    for asset_id, isnap in isnaps.items():
        asset_scores: dict[str, float | None] = {}

        for sig in asset_signals:
            if sig.formula_type == "composite":
                continue
            value = isnap.get(sig.indicator_key) if sig.indicator_key else None
            score = signal_engine.evaluate(sig.formula_type, sig.params, value,
                                           params=params_by_id.get(sig.id))
            asset_scores[sig.key] = score

        groups = asset_groups.get(asset_id, {})
        for sig in group_signals:
            if sig.formula_type == "composite":
                continue
            group_id = groups.get(sig.group_type)
            if group_id is None:
                asset_scores[sig.key] = None
                continue
            memo_key = (sig.id, group_id)
            if memo_key in group_score_memo:
                asset_scores[sig.key] = group_score_memo[memo_key]
                continue
            gscore = gscores.get((sig.group_type, group_id))
            if gscore is None:
                group_score_memo[memo_key] = None
                asset_scores[sig.key] = None
                continue
            value = _get_group_indicator_value(gscore, sig.indicator_key) if sig.indicator_key else None
            score = signal_engine.evaluate(sig.formula_type, sig.params, value,
                                           params=params_by_id.get(sig.id))
            group_score_memo[memo_key] = score
            asset_scores[sig.key] = score

        _build_composite_scores(signals, asset_scores,
                                refs_by_key=refs_by_key, params_by_id=params_by_id)

        for sig in signals:
            score = asset_scores.get(sig.key)
            if score is None:
                continue
            key = (sig.id, asset_id)
            sv = existing_svs.get(key)
            if sv is None:
                sv = SignalValue(signal_id=sig.id, asset_id=asset_id, date=target_date)
                s.add(sv)
                existing_svs[key] = sv
            sv.score = score
            written += 1

    s.commit()
    logger.info("signal_service: %d signal_value escritos para %s", written, target_date)
    return written


def compute_group_signal_values(target_date: date_type,
                                only_signal_ids: set[int] | None = None) -> int:
    s = get_session()

    group_signals = (
        s.query(SignalDefinition).filter(SignalDefinition.source == "group").all()
    )
    if only_signal_ids is not None:
        group_signals = [sg for sg in group_signals if sg.id in only_signal_ids]
    if not group_signals:
        return 0

    import json as _json
    params_by_id: dict[int, dict | None] = {}
    for sig in group_signals:
        try:
            params_by_id[sig.id] = _json.loads(sig.params)
        except (TypeError, ValueError):
            params_by_id[sig.id] = None

    gscores = (
        s.query(GroupScore)
        .filter(GroupScore.date == target_date)
        .all()
    )

    existing_gsvs: dict[tuple, GroupSignalValue] = {
        (gsv.signal_id, gsv.group_type, gsv.group_id): gsv
        for gsv in s.query(GroupSignalValue).filter(GroupSignalValue.date == target_date).all()
    }

    written = 0

    for gscore in gscores:
        for sig in group_signals:
            if sig.group_type and sig.group_type != gscore.group_type:
                continue
            value = _get_group_indicator_value(gscore, sig.indicator_key) if sig.indicator_key else None
            score = signal_engine.evaluate(sig.formula_type, sig.params, value,
                                           params=params_by_id.get(sig.id))
            if score is None:
                continue

            key = (sig.id, gscore.group_type, gscore.group_id)
            gsv = existing_gsvs.get(key)
            if gsv is None:
                gsv = GroupSignalValue(
                    signal_id=sig.id,
                    group_type=gscore.group_type,
                    group_id=gscore.group_id,
                    date=target_date,
                )
                s.add(gsv)
                existing_gsvs[key] = gsv
            gsv.score = score
            written += 1

    s.commit()
    logger.info("signal_service: %d group_signal_value escritos para %s", written, target_date)
    return written


def run_daily(target_date: date_type | None = None) -> dict:
    if target_date is None:
        from app.services.group_score_service import get_default_target_date
        target_date = get_default_target_date()

    asset_written = compute_signal_values(target_date)
    group_written = compute_group_signal_values(target_date)

    return {"date": str(target_date), "signal_values": asset_written, "group_signal_values": group_written}


# ── CRUD ──────────────────────────────────────────────────────────────────────

def get_all_signals() -> list:
    s = get_session()
    return s.query(SignalDefinition).order_by(SignalDefinition.id).all()


def save_signal(
    key: str,
    name: str,
    source: str,
    formula_type: str,
    params_json: str,
    *,
    description: str | None = None,
    group_type: str | None = None,
    indicator_key: str | None = None,
    signal_id: int | None = None,
) -> SignalDefinition:
    import json as _json
    params = _json.loads(params_json)
    shape_error = signal_engine.validate_params(
        formula_type, params if isinstance(params, dict) else {})
    if shape_error:
        raise ValueError(shape_error)

    s = get_session()
    if signal_id:
        sig = s.query(SignalDefinition).filter(SignalDefinition.id == signal_id).first()
        if sig is None:
            raise ValueError(f"Señal id={signal_id} no encontrada.")
    else:
        existing = s.query(SignalDefinition).filter(SignalDefinition.key == key).first()
        if existing:
            raise ValueError(f"Ya existe una señal con key '{key}'.")
        sig = SignalDefinition()
        sig.is_system = False
        s.add(sig)

    sig.key           = key
    sig.name          = name
    sig.description   = description
    sig.source        = source
    sig.group_type    = group_type or None
    sig.indicator_key = indicator_key or None
    sig.formula_type  = formula_type
    sig.params        = params_json
    s.commit()
    return sig


def delete_signal(signal_id: int) -> None:
    s = get_session()
    sig = s.query(SignalDefinition).filter(SignalDefinition.id == signal_id).first()
    if sig is None:
        raise ValueError(f"Señal id={signal_id} no encontrada.")
    if sig.is_system:
        raise ValueError(f"No se puede eliminar la señal de sistema '{sig.key}'.")
    s.delete(sig)
    s.commit()


# ── Export / Import Excel ──────────────────────────────────────────────────────

def export_signals_excel() -> bytes:
    import openpyxl
    from io import BytesIO

    signals = get_all_signals()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Señales"
    ws.append(["key", "name", "description", "source", "group_type",
                "indicator_key", "formula_type", "params"])
    for sig in signals:
        ws.append([
            sig.key, sig.name, sig.description or "",
            sig.source, sig.group_type or "", sig.indicator_key or "",
            sig.formula_type, sig.params,
        ])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def import_signals_excel(file_bytes: bytes) -> list[dict]:
    """Importación todo-o-nada en dos pasadas: primero se valida el archivo
    completo sin tocar la base; solo si no hay errores se escribe todo."""
    import openpyxl
    import json as _json
    from io import BytesIO

    wb = openpyxl.load_workbook(BytesIO(file_bytes))
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []

    headers = [str(h).strip().lower() for h in rows[0]]

    _FORMULA_TYPES = ("discrete_map", "threshold", "range", "composite")
    _SOURCES       = ("asset", "group")

    # Catálogos para validar referencias (indicadores, señales existentes)
    s = get_session()
    from app.models.indicator_definition import IndicatorDefinition
    known_indicators = {
        d.code for d in s.query(IndicatorDefinition.code).all()
    } | set(_VIRTUAL_CODES)
    known_signal_keys = {r.key for r in s.query(SignalDefinition.key).all()}

    # ── Pasada 1: validación completa sin escribir ────────────────────────────
    parsed: list[dict] = []
    invalid = False
    for row in rows[1:]:
        data = dict(zip(headers, row))
        key = str(data.get("key") or "").strip()
        if not key:
            continue
        params_str    = str(data.get("params") or "{}")
        formula_type  = str(data.get("formula_type") or "range")
        source        = str(data.get("source") or "asset")
        indicator_key = str(data.get("indicator_key") or "").strip()
        group_type    = str(data.get("group_type") or "").strip()
        error = None
        params = None
        try:
            params = _json.loads(params_str)
        except Exception as exc:
            error = f"params inválido: {exc}"
        if error is None and formula_type not in _FORMULA_TYPES:
            error = f"formula_type desconocido: '{formula_type}'"
        if error is None and source not in _SOURCES:
            error = f"source desconocido: '{source}'"
        if error is None:
            # Forma de params según la fórmula: un params json-válido pero
            # con la forma equivocada no rompe nada — la señal nunca
            # puntuaría, silenciosamente. Mejor rechazar acá.
            error = signal_engine.validate_params(
                formula_type, params if isinstance(params, dict) else {})
        if error is None and formula_type != "composite":
            if source == "group":
                if not group_type:
                    error = "source=group requiere group_type"
                elif indicator_key not in _VALID_GROUP_INDICATOR_KEYS:
                    error = (f"indicator_key '{indicator_key}' no es un campo "
                             f"válido de group_scores")
            elif indicator_key and indicator_key not in known_indicators:
                error = f"indicador desconocido: '{indicator_key}'"
        if error:
            invalid = True
        parsed.append({"key": key, "data": data, "params": params_str,
                       "formula_type": formula_type, "source": source,
                       "error": error})

    # Refs de composites: contra las señales del archivo + las de la base
    file_keys = {p["key"] for p in parsed}
    for p in parsed:
        if p["error"] is None and p["formula_type"] == "composite":
            refs = {
                c.get("signal_key")
                for c in _json.loads(p["params"]).get("components", [])
            }
            missing = refs - file_keys - known_signal_keys
            if missing:
                p["error"] = f"composite referencia señales inexistentes: {sorted(missing)}"
                invalid = True

    if invalid:
        return [
            {"key": p["key"],
             "status": "error" if p["error"] else "omitido",
             "detail": p["error"] or "el archivo contiene errores; no se importó nada"}
            for p in parsed
        ]

    # ── Pasada 2: escribir todo en una sola transacción ───────────────────────
    s = get_session()
    results: list[dict] = []
    try:
        for p in parsed:
            data = p["data"]
            key  = p["key"]
            sig = s.query(SignalDefinition).filter(SignalDefinition.key == key).first()
            if sig is None:
                sig = SignalDefinition()
                sig.is_system = False
                s.add(sig)
            sig.key           = key
            sig.name          = str(data.get("name") or key)
            sig.source        = p["source"]
            sig.formula_type  = p["formula_type"]
            sig.params        = p["params"]
            sig.description   = str(data.get("description") or "") or None
            sig.group_type    = str(data.get("group_type") or "") or None
            sig.indicator_key = str(data.get("indicator_key") or "") or None
            s.flush()
            results.append({"key": key, "status": "ok", "detail": f"id={sig.id}"})
        s.commit()
    except Exception as exc:
        s.rollback()
        failed_key = parsed[len(results)]["key"] if len(results) < len(parsed) else "?"
        return [
            {"key": p["key"],
             "status": "error" if p["key"] == failed_key else "revertido",
             "detail": str(exc) if p["key"] == failed_key
                       else "revertido por error en otra fila"}
            for p in parsed
        ]

    return results


# ── Backfill histórico (Centro de Datos) ──────────────────────────────────────

def _dates_to_compute(trading_dates: list, computed_dates: set,
                      force: bool) -> list:
    """Qué fechas correr. force=False (delta): las que no tienen ningún
    signal_value, más SIEMPRE la última (sus precios/indicadores son
    preliminares — mismo criterio que el delta de indicadores). force=True:
    todas."""
    if force:
        return list(trading_dates)
    if not trading_dates:
        return []
    last = trading_dates[-1]
    return [d for d in trading_dates if d not in computed_dates or d == last]


def _closure_composites(seed_ids: set[int], signals: list) -> set[int]:
    """Cierra el subconjunto sumando las señales referenciadas por las
    composites incluidas, recursivo."""
    import json as _json
    by_key = {sg.key: sg for sg in signals}
    by_id  = {sg.id: sg for sg in signals}
    closed, frontier = set(seed_ids), list(seed_ids)
    while frontier:
        sig = by_id.get(frontier.pop())
        if sig is None or sig.formula_type != "composite":
            continue
        try:
            refs = {c.get("signal_key")
                    for c in _json.loads(sig.params).get("components", [])}
        except (TypeError, ValueError):
            refs = set()
        for k in refs:
            ref = by_key.get(k)
            if ref is not None and ref.id not in closed:
                closed.add(ref.id)
                frontier.append(ref.id)
    return closed


def _scope_signal_ids(s, scope: str | None):
    """Resuelve el alcance del backfill.

    scope: None (todo) | "strategy:<id>" | "signal:<key>".
    Devuelve (only_signal_ids | None, strategy_id | None, scope_kind).
    Para una estrategia incluye: señales de sus componentes + señales usadas
    como operando en su filtro de elegibilidad + composites referenciadas
    (recursivo)."""
    if not scope:
        return None, None, None
    kind, _, val = scope.partition(":")
    signals = s.query(SignalDefinition).all()
    by_key = {sg.key: sg for sg in signals}

    if kind == "strategy":
        from app.models import Strategy
        from app.services import strategy_filter
        strategy_id = int(val)
        strat = s.query(Strategy).filter(Strategy.id == strategy_id).first()
        if strat is None:
            raise ValueError(f"Estrategia id={strategy_id} no encontrada.")
        seed = {c.signal_id for c in strat.components}
        tree = strategy_filter.parse_tree(strat.filter_conditions)
        if tree is not None:
            for t, key, _res in strategy_filter.collect_operands(tree):
                if t == "signal" and key in by_key:
                    seed.add(by_key[key].id)
        return _closure_composites(seed, signals), strategy_id, "strategy"

    if kind == "signal":
        sig = by_key.get(val)
        if sig is None:
            raise ValueError(f"Señal '{val}' no encontrada.")
        return _closure_composites({sig.id}, signals), None, "signal"

    raise ValueError(f"Alcance desconocido: {scope!r}")


def _signal_history_run(progress_cb=None, days: int = 365,
                        force: bool = False, scope: str | None = None) -> dict:
    """Corre el pipeline (scores de grupo → señales → estrategias) para cada
    fecha con precios dentro del horizonte. Delta (force=False): solo fechas
    sin cálculo previo + la última. Rebuild (force=True): todas.

    scope acota a una estrategia (señales necesarias + sus resultados) o a
    una señal suelta (sin tocar resultados de estrategias)."""
    from datetime import timedelta

    from app.services import group_score_service, strategy_service

    s = get_session()
    only_ids, strategy_id, scope_kind = _scope_signal_ids(s, scope)

    last = s.query(sa.func.max(Price.date)).scalar()
    if last is None:
        return {"total": 0, "success": 0, "errors": []}
    horizon = last - timedelta(days=int(days or 365))

    trading_dates = sorted({
        d for (d,) in s.query(Price.date).distinct()
        .filter(Price.date >= horizon).all()
    })

    # "Ya calculado" según el alcance: los resultados de ESA estrategia, los
    # scores de ESA señal, o cualquier señal del día (alcance total)
    if scope_kind == "strategy":
        from app.models import StrategyResult
        computed = {
            d for (d,) in s.query(StrategyResult.date).distinct().filter(
                StrategyResult.strategy_id == strategy_id,
                StrategyResult.date >= horizon)
        }
    elif scope_kind == "signal":
        # La señal pedida (no sus dependencias) define el "ya calculado"
        target_sig = s.query(SignalDefinition).filter(
            SignalDefinition.key == scope.partition(":")[2]).first()
        table = GroupSignalValue if target_sig.source == "group" else SignalValue
        computed = {
            d for (d,) in s.query(table.date).distinct().filter(
                table.signal_id == target_sig.id, table.date >= horizon)
        }
    else:
        computed = {
            d for (d,) in s.query(SignalValue.date).distinct()
            .filter(SignalValue.date >= horizon)
        }

    dates = _dates_to_compute(trading_dates, computed, force)

    total, ok, errors = len(dates), 0, []
    for i, d in enumerate(dates, start=1):
        if progress_cb:
            progress_cb(i, total, str(d))
        try:
            group_score_service.run_daily(d)
            compute_signal_values(d, only_signal_ids=only_ids)
            compute_group_signal_values(d, only_signal_ids=only_ids)
            if scope_kind == "strategy":
                strategy_service.compute_strategy_results(strategy_id, d)
            elif scope_kind is None:
                strategy_service.compute_all_strategies(d)
            # scope señal: no toca resultados de estrategias
            ok += 1
        except Exception as exc:
            logger.exception("signal_service: backfill falló para %s", d)
            errors.append({"date": str(d), "error": f"{d}: {exc}"})
    return {"total": total, "success": ok, "errors": errors}


def update_signal_history(progress_cb=None, days: int = 365,
                          scope: str | None = None) -> dict:
    """Delta: llena huecos (fechas con precios pero sin cálculo) dentro del
    horizonte y recalcula la última fecha. Cubre el día a día manual con el
    scheduler apagado y el catch-up tras días sin correr."""
    return _signal_history_run(progress_cb, days=days, force=False, scope=scope)


def rebuild_signal_history(progress_cb=None, days: int = 365,
                           scope: str | None = None) -> dict:
    """Rebuild: recalcula TODAS las fechas con precios del horizonte
    (reescribe lo existente — para cambios de definición o fixes)."""
    return _signal_history_run(progress_cb, days=days, force=True, scope=scope)


def run_recalculate(target_date: date_type | None = None) -> dict:
    from app.services import group_score_service, strategy_service

    if target_date is None:
        target_date = group_score_service.get_default_target_date()

    group_score_service.run_daily(target_date)
    result = run_daily(target_date)

    strat_result = strategy_service.run_daily(target_date)
    result["strategy_results"] = strat_result.get("strategy_results", 0)
    return result
