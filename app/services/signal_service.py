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

    # Cargar info de grupo de cada activo (todas las dimensiones soportadas como group_type)
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

    # Pre-cargar SignalValues del día: evita N×M queries en el upsert
    existing_svs: dict[tuple, SignalValue] = {
        (sv.signal_id, sv.asset_id): sv
        for sv in s.query(SignalValue).filter(SignalValue.date == snap_date).all()
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

        # 4. Persistir (upsert via dict precargado — sin queries adicionales)
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

    # Pre-cargar GroupSignalValues del día
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
            score = signal_engine.evaluate(sig.formula_type, sig.params, value)
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


# ── CRUD ──────────────────────────────────────────────────────────────────────

def get_all_signals() -> list:
    s = get_session()
    return s.query(SignalDefinition).order_by(SignalDefinition.id).all()


def _find_signal_id_by_key(key: str) -> int | None:
    s = get_session()
    sig = s.query(SignalDefinition).filter(SignalDefinition.key == key).first()
    return sig.id if sig else None


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
    _json.loads(params_json)  # valida JSON antes de guardar

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
    import openpyxl
    from io import BytesIO

    wb = openpyxl.load_workbook(BytesIO(file_bytes))
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []

    headers = [str(h).strip().lower() for h in rows[0]]
    results = []

    for row in rows[1:]:
        data = dict(zip(headers, row))
        key = str(data.get("key") or "").strip()
        if not key:
            continue
        try:
            sig = save_signal(
                key=key,
                name=str(data.get("name") or key),
                source=str(data.get("source") or "asset"),
                formula_type=str(data.get("formula_type") or "range"),
                params_json=str(data.get("params") or "{}"),
                description=str(data.get("description") or "") or None,
                group_type=str(data.get("group_type") or "") or None,
                indicator_key=str(data.get("indicator_key") or "") or None,
                signal_id=_find_signal_id_by_key(key),
            )
            results.append({"key": key, "status": "ok", "detail": f"id={sig.id}"})
        except Exception as exc:
            results.append({"key": key, "status": "error", "detail": str(exc)})

    return results


def run_recalculate(snap_date: date_type | None = None) -> dict:
    """Recalcula indicadores + señales + estrategias para snap_date."""
    from datetime import date as dt_date
    from app.services import indicator_service, strategy_service

    if snap_date is None:
        snap_date = dt_date.today()

    indicator_service.run_daily(snap_date)
    result = run_daily(snap_date)

    strat_result = strategy_service.run_daily(snap_date)
    result["strategy_results"] = strat_result.get("strategy_results", 0)
    return result
