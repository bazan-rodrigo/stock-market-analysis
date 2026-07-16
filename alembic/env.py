import re
import sys
from pathlib import Path

# Asegurar que el proyecto esté en el path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import Config
from app.database import Base

# Importar todos los modelos para que Alembic los detecte
import app.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Inyectar la URL desde Config solo si no viene ya definida (alembic.ini la
# deja vacía; los tests de portabilidad pasan una URL explícita por dialecto
# para renderizar migraciones en modo offline — ver
# tests/test_migration_portability.py)
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", Config.DATABASE_URL)

target_metadata = Base.metadata

# Tablas dinámicas: viven FUERA de Base.metadata a propósito (una por
# indicador/señal/estrategia — ver get_ind_table y signal_store). Sin este
# filtro, autogenerate las ve solo en la base y propone DROPearlas todas.
# ind_asset_meta sí es un modelo: no matchea la condición porque está en
# target_metadata.
_DYNAMIC_RE = re.compile(r"^(ind_.+|sig_\d+|strat_res_\d+)$")


def _include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table":
        return not (_DYNAMIC_RE.match(name or "")
                    and name not in target_metadata.tables)
    if type_ == "index":
        tname = getattr(getattr(obj, "table", None), "name", "") or ""
        return not (_DYNAMIC_RE.match(tname)
                    and tname not in target_metadata.tables)
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=_include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
