import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

from datetime import date as _date_type

from app.database import get_session, Session as _ScopedSession
from app.models import (
    Asset, FundamentalQuarterly, FundamentalUpdateLog, Price,
)
from app.models.indicator_definition import IndicatorDefinition
from app.models.indicator_value import IndicatorValue

_fund_ind_cache: dict[str, int] = {}  # code → indicator_id

logger = logging.getLogger(__name__)

_STALE_DAYS    = 90  # re-fetch solo si los datos tienen más de 90 días (datos trimestrales)
_UPDATE_WORKERS = 4  # workers paralelos para fetch de fundamentales


# ── helpers internos ──────────────────────────────────────────────────────────

def _is_stale(asset_id: int, s) -> bool:
    log = s.query(FundamentalUpdateLog).filter_by(asset_id=asset_id).first()
    if log is None or not log.success:
        return True
    return datetime.utcnow() - log.last_attempt_at > timedelta(days=_STALE_DAYS)


def _save_log(asset_id: int, success: bool, error: str | None, s) -> None:
    log = s.query(FundamentalUpdateLog).filter_by(asset_id=asset_id).first()
    if log is None:
        log = FundamentalUpdateLog(asset_id=asset_id, success=success,
                                   last_attempt_at=datetime.utcnow(), error_detail=error)
        s.add(log)
    else:
        log.last_attempt_at = datetime.utcnow()
        log.success = success
        log.error_detail = error


def _latest_price(asset_id: int, s) -> float | None:
    row = (s.query(Price.close)
             .filter(Price.asset_id == asset_id, Price.close.isnot(None))
             .order_by(Price.date.desc())
             .first())
    return row[0] if row else None


def _price_1y_ago(asset_id: int, s) -> float | None:
    from datetime import date, timedelta
    target = date.today() - timedelta(days=365)
    row = (s.query(Price.close)
             .filter(Price.asset_id == asset_id,
                     Price.date <= target,
                     Price.close.isnot(None))
             .order_by(Price.date.desc())
             .first())
    return row[0] if row else None


def _upsert_quarterly(asset_id: int, quarters: list[dict], s) -> None:
    for q in quarters:
        existing = (s.query(FundamentalQuarterly)
                     .filter_by(asset_id=asset_id, period_date=q["period_date"])
                     .first())
        if existing is None:
            existing = FundamentalQuarterly(asset_id=asset_id)
            s.add(existing)
        for k, v in q.items():
            setattr(existing, k, v)


def _write_fundamental_values(asset_id: int, snap_date: _date_type, values: dict, s) -> None:
    global _fund_ind_cache
    if not _fund_ind_cache:
        for d in s.query(IndicatorDefinition).all():
            _fund_ind_cache[d.code] = d.id

    ind_ids = [_fund_ind_cache[c] for c in values if c in _fund_ind_cache]
    if not ind_ids:
        return  # indicator_definitions aún no tiene los códigos fundamentales

    existing = {
        iv.indicator_id: iv
        for iv in s.query(IndicatorValue).filter(
            IndicatorValue.asset_id == asset_id,
            IndicatorValue.date == snap_date,
            IndicatorValue.indicator_id.in_(ind_ids),
        ).all()
    }

    for code, val in values.items():
        ind_id = _fund_ind_cache.get(code)
        if ind_id is None or val is None:
            continue
        iv = existing.get(ind_id)
        if iv is None:
            iv = IndicatorValue(asset_id=asset_id, indicator_id=ind_id, date=snap_date)
            s.add(iv)
        iv.value_num = float(val)
        iv.value_str = None


