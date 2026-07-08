import logging
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import numpy as np
from datetime import date as _date_type

from sqlalchemy.dialects.mysql import insert as _mysql_insert
from sqlalchemy.exc import OperationalError

from app.database import engine, get_session, Session as _ScopedSession
from app.models import (
    Asset, FundamentalQuarterly, FundamentalUpdateLog, Price,
)
from app.models.indicator_store import get_ind_table

logger = logging.getLogger(__name__)

_STALE_DAYS      = 90
_UPDATE_WORKERS  = 4
# Activos por query al leer fechas existentes durante un backfill delta
_EXISTING_CHUNK  = 100

# Códigos de error InnoDB para los que MySQL espera que la aplicación
# reintente la transacción entera (no son bugs, son el resultado esperado
# de escrituras concurrentes contra la misma tabla — ver docs de InnoDB).
_DEADLOCK_ERRNO     = 1213  # "Deadlock found when trying to get lock"
_LOCK_TIMEOUT_ERRNO = 1205  # "Lock wait timeout exceeded"
_MAX_LOCK_RETRIES   = 3


def _is_retryable_lock_error(exc: BaseException) -> bool:
    orig  = getattr(exc, "orig", None)
    errno = orig.args[0] if orig and getattr(orig, "args", None) else None
    return errno in (_DEADLOCK_ERRNO, _LOCK_TIMEOUT_ERRNO)

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


def _ref_1y_ord(d: _date_type) -> int:
    """Ordinal de la fecha equivalente un año atrás (29/2 sin equivalente → día 28)."""
    try:
        return _date_type(d.year - 1, d.month, d.day).toordinal()
    except ValueError:
        return _date_type(d.year - 1, d.month, 28).toordinal()


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


def _upsert_fund_value(code: str, asset_id: int, target_date, val: float, s) -> None:
    if val is None:
        return
    t    = get_ind_table(code)
    v    = float(val)
    stmt = _mysql_insert(t).values(asset_id=asset_id, date=target_date, value=v)
    stmt = stmt.on_duplicate_key_update(value=v)
    s.execute(stmt)


def _write_fundamental_values(asset_id: int, target_date: _date_type, values: dict, s) -> None:
    for code, val in values.items():
        if val is not None:
            _upsert_fund_value(code, asset_id, target_date, val, s)


_UNSET = object()


def _compute_current_ratios(asset_id: int, s, *, quarters=None,
                      latest_price=_UNSET, price_1y=_UNSET) -> None:
    """Escribe los ratios vigentes del activo en ind_* con fecha de hoy.

    Reutiliza las fórmulas del backfill (_compute_quarterly_ratios /
    _compute_daily_ratios) para que el valor vigente y la historia nunca diverjan.
    quarters / latest_price / price_1y permiten inyectar datos precargados en
    corridas masivas (recompute_all_ratios)."""
    if quarters is None:
        quarters = (s.query(FundamentalQuarterly)
                      .filter_by(asset_id=asset_id)
                      .order_by(FundamentalQuarterly.period_date.asc())
                      .all())
    if not quarters:
        return

    idx    = len(quarters) - 1
    values = dict(_compute_quarterly_ratios(quarters, idx))

    price = latest_price if latest_price is not _UNSET else _latest_price(asset_id, s)
    if price:
        ref_ord = _ref_1y_ord(_date_type.today())
        px_1y   = price_1y if price_1y is not _UNSET else _price_1y_ago(asset_id, s)
        if px_1y:
            p_ords, p_closes = np.array([ref_ord]), np.array([float(px_1y)])
        else:
            p_ords, p_closes = np.array([], dtype=np.int64), np.array([])
        q_ords = np.array([q.period_date.toordinal() for q in quarters])
        values.update(_compute_daily_ratios(
            float(price), quarters, q_ords, idx, p_ords, p_closes, ref_ord,
        ))

    _write_fundamental_values(asset_id, _date_type.today(), values, s)


# ── API pública ───────────────────────────────────────────────────────────────

