"""Configuración de la suite.

Los tests cubren SOLO lógica pura (fórmulas, algoritmos, helpers): nunca se
conecta a la base. Para poder importar los servicios sin el driver de MySQL,
la DATABASE_URL se apunta a un stub sqlite ANTES de importar nada de app.
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# El stub es descartable: se borra en cada corrida para que create_all lo
# recree con el esquema ACTUAL de los modelos (create_all no altera tablas
# existentes — un stub viejo rompería la suite tras agregar una columna).
_STUB = ROOT / ".pytest-stub.db"
try:
    _STUB.unlink(missing_ok=True)
except PermissionError:
    # Windows: si otro proceso todavía tiene tomado el archivo (dos corridas
    # de pytest en paralelo, o un handle que quedó colgado de una anterior),
    # unlink tira WinError 32 y ABORTA la colección entera. Usar un stub
    # propio del proceso en vez de romper la suite.
    _STUB = ROOT / f".pytest-stub-{os.getpid()}.db"
    _STUB.unlink(missing_ok=True)

# FORZADO, no setdefault: si DATABASE_URL ya viene seteada —Codespace,
# Railway, cualquier entorno con base real— setdefault la respetaría y la
# suite entera correría contra ESA base. No es teórico: el fixture de
# tests/test_affected_by_new_assets.py hace `DELETE FROM assets`, y prices e
# ind_* tienen ON DELETE CASCADE sobre assets -> vaciaría la base completa.
# La suite es de lógica pura: SIEMPRE va contra el stub sqlite.
_prev = os.environ.get("DATABASE_URL")
os.environ["DATABASE_URL"] = f"sqlite:///{_STUB}"
if _prev and not _prev.startswith("sqlite"):
    print(f"[conftest] DATABASE_URL real ignorada ({_prev.split('://')[0]}://…): "
          "la suite corre SIEMPRE contra el stub sqlite, nunca contra una "
          "base real.", file=sys.stderr)

# La suite corre contra el stub sqlite con tablas ind_{code} per-código: forzar
# el camino per-código (en prod el default de use_wide_ind_tables es wide desde
# la fase 5). Los tests de tablas anchas lo vuelven a "1" con monkeypatch.
os.environ["USE_WIDE_IND_TABLES"] = "0"


def pytest_sessionstart(session):
    """Cinturón además de tiradores: aborta la corrida si el engine NO quedó
    apuntando a sqlite.

    El forzado de DATABASE_URL de arriba ya lo garantiza hoy, pero varios
    fixtures borran tablas sin ningún filtro — el peor es
    `DELETE FROM assets` en test_affected_by_new_assets, que por
    ON DELETE CASCADE arrastra prices y todas las ind_*. Si alguien vuelve a
    poner setdefault, cambia la config o agrega otro conftest, esto tiene que
    fallar RUIDOSAMENTE antes de tocar nada, no vaciar una base real.

    Corre en sessionstart: antes de la colección y de cualquier fixture, así
    que si aborta todavía no se ejecutó ninguna sentencia.
    """
    from app.database import engine

    if engine.dialect.name != "sqlite":
        pytest.exit(
            f"ABORTADO: la suite quedó apuntando a un engine "
            f"'{engine.dialect.name}', no a sqlite.\n"
            f"Los fixtures hacen DELETE/TRUNCATE sin filtro y vaciarían esa "
            f"base (assets -> CASCADE -> prices e ind_*).\n"
            f"Revisá el forzado de DATABASE_URL en tests/conftest.py.",
            returncode=3)
