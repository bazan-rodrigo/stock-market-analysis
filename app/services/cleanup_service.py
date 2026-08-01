"""Limpieza de datos derivados/operativos, preservando lo que se cargó a mano.

Fuente ÚNICA de verdad del alcance de la limpieza: la consumen tanto la
pantalla `/admin/cleanup` como `scripts/clean_data.py`. Antes cada una tenía
su propia lista y divergieron — la pantalla quedó con la lista vieja, que
incluía assets/prices/catálogos y borraba con FOREIGN_KEY_CHECKS=0: eso dejó
huérfanas ~45 tablas relacionadas a activos (jul-2026). Cualquier tabla nueva
se agrega ACÁ y las dos entradas quedan al día.

Qué borra (todo 100% recomputable desde lo que queda — assets + prices +
fundamental_quarterly + fórmulas de sintéticos — vía los botones "Recalcular
completo" del Centro de Datos), y los snapshots de backtest/cartera, que NO se
recomputan pero se borran por decisión de producto: la limpieza deja la base sin
datos operativos.

Qué NO borra, nunca: activos, precios, fuentes, catálogos, definiciones
(indicadores/señales/estrategias), configuración (*_config, scheduler),
fórmulas de sintéticos, divisores de conversión, usuarios, los estados
contables trimestrales (ver abajo) y —lo más irreemplazable— las carteras con
su registro de operaciones (portfolio / portfolio_member /
portfolio_transaction), que son datos cargados a mano y no se recrean solos.

Este módulo expone además `reset_to_fresh_install` (mucho más destructivo): un
reinicio TOTAL que deja la base como recién instalada —vacía TODO, incluido lo
que clean_data preserva, resiembra los datos integrados y recrea admin/admin123—.
Es la contracara del borrado suave; lo consumen el botón con doble confirmación
de /admin/cleanup y el `--reset` de scripts/clean_data.py.
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
    # OJO: `fundamental_quarterly` NO va acá. Estuvo hasta jul-2026 por un
    # error de clasificación: son estados contables CRUDOS bajados de la
    # fuente (fundamental_service._fetch → source.fetch_quarterly), no ratios
    # calculados, y encima son el INSUMO del recálculo — `_load_all_quarters`
    # lee de ahí para producir ind_fundamental_*. Borrarlos dejaba a
    # "Recalcular completo" sin materia prima. Y no se recuperan con una
    # redescarga: Yahoo sirve una ventana corta de trimestres (~4-5) y la
    # historia larga se acumula upsert a upsert con el correr de las corridas.
    # Por el propio criterio de este módulo, califican MÁS que `prices` para
    # conservarse.
    "current_indicator_values",
    # ── Señales y estrategias (derivados) ──
    # Las tablas ANCHAS son el almacenamiento vivo desde el cutover (migración
    # 0094 dropeó las per-entidad sig_{id}/strat_res_{id}). Van explícitas
    # porque _DYNAMIC_PREFIXES ya no las alcanza: "sig_" y "strat_res_" no
    # matchean "signal_values_wide" ni "strategy_results_wide". Sin esto la
    # limpieza borraba los markers pero DEJABA los valores — prometía vaciar
    # "señales y estrategias" y no lo hacía.
    "signal_values_wide",
    "strategy_results_wide",
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
    ("signal_values_wide / strategy_results_wide",
     "Valores de señales y rankings de estrategias"),
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
    "Estados contables trimestrales descargados de la fuente",
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


# ── Reinicio total a estado de fábrica (reset_to_fresh_install) ───────────────
# Mucho más destructivo que clean_data: borra TODO, incluido lo que la limpieza
# preserva. Estas listas son el mensaje legible del botón con doble confirmación
# de /admin/cleanup.
RESET_WIPES_INFO = [
    "Activos, precios y fuentes de precio propias",
    "Estados contables trimestrales descargados de la fuente",
    "Catálogos y sus membresías (sectores, industrias, mercados, países, "
    "monedas, tipos de instrumento)",
    "Definiciones de señales y estrategias, y todo lo derivado (indicadores, "
    "señales, rankings)",
    "Fórmulas de sintéticos y divisores de conversión de moneda",
    "Carteras y su registro de operaciones",
    "Corridas guardadas de backtest y de cartera",
    "Configuración de la app y del scheduler",
    "TODOS los usuarios (se recrea solo admin/admin123)",
]

RESET_KEEPS_INFO = [
    "El esquema de la base (tablas vacías, sin cambiar la versión de migraciones)",
    "Los datos integrados de fábrica: fuentes Yahoo/Ámbito/Calculado, "
    "indicadores integrados y el activo RIESGO_PAIS_AR",
    "El usuario admin de fábrica (admin / admin123)",
]


def _fresh_install_wipe(conn) -> list[str]:
    """Vacía TODAS las tablas de la base y devuelve sus nombres.

    NO toca `alembic_version`: no está en el metadata ORM ni matchea los
    prefijos dinámicos, así que la versión de migraciones queda intacta (el
    esquema ya está en head, no hace falta re-estampar).

    El vaciado —incluidas las tablas dinámicas ind_*/sig_*/strat_res_— lo hace
    db_compat.truncate_all_tables de una sola vez, salteando la verificación de
    FK: es seguro porque se vacía TODO el grafo (nada puede quedar huérfano) y
    así se resuelve el ciclo assets ↔ markets, que un DELETE ordenado no podría
    (a diferencia de la limpieza parcial de clean_data, que mantiene los FK).
    """
    from app.database import Base

    existing = set(sa.inspect(conn).get_table_names())
    core_names = [n for n in Base.metadata.tables if n in existing]
    # Dinámicas: existen fuera del metadata (ind_asset_meta SÍ es modelo, así
    # que ya está en core_names y no se duplica).
    core_set = set(core_names)
    dynamic = [t for t in db_compat.list_tables_by_prefix(conn, *_DYNAMIC_PREFIXES)
               if t not in core_set]

    names = dynamic + core_names
    db_compat.truncate_all_tables(conn, names)
    for name in names:
        logger.info("%-40s vaciada", name)
    return names


def _recreate_admin_user() -> None:
    """Recrea el usuario admin inicial (mismo criterio que scripts/init_db.py).
    Se llama tras vaciar la tabla de usuarios, así que siempre inserta; el
    filtro ci_equals es una defensa por si quedara alguno."""
    from app.config import Config
    from app.database import get_session
    from app.models import User

    s = get_session()
    if s.query(User).filter(
            db_compat.ci_equals(User.username, Config.ADMIN_USERNAME)).first():
        return
    admin = User(username=Config.ADMIN_USERNAME, role="admin", active=True)
    admin.set_password(Config.ADMIN_PASSWORD)
    s.add(admin)
    s.commit()
    logger.info("Usuario admin de fábrica recreado: '%s'.", Config.ADMIN_USERNAME)


def reset_to_fresh_install(bind=None) -> dict:
    """Deja la base COMO RECIÉN INSTALADA. Devuelve {'tables': [...]} vaciadas.

    Equivale a scripts/init_db.py sobre una base vacía: vacía TODAS las tablas
    —incluidas las que clean_data preserva: activos, precios, catálogos,
    definiciones de señales/estrategias, sintéticos, conversión, carteras y
    usuarios—, resiembra los datos integrados y recrea el admin de fábrica.

    NO dropea ni recrea el esquema, y no toca alembic_version: la versión de
    migraciones queda intacta. Las tablas dinámicas sig_*/strat_res_* huérfanas
    las dropea el reconciliador que corre dentro de ensure_builtin_data (ya sin
    definición que las respalde); las ind_* de los indicadores integrados se
    conservan vacías (checkfirst en la resiembra).

    El vaciado corre en una transacción sobre `bind` (default: engine); la
    resiembra y el admin usan la sesión global de la app (mismo engine). Es la
    contracara —mucho más destructiva— del borrado suave de clean_data.
    """
    from app.database import engine

    bind = bind if bind is not None else engine
    with bind.begin() as conn:
        wiped = _fresh_install_wipe(conn)

    # Resembrar lo integrado (fuentes, RIESGO_PAIS_AR, indicadores + tablas
    # ind_*) y reconciliar dinámicas (dropea las sig_/strat_res_ huérfanas).
    from app.services.startup_service import ensure_builtin_data
    ensure_builtin_data()

    # Usuario admin de fábrica (la tabla de usuarios quedó vacía arriba).
    _recreate_admin_user()

    logger.info("Reinicio a estado de fábrica completado: %d tablas vaciadas.",
                len(wiped))
    return {"tables": wiped}
