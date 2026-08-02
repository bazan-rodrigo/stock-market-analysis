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
    # Historial de corridas (0096). Quedó afuera de esta lista hasta ago-2026
    # simplemente porque nació después de escribirla — el trinquete de
    # clasificación (test_toda_tabla_del_esquema_esta_clasificada) lo destapó.
    # Va con el resto de los registros de corrida: después de la limpieza
    # describiría corridas cuyos datos ya no existen. Se autolimpia igual a los
    # 180 días (run_history_service.prune_old), así que esto no es por tamaño.
    "run_history",
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

# Lo que la limpieza preserva DELIBERADAMENTE, con el motivo de cada una. Es la
# contracara exacta de las listas de arriba: entre las tres tiene que quedar
# clasificada CADA tabla del esquema, y eso lo verifica
# test_toda_tabla_del_esquema_esta_clasificada — una tabla nueva rompe la suite
# hasta que alguien decida conscientemente de qué lado va.
#
# Por qué existe esta lista y no alcanza con "lo que no está en _LEAF_TABLES":
# ese implícito fue el agujero. Cuando la 0094 dropeó las tablas por señal, la
# limpieza dejó de vaciar los valores y los tests siguieron en verde, porque
# preguntaban por nombres escritos a mano en vez de por el esquema real. Lo
# mismo con `run_history`, que nació después de la lista y quedó sin vaciar sin
# que nadie lo decidiera. `PRESERVED_INFO` (abajo) dice esto mismo en lenguaje
# de usuario, para la pantalla; acá está por tabla, para la suite.
_PRESERVED_TABLES = {
    # ── El insumo del recálculo: sin esto "Recalcular completo" no puede ──
    "assets":            "el activo en sí, cargado a mano o por import",
    "prices":            "serie de precios: insumo de TODOS los derivados",
    "price_sources":     "de dónde baja los precios cada activo",
    "fundamental_quarterly":
        "estados contables CRUDOS de la fuente e insumo de ind_fundamental_*; "
        "Yahoo sirve una ventana corta de trimestres, así que una redescarga NO "
        "los restituye (ver el comentario en _LEAF_TABLES)",
    "fundamental_sources": "de dónde bajan los fundamentales",
    # ── Catálogos (se reimportan, pero son curados) ──
    "sectors":           "catálogo",
    "industries":        "catálogo",
    "markets":           "catálogo",
    "countries":         "catálogo",
    "currencies":        "catálogo",
    "instrument_types":  "catálogo",
    # ── Definiciones: la limpieza borra los RESULTADOS, no las reglas ──
    "indicator_definitions": "definición de indicador",
    "signal":                "definición de señal",
    "strategy":              "definición de estrategia",
    "strategy_component":    "componentes de la estrategia (parte de su definición)",
    "synthetic_formula":     "fórmula del activo sintético",
    "synthetic_component":   "operandos de la fórmula sintética",
    "currency_conversion_divisor":
        "divisor de conversión de moneda, elegido a mano",
    # ── Parámetros de cálculo (configuración, no datos) ──
    "pnf_config":        "parámetros de Point & Figure",
    "sr_config":         "parámetros de soportes/resistencias",
    "regime_config":     "parámetros de régimen",
    "volatility_config": "parámetros de volatilidad",
    "drawdown_config":   "parámetros de drawdown",
    "scheduler_config":  "horarios de las tareas diarias",
    # ── Lo más irreemplazable: cargado a mano y no se recrea solo ──
    "portfolio":             "cartera",
    "portfolio_member":      "composición de la cartera",
    "portfolio_transaction": "registro de operaciones, cargado a mano",
    # ── Acceso ──
    "users":        "usuarios y sus roles",
    "oauth_client": "conector MCP autorizado: borrarlo cortaría el acceso de "
                    "la IA sin avisar, igual que borrar el usuario",
    "oauth_grant":  "sesión OAuth viva del conector MCP",
}

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
    ("run_history",               "Historial de corridas"),
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


# Lo único que sobrevive al reinicio TOTAL: la versión de migraciones (el
# esquema ya está en head, no hace falta re-estampar). Va explícito porque el
# alcance se deriva del catálogo — antes quedaba afuera de casualidad.
_RESET_KEEP_TABLES = frozenset({"alembic_version"})


def _fresh_install_wipe(conn) -> list[str]:
    """Vacía TODAS las tablas de la base y devuelve sus nombres.

    El alcance sale del CATÁLOGO (todo lo que existe menos _RESET_KEEP_TABLES),
    no de Base.metadata + prefijos: enumerar dejaba afuera EN SILENCIO todo lo
    que no fuera modelo ORM ni matcheara un prefijo, y se comió dos casos
    (ago-2026):
    - `signal_values_wide` / `strategy_results_wide`, el almacenamiento vivo de
      señales y estrategias desde el cutover, no son modelos (se crean con un
      MetaData propio en signal_store) y no empiezan con "sig_"/"strat_res_" →
      el reinicio "a fábrica" las dejaba POBLADAS, con filas de activos que ya
      no existían. Mismo hueco que la 0094 abrió en clean_data, arreglado allá
      y no acá.
    - Por el camino del CLI (`scripts/clean_data.py --reset` importa solo este
      servicio) `Base.metadata` está VACÍO: el reset no vaciaba ni `assets`, y
      el script informaba igual que había reiniciado la base.
    Derivar del catálogo hace que nada pueda quedar afuera y que el resultado no
    dependa de qué módulos estén importados. La contracara es que una tabla
    ajena en el mismo schema también se vacía: es lo correcto para un botón que
    promete dejar la base como recién instalada.

    El vaciado lo hace db_compat.truncate_all_tables de una sola vez, salteando
    la verificación de FK: es seguro porque se vacía TODO el grafo (nada puede
    quedar huérfano) y así se resuelve el ciclo assets ↔ markets, que un DELETE
    ordenado no podría (a diferencia de la limpieza parcial de clean_data, que
    mantiene los FK).
    """
    names = sorted(n for n in sa.inspect(conn).get_table_names()
                   if n not in _RESET_KEEP_TABLES)
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
    conservan vacías (checkfirst en la resiembra). Ese mismo reconciliador
    dropea las COLUMNAS de las anchas (reconcile_wide_columns): sin señales ni
    estrategias vivas, signal_values_wide/strategy_results_wide quedan sin
    columnas de valor. Es la diferencia con clean_data, que preserva las
    definiciones y por eso vacía las filas SIN tocar las columnas — tienen que
    seguir ahí para que "Recalcular completo" las repueble.

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
