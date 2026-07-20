"""Mantenimiento de la base: recuperar espacio de tuplas muertas (bloat).

VACUUM FULL (PostgreSQL) / OPTIMIZE TABLE (MySQL/MariaDB) reescriben la tabla y
DEVUELVEN al disco el espacio de las tuplas muertas que dejan los UPDATE/DELETE
(ver docs/notes/design_ind_wide_tables.md — qué es el bloat). NO borran datos.

Notas:
- No se pueden correr dentro de una transacción (Postgres) → conexión en
  AUTOCOMMIT.
- Toman un lock exclusivo por tabla mientras duran → correr en un momento
  tranquilo (el pipeline que escriba esas tablas esperaría al lock).
- sqlite (tests) no compacta por tabla: VACUUM es de toda la base.
"""
import logging

import sqlalchemy as sa

from app.database import engine
from app.services import db_compat

logger = logging.getLogger(__name__)

# Tablas fijas propensas a bloat por el churn del pipeline (además de las
# dinámicas ind_*/sig_*/strat_res_* que se descubren por prefijo).
_FIXED_BLOAT_TABLES = (
    "prices", "group_scores", "signal_eval_log", "current_indicator_values",
    "ind_asset_meta", "price_update_log",
)


def bloat_tables() -> list[str]:
    """Tablas candidatas a compactar (indicadores, señales, estrategias,
    precios, scores…). Las dinámicas se descubren por prefijo."""
    with engine.connect() as conn:
        dynamic = db_compat.list_tables_by_prefix(conn, "ind_", "sig_", "strat_res_")
        insp = sa.inspect(conn)
        fixed = [t for t in _FIXED_BLOAT_TABLES if insp.has_table(t)]
    return sorted(set(dynamic) | set(fixed))


def _table_size_bytes(conn, table: str) -> int:
    if db_compat.is_postgres(conn):
        return int(conn.execute(
            sa.text("SELECT pg_total_relation_size(:t)"), {"t": table}
        ).scalar() or 0)
    if db_compat.is_mysql(conn):
        return int(conn.execute(sa.text(
            "SELECT COALESCE(data_length + index_length, 0) "
            "FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name = :t"),
            {"t": table}).scalar() or 0)
    return 0


def vacuum_tables(tables: list[str]) -> dict:
    """VACUUM FULL (PG) / OPTIMIZE TABLE (MySQL) de `tables`. sqlite: VACUUM de
    toda la base. Devuelve {"tables": {t: (antes, después)}, "freed_bytes",
    "dialect"}."""
    dialect = engine.dialect.name

    if dialect == "sqlite":
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
            c.exec_driver_sql("VACUUM")
        return {"tables": {}, "freed_bytes": 0, "dialect": dialect}

    sizes: dict[str, tuple[int, int]] = {}
    freed = 0
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        for t in tables:
            # Las MEDICIONES van dentro del try, no solo el VACUUM: la lista de
            # tablas se arma antes de empezar y las dinámicas pueden
            # desaparecer mientras corre (signal_store dropea sig_{id}/
            # strat_res_{id} al borrar una señal o estrategia). En PostgreSQL
            # pg_total_relation_size() sobre una tabla que ya no existe LANZA
            # undefined_table — con la medición afuera, eso abortaba la corrida
            # entera y las tablas siguientes quedaban sin compactar.
            try:
                q = db_compat.quote_ident(conn, t)
                before = _table_size_bytes(conn, t)
                if db_compat.is_postgres(conn):
                    conn.exec_driver_sql(f"VACUUM (FULL, ANALYZE) {q}")
                else:  # mysql / mariadb
                    conn.exec_driver_sql(f"OPTIMIZE TABLE {q}")
                after = _table_size_bytes(conn, t)
            except Exception as exc:
                logger.warning("VACUUM/OPTIMIZE falló en %s: %s", t, exc)
                continue
            sizes[t] = (before, after)
            freed += max(0, before - after)

    logger.info("Mantenimiento: %d tablas compactadas, ~%.1f MB liberados",
                len(sizes), freed / 1024 / 1024)
    return {"tables": sizes, "freed_bytes": freed, "dialect": dialect}


