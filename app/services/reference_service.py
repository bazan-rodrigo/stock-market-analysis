"""
Servicio CRUD para todas las tablas de referencia.
Cada función de borrado valida referencias antes de ejecutar.
"""
import logging
from typing import Type

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
    return session.query(model).order_by(model.name).all()


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


def create_currency(name: str, iso_code: str = None) -> Currency:
    s = get_session()
    obj = Currency(name=name.strip(), iso_code=iso_code.strip().upper() if iso_code else None)
    s.add(obj)
    s.commit()
    s.refresh(obj)
    return obj


def update_currency(currency_id: int, name: str, iso_code: str = None) -> Currency:
    s = get_session()
    obj = _get_by_id(Currency, currency_id, s)
    obj.name = name.strip()
    obj.iso_code = iso_code.strip().upper() if iso_code else None
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


def create_market(name: str, country_id: int, benchmark_id: int | None = None) -> Market:
    s = get_session()
    obj = Market(name=name.strip(), country_id=country_id, benchmark_id=benchmark_id)
    s.add(obj)
    s.commit()
    s.refresh(obj)
    return obj


def update_market(market_id: int, name: str, country_id: int, benchmark_id: int | None = None) -> Market:
    s = get_session()
    obj = _get_by_id(Market, market_id, s)
    obj.name = name.strip()
    obj.country_id = country_id
    obj.benchmark_id = benchmark_id
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

def get_price_sources() -> list[PriceSource]:
    s = get_session()
    return s.query(PriceSource).order_by(PriceSource.name).all()


def create_price_source(name: str, description: str) -> PriceSource:
    s = get_session()
    obj = PriceSource(name=name.strip(), description=description)
    s.add(obj)
    s.commit()
    s.refresh(obj)
    return obj


def update_price_source(source_id: int, name: str, description: str) -> PriceSource:
    s = get_session()
    obj = _get_by_id(PriceSource, source_id, s)
    obj.name = name.strip()
    obj.description = description
    s.commit()
    s.refresh(obj)
    return obj


_PROTECTED_SOURCES = {"Yahoo Finance", "Calculado"}


def delete_price_source(source_id: int) -> None:
    s = get_session()
    obj = _get_by_id(PriceSource, source_id, s)
    if obj.name in _PROTECTED_SOURCES:
        raise ValueError(f"La fuente '{obj.name}' es de sistema y no puede eliminarse.")
    _delete_with_fk_check(obj, s)
    s.commit()


# ---------------------------------------------------------------------------
# Usuarios (gestión básica para el panel admin)
# ---------------------------------------------------------------------------

from app.models import User


def get_users() -> list[User]:
    # No usa _get_all: User no tiene columna `name`; se ordena por username
    return get_session().query(User).order_by(User.username).all()


# Guardia del último administrador: sin el modo invitado (eliminado jul-2026)
# no existe puerta de atrás — si el sistema se queda sin ningún admin activo,
# nadie puede volver a administrar desde la aplicación.

_ULTIMO_ADMIN_MSG = (
    "Es el último administrador activo: el sistema quedaría sin ninguna "
    "cuenta que pueda administrar. Antes activá o promové a otro "
    "administrador."
)


def deja_sin_admins(era_admin_activo: bool, queda_admin_activo: bool,
                    otros_admins_activos: int) -> bool:
    """True si la operación dejaría el sistema sin ningún admin activo.

    Lógica pura (testeable sin BD). Solo bloquea cuando el afectado ES hoy un
    admin activo y dejaría de serlo: tocar analistas o admins inactivos nunca
    se bloquea, aunque la instalación ya esté (mal) sin admins activos — esa
    situación no la creó esta operación y bloquear no la arregla.
    """
    return era_admin_activo and not queda_admin_activo \
        and otros_admins_activos == 0


def _otros_admins_activos(s, user_id: int) -> int:
    return (s.query(User)
            .filter(User.role == "admin", User.active.is_(True),
                    User.id != user_id)
            .count())


_USERNAME_DUPLICADO_MSG = (
    "Ya existe un usuario con ese nombre. Los nombres de usuario no "
    "distinguen mayúsculas de minúsculas: no puede haber 'Ana' y 'ana' "
    "al mismo tiempo."
)


def _username_ocupado(s, username: str, excluir_id: int | None = None) -> bool:
    """True si ya hay un usuario con ese nombre, SIN distinguir mayúsculas.

    El login resuelve el usuario con ci_equals (contrato heredado de la
    collation case-insensitive de MySQL), así que dos cuentas que difieren
    solo en el caso son indistinguibles al entrar. El `unique=True` de la
    columna no alcanza para impedirlas: en PostgreSQL '=' distingue caso y
    las deja convivir. Validar acá evita crear el par; la migración 0088
    (índice único sobre LOWER(username)) lo hará imposible.
    """
    from app.services.db_compat import ci_equals
    q = s.query(User.id).filter(ci_equals(User.username, username))
    if excluir_id is not None:
        q = q.filter(User.id != excluir_id)
    return q.first() is not None


def create_user(username: str, password: str, role: str) -> User:
    s = get_session()
    username = username.strip()
    if _username_ocupado(s, username):
        raise ValueError(_USERNAME_DUPLICADO_MSG)
    obj = User(username=username, role=role)
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
    era = obj.role == "admin" and obj.active
    queda = role == "admin" and bool(active)
    if deja_sin_admins(era, queda, _otros_admins_activos(s, obj.id)):
        raise ValueError(_ULTIMO_ADMIN_MSG)
    username = username.strip()
    if _username_ocupado(s, username, excluir_id=obj.id):
        raise ValueError(_USERNAME_DUPLICADO_MSG)
    obj.username = username
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
    era = obj.role == "admin" and obj.active
    if deja_sin_admins(era, False, _otros_admins_activos(s, obj.id)):
        raise ValueError(_ULTIMO_ADMIN_MSG)
    s.delete(obj)
    s.commit()


# ---------------------------------------------------------------------------
# Helpers get-or-create (usados por autocompletado)
# ---------------------------------------------------------------------------


def _upsert_alias(s, entity_type: str, source_value: str, entity_id: int) -> None:
    # ci_equals: el match de aliases era case-insensitive vía collation de
    # MySQL — sin esto, en PG 'Technology' y 'technology' serían aliases
    # distintos (duplicados silenciosos)
    from app.services.db_compat import ci_equals
    obj = s.query(CatalogAlias).filter(
        CatalogAlias.entity_type == entity_type,
        ci_equals(CatalogAlias.source_value, source_value),
    ).first()
    if obj:
        obj.entity_id = entity_id
    else:
        s.add(CatalogAlias(entity_type=entity_type, source_value=source_value, entity_id=entity_id))


def _resolve_alias(s, entity_type: str, value: str, Model):
    from app.services.db_compat import ci_equals
    alias = s.query(CatalogAlias).filter(
        CatalogAlias.entity_type == entity_type,
        ci_equals(CatalogAlias.source_value, value),
    ).first()
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


def get_or_create_currency_by_name(name: str) -> tuple:
    s = get_session()
    value = name.strip()
    existing = s.query(Currency).filter(Currency.name.ilike(value)).first()
    if existing:
        return existing, False
    obj = Currency(name=value, iso_code=None)
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

