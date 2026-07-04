"""
Servicio de señales.
Evalúa cada SignalDefinition contra indicadores (ind_*) / group_indicator_snapshot
y persiste los resultados en signal_value / group_signal_value.
"""
import logging
import sqlalchemy as sa
from datetime import date as date_type

from app.database import get_session
from app.models import (
    Asset,
    GroupIndicatorSnapshot,
    GroupSignalValue,
    SignalDefinition,
    SignalValue,
)
from app.models.indicator_definition import IndicatorDefinition
from app.models.indicator_store import get_ind_table
from app.models.price import Price
from app.services import signal_engine

logger = logging.getLogger(__name__)


_VALID_GROUP_INDICATOR_KEYS = frozenset({"regime_score_d", "regime_score_w", "regime_score_m"})

# Indicadores virtuales: no tienen tabla ind_*, se leen de otra fuente
_VIRTUAL_CODES = frozenset({"last_close"})


def _load_virtual(s, code: str, snap_date) -> dict:
    """Carga un indicador virtual. Retorna {asset_id: value}."""
    if code == "last_close":
        rows = s.query(Price.asset_id, Price.close).filter(Price.date == snap_date).all()
        return {r[0]: float(r[1]) for r in rows if r[1] is not None}
    return {}


def _get_group_indicator_value(gsnap: GroupIndicatorSnapshot, key: str):
    if key not in _VALID_GROUP_INDICATOR_KEYS:
        logger.warning("signal_service: indicator_key '%s' no es un campo válido de GroupIndicatorSnapshot", key)
        return None
    return getattr(gsnap, key)


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


def compute_signal_values(snap_date: date_type) -> int:
    """
    Calcula signal_value para todos los activos para snap_date.
    Lee valores desde cada tabla ind_{code} por separado.
    """
    s = get_session()

    signals = s.query(SignalDefinition).all()
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

    # Cargar todos los indicadores con keep_history=True
    all_defs = {
        d.code: d
        for d in s.query(IndicatorDefinition).filter(
            IndicatorDefinition.keep_history.is_(True)
        ).all()
    }

    # Solo los que las señales referencian (virtuales se manejan aparte)
    codes_to_load = (needed_codes - _VIRTUAL_CODES) & set(all_defs.keys())
    virtual_to_load = needed_codes & _VIRTUAL_CODES

    # Construir {asset_id: {code: value}} leyendo cada ind_* table
    isnaps: dict[int, dict] = {}
    for code in codes_to_load:
        defn = all_defs[code]
        try:
            t = get_ind_table(code)
        except Exception:
            continue
        rows = s.execute(
            sa.select(t.c.asset_id, t.c.value).where(t.c.date == snap_date)
        ).fetchall()
        for asset_id_row, value in rows:
            isnaps.setdefault(asset_id_row, {})[code] = value

    # Indicadores virtuales (last_close → prices table)
    for code in virtual_to_load:
        for asset_id, value in _load_virtual(s, code, snap_date).items():
            isnaps.setdefault(asset_id, {})[code] = value

    if not isnaps:
        logger.info("signal_service: sin valores de indicadores para %s", snap_date)
        return 0

    # Cargar group_indicator_snapshots
    gsnaps: dict[tuple, GroupIndicatorSnapshot] = {
        (gs.group_type, gs.group_id): gs
        for gs in s.query(GroupIndicatorSnapshot).filter(GroupIndicatorSnapshot.date == snap_date).all()
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
        for sv in s.query(SignalValue).filter(SignalValue.date == snap_date).all()
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
            gsnap = gsnaps.get((sig.group_type, group_id))
            if gsnap is None:
                group_score_memo[memo_key] = None
                asset_scores[sig.key] = None
                continue
            value = _get_group_indicator_value(gsnap, sig.indicator_key) if sig.indicator_key else None
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
                sv = SignalValue(signal_id=sig.id, asset_id=asset_id, date=snap_date)
                s.add(sv)
                existing_svs[key] = sv
            sv.score = score
            written += 1

    s.commit()
    logger.info("signal_service: %d signal_value escritos para %s", written, snap_date)
    return written


def compute_group_signal_values(snap_date: date_type) -> int:
    s = get_session()

    group_signals = (
        s.query(SignalDefinition).filter(SignalDefinition.source == "group").all()
    )
    if not group_signals:
        return 0

    import json as _json
    params_by_id: dict[int, dict | None] = {}
    for sig in group_signals:
        try:
            params_by_id[sig.id] = _json.loads(sig.params)
        except (TypeError, ValueError):
            params_by_id[sig.id] = None

    gsnaps = (
        s.query(GroupIndicatorSnapshot)
        .filter(GroupIndicatorSnapshot.date == snap_date)
        .all()
    )

    existing_gsvs: dict[tuple, GroupSignalValue] = {
        (gsv.signal_id, gsv.group_type, gsv.group_id): gsv
        for gsv in s.query(GroupSignalValue).filter(GroupSignalValue.date == snap_date).all()
    }

    written = 0

    for gsnap in gsnaps:
        for sig in group_signals:
            if sig.group_type and sig.group_type != gsnap.group_type:
                continue
            value = _get_group_indicator_value(gsnap, sig.indicator_key) if sig.indicator_key else None
            score = signal_engine.evaluate(sig.formula_type, sig.params, value,
                                           params=params_by_id.get(sig.id))
            if score is None:
                continue

            key = (sig.id, gsnap.group_type, gsnap.group_id)
            gsv = existing_gsvs.get(key)
            if gsv is None:
                gsv = GroupSignalValue(
                    signal_id=sig.id,
                    group_type=gsnap.group_type,
                    group_id=gsnap.group_id,
                    date=snap_date,
                )
                s.add(gsv)
                existing_gsvs[key] = gsv
            gsv.score = score
            written += 1

    s.commit()
    logger.info("signal_service: %d group_signal_value escritos para %s", written, snap_date)
    return written


def run_daily(snap_date: date_type | None = None) -> dict:
    if snap_date is None:
        from app.services.indicator_service import get_default_snap_date
        snap_date = get_default_snap_date()

    asset_written = compute_signal_values(snap_date)
    group_written = compute_group_signal_values(snap_date)

    return {"date": str(snap_date), "signal_values": asset_written, "group_signal_values": group_written}


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
    _json.loads(params_json)

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

    # ── Pasada 1: validación completa sin escribir ────────────────────────────
    parsed: list[dict] = []
    invalid = False
    for row in rows[1:]:
        data = dict(zip(headers, row))
        key = str(data.get("key") or "").strip()
        if not key:
            continue
        params_str   = str(data.get("params") or "{}")
        formula_type = str(data.get("formula_type") or "range")
        source       = str(data.get("source") or "asset")
        error = None
        try:
            _json.loads(params_str)
        except Exception as exc:
            error = f"params inválido: {exc}"
        if error is None and formula_type not in _FORMULA_TYPES:
            error = f"formula_type desconocido: '{formula_type}'"
        if error is None and source not in _SOURCES:
            error = f"source desconocido: '{source}'"
        if error:
            invalid = True
        parsed.append({"key": key, "data": data, "params": params_str,
                       "formula_type": formula_type, "source": source,
                       "error": error})

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


def run_recalculate(snap_date: date_type | None = None) -> dict:
    from app.services import indicator_service, strategy_service

    if snap_date is None:
        snap_date = indicator_service.get_default_snap_date()

    indicator_service.run_daily(snap_date)
    result = run_daily(snap_date)

    strat_result = strategy_service.run_daily(snap_date)
    result["strategy_results"] = strat_result.get("strategy_results", 0)
    return result
