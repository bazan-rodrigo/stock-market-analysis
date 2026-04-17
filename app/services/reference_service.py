"""
Servicio CRUD para todas las tablas de referencia.
Cada función de borrado valida referencias antes de ejecutar.
"""
import logging
from typing import Any, Type

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import (
    CatalogAlias,
    Country,
    Currency,
    Industry,
    InstrumentType,
    Market,
    PriceSource,
    Sector,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers genéricos
# ---------------------------------------------------------------------------

def _get_all(model: Type, session: Session) -> list:
    return session.query(model).order_by(model.id).all()


def _get_by_id(model: Type, entity_id: int, session: Session):
    obj = session.get(model, entity_id)
    if obj is None:
        raise ValueError(f"{model.__name__} id={entity_id} no encontrado")
    return obj


def _delete_with_fk_check(obj, session: Session) -> None:
    try:
        session.delete(obj)
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise ValueError(
            f"No se puede eliminar: está referenciado por otros registros. "
            f"Detalle: {exc.orig}"
        ) from exc


# ---------------------------------------------------------------------------
# Países
# ---------------------------------------------------------------------------

def get_countries() -> list[Country]:
    s = get_session()
    return _get_all(Country, s)


def create_country(name: str, iso_code: str) -> Country:
    s = get_session()
    obj = Country(name=name.strip(), iso_code=iso_code.strip().upper())
    s.add(obj)
    s.commit()
    s.refresh(obj)
    return obj


def update_country(country_id: int, name: str, iso_code: str) -> Country:
    s = get_session()
    obj = _get_by_id(Country, country_id, s)
    obj.name = name.strip()
    obj.iso_code = iso_code.strip().upper()
    s.commit()
    s.refresh(obj)
    return obj


def delete_country(country_id: int) -> None:
    s = get_session()
    obj = _get_by_id(Country, country_id, s)
    _delete_with_fk_check(obj, s)
    s.commit()


# ---------------------------------------------------------------------------
# Monedas
# ---------------------------------------------------------------------------

def get_currencies() -> list[Currency]:
    return _get_all(Currency, get_session())


def create_currency(name: str, iso_code: str) -> Currency:
    s = get_session()
    obj = Currency(name=name.strip(), iso_code=iso_code.strip().upper())
    s.add(obj)
    s.commit()
    s.refresh(obj)
    return obj


def update_currency(currency_id: int, name: str, iso_code: str) -> Currency:
    s = get_session()
    obj = _get_by_id(Currency, currency_id, s)
    obj.name = name.strip()
    obj.iso_code = iso_code.strip().upper()
    s.commit()
    s.refresh(obj)
    return obj


def delete_currency(currency_id: int) -> None:
    s = get_session()
    obj = _get_by_id(Currency, currency_id, s)
    _delete_with_fk_check(obj, s)
    s.commit()


# ---------------------------------------------------------------------------
# Mercados
# ---------------------------------------------------------------------------

def get_markets() -> list[Market]:
    return _get_all(Market, get_session())


def create_market(name: str, country_id: int) -> Market:
    s = get_session()
    obj = Market(name=name.strip(), country_id=country_id)
    s.add(obj)
    s.commit()
    s.refresh(obj)
    return obj


def update_market(market_id: int, name: str, country_id: int) -> Market:
    s = get_session()
    obj = _get_by_id(Market, market_id, s)
    obj.name = name.strip()
    obj.country_id = country_id
    s.commit()
    s.refresh(obj)
    return obj


def delete_market(market_id: int) -> None:
    s = get_session()
    obj = _get_by_id(Market, market_id, s)
    _delete_with_fk_check(obj, s)
    s.commit()


# ---------------------------------------------------------------------------
# Tipos de instrumento
# ---------------------------------------------------------------------------

def get_instrument_types() -> list[InstrumentType]:
    return _get_all(InstrumentType, get_session())


def create_instrument_type(name: str, default_currency_id: int) -> InstrumentType:
    s = get_session()
    obj = InstrumentType(name=name.strip(), default_currency_id=default_currency_id)
    s.add(obj)
    s.commit()
    s.refresh(obj)
    return obj


def update_instrument_type(
    itype_id: int, name: str, default_currency_id: int
) -> InstrumentType:
    s = get_session()
    obj = _get_by_id(InstrumentType, itype_id, s)
    obj.name = name.strip()
    obj.default_currency_id = default_currency_id
    s.commit()
    s.refresh(obj)
    return obj


def delete_instrument_type(itype_id: int) -> None:
    s = get_session()
    obj = _get_by_id(InstrumentType, itype_id, s)
    _delete_with_fk_check(obj, s)
    s.commit()


# ---------------------------------------------------------------------------
# Sectores
# ---------------------------------------------------------------------------

def get_sectors() -> list[Sector]:
    return _get_all(Sector, get_session())


def create_sector(name: str) -> Sector:
    s = get_session()
    obj = Sector(name=name.strip())
    s.add(obj)
    s.commit()
    s.refresh(obj)
    return obj


def update_sector(sector_id: int, name: str) -> Sector:
    s = get_session()
    obj = _get_by_id(Sector, sector_id, s)
    obj.name = name.strip()
    s.commit()
    s.refresh(obj)
    return obj


def delete_sector(sector_id: int) -> None:
    s = get_session()
    obj = _get_by_id(Sector, sector_id, s)
    _delete_with_fk_check(obj, s)
    s.commit()


# ---------------------------------------------------------------------------
# Industrias
# ---------------------------------------------------------------------------

def get_industries() -> list[Industry]:
    return _get_all(Industry, get_session())


def create_industry(name: str, sector_id: int = None) -> Industry:
    s = get_session()
    obj = Industry(name=name.strip(), sector_id=sector_id)
    s.add(obj)
    s.commit()
    s.refresh(obj)
    return obj


def update_industry(industry_id: int, name: str, sector_id: int) -> Industry:
    s = get_session()
    obj = _get_by_id(Industry, industry_id, s)
    obj.name = name.strip()
    obj.sector_id = sector_id
    s.commit()
    s.refresh(obj)
    return obj


def delete_industry(industry_id: int) -> None:
    s = get_session()
    obj = _get_by_id(Industry, industry_id, s)
    _delete_with_fk_check(obj, s)
    s.commit()


# ---------------------------------------------------------------------------
# Fuentes de precios
# ---------------------------------------------------------------------------

def get_price_sources(only_active: bool = False) -> list[PriceSource]:
    s = get_session()
    q = s.query(PriceSource)
    if only_active:
        q = q.filter(PriceSource.active == True)
    return q.order_by(PriceSource.id).all()


def create_price_source(name: str, description: str, active: bool) -> PriceSource:
    s = get_session()
    obj = PriceSource(name=name.strip(), description=description, active=active)
    s.add(obj)
    s.commit()
    s.refresh(obj)
    return obj


def update_price_source(
    source_id: int, name: str, description: str, active: bool
) -> PriceSource:
    s = get_session()
    obj = _get_by_id(PriceSource, source_id, s)
    obj.name = name.strip()
    obj.description = description
    obj.active = active
    s.commit()
    s.refresh(obj)
    return obj


def delete_price_source(source_id: int) -> None:
    s = get_session()
    obj = _get_by_id(PriceSource, source_id, s)
    _delete_with_fk_check(obj, s)
    s.commit()


# ---------------------------------------------------------------------------
# Usuarios (gestión básica para el panel admin)
# ---------------------------------------------------------------------------

from app.models import User


def get_users() -> list[User]:
    return _get_all(User, get_session())


def create_user(username: str, password: str, role: str) -> User:
    s = get_session()
    obj = User(username=username.strip(), role=role)
    obj.set_password(password)
    s.add(obj)
    s.commit()
    s.refresh(obj)
    return obj


def update_user(
    user_id: int,
    username: str,
    role: str,
    active: bool,
    password: str | None = None,
) -> User:
    s = get_session()
    obj = _get_by_id(User, user_id, s)
    obj.username = username.strip()
    obj.role = role
    obj.active = active
    if password:
        obj.set_password(password)
    s.commit()
    s.refresh(obj)
    return obj


def delete_user(user_id: int) -> None:
    s = get_session()
    obj = _get_by_id(User, user_id, s)
    s.delete(obj)
    s.commit()


# ---------------------------------------------------------------------------
# Helpers get-or-create (usados por autocompletado)
# ---------------------------------------------------------------------------

def _get_or_create(Model, s, **filter_kwargs):
    """Busca un registro por los kwargs dados; lo crea si no existe."""
    obj = s.query(Model).filter_by(**filter_kwargs).first()
    if obj is None:
        obj = Model(**filter_kwargs)
        s.add(obj)
        s.commit()
        s.refresh(obj)
    return obj, obj not in s.identity_map.values()


def _upsert_alias(s, entity_type: str, source_value: str, entity_id: int) -> None:
    obj = s.query(CatalogAlias).filter_by(
        entity_type=entity_type, source_value=source_value
    ).first()
    if obj:
        obj.entity_id = entity_id
    else:
        s.add(CatalogAlias(entity_type=entity_type, source_value=source_value, entity_id=entity_id))


def _resolve_alias(s, entity_type: str, value: str, Model):
    alias = s.query(CatalogAlias).filter_by(entity_type=entity_type, source_value=value).first()
    if alias:
        entity = s.get(Model, alias.entity_id)
        if entity:
            return entity
    return None


def get_or_create_country(name: str) -> tuple:
    s = get_session()
    value = name.strip()
    entity = _resolve_alias(s, "country", value, Country)
    if entity:
        return entity, False
    existing = s.query(Country).filter(Country.name.ilike(value)).first()
    if existing:
        _upsert_alias(s, "country", value, existing.id)
        s.commit()
        return existing, False
    obj = Country(name=value, iso_code=None)
    s.add(obj)
    s.flush()
    _upsert_alias(s, "country", value, obj.id)
    s.commit()
    s.refresh(obj)
    return obj, True


def get_or_create_currency(iso_code: str) -> tuple:
    s = get_session()
    code = iso_code.strip().upper()
    existing = s.query(Currency).filter(Currency.iso_code == code).first()
    if existing:
        return existing, False
    obj = Currency(iso_code=code, name=code)
    s.add(obj)
    s.commit()
    s.refresh(obj)
    return obj, True


def get_or_create_market(name: str, country_id: int = None) -> tuple:
    s = get_session()
    value = name.strip()
    entity = _resolve_alias(s, "market", value, Market)
    if entity:
        return entity, False
    existing = s.query(Market).filter(Market.name.ilike(value)).first()
    if existing:
        _upsert_alias(s, "market", value, existing.id)
        s.commit()
        return existing, False
    obj = Market(name=value, country_id=country_id)
    s.add(obj)
    s.flush()
    _upsert_alias(s, "market", value, obj.id)
    s.commit()
    s.refresh(obj)
    return obj, True


def get_or_create_instrument_type(name: str) -> tuple:
    s = get_session()
    value = name.strip()
    entity = _resolve_alias(s, "instrument_type", value, InstrumentType)
    if entity:
        return entity, False
    existing = s.query(InstrumentType).filter(InstrumentType.name.ilike(value)).first()
    if existing:
        _upsert_alias(s, "instrument_type", value, existing.id)
        s.commit()
        return existing, False
    obj = InstrumentType(name=value)
    s.add(obj)
    s.flush()
    _upsert_alias(s, "instrument_type", value, obj.id)
    s.commit()
    s.refresh(obj)
    return obj, True


def get_or_create_sector(name: str) -> tuple:
    s = get_session()
    value = name.strip()
    entity = _resolve_alias(s, "sector", value, Sector)
    if entity:
        return entity, False
    existing = s.query(Sector).filter(Sector.name.ilike(value)).first()
    if existing:
        _upsert_alias(s, "sector", value, existing.id)
        s.commit()
        return existing, False
    obj = Sector(name=value)
    s.add(obj)
    s.flush()
    _upsert_alias(s, "sector", value, obj.id)
    s.commit()
    s.refresh(obj)
    return obj, True


def get_or_create_industry(name: str, sector_id: int = None) -> tuple:
    s = get_session()
    value = name.strip()
    entity = _resolve_alias(s, "industry", value, Industry)
    if entity:
        return entity, False
    existing = s.query(Industry).filter(Industry.name.ilike(value)).first()
    if existing:
        _upsert_alias(s, "industry", value, existing.id)
        s.commit()
        return existing, False
    obj = Industry(name=value, sector_id=sector_id)
    s.add(obj)
    s.flush()
    _upsert_alias(s, "industry", value, obj.id)
    s.commit()
    s.refresh(obj)
    return obj, True


# ---------------------------------------------------------------------------
# Catalog mapper — aliases y fusión de entidades
# ---------------------------------------------------------------------------

_ENTITY_MODELS = {
    "country":         Country,
    "market":          Market,
    "instrument_type": InstrumentType,
    "sector":          Sector,
    "industry":        Industry,
}


def get_catalog_entities_with_aliases(entity_type: str) -> tuple:
    s = get_session()
    Model = _ENTITY_MODELS[entity_type]
    entities = s.query(Model).order_by(Model.name).all()
    aliases = s.query(CatalogAlias).filter_by(entity_type=entity_type).all()
    return entities, aliases


def get_aliases(entity_type: str) -> list:
    return get_session().query(CatalogAlias).filter_by(entity_type=entity_type).all()


def delete_alias(alias_id: int) -> None:
    s = get_session()
    obj = s.get(CatalogAlias, alias_id)
    if obj:
        s.delete(obj)
        s.commit()


def merge_entities(entity_type: str, source_id: int, target_id: int) -> str:
    """
    Fusiona source en target: redirige todas las FK, crea alias con el nombre
    del source y elimina el source. Devuelve el nombre del source.
    """
    from app.models import Asset
    s = get_session()
    Model = _ENTITY_MODELS[entity_type]
    source = s.get(Model, source_id)
    target = s.get(Model, target_id)

    if source is None or target is None:
        raise ValueError("Entidad no encontrada")
    if source_id == target_id:
        raise ValueError("No podés fusionar una entidad consigo misma")

    source_name = source.name

    if entity_type == "country":
        s.query(Asset).filter(Asset.country_id == source_id).update({"country_id": target_id})
        s.query(Market).filter(Market.country_id == source_id).update({"country_id": target_id})
    elif entity_type == "market":
        s.query(Asset).filter(Asset.market_id == source_id).update({"market_id": target_id})
    elif entity_type == "instrument_type":
        s.query(Asset).filter(Asset.instrument_type_id == source_id).update({"instrument_type_id": target_id})
    elif entity_type == "sector":
        s.query(Asset).filter(Asset.sector_id == source_id).update({"sector_id": target_id})
        s.query(Industry).filter(Industry.sector_id == source_id).update({"sector_id": target_id})
    elif entity_type == "industry":
        s.query(Asset).filter(Asset.industry_id == source_id).update({"industry_id": target_id})

    _upsert_alias(s, entity_type, source_name, target_id)
    s.delete(source)
    s.commit()
    return source_name