def update_asset_fundamentals(asset_id: int, *, force: bool = False,
                              replace: bool = False) -> None:
    """replace=True borra el historial trimestral existente y lo reemplaza por la
    descarga nueva, dentro de la misma transacción: si la descarga falla, el
    historial previo se conserva."""
    from app.sources.fundamental.registry import get_fundamental_source
    from app.services.technical_service import _save_indicator_log

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
        if replace:
            s.query(FundamentalQuarterly).filter(
                FundamentalQuarterly.asset_id == asset_id
            ).delete(synchronize_session=False)
        _upsert_quarterly(asset_id, quarters, s)
        s.flush()
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

    # Recálculo de ratios (P/E, P/B, etc.): error independiente de la descarga.
    # Si falla, no invalida el éxito de la descarga de trimestrales de arriba.
    try:
        _compute_current_ratios(asset_id, s)
        _save_indicator_log(asset_id, success=True, error=None, session=s)
    except Exception as exc:
        s.rollback()
        error_msg = f"{type(exc).__name__}: {exc}"
        logger.warning("Error recomputo ratios %s: %s", asset.ticker, error_msg)
        _save_indicator_log(asset_id, success=False, error=error_msg, session=s)


def recompute_ratios_for_asset(asset_id: int) -> None:
    s = get_session()
    has_quarters = s.query(FundamentalQuarterly).filter_by(asset_id=asset_id).first()
    if has_quarters is None:
        return
    _compute_current_ratios(asset_id, s)
    s.commit()


def recompute_all_ratios(progress_cb=None, *, quarters_cache: dict | None = None) -> dict:
    """Recomputa los ratios vigentes de todos los activos con fundamentales.

    Los quarters y los precios (último y de hace 1 año) se cargan en 3 queries
    para todos los activos, en lugar de 3-4 queries por activo.

    quarters_cache: si el caller ya lo cargó (ver _run_ratios_and_backfill,
    que lo comparte con backfill_all_fundamental_values), se reusa en vez
    de volver a consultarlo."""
    from datetime import timedelta as _td
    from sqlalchemy import and_ as _and, func as _func

    s = get_session()
    if quarters_cache is None:
        quarters_cache = _load_all_quarters(s)
    asset_ids = sorted(quarters_cache.keys())
    total   = len(asset_ids)
    summary = {"total": total, "success": 0, "errors": []}
    if not asset_ids:
        return summary

    def _prices_asof(max_date=None) -> dict:
        """{asset_id: último close} opcionalmente acotado a fechas <= max_date."""
        q = (s.query(Price.asset_id, _func.max(Price.date).label("md"))
              .filter(Price.close.isnot(None)))
        if max_date is not None:
            q = q.filter(Price.date <= max_date)
        subq = q.group_by(Price.asset_id).subquery()
        rows = (s.query(Price.asset_id, Price.close)
                 .join(subq, _and(Price.asset_id == subq.c.asset_id,
                                  Price.date == subq.c.md))
                 .all())
        return dict(rows)

    latest_prices = _prices_asof()
    prices_1y     = _prices_asof(_date_type.today() - _td(days=365))

    if progress_cb:
        progress_cb(0, total)
    for i, asset_id in enumerate(asset_ids, 1):
        try:
            _compute_current_ratios(
                asset_id, s,
                quarters=quarters_cache[asset_id],
                latest_price=latest_prices.get(asset_id),
                price_1y=prices_1y.get(asset_id),
            )
            s.commit()
            summary["success"] += 1
        except Exception as exc:
            s.rollback()
            logger.error("Error recompute fundamental asset_id=%d: %s", asset_id, exc, exc_info=True)
            summary["errors"].append({"asset_id": asset_id, "error": str(exc)})
        if progress_cb:
            progress_cb(i, total)
    return summary


def _fund_worker(asset_id: int, ticker: str, *, clear: bool = False) -> tuple[bool, dict | None]:
    """_UPDATE_WORKERS threads concurrentes escriben cada uno a un asset_id
    distinto en fundamental_quarterly, pero InnoDB puede igual deadlockear
    entre INSERTs concurrentes a la misma tabla (gap locks/FK checks, no
    hace falta que se pisen filas). Reintenta la transacción completa (todo
    update_asset_fundamentals, es idempotente) ante deadlock/lock timeout,
    tal como recomienda la documentación de InnoDB."""
    for attempt in range(_MAX_LOCK_RETRIES + 1):
        try:
            update_asset_fundamentals(asset_id, force=clear, replace=clear)
            return True, None
        except OperationalError as exc:
            if attempt < _MAX_LOCK_RETRIES and _is_retryable_lock_error(exc):
                logger.warning(
                    "Deadlock/lock timeout actualizando fundamentales %s "
                    "(intento %d/%d), reintentando...",
                    ticker, attempt + 1, _MAX_LOCK_RETRIES,
                )
                time.sleep(0.2 * (attempt + 1) + random.uniform(0, 0.2))
                continue
            return False, {"ticker": ticker, "error": str(exc)}
        except Exception as exc:
            return False, {"ticker": ticker, "error": str(exc)}
        finally:
            _ScopedSession.remove()


