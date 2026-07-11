import bisect
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
# Commits por lote en recompute_all_ratios: cada asset_id se procesa en su
# propio SAVEPOINT (ver recompute_all_ratios), así que un error puntual solo
# descarta ese activo, no el resto del lote ya procesado.
_RATIO_COMMIT_BATCH = 50

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
    "fundamental_net_income_growth_yoy",
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
                              replace: bool = False, skip_ratios: bool = False) -> None:
    """replace=True borra el historial trimestral existente y lo reemplaza por la
    descarga nueva, dentro de la misma transacción: si la descarga falla, el
    historial previo se conserva.

    skip_ratios=True: no recalcula ratios acá (lo usan las corridas masivas
    — update_new_fundamentals/update_all_fundamentals/redownload_all_fundamentals
    — que descargan reportes para muchos activos y después encadenan
    _run_ratios_and_backfill una sola vez para todos, en vez de recalcular
    activo por activo con este camino rápido). Los llamadores puntuales
    (botón "Recalcular indicadores" de la página de Precios, alta de activo
    nuevo) siguen usando el default False."""
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

    if skip_ratios:
        return

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


def backfill_asset_fund_history(asset_id: int) -> dict:
    """Reconstruye desde cero la historia de ratios fundamentales
    (ind_fundamental_*) de UN activo — equivalente fundamental de
    backfill_asset_history (technical_service.py): borra las filas de ese
    activo en cada ind_fundamental_* (DELETE puntual por asset_id, no
    TRUNCATE — a diferencia de backfill_all_fundamental_values(force=True),
    esto no toca el resto de la tabla) y las recalcula completas a partir
    de los trimestrales/precios ya guardados.

    Pensado para después de un redescargo puntual de fundamentales
    (ver redownload_all_fundamentals con selección): como los trimestrales
    son enteramente nuevos, conviene recalcular todo en vez de confiar en
    el atajo delta de _backfill_fund_indicator (que solo completa fechas
    faltantes)."""
    s = get_session()
    quarters = _load_all_quarters(s, [asset_id]).get(asset_id, [])
    if not quarters:
        return {"inserted": 0}
    q_ords = np.array([q.period_date.toordinal() for q in quarters])
    price_rows = _load_fund_prices(s, [asset_id]).get(asset_id, [])

    inserted = 0
    for code in sorted(_ALL_FUND_CODES):
        t = get_ind_table(code)
        s.execute(t.delete().where(t.c.asset_id == asset_id))

        if code in _FUND_DAILY_CODES:
            if not price_rows:
                continue
            dates_seq       = [d for d, _ in price_rows]
            price_dates_ord = np.array([d.toordinal() for d, _ in price_rows])
            price_closes    = np.array([c for _, c in price_rows])
            series = _daily_ratio_series(quarters, q_ords, dates_seq,
                                         price_dates_ord, price_closes)
            batch = [{"asset_id": asset_id, "date": d, "value": float(v)}
                    for d, v in zip(dates_seq, series[code]) if not np.isnan(v)]
        else:
            batch = []
            for idx, q in enumerate(quarters):
                val = _compute_quarterly_ratios(quarters, idx).get(code)
                if val is not None:
                    batch.append({"asset_id": asset_id, "date": q.period_date,
                                  "value": float(val)})

        if batch:
            stmt = _mysql_insert(t).values(batch)
            s.execute(stmt.on_duplicate_key_update(value=stmt.inserted.value))
            inserted += len(batch)

    s.commit()
    return {"inserted": inserted}


def _rebuild_ratios_for_assets(progress_cb, asset_ids: list) -> dict:
    """Recalculo COMPLETO (no delta) de ratios fundamentales para una
    selección puntual de activos — usado tras un redescargo de
    trimestrales puntual (ver redownload_all_fundamentals): como los
    trimestrales son enteramente nuevos, un delta podría no recalcular
    fechas ya escritas que ahora deberían dar un valor distinto; el
    rebuild por activo no tiene atajos, así que siempre queda consistente.
    El costo es aceptable porque esta selección siempre es chica (uso
    puntual desde /admin/fundamentals, no la corrida global)."""
    total  = len(asset_ids)
    errors = []
    for i, aid in enumerate(asset_ids, 1):
        if progress_cb:
            progress_cb(i, total, f"Recalculando ratios id={aid}...")
        try:
            recompute_ratios_for_asset(aid)
            backfill_asset_fund_history(aid)
        except Exception as exc:
            errors.append({"ticker": str(aid), "error": str(exc)})
    return {"total": total, "success": total - len(errors), "errors": errors}