def _compute_snapshot(asset_id: int, s) -> None:
    rows = (s.query(FundamentalQuarterly)
              .filter_by(asset_id=asset_id)
              .order_by(FundamentalQuarterly.period_date.desc())
              .limit(8)
              .all())
    if not rows:
        return

    latest = rows[0]
    price  = _latest_price(asset_id, s)

    def _safe_div(a, b):
        return round(a / b, 4) if a and b and b != 0 else None

    # Márgenes (último trimestre)
    rev = latest.revenue
    net_margin   = _safe_div(latest.net_income,       rev)
    gross_margin = _safe_div(latest.gross_profit,     rev)
    op_margin    = _safe_div(latest.operating_income, rev)
    d_e          = _safe_div(latest.total_debt,       latest.equity)

    # TTM (últimos 4 trimestres)
    ttm4 = rows[:4]
    ttm_eps = sum(r.net_income for r in ttm4 if r.net_income is not None)
    ttm_rev = sum(r.revenue    for r in ttm4 if r.revenue    is not None)
    shares  = next((r.shares for r in ttm4 if r.shares), None)

    ttm_eps_ps = _safe_div(ttm_eps, shares) if shares else None
    ttm_rev_ps = _safe_div(ttm_rev, shares) if shares else None
    book_ps    = _safe_div(latest.equity, shares) if shares else None

    pe_ttm = _safe_div(price, ttm_eps_ps) if price and ttm_eps_ps and ttm_eps_ps > 0 else None
    pb     = _safe_div(price, book_ps)    if price and book_ps    and book_ps    > 0 else None
    ps_ttm = _safe_div(price, ttm_rev_ps) if price and ttm_rev_ps and ttm_rev_ps > 0 else None

    # YoY (Q vs Q-4)
    rev_growth = None
    eps_growth = None
    pe_growth  = None
    if len(rows) >= 5:
        q0, q4 = rows[0], rows[4]
        if q0.revenue and q4.revenue and q4.revenue != 0:
            rev_growth = round((q0.revenue - q4.revenue) / abs(q4.revenue), 4)
        ni0 = q0.net_income
        ni4 = q4.net_income
        if ni0 is not None and ni4 and ni4 != 0:
            eps_growth = round((ni0 - ni4) / abs(ni4), 4)

    # ROIC
    ttm_net_income = sum(r.net_income for r in ttm4 if r.net_income is not None)
    ttm_nopat      = sum(r.nopat for r in ttm4 if r.nopat is not None) or None
    ic_avg         = next((r.invested_capital_avg for r in ttm4 if r.invested_capital_avg), None)
    if ttm_nopat and ic_avg and ic_avg != 0:
        roic = round(ttm_nopat / ic_avg, 4)
    else:
        invested_capital = (latest.equity or 0) + (latest.total_debt or 0)
        roic = round(ttm_net_income / invested_capital, 4) if invested_capital and invested_capital != 0 else None

    # P/E YoY
    if len(rows) >= 8 and pe_ttm is not None:
        ttm4_prev       = rows[4:8]
        shares_prev     = next((r.shares for r in ttm4_prev if r.shares), None)
        ttm_eps_prev    = sum(r.net_income for r in ttm4_prev if r.net_income is not None)
        ttm_eps_ps_prev = _safe_div(ttm_eps_prev, shares_prev) if shares_prev else None
        price_prev      = _price_1y_ago(asset_id, s)
        pe_prev = _safe_div(price_prev, ttm_eps_ps_prev) if (
            price_prev and ttm_eps_ps_prev and ttm_eps_ps_prev > 0
        ) else None
        if pe_prev and pe_prev != 0:
            pe_growth = round((pe_ttm - pe_prev) / abs(pe_prev), 4)

    snap_date = _date_type.today()
    _write_fundamental_values(asset_id, snap_date, {
        "fundamental_pe_ttm":             pe_ttm,
        "fundamental_pb":                 pb,
        "fundamental_ps_ttm":             ps_ttm,
        "fundamental_net_margin":         net_margin,
        "fundamental_gross_margin":       gross_margin,
        "fundamental_operating_margin":   op_margin,
        "fundamental_debt_to_equity":     d_e,
        "fundamental_revenue_growth_yoy": rev_growth,
        "fundamental_eps_growth_yoy":     eps_growth,
        "fundamental_pe_growth_yoy":      pe_growth,
        "fundamental_roic":               roic,
    }, s)


# ── API pública ───────────────────────────────────────────────────────────────

def update_asset_fundamentals(asset_id: int, *, force: bool = False) -> None:
    from app.sources.fundamental.registry import get_fundamental_source

    s = get_session()
    asset = s.get(Asset, asset_id)
    if asset is None or asset.fundamental_source_id is None:
        return

    if not force and not _is_stale(asset_id, s):
        return

    source_name = asset.fundamental_source.name
    try:
        source   = get_fundamental_source(source_name)
        quarters = source.fetch_quarterly(asset.ticker)
        if not quarters:
            raise ValueError(f"No se obtuvieron datos trimestrales para {asset.ticker}")
        _upsert_quarterly(asset_id, quarters, s)
        s.flush()  # autoflush=False — hacer visible los rows antes del query en _compute_snapshot
        _compute_snapshot(asset_id, s)
        _save_log(asset_id, success=True, error=None, s=s)
        s.commit()
        logger.info("Fundamentales actualizados: %s (%d trimestres)", asset.ticker, len(quarters))
    except Exception as exc:
        s.rollback()
        error_msg = str(exc)
        logger.error("Error fundamentales %s: %s", asset.ticker, error_msg)
        _save_log(asset_id, success=False, error=error_msg, s=s)
        s.commit()
        raise