def _run_fund_batch(pairs: list[tuple[int, str]], *, clear: bool = False,
                    progress_cb=None, presuccess: int = 0,
                    total: int | None = None) -> dict:
    """Ejecuta _fund_worker en paralelo para una lista de (asset_id, ticker).

    presuccess/total permiten contar como éxito activos que no necesitaron
    procesarse (p. ej. fundamentales aún vigentes)."""
    total_n = total if total is not None else len(pairs)
    summary = {"total": total_n, "success": presuccess, "errors": []}
    if not pairs:
        return summary
    done_count = 0
    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=_UPDATE_WORKERS) as pool:
        futures = {pool.submit(_fund_worker, aid, ticker, clear=clear): ticker
                   for aid, ticker in pairs}
        for future in as_completed(futures):
            ok, err = future.result()
            with lock:
                done_count += 1
                if progress_cb:
                    progress_cb(done_count, len(pairs))
            if ok:
                summary["success"] += 1
            elif err:
                summary["errors"].append(err)
    return summary


def update_new_fundamentals(progress_cb=None) -> dict:
    s = get_session()
    logged_ids = {r[0] for r in s.query(FundamentalUpdateLog.asset_id).all()}
    assets = s.query(Asset).filter(
        Asset.fundamental_source_id.isnot(None),
        ~Asset.id.in_(logged_ids) if logged_ids else True,
    ).all()
    pairs = [(a.id, a.ticker) for a in assets]
    return _run_fund_batch(pairs, progress_cb=progress_cb)


def update_all_fundamentals(progress_cb=None) -> dict:
    """Actualiza los fundamentales vencidos (> _STALE_DAYS o con error previo).

    La staleness se resuelve con un solo prefetch de logs; los activos aún
    vigentes cuentan como éxito sin encolarse."""
    s = get_session()
    assets = s.query(Asset).filter(Asset.fundamental_source_id.isnot(None)).all()
    logs   = {l.asset_id: l for l in s.query(FundamentalUpdateLog).all()}

    def _stale(asset_id: int) -> bool:
        log = logs.get(asset_id)
        if log is None or not log.success:
            return True
        return datetime.utcnow() - log.last_attempt_at > timedelta(days=_STALE_DAYS)

    pairs       = [(a.id, a.ticker) for a in assets]
    stale_pairs = [(aid, ticker) for aid, ticker in pairs if _stale(aid)]
    fresh_count = len(pairs) - len(stale_pairs)
    return _run_fund_batch(stale_pairs, progress_cb=progress_cb,
                           presuccess=fresh_count, total=len(pairs))


def redownload_all_fundamentals(progress_cb=None) -> dict:
    """Borra el historial trimestral de todos los activos con fuente configurada
    y lo redescarga completo desde la fuente."""
    s = get_session()
    assets = s.query(Asset).filter(Asset.fundamental_source_id.isnot(None)).all()
    pairs  = [(a.id, a.ticker) for a in assets]
    return _run_fund_batch(pairs, clear=True, progress_cb=progress_cb)


def get_fundamentals_log() -> list[dict]:
    from app.models import IndicatorUpdateLog

    s = get_session()
    logs   = (s.query(FundamentalUpdateLog)
                .join(Asset)
                .order_by(Asset.ticker)
                .all())
    assets   = {a.id: a for a in s.query(Asset).all()}
    ind_logs = {log.asset_id: log for log in s.query(IndicatorUpdateLog).all()}

    def _ind_fields(asset_id):
        ind_log = ind_logs.get(asset_id)
        return {
            "last_indicator_at":      str(ind_log.last_attempt_at)[:19] if ind_log else "—",
            "indicator_result":       ("Éxito" if ind_log.success else "Error") if ind_log else "—",
            "indicator_error_detail": (ind_log.error_detail or "") if ind_log else "",
        }

    result = []
    for log in logs:
        a = assets.get(log.asset_id)
        result.append({
            "ticker":         a.ticker if a else str(log.asset_id),
            "name":           a.name   if a else "",
            "last_attempt_at": str(log.last_attempt_at)[:19],
            "result":         "Éxito" if log.success else "Error",
            "error_detail":   log.error_detail or "",
            **_ind_fields(log.asset_id),
        })
    logged_ids = {log.asset_id for log in logs}
    for a in s.query(Asset).filter(Asset.fundamental_source_id.isnot(None)).all():
        if a.id not in logged_ids:
            result.append({
                "ticker": a.ticker, "name": a.name or "",
                "last_attempt_at": "—", "result": "—", "error_detail": "",
                **_ind_fields(a.id),
            })
    return result


