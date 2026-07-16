"""
Portabilidad del esquema y de las migraciones (soporte dual MySQL/PG,
ver docs/notes/design_postgresql_dual.md).

La cadena Alembic 0001–0075 está CONGELADA como solo-MySQL: las bases
nuevas (de cualquier motor) nacen por create_all + stamp head
(scripts/init_db.py). Desde la 0076 la cadena es ÚNICA y portable — el
meta-test de acá renderiza en modo offline (--sql) las migraciones
posteriores al freeze contra los dialectos mysql y postgresql: atrapa
backticks, AUTO_INCREMENT crudo, DATABASE(), enteros en Boolean y todo
error de compilación de DDL, sin ninguna base ni driver.

Limitación conocida: una migración de DATOS que lea con op.get_bind() no
puede renderizarse offline — si aparece una legítima, excluirla acá
explícitamente (y verificarla contra ambos motores en el Codespace).
"""
import io
from pathlib import Path

import pytest
import sqlalchemy as sa

# El paquete alembic instalado (regular) gana sobre el directorio alembic/
# del repo (namespace) — pero si no está instalado, el import resolvería al
# directorio y daría errores crípticos: skip explícito con el motivo real.
pytest.importorskip("alembic.command",
                    reason="requiere el paquete alembic instalado en el venv")
from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parent.parent

# Última revisión de la cadena congelada solo-MySQL. No mover hacia
# adelante: las migraciones posteriores DEBEN ser portables.
FROZEN_HEAD = "0075"


def _cfg(url: str) -> AlembicConfig:
    cfg = AlembicConfig(str(ROOT / "alembic.ini"), stdout=io.StringIO())
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    # env.py solo inyecta Config.DATABASE_URL si la URL viene vacía: esta
    # URL explícita define el dialecto del render offline
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _head() -> str:
    return ScriptDirectory.from_config(_cfg("sqlite://")).get_current_head()


@pytest.mark.parametrize("dialect_url", ["mysql://", "postgresql://"])
def test_migraciones_post_freeze_renderizan_en_ambos_dialectos(dialect_url):
    head = _head()
    if head == FROZEN_HEAD:
        pytest.skip("sin migraciones posteriores al freeze 0075 todavía")
    # Si una migración nueva tiene SQL de un solo motor, el render del otro
    # dialecto revienta acá (CompileError / error de sintaxis del DDL)
    command.upgrade(_cfg(dialect_url), f"{FROZEN_HEAD}:{head}", sql=True)


def test_enums_de_modelos_tienen_nombre():
    """sa.Enum sin name= compila en MySQL (ENUM inline) pero aborta el DDL
    en PostgreSQL (CREATE TYPE necesita nombre). Como las bases nuevas
    nacen por create_all desde los modelos, ningún Enum puede quedar sin
    nombre."""
    import app.models  # noqa: F401 — registra todos los modelos
    from app.database import Base

    sin_nombre = sorted(
        f"{t.name}.{c.name}"
        for t in Base.metadata.tables.values()
        for c in t.columns
        if isinstance(c.type, sa.Enum) and not c.type.name
    )
    assert sin_nombre == [], (
        f"Enums sin name= (rompen create_all en PostgreSQL): {sin_nombre}")


# ── ensure_ind_table: materializa ind_{code} en bases nacidas por create_all ─

def test_ensure_ind_table_crea_num_y_str_y_es_idempotente():
    from app.models.indicator_store import ensure_ind_table

    eng = sa.create_engine("sqlite://")
    ensure_ind_table("rsi_daily", "num", bind=eng)
    ensure_ind_table("trend_daily", "str", bind=eng)
    ensure_ind_table("rsi_daily", "num", bind=eng)   # segunda vez: no-op

    insp = sa.inspect(eng)
    assert insp.has_table("ind_rsi_daily")
    assert insp.has_table("ind_trend_daily")

    # esquema de la migración 0043: PK (asset_id, date) y columna value
    # tipada según el indicador
    cols_num = {c["name"]: c for c in insp.get_columns("ind_rsi_daily")}
    cols_str = {c["name"]: c for c in insp.get_columns("ind_trend_daily")}
    assert set(cols_num) == {"asset_id", "date", "value"}
    assert isinstance(cols_num["value"]["type"], sa.Float)
    assert isinstance(cols_str["value"]["type"], sa.String)
    assert insp.get_pk_constraint("ind_rsi_daily")["constrained_columns"] == [
        "asset_id", "date"]

    # índice por date (migración 0062)
    assert any(ix["column_names"] == ["date"]
               for ix in insp.get_indexes("ind_rsi_daily"))