def recompute_snapshot_for_asset(asset_id: int) -> None:
    """Recomputa el snapshot de ratios sin volver a fetchear datos de la fuente.
    Se llama con cada actualización de precios para mantener P/E y otros ratios frescos."""
    s = get_session()
    has_quarters = s.query(FundamentalQuarterly).filter_by(asset_id=asset_id).first()
    if has_quarters is None:
        return
    _compute_snapshot(asset_id, s)
    s.commit()


def recompute_all_snapshots(progress_cb=None) -> dict:
    """Recomputa todos los snapshots desde datos ya almacenados, sin fetch externo."""
    s = get_session()
    asset_ids = [r[0] for r in s.query(FundamentalQuarterly.asset_id).distinct().all()]
    total   = len(asset_ids)
    summary = {"total": total, "success": 0, "errors": []}
    for i, asset_id in enumerate(asset_ids, 1):
        if progress_cb:
            progress_cb(i, total)
        try:
            recompute_snapshot_for_asset(asset_id)
            summary["success"] += 1
        except Exception as exc:
            logger.error("Error recompute fundamental asset_id=%d: %s", asset_id, exc, exc_info=True)
            summary["errors"].append({"asset_id": asset_id, "error": str(exc)})
    return summary


def _fund_worker(asset_id: int, ticker: str) -> tuple[bool, dict | None]:
    """Actualiza fundamentales de un activo en su propio thread."""
    try:
        update_asset_fundamentals(asset_id)
        return True, None
    except Exception as exc:
        return False, {"ticker": ticker, "error": str(exc)}
    finally:
        _ScopedSession.remove()


def update_new_fundamentals(progress_cb=None) -> dict:
    """Solo activos con fuente de fundamentales pero sin FundamentalUpdateLog previo."""
    s = get_session()
    logged_ids = {r[0] for r in s.query(FundamentalUpdateLog.asset_id).all()}
    assets = s.query(Asset).filter(
        Asset.fundamental_source_id.isnot(None),
        ~Asset.id.in_(logged_ids) if logged_ids else True,
    ).all()
    pairs  = [(a.id, a.ticker) for a in assets]
    total  = len(pairs)
    summary = {"total": total, "success": 0, "errors": []}
    done_count = 0
    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=_UPDATE_WORKERS) as pool:
        futures = {pool.submit(_fund_worker, aid, ticker): ticker for aid, ticker in pairs}
        for future in as_completed(futures):
            ok, err = future.result()
            with lock:
                done_count += 1
                if progress_cb:
                    progress_cb(done_count, total)
            if ok:
                summary["success"] += 1
            elif err:
                summary["errors"].append(err)
    return summary


def update_all_fundamentals(progress_cb=None) -> dict:
    s = get_session()
    assets = s.query(Asset).filter(Asset.fundamental_source_id.isnot(None)).all()
    pairs  = [(a.id, a.ticker) for a in assets]
    total  = len(pairs)
    summary = {"total": total, "success": 0, "errors": []}

    done_count = 0
    lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=_UPDATE_WORKERS) as pool:
        futures = {pool.submit(_fund_worker, aid, ticker): ticker
                   for aid, ticker in pairs}
        for future in as_completed(futures):
            ok, err = future.result()
            with lock:
                done_count += 1
                if progress_cb:
                    progress_cb(done_count, total)
            if ok:
                summary["success"] += 1
            elif err:
                summary["errors"].append(err)

    return summary


def get_fundamentals_log() -> list[dict]:
    s = get_session()
    logs   = (s.query(FundamentalUpdateLog)
                .join(Asset)
                .order_by(Asset.ticker)
                .all())
    assets = {a.id: a for a in s.query(Asset).all()}
    result = []
    for log in logs:
        a = assets.get(log.asset_id)
        result.append({
            "ticker":         a.ticker if a else str(log.asset_id),
            "name":           a.name   if a else "",
            "last_attempt_at": str(log.last_attempt_at)[:19],
            "result":         "Éxito" if log.success else "Error",
            "error_detail":   log.error_detail or "",
        })
    # Activos con fuente pero sin log todavía
    logged_ids = {log.asset_id for log in logs}
    for a in s.query(Asset).filter(Asset.fundamental_source_id.isnot(None)).all():
        if a.id not in logged_ids:
            result.append({
                "ticker": a.ticker, "name": a.name or "",
                "last_attempt_at": "—", "result": "—", "error_detail": "",
            })
    return result


