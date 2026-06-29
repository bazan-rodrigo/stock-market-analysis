import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import numpy as np
from datetime import date as _date_type

from sqlalchemy.dialects.mysql import insert as _mysql_insert

from app.database import get_session, Session as _ScopedSession
from app.models import (
    Asset, FundamentalQuarterly, FundamentalUpdateLog, Price,
)
from app.models.indicator_store import get_ind_table

logger = logging.getLogger(__name__)

_STALE_DAYS      = 90
_UPDATE_WORKERS  = 4
_BACKFILL_WORKERS = 4

_FUND_DAILY_CODES = frozenset({
    "fundamental_pe_ttm",
    "fundamental_pb",
    "fundamental_ps_ttm",
    "fundamental_pe_growth_yoy",
})

_FUND_QUARTERLY_CODES = frozenset({
    "fundamental_net_margin",
    "fundamental_gross_margin",
    "fundamental_operating_margin",
    "fundamental_debt_to_equity",
    "fundamental_revenue_growth_yoy",
    "fundamental_eps_growth_yoy",
    "fundamental_roic",
})

_ALL_FUND_CODES = _FUND_DAILY_CODES | _FUND_QUARTERLY_CODES


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


def _upsert_fund_value(code: str, asset_id: int, snap_date, val: float, s) -> None:
    if val is None:
        return
    t    = get_ind_table(code)
    v    = float(val)
    stmt = _mysql_insert(t).values(asset_id=asset_id, date=snap_date, value=v)
    stmt = stmt.on_duplicate_key_update(value=v)
    s.execute(stmt)


def _write_fundamental_values(asset_id: int, snap_date: _date_type, values: dict, s) -> None:
    for code, val in values.items():
        if val is not None:
            _upsert_fund_value(code, asset_id, snap_date, val, s)


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

    rev = latest.revenue
    net_margin   = _safe_div(latest.net_income,       rev)
    gross_margin = _safe_div(latest.gross_profit,     rev)
    op_margin    = _safe_div(latest.operating_income, rev)
    d_e          = _safe_div(latest.total_debt,       latest.equity)

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

    rev_growth = eps_growth = pe_growth = None
    if len(rows) >= 5:
        q0, q4 = rows[0], rows[4]
        if q0.revenue and q4.revenue and q4.revenue != 0:
            rev_growth = round((q0.revenue - q4.revenue) / abs(q4.revenue), 4)
        ni0 = q0.net_income
        ni4 = q4.net_income
        if ni0 is not None and ni4 and ni4 != 0:
            eps_growth = round((ni0 - ni4) / abs(ni4), 4)

    ttm_net_income = sum(r.net_income for r in ttm4 if r.net_income is not None)
    ttm_nopat      = sum(r.nopat for r in ttm4 if r.nopat is not None) or None
    ic_avg         = next((r.invested_capital_avg for r in ttm4 if r.invested_capital_avg), None)
    if ttm_nopat and ic_avg and ic_avg != 0:
        roic = round(ttm_nopat / ic_avg, 4)
    else:
        invested_capital = (latest.equity or 0) + (latest.total_debt or 0)
        roic = round(ttm_net_income / invested_capital, 4) if invested_capital and invested_capital != 0 else None

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
        s.flush()
        _compute_snapshot(asset_id, s)
        _save_log(asset_id, success=True, error=None, s=s)
        s.commit()
        logger.info("Fundamentales actualizados: %s (%d trimestres)", asset.ticker, len(quarters))
    except Exception as exc:
        s.rollback()
        error_msg = f"{type(exc).__name__}: {exc}"
        logger.error("Error fundamentales %s: %s", asset.ticker, error_msg)
        _save_log(asset_id, success=False, error=error_msg, s=s)
        s.commit()
        raise


def recompute_snapshot_for_asset(asset_id: int) -> None:
    s = get_session()
    has_quarters = s.query(FundamentalQuarterly).filter_by(asset_id=asset_id).first()
    if has_quarters is None:
        return
    _compute_snapshot(asset_id, s)
    s.commit()


