"""Limpieza de datos derivados/operativos, preservando lo que se cargó a mano.

Fuente ÚNICA de verdad del alcance de la limpieza: la consumen tanto la
pantalla `/admin/cleanup` como `scripts/clean_data.py`. Antes cada una tenía
su propia lista y divergieron — la pantalla quedó con la lista vieja, que
incluía assets/prices/catálogos y borraba con FOREIGN_KEY_CHECKS=0: eso dejó
huérfanas ~45 tablas relacionadas a activos (jul-2026). Cualquier tabla nueva
se agrega ACÁ y las dos entradas quedan al día.

Qué borra (todo 100% recomputable desde lo que queda — assets + prices +
fórmulas de sintéticos — vía los botones "Recalcular completo" del Centro de
Datos), y los snapshots de backtest/cartera, que NO se recomputan pero se
borran por decisión de producto: la limpieza deja la base sin datos operativos.

Qué NO borra, nunca: activos, precios, fuentes, catálogos, definiciones
(indicadores/señales/estrategias), configuración (*_config, scheduler),
fórmulas de sintéticos, divisores de conversión, usuarios y
—lo más irreemplazable— las carteras con su registro de operaciones
(portfolio / portfolio_member / portfolio_transaction), que son datos
cargados a mano y no se recrean solos.
"""
import logging

import sqlalchemy as sa

from app.services import db_compat

logger = logging.getLogger(__name__)

# Tablas dinámicas, una por indicador/señal/estrategia (ver get_ind_table y
# signal_store): se descubren del catálogo en vez de mantenerse a mano, para
# no volver a dejar alguna afuera al agregar una nueva. Se VACÍAN, no se
# dropean — la definición sigue existiendo.
# Ojo con los prefijos: llevan "_" a propósito. Sin él, "ind_" tomaría
# `industries` e `indicator_definitions`, y "sig_" tomaría `signal`.
_DYNAMIC_PREFIXES = ("ind_", "sig_", "strat_res_")

# Tablas hoja: nada las referencia, así que se vacían en cualquier orden y sin
# tocar el chequeo de FKs.
_LEAF_TABLES = [
    # ── Indicadores y fundamentales (derivados) ──
    "current_indicator_values",
    "fundamental_quarterly",
    # ── Señales y estrategias (derivados) ──
    "group_scores",
    "group_signal_value",
    # Crítico limpiarla junto con las tablas de señales: si quedaran markers
    # de fechas "ya evaluadas", el delta SALTEARÍA las fechas recién limpiadas.
    "signal_eval_log",
    # ── Logs y registros de corrida ──
    "indicator_update_log",
    "fundamental_update_log",
    "price_update_log",
    "import_log",
    "verification_run_log",
    "asset_verification_flag",
    # Locks persistidos de corridas: un lock huérfano deja trabado el botón
    # del Centro de Datos, así que la limpieza también lo destraba.
    "run_lock",
    # ── Eventos y aliases (se redescargan / reimportan) ──
    "market_event",
    "catalog_aliases",
    # ── Hijas de los snapshots: van ANTES que sus padres (ver abajo) ──
    "backtest_ic_point",
    "backtest_quantile_stat",
    "portfolio_run_point",
]

# Tablas referenciadas por una FK desde otra tabla. Van al final (sus hijas ya
# quedaron vacías) y con DELETE, no TRUNCATE: MySQL rechaza TRUNCATE sobre una
# tabla con FKs entrantes aunque la hija esté vacía, y PG exige CASCADE. Son
# tablas chicas (una fila por corrida guardada), el DELETE no pesa.
_REFERENCED_TABLES = [
    "backtest_run",
    "portfolio_run",
]

# Descripción para la UI: qué se borra, en lenguaje de usuario. El detalle
# exacto sale de resolve_tables(); esto es el resumen legible.
TABLES_INFO = [
    ("ind_* / ind_fundamental_* / ind_asset_meta",
     "Series históricas de indicadores por activo"),
    ("current_indicator_values",  "Valores vigentes de indicadores"),
    ("sig_* / strat_res_*",       "Valores de señales y rankings de estrategias"),
    ("group_scores / group_signal_value",
     "Agregados y señales por grupo"),
    ("fundamental_quarterly",     "Ratios fundamentales trimestrales"),
    ("backtest_run / portfolio_run",
     "Corridas guardadas de backtest y de cartera"),
    ("market_event",              "Eventos de mercado"),
    ("catalog_aliases",           "Aliases del catálogo"),
    ("run_lock",                  "Locks de corridas"),
    ("*_update_log / *_eval_log / import_log",
     "Logs de actualización, evaluación e importación"),
    ("asset_verification_flag / verification_run_log",
     "Flags y logs de verificación de activos"),
]

# Lo que se preserva, para mostrarlo junto al botón: la mitad tranquilizadora
# del mensaje es tan importante como la lista de arriba.
PRESERVED_INFO = [
    "Activos, precios y fuentes de precio",
    "Catálogos (sectores, industrias, mercados, países, monedas, tipos)",
    "Definiciones de indicadores, señales y estrategias",
    "Fórmulas de sintéticos y divisores de conversión",
    "Carteras y su registro de operaciones",
    "Usuarios y configuración de la app",
]


def resolve_tables(bind) -> tuple[list[str], list[str]]:
    """(hojas, referenciadas) que existen realmente en esta base.

    Se filtra por existencia porque la lista fija sobrevive a los modelos: la
    limpieza vieja borraba `screener_snapshot`, cuyo modelo ya no existe, y en
    una base nueva ese DELETE reventaba la corrida entera.
    """
    existing = set(sa.inspect(bind).get_table_names())
    dynamic = db_compat.list_tables_by_prefix(bind, *_DYNAMIC_PREFIXES)
    leaves = dynamic + [t for t in _LEAF_TABLES if t in existing]
    referenced = [t for t in _REFERENCED_TABLES if t in existing]
    return leaves, referenced


def clean_data(bind=None) -> dict:
    """Vacía las tablas derivadas/operativas. Devuelve {'tables': [...]}.

    Todo en una transacción: si algo falla, no queda una limpieza a medias.
    No se toca FOREIGN_KEY_CHECKS — con esta lista no hace falta (ninguna
    tabla padre de las que se preservan está incluida), y desactivarlo fue
    justamente lo que dejó filas huérfanas la vez anterior.
    """
    from app.database import engine

    bind = bind if bind is not None else engine
    with bind.begin() as conn:
        leaves, referenced = resolve_tables(conn)
        for table in leaves:
            db_compat.wipe_table(conn, db_compat.quote_ident(conn, table))
            logger.info("%-40s vaciada", table)
        for table in referenced:
            conn.execute(sa.text(
                f"DELETE FROM {db_compat.quote_ident(conn, table)}"))
            logger.info("%-40s vaciada", table)

    tables = leaves + referenced
    logger.info("Limpieza completada: %d tablas vaciadas.", len(tables))
    return {"tables": tables}