def get_asset_fundamentals(asset_id: int) -> dict:
    import sqlalchemy as sa
    s = get_session()
    quarters = (s.query(FundamentalQuarterly)
                  .filter_by(asset_id=asset_id)
                  .order_by(FundamentalQuarterly.period_date)
                  .all())

    # Leer ratios vigentes desde tablas ind_* (última fecha disponible por indicador)
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
        _compute_current_ratios(asset_id, s)
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
        "ratios": {
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


# ── Backfill histórico de indicadores fundamentales ───────────────────────────

def _safe_div_r(a, b, decimals=4) -> float | None:
    if a is not None and b and b != 0:
        return round(a / b, decimals)
    return None


def _compute_quarterly_ratios(quarters: list, idx: int) -> dict:
    q      = quarters[idx]
    ttm4   = quarters[max(0, idx - 3): idx + 1]
    # reversed: usar el dato más reciente disponible dentro de la ventana TTM
    shares = next((r.shares for r in reversed(ttm4) if r.shares), None)

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
    ic_avg    = next((r.invested_capital_avg for r in reversed(ttm4)
                      if r.invested_capital_avg), None)
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
    ref_1y_ord: int,
) -> dict:
    ttm4   = quarters[max(0, last_q_idx - 3): last_q_idx + 1]
    latest = quarters[last_q_idx]
    shares = next((q.shares for q in reversed(ttm4) if q.shares), None)

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
        sh_prev   = next((q.shares for q in reversed(ttm4_prev) if q.shares), None)
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


def _daily_ratio_series(quarters, q_ords: np.ndarray, price_dates: list,
                        price_dates_ord: np.ndarray,
                        price_closes: np.ndarray) -> dict:
    """Series completas de los 4 ratios diarios de un activo, vectorizadas.

    Aprovecha que entre dos cierres de trimestre los valores per-share son
    constantes: cada ratio es una división de arrays por segmento en lugar de
    un cálculo Python por fecha. Paridad exacta con _compute_daily_ratios
    (verificada por test)."""
    n = len(price_closes)
    codes = ("fundamental_pe_ttm", "fundamental_pb", "fundamental_ps_ttm",
             "fundamental_pe_growth_yoy")
    out = {c: np.full(n, np.nan) for c in codes}
    nq = len(quarters)
    if n == 0 or nq == 0:
        return out

    # Per-share por trimestre (constantes dentro de cada segmento)
    eps_ps  = np.full(nq, np.nan)
    rev_ps  = np.full(nq, np.nan)
    book_ps = np.full(nq, np.nan)
    for i, q in enumerate(quarters):
        ttm4   = quarters[max(0, i - 3): i + 1]
        shares = next((x.shares for x in reversed(ttm4) if x.shares), None)
        if not shares:
            continue
        e = _safe_div_r(sum(x.net_income for x in ttm4 if x.net_income is not None), shares)
        r = _safe_div_r(sum(x.revenue    for x in ttm4 if x.revenue    is not None), shares)
        b = _safe_div_r(q.equity, shares)
        if e is not None:
            eps_ps[i] = e
        if r is not None:
            rev_ps[i] = r
        if b is not None:
            book_ps[i] = b

    seg   = np.searchsorted(q_ords, price_dates_ord, side="right") - 1
    has_q = seg >= 0
    seg_c = np.where(has_q, seg, 0)

    def _ratio(per_share):
        ps = per_share[seg_c]
        ok = has_q & (ps > 0)                    # NaN > 0 → False
        return np.where(ok, np.round(price_closes / np.where(ok, ps, 1.0), 4), np.nan)

    out["fundamental_pe_ttm"] = _ratio(eps_ps)
    out["fundamental_pb"]     = _ratio(book_ps)
    out["fundamental_ps_ttm"] = _ratio(rev_ps)

    # P/E growth vs hace 1 año (TTM anclado al trimestre vigente en esa fecha)
    ref_ords = np.array([_ref_1y_ord(d) for d in price_dates], dtype=np.int64)
    q1y = np.searchsorted(q_ords, ref_ords, side="right") - 1
    p1y = np.searchsorted(price_dates_ord, ref_ords, side="right") - 1
    q1y_c, p1y_c = np.where(q1y >= 0, q1y, 0), np.where(p1y >= 0, p1y, 0)
    eps_prev = eps_ps[q1y_c]
    ok_prev  = (q1y >= 0) & (p1y >= 0) & (eps_prev > 0)
    pe_prev  = np.where(
        ok_prev,
        np.round(price_closes[p1y_c] / np.where(ok_prev, eps_prev, 1.0), 4),
        np.nan)
    pe   = out["fundamental_pe_ttm"]
    ok_g = ~np.isnan(pe) & (pe != 0) & ~np.isnan(pe_prev) & (pe_prev != 0)
    out["fundamental_pe_growth_yoy"] = np.where(
        ok_g,
        np.round((pe - pe_prev) / np.abs(np.where(ok_g, pe_prev, 1.0)), 4),
        np.nan)
    return out


