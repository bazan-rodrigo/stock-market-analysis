"""
Script de inicialización de la base de datos.

Uso:
    python scripts/init_db.py

Qué hace:
  1. Aplica las migraciones de Alembic (crea todas las tablas).
  2. Inserta datos de referencia básicos (fuente Yahoo Finance).
  3. Crea el usuario admin inicial (admin / admin123).

Seguro para ejecutar múltiples veces: verifica existencia antes de insertar.
"""
import sys
from pathlib import Path

# Asegurar que la raíz del proyecto está en el path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import subprocess
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def run_migrations() -> None:
    logger.info("Aplicando migraciones de Alembic...")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.error("Error en migraciones:\n%s", result.stderr)
        sys.exit(1)
    logger.info("Migraciones aplicadas correctamente.")
    if result.stdout:
        logger.info(result.stdout)


def _upsert(session, model, lookup_field: str, lookup_value, **kwargs):
    """Inserta el registro si no existe. Devuelve el objeto."""
    obj = session.query(model).filter(
        getattr(model, lookup_field) == lookup_value
    ).first()
    if obj is None:
        obj = model(**{lookup_field: lookup_value}, **kwargs)
        session.add(obj)
        session.flush()
        logger.info("%s '%s' creado.", model.__name__, lookup_value)
    return obj


def seed_reference_data() -> None:
    from app.database import get_session
    from app.models import (
        Country, Currency, InstrumentType, Market, PriceSource,
    )

    s = get_session()

    # ── Fuente de precios ──────────────────────────────────────────────────
    _upsert(s, PriceSource, "name", "Yahoo Finance",
            description="Datos de mercado gratuitos via yfinance (Yahoo Finance API).",
            active=True)

    # ── Países ────────────────────────────────────────────────────────────
    countries_data = [
        ("Estados Unidos", "USA"),
        ("Argentina",      "ARG"),
        ("México",         "MEX"),
        ("Alemania",       "DEU"),
        ("Reino Unido",    "GBR"),
        ("Global",         "GLB"),   # usado por mercados sin país específico (ej: cripto)
    ]
    countries = {}
    for name, iso in countries_data:
        countries[iso] = _upsert(s, Country, "iso_code", iso, name=name)

    # ── Monedas ───────────────────────────────────────────────────────────
    currencies_data = [
        ("USD",  "Dólar estadounidense"),
        ("ARS",  "Peso argentino"),
        ("MXN",  "Peso mexicano"),
        ("EUR",  "Euro"),
        ("GBP",  "Libra esterlina"),
        ("USDT", "Tether"),
    ]
    currencies = {}
    for iso, name in currencies_data:
        currencies[iso] = _upsert(s, Currency, "iso_code", iso, name=name)

    # ── Mercados ──────────────────────────────────────────────────────────
    markets_data = [
        ("NYSE",     "New York Stock Exchange",  "USA"),
        ("NASDAQ",   "NASDAQ",                   "USA"),
        ("BYMA",     "Bolsa y Mercados Argentinos", "ARG"),
        ("MAE",      "Mercado Abierto Electrónico", "ARG"),
        ("BMV",      "Bolsa Mexicana de Valores",   "MEX"),
        ("XETRA",    "Deutsche Börse XETRA",        "DEU"),
        ("LSE",      "London Stock Exchange",        "GBR"),
        ("EURONEXT", "Euronext",                     "DEU"),
        ("CRYPTO",   "Mercado de Criptomonedas",     "GLB"),
    ]
    for code, name, country_iso in markets_data:
        _upsert(s, Market, "name", name,
                country_id=countries[country_iso].id)

    # ── Tipos de instrumento ──────────────────────────────────────────────
    instrument_types_data = [
        ("Acción",        "USD"),
        ("ETF",           "USD"),
        ("Bono",          "USD"),
        ("CEDEAR",        "ARS"),
        ("Criptomoneda",  "USDT"),
        ("Opción",        "USD"),
        ("Futuro",        "USD"),
        ("Índice",        "USD"),
    ]
    for name, cur_iso in instrument_types_data:
        _upsert(s, InstrumentType, "name", name,
                default_currency_id=currencies[cur_iso].id)

    s.commit()
    logger.info("Datos de referencia cargados correctamente.")


def create_admin_user() -> None:
    from app.config import Config
    from app.database import get_session
    from app.models import User

    s = get_session()
    existing = s.query(User).filter(User.username == Config.ADMIN_USERNAME).first()
    if existing is not None:
        logger.info("Usuario admin '%s' ya existe — omitido.", Config.ADMIN_USERNAME)
        return

    admin = User(
        username=Config.ADMIN_USERNAME,
        role="admin",
        active=True,
    )
    admin.set_password(Config.ADMIN_PASSWORD)
    s.add(admin)
    s.commit()
    logger.info(
        "Usuario admin creado: usuario='%s', contraseña='%s'. "
        "¡Cambiala después del primer login!",
        Config.ADMIN_USERNAME,
        Config.ADMIN_PASSWORD,
    )


if __name__ == "__main__":
    run_migrations()
    seed_reference_data()
    create_admin_user()
    logger.info("Inicialización completada.")
