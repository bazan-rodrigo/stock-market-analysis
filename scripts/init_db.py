"""
Script de inicialización de la base de datos (MySQL/MariaDB o PostgreSQL,
según DATABASE_URL — ver docs/notes/design_postgresql_dual.md).

Uso:
    python scripts/init_db.py [--via-migrations]

Qué hace:
  1. Crea el esquema:
     - Base VACÍA → esquema final directo desde los modelos ORM
       (Base.metadata.create_all) + `alembic stamp head`. Es el único
       camino que funciona en PostgreSQL (la cadena 0001–0075 quedó
       congelada como solo-MySQL) y el recomendado también para MySQL
       nuevo. Con --via-migrations se fuerza el replay de la cadena
       completa (solo MySQL, para comparar esquemas).
     - Base EXISTENTE → `alembic upgrade head` (aplica lo pendiente).
  2. Inserta los datos de referencia integrados (fuentes de precio y de
     fundamentales, indicadores, tablas ind_*). Idempotente.
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


def _alembic(*args: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.error("Error en alembic %s:\n%s", " ".join(args), result.stderr)
        sys.exit(1)
    if result.stdout:
        logger.info(result.stdout)


def _database_is_empty() -> bool:
    import sqlalchemy as sa
    from app.database import engine
    return not sa.inspect(engine).get_table_names()


def create_schema(via_migrations: bool = False) -> None:
    if not _database_is_empty():
        logger.info("Base existente: aplicando migraciones pendientes...")
        _alembic("upgrade", "head")
        logger.info("Migraciones aplicadas correctamente.")
        return

    if via_migrations:
        logger.info("Base vacía: replay de la cadena completa de "
                    "migraciones (--via-migrations, solo MySQL)...")
        _alembic("upgrade", "head")
        logger.info("Migraciones aplicadas correctamente.")
        return

    logger.info("Base vacía: creando esquema final desde los modelos "
                "(create_all) + stamp head...")
    from app.database import Base, engine
    import app.models  # noqa: F401 — registra todos los modelos en Base.metadata
    Base.metadata.create_all(engine)
    _alembic("stamp", "head")
    logger.info("Esquema creado y estampado en head.")



def seed_reference_data() -> None:
    from app.services.startup_service import ensure_builtin_data
    ensure_builtin_data()
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
    create_schema(via_migrations="--via-migrations" in sys.argv)
    seed_reference_data()
    create_admin_user()
    logger.info("Inicialización completada.")
