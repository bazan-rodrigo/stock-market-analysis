"""
Limpia todos los datos operativos de la BD, preservando usuarios.

Elimina (en orden seguro para FKs):
  precios, logs de precios, screener snapshots, eventos de mercado,
  logs de importación, aliases de catálogo, activos, industrias,
  mercados, tipos de instrumento, sectores, países, monedas,
  fuentes de precios.

Uso:
    python scripts/clean_data.py
    python scripts/clean_data.py --confirm   (sin pregunta interactiva)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Orden importa: hijos antes que padres
_TABLES = [
    "prices",
    "price_update_log",
    "screener_snapshot",
    "market_event",
    "import_log",
    "catalog_aliases",
    "assets",
    "industries",
    "markets",
    "instrument_types",
    "sectors",
    "countries",
    "currencies",
    "price_sources",
]


def clean_data() -> None:
    from sqlalchemy import text
    from app.database import engine

    with engine.begin() as conn:
        try:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
            total = 0
            for table in _TABLES:
                result = conn.execute(text(f"DELETE FROM `{table}`"))
                rows = result.rowcount
                total += rows
                logger.info("%-25s  %d filas eliminadas", table, rows)
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
            logger.info("Listo. Total: %d filas eliminadas. Usuarios conservados.", total)
        except Exception as exc:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
            logger.error("Error durante la limpieza: %s", exc)
            raise


if __name__ == "__main__":
    confirm = "--confirm" in sys.argv
    if not confirm:
        print("ATENCIÓN: esto eliminará TODOS los activos, precios y catálogos.")
        print("Los usuarios se conservan.")
        resp = input("¿Confirmar? (s/N): ").strip().lower()
        if resp != "s":
            print("Cancelado.")
            sys.exit(0)

    clean_data()
