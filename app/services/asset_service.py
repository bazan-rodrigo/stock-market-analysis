"""
Servicio CRUD para activos financieros.
Incluye autocompletado desde la fuente de precios y validación de tickers.
"""
import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.database import get_session
from app.models import Asset, PriceSource, SyntheticComponent, SyntheticFormula
from app.services import db_compat
from app.sources.registry import get_source

logger = logging.getLogger(__name__)

# Tablas de alto volumen con columna asset_id que se borran por lotes ANTES de
# eliminar el activo, para no retener locks en una transacción de cascada
# gigante (contención con backfills concurrentes → lock wait timeout). El resto
# de las tablas hijas (logs, flags, synthetic_formula...) las limpia el
# ON DELETE CASCADE de la BD al borrar la fila de `assets`.
_HIGH_VOLUME_ASSET_TABLES = (
    "current_indicator_values", "fundamental_quarterly", "prices",
)
_DELETE_BATCH = 5000


def _bloquear_si_es_componente(s, ids: list[int]) -> None:
    """ValueError si algún id es componente de un sintético fuera del lote.

    El mensaje agrupa por componente y nombra los sintéticos que lo usan, igual
    que el chequeo de benchmark de delete_asset: el usuario sabe exactamente
    qué eliminar (o de qué fórmula quitarlo) antes de reintentar."""
    from sqlalchemy.orm import aliased
    comp, owner = aliased(Asset), aliased(Asset)
    filas = (
        s.query(comp.ticker, owner.ticker)
         .select_from(SyntheticComponent)
         .join(SyntheticFormula,
               SyntheticComponent.formula_id == SyntheticFormula.id)
         .join(owner, SyntheticFormula.asset_id == owner.id)
         .join(comp, SyntheticComponent.asset_id == comp.id)
         .filter(SyntheticComponent.asset_id.in_(ids),
                 ~SyntheticFormula.asset_id.in_(ids))
         .distinct()
         .all()
    )
    if not filas:
        return
    por_componente: dict[str, set[str]] = {}
    for comp_ticker, owner_ticker in filas:
        por_componente.setdefault(comp_ticker, set()).add(owner_ticker)
    detalle = "; ".join(
        f"'{c}' es componente de {', '.join(sorted(usos))}"
        for c, usos in sorted(por_componente.items())
    )
    raise ValueError(
        "No se puede eliminar: " + detalle +
        ". Eliminá esos sintéticos (o quitá el componente de la fórmula) "
        "antes de borrar."
    )


def purge_assets(s, asset_ids, progress_cb=None) -> int:
    """Borra los activos indicados y TODA su historia. Devuelve cuántos ids se
    pidieron borrar.

    En MySQL/MariaDB: SQL crudo por lotes — DELETE por tabla de alto volumen con
    `asset_id IN (...) LIMIT`, commit por lote (locks acotados), y al final un
    `DELETE FROM assets WHERE id IN (...)` que deja el resto al ON DELETE CASCADE.
    NO usa `s.delete()` del ORM a propósito: con commits intermedios que expiran
    los objetos, el ORM dispara un lazy-load de cascada frágil y lento, y tira
    ObjectDeletedError si otra transacción ya borró la fila. Acepta un conjunto
    de ids para borrar muchos sintéticos de una (round-trips = tablas × lotes,
    no activos × tablas × lotes).

    progress_cb(tablas_hechas, tablas_total, tabla_actual): opcional, para que
    la UI muestre avance (borrar muchos activos puede tardar minutos)."""
    ids = [int(a) for a in asset_ids]
    if not ids:
        return 0

    # Guardia previa a cualquier DELETE: si un id del lote es componente de un
    # sintético que NO está en el lote, la FK RESTRICT de synthetic_component
    # rechazaría recién el DELETE final de assets — con la historia del activo
    # ya borrada y commiteada por lotes (quedaría vivo pero sin señales, y esa
    # historia solo vuelve con un recálculo completo). Cortar acá, antes de
    # tocar nada. Borrar el componente JUNTO con su sintético en el mismo lote
    # sí está permitido.
    _bloquear_si_es_componente(s, ids)

    if db_compat.is_mysql(s):
        # ids validados a int → seguro interpolarlos (IN con N valores); LIMIT
        # inline porque algunos drivers no aceptan placeholder ahí
        id_list = ", ".join(str(i) for i in ids)
        # ind_{code}/ind_fundamental_{code}/ind_asset_meta: dinámicas por
        # indicador (ver get_ind_table); sig_{id}/strat_res_{id}: dinámicas
        # por señal/estrategia (ver signal_store). Descubiertas desde
        # information_schema.
        dyn = [r[0] for r in s.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND (table_name LIKE 'ind\\_%' "
            "OR table_name LIKE 'sig\\_%' "
            "OR table_name LIKE 'strat\\_res\\_%')")).all()]
        tables = (*_HIGH_VOLUME_ASSET_TABLES, *dyn)
        total  = len(tables) + 1  # +1: el DELETE final de assets (cascade)
        for i, tbl in enumerate(tables):
            if progress_cb:
                progress_cb(i, total, tbl)
            while True:
                res = s.execute(text(
                    f"DELETE FROM `{tbl}` WHERE asset_id IN ({id_list}) "
                    f"LIMIT {_DELETE_BATCH}"))
                s.commit()
                if res.rowcount < _DELETE_BATCH:
                    break
        if progress_cb:
            progress_cb(len(tables), total, "assets")
        s.execute(text(f"DELETE FROM assets WHERE id IN ({id_list})"))
        s.commit()
        if progress_cb:
            progress_cb(total, total, "")
    elif db_compat.is_postgres(s):
        # PostgreSQL: mismas tablas que la rama MySQL (las dinámicas NO
        # tienen FK a assets — sin esta limpieza explícita quedarían filas
        # huérfanas). Sin LIMIT (no existe en DELETE de PG) y sin lotes: en
        # MVCC un DELETE por tabla no bloquea lectores, y el commit por
        # tabla acota la transacción igual que los lotes en InnoDB.
        id_list = ", ".join(str(i) for i in ids)
        dyn = db_compat.list_tables_by_prefix(s, "ind_", "sig_", "strat_res_")
        tables = (*_HIGH_VOLUME_ASSET_TABLES, *dyn)
        total  = len(tables) + 1
        for i, tbl in enumerate(tables):
            if progress_cb:
                progress_cb(i, total, tbl)
            s.execute(text(
                f"DELETE FROM {db_compat.quote_ident(s, tbl)} "
                f"WHERE asset_id IN ({id_list})"))
            s.commit()
        if progress_cb:
            progress_cb(len(tables), total, "assets")
        s.execute(text(f"DELETE FROM assets WHERE id IN ({id_list})"))
        s.commit()
        if progress_cb:
            progress_cb(total, total, "")
    else:
        # sqlite (tests): borrado en bloque, sin cascade lazy-load del ORM
        s.query(Asset).filter(Asset.id.in_(ids)).delete(synchronize_session=False)
        s.commit()
    return len(ids)


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

    purge_assets(s, [asset_id])


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
