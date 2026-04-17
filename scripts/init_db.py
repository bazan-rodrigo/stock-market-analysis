"""
Script de inicialización de la base de datos.

Uso:
    python scripts/init_db.py

Qué hace:
  1. Aplica las migraciones de Alembic (crea todas las tablas).
  2. Inserta la fuente de precios Yahoo Finance.
  3. Crea el usuario admin inicial.

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
    from app.models import PriceSource

    s = get_session()

    _upsert(s, PriceSource, "name", "Yahoo Finance",
            description="Datos de mercado gratuitos via yfinance (Yahoo Finance API).",
            active=True)

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