def recompute_all_snapshots(progress_cb=None) -> dict:
    s = get_session()
    asset_ids = [
        r[0] for r in
        s.query(FundamentalQuarterly.asset_id)
         .join(Asset, FundamentalQuarterly.asset_id == Asset.id)
         .distinct()
         .all()
    ]
    total   = len(asset_ids)
    summary = {"total": total, "success": 0, "errors": []}
    for i, asset_id in enumerate(asset_ids, 1):
        if progress_cb:
            progress_cb(i, total)
        try:
            recompute_snapshot_for_asset(asset_id)
            summary["success"] += 1
        except Exception as exc:
            get_session().rollback()
            logger.error("Error recompute fundamental asset_id=%d: %s", asset_id, exc, exc_info=True)
            summary["errors"].append({"asset_id": asset_id, "error": str(exc)})
    return summary


def _fund_worker(asset_id: int, ticker: str) -> tuple[bool, dict | None]:
    try:
        update_asset_fundamentals(asset_id)
        return True, None
    except Exception as exc:
        return False, {"ticker": ticker, "error": str(exc)}
    finally:
        _ScopedSession.remove()


def update_new_fundamentals(progress_cb=None) -> dict:
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
    logged_ids = {log.asset_id for log in logs}
    for a in s.query(Asset).filter(Asset.fundamental_source_id.isnot(None)).all():
        if a.id not in logged_ids:
            result.append({
                "ticker": a.ticker, "name": a.name or "",
                "last_attempt_at": "—", "result": "—", "error_detail": "",
            })
    return result


def get_asset_fundamentals(asset_id: int) -> dict:
    import sqlalchemy as sa
    s = get_session()
    quarters = (s.query(FundamentalQuarterly)
                  .filter_by(asset_id=asset_id)
                  .order_by(FundamentalQuarterly.period_date)
                  .all())

    # Leer snapshot desde tablas ind_* (última fecha disponible por indicador)
    _FUND_CODES = [
        "fundamental_pe_ttm", "fundamental_pb", "fundamental_ps_ttm",
        "fundamental_net_margin", "fundamental_gross_margin", "fundamental_operating_margin",
        "fundamental_debt_to_equity", "fundamental_revenue_growth_yoy",
        "fundamental_eps_growth_yoy", "fundamental_pe_growth_yoy", "fundamental_roic",
    ]

    snap_vals: dict = {}
    updated_at = None

    for code in _FUND_CODES:
        try:
            t = get_ind_table(code)
        except Exception:
            continue
        row = s.execute(
            sa.select(t.c.value, t.c.date)
            .where(t.c.asset_id == asset_id)
            .order_by(t.c.date.desc())
            .limit(1)
        ).fetchone()
        if row is not None:
            key = code.replace("fundamental_", "")
            snap_vals[key] = row[0]
            if updated_at is None or row[1] > updated_at:
                updated_at = row[1]

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


# ── Backfill histórico de indicadores fundamentales ───────────────────────────

def _safe_div_r(a, b, decimals=4) -> float | None:
    if a is not None and b and b != 0:
        return round(a / b, decimals)
    return None


def _compute_quarterly_ratios(quarters: list, idx: int) -> dict:
    q      = quarters[idx]
    ttm4   = quarters[max(0, idx - 3): idx + 1]
    shares = next((r.shares for r in ttm4 if r.shares), None)

    rev      = q.revenue
    net_m    = _safe_div_r(q.net_income,       rev)
    gross_m  = _safe_div_r(q.gross_profit,     rev)
    op_m     = _safe_div_r(q.operating_income, rev)
    d_e      = _safe_div_r(q.total_debt,       q.equity)

    rev_growth = eps_growth = None
    if idx >= 4:
        q4 = quarters[idx - 4]
        rev_growth = _safe_div_r(
            (q.revenue - q4.revenue) if (q.revenue is not None and q4.revenue is not None) else None,
            abs(q4.revenue) if q4.revenue else None,
        )
        eps_growth = _safe_div_r(
            (q.net_income - q4.net_income) if (q.net_income is not None and q4.net_income is not None) else None,
            abs(q4.net_income) if q4.net_income else None,
        )

    ttm_nopat = sum(r.nopat for r in ttm4 if r.nopat is not None) or None
    ic_avg    = next((r.invested_capital_avg for r in ttm4 if r.invested_capital_avg), None)
    ttm_ni    = sum(r.net_income for r in ttm4 if r.net_income is not None)
    if ttm_nopat and ic_avg and ic_avg != 0:
        roic = round(ttm_nopat / ic_avg, 4)
    else:
        inv_cap = (q.equity or 0) + (q.total_debt or 0)
        roic = _safe_div_r(ttm_ni, inv_cap)

    return {
        "fundamental_net_margin":         net_m,
        "fundamental_gross_margin":       gross_m,
        "fundamental_operating_margin":   op_m,
        "fundamental_debt_to_equity":     d_e,
        "fundamental_revenue_growth_yoy": rev_growth,
        "fundamental_eps_growth_yoy":     eps_growth,
        "fundamental_roic":               roic,
    }