# ── Backfill por indicador (1 thread por código) ──────────────────────────────

from collections import namedtuple as _nt

_Quarter = _nt("_Quarter", [
    "period_date", "revenue", "gross_profit", "operating_income", "net_income",
    "ebitda", "total_debt", "equity", "shares", "fcf", "operating_cf",
    "eps_actual", "eps_estimated", "nopat", "invested_capital_avg",
])


def _load_all_quarters(s) -> dict:
    """Carga todos los quarters como namedtuples thread-safe. {asset_id: [_Quarter]}"""
    from itertools import groupby as _gb
    rows = (s.query(FundamentalQuarterly)
              .order_by(FundamentalQuarterly.asset_id,
                        FundamentalQuarterly.period_date.asc())
              .all())
    cache: dict = {}
    for asset_id, grp in _gb(rows, key=lambda q: q.asset_id):
        cache[asset_id] = [
            _Quarter(
                period_date=q.period_date,
                revenue=q.revenue, gross_profit=q.gross_profit,
                operating_income=q.operating_income, net_income=q.net_income,
                ebitda=q.ebitda, total_debt=q.total_debt, equity=q.equity,
                shares=q.shares, fcf=q.fcf, operating_cf=q.operating_cf,
                eps_actual=q.eps_actual, eps_estimated=q.eps_estimated,
                nopat=q.nopat, invested_capital_avg=q.invested_capital_avg,
            )
            for q in grp
        ]
    return cache


def _load_fund_prices(_s, asset_ids: list) -> dict:
    """Carga (date, close) para los activos con fundamentales."""
    import pandas as pd
    from sqlalchemy import text as _text
    if not asset_ids:
        return {}
    ids_csv = ",".join(str(x) for x in asset_ids)
    with engine.connect() as conn:
        rows = conn.execute(
            _text(f"SELECT asset_id, date, close FROM prices"
                  f" WHERE asset_id IN ({ids_csv}) AND close IS NOT NULL"
                  f" ORDER BY asset_id, date")
        ).fetchall()
    df = pd.DataFrame(rows, columns=["asset_id", "date", "close"])
    return {
        aid: list(zip(sub["date"], sub["close"].astype(float)))
        for aid, sub in df.groupby("asset_id")
    }