def recompute_all_ratios(progress_cb=None, *, quarters_cache: dict | None = None,
                         price_cache: dict | None = None) -> dict:
    """Recomputa los ratios vigentes de todos los activos con fundamentales.

    quarters_cache/price_cache: si el caller ya los cargó (ver
    _run_ratios_and_backfill, que los comparte con
    backfill_all_fundamental_values), se reusan en vez de volver a
    consultarlos — antes esta función hacía sus propias 2 queries
    GROUP BY MAX(date) contra toda la tabla prices (_prices_asof, ya
    eliminada) aunque backfill_all_fundamental_values ya había cargado
    virtualmente los mismos datos; con price_cache alcanza un bisect en
    memoria (_price_asof_from_cache), sin depender de qué tan tibio esté
    el buffer pool de MariaDB (ver _run_ratios_and_backfill: el orden de
    fases se invierte entre delta y force, así que antes el costo de estas
    2 queries variaba mucho según el modo)."""
    from datetime import timedelta as _td

    s = get_session()
    if quarters_cache is None:
        quarters_cache = _load_all_quarters(s)
    asset_ids = sorted(quarters_cache.keys())
    total   = len(asset_ids)
    summary = {"total": total, "success": 0, "errors": []}
    if not asset_ids:
        return summary

    if price_cache is None:
        price_cache = _load_fund_prices(s, asset_ids)
    cutoff = _date_type.today() - _td(days=365)

    asset_errors: dict[int, str] = {}
    if progress_cb:
        progress_cb(0, total)
    for i, asset_id in enumerate(asset_ids, 1):
        prices = price_cache.get(asset_id, [])
        try:
            with s.begin_nested():
                _compute_current_ratios(
                    asset_id, s,
                    quarters=quarters_cache[asset_id],
                    latest_price=_price_asof_from_cache(prices),
                    price_1y=_price_asof_from_cache(prices, cutoff),
                )
            summary["success"] += 1
        except Exception as exc:
            logger.error("Error recompute fundamental asset_id=%d: %s", asset_id, exc, exc_info=True)
            summary["errors"].append({"asset_id": asset_id, "error": str(exc)})
            asset_errors[asset_id] = str(exc)
        # SAVEPOINT por activo (arriba) ya aísla un error puntual del resto
        # del lote; el commit real se batchea cada _RATIO_COMMIT_BATCH para
        # no pagar un round-trip a la base por cada uno de los ~350-10000
        # activos (ver _RATIO_COMMIT_BATCH).
        if i % _RATIO_COMMIT_BATCH == 0:
            s.commit()
        if progress_cb:
            progress_cb(i, total)
    s.commit()   # cierra el resto del último lote parcial

    # Un registro por activo en indicator_update_log (mismo patrón que
    # recompute_current_indicators en technical_service.py) — necesario
    # porque update_all_fundamentals/update_new_fundamentals/
    # redownload_all_fundamentals ahora encadenan acá con skip_ratios=True
    # en vez de recalcular ratios activo por activo (que era quien
    # escribía este log antes).
    from app.services.technical_service import _save_indicator_log
    for asset_id in asset_ids:
        _save_indicator_log(
            asset_id, success=asset_id not in asset_errors,
            error=asset_errors.get(asset_id), session=s,
        )
    return summary