def _compute_daily_ratios(
    price: float,
    quarters: list,
    q_ords: np.ndarray,
    last_q_idx: int,
    price_dates_ord: np.ndarray,
    price_closes: np.ndarray,
    price_day_ord: int,
    ref_1y_ord: int,
) -> dict:
    ttm4   = quarters[max(0, last_q_idx - 3): last_q_idx + 1]
    latest = quarters[last_q_idx]
    shares = next((q.shares for q in ttm4 if q.shares), None)

    ttm_eps = sum(q.net_income for q in ttm4 if q.net_income is not None)
    ttm_rev = sum(q.revenue    for q in ttm4 if q.revenue    is not None)
    book_ps = _safe_div_r(latest.equity, shares)

    ttm_eps_ps = _safe_div_r(ttm_eps, shares)
    ttm_rev_ps = _safe_div_r(ttm_rev, shares)

    pe = _safe_div_r(price, ttm_eps_ps) if ttm_eps_ps and ttm_eps_ps > 0 else None
    pb = _safe_div_r(price, book_ps)    if book_ps    and book_ps    > 0 else None
    ps = _safe_div_r(price, ttm_rev_ps) if ttm_rev_ps and ttm_rev_ps > 0 else None

    pe_growth = None
    last_q_1y = int(np.searchsorted(q_ords, ref_1y_ord, side="right")) - 1
    if last_q_1y >= 0:
        ttm4_prev = quarters[max(0, last_q_1y - 3): last_q_1y + 1]
        sh_prev   = next((q.shares for q in ttm4_prev if q.shares), None)
        eps_prev  = sum(q.net_income for q in ttm4_prev if q.net_income is not None)
        eps_ps_pv = _safe_div_r(eps_prev, sh_prev)
        p_1y_idx  = int(np.searchsorted(price_dates_ord, ref_1y_ord, side="right")) - 1
        price_1y  = float(price_closes[p_1y_idx]) if p_1y_idx >= 0 else None
        pe_prev   = _safe_div_r(price_1y, eps_ps_pv) if eps_ps_pv and eps_ps_pv > 0 else None
        if pe and pe_prev and pe_prev != 0:
            pe_growth = round((pe - pe_prev) / abs(pe_prev), 4)

    return {
        "fundamental_pe_ttm":        pe,
        "fundamental_pb":            pb,
        "fundamental_ps_ttm":        ps,
        "fundamental_pe_growth_yoy": pe_growth,
    }