def _backfill_fund_indicator(
    code: str,
    asset_ids: list,
    *,
    force: bool = False,
    asset_tick=None,
    quarters_cache: dict | None = None,
    price_cache: dict | None = None,
) -> dict:
    """Backfill de un indicador fundamental para todos los activos."""
    import sqlalchemy as sa
    s        = get_session()
    t        = get_ind_table(code)
    is_daily = code in _FUND_DAILY_CODES
    inserted = 0

    if force:
        # TRUNCATE: instantáneo y sin undo log (vs DELETE por activo)
        s.execute(sa.text(f"TRUNCATE TABLE {t.name}"))
        s.commit()

    for c0 in range(0, len(asset_ids), _EXISTING_CHUNK):
        chunk = asset_ids[c0:c0 + _EXISTING_CHUNK]

        # Fechas existentes del chunk en una sola query (evita 1 por activo)
        existing_by_asset: dict[int, set] = {}
        if not force:
            for aid, d in s.execute(
                sa.select(t.c.asset_id, t.c.date).where(t.c.asset_id.in_(chunk))
            ).fetchall():
                existing_by_asset.setdefault(aid, set()).add(d)

        for asset_id in chunk:
            quarters = quarters_cache.get(asset_id) if quarters_cache else [
                _Quarter(**{f: getattr(q, f) for f in _Quarter._fields})
                for q in s.query(FundamentalQuarterly)
                          .filter_by(asset_id=asset_id)
                          .order_by(FundamentalQuarterly.period_date.asc())
                          .all()
            ]
            if not quarters:
                if asset_tick:
                    asset_tick()
                continue

            q_ords   = np.array([q.period_date.toordinal() for q in quarters])
            existing = existing_by_asset.get(asset_id, set())

            if is_daily:
                price_rows = price_cache.get(asset_id) if price_cache else [
                    (r[0], r[1]) for r in
                    s.query(Price.date, Price.close)
                     .filter(Price.asset_id == asset_id, Price.close.isnot(None))
                     .order_by(Price.date.asc())
                     .all()
                ]
                if not price_rows:
                    if asset_tick:
                        asset_tick()
                    continue

                price_dates_ord = np.array([r[0].toordinal() for r in price_rows])
                price_closes    = np.array([float(r[1]) for r in price_rows])

                if force:
                    target = set(r[0] for r in price_rows)
                else:
                    target = {r[0] for r in price_rows} - existing
                    # El último precio es preliminar: su ratio se recalcula siempre
                    target.add(price_rows[-1][0])

                dates_seq = [r[0] for r in price_rows]
                series = _daily_ratio_series(quarters, q_ords, dates_seq,
                                             price_dates_ord, price_closes)
                batch = [
                    {"asset_id": asset_id, "date": d, "value": float(v)}
                    for d, v in zip(dates_seq, series[code])
                    if d in target and not np.isnan(v)
                ]
                if batch:
                    stmt = _mysql_insert(t).values(batch)
                    s.execute(stmt.on_duplicate_key_update(value=stmt.inserted.value))
                    inserted += len(batch)
            else:
                if force:
                    target = {q.period_date for q in quarters}
                else:
                    target = {q.period_date for q in quarters} - existing
                    # El último trimestre puede haber sido revisado por la fuente
                    target.add(quarters[-1].period_date)

                batch = []
                for idx, q in enumerate(quarters):
                    if q.period_date not in target:
                        continue
                    ratios = _compute_quarterly_ratios(quarters, idx)
                    val = ratios.get(code)
                    if val is not None:
                        batch.append({"asset_id": asset_id, "date": q.period_date,
                                      "value": float(val)})
                if batch:
                    stmt = _mysql_insert(t).values(batch)
                    s.execute(stmt.on_duplicate_key_update(value=stmt.inserted.value))
                    inserted += len(batch)

            if asset_tick:
                asset_tick()

        # Commit por chunk de activos: un fsync por activo es puro overhead
        # (los ratios trimestrales son ~decenas de filas por activo)
        s.commit()

    return {"inserted": inserted, "code": code}


def _backfill_fund_indicator_worker(
    code: str, asset_ids: list, force: bool,
    asset_tick, quarters_cache: dict, price_cache: dict,
) -> dict:
    from app.services.technical_service import _set_bulk_load_checks
    try:
        if force:
            _set_bulk_load_checks(get_session(), False)
        return _backfill_fund_indicator(
            code, asset_ids, force=force, asset_tick=asset_tick,
            quarters_cache=quarters_cache, price_cache=price_cache,
        )
    except Exception as exc:
        logger.warning("Fund backfill indicator error code=%s: %s", code, exc)
        return {"inserted": 0, "code": code, "error": str(exc)}
    finally:
        if force:
            _set_bulk_load_checks(get_session(), True)
        _ScopedSession.remove()


