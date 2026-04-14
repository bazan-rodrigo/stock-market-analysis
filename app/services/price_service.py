"""
Servicio de descarga y actualización de precios históricos.
Lógica principal:
  - Si el activo no tiene precios: descarga toda la historia.
  - Si ya tiene precios: borra el último día y descarga desde ese día inclusive.
"""
import logging
from datetime import datetime

from sqlalchemy import func

from app.database import get_session
from app.models import Asset, Price, PriceUpdateLog
from app.services.screener_service import compute_and_save_snapshot
from app.sources.registry import get_source

logger = logging.getLogger(__name__)


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
    ).delete(synchronize_session="fetch")


def _upsert_prices(asset_id: int, df, session) -> int:
    """Inserta filas del DataFrame en la tabla de precios. Devuelve cantidad insertada."""
    if df.empty:
        return 0
    count = 0
    for row in df.itertuples(index=False):
        price = Price(
            asset_id=asset_id,
            date=row.date,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=int(row.volume) if row.volume is not None else None,
        )
        session.add(price)
        count += 1
    return count


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


def update_asset_prices(asset_id: int) -> None:
    """
    Actualiza los precios de un activo.
    Si falla, registra el error en price_update_log y relanza la excepción.
    """
    s = get_session()
    asset = s.get(Asset, asset_id)
    if asset is None:
        raise ValueError(f"Activo id={asset_id} no encontrado")

    source = get_source(asset.price_source.name)
    last_date = _get_last_price_date(asset_id, s)

    try:
        if last_date is None:
            df = source.download_history(asset.ticker)
        else:
            _delete_from_date(asset_id, last_date, s)
            df = source.download_history(asset.ticker, start=last_date)

        count = _upsert_prices(asset_id, df, s)
        _save_update_log(asset_id, success=True, error=None, session=s)
        s.commit()
        logger.info("Activo %s: %d filas importadas", asset.ticker, count)

        # Recalcular snapshot del screener
        try:
            compute_and_save_snapshot(asset_id)
        except Exception as snap_exc:
            logger.warning(
                "Error calculando snapshot screener para %s: %s", asset.ticker, snap_exc
            )

    except Exception as exc:
        s.rollback()
        error_msg = str(exc)
        logger.error("Error actualizando precios de %s: %s", asset.ticker, error_msg)
        _save_update_log(asset_id, success=False, error=error_msg, session=s)
        s.commit()
        raise


def update_all_active_assets() -> dict:
    """
    Actualiza todos los activos activos. Tolerante a fallos individuales.
    Devuelve un resumen con éxitos y errores.
    """
    s = get_session()
    assets = s.query(Asset).filter(Asset.active == True).all()
    summary = {"total": len(assets), "success": 0, "errors": []}

    for asset in assets:
        try:
            update_asset_prices(asset.id)
            summary["success"] += 1
        except Exception as exc:
            summary["errors"].append({"ticker": asset.ticker, "error": str(exc)})

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
    import pandas as pd

    s = get_session()
    rows = (
        s.query(Price)
        .filter(Price.asset_id == asset_id)
        .order_by(Price.date)
        .all()
    )
    if not rows:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    return pd.DataFrame(
        [
            {
                "date": r.date,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
            }
            for r in rows
        ]
    )


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
    assets = s.query(Asset).filter(Asset.active == True).order_by(Asset.ticker).all()
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
        .filter(Asset.active == True)
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
