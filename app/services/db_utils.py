"""
Utilidades de mantenimiento de BD compartidas.

CONVENCIÓN (ver CLAUDE.md): todo DELETE masivo (miles de filas o más) va por
lotes con esta función — nunca una sentencia única. Un DELETE por rango sobre
millones de filas retiene locks y genera undo durante minutos (medido: 400s+
una sola sentencia sobre signal_value, bloqueando backfills concurrentes con
1205); por lotes, cada transacción es corta y el purge de InnoDB avanza
incremental.
"""
import logging

import sqlalchemy as sa

logger = logging.getLogger(__name__)

_DEFAULT_BATCH = 5000


def delete_in_batches(session, table: str, where_sql: str,
                      params: dict | None = None,
                      batch: int = _DEFAULT_BATCH) -> int:
    """DELETE FROM {table} WHERE {where_sql}, por lotes de `batch` con commit
    por lote (MySQL/MariaDB via LIMIT; en otros dialectos —sqlite en tests—
    una sola sentencia, no soportan DELETE..LIMIT). Devuelve filas borradas.

    table y where_sql se interpolan en el SQL: SOLO strings construidos por
    el caller (nombres de tabla/columna propios, ids numéricos validados) —
    nunca input del usuario. Los valores variables van en params.
    """
    params = params or {}
    total = 0
    if session.get_bind().dialect.name in ("mysql", "mariadb"):
        stmt = sa.text(f"DELETE FROM {table} WHERE {where_sql} "
                       f"LIMIT {int(batch)}")
        while True:
            res = session.execute(stmt, params)
            session.commit()
            total += res.rowcount
            if res.rowcount < batch:
                break
    else:
        res = session.execute(
            sa.text(f"DELETE FROM {table} WHERE {where_sql}"), params)
        session.commit()
        total += res.rowcount
    if total:
        logger.info("delete_in_batches: %s filas borradas de %s", total, table)
    return total