def _backfill_fund_daily_all(
    daily_codes: list, asset_ids: list, *,
    force: bool, tick_fns: dict,
    quarters_cache: dict, price_cache: dict,
) -> dict:
    """Procesa todos los daily codes en un único pass por activo×fecha.

    Llama a _compute_daily_ratios una sola vez por (activo, fecha) en lugar de
    una vez por código, eliminando 4x de cómputo redundante.
    """
    import sqlalchemy as sa
    s      = get_session()
    tables = {code: get_ind_table(code) for code in daily_codes}
    inserted = 0

    if force:
        # TRUNCATE: instantáneo y sin undo log (vs DELETE por activo)
        for t in tables.values():
            s.execute(sa.text(f"TRUNCATE TABLE {t.name}"))
        s.commit()

    for c0 in range(0, len(asset_ids), _EXISTING_CHUNK):
        chunk = asset_ids[c0:c0 + _EXISTING_CHUNK]

        # Fechas existentes por código para todo el chunk (evita 4 queries por activo)
        existing_by_code: dict[str, dict[int, set]] = {c: {} for c in daily_codes}
        if not force:
            for code, t in tables.items():
                for aid, d in s.execute(
                    sa.select(t.c.asset_id, t.c.date).where(t.c.asset_id.in_(chunk))
                ).fetchall():
                    existing_by_code[code].setdefault(aid, set()).add(d)

        for asset_id in chunk:
            quarters = quarters_cache.get(asset_id, [])
            if not quarters:
                for code in daily_codes:
                    tick_fns[code]()
                continue

            q_ords     = np.array([q.period_date.toordinal() for q in quarters])
            price_rows = price_cache.get(asset_id, [])
            if not price_rows:
                for code in daily_codes:
                    tick_fns[code]()
                continue

            price_dates_ord = np.array([r[0].toordinal() for r in price_rows])
            price_closes    = np.array([float(r[1]) for r in price_rows])

            if force:
                all_dates = {r[0] for r in price_rows}
                targets   = {code: all_dates for code in daily_codes}
            else:
                targets = {
                    code: {r[0] for r in price_rows}
                          - existing_by_code[code].get(asset_id, set())
                    for code in daily_codes
                }
                # El último precio es preliminar: su ratio se recalcula siempre
                last_d = price_rows[-1][0]
                for code in daily_codes:
                    targets[code].add(last_d)

            dates_seq = [r[0] for r in price_rows]
            series = _daily_ratio_series(quarters, q_ords, dates_seq,
                                         price_dates_ord, price_closes)
            batches = {
                code: [
                    {"asset_id": asset_id, "date": d, "value": float(v)}
                    for d, v in zip(dates_seq, series[code])
                    if d in targets[code] and not np.isnan(v)
                ]
                for code in daily_codes
            }

            for code, batch in batches.items():
                if batch:
                    t    = tables[code]
                    stmt = _mysql_insert(t).values(batch)
                    s.execute(stmt.on_duplicate_key_update(value=stmt.inserted.value))
                    inserted += len(batch)

            s.commit()
            for code in daily_codes:
                tick_fns[code]()

    return {"inserted": inserted, "codes": daily_codes}


def _backfill_fund_daily_all_worker(
    daily_codes: list, asset_ids: list, force: bool,
    tick_fns: dict, quarters_cache: dict, price_cache: dict,
) -> dict:
    from app.services.technical_service import _set_bulk_load_checks
    try:
        if force:
            _set_bulk_load_checks(get_session(), False)
        return _backfill_fund_daily_all(
            daily_codes, asset_ids, force=force, tick_fns=tick_fns,
            quarters_cache=quarters_cache, price_cache=price_cache,
        )
    except Exception as exc:
        logger.warning("Fund backfill daily error codes=%s: %s", daily_codes, exc)
        return {"inserted": 0, "codes": daily_codes, "error": str(exc)}
    finally:
        if force:
            _set_bulk_load_checks(get_session(), True)
        _ScopedSession.remove()


