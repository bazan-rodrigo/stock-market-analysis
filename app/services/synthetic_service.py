"""
Servicio para activos sintéticos: precio = numerador / denominador por fecha.
OHLC: close = num.close/den.close; open = num.open/den.open (si disponible).
High y low se derivan de open y close (la intradiaria no es significativa en datos diarios).
"""
import logging

from sqlalchemy import func

from app.database import get_session
from app.models import Asset, Price, SyntheticAssetConfig
from app.services.screener_service import compute_and_save_snapshot

logger = logging.getLogger(__name__)


def get_all_configs() -> list[SyntheticAssetConfig]:
    s = get_session()
    return s.query(SyntheticAssetConfig).all()


def get_config(asset_id: int) -> SyntheticAssetConfig | None:
    s = get_session()
    return s.query(SyntheticAssetConfig).filter(
        SyntheticAssetConfig.asset_id == asset_id
    ).first()


def is_synthetic(asset_id: int) -> bool:
    return get_config(asset_id) is not None


def save_config(asset_id: int, numerator_id: int, denominator_id: int) -> SyntheticAssetConfig:
    s = get_session()
    cfg = s.query(SyntheticAssetConfig).filter(
        SyntheticAssetConfig.asset_id == asset_id
    ).first()
    if cfg is None:
        cfg = SyntheticAssetConfig(asset_id=asset_id)
        s.add(cfg)
    cfg.numerator_asset_id   = numerator_id
    cfg.denominator_asset_id = denominator_id
    s.commit()
    s.refresh(cfg)
    return cfg


def delete_config(config_id: int) -> None:
    s = get_session()
    cfg = s.query(SyntheticAssetConfig).filter(SyntheticAssetConfig.id == config_id).first()
    if cfg:
        s.delete(cfg)
        s.commit()


def compute_synthetic_prices(asset_id: int, full: bool = False) -> int:
    """
    Calcula y persiste precios del activo sintético.
    full=True → borra todo y recalcula desde el inicio.
    full=False → recalcula solo desde la última fecha registrada (delta).
    Retorna cantidad de filas insertadas.
    """
    s = get_session()
    cfg = get_config(asset_id)
    if cfg is None:
        raise ValueError(f"No hay configuración sintética para activo id={asset_id}")

    if full:
        s.query(Price).filter(Price.asset_id == asset_id).delete()
        s.commit()
        start_date = None
    else:
        last_date = s.query(func.max(Price.date)).filter(
            Price.asset_id == asset_id
        ).scalar()
        if last_date:
            # Re-calcular desde la última fecha (puede haber sido parcial)
            s.query(Price).filter(
                Price.asset_id == asset_id,
                Price.date >= last_date,
            ).delete()
            s.commit()
            start_date = last_date
        else:
            start_date = None

    num_q = s.query(Price).filter(Price.asset_id == cfg.numerator_asset_id)
    den_q = s.query(Price).filter(Price.asset_id == cfg.denominator_asset_id)
    if start_date:
        num_q = num_q.filter(Price.date >= start_date)
        den_q = den_q.filter(Price.date >= start_date)

    num_prices = {p.date: p for p in num_q.all()}
    den_prices = {p.date: p for p in den_q.all()}

    common_dates = sorted(set(num_prices.keys()) & set(den_prices.keys()))
    count = 0

    for d in common_dates:
        n = num_prices[d]
        den = den_prices[d]
        if not den.close:
            continue

        close = round(n.close / den.close, 8)
        open_ = round(n.open / den.open, 8) if n.open and den.open else close

        s.add(Price(
            asset_id=asset_id,
            date=d,
            open=open_,
            high=max(open_, close),
            low=min(open_, close),
            close=close,
            volume=None,
        ))
        count += 1

    s.commit()
    logger.info("Activo sintético id=%d: %d precios calculados (full=%s)", asset_id, count, full)

    try:
        compute_and_save_snapshot(asset_id)
    except Exception as exc:
        logger.warning("Error snapshot para activo sintético id=%d: %s", asset_id, exc)

    return count


def compute_all_synthetic(progress_cb=None) -> dict:
    """Recalcula (delta) todos los activos sintéticos configurados."""
    configs = get_all_configs()
    total   = len(configs)
    errors  = []

    for i, cfg in enumerate(configs):
        if progress_cb:
            progress_cb(i + 1, total)
        try:
            compute_synthetic_prices(cfg.asset_id, full=False)
        except Exception as exc:
            ticker = cfg.asset.ticker if cfg.asset else str(cfg.asset_id)
            logger.warning("Error calculando sintético %s: %s", ticker, exc)
            errors.append({"ticker": ticker, "error": str(exc)})

    return {"total": total, "errors": errors}


def get_assets_options_for_synthetic() -> list[dict]:
    """Activos con fuente Calculado (candidatos a ser sintéticos)."""
    s = get_session()
    from app.models import PriceSource
    source = s.query(PriceSource).filter(PriceSource.name == "Calculado").first()
    if source is None:
        return []
    assets = (
        s.query(Asset)
        .filter(Asset.price_source_id == source.id, Asset.active == True)
        .order_by(Asset.ticker)
        .all()
    )
    return [{"label": f"{a.ticker} — {a.name}", "value": a.id} for a in assets]


def get_all_assets_options() -> list[dict]:
    """Todos los activos activos (para seleccionar numerador/denominador)."""
    s = get_session()
    assets = s.query(Asset).filter(Asset.active == True).order_by(Asset.ticker).all()
    return [{"label": f"{a.ticker} — {a.name}", "value": a.id} for a in assets]