def _fund_worker(asset_id: int, ticker: str, *, clear: bool = False,
                 skip_ratios: bool = False) -> tuple[bool, dict | None]:
    """_UPDATE_WORKERS threads concurrentes escriben cada uno a un asset_id
    distinto en fundamental_quarterly, pero InnoDB puede igual deadlockear
    entre INSERTs concurrentes a la misma tabla (gap locks/FK checks, no
    hace falta que se pisen filas). Reintenta la transacción completa (todo
    update_asset_fundamentals, es idempotente) ante deadlock/lock timeout,
    tal como recomienda la documentación de InnoDB."""
    for attempt in range(_MAX_LOCK_RETRIES + 1):
        try:
            update_asset_fundamentals(asset_id, force=clear, replace=clear,
                                      skip_ratios=skip_ratios)
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
                    total: int | None = None, skip_ratios: bool = False) -> dict:
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
        futures = {pool.submit(_fund_worker, aid, ticker, clear=clear,
                               skip_ratios=skip_ratios): ticker
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


def _chain_to_ratio_delta(progress_cb, download_result: dict) -> dict:
    """Encadena _run_ratios_and_backfill(force=False) después de una
    descarga masiva de fundamentales (ver skip_ratios en
    update_asset_fundamentals: las corridas masivas ya no recalculan
    ratios activo por activo, lo hacen acá una sola vez para todos).

    La barra de progreso se reacomoda al pasar de la fase de descarga a
    la de ratios (cada fase reporta su propio total) — aceptado, el
    mensaje aclara qué fase está corriendo en cada momento.

    Si no había nada para descargar (ej. "solo nuevos" sin nada nuevo), no
    vale la pena pagar un delta completo por nada — se salta.

    Solo la usan los jobs globales (update_new_fundamentals/update_all_
    fundamentals) — redownload_all_fundamentals con selección puntual usa
    _rebuild_ratios_for_assets en su lugar (rebuild completo por activo,
    no delta: ver esa función para el motivo)."""
    if download_result.get("total", 0) == 0:
        return download_result
    if progress_cb:
        progress_cb(0, 1, "Recalculando ratios...")
    ratio_result = _run_ratios_and_backfill(progress_cb, force=False)
    # Acumulado, no solo el de la última fase: success + len(errors) tiene
    # que dar total, si no el resumen final ("X/Y OK") no cierra.
    total   = download_result["total"]   + ratio_result["total"]
    success = download_result["success"] + ratio_result["success"]
    errors  = download_result["errors"]  + ratio_result["errors"]
    return {"total": total, "success": success, "errors": errors}


def update_new_fundamentals(progress_cb=None) -> dict:
    s = get_session()
    logged_ids = {r[0] for r in s.query(FundamentalUpdateLog.asset_id).all()}
    assets = s.query(Asset).filter(
        Asset.fundamental_source_id.isnot(None),
        ~Asset.id.in_(logged_ids) if logged_ids else True,
    ).all()
    pairs = [(a.id, a.ticker) for a in assets]
    download_result = _run_fund_batch(pairs, progress_cb=progress_cb, skip_ratios=True)
    return _chain_to_ratio_delta(progress_cb, download_result)


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
    download_result = _run_fund_batch(stale_pairs, progress_cb=progress_cb,
                                      presuccess=fresh_count, total=len(pairs),
                                      skip_ratios=True)
    return _chain_to_ratio_delta(progress_cb, download_result)


def redownload_all_fundamentals(asset_ids: list[int] | None = None, progress_cb=None) -> dict:
    """Borra el historial trimestral y lo redescarga completo desde la fuente.
    Si asset_ids es None, aplica a todos los activos con fuente configurada
    (mismo patrón que redownload_prices en price_service.py).

    Con una selección puntual, el recálculo de ratios que sigue a la
    descarga es un rebuild COMPLETO por activo (_rebuild_ratios_for_assets),
    no el delta que usan los jobs globales (_chain_to_ratio_delta) — los
    trimestrales son enteramente nuevos, así que conviene recalcular todo
    en vez de confiar en atajos. Antes esto además recorría el universo
    entero aunque se hubiese redescargado un solo activo puntual, dando un
    resumen final confuso (ej. "351/352 exitosos" habiendo seleccionado 1)."""
    s = get_session()
    q = s.query(Asset).filter(Asset.fundamental_source_id.isnot(None))
    if asset_ids is not None:
        q = q.filter(Asset.id.in_(asset_ids))
    assets = q.all()
    pairs  = [(a.id, a.ticker) for a in assets]
    download_result = _run_fund_batch(pairs, clear=True, progress_cb=progress_cb,
                                      skip_ratios=True)

    if asset_ids is None:
        return _chain_to_ratio_delta(progress_cb, download_result)
    if download_result.get("total", 0) == 0:
        return download_result
    if progress_cb:
        progress_cb(0, 1, "Recalculando ratios...")
    ratio_result = _rebuild_ratios_for_assets(progress_cb, asset_ids)
    total   = download_result["total"]   + ratio_result["total"]
    success = download_result["success"] + ratio_result["success"]
    errors  = download_result["errors"]  + ratio_result["errors"]
    return {"total": total, "success": success, "errors": errors}


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
        "fundamental_eps_growth_yoy", "fundamental_net_income_growth_yoy",
        "fundamental_pe_growth_yoy", "fundamental_roic",
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
            "revenue_growth_yoy":    snap_vals.get("revenue_growth_yoy"),
            "eps_growth_yoy":        snap_vals.get("eps_growth_yoy"),
            "net_income_growth_yoy": snap_vals.get("net_income_growth_yoy"),
            "pe_growth_yoy":         snap_vals.get("pe_growth_yoy"),
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

    rev_growth = eps_growth = ni_growth = None
    if idx >= 4:
        q4 = quarters[idx - 4]
        rev_growth = _safe_div_r(
            (q.revenue - q4.revenue) if (q.revenue is not None and q4.revenue is not None) else None,
            abs(q4.revenue) if q4.revenue else None,
        )
        eps_growth = _safe_div_r(
            (q.eps_actual - q4.eps_actual) if (q.eps_actual is not None and q4.eps_actual is not None) else None,
            abs(q4.eps_actual) if q4.eps_actual else None,
        )
        ni_growth = _safe_div_r(
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
        "fundamental_revenue_growth_yoy":    rev_growth,
        "fundamental_eps_growth_yoy":        eps_growth,
        "fundamental_net_income_growth_yoy": ni_growth,
        "fundamental_roic":                  roic,
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

    book_ps = _safe_div_r(latest.equity, shares)
    pb = _safe_div_r(price, book_ps) if book_ps and book_ps > 0 else None

    # TTM (trailing twelve months) necesita 4 trimestres reales: con menos
    # (activo recién agregado, aún sin un año de historia) sumar los que
    # haya subestima la ganancia/ingreso anualizado y da un P/E sin
    # sentido (hallazgo real: CMPC.SN con 1 solo trimestre cargado dio
    # P/E ~369000) — mejor no calcular hasta tener el año completo.
    pe = ps = None
    if len(ttm4) == 4:
        ttm_eps = sum(q.net_income for q in ttm4 if q.net_income is not None)
        ttm_rev = sum(q.revenue    for q in ttm4 if q.revenue    is not None)
        ttm_eps_ps = _safe_div_r(ttm_eps, shares)
        ttm_rev_ps = _safe_div_r(ttm_rev, shares)
        pe = _safe_div_r(price, ttm_eps_ps) if ttm_eps_ps and ttm_eps_ps > 0 else None
        ps = _safe_div_r(price, ttm_rev_ps) if ttm_rev_ps and ttm_rev_ps > 0 else None

    pe_growth = None
    last_q_1y = int(np.searchsorted(q_ords, ref_1y_ord, side="right")) - 1
    if last_q_1y >= 0:
        ttm4_prev = quarters[max(0, last_q_1y - 3): last_q_1y + 1]
        if len(ttm4_prev) == 4:
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
        b = _safe_div_r(q.equity, shares)
        if b is not None:
            book_ps[i] = b
        # ver _compute_daily_ratios: TTM necesita 4 trimestres reales, si no
        # el ingreso/ganancia anualizado queda subestimado y el ratio no
        # tiene sentido. pb no depende de esto (usa solo el trimestre actual).
        if len(ttm4) != 4:
            continue
        e = _safe_div_r(sum(x.net_income for x in ttm4 if x.net_income is not None), shares)
        r = _safe_div_r(sum(x.revenue    for x in ttm4 if x.revenue    is not None), shares)
        if e is not None:
            eps_ps[i] = e
        if r is not None:
            rev_ps[i] = r

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


def _load_all_quarters(s, asset_ids: list | None = None) -> dict:
    """Carga los quarters como namedtuples thread-safe. {asset_id: [_Quarter]}
    asset_ids=None: todos los activos con fundamentales (default, sin
    cambios); si se pasa una lista, solo esos (ver _run_ratios_and_backfill,
    usado para escopar el recálculo de ratios a un redescargo puntual en
    vez de recorrer siempre el universo entero)."""
    from itertools import groupby as _gb
    q = s.query(FundamentalQuarterly)
    if asset_ids is not None:
        q = q.filter(FundamentalQuarterly.asset_id.in_(asset_ids))
    rows = (q.order_by(FundamentalQuarterly.asset_id,
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


def _price_asof_from_cache(prices: list, max_date=None) -> float | None:
    """Último close de una lista [(date, close), ...] ordenada por fecha
    ascendente (ver _load_fund_prices), opcionalmente acotado a
    fecha <= max_date. None si no hay ninguna fila que cumpla.

    Reemplaza las 2 queries GROUP BY MAX(date) que hacía _prices_asof()
    (recompute_all_ratios) contra toda la tabla prices: con price_cache ya
    cargado (lo carga backfill_all_fundamental_values de todos modos, ver
    _run_ratios_and_backfill) alcanza con un bisect en memoria, sin ida y
    vuelta a la base ni depender de que el buffer pool esté tibio."""
    if not prices:
        return None
    if max_date is None:
        return prices[-1][1]
    dates = [d for d, _ in prices]
    idx = bisect.bisect_right(dates, max_date) - 1
    return prices[idx][1] if idx >= 0 else None


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
                                    quarters_cache: dict | None = None,
                                    price_cache: dict | None = None) -> dict:
    """Backfill histórico de indicadores fundamentales.

    Indicadores trimestrales: 1 thread por código.
    Indicadores diarios (pe_ttm, pb, ps_ttm, pe_growth_yoy): 1 thread combinado
    que llama _compute_daily_ratios una sola vez por (activo, fecha).

    quarters_cache/price_cache: si el caller ya los cargó (ver
    _run_ratios_and_backfill, que los comparte con recompute_all_ratios),
    se reusan en vez de volver a consultarlos.
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
    if price_cache is None:
        price_cache = _load_fund_prices(s, asset_ids)
    n_assets       = len(asset_ids)
    total_work     = n_ind * n_assets
    logger.info("Datos cargados: %d activos, %d indicadores", n_assets, n_ind)

    done_ind = 0
    inserted = 0
    errors:  list[dict] = []

    _assets_done  = 0
    _lock         = _th.Lock()
    _worker_slots: dict[int, int] = {}

    def _worker_slot() -> int:
        ident = _th.get_ident()
        with _lock:
            if ident not in _worker_slots:
                _worker_slots[ident] = len(_worker_slots)
            return _worker_slots[ident]

    def _make_tick(code):
        per_ind = [0]
        def _tick():
            nonlocal _assets_done
            per_ind[0] += 1
            with _lock:
                _assets_done += 1
                n = _assets_done
            if progress_cb:
                progress_cb(n, total_work, f"{code}: {per_ind[0]}/{n_assets} w{_worker_slot()}")
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

    quarters_cache/price_cache se cargan UNA sola vez acá y se comparten
    entre las dos fases (antes cada una llamaba a _load_all_quarters /
    hacía sus propias queries de precio por separado) — de paso el total
    combinado queda exacto (ambas fases cuentan los mismos activos) y
    recompute_all_ratios deja de pagar 2 queries GROUP BY MAX(date) contra
    toda la tabla prices que backfill_all_fundamental_values ya había
    resuelto con price_cache (ver _price_asof_from_cache): antes, según el
    orden de fases (que se invierte entre delta y force), esas 2 queries
    podían salir con el buffer pool frío o tibio — una asimetría de tiempo
    que no tenía que ver con cuánto trabajo real había, solo con el orden."""
    s = get_session()
    if progress_cb:
        progress_cb(0, 1, "Cargando datos fundamentales en memoria...")
    quarters_cache = _load_all_quarters(s)
    asset_ids      = sorted(quarters_cache.keys())
    price_cache    = _load_fund_prices(s, asset_ids)
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
                                             quarters_cache=quarters_cache,
                                             price_cache=price_cache)
        r2 = recompute_all_ratios(progress_cb=_offset_cb(backfill_total),
                                  quarters_cache=quarters_cache, price_cache=price_cache)
        total = r2["total"]
    else:
        # Delta: ratios vigentes primero, historia (huecos) después — orden
        # igual que antes.
        r1 = recompute_all_ratios(progress_cb=_offset_cb(0), quarters_cache=quarters_cache,
                                  price_cache=price_cache)
        r2 = backfill_all_fundamental_values(progress_cb=_offset_cb(ratios_total), force=False,
                                             quarters_cache=quarters_cache,
                                             price_cache=price_cache)
        total = r1["total"]

    errors = r1["errors"] + r2["errors"]
    return {"total": total, "success": max(total - len(errors), 0), "errors": errors}


def update_ratio_history(progress_cb=None) -> dict:
    """Recomputa los ratios vigentes y completa huecos históricos (backfill delta)."""
    return _run_ratios_and_backfill(progress_cb, force=False)


def rebuild_ratio_history(progress_cb=None) -> dict:
    """Borra y recalcula todo el historial de ratios fundamentales desde cero."""
    return _run_ratios_and_backfill(progress_cb, force=True)
