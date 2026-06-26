import logging
from datetime import datetime, timedelta

from app.database import get_session
from app.models import (
    Asset, FundamentalQuarterly, FundamentalSnapshot, FundamentalUpdateLog, Price,
)

logger = logging.getLogger(__name__)

_STALE_DAYS = 7  # re-fetch solo si los datos tienen más de 7 días


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
    net_margin  = _safe_div(latest.net_income,       rev)
    gross_margin= _safe_div(latest.gross_profit,     rev)
    op_margin   = _safe_div(latest.operating_income, rev)
    d_e         = _safe_div(latest.total_debt,       latest.equity)

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
    if len(rows) >= 5:
        q0, q4 = rows[0], rows[4]
        if q0.revenue and q4.revenue and q4.revenue != 0:
            rev_growth = round((q0.revenue - q4.revenue) / abs(q4.revenue), 4)
        ni0 = q0.net_income
        ni4 = q4.net_income
        if ni0 is not None and ni4 and ni4 != 0:
            eps_growth = round((ni0 - ni4) / abs(ni4), 4)

    snap = s.query(FundamentalSnapshot).filter_by(asset_id=asset_id).first()
    if snap is None:
        snap = FundamentalSnapshot(asset_id=asset_id)
        s.add(snap)
    snap.updated_at         = datetime.utcnow()
    snap.pe_ttm             = pe_ttm
    snap.pb                 = pb
    snap.ps_ttm             = ps_ttm
    snap.net_margin         = net_margin
    snap.gross_margin       = gross_margin
    snap.operating_margin   = op_margin
    snap.debt_to_equity     = d_e
    snap.revenue_growth_yoy = rev_growth
    snap.eps_growth_yoy     = eps_growth


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


def update_all_fundamentals(progress_cb=None) -> dict:
    s = get_session()
    assets = s.query(Asset).filter(Asset.fundamental_source_id.isnot(None)).all()
    total   = len(assets)
    summary = {"total": total, "success": 0, "skipped": 0, "errors": []}

    for i, asset in enumerate(assets, 1):
        if progress_cb:
            progress_cb(i, total)
        try:
            update_asset_fundamentals(asset.id)
            summary["success"] += 1
        except Exception as exc:
            summary["errors"].append({"ticker": asset.ticker, "error": str(exc)})

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
    s = get_session()
    quarters = (s.query(FundamentalQuarterly)
                  .filter_by(asset_id=asset_id)
                  .order_by(FundamentalQuarterly.period_date)
                  .all())
    snap = s.query(FundamentalSnapshot).filter_by(asset_id=asset_id).first()

    # Si hay datos trimestrales pero falta el snapshot (e.g. bug de autoflush anterior),
    # recomputar on-the-fly
    if quarters and snap is None:
        _compute_snapshot(asset_id, s)
        s.commit()
        snap = s.query(FundamentalSnapshot).filter_by(asset_id=asset_id).first()
    return {
        "quarters": [
            {
                "period":          str(q.period_date),
                "revenue":         q.revenue,
                "gross_profit":    q.gross_profit,
                "operating_income":q.operating_income,
                "net_income":      q.net_income,
                "ebitda":          q.ebitda,
                "total_debt":      q.total_debt,
                "equity":          q.equity,
                "fcf":             q.fcf,
                "eps_actual":      q.eps_actual,
            }
            for q in quarters
        ],
        "snapshot": {
            "pe_ttm":             snap.pe_ttm             if snap else None,
            "pb":                 snap.pb                 if snap else None,
            "ps_ttm":             snap.ps_ttm             if snap else None,
            "net_margin":         snap.net_margin         if snap else None,
            "gross_margin":       snap.gross_margin       if snap else None,
            "operating_margin":   snap.operating_margin   if snap else None,
            "debt_to_equity":     snap.debt_to_equity     if snap else None,
            "revenue_growth_yoy": snap.revenue_growth_yoy if snap else None,
            "eps_growth_yoy":     snap.eps_growth_yoy     if snap else None,
            "updated_at":         str(snap.updated_at)[:19] if snap else None,
        } if snap else {},
    }


def get_assets_with_fundamentals() -> list[Asset]:
    s = get_session()
    return (s.query(Asset)
              .filter(Asset.fundamental_source_id.isnot(None))
              .order_by(Asset.ticker)
              .all())
