"""
Limpia datos derivados/operativos de la BD, preservando activos, precios,
fuentes de precio, catálogos (industrias, mercados, sectores, países,
monedas, tipos de instrumento) y usuarios.

Todo lo que borra es 100% recomputable desde lo que queda (assets + prices
+ fórmulas de sintéticos ya cargadas) vía los botones "Recalcular completo"
de cada tarjeta del Centro de Datos — indicadores técnicos, ratios
fundamentales, valores de sintéticos, logs de recálculo.

No borra assets/prices/price_sources/catálogos ni synthetic_formula/
synthetic_component: son datos que no se recrean solos (un activo cargado
a mano, precios que tardan en redescargarse de una fuente externa, una
fórmula de sintético armada por el usuario) — antes esta lista SÍ incluía
assets/prices/catálogos, y una limpieza con FOREIGN_KEY_CHECKS=0 dejó
huérfanas ~45 tablas relacionadas a activos porque no estaban en la lista
(ver jul-2026: fundamental_quarterly, current_indicator_values,
synthetic_formula/component y varias ind_fundamental_* quedaron con filas
apuntando a activos ya borrados).

Elimina:
  - tablas ind_{código}/ind_fundamental_{código} e ind_asset_meta:
    descubiertas desde information_schema (no hace falta mantenerlas a
    mano, se crean una por indicador — ver get_ind_table).
  - metadatos/logs de indicadores y fundamentales: current_indicator_values,
    indicator_update_log, fundamental_quarterly, fundamental_update_log.
  - señales y resultados de estrategias: tablas sig_{id}/strat_res_{id}
    (dinámicas por señal/estrategia, ver signal_store — se VACÍAN, no se
    dropean: la definición sigue existiendo), group_signal_value,
    group_scores, signal_eval_log.
  - screener, eventos de mercado, logs de importación, aliases de catálogo.

Uso:
    python scripts/clean_data.py
    python scripts/clean_data.py --confirm   (sin pregunta interactiva)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import logging

from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Tablas fijas a limpiar (no dependen de un indicador puntual). synthetic_formula/
# synthetic_component NO están acá a propósito: son configuración armada a mano,
# no datos derivados — ver docstring del módulo.
_TABLES = [
    "screener_snapshot",
    "market_event",
    "import_log",
    "catalog_aliases",
    "group_signal_value",
    "group_scores",
    # crítico limpiarla junto con las tablas de señales: si quedaran markers
    # de fechas "ya evaluadas", el delta SALTEARÍA las fechas recién limpiadas
    "signal_eval_log",
    "current_indicator_values",
    "indicator_update_log",
    "fundamental_quarterly",
    "fundamental_update_log",
]


def _dynamic_tables(conn) -> list[str]:
    """Tablas ind_{code}/ind_fundamental_{code} (una por indicador, ver
    get_ind_table) y sig_{id}/strat_res_{id} (una por señal/estrategia, ver
    signal_store), sin modelo Python fijo — se listan desde
    information_schema en vez de mantenerlas a mano acá, para no volver a
    dejar alguna afuera cuando se agregue una nueva."""
    rows = conn.execute(text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND (table_name LIKE 'ind\\_%' "
        "OR table_name LIKE 'sig\\_%' OR table_name LIKE 'strat\\_res\\_%')"
    )).fetchall()
    return [r[0] for r in rows]


def clean_data() -> None:
    from app.database import engine

    with engine.begin() as conn:
        try:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
            tables = _dynamic_tables(conn) + _TABLES
            total = 0
            for table in tables:
                result = conn.execute(text(f"DELETE FROM `{table}`"))
                rows = result.rowcount
                total += rows
                logger.info("%-35s  %d filas eliminadas", table, rows)
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
            logger.info(
                "Listo. Total: %d filas eliminadas. "
                "Activos, precios, fuentes y catálogos preservados.", total,
            )
        except Exception as exc:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
            logger.error("Error durante la limpieza: %s", exc)
            raise


if __name__ == "__main__":
    confirm = "--confirm" in sys.argv
    if not confirm:
        print("Esto eliminará indicadores, ratios fundamentales, señales, resultados")
        print("de estrategias y logs de recálculo. Activos, precios, fuentes de precio,")
        print("catálogos y fórmulas de sintéticos se conservan.")
        resp = input("¿Confirmar? (s/N): ").strip().lower()
        if resp != "s":
            print("Cancelado.")
            sys.exit(0)

    clean_data()