def vacuum_bloat_tables() -> dict:
    """Compacta las tablas propensas a bloat del pipeline (ver bloat_tables)."""
    return vacuum_tables(bloat_tables())


# ── Reporte de uso de espacio ─────────────────────────────────────────────────

def format_bytes(n) -> str:
    """Bytes → texto legible ('181.0 MB', '4.1 GB'). Puro (testeable)."""
    x = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if x < 1024 or unit == "TB":
            return f"{int(x)} {unit}" if unit == "B" else f"{x:.1f} {unit}"
        x /= 1024


def classify_table(name: str) -> str:
    """Familia a la que pertenece una tabla, para el desglose de espacio.
    Puro (testeable): fija que ind_dist_sma50 → Indicadores, sig_3 → Señales,
    strat_res_2 → Estrategias, etc. El orden de los chequeos importa."""
    n = name.lower()
    if n == "prices":
        return "Precios"
    if n.startswith("ind_") or n in (
            "current_indicator_values", "indicator_definitions",
            "indicator_update_log"):
        return "Indicadores"
    if n.startswith("sig_") or n in (
            "signal", "signal_value", "group_signal_value", "signal_eval_log"):
        return "Señales"
    if n.startswith("strat_res_") or n in (
            "strategy", "strategy_component", "strategy_result"):
        return "Estrategias"
    if n == "group_scores":
        return "Scores de grupo"
    if n.startswith("fundamental"):
        return "Fundamentales"
    if n.startswith("backtest") or n.startswith("portfolio"):
        return "Backtest / Carteras"
    return "Otras"


def group_by_family(tables: list[tuple[str, int]]) -> list[dict]:
    """Agrupa (tabla, bytes) por familia → filas {family, count, bytes}
    ordenadas por bytes desc. Puro (testeable)."""
    acc: dict[str, dict] = {}
    for name, size in tables:
        fam = classify_table(name)
        row = acc.setdefault(fam, {"family": fam, "count": 0, "bytes": 0})
        row["count"] += 1
        row["bytes"] += int(size or 0)
    return sorted(acc.values(), key=lambda r: r["bytes"], reverse=True)


def _all_table_sizes(conn) -> list[tuple[str, int]]:
    """(tabla, bytes) de todas las tablas base del esquema actual."""
    if db_compat.is_postgres(conn):
        rows = conn.execute(sa.text(
            "SELECT c.relname, pg_total_relation_size(c.oid) "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'r'"))
        return [(r[0], int(r[1] or 0)) for r in rows]
    if db_compat.is_mysql(conn):
        rows = conn.execute(sa.text(
            "SELECT table_name, COALESCE(data_length + index_length, 0) "
            "FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE'"))
        return [(r[0], int(r[1] or 0)) for r in rows]
    return []  # sqlite (tests): sin tamaño por tabla


def database_size_report(top_n: int = 25) -> dict:
    """Uso de espacio de la base: total, desglose por familia y top-N tablas.

    Devuelve {"total_bytes", "by_family": [{family,count,bytes}],
    "tables": [(nombre, bytes)], "dialect"}. Solo lectura (metadata)."""
    dialect = engine.dialect.name
    with engine.connect() as conn:
        if db_compat.is_postgres(conn):
            total = int(conn.execute(sa.text(
                "SELECT pg_database_size(current_database())")).scalar() or 0)
        elif db_compat.is_mysql(conn):
            total = int(conn.execute(sa.text(
                "SELECT COALESCE(SUM(data_length + index_length), 0) "
                "FROM information_schema.tables "
                "WHERE table_schema = DATABASE()")).scalar() or 0)
        else:
            total = 0
        tables = _all_table_sizes(conn)

    tables.sort(key=lambda t: t[1], reverse=True)
    return {
        "total_bytes": total,
        "by_family": group_by_family(tables),
        "tables": tables[:top_n],
        "dialect": dialect,
    }