def backfill_fundamental_values(asset_id: int, session=None, *, force: bool = False) -> dict:
    """
    Backfill de ind_* para indicadores fundamentales.
    force=False: solo procesa fechas/quarters sin dato existente.
    force=True : borra todos los indicadores fundamentales del activo y recalcula todo.
    """
    import sqlalchemy as sa
    s = session or get_session()

    quarters = (s.query(FundamentalQuarterly)
                  .filter_by(asset_id=asset_id)
                  .order_by(FundamentalQuarterly.period_date.asc())
                  .all())
    if not quarters:
        return {"inserted": 0, "dates_processed": 0}

    price_rows = (s.query(Price.date, Price.close)
                   .filter(Price.asset_id == asset_id, Price.close.isnot(None))
                   .order_by(Price.date.asc())
                   .all())

    if force:
        for code in _ALL_FUND_CODES:
            try:
                t = get_ind_table(code)
                s.execute(t.delete().where(t.c.asset_id == asset_id))
            except Exception:
                pass
        missing_q_dates = {q.period_date for q in quarters}
        missing_d_dates = {r[0] for r in price_rows}
    else:
        # Descubrir fechas ya existentes por código (basta con uno representativo)
        def _existing_dates_for(code: str) -> set:
            try:
                t = get_ind_table(code)
                return {r[0] for r in s.execute(
                    sa.select(t.c.date).where(t.c.asset_id == asset_id)
                ).fetchall()}
            except Exception:
                return set()

        ref_q_code = next(iter(_FUND_QUARTERLY_CODES))
        ref_d_code = next(iter(_FUND_DAILY_CODES))
        existing_q = _existing_dates_for(ref_q_code)
        existing_d = _existing_dates_for(ref_d_code)
        missing_q_dates = {q.period_date for q in quarters} - existing_q
        missing_d_dates = {r[0] for r in price_rows}        - existing_d

    if not missing_q_dates and not missing_d_dates:
        return {"inserted": 0, "dates_processed": 0}

    q_ords          = np.array([q.period_date.toordinal() for q in quarters])
    price_dates_ord = np.array([r[0].toordinal() for r in price_rows])
    price_closes    = np.array([float(r[1]) for r in price_rows])

    inserted  = 0
    processed = 0

    # ── 1. Indicadores trimestrales ──────────────────────────────────────────
    for idx, q in enumerate(quarters):
        if q.period_date not in missing_q_dates:
            continue
        ratios = _compute_quarterly_ratios(quarters, idx)
        for code, val in ratios.items():
            if val is not None:
                _upsert_fund_value(code, asset_id, q.period_date, val, s)
                inserted += 1
        processed += 1

    # ── 2. Indicadores diarios ───────────────────────────────────────────────
    for price_date, price_close in price_rows:
        if price_date not in missing_d_dates:
            continue
        d_ord       = price_date.toordinal()
        last_q_idx  = int(np.searchsorted(q_ords, d_ord, side="right")) - 1
        if last_q_idx < 0:
            continue

        try:
            ref_1y_ord = _date_type(price_date.year - 1, price_date.month, price_date.day).toordinal()
        except ValueError:
            ref_1y_ord = _date_type(price_date.year - 1, price_date.month, 28).toordinal()

        ratios = _compute_daily_ratios(
            float(price_close), quarters, q_ords, last_q_idx,
            price_dates_ord, price_closes, d_ord, ref_1y_ord,
        )
        for code, val in ratios.items():
            if val is not None:
                _upsert_fund_value(code, asset_id, price_date, val, s)
                inserted += 1
        processed += 1

    s.commit()
    return {"inserted": inserted, "dates_processed": processed}


def _backfill_fund_worker(asset_id: int, force: bool = False) -> dict:
    try:
        s = get_session()
        return backfill_fundamental_values(asset_id, s, force=force)
    except Exception as exc:
        logger.warning("Fund backfill error asset_id=%d: %s", asset_id, exc)
        return {"inserted": 0, "dates_processed": 0, "error": str(exc)}
    finally:
        _ScopedSession.remove()


def backfill_all_fundamental_values(progress_cb=None, *, force: bool = False) -> dict:
    """Backfill histórico de indicadores fundamentales para todos los activos."""
    s         = get_session()
    asset_ids = [
        r[0] for r in
        s.query(FundamentalQuarterly.asset_id)
         .join(Asset, FundamentalQuarterly.asset_id == Asset.id)
         .distinct().all()
    ]
    total    = len(asset_ids)
    done     = 0
    inserted = 0
    errors: list[dict] = []

    with ThreadPoolExecutor(max_workers=_BACKFILL_WORKERS) as pool:
        futures = {pool.submit(_backfill_fund_worker, aid, force): aid for aid in asset_ids}
        for future in as_completed(futures):
            done += 1
            aid  = futures[future]
            if progress_cb:
                progress_cb(done, total)
            try:
                res = future.result()
                inserted += res.get("inserted", 0)
                if "error" in res:
                    errors.append({"asset_id": aid, "error": res["error"]})
            except Exception as exc:
                logger.warning("Fund backfill future error aid=%d: %s", aid, exc)
                errors.append({"asset_id": aid, "error": str(exc)})

    return {"total": total, "success": total - len(errors), "inserted": inserted, "errors": errors}
