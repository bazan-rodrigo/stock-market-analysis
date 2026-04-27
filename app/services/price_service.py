"""
Servicio de descarga y actualización de precios históricos.
Lógica principal:
  - Si el activo no tiene precios: descarga toda la historia.
  - Si ya tiene precios: borra el último día y descarga desde ese día inclusive.
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd
import yfinance as yf
from sqlalchemy import func

from app.database import get_session, Session as _ScopedSession
from app.models import Asset, Price, PriceUpdateLog
from app.services.screener_service import (
    compute_and_save_snapshot,
    _get_drawdown_config,
    _get_regime_config,
    _get_volatility_config,
)
from app.services import sr_service
from app.sources.registry import get_source

logger = logging.getLogger(__name__)

# Activos procesados en paralelo (DB write + snapshot por activo)
_UPDATE_WORKERS = 6


def _get_last_price_date(asset_id: int, session):
    result = (
        session.query(func.max(Price.date))
        .filter(Price.asset_id == asset_id)
        .scalar()
    )
    return result  # datetime.date o None


def _delete_from_date(asset_id: int, from_date, session) -> None:
    session.query(Price).filter(
        Price.asset_id == asset_id, Price.date >= from_date
    ).delete(synchronize_session=False)


def _upsert_prices(asset_id: int, df, session) -> int:
    """Inserta filas del DataFrame en la tabla de precios. Devuelve cantidad insertada."""
    if df.empty:
        return 0
    import math
    mappings = [
        {
            "asset_id": asset_id,
            "date":     row.date,
            "open":     row.open,
            "high":     row.high,
            "low":      row.low,
            "close":    row.close,
            "volume":   int(row.volume) if (row.volume is not None and not math.isnan(float(row.volume))) else None,
        }
        for row in df.itertuples(index=False)
    ]
    session.bulk_insert_mappings(Price, mappings)
    return len(mappings)


def _save_update_log(asset_id: int, success: bool, error: str | None, session) -> None:
    log = session.query(PriceUpdateLog).filter(
        PriceUpdateLog.asset_id == asset_id
    ).first()
    if log is None:
        log = PriceUpdateLog(asset_id=asset_id, success=success, error_detail=error)
        session.add(log)
    else:
        log.last_attempt_at = datetime.utcnow()
        log.success = success
        log.error_detail = error


def update_asset_prices(
    asset_id: int,
    *,
    _dd_cfg=None,
    _regime_cfg=None,
    _vol_cfg=None,
    _sr_cfg=None,
) -> None:
    """
    Actualiza los precios de un activo.
    Si el activo es sintético (fuente Calculado), delega al synthetic_service.
    Si falla, registra el error en price_update_log y relanza la excepción.
    Los parámetros _*_cfg permiten reutilizar configs pre-cargadas en llamadas masivas.
    """
    from app.services.synthetic_service import compute_synthetic_prices

    s  = get_session()
    asset = s.get(Asset, asset_id)
    if asset is None:
        raise ValueError(f"Activo id={asset_id} no encontrado")

    if asset.price_source.name == "Calculado":
        compute_synthetic_prices(asset_id, full=False)
        return

    source = get_source(asset.price_source.name)
    last_date = _get_last_price_date(asset_id, s)

    try:
        if last_date is None:
            df = source.download_history(asset.ticker)
        else:
            _delete_from_date(asset_id, last_date, s)
            df = source.download_history(asset.ticker, start=last_date)

        if df.empty:
            raise ValueError(f"No se encontraron datos de precio para '{asset.ticker}'. Verificá que el ticker sea válido en Yahoo Finance.")

        count = _upsert_prices(asset_id, df, s)
        _save_update_log(asset_id, success=True, error=None, session=s)
        s.commit()
        logger.info("Activo %s: %d filas importadas", asset.ticker, count)

        # Recalcular snapshot del screener
        try:
            compute_and_save_snapshot(
                asset_id,
                _dd_cfg=_dd_cfg,
                _regime_cfg=_regime_cfg,
                _vol_cfg=_vol_cfg,
                _sr_cfg=_sr_cfg,
                quick=True,
            )
        except Exception as snap_exc:
            logger.warning(
                "Error calculando snapshot screener para %s: %s", asset.ticker, snap_exc
            )

    except NotImplementedError as exc:
        s.rollback()
        error_msg = str(exc)
        logger.info("Activo %s omitido (fuente no descargable): %s", asset.ticker, error_msg)
        _save_update_log(asset_id, success=False, error=error_msg, session=s)
        s.commit()
    except Exception as exc:
        s.rollback()
        error_msg = str(exc)
        logger.error("Error actualizando precios de %s: %s", asset.ticker, error_msg)
        _save_update_log(asset_id, success=False, error=error_msg, session=s)
        s.commit()
        raise


_YF_COLS = ["date", "open", "high", "low", "close", "volume"]


def _yf_batch_download(tickers: list, start=None) -> "pd.DataFrame | None":
    """
    Un solo yf.download(). start=None → period='max', start=date → desde esa fecha.
    Retorna el DataFrame crudo o None si falla.
    """
    try:
        kwargs = dict(auto_adjust=True, group_by="ticker", progress=False, threads=True)
        if start is None:
            return yf.download(tickers, period="max", **kwargs)
        else:
            return yf.download(tickers, start=start.isoformat(), **kwargs)
    except Exception as exc:
        logger.warning("Batch yfinance download falló (%s): %s", tickers, exc)
        return None


def _extract_ticker_df(raw, ticker: str) -> "pd.DataFrame":
    """Extrae y normaliza el sub-DataFrame de un ticker del resultado batch."""
    _rename = {"Date": "date", "Open": "open", "High": "high",
               "Low": "low", "Close": "close", "Volume": "volume"}
    df = raw[ticker].copy() if isinstance(raw.columns, pd.MultiIndex) else raw.copy()
    df = df.reset_index()
    df.rename(columns=_rename, inplace=True)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    present = [c for c in _YF_COLS if c in df.columns]
    return df[present].dropna(subset=["close"])


def _bulk_prefetch_yfinance(assets_with_dates: list) -> dict:
    """
    Descarga precios de múltiples tickers en el menor número de llamadas posible.
    assets_with_dates: lista de (asset, last_date).
    Retorna dict {asset_id: DataFrame}.

    Separación en dos grupos para manejar fechas distintas correctamente:
    - Sin last_date (primera vez): necesitan historia completa → batch con period='max'.
    - Con last_date: incrementales → batch desde min(last_dates) del grupo.
      Cada ticker recibe solo las filas >= su propio last_date (filtro en memoria).
    """
    if not assets_with_dates:
        return {}

    first_time  = [(a, d) for a, d in assets_with_dates if d is None]
    incremental = [(a, d) for a, d in assets_with_dates if d is not None]
    result = {}

    # --- Grupo 1: primera descarga (historia completa) ---
    if first_time:
        tickers = [a.ticker for a, _ in first_time]
        raw = _yf_batch_download(tickers, start=None)
        if raw is not None:
            for asset, _ in first_time:
                try:
                    result[asset.id] = _extract_ticker_df(raw, asset.ticker)
                except Exception as exc:
                    logger.warning("Error procesando batch (full) para %s: %s", asset.ticker, exc)

    # --- Grupo 2: actualizaciones incrementales ---
    if incremental:
        min_start = min(d for _, d in incremental)
        tickers   = [a.ticker for a, _ in incremental]
        raw = _yf_batch_download(tickers, start=min_start)
        if raw is not None:
            for asset, last_date in incremental:
                try:
                    df = _extract_ticker_df(raw, asset.ticker)
                    # Cada ticker solo recibe filas desde su propio last_date
                    df = df[df["date"] >= last_date].reset_index(drop=True)
                    result[asset.id] = df
                except Exception as exc:
                    logger.warning("Error procesando batch (incr) para %s: %s", asset.ticker, exc)

    return result


def _process_yf_asset_worker(
    asset_id: int,
    ticker: str,
    df,
    last_date,
    _dd_cfg, _regime_cfg, _vol_cfg, _sr_cfg,
) -> tuple[bool, dict | None]:
    """Procesa un activo Yahoo Finance en su propio thread: escribe precios y calcula snapshot."""
    s = get_session()
    try:
        if df.empty:
            raise ValueError(
                f"No se encontraron datos de precio para '{ticker}'. "
                "Verificá que el ticker sea válido en Yahoo Finance."
            )
        if last_date is not None:
            _delete_from_date(asset_id, last_date, s)
        count = _upsert_prices(asset_id, df, s)
        _save_update_log(asset_id, success=True, error=None, session=s)
        s.commit()
        logger.info("Activo %s: %d filas importadas (batch)", ticker, count)
        try:
            compute_and_save_snapshot(
                asset_id,
                _dd_cfg=_dd_cfg, _regime_cfg=_regime_cfg,
                _vol_cfg=_vol_cfg, _sr_cfg=_sr_cfg,
                quick=True,
            )
        except Exception as snap_exc:
            logger.warning("Error snapshot %s: %s", ticker, snap_exc)
        return True, None
    except Exception as exc:
        s.rollback()
        error_msg = str(exc)
        logger.error("Error actualizando precios de %s: %s", ticker, error_msg)
        _save_update_log(asset_id, success=False, error=error_msg, session=s)
        s.commit()
        return False, {"ticker": ticker, "error": error_msg}
    finally:
        _ScopedSession.remove()


def _process_other_asset_worker(
    asset_id: int,
    ticker: str,
    _dd_cfg, _regime_cfg, _vol_cfg, _sr_cfg,
) -> tuple[bool, dict | None]:
    """Procesa un activo no-YF (otra fuente o sintético) en su propio thread."""
    try:
        update_asset_prices(
            asset_id,
            _dd_cfg=_dd_cfg, _regime_cfg=_regime_cfg,
            _vol_cfg=_vol_cfg, _sr_cfg=_sr_cfg,
        )
        return True, None
    except Exception as exc:
        return False, {"ticker": ticker, "error": str(exc)}
    finally:
        _ScopedSession.remove()


def update_all_active_assets(progress_cb=None) -> dict:
    """
    Actualiza todos los activos activos. Primero los regulares, luego los sintéticos.
    Tolerante a fallos individuales. Devuelve un resumen con éxitos y errores.
    """
    from app.models import SyntheticFormula, PriceSource

    s = get_session()
    all_assets = s.query(Asset).all()

    # Fix N+1: un solo query para IDs sintéticos
    synthetic_ids = {r[0] for r in s.query(SyntheticFormula.asset_id).all()}
    regular   = [a for a in all_assets if a.id not in synthetic_ids]
    synthetic = [a for a in all_assets if a.id in synthetic_ids]
    total     = len(all_assets)
    summary   = {"total": total, "success": 0, "errors": []}

    # Pre-cargar configs de snapshot una sola vez (evita N × 4 queries)
    _dd_cfg     = _get_drawdown_config()
    _regime_cfg = _get_regime_config()
    _vol_cfg    = _get_volatility_config()
    _sr_cfg     = sr_service._get_sr_config()

    # Separar activos Yahoo Finance para batch download
    yf_src = s.query(PriceSource).filter(PriceSource.name == "Yahoo Finance").first()
    yf_src_id = yf_src.id if yf_src else None

    yf_assets   = [a for a in regular if yf_src_id and a.price_source_id == yf_src_id]
    other_regular = [a for a in regular if not (yf_src_id and a.price_source_id == yf_src_id)]

    # Prefetch de last_dates en una sola query GROUP BY
    yf_ids = [a.id for a in yf_assets]
    if yf_ids:
        _max_dates = {
            r[0]: r[1]
            for r in s.query(Price.asset_id, func.max(Price.date))
                      .filter(Price.asset_id.in_(yf_ids))
                      .group_by(Price.asset_id)
                      .all()
        }
    else:
        _max_dates = {}
    yf_last_dates = {a.id: _max_dates.get(a.id) for a in yf_assets}

    prefetched = _bulk_prefetch_yfinance(
        [(a, yf_last_dates[a.id]) for a in yf_assets]
    )

    # Colectar (id, ticker) antes del loop: los commits expiran los objetos ORM
    # y acceder a sus atributos después podría fallar si fueron eliminados en otro thread.
    yf_pairs        = [(a.id, a.ticker) for a in yf_assets]
    other_pairs     = [(a.id, a.ticker) for a in other_regular + synthetic]

    cfgs = dict(
        _dd_cfg=_dd_cfg, _regime_cfg=_regime_cfg,
        _vol_cfg=_vol_cfg, _sr_cfg=_sr_cfg,
    )

    futures: dict = {}
    with ThreadPoolExecutor(max_workers=_UPDATE_WORKERS) as pool:
        for asset_id, asset_ticker in yf_pairs:
            if asset_id in prefetched:
                futures[pool.submit(
                    _process_yf_asset_worker,
                    asset_id, asset_ticker, prefetched[asset_id], yf_last_dates[asset_id],
                    **cfgs,
                )] = asset_ticker
            else:
                futures[pool.submit(
                    _process_other_asset_worker, asset_id, asset_ticker, **cfgs,
                )] = asset_ticker

        for asset_id, asset_ticker in other_pairs:
            futures[pool.submit(
                _process_other_asset_worker, asset_id, asset_ticker, **cfgs,
            )] = asset_ticker

        done = 0
        for future in as_completed(futures):
            done += 1
            if progress_cb:
                progress_cb(done, total)
            ok, err = future.result()
            if ok:
                summary["success"] += 1
            elif err:
                summary["errors"].append(err)

    logger.info(
        "Actualización completa: %d/%d exitosos, %d errores",
        summary["success"],
        summary["total"],
        len(summary["errors"]),
    )
    return summary


def clear_prices(asset_id: int) -> None:
    """Borra toda la historia de precios de un activo."""
    s = get_session()
    s.query(Price).filter(Price.asset_id == asset_id).delete()
    s.commit()
    logger.info("Historia de precios borrada para activo id=%d", asset_id)


def get_prices_df(asset_id: int):
    """Devuelve todos los precios del activo como DataFrame ordenado por fecha."""
    s = get_session()
    rows = (
        s.query(Price.date, Price.open, Price.high, Price.low, Price.close, Price.volume)
        .filter(Price.asset_id == asset_id)
        .order_by(Price.date)
        .all()
    )
    if not rows:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    return pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])


def get_update_logs() -> list[PriceUpdateLog]:
    s = get_session()
    return (
        s.query(PriceUpdateLog)
        .join(Asset)
        .order_by(Asset.ticker)
        .all()
    )


def get_all_assets_with_log() -> list[dict]:
    """Devuelve todos los activos activos con su último log de actualización (si existe)."""
    s = get_session()
    assets = s.query(Asset).order_by(Asset.ticker).all()
    logs = {log.asset_id: log for log in s.query(PriceUpdateLog).all()}
    result = []
    for asset in assets:
        log = logs.get(asset.id)
        result.append({
            "ticker": asset.ticker,
            "asset_name": asset.name,
            "last_attempt_at": str(log.last_attempt_at)[:19] if log else "—",
            "result": ("Éxito" if log.success else "Error") if log else "—",
            "error_detail": (log.error_detail or "") if log else "",
        })
    return result


def clear_update_logs() -> None:
    s = get_session()
    s.query(PriceUpdateLog).delete()
    s.commit()


def get_latest_prices_all() -> list[dict]:
    """Devuelve el precio de cierre más reciente de cada activo activo."""
    s = get_session()
    from sqlalchemy import func
    subq = (
        s.query(Price.asset_id, func.max(Price.date).label("max_date"))
        .group_by(Price.asset_id)
        .subquery()
    )
    rows = (
        s.query(Price, Asset)
        .join(subq, (Price.asset_id == subq.c.asset_id) & (Price.date == subq.c.max_date))
        .join(Asset, Price.asset_id == Asset.id)
        .order_by(Asset.ticker)
        .all()
    )
    return [
        {
            "ticker": asset.ticker,
            "name": asset.name,
            "date": str(price.date),
            "close": price.close,
            "volume": price.volume,
        }
        for price, asset in rows
    ]