def get_asset_fundamentals(asset_id: int) -> dict:
    """Devuelve datos para la pantalla de fundamentales de un activo."""
    from sqlalchemy import func as _func
    s = get_session()
    quarters = (s.query(FundamentalQuarterly)
                  .filter_by(asset_id=asset_id)
                  .order_by(FundamentalQuarterly.period_date)
                  .all())

    # Leer snapshot desde indicator_values (última fecha disponible por indicador)
    _FUND_CODES = [
        "fundamental_pe_ttm", "fundamental_pb", "fundamental_ps_ttm",
        "fundamental_net_margin", "fundamental_gross_margin", "fundamental_operating_margin",
        "fundamental_debt_to_equity", "fundamental_revenue_growth_yoy",
        "fundamental_eps_growth_yoy", "fundamental_pe_growth_yoy", "fundamental_roic",
    ]
    global _fund_ind_cache
    if not _fund_ind_cache:
        for d in s.query(IndicatorDefinition).all():
            _fund_ind_cache[d.code] = d.id

    fund_ids = {c: _fund_ind_cache[c] for c in _FUND_CODES if c in _fund_ind_cache}

    # Subconsulta: fecha más reciente por (asset_id, indicator_id)
    latest_date_sub = (
        s.query(
            IndicatorValue.indicator_id,
            _func.max(IndicatorValue.date).label("max_date"),
        )
        .filter(
            IndicatorValue.asset_id == asset_id,
            IndicatorValue.indicator_id.in_(fund_ids.values()),
        )
        .group_by(IndicatorValue.indicator_id)
        .subquery()
    )
    rows = (
        s.query(IndicatorDefinition.code, IndicatorValue.value_num, IndicatorValue.date)
        .join(IndicatorValue, IndicatorDefinition.id == IndicatorValue.indicator_id)
        .join(
            latest_date_sub,
            (IndicatorValue.indicator_id == latest_date_sub.c.indicator_id)
            & (IndicatorValue.date == latest_date_sub.c.max_date),
        )
        .filter(IndicatorValue.asset_id == asset_id)
        .all()
    )

    snap_vals: dict = {}
    updated_at = None
    for code, val, snap_date in rows:
        key = code.replace("fundamental_", "")
        snap_vals[key] = val
        if updated_at is None or snap_date > updated_at:
            updated_at = snap_date

    # Recomputar on-the-fly si hay trimestres pero no hay snapshot aún
    if quarters and not snap_vals:
        _compute_snapshot(asset_id, s)
        s.commit()
        return get_asset_fundamentals(asset_id)

    return {
        "quarters": [
            {
                "period":           str(q.period_date),
                "revenue":          q.revenue,
                "gross_profit":     q.gross_profit,
                "operating_income": q.operating_income,
                "net_income":       q.net_income,
                "ebitda":           q.ebitda,
                "total_debt":       q.total_debt,
                "equity":           q.equity,
                "fcf":              q.fcf,
                "eps_actual":       q.eps_actual,
            }
            for q in quarters
        ],
        "snapshot": {
            "pe_ttm":             snap_vals.get("pe_ttm"),
            "pb":                 snap_vals.get("pb"),
            "ps_ttm":             snap_vals.get("ps_ttm"),
            "net_margin":         snap_vals.get("net_margin"),
            "gross_margin":       snap_vals.get("gross_margin"),
            "operating_margin":   snap_vals.get("operating_margin"),
            "debt_to_equity":     snap_vals.get("debt_to_equity"),
            "revenue_growth_yoy": snap_vals.get("revenue_growth_yoy"),
            "eps_growth_yoy":     snap_vals.get("eps_growth_yoy"),
            "pe_growth_yoy":      snap_vals.get("pe_growth_yoy"),
            "roic":               snap_vals.get("roic"),
            "updated_at":         str(updated_at) if updated_at else None,
        } if snap_vals else {},
    }


def get_assets_with_fundamentals() -> list[Asset]:
    s = get_session()
    return (s.query(Asset)
              .filter(Asset.fundamental_source_id.isnot(None))
              .order_by(Asset.ticker)
              .all())
