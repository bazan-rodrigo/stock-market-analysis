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
            q = db_compat.quote_ident(conn, t)
            before = _table_size_bytes(conn, t)
            try:
                if db_compat.is_postgres(conn):
                    conn.exec_driver_sql(f"VACUUM (FULL, ANALYZE) {q}")
                else:  # mysql / mariadb
                    conn.exec_driver_sql(f"OPTIMIZE TABLE {q}")
            except Exception as exc:
                logger.warning("VACUUM/OPTIMIZE falló en %s: %s", t, exc)
                continue
            after = _table_size_bytes(conn, t)
            sizes[t] = (before, after)
            freed += max(0, before - after)

    logger.info("Mantenimiento: %d tablas compactadas, ~%.1f MB liberados",
                len(sizes), freed / 1024 / 1024)
    return {"tables": sizes, "freed_bytes": freed, "dialect": dialect}


def vacuum_bloat_tables() -> dict:
    """Compacta las tablas propensas a bloat del pipeline (ver bloat_tables)."""
    return vacuum_tables(bloat_tables())
