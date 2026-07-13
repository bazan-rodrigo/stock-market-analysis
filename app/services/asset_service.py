"""
Servicio CRUD para activos financieros.
Incluye autocompletado desde la fuente de precios y validación de tickers.
"""
import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.database import get_session
from app.models import Asset, PriceSource
from app.sources.registry import get_source

logger = logging.getLogger(__name__)

# Tablas de alto volumen con columna asset_id que se borran por lotes ANTES de
# eliminar el activo, para no retener locks en una transacción de cascada
# gigante (contención con backfills concurrentes → lock wait timeout). El resto
# de las tablas hijas (logs, flags) las limpia el ON DELETE CASCADE al final.
_HIGH_VOLUME_ASSET_TABLES = (
    "signal_value", "strategy_result", "current_indicator_values",
    "fundamental_quarterly", "prices",
)
_DELETE_BATCH = 5000


def _purge_asset_high_volume(s, asset_id: int) -> None:
    """Borra por lotes (con commit por lote) las filas de alto volumen del
    activo. Solo en MySQL/MariaDB: sqlite (tests) no soporta DELETE ... LIMIT
    ni information_schema, y ahí el cascade simple del ORM alcanza."""
    if s.get_bind().dialect.name not in ("mysql", "mariadb"):
        return
    # ind_{code}/ind_fundamental_{code}/ind_asset_meta: dinámicas por indicador
    # (ver get_ind_table), descubiertas desde information_schema
    dyn = [r[0] for r in s.execute(text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_name LIKE 'ind\\_%'")).all()]
    for tbl in (*_HIGH_VOLUME_ASSET_TABLES, *dyn):
        while True:
            # _DELETE_BATCH inline (no como parámetro): algunos drivers MySQL
            # no aceptan placeholder en LIMIT. Es una constante, no hay inyección.
            res = s.execute(
                text(f"DELETE FROM `{tbl}` WHERE asset_id = :aid LIMIT {_DELETE_BATCH}"),
                {"aid": asset_id})
            s.commit()
            if res.rowcount < _DELETE_BATCH:
                break


def get_assets() -> list[Asset]:
    s = get_session()
    return s.query(Asset).order_by(Asset.ticker).all()


def get_asset_by_id(asset_id: int) -> Asset:
    s = get_session()
    obj = s.get(Asset, asset_id)
    if obj is None:
        raise ValueError(f"Activo id={asset_id} no encontrado")
    return obj


def get_asset_by_ticker(ticker: str) -> Optional[Asset]:
    s = get_session()
    return s.query(Asset).filter(Asset.ticker == ticker.upper()).first()


def create_asset(
    ticker: str,
    price_source_id: int,
    name: Optional[str] = None,
    country_id: Optional[int] = None,
    market_id: Optional[int] = None,
    instrument_type_id: Optional[int] = None,
    currency_id: Optional[int] = None,
    sector_id: Optional[int] = None,
    industry_id: Optional[int] = None,
    benchmark_id: Optional[int] = None,
    fundamental_source_id: Optional[int] = None,
) -> Asset:
    s = get_session()
    obj = Asset(
        ticker=ticker.strip().upper(),
        name=name.strip() if name else ticker.strip().upper(),
        country_id=country_id,
        market_id=market_id,
        instrument_type_id=instrument_type_id,
        currency_id=currency_id,
        price_source_id=price_source_id,
        sector_id=sector_id,
        industry_id=industry_id,
        benchmark_id=benchmark_id,
        fundamental_source_id=fundamental_source_id,
    )
    s.add(obj)
    try:
        s.commit()
    except IntegrityError as exc:
        s.rollback()
        raise ValueError(f"El ticker '{ticker.upper()}' ya existe") from exc
    s.refresh(obj)
    return obj


def update_asset(
    asset_id: int,
    ticker: str,
    price_source_id: int,
    name: Optional[str] = None,
    country_id: Optional[int] = None,
    market_id: Optional[int] = None,
    instrument_type_id: Optional[int] = None,
    currency_id: Optional[int] = None,
    sector_id: Optional[int] = None,
    industry_id: Optional[int] = None,
    benchmark_id: Optional[int] = None,
    fundamental_source_id: Optional[int] = None,
) -> Asset:
    s = get_session()
    obj = s.get(Asset, asset_id)
    if obj is None:
        raise ValueError(f"Activo id={asset_id} no encontrado")
    obj.ticker = ticker.strip().upper()
    obj.name = name.strip() if name else obj.name
    obj.country_id = country_id
    obj.market_id = market_id
    obj.instrument_type_id = instrument_type_id
    obj.currency_id = currency_id
    obj.price_source_id = price_source_id
    obj.sector_id = sector_id
    obj.industry_id = industry_id
    obj.benchmark_id = benchmark_id
    obj.fundamental_source_id = fundamental_source_id
    try:
        s.commit()
    except IntegrityError as exc:
        s.rollback()
        raise ValueError(f"El ticker '{ticker.upper()}' ya existe") from exc
    s.refresh(obj)
    return obj


def delete_asset(asset_id: int) -> None:
    """Borra el activo y toda su historia de precios (cascade en BD)."""
    from app.models import Market
    s = get_session()
    obj = s.get(Asset, asset_id)
    if obj is None:
        raise ValueError(f"Activo id={asset_id} no encontrado")

    # Verificar que no sea benchmark de otros activos o mercados
    assets_using = (
        s.query(Asset.ticker)
         .filter(Asset.benchmark_id == asset_id, Asset.id != asset_id)
         .all()
    )
    markets_using = (
        s.query(Market.name)
         .filter(Market.benchmark_id == asset_id)
         .all()
    )
    dependents = []
    if assets_using:
        dependents.append("activos: " + ", ".join(r.ticker for r in assets_using))
    if markets_using:
        dependents.append("mercados: " + ", ".join(r.name for r in markets_using))
    if dependents:
        raise ValueError(
            f"No se puede eliminar: '{obj.ticker}' está configurado como benchmark en "
            + " y ".join(dependents) + ". Reasigná el benchmark antes de borrar."
        )

    _purge_asset_high_volume(s, asset_id)
    s.delete(obj)
    s.commit()


def bulk_update_assets(asset_ids: list[int], field: str, value) -> int:
    """Actualiza un campo específico en múltiples activos. Retorna cantidad actualizada."""
    _ALLOWED = {"benchmark_id", "market_id", "country_id", "instrument_type_id", "currency_id", "sector_id", "industry_id", "fundamental_source_id"}
    if field not in _ALLOWED:
        raise ValueError(f"Campo '{field}' no permitido para edición masiva.")
    s = get_session()
    assets = s.query(Asset).filter(Asset.id.in_(asset_ids)).all()
    for a in assets:
        setattr(a, field, value)
    s.commit()
    return len(assets)


def autocomplete_from_source(ticker: str, price_source_id: int) -> dict:
    """
    Consulta la fuente de precios y devuelve los metadatos disponibles
    para pre-rellenar el formulario. No guarda nada en la BD.
    """
    s = get_session()
    source_obj = s.get(PriceSource, price_source_id)
    if source_obj is None:
        raise ValueError("Fuente de precios no encontrada")

    source = get_source(source_obj.name)
    result = source.validate_ticker(ticker.strip().upper())

    if not result.valid:
        raise ValueError(result.error or "Ticker inválido")

    meta = result.metadata or {}
    return {
        "name": getattr(meta, "name", None),
        "sector": getattr(meta, "sector", None),
        "industry": getattr(meta, "industry", None),
        "currency_iso": getattr(meta, "currency_iso", None),
        "exchange": getattr(meta, "exchange", None),
        "exchange_name": getattr(meta, "exchange_name", None),
        "country": getattr(meta, "country", None),
        "quote_type": getattr(meta, "quote_type", None),
    }