def backfill_all_fundamental_values(progress_cb=None, *, force: bool = False,
                                    quarters_cache: dict | None = None) -> dict:
    """Backfill histórico de indicadores fundamentales.

    Indicadores trimestrales: 1 thread por código.
    Indicadores diarios (pe_ttm, pb, ps_ttm, pe_growth_yoy): 1 thread combinado
    que llama _compute_daily_ratios una sola vez por (activo, fecha).

    quarters_cache: si el caller ya lo cargó (ver _run_ratios_and_backfill,
    que lo comparte con recompute_all_ratios), se reusa en vez de volver a
    consultarlo.
    """
    import threading as _th
    s               = get_session()
    fund_codes      = sorted(_ALL_FUND_CODES)
    daily_codes     = sorted(c for c in fund_codes if c in _FUND_DAILY_CODES)
    quarterly_codes = sorted(c for c in fund_codes if c not in _FUND_DAILY_CODES)
    n_ind           = len(fund_codes)

    if progress_cb:
        progress_cb(0, 1, "Cargando datos fundamentales en memoria...")

    if quarters_cache is None:
        logger.info("Pre-cargando datos fundamentales en memoria...")
        quarters_cache = _load_all_quarters(s)
    asset_ids      = sorted(quarters_cache.keys())
    price_cache    = _load_fund_prices(s, asset_ids)
    n_assets       = len(asset_ids)
    total_work     = n_ind * n_assets
    logger.info("Datos cargados: %d activos, %d indicadores", n_assets, n_ind)

    done_ind = 0
    inserted = 0
    errors:  list[dict] = []

    _assets_done = 0
    _lock        = _th.Lock()

    def _make_tick(code):
        per_ind = [0]
        def _tick():
            nonlocal _assets_done
            per_ind[0] += 1
            with _lock:
                _assets_done += 1
                n = _assets_done
            if progress_cb:
                progress_cb(n, total_work, f"{code}: {per_ind[0]}/{n_assets}")
        return _tick

    tick_fns = {code: _make_tick(code) for code in fund_codes}

    # n_workers = quarterly codes + 1 combined daily worker
    n_workers = len(quarterly_codes) + (1 if daily_codes else 0)
    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures: dict = {}

        for code in quarterly_codes:
            futures[pool.submit(
                _backfill_fund_indicator_worker,
                code, asset_ids, force, tick_fns[code],
                quarters_cache, price_cache,
            )] = [code]

        if daily_codes:
            futures[pool.submit(
                _backfill_fund_daily_all_worker,
                daily_codes, asset_ids, force,
                {c: tick_fns[c] for c in daily_codes},
                quarters_cache, price_cache,
            )] = daily_codes

        if progress_cb:
            progress_cb(0, total_work, f"__init__:{n_assets}:{','.join(fund_codes)}")

        for future in as_completed(futures):
            done_ind += 1
            codes = futures[future]
            try:
                res = future.result()
                inserted += res.get("inserted", 0)
                if "error" in res:
                    errors.append({"code": str(codes), "error": res["error"]})
            except Exception as exc:
                logger.warning("Fund backfill future error codes=%s: %s", codes, exc)
                errors.append({"code": str(codes), "error": str(exc)})

    return {"total": n_ind, "success": n_ind - len(errors),
            "inserted": inserted, "errors": errors}


# ── Acciones combinadas (Centro de Datos) ───────────────────────────────────────

def _run_ratios_and_backfill(progress_cb, *, force: bool) -> dict:
    """recompute_all_ratios + backfill_all_fundamental_values en secuencia,
    con una barra de progreso COMBINADA — mismo patrón y mismo motivo que
    _run_current_and_backfill en technical_service.py: cada fase reporta su
    propio (cur, total) interno, y sin combinarlos la barra salta hacia
    atrás al pasar de una fase a la otra (el usuario lo notó como "se
    resetea", igual que ya había pasado con los indicadores técnicos).

    quarters_cache se carga UNA sola vez acá y se comparte entre las dos
    fases (antes cada una llamaba a _load_all_quarters por separado) — de
    paso el total combinado queda exacto, ya que ambas fases cuentan los
    mismos activos."""
    s = get_session()
    if progress_cb:
        progress_cb(0, 1, "Cargando datos fundamentales en memoria...")
    quarters_cache = _load_all_quarters(s)
    n_assets       = len(quarters_cache)
    n_ind          = len(_ALL_FUND_CODES)

    ratios_total   = n_assets
    backfill_total = n_ind * n_assets
    combined_total = ratios_total + backfill_total

    def _offset_cb(offset):
        def _cb(cur, tot, label=""):
            if progress_cb:
                progress_cb(offset + cur, combined_total, label)
        return _cb

    if force:
        # Rebuild: historia completa primero (los ratios vigentes dependen
        # de ella), ratios vigentes después.
        r1 = backfill_all_fundamental_values(progress_cb=_offset_cb(0), force=True,
                                             quarters_cache=quarters_cache)
        r2 = recompute_all_ratios(progress_cb=_offset_cb(backfill_total),
                                  quarters_cache=quarters_cache)
        total = r2["total"]
    else:
        # Delta: ratios vigentes primero, historia (huecos) después — orden
        # igual que antes.
        r1 = recompute_all_ratios(progress_cb=_offset_cb(0), quarters_cache=quarters_cache)
        r2 = backfill_all_fundamental_values(progress_cb=_offset_cb(ratios_total), force=False,
                                             quarters_cache=quarters_cache)
        total = r1["total"]

    errors = r1["errors"] + r2["errors"]
    return {"total": total, "success": max(total - len(errors), 0), "errors": errors}


def update_ratio_history(progress_cb=None) -> dict:
    """Recomputa los ratios vigentes y completa huecos históricos (backfill delta)."""
    return _run_ratios_and_backfill(progress_cb, force=False)


def rebuild_ratio_history(progress_cb=None) -> dict:
    """Borra y recalcula todo el historial de ratios fundamentales desde cero."""
    return _run_ratios_and_backfill(progress_cb, force=True)
